# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=missing-module-docstring
from pathlib import Path
from wmcompanion import use, on
from wmcompanion.utils.process import cmd
from wmcompanion.modules.notifications import Notify, Urgency
from wmcompanion.events.x11 import DeviceState


@on(DeviceState)
@use(Notify)
async def configure_screens(status: dict, notify: Notify):
    """
    Configure our screen layouts using Xrandr

    Dependencies: xrandr and feh
    """

    if status["event"] != DeviceState.ChangeEvent.SCREEN_CHANGE:
        return

    match status["screens"]:
        # Single monitor
        # If it's a single monitor (most cases) then layouts don't matter, it will always be
        # assigned as the primary
        case [{"output": output, "edid_hash": _}]:
            await cmd("xrandr", "--output", output, "--preferred", "--primary")

        # Configured layouts
        # Notice that we also match the monitor EDID so that we have unique configurations per
        # monitor, in case we have a laptop and we connect to different monitors like office or home
        case [
            {"output": "eDP-1", "edid_hash": "7B59785F"},
            {"output": "HDMI-1", "edid_hash": "E65018AA"},
        ]:
            await cmd(
                "xrandr",
                "--output", "HDMI-1", "--preferred", "--primary", "--pos", "0x0",
                "--output", "eDP-1", "--preferred", "--pos", "3440x740",
            )

        # No monitors - we turn everything off
        case []:
            return await cmd("xrandr", "--output", "eDP-1", "--off", "--output", "HDMI-1", "--off")

        # Layout not configured
        # Then we just notify the user to do a manual configuration
        case _:
            await notify(
                "Monitor combination not configured",
                "Run 'Arandr' to configure it manually.",
                urgency=Urgency.CRITICAL,
            )

    # Start/reload polybar to switch the monitor/size if needed
    # await cmd("systemctl", "reload-or-restart", "--user", "polybar")

    # Apply background
    await cmd(
        "feh",
        "--bg-fill",
        "--no-fehbg",
        Path.home().joinpath("Wallpapers/mountains.png"),
    )
