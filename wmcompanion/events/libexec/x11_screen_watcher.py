# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# Watch for screen plug/unplug events
#
# Dependencies:
# - Required: xcffib       (Arch: python-xcffib)
# - Optional: acpi-daemon  (Arch: acpid)
#
# Useful constant locations:
# * /usr/include/X11/X.h
# * /usr/include/X11/extensions/Xrandr.h
# * /usr/include/X11/extensions/randr.h

import os, traceback, shutil, signal, sys, threading, socket
import json, zlib, re, glob, concurrent.futures

class RPCPrinter:
    """Communicate with the main process through stdout messages"""

    @staticmethod
    def event(e):
        print(json.dumps({ "action": "event", "event": e }), flush=True)

    @staticmethod
    def exception(e):
        RPCPrinter.error(traceback.format_exception(e))

    @staticmethod
    def error(e):
        print(json.dumps({ "action": "error", "error": e }), flush=True)

try:
    import xcffib, xcffib.xproto, xcffib.randr
    from xcffib.randr import Connection, NotifyMask, ScreenChangeNotifyEvent
except ModuleNotFoundError as e:
    RPCPrinter.error("Python xcffib module is not installed!")
    quit()

class X11Client:
    main_window_id = 0
    randr = None
    conn = None

    def __init__(self):
        self.conn = xcffib.connect()
        self.randr = self.conn(xcffib.randr.key)
        self.main_window_id = self.conn.get_setup().roots[self.conn.pref_screen].root

    def disconnect(self):
        self.conn.disconnect()

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
                type_int = xcffib.xproto.Atom.INTEGER
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

    def listen_monitor_plug_events(self, callback):
        self.randr.SelectInput(self.main_window_id, NotifyMask.ScreenChange)
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

            # Ignore unrelated events
            if type(event["value"]) != ScreenChangeNotifyEvent:
                continue

            callback()


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


class MonitorStatusReader:
    x11_client = None
    consider_lid = True

    # For plug/unplugging change detection
    current_state = []

    def __init__(self):
        self.x11_client = X11Client()
        self.consider_lid = MonitorLid.instance().is_present

    def listen_changes(self):
        signal.signal(signal.SIGINT, self._exit_handler)

        # Execute the two blocking operations in a ThreadPool
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = []

            # Print the initial state right off the bat
            futures.append(executor.submit(self.dispatch_current_state))

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

    def get_connected_monitors(self, state):
        def monitor_is_on(mon):
            return not self.consider_lid or MonitorLid.instance().is_open(mon["output"])

        return [mon for mon in state if monitor_is_on(mon)]

    def dispatch_current_state(self):
        # Refresh the X11 state
        previous_state = self.current_state
        self.current_state = self.get_connected_monitors(self.x11_client.get_connected_outputs())

        # Avoid dispatching events if the state hasn't really changed (X11 GetScreenResources may be
        # triggered by any xrandr event such as monitor rearrangement)
        if previous_state == self.current_state:
            return

        RPCPrinter.event(self.current_state)

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
                self.dispatch_current_state()

    def _x11_listener(self):
        self.x11_client.listen_monitor_plug_events(self.dispatch_current_state)

    def _exit_handler(self, *_):
        print("SIGINT received, exiting...", file=sys.stderr, flush=True)
        os._exit(0)

if __name__ == "__main__":
    monitor_status_reader = MonitorStatusReader()
    monitor_status_reader.listen_changes()
