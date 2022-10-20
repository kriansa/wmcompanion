# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=missing-module-docstring
from types import SimpleNamespace
from wmcompanion import use, on
from wmcompanion.modules.polybar import Polybar
from wmcompanion.events.bluetooth import BluetoothRadioStatus
from wmcompanion.events.notifications import DunstPausedStatus
from wmcompanion.events.keyboard import KbddChangeLayout
from wmcompanion.events.audio import MainVolumeLevel
from wmcompanion.events.network import WifiStatus, NetworkConnectionStatus

# Setup few colors that I like to use on my setup
colors = SimpleNamespace(BAR_FG="#F2F5EA", BAR_DISABLED="#2E5460")

@on(BluetoothRadioStatus)
@use(Polybar)
async def bluetooth_status(status: dict, polybar: Polybar):
    """
    Show the bluetooth status icon on Polybar

    This requires you to setup a polybar module using `custom/ipc` as the type
    """

    icon_color = colors.BAR_FG if status["enabled"] else colors.BAR_DISABLED
    await polybar("bluetooth", polybar.fmt("", color=icon_color))

@on(DunstPausedStatus)
@use(Polybar)
async def dunst_status(status: dict, polybar: Polybar):
    """
    Show the dunst status icon on Polybar

    This requires you to setup a polybar module using `custom/ipc` as the type

    Dependencies: dunst
    """

    if status["paused"]:
        content = polybar.fmt("", color=colors.BAR_DISABLED)
    else:
        content = polybar.fmt("", color=colors.BAR_FG)

    await polybar("dunst", content)

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

    await polybar("kbdd", polybar.fmt("", color=colors.BAR_FG), output)

@on(WifiStatus)
@use(Polybar)
async def wifi_status(status: dict, polybar: Polybar):
    """
    Show the wifi signal and status icon on Polybar
    """

    if status["connected"]:
        color = colors.BAR_FG
        label = f"{status['strength']}%"
    elif not status["enabled"]:
        color = colors.BAR_DISABLED
        label = ""
    else:
        color = colors.BAR_FG
        label = ""

    await polybar("wlan", polybar.fmt("", color=color), label)

@on(NetworkConnectionStatus, connection_name="Wired-Network")
@use(Polybar)
async def network_status(status: dict, polybar: Polybar):
    """
    Show the Wired-Network connection status icon on Polybar

    Dependencies: NetworkManager
    """
    color = colors.BAR_FG if status["connected"] else colors.BAR_DISABLED
    await polybar("eth", polybar.fmt("", color=color))

@on(MainVolumeLevel)
@use(Polybar)
async def volume_level(volume: dict, polybar: Polybar):
    """
    Show both speaker and mic volume level and status icon on Polybar

    Dependencies: PipeWire, WirePlumber
    """
    async def render(polybar_module, icon_on, icon_muted, volume):
        if not volume["available"]:
            return await polybar(polybar_module, "")

        if not volume["muted"]:
            icon = icon_on
            color = colors.BAR_FG
        else:
            icon = icon_muted
            color = colors.BAR_DISABLED

        level = int(volume['level'] * 100)
        await polybar(polybar_module, polybar.fmt(f"{icon} {level}%", color=color))

    await render("mic", "", "", volume["input"])
    await render("speaker", "", "", volume["output"])
