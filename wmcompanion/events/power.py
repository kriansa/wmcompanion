# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from enum import Enum
from pathlib import Path
from datetime import datetime
from ..utils.dbus_client import SystemDBusClient
from ..event_listening import EventListener
from ..errors import WMCompanionError

logger = logging.getLogger(__name__)


class LogindIdleStatus(EventListener):
    """
    Listen for systemd-logind IdleHint events, which is how the desktop environment let systemd know
    that it is idle so it can take actions such as automatically suspending. With this module, you
    are able to hook on those events and perform those actions yourself.

    See: https://www.freedesktop.org/wiki/Software/systemd/logind/
    See: https://www.freedesktop.org/software/systemd/man/logind.conf.html
    """

    async def start(self):
        def property_changed(prop, values, _, dbus_message):
            if "/org/freedesktop/login1" not in dbus_message.path:
                return

            if prop == "org.freedesktop.login1.Manager" and "IdleHint" in values:
                status = values["IdleHint"].value
                time = datetime.fromtimestamp(values["IdleSinceHint"].value / 1000000)
                self.run_coro(self.trigger({"idle": status, "idle-since": time}))

        subscribed = await SystemDBusClient().add_signal_receiver(
            callback=property_changed,
            signal_name="PropertiesChanged",
            dbus_interface="org.freedesktop.DBus.Properties",
        )

        if not subscribed:
            logger.warning("Could not subscribe to DBus PropertiesChanged signal.")
            raise RuntimeError(
                "Fail to setup logind DBus signal receiver for PropertiesChanged"
            )


