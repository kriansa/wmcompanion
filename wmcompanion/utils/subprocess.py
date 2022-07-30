# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
from logging import getLogger

logger = getLogger(__name__)

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
