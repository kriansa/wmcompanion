# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=missing-module-docstring
from wmcompanion import on
from wmcompanion.utils.process import cmd
from wmcompanion.events.power import PowerActions


@on(PowerActions)
async def power_menu(status: dict):
    """
    Opens up a different power menu by pressing the power button
    """
    if status["event"] == PowerActions.Events.POWER_BUTTON_PRESS:
        await cmd("my-rofi-power-menu")
