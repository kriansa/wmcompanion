# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import logging
from ..utils.dbus_client import SessionDBusClient
from ..event_listening import EventListener

logger = logging.getLogger(__name__)


class DunstPausedStatus(EventListener):
    """
    Reacts to dunst pause status changes
    """

    async def start(self):
        client = SessionDBusClient()

        state = await client.call_method(
            destination="org.freedesktop.Notifications",
            interface="org.freedesktop.DBus.Properties",
            path="/org/freedesktop/Notifications",
            member="Get",
            signature="ss",
            body=["org.dunstproject.cmd0", "paused"],
        )

        if state is None:
            logger.warning("Unable to get initial keyboard state from DBus")
            raise RuntimeError("Fail to get initial kbdd DBus status")

        # Set the initial state
        await self.trigger({"paused": state.value})

        def property_changed(prop, value, *_, **__):
            if prop == "org.dunstproject.cmd0" and "paused" in value:
                self.run_coro(self.trigger({"paused": value["paused"].value}))

        # Then subscribe for changes
        subscribed = await client.add_signal_receiver(
            callback=property_changed,
            signal_name="PropertiesChanged",
            dbus_interface="org.freedesktop.DBus.Properties",
        )

        if not subscribed:
            logger.warning("Could not subscribe to kbdd signal.")
            raise RuntimeError("Fail to setup kbdd DBus signal receiver")
