# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# Watch for screen, keyboard and mice plug/unplug events
#
# Dependencies:
# - Required: xcffib       (Arch: python-xcffib)
# - Optional: acpi-daemon  (Arch: acpid)
#
# Useful constant locations:
# * /usr/include/X11/X.h
# * /usr/include/X11/extensions/Xrandr.h
# * /usr/include/X11/extensions/randr.h
# * /usr/include/X11/extensions/Xinput2.h

import os, traceback, shutil, signal, sys, threading, socket
import json, zlib, re, glob, concurrent.futures
from enum import Enum

class RPCPrinter:
    """Communicate with the main process through stdout messages"""

    @staticmethod
    def event(evtype: 'EventType', event: any):
        print(json.dumps({ "action": evtype.value, "state": event }), flush=True)

    @staticmethod
    def exception(e):
        RPCPrinter.error(traceback.format_exception(e))

    @staticmethod
    def error(e):
        print(json.dumps({ "action": "error", "error": e }), flush=True)

try:
    import xcffib, xcffib.randr, xcffib.xinput
    from xcffib.xproto import GeGenericEvent, Atom
    from xcffib.randr import Connection, NotifyMask, ScreenChangeNotifyEvent
    from xcffib.xinput import Device, DeviceType, EventMask, \
        HierarchyInfo, HierarchyMask, \
        XIDeviceInfo, XIEventMask
except ModuleNotFoundError as e:
    RPCPrinter.error("Python xcffib module is not installed!")
    quit()


class EventType(Enum):
    SCREEN_CHANGE = "screen-change"
    INPUT_CHANGE = "input-change"


class X11Client:
    def __init__(self):
        self.conn = xcffib.connect()
        self.randr = self.conn(xcffib.randr.key)
        self.xinput = self.conn(xcffib.xinput.key)
        self.main_window_id = self.conn.get_setup().roots[self.conn.pref_screen].root

    def get_monitor_unique_id(self, output: int):
        edid = self.get_output_edid(output)
        if edid == None:
            return None

        return hex(zlib.crc32(edid.raw))[2:].upper().rjust(8, '0')

    def get_output_edid(self, output: int):
        atoms = self.randr.ListOutputProperties(output).reply().atoms.list
        for atom in atoms:
            name = self.conn.core.GetAtomName(atom).reply().name.raw.decode('ascii')
            if name == "EDID":
                type_int = Atom.INTEGER
                reply = self.randr.GetOutputProperty(output, atom, type_int, 0, 2048, False, False).reply()
                return reply.data

        return None

    def get_connected_outputs(self):
        res = self.randr.GetScreenResources(self.main_window_id).reply()

        monitors = []
        for output in res.outputs:
            info = self.randr.GetOutputInfo(output, xcffib.CurrentTime).reply()
            if info.connection != Connection.Connected:
                continue

            monitors.append({
                "output": info.name.raw.decode("ascii"),
                "edid_hash": self.get_monitor_unique_id(output),
            })

        return monitors

    X11_INPUT_TYPES = [
        DeviceType.MasterPointer, DeviceType.MasterKeyboard, DeviceType.SlavePointer,
        DeviceType.SlaveKeyboard, DeviceType.FloatingSlave
    ]

    X11_INPUT_TYPES_STR = {
        DeviceType.MasterPointer: "master-pointer",
        DeviceType.MasterKeyboard: "master-keyboard",
        DeviceType.SlavePointer: "slave-pointer",
        DeviceType.SlaveKeyboard: "slave-keyboard",
        DeviceType.FloatingSlave: "floating-slave",
    }

    def get_connected_inputs(self):
        inputs = []
        for info in self.xinput.XIQueryDevice(Device.All).reply().infos:
            if info.type in self.X11_INPUT_TYPES:
                inputs.append({
                    "id": info.deviceid,
                    "type": self.X11_INPUT_TYPES_STR[info.type],
                    "name": info.name.raw.decode('utf-8'),
                })

        return inputs

    def listen_device_connection_events(self, callback):
        # Watch for both randr screen change
        self.randr.SelectInput(self.main_window_id, NotifyMask.ScreenChange)
        # And XI2 device tree change
        mask = EventMask.synthetic(Device.All, 1, [XIEventMask.Hierarchy])
        self.xinput.XISelectEvents(self.main_window_id, 1, [mask])

        self.conn.flush()
        stop = threading.Event()

        # We use xcffib lib, which uses Python's CFFI library under the hood in order to provide a
        # thin layer on top of XCB C lib.
        # As in any FFI library, whenever we switch control to the C code, Python's VM loses control
        # over that program until the routine C yields, which is not the case for a blocking
        # function such as `wait_for_event`.
        # In order to increase the responsiveness of this application and make sure we are able to
        # stop it quickly if needed, we'll run it within a separate thread, leaving the main one
        # free for user interactivity.
        def wait_for_x11_event(stop, event):
            try:
                event["value"] = self.conn.wait_for_event()
            except Exception as err:
                event["value"] = err
            finally:
                stop.set()

        while True:
            event = {}
            stop.clear()
            threading.Thread(
                target = wait_for_x11_event,
                args=(stop, event,),
                # Daemonize this thread so Python can exit even with it still running, which will
                # likely be the case because it will be blocked by the C function underneath.
                daemon = True,
            ).start()

            # Wait for the blocking operation
            stop.wait()

            if type(event["value"]) == Exception:
                raise event["value"]

            if type(event["value"]) == GeGenericEvent:
                callback(EventType.INPUT_CHANGE)

            if type(event["value"]) == ScreenChangeNotifyEvent:
                callback(EventType.SCREEN_CHANGE)