class PowerActions(EventListener):
    """
    PowerActions will listen for all possible power related events, such as power source switch and
    battery level changes, then proceed with notifying the callbacks with the current system power
    state.
    """

    previous_level: int = 0
    previous_status: "BatteryStatus" = None

    class Events(Enum):
        """The kind of event that's been triggered"""

        INITIAL_STATE = "initial-state"
        RETURN_FROM_SLEEP = "return-from-sleep"
        BATTERY_LEVEL_CHANGE = "battery-level-change"
        POWER_BUTTON_PRESS = "power-button-press"
        POWER_SOURCE_SWITCH = "power-source-switch"

    class PowerSource(Enum):
        """The current computer power source"""

        AC = "ac"
        BATTERY = "battery"

    class BatteryStatus(Enum):
        """The current status of the battery"""

        NOT_CHARGING = "Not charging"
        CHARGING = "Charging"
        DISCHARGING = "Discharging"
        UNKNOWN = "Unknown"
        FULL = "Full"

    async def start(self):
        await self.start_battery_poller()
        await self.start_acpi_listener()
        await self.start_wakeup_detector()
        await self.trigger_event(self.Events.INITIAL_STATE)

    async def trigger_event(
        self,
        event: Events,
        power_source: PowerSource = None,
        battery_status: BatteryStatus = None,
        battery_level: int = None,
    ):
        """
        Triggers a power event with current power state
        """
        if not power_source:
            power_source = await self.current_power_source()
        if not battery_level:
            battery_level = await self.current_battery_level()
        if not battery_status:
            battery_status = await self.current_battery_status()
        allow_duplicate_events = event in [
            self.Events.POWER_BUTTON_PRESS,
            self.Events.RETURN_FROM_SLEEP,
        ]

        self.previous_level = battery_level
        self.previous_status = battery_status

        await self.trigger(
            {
                "event": event,
                "power-source": power_source,
                "battery-level": battery_level,
                "battery-status": battery_status,
            },
            allow_duplicate_events=allow_duplicate_events,
        )

    async def start_battery_poller(self):
        """
        Starts a battery level poller that is only activated if the system has a battery
        """
        if not await self.system_has_battery():
            return
        self.run_coro(self.battery_poller())

    async def battery_poller(self):
        """
        Polls the battery for level changes and triggers an event upon a state change
        """
        frequency = 60
        while await asyncio.sleep(frequency, True):
            battery_status = await self.current_battery_status()
            battery_level = await self.current_battery_level()

            # Nothing has changed, save one call
            if (
                battery_status == self.previous_status
                and battery_level == self.previous_level
            ):
                continue

            await self.trigger_event(
                self.Events.BATTERY_LEVEL_CHANGE,
                battery_status=battery_status,
                battery_level=battery_level,
            )

            # Inteligently adjust the polling frequency:
            #
            # - If the last measured status is unknown, it is very likely for it to change shortly
            #   after that, so we just monitor for that change more tightly, giving a more real-time
            #   sense for the poll.
            # - When battery is low, it usually drains quicker, so we need to check that more
            #   frequently
            # - Otherwise we just keep the default polling freq.
            if self.previous_status == self.BatteryStatus.UNKNOWN:
                frequency = 5
            elif self.previous_level <= 10:
                frequency = 30
            else:
                frequency = 60

    async def current_power_source(self) -> PowerSource:
        """
        Retrieves the current system power source
        """

        def is_on_ac():
            return (
                not Path("/sys/class/power_supply/AC").is_dir()
                or Path("/sys/class/power_supply/AC/online").read_text("utf-8").strip()
                == "1"
            )

        if await self.run_blocking_io(is_on_ac):
            return self.PowerSource.AC

        return self.PowerSource.BATTERY

    async def system_has_battery(self) -> bool:
        """
        Checks whether the system has a battery
        """

        def has_battery():
            """Blocking I/O that gets whether this system has battery or not"""
            return Path("/sys/class/power_supply/BAT0").is_dir()

        return await self.run_blocking_io(has_battery)

    async def current_battery_status(self) -> BatteryStatus:
        """
        Get the current battery status
        """

        def battery_status():
            """
            Blocking I/O that gets the battery status
            (Not Charging, Charging, Discharging, Unknown, Full)
            """
            return (
                Path("/sys/class/power_supply/BAT0/status").read_text("utf-8").strip()
            )

        return self.BatteryStatus(await self.run_blocking_io(battery_status))

    async def current_battery_level(self) -> int:
        """
        Get the current battery level
        """

        def battery_capacity():
            """Blocking I/O that gets the battery capacity"""
            return Path("/sys/class/power_supply/BAT0/capacity").read_text("utf-8")

        return int(await self.run_blocking_io(battery_capacity))

    async def system_has_acpi(self) -> bool:
        """
        Checks whether the system has ACPI daemon installed
        """

        def has_acpi():
            """Blocking I/O that gets whether this system has acpid installed or not"""
            return Path("/etc/acpi").is_dir()

        return await self.run_blocking_io(has_acpi)

    async def start_acpi_listener(self):
        """
        Starts the ACPI daemon listener that helps detecting power events such as power button or
        power source changes
        """
        if not await self.system_has_acpi():
            return

        try:
            reader, _writer = await asyncio.open_unix_connection(
                "/var/run/acpid.socket"
            )
            self.run_coro(self.acpid_event(reader))
        except FileNotFoundError as err:
            raise WMCompanionError(
                "ACPI socket not found. Listener can't be started."
            ) from err

    async def start_wakeup_detector(self):
        """Detects when the system has returned from sleep or hibernation"""

        def prepare_for_sleep(sleeping: bool, **_):
            if not sleeping:
                self.run_coro(self.trigger_event(self.Events.RETURN_FROM_SLEEP))

        dbus = SystemDBusClient()
        subscribed = await dbus.add_signal_receiver(
            callback=prepare_for_sleep,
            signal_name="PrepareForSleep",
            dbus_interface="org.freedesktop.login1.Manager",
        )

        if not subscribed:
            logger.warning("Could not subscribe to DBus PrepareForSleep signal.")
            raise RuntimeError(
                "Fail to setup logind DBus signal receiver for PrepareForSleep"
            )

    async def acpid_event(self, reader: asyncio.StreamReader):
        """
        Callback called when there's any ACPI daemon event triggered, then converts them to
        wmcompanion ones
        """
        while line := (await reader.readline()).decode("utf-8").strip():
            if "button/power" in line:
                await self.trigger_event(self.Events.POWER_BUTTON_PRESS)
            elif "ac_adapter" in line:
                if line.split(" ")[3] == "00000000":
                    source = self.PowerSource.BATTERY
                else:
                    source = self.PowerSource.AC

                await self.trigger_event(
                    self.Events.POWER_SOURCE_SWITCH, power_source=source
                )

                async def schedule_battery_report():
                    """
                    We schedule a new battery report to 5 seconds from now. This threshold is so
                    that we can account for the kernel to process the battery state transition
                    after a plug/unplug event
                    """
                    await asyncio.sleep(5)
                    await self.trigger_event(self.Events.BATTERY_LEVEL_CHANGE)

                self.run_coro(schedule_battery_report())
