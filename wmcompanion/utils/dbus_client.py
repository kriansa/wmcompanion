# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0 AND MIT

import logging

# pylint: disable-next=unused-import
from dbus_next import Message, Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType, MessageType

logger = logging.getLogger(__package__)


class DBusClientError(Exception):
    """
    Base error class for DBus related exceptions
    """


class DBusClient:
    """
    Base DBus client class
    """

    def __init__(self, bus_type: BusType):
        self.bus_type = bus_type
        self.bus = None

    async def connect(self) -> None:
        """
        Connects to DBus allowing this instance to call methods
        """
        if self.bus:
            return

        try:
            self.bus = await MessageBus(bus_type=self.bus_type).connect()
        except Exception as err:
            raise DBusClientError("Unable to connect to dbus.") from err

    async def disconnect(self) -> None:
        """
        Disconnects from an existing DBus connection.
        """
        if self.bus:
            self.bus.disconnect()

    # pylint: disable-next=too-many-arguments
    async def add_signal_receiver(
        self,
        callback: callable,
        signal_name: str | None = None,
        dbus_interface: str | None = None,
        bus_name: str | None = None,
        path: str | None = None,
    ) -> bool:
        """
        Helper function which aims to recreate python-dbus's add_signal_receiver
        method in dbus_next with asyncio calls.
        Returns True if subscription is successful.
        """
        match_args = {
            "type": "signal",
            "sender": bus_name,
            "member": signal_name,
            "path": path,
            "interface": dbus_interface,
        }

        rule = ",".join(f"{k}='{v}'" for k, v in match_args.items() if v)

        try:
            await self.call_method(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "AddMatch",
                "s",
                rule,
            )
        except DBusClientError:
            # Check if message sent successfully
            logger.warning("Unable to add watch for DBus events (%s)", rule)
            return False

        def message_handler(message):
            if message.message_type != MessageType.SIGNAL:
                return

            callback(*message.body, dbus_message=message)

        self.bus.add_message_handler(message_handler)
        return True

    # pylint: disable-next=too-many-arguments
    async def call_method(
        self,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str,
        body: any,
    ) -> any:
        """
        Calls any available DBus method and return its value
        """
        msg = await self._send_dbus_message(
            MessageType.METHOD_CALL,
            destination,
            interface,
            path,
            member,
            signature,
            body,
        )

        if msg is None or msg.message_type != MessageType.METHOD_RETURN:
            raise DBusClientError(f"Unable to call method on dbus: {msg.error_name}")

        match len(msg.body):
            case 0:
                return None
            case 1:
                return msg.body[0]
            case _:
                return msg.body

    # pylint: disable-next=too-many-arguments
    async def _send_dbus_message(
        self,
        message_type: MessageType,
        destination: str | None,
        interface: str | None,
        path: str | None,
        member: str | None,
        signature: str,
        body: any,
    ) -> Message | None:
        """
        Private method to send messages to dbus via dbus_next.
        Returns a tuple of the bus object and message response.
        """

        if isinstance(body, str):
            body = [body]

        await self.connect()

        # Ignore types here: dbus-next has default values of `None` for certain
        # parameters but the signature is `str` so passing `None` results in an
        # error in mypy.
        return await self.bus.call(
            Message(
                message_type=message_type,
                destination=destination,  # type: ignore
                interface=interface,  # type: ignore
                path=path,  # type: ignore
                member=member,  # type: ignore
                signature=signature,
                body=body,
            )
        )


class SessionDBusClient(DBusClient):
    """
    Session DBus client
    """

    def __init__(self):
        super().__init__(BusType.SESSION)


class SystemDBusClient(DBusClient):
    """
    System DBus client
    """

    def __init__(self):
        super().__init__(BusType.SYSTEM)
