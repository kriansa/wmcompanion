# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=missing-module-docstring
from asyncio import sleep
from wmcompanion import use, on
from wmcompanion.utils.process import cmd
from wmcompanion.modules.notifications import Notify, Urgency
from wmcompanion.events.power import PowerActions


@on(PowerActions)
@use(Notify)
async def battery_level_warning(status: dict, notify: Notify):
    """
    Notify when the battery is below 10% and automatically hibernates whenever it reaches 5%

    Depedencies: systemd
    """
    ignore_battery_statuses = [
        PowerActions.BatteryStatus.CHARGING,
        PowerActions.BatteryStatus.FULL,
    ]

    if (
        status["event"] != PowerActions.Events.BATTERY_LEVEL_CHANGE
        or status["battery-status"] in ignore_battery_statuses
    ):
        return

    level = status["battery-level"]
    if level > 10:
        return

    if level > 5:
        await notify(
            f"Battery is low ({level}%)",
            "System will hibernate automatically at 5%",
            urgency=Urgency.NORMAL,
            dunst_stack_tag="low-battery-warn",
            icon="battery-level-10-symbolic",
        )
    else:
        await notify(
            "Hibernating in 5 seconds...",
            urgency=Urgency.CRITICAL,
            dunst_stack_tag="low-battery-warn",
            icon="battery-level-0-symbolic",
        )
        await sleep(5)
        await cmd("systemctl", "hibernate")
