# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=missing-module-docstring
from asyncio import get_running_loop, sleep
from wmcompanion import on
from wmcompanion.utils.process import cmd
from wmcompanion.events.power import LogindIdleStatus


IDLE_TIMER: "async.Task" = None

@on(LogindIdleStatus)
async def suspend_when_idle(status: dict):
    """
    Automatically suspends the system when we idle for over 20 minutes.

    This is only possible when using `xss-lock`, a tool that intercepts X11 ScreenSaver and helps
    with locking the session, as well as telling `logind` that the system is idle. With that
    information you can either configure systemd-logind `logind.conf` so that it automatically
    perform an action after a certain time, or you can use this hook to do it programatically and
    leveraging other system variables such as power source, for instance.

    Dependencies: xss-lock
    """
    global IDLE_TIMER  # pylint: disable=global-statement
    if IDLE_TIMER:
        IDLE_TIMER.cancel()
        IDLE_TIMER = None

    if status["idle"]:
        async def sleep_then_suspend():
            await sleep(20 * 60)
            await cmd("systemctl", "suspend")
        IDLE_TIMER = get_running_loop().create_task(sleep_then_suspend)
