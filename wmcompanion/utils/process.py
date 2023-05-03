# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import asyncio.subprocess
from typing import Coroutine
from datetime import datetime, timedelta
from logging import getLogger

logger = getLogger(__name__)


class ProcessWatcher:  # pylint: disable=too-many-instance-attributes
    """
    Watches a process asynchronously, restarting it if it ends unexpectedly, and restarting it
    automatically if `restart_every` is set.
    """

    def __init__(
        self,
        exec_args: list[str],
        restart_every: int | None = None,
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
        self.start_callback = lambda: None
        self.failure_callback = lambda: None
        self.proc = None

    def on_start(self, callback: Coroutine):
        """
        Sets a callback to be called when the process starts
        """
        self.start_callback = callback

    def on_failure(self, callback: Coroutine):
        """
        Sets a callback to be called when the process execution fails
        """
        self.failure_callback = callback

    async def start(self):
        """
        Starts the process, then automatically restarts it on the specified timeout or when there's
        a failure
        """
        self.proc = await asyncio.create_subprocess_exec(
            "/usr/bin/env",
            *self.exec_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        logger.debug("Process %s started.", self.exec_args[0])
        self.stopped = False

        self._add_to_loop(self.start_callback(self.proc))
        self._add_to_loop(self._auto_restart())
        self._add_to_loop(self._watch())

    async def stop(self):
        """
        Stops the process and the automatic restart watcher
        """
        # `watch()` is holding `proc.wait()`, therefore as soon as the process is killed it will
        # understand as the process died if we don't let it know that we purposefully killed it and
        # it should not restart it.
        self.stopped = True

        self.proc.kill()
        await self.proc.wait()
        logger.debug("Process %s stopped.", self.exec_args[0])

    async def restart(self):
        """
        Restarts the process
        """
        await self.stop()
        await self.start()

    async def _watch(self):
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
            logger.warning(
                "Process %s died unexpectedly. Restarting... (%s/%s)",
                self.exec_args[0],
                self.retry_attempts,
                self.retries,
            )
            await asyncio.sleep(2**self.retry_attempts)
            self.last_restarted_at = datetime.now()
            await self.start()
        else:
            logger.error(
                "Process %s has reached the restart threshold...",
                self.exec_args[0],
            )
            await self.failure_callback()

    def _add_to_loop(self, coro: Coroutine):
        task = asyncio.get_running_loop().create_task(coro)
        # Add the coroutine to the set, creating a strong reference and preventing it from being
        # garbage-collected before it's finished
        self.loop_tasks.add(task)
        # But then ensure we clear its reference after it's done
        task.add_done_callback(self.loop_tasks.discard)

    async def _auto_restart(self):
        if not self.restart_every:
            return

        await asyncio.sleep(self.restart_every)
        logger.debug("Automatically restarting process %s...", self.exec_args[0])
        await self.restart()


async def cmd(
    command: str, *args: list[str], env: dict = None, output_encoding: str = "utf-8"
):
    """
    Run a command in the existing thread event loop and return its return code and outputs.
    """
    proc = await asyncio.create_subprocess_exec(
        command,
        *args,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.warning(
            "Process '%s' returned %i: %s",
            command,
            proc.returncode,
            stderr.decode(output_encoding).strip(),
        )

    return dict(
        rc=proc.returncode,
        stderr=stderr.decode(output_encoding),
        stdout=stdout.decode(output_encoding),
    )


async def shell(command: str, env: dict = None, output_encoding: str = "utf-8"):
    """
    Run a shell command in the existing thread event loop and return its return code and outputs.
    """
    proc = await asyncio.create_subprocess_shell(
        command,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.warning(
            "Shell command '%s' returned %i: %s",
            command,
            proc.returncode,
            stderr.decode(output_encoding).strip(),
        )

    return dict(
        rc=proc.returncode,
        stderr=stderr.decode(output_encoding),
        stdout=stdout.decode(output_encoding),
    )
