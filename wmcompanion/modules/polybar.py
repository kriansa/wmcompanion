# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import asyncio, os, errno, glob, struct, logging
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
        self._write_module_content(module, content_str)
        await self._ipc_action(f"#{module}.send.{content_str}")

    # Make this object callable by invoking set_module_content
    __call__ = set_module_content

    def _write_module_content(self, module: str, content: str):
        """
        Set the value of the content statically so that when polybar restarts it can pick up the
        value previously set
        """
        with open(f"{os.getenv('XDG_RUNTIME_DIR')}/polybar/{module}", "w") as out:
            out.write(content)

    async def _ipc_action(self, cmd: str):
        """
        Replicates the behavior of polybar-msg action
        """
        payload = bytes(cmd, "utf-8")
        ipc_version = 0
        msg_type = 2
        data = (
            b"polyipc" # magic
            + struct.pack("=BIB", ipc_version, len(payload), msg_type) # header: version, length, type
            + payload
        )

        for name in glob.glob(f"{os.getenv('XDG_RUNTIME_DIR')}/polybar/*.sock"):
            try:
                reader, writer = await asyncio.open_unix_connection(name)
            except OSError as err:
                if err.errno not in (errno.ENXIO, errno.ECONNREFUSED):
                    raise WMCompanionError(f"Failed to connect to unix socket {name}") from err
            finally:
                try:
                    writer.write(data)
                    await writer.drain()
                    await reader.read()
                    logger.debug(f"polybar action sent to socket {name}: {payload}")
                finally:
                    writer.close()
                    await writer.wait_closed()
