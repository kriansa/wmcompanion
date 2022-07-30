# Copyright (c) 2022 Daniel Pereira
# 
# SPDX-License-Identifier: Apache-2.0

from contextlib import suppress
from ..utils.dbus_client import DBusClient, DBusClientError
from ..event_listening import EventListener

class WifiStatus(EventListener):
    """
    Reacts to wifi radio changes, connection activity and strength changes.
    """
    # Sets which adapter we want to watch for updates. If blank, use the first available
    wifi_adapter: str = ""

    async def update_state(self):
        await self.fetch_wifi_access_point()
        await self.fetch_wifi_strength()
        await self.trigger({
            "enabled": self.wifi_enabled,
            "connected": self.wifi_connected,
            "strength": self.wifi_strength,
        })

    async def start(self):
        self.dbus = DBusClient(session_bus=False)

        # Get initial state
        await self.update_state()

        # Then subscribe for state updates
        def property_changed(prop, value, _, dbus_message):
            # AccessPoint Strength update
            if prop == "org.freedesktop.NetworkManager.AccessPoint":
                if "Strength" in value and dbus_message.path == self.wifi_access_point_path:
                    self.wifi_strength = value["Strength"].value
                    self.run_coro(self.update_state())
                return

            # Connected/disconnected event
            if prop == "org.freedesktop.NetworkManager" and "ActiveConnections" in value:
                self.run_coro(self.update_state())

        subscribed = await self.dbus.add_signal_receiver(
            callback = property_changed,
            signal_name = "PropertiesChanged",
            dbus_interface = "org.freedesktop.DBus.Properties",
        )

        if not subscribed:
            logger.warning("Could not subscribe to DBus PropertiesChanged signal.")
            raise RuntimeError("Fail to setup NetworkManager DBus signal receiver")

    async def is_connection_wifi(self, connection_path) -> bool:
        """
        If there's a defined interface name for the wifi network, check if that's the one
        Otherwise, simply check if this connection is wireless
        """
        if self.wifi_adapter:
            conn_devices = await self.dbus.call_method(
                destination = "org.freedesktop.NetworkManager",
                path = connection_path,

                interface = "org.freedesktop.DBus.Properties",
                member = "Get",
                signature = "ss",
                body = ["org.freedesktop.NetworkManager.Connection.Active", "Devices"],
            )

            for device_path in conn_devices.value:
                device = await self.dbus.call_method(
                    destination = "org.freedesktop.NetworkManager",
                    path = device_path,

                    interface = "org.freedesktop.DBus.Properties",
                    member = "Get",
                    signature = "ss",
                    body = ["org.freedesktop.NetworkManager.Device", "Interface"],
                )

                if device.value == self.wifi_adapter:
                    return True

            return False
        else:
            conn_type = await self.dbus.call_method(
                destination = "org.freedesktop.NetworkManager",
                path = connection_path,

                interface = "org.freedesktop.DBus.Properties",
                member = "Get",
                signature = "ss",
                body = ["org.freedesktop.NetworkManager.Connection.Active", "Type"],
            )

            return conn_type.value == "802-11-wireless"

    async def fetch_wifi_access_point(self):
        # 0. Check if HW/SW access to wifi is enabled
        self.wifi_enabled = await self.wifi_is_enabled()
        if not self.wifi_enabled:
            self.wifi_connected = False
            self.wifi_access_point_path = ""
            return

        # 1. Collect all active connections
        active_connections = await self.dbus.call_method(
            destination = "org.freedesktop.NetworkManager",
            path = "/org/freedesktop/NetworkManager",

            interface = "org.freedesktop.DBus.Properties",
            member = "Get",
            signature = "ss",
            body = ["org.freedesktop.NetworkManager", "ActiveConnections"],
        )

        # 2A. Next, if we know which interface name, we filter by it
        # 2B. Otherwise, we get the first connection that is wireless and we'll use it
        wifi_connection = None
        for connection_path in active_connections.value:
            if (await self.is_connection_wifi(connection_path)):
                wifi_connection = connection_path
                break

        # No wifi detected, just skip through
        if not wifi_connection:
            self.wifi_connected = False
            self.wifi_access_point_path = ""
            return

        # 3. Get AccessPoint from Wi-Fi connection
        access_point = await self.dbus.call_method(
            destination = "org.freedesktop.NetworkManager",
            path = wifi_connection,

            interface = "org.freedesktop.DBus.Properties",
            member = "Get",
            signature = "ss",
            body = ["org.freedesktop.NetworkManager.Connection.Active", "SpecificObject"],
        )

        self.wifi_connected = True
        self.wifi_access_point_path = access_point.value

    async def fetch_wifi_strength(self) -> None:
        """
        Updates the signal strength of the current connected network, or sets to 0 in case we're not
        connected to any wireless network.
        """

        if not self.wifi_connected:
            self.wifi_strength = 0
            return

        signal = await self.dbus.call_method(
            destination = "org.freedesktop.NetworkManager",
            path = self.wifi_access_point_path,

            interface = "org.freedesktop.DBus.Properties",
            member = "Get",
            signature = "ss",
            body = ["org.freedesktop.NetworkManager.AccessPoint", "Strength"],
        )

        self.wifi_strength = signal.value

    async def wifi_is_enabled(self):
        """
        Test whether wifi is enabled in hardware and software.
        """
        state = await self.dbus.call_method(
            destination = "org.freedesktop.NetworkManager",
            path = "/org/freedesktop/NetworkManager",

            interface = "org.freedesktop.DBus.Properties",
            member = "Get",
            signature = "ss",
            body = ["org.freedesktop.NetworkManager", "WirelessEnabled"],
        )

        hw_state = await self.dbus.call_method(
            destination = "org.freedesktop.NetworkManager",
            path = "/org/freedesktop/NetworkManager",

            interface = "org.freedesktop.DBus.Properties",
            member = "Get",
            signature = "ss",
            body = ["org.freedesktop.NetworkManager", "WirelessHardwareEnabled"],
        )

        return state.value and hw_state.value


