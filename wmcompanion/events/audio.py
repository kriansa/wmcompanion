# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
from typing import Coroutine
from pathlib import Path
from decimal import Decimal
from ..utils.inotify_simple import INotify, Flags as INotifyFlags
from ..utils.process import ProcessWatcher
from ..event_listening import EventListener
from ..errors import WMCompanionFatalError


class MainVolumeLevel(EventListener):
    """
    Reacts to the main volume source/sink level changes.
    Uses wireplumber in order to do so, and be able to react to default sink/source changes.
    """

    wp_state_file: Path = Path("~/.local/state/wireplumber/default-nodes").expanduser()
    volume_output: Decimal = None
    volume_input: Decimal = None
    restart_watcher: callable = None
    inotify: INotify = None

    AUDIO_DIRECTION_INPUT = "@DEFAULT_SOURCE@"
    AUDIO_DIRECTION_OUTPUT = "@DEFAULT_SINK@"

    async def set_volume(self, direction, level, muted, available):
        """
        Triggers a volume change event
        """
        volume = {"level": level, "muted": muted, "available": available}
        if direction == self.AUDIO_DIRECTION_OUTPUT:
            self.volume_output = volume
        else:
            self.volume_input = volume

        await self.trigger({"input": self.volume_input, "output": self.volume_output})

    def wp_statefile_changed(self):
        """
        This is a callback that gets called every time a change on WirePlumber's state file is
        detected, meaning we need to restart the Lua volume watcher daemon.
        """
        for event in self.inotify.read():
            if "default-nodes" in event.name:
                # Restarting the watcher will re-read all volumes
                self.run_coro(self.restart_watcher())
                return

    async def run_volume_watcher(self):
        """
        Run a separate daemon that listen for wireplumber volume change events so we can pick them
        up and trigger wmcompanion events.
        """
        cmd = [
            "wpexec",
            Path(__file__).parent.joinpath("libexec/wireplumber-volume-watcher.lua"),
        ]
        watcher = ProcessWatcher(cmd, restart_every=3600)
        self.restart_watcher = watcher.restart

        async def read_events(proc: Coroutine):
            while line := await proc.stdout.readline():
                direction, level, muted, available = (
                    line.decode("ascii").strip().split(":")
                )
                direction = (
                    self.AUDIO_DIRECTION_OUTPUT
                    if "output" == direction
                    else self.AUDIO_DIRECTION_INPUT
                )
                level = Decimal(level)
                muted = muted == "true"
                available = available == "true"

                await self.set_volume(direction, level, muted, available)

        async def on_fail():
            raise WMCompanionFatalError(
                "wireplumber-volume-watcher.lua initialization failed"
            )

        watcher.on_start(read_events)
        watcher.on_failure(on_fail)
        await watcher.start()

    async def start(self):
        # Initial values for volume
        self.volume_input = self.volume_output = {
            "level": 0,
            "muted": False,
            "available": False,
        }
        # Add a watcher for wireplumber state file so we can get to know when the default
        # input/output devices have changed and act upon it
        self.inotify = INotify()
        self.inotify.add_watch(self.wp_state_file.parent, INotifyFlags.CREATE)
        # Then we add the IO file to the event loop
        asyncio.get_running_loop().add_reader(self.inotify, self.wp_statefile_changed)

        # Then we start the volume watcher subprocess using wireplumber's wpexec engine
        await self.run_volume_watcher()
