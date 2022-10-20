# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=missing-module-docstring
from wmcompanion import use, on
from wmcompanion.utils.process import cmd
from wmcompanion.events.power import PowerActions


@on(PowerActions)
async def set_energy_profile(status: dict):
    """
    Automatically set the energy profile based on the power source. Very useful for laptops.

    Dependencies: cpupower, xset and xbacklight
    """
    if status["event"] not in [
        PowerActions.Events.INITIAL_STATE,
        PowerActions.Events.POWER_SOURCE_SWITCH,
        PowerActions.Events.RETURN_FROM_SLEEP,
    ]:
        return

    if status["power-source"] == PowerActions.PowerSource.AC:
        cpu_governor = "performance"
        screen_saver = "300"
        backlight = "70"
    elif status["power-source"] == PowerActions.PowerSource.BATTERY:
        cpu_governor = "powersave"
        screen_saver = "60"
        backlight = "30"

    await cmd("sudo", "cpupower", "frequency-set", "-g", cpu_governor)

    # xset s <timeout> <cycle>
    # The meaning of these values are that timeout is how much time after idling it will trigger the
    # ScreenSaver ON, while the cycle is, after screen saver being on, how often it will trigger its
    # cycle event, originally meant for changing background patterns to avoid burn-in, but nowadays
    # it's used to flag `xss-lock` that the locker can be executed -- otherwise, `xss-lock` will
    # only execute the `notify` application. See more on xss-lock(1).
    #
    # Recommendation: Keep the second parameter the amount of time that the dimmer (notify app for
    # `xss-lock`) needs to fade out completely before showing the locker - usually 5 seconds.
    await cmd("xset", "s", screen_saver, "5")
    await cmd("xbacklight", "-ctrl", "intel_backlight", "-set", backlight)
