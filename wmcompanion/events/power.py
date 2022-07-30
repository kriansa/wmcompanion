import asyncio
from enum import Enum
from pathlib import Path
from ..event_listening import EventListener
from ..errors import WMCompanionError

class PowerActions(EventListener):
    class Actions(Enum):
        INITIAL_STATE = "initial-state"
        BATTERY_LEVEL_CHANGE = "battery-level-change"
        POWER_BUTTON_PRESS = "power-button-press"
        POWER_SOURCE_SWITCH = "power-source-switch"

    class PowerSource(Enum):
        AC = "ac"
        BATTERY = "battery"

    class BatteryStatus(Enum):
        NOT_CHARGING = "Not Charging"
        CHARGING = "Charging"
        DISCHARGING = "Discharging"
        UNKNOWN = "Unknown"
        FULL = "Full"

    async def start(self):
        await self.fetch_initial_state()
        self.run_coro(self.start_battery_poller())
        self.run_coro(self.start_acpi_listener())

    async def fetch_initial_state(self):
        power_source = await self.current_power_source()
        battery_level = await self.battery_current_level()
        battery_status = await self.battery_current_status()

        self.previous_level = battery_level
        self.previous_status = battery_status

        await self.trigger({
            "action": self.Actions.INITIAL_STATE,
            "power-source": power_source,
            "battery-level": battery_level,
            "battery-status": battery_status,
        })

    async def start_battery_poller(self):
        if not await self.system_has_battery():
            return

        frequency = 60
        while await asyncio.sleep(frequency, True):
            await self.trigger_battery_report()
            frequency = 30 if self.previous_level <= 10 else 60

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

    async def trigger_battery_report(self):
        level = await self.battery_current_level()
        status = await self.battery_current_status()

        self.previous_level = level
        self.previous_status = status

        await self.trigger({
            "action": self.Actions.BATTERY_LEVEL_CHANGE,
            "battery-level": level,
            "battery-status": status,
        })

    async def current_power_source(self) -> PowerSource:
        def is_on_ac():
            return not Path("/sys/class/power_supply/AC").is_dir() or \
                Path("/sys/class/power_supply/AC/online").read_text("utf-8").strip() == "1"

        if await self.run_blocking_io(is_on_ac):
            return self.PowerSource.AC
        else:
            return self.PowerSource.BATTERY

    async def system_has_battery(self) -> bool:
        def has_battery():
            """Blocking I/O that gets whether this system has battery or not"""
            return Path("/sys/class/power_supply/BAT0").is_dir()

        return await self.run_blocking_io(has_battery)

    async def battery_current_status(self) -> BatteryStatus:
        def battery_status():
            """
            Blocking I/O that gets the battery status
            (Not Charging, Charging, Discharging, Unknown, Full)
            """
            return Path("/sys/class/power_supply/BAT0/status").read_text("utf-8").strip()

        return self.BatteryStatus(await self.run_blocking_io(battery_status))

    async def battery_current_level(self) -> int:
        def battery_capacity():
            """Blocking I/O that gets the battery capacity"""
            return Path("/sys/class/power_supply/BAT0/capacity").read_text("utf-8")

        return int(await self.run_blocking_io(battery_capacity))

    async def start_acpi_listener(self):
        try:
            reader, writer = await asyncio.open_unix_connection("/var/run/acpid.socket")
            while line := (await reader.readline()).decode('utf-8').strip():
                if "button/power" in line:
                    await self.trigger(
                        { "action": self.Actions.POWER_BUTTON_PRESS },
                        allow_duplicate_events = True,
                    )
                elif "ac_adapter" in line:
                    if line.split(" ")[3] == "00000000":
                        source = self.PowerSource.BATTERY
                    else:
                        source = self.PowerSource.AC

                    await self.trigger({
                        "action": self.Actions.POWER_SOURCE_SWITCH,
                        "power-source": source,
                    })

                    async def schedule_battery_report():
                        """
                        We schedule a new battery report to 5 seconds from now. This threshold is so
                        that we can account for the kernel to process the battery state transition
                        after a plug/unplug event
                        """
                        await asyncio.sleep(5)
                        await self.trigger_battery_report()

                    self.run_coro(schedule_battery_report())
        except FileNotFoundError as err:
            raise WMCompanionError(f"ACPI socket not found. Listener can't be started.") from err
