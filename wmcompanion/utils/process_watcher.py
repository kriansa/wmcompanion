# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import asyncio, asyncio.subprocess
from logging import getLogger

logger = getLogger(__name__)

class ProcessWatcher:
    """
    Watches a process asynchronously, restarting it if it ends unexpectedly, and restarting it
    automatically if `restart_every` is set.
    """

    def __init__(self, exec_args: list[str], restart_every: int|None = None, retries: int = 5):
        self.exec_args = exec_args
        self.restart_every = restart_every
        self.retries = retries
        self.loop_tasks = set()
        self.stopped = False
        self.retry_attempts = 0

    def on_start(self, callback: asyncio.coroutine):
        self.start_callback = callback

    def on_failure(self, callback: asyncio.coroutine):
        self.failure_callback = callback

    async def restart(self):
        await self.stop()
        await self.start()

    async def watch(self):
        await self.proc.wait()

        # Checks if the process died because we wanted it to (by calling `stop()`) then don't
        # try to restart it.
        if self.stopped:
            return

        if self.retry_attempts < self.retries:
            self.retry_attempts += 1
            logger.warning(f"Process {self.exec_args[0]} has died unexpectedly. Restarting... ({self.retry_attempts}/{self.retries})")
            await asyncio.sleep(1)
            await self.start()
        else:
            logger.error(f"Process {self.exec_args[0]} has reached the restart threshold...")
            await self.failure_callback()

    def _add_to_loop(self, coro: asyncio.coroutine):
        task = asyncio.get_running_loop().create_task(coro)
        # Add the coroutine to the set, creating a strong reference and preventing it from being
        # garbage-collected before it's finished
        self.loop_tasks.add(task)
        # But then ensure we clear its reference after it's done
        task.add_done_callback(self.loop_tasks.discard)

    async def start(self):
        self.proc = await asyncio.create_subprocess_exec(
            "/usr/bin/env", *self.exec_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._add_to_loop(self.watch())
        self._add_to_loop(self.start_callback(self.proc))

    async def stop(self):
        self.proc.kill()

        # `watch()` is holding `proc.wait()`, therefore as soon as the process is killed it will
        # understand as the process died if we don't let it know that we purposefully killed it and
        # it should not restart it.
        self.stopped = True
