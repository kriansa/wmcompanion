# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

from ..event_listening import EventListener
from ..utils.dbus_client import DBusClient

class BluetoothRadioStatus(EventListener):
    """
    Reacts to bluetooth radio status changes
    """
    async def start(self):
        client = DBusClient(session_bus=False)

        # Get the initial state
        state = await client.call_method(
            destination = "org.bluez",
            interface = "org.freedesktop.DBus.Properties",
            path = "/org/bluez/hci0",
            member = "Get",
            signature = "ss",
            body = ["org.bluez.Adapter1", "Powered"],
        )

        await self.trigger({ "enabled": state.value })

        def property_changed(adapter, values, _, dbus_message):
            if adapter == "org.bluez.Adapter1" and "Powered" in values:
                self.run_coro(self.trigger({ "enabled": values["Powered"].value }))

        # Then subscribe for changes
        subscribed = await client.add_signal_receiver(
            callback = property_changed,
            signal_name = "PropertiesChanged",
            dbus_interface = "org.freedesktop.DBus.Properties",
            path = "/org/bluez/hci0",
        )

        if not subscribed:
            logger.warning("Could not subscribe to bluetooth status signal.")
            raise RuntimeError("Fail to setup bluez DBus signal receiver")
