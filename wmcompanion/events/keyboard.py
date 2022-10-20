# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import logging
from ..utils.dbus_client import SessionDBusClient
from ..event_listening import EventListener

logger = logging.getLogger(__name__)

class KbddChangeLayout(EventListener):
    """
    Reacts to kbdd layout changes
    """
    async def start(self):
        client = SessionDBusClient()

        # This is equivalent to running the following in the terminal:
        # dbus-send --dest=ru.gentoo.KbddService /ru/gentoo/KbddService \
        #   ru.gentoo.kbdd.getCurrentLayout
        state = await client.call_method(
            destination = "ru.gentoo.KbddService",
            interface = "ru.gentoo.kbdd",
            path = "/ru/gentoo/KbddService",
            member = "getCurrentLayout",
            signature = "",
            body = [],
        )

        await self.trigger({ "id": state })

        def layout_changed(layout_id, **_):
            self.run_coro(self.trigger({ "id": layout_id }))

        subscribed = await client.add_signal_receiver(
            callback=layout_changed,
            signal_name="layoutChanged",
            dbus_interface="ru.gentoo.kbdd",
        )

        if not subscribed:
            logger.warning("Could not subscribe to kbdd signal.")
            raise RuntimeError("Fail to setup kbdd DBus signal receiver")
