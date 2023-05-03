# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import zlib
import pickle
from typing import Coroutine
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

    previous_trigger_checksum: dict = None

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
        self.previous_trigger_checksum = {}
        cmd = [
            "python",
            Path(__file__).parent.joinpath("libexec/x11_device_watcher.py"),
        ]
        watcher = ProcessWatcher(cmd, restart_every=3600)
        watcher.on_start(self.read_events)
        watcher.on_failure(self.on_failure)
        await watcher.start()

    async def read_events(self, proc: Coroutine):
        """
        Reads and processes any event coming from X11 Device Watcher daemon
        """
        while line := await proc.stdout.readline():
            event = json.loads(line.decode("utf-8"))

            # Detect and prevent duplicate events.
            #
            # Although the duplication detection already exists at EventListener, it only works for
            # events of the same kind, but because this class treats two kinds of changes (input OR
            # screens) as if they were only one, then it won't help and we need to do the work on
            # this class.
            #
            # We do the detection by checking the `state.active` key, where active input and screens
            # are stored and thus the key to determine whether this is a duplicate event based on
            # the last one triggered.
            #
            # This duplicate prevention is very important because by default the X11 helper process
            # gets restarted every hour, and each time it starts, the entire state is resent as an
            # event, but no necessarily a change would happen.
            trigger_checksum = zlib.adler32(pickle.dumps(event["state"]["active"]))
            if trigger_checksum == self.previous_trigger_checksum.get(event["action"]):
                continue

            self.previous_trigger_checksum[event["action"]] = trigger_checksum

            match event["action"]:
                case "screen-change":
                    await self.trigger(
                        {
                            "event": self.ChangeEvent.SCREEN_CHANGE,
                            "screens": event["state"]["active"],
                        },
                        allow_duplicate_events=True,
                    )

                case "input-change":
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
