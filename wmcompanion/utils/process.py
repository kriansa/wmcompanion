# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import asyncio, asyncio.subprocess
from datetime import datetime, timedelta
from logging import getLogger

logger = getLogger(__name__)

class ProcessWatcher:
    """
    Watches a process asynchronously, restarting it if it ends unexpectedly, and restarting it
    automatically if `restart_every` is set.
    """

    def __init__(
            self,
            exec_args: list[str],
            restart_every: int|None = None,
            retries: int = 5,
            retry_threshold_seconds: int = 30,
        ):
        self.exec_args = exec_args
        self.restart_every = restart_every
        self.retries = retries
        self.retry_threshold_seconds = retry_threshold_seconds
        self.loop_tasks = set()
        self.stopped = False
        self.retry_attempts = 0
        self.last_restarted_at = 0

    def on_start(self, callback: asyncio.coroutine):
        self.start_callback = callback

    def on_failure(self, callback: asyncio.coroutine):
        self.failure_callback = callback

    async def restart(self):
        await self.stop()
        await self.start()

    async def watch(self):
        await self.proc.wait()

        # Reset restart ticks if it's over the threshold
        restart_delta = datetime.now() - timedelta(seconds=self.retry_threshold_seconds)
        if self.last_restarted_at and self.last_restarted_at <= restart_delta:
            self.retry_attempts = 0

        # Checks if the process died because we wanted it to (by calling `stop()`) then don't
        # try to restart it.
        if self.stopped:
            return

        if self.retry_attempts < self.retries:
            self.retry_attempts += 1
            logger.warning(f"Process {self.exec_args[0]} died unexpectedly. Restarting... ({self.retry_attempts}/{self.retries})")
            await asyncio.sleep(2 ** self.retry_attempts)
            self.last_restarted_at = datetime.now()
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

    async def auto_restart(self):
        if not self.restart_every:
            return

        await asyncio.sleep(self.restart_every)
        logger.debug(f"Automatically restarting process {self.exec_args[0]}...")
        await self.restart()

    async def start(self):
        self.proc = await asyncio.create_subprocess_exec(
            "/usr/bin/env", *self.exec_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        logger.debug(f"Process {self.exec_args[0]} started.")
        self.stopped = False

        self._add_to_loop(self.start_callback(self.proc))
        self._add_to_loop(self.auto_restart())
        self._add_to_loop(self.watch())

    async def stop(self):
        # `watch()` is holding `proc.wait()`, therefore as soon as the process is killed it will
        # understand as the process died if we don't let it know that we purposefully killed it and
        # it should not restart it.
        self.stopped = True

        self.proc.kill()
        await self.proc.wait()
        logger.debug(f"Process {self.exec_args[0]} stopped.")

async def cmd(cmd: str, *args: list[str], env: dict = None, output_encoding: str = "utf-8"):
    """
    Run a command in the existing thread event loop and return its return code and outputs.
    """
    proc = await asyncio.create_subprocess_exec(
        cmd, *args, env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        stderr_str = stderr.decode(output_encoding).strip()
        logger.warn(f"Process '{cmd}' returned {proc.returncode}: {stderr_str}")

    return dict(
        rc=proc.returncode,
        stderr=stderr.decode(output_encoding),
        stdout=stdout.decode(output_encoding),
    )

async def shell(cmd: str, env: dict = None, output_encoding: str = "utf-8"):
    """
    Run a shell command in the existing thread event loop and return its return code and outputs.
    """
    proc = await asyncio.create_subprocess_shell(
        cmd, env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        stderr_str = stderr.decode(output_encoding).strip()
        logger.warn(f"Shell command '{cmd}' returned {proc.returncode}: {stderr_str}")

    return dict(
        rc=proc.returncode,
        stderr=stderr.decode(output_encoding),
        stdout=stdout.decode(output_encoding),
    )
