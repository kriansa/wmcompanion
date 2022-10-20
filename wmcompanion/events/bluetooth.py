# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import logging
from ..event_listening import EventListener
from ..utils.dbus_client import SystemDBusClient

logger = logging.getLogger(__name__)

class BluetoothRadioStatus(EventListener):
    """
    Reacts to bluetooth radio status changes
    """

    async def start(self):
        client = SystemDBusClient()

        # Get the initial state
        state = await client.call_method(
            destination="org.bluez",
            interface="org.freedesktop.DBus.ObjectManager",
            path="/",
            member="GetManagedObjects",
            signature="",
            body=[],
        )

        for _, props in state.items():
            if "org.bluez.Adapter1" in props.keys():
                await self.trigger(
                    {"enabled": props["org.bluez.Adapter1"]["Powered"].value}
                )

        def property_changed(adapter, values, _, dbus_message):
            if "/org/bluez/hci" not in dbus_message.path:
                return

            if adapter == "org.bluez.Adapter1" and "Powered" in values:
                self.run_coro(self.trigger({"enabled": values["Powered"].value}))

        # Then subscribe for changes
        subscribed = await client.add_signal_receiver(
            callback=property_changed,
            signal_name="PropertiesChanged",
            dbus_interface="org.freedesktop.DBus.Properties",
        )

        if not subscribed:
            logger.warning("Could not subscribe to bluetooth status signal.")
            raise RuntimeError("Fail to setup bluez DBus signal receiver")
