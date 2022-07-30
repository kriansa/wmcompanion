# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import asyncio, os
from decimal import Decimal
from ..utils.dbus_client import DBusClient
from ..utils.inotify_simple import INotify, flags as INotifyFlags
from ..utils.process_watcher import ProcessWatcher
from ..event_listening import EventListener

class MainVolumeLevel(EventListener):
    """
    Reacts to the main volume source/sink level changes.
    Uses wireplumber in order to do so, and be able to react to default sink/source changes.
    """
    wp_state_file: str = os.path.expanduser("~/.local/state/wireplumber/default-nodes")

    AUDIO_DIRECTION_INPUT = "@DEFAULT_SOURCE@"
    AUDIO_DIRECTION_OUTPUT = "@DEFAULT_SINK@"

    async def set_volume(self, direction, level, muted, available):
        volume = { "level": level, "muted": muted, "available": available }
        if direction == self.AUDIO_DIRECTION_OUTPUT:
            self.volume_output = volume
        else:
            self.volume_input = volume

        await self.trigger({ "input": self.volume_input, "output": self.volume_output })

    def state_changed(self):
        for event in self.inotify.read():
            if "default-nodes" in event.name:
                # Restarting the watcher will re-read all volumes
                self.run_coro(self.restart_watcher())
                return

    async def run_volume_watcher(self):
        cmd = [
            "wpexec",
            os.path.dirname(__file__) + "/wireplumber-volume-watcher.lua",
        ]

        pw = ProcessWatcher(cmd, restart_every=3600, retries=3)
        self.restart_watcher = pw.restart

        async def read_events(proc):
            while line := await proc.stdout.readline():
                direction, level, muted, available = line.decode("ascii").strip().split(":")
                direction = self.AUDIO_DIRECTION_OUTPUT if "output" == direction else self.AUDIO_DIRECTION_INPUT
                level = Decimal(level)
                muted = muted == "true"
                available = available == "true"

                await self.set_volume(direction, level, muted, available)

        async def on_fail():
            raise CompanionFatalException("wireplumber-volume-watcher.lua failed multiple times")

        pw.on_start(read_events)
        pw.on_failure(on_fail)
        await pw.start()

    async def start(self):
        # Initial values for volume
        self.volume_input = self.volume_output = { "level": 0, "muted": False, "available": False }
        # Add a watcher for wireplumber state file so we can get to know when the default
        # input/output devices have changed and act upon it
        self.inotify = INotify()
        self.inotify.add_watch(os.path.dirname(self.wp_state_file), INotifyFlags.CREATE)
        # Then we add the IO file to the event loop
        asyncio.get_running_loop().add_reader(self.inotify, self.state_changed)

        # Then we start the volume watcher subprocess using wireplumber's wpexec engine
        await self.run_volume_watcher()