class NetworkConnectionStatus(EventListener):
    """
    Reacts to NetworkManager connection status change
    """
    # Defines which connection name on NetworkManager we want to monitor
    connection_name: str = ""

    def __str__(self):
        return f"{type(self).__name__}[{self.connection_name}]"

    async def start(self):
        self.dbus = DBusClient(session_bus=False)

        # Get initial state
        await self.update_state()

        # Then subscribe for state updates
        def property_changed(prop, value, _, dbus_message):
            # Connected/disconnected event
            if prop == "org.freedesktop.NetworkManager" and "ActiveConnections" in value:
                self.run_coro(self.update_state())

        subscribed = await self.dbus.add_signal_receiver(
            callback = property_changed,
            signal_name = "PropertiesChanged",
            dbus_interface = "org.freedesktop.DBus.Properties",
        )

        if not subscribed:
            logger.warning("Could not subscribe to DBus PropertiesChanged signal.")
            raise RuntimeError("Fail to setup NetworkManager DBus signal receiver")

    async def update_state(self):
        connected = await self.connection_is_active()
        await self.trigger({ "connected": connected })

    async def connection_is_active(self) -> bool:
        """
        Check whether the connection name is active
        """
        with suppress(DBusClientError):
            # 1. Collect all active connections
            active_connections = await self.dbus.call_method(
                destination = "org.freedesktop.NetworkManager",
                path = "/org/freedesktop/NetworkManager",

                interface = "org.freedesktop.DBus.Properties",
                member = "Get",
                signature = "ss",
                body = ["org.freedesktop.NetworkManager", "ActiveConnections"],
            )

            # Check if the one we're looking for is here...
            for connection_path in active_connections.value:
                conn_name = await self.dbus.call_method(
                    destination = "org.freedesktop.NetworkManager",
                    path = connection_path,

                    interface = "org.freedesktop.DBus.Properties",
                    member = "Get",
                    signature = "ss",
                    body = ["org.freedesktop.NetworkManager.Connection.Active", "Id"],
                )

                if conn_name.value == self.connection_name:
                    return True

        return False