class MonitorLid:
    lid_state_file = None
    is_present = None

    # Singleton
    _instance = None

    @classmethod
    def instance(klass):
        if klass._instance is None:
            klass._instance = klass()
        return klass._instance

    def __init__(self):
        lids = glob.glob("/proc/acpi/button/lid/*/state")
        self.lid_state_file = lids[0] if len(lids) == 1 else None
        self.is_present = shutil.which('acpi_listen') is not None and \
            self.lid_state_file is not None

    def is_open(self, output_name = None):
        # If we don't have ACPI, then the lid is always open
        if not self.is_present:
            return True

        # If this is not a "laptop monitor", then the "lid" is open
        # Stolen from autorandr
        if output_name is not None and not re.match(r'(eDP(-?[0-9]\+)*|LVDS(-?[0-9]\+)*)', output_name):
            return True

        with open(self.lid_state_file) as f:
            return "open" in f.read()


class DeviceStatusReader:
    def __init__(self):
        self.x11_client = X11Client()
        self.consider_lid = MonitorLid.instance().is_present
        self.device_state = []
        self.screen_state = []

    def listen_changes(self):
        signal.signal(signal.SIGINT, self._exit_handler)

        # Execute the two blocking operations in a ThreadPool
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = []

            # Print the initial state on startup
            futures.append(executor.submit(self.dispatch_display_state))
            futures.append(executor.submit(self.dispatch_device_state))

            # Start the XCB listener
            futures.append(executor.submit(self._x11_listener))

            # And if available, start the ACPI listener
            if self.consider_lid:
                futures.append(executor.submit(self._acpi_listener))

            # Handle errors
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    RPCPrinter.exception(exc)
                    os._exit(0)

    def get_active_screens(self, state):
        """
        Filter screens that are really considered active based on their lid state, if applicable
        """
        def monitor_is_on(mon):
            return not self.consider_lid or MonitorLid.instance().is_open(mon["output"])

        return [mon for mon in state if monitor_is_on(mon)]

    def dispatch_device_state(self):
        previous_state = self.device_state
        self.device_state = self.x11_client.get_connected_inputs()

        # Avoid dispatching events if the state hasn't really changed
        if previous_state == self.device_state:
            return

        event = { "active": self.device_state }

        # Check what's changed specifically
        added = [x for x in self.device_state if x not in previous_state]
        removed = [x for x in previous_state if x not in self.device_state]
        if added:
            event["added"] = added
        if removed:
            event["removed"] = removed

        RPCPrinter.event(EventType.INPUT_CHANGE, event)

    def dispatch_display_state(self):
        previous_state = self.screen_state
        self.screen_state = self.get_active_screens(self.x11_client.get_connected_outputs())

        # Avoid dispatching events if the state hasn't really changed
        if previous_state == self.screen_state:
            return

        event = { "active": self.screen_state }
        RPCPrinter.event(EventType.SCREEN_CHANGE, event)

    def _handle_x11_callback(self, event: EventType):
        match event:
            case EventType.SCREEN_CHANGE:
                self.dispatch_display_state()
            case EventType.INPUT_CHANGE:
                self.dispatch_device_state()
            case _:
                raise RuntimeError(f"Unable to understand X11Client callback response: {event}")

    def _acpi_listener(self):
        last_state = "open" if MonitorLid.instance().is_open() else "closed"
        current_state = last_state

        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect("/var/run/acpid.socket")
        while True:
            line = s.recv(128).decode("utf-8")
            if "button/lid" in line:
                current_state = "open" if "open" in line else "closed"
                if current_state == last_state:
                    continue

                last_state = current_state
                self.dispatch_display_state()

    def _x11_listener(self):
        self.x11_client.listen_device_connection_events(self._handle_x11_callback)

    def _exit_handler(self, *_):
        print("SIGINT received, exiting...", file=sys.stderr, flush=True)
        os._exit(0)

if __name__ == "__main__":
    monitor_status_reader = DeviceStatusReader()
    monitor_status_reader.listen_changes()
