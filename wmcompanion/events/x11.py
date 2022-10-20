# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import zlib
import pickle
from pathlib import Path
from enum import Enum
from ..event_listening import EventListener
from ..utils.process import ProcessWatcher
from ..errors import WMCompanionFatalError

logger = logging.getLogger(__name__)


class DeviceState(EventListener):
    """
    Listen for X11 input device and screen changes, making it easy for configuring devices using
    xinput and screen resolution with xrandr.
    """

    previous_trigger_checksum: str = ""

    class ChangeEvent(Enum):
        """
        The kind of change a given event is related to
        """

        SCREEN_CHANGE = "screen-change"
        INPUT_CHANGE = "input-change"

    class InputType(Enum):
        """
        Input type of a INPUT_CHANGE event
        """

        MASTER_POINTER = "master-pointer"
        MASTER_KEYBOARD = "master-keyboard"
        SLAVE_POINTER = "slave-pointer"
        SLAVE_KEYBOARD = "slave-keyboard"
        FLOATING_SLAVE = "floating-slave"

    async def start(self):
        cmd = [
            "python",
            Path(__file__).parent.joinpath("libexec/x11_device_watcher.py"),
        ]
        watcher = ProcessWatcher(cmd, restart_every=3600)
        watcher.on_start(self.read_events)
        watcher.on_failure(self.on_failure)
        await watcher.start()

    async def read_events(self, proc: "asyncio.coroutine"):
        """
        Reads and processes any event coming from X11 Device Watcher daemon
        """
        while line := await proc.stdout.readline():
            event = json.loads(line.decode("utf-8"))
            match event["action"]:
                case "screen-change":
                    await self.trigger(
                        {
                            "event": self.ChangeEvent.SCREEN_CHANGE,
                            "screens": event["state"]["active"],
                        }
                    )

                case "input-change":
                    # When handling input changes, ensure that we only use the active-inputs as the
                    # unique key for comparing past events, as there is the possibility of this
                    # being triggered twice even with no change in the existing device tree (eg.
                    # when the process is restarted and the state is resent)
                    unique_key = event["state"]["active"]
                    trigger_checksum = zlib.adler32(pickle.dumps(unique_key))
                    if trigger_checksum != self.previous_trigger_checksum:
                        self.previous_trigger_checksum = trigger_checksum
                        await self.trigger(
                            {
                                "event": self.ChangeEvent.INPUT_CHANGE,
                                "inputs": event["state"],
                            },
                            allow_duplicate_events=True,
                        )

                case "error":
                    logger.error(
                        "x11_device_watcher error: %s", "".join(event["error"])
                    )

    async def on_failure(self):
        """
        Callback for failures on X11 Device Watcher daemon
        """
        raise WMCompanionFatalError(
            "x11_device_watcher run failed, please check the logs"
        )
