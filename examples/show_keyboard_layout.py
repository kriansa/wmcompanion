# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=missing-module-docstring
from wmcompanion import use, on
from wmcompanion.modules.polybar import Polybar
from wmcompanion.events.keyboard import KbddChangeLayout

@on(KbddChangeLayout)
@use(Polybar)
async def kbdd_layout(layout: dict, polybar: Polybar):
    """
    Show an icon of the current selected keyboard layout on your Polybar

    This requires you to setup a polybar module using `custom/ipc` as the type

    Dependencies: kbdd
    """

    layout_mappings = ["U.S.", "INT."]
    layout_id = layout["id"]

    if len(layout_mappings) >= layout_id + 1:
        output = layout_mappings[layout_id]
    else:
        output = f"Unknown: {layout}"

    await polybar("kbdd", polybar.fmt("", color="#F2F5EA"), output)
