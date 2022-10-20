# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=missing-module-docstring
from wmcompanion import use, on
from wmcompanion.utils.process import cmd
from wmcompanion.events.x11 import DeviceState


@on(DeviceState)
async def configure_inputs(status: dict):
    """
    Configure my input devices, such as mice and keyboards

    Dependencies: xset and xinput
    """

    if status["event"] != DeviceState.ChangeEvent.INPUT_CHANGE or "added" not in status["inputs"]:
        return

    for device in status["inputs"]["added"]:
        dev_id = str(device["id"])

        # Setup all my keyboards with two layouts, with CAPS LOCK as the layout toggle shortcut
        # Also set a lower key repeat rate
        if device["type"] == DeviceState.InputType.SLAVE_KEYBOARD:
            await cmd(
                "setxkbmap",
                "-model", "pc104",
                "-layout", "us,us",
                "-variant", ",alt-intl",
                "-option", "", "-option", "grp:caps_toggle",
            )
            await cmd("xset", "r", "rate", "300", "30")

        elif device["type"] == DeviceState.InputType.SLAVE_POINTER:
            # Configure my mouse
            if "Razer DeathAdder" in device["name"]:
                await cmd("xinput", "set-prop", dev_id, "libinput Accel Speed", "-0.800000")

            # And my trackpad
            elif "Touchpad" in device["name"]:
                await cmd("xinput", "set-prop", dev_id, "libinput Tapping Enabled", "1")
                await cmd("xinput", "set-prop", dev_id, "libinput Natural Scrolling Enabled", "1")
                await cmd("xinput", "set-prop", dev_id, "libinput Tapping Drag Lock Enabled", "1")
