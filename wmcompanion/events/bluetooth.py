# Copyright (c) 2022 Daniel Pereira
# 
# SPDX-License-Identifier: Apache-2.0

import asyncio, subprocess, re
from systemd import journal
from ..event import EventListener

class BluetoothRadioStatus(EventListener):
    """
    Reacts to bluetooth radio status changes
    """
    async def start(self):
        self.reader = journal.Reader()
        self.reader.this_boot()
        self.reader.seek_tail()
        self.reader.add_match(SYSLOG_IDENTIFIER="rfkill")

        # It seems odd manipulating the event loop manually, but the reason is because Python
        # asyncio doesn't natively support file I/O, so we could either use an external library or
        # simply add a fd reader as part of the loop and running its callback asynchronously.
        asyncio.get_running_loop().add_reader(
            self.reader.fileno(),
            lambda: self.run_coro(self.process_line()),
        )

        await self.set_initial_status()

    async def process_line(self):
        self.reader.process()
        for entry in self.reader:
            # Messages from rfkill are like these:
            # block/unblock set for type bluetooth
            if "bluetooth" in entry["MESSAGE"]:
                bluetooth_radio_enabled = entry["MESSAGE"][0:7] == "unblock"
                await self.trigger({ "enabled": bluetooth_radio_enabled })

    async def set_initial_status(self):
        # Get bluetooth status
        output = subprocess.run(["rfkill", "list", "bluetooth"], capture_output=True)
        stdout = output.stdout.decode("ascii")
        bluetooth_radio_enabled = \
            re.search("Soft blocked: (?P<blocked>yes|no)", stdout).group('blocked') == "no"

        await self.trigger({ "enabled": bluetooth_radio_enabled })
