# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
import glob
import struct
import logging
from contextlib import suppress
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from ..errors import WMCompanionError

logger = logging.getLogger(__name__)

class Polybar:
    """
    Set of functionality to interact with polybar modules. Uses ipc functionality available on
    Polybar >= 3.5 to communicate with the daemon and change module values at runtime.

    To use this module properly, you can simply call `set_module_content()` and pass the module name
    and the content you want to override on Polybar. On Polybar config file, you must state that the
    given module is a `custom/ipc` as the example below:

    ```ini
    [module/eth]
    type = custom/ipc
    hook-0 = cat $XDG_RUNTIME_DIR/polybar/eth 2> /dev/null
    initial = 1
    ```

    Observe how the hook path filename must match the module name to have better results and be able
    to properly restart Polybar while maintaining the value set by wmcompanion.
    """
    def __init__(self):
        Path(f"{os.getenv('XDG_RUNTIME_DIR')}/polybar").mkdir(mode=0o700, exist_ok=True)

    def format(self, content: str, color: str = None) -> str:
        """
        Formats a string with the proper tags.

        TODO: Add all format tags available for Polybar.
        See: https://github.com/polybar/polybar/wiki/Formatting#format-tags
        """
        result = content
        if color:
            result = f"%{{F{color}}}{result}%{{F-}}"
        return result

    # Alias fmt as format
    fmt = format

    async def set_module_content(self, module: str, *content: list[str]):
        """
        Set the value of a given Polybar module to the content provided.
        You can provide multiple strings as the content and they will be joined by spaces when
        rendered.
        """
        content_str = " ".join(content)
        await self._write_module_content(module, content_str)
        await self._ipc_action(f"#{module}.send.{content_str}")

    # Make this object callable by invoking set_module_content
    __call__ = set_module_content

    async def _write_module_content(self, module: str, content: str):
        """
        Set the value of the content statically so that when polybar restarts it can pick up the
        value previously set
        """
        def sync_io():
            module_path = f"{os.getenv('XDG_RUNTIME_DIR')}/polybar/{module}"
            with open(module_path, "w", encoding="utf-8") as out:
                out.write(content)

        # REFACTOR: This is a copy of the same method on `event_listening.EventListener`
        with ThreadPoolExecutor(max_workers=1) as executor:
            await asyncio.get_running_loop().run_in_executor(executor, sync_io)

    async def _ipc_action(self, cmd: str):
        """
        Replicates the behavior of polybar-msg action
        """
        payload = bytes(cmd, "utf-8")
        ipc_version = 0
        msg_type = 2
        data = (
            b"polyipc" # magic
            + struct.pack("=BIB", ipc_version, len(payload), msg_type) # version, length, type
            + payload
        )

        for name in glob.glob(f"{os.getenv('XDG_RUNTIME_DIR')}/polybar/*.sock"):
            try:
                with suppress(ConnectionError):
                    reader, writer = await asyncio.open_unix_connection(name)

                    # Write to the file
                    writer.write(data)
                    await writer.drain()
                    logger.debug("polybar action sent to socket %s: %s", name, payload)

                    # Then close it
                    await reader.read()
                    writer.close()
                    await writer.wait_closed()
            except Exception as err:
                raise WMCompanionError(f"Failed to connect to unix socket {name}") from err
