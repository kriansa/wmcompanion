# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import asyncio
import logging
import signal
import traceback
import gc
from typing import Coroutine
from concurrent.futures import ThreadPoolExecutor
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader
from .errors import WMCompanionFatalError

logger = logging.getLogger(__name__)


class EventListener:
    """
    This is the base class for every class that is supposed to listen for a specific kind of
    systematic action and then reacts to it.

    For instance, we could have a VolumeControlListener that listen for volume changes and then
    reacts to it by invoking the callback with the current volume.

    An EventListener is used on user configuration under the `@on` decorator, and it is
    automatically instantiated by EventWatcher whenever there's at least one `@on` decorator using
    it.
    """

    def __init__(self, event_watcher: "EventWatcher"):
        self.event_watcher = event_watcher
        self.previous_trigger_argument = None
        self.callbacks = []

    def name(self) -> str:
        """
        Full name of this class to help identifying it on logs
        """
        return ".".join([self.__class__.__module__, self.__class__.__name__])

    def add_callback(self, callback: callable):
        """
        Append the function as a callback to this listener, and it will be called whenever
        `trigger()` is called.
        """
        self.callbacks.append(callback)

    def run_coro(self, coro: Coroutine):
        """
        Adds a coroutine to the main event loop. It has a similar behavior than what you would
        expect from `asyncio.run()` - but it instead uses the same event loop the application is on.
        """
        self.event_watcher.run_coro(coro)

    async def run_blocking_io(self, callback: callable) -> any:
        """
        Python asyncio does not natively support regular files, so in order to avoid blocking
        functions in the loop, use this to spawn a separate thread to run blocking operations.
        """
        with ThreadPoolExecutor(max_workers=1) as executor:
            return await asyncio.get_running_loop().run_in_executor(executor, callback)

    async def trigger(self, value: dict = None, allow_duplicate_events: bool = False):
        """
        Executes all callbacks registered for that listener. Callbacks will receive the events in
        the order they have been registered.

        Optionally, an arbitrary `value` can be passed and it will be forwarded to the callback
        function as the first argument. If passed, a value will be compared to its previous
        triggered value and will not continue if it is the same, so that we don't bother callbacks
        with repetitive triggers and avoid unecessary re-renders or stacked notifications. This
        behavior can be turned off if you pass True to the parameter `allow_duplicate_events`.
        """
        if (
            not allow_duplicate_events
            and value
            and value == self.previous_trigger_argument
        ):
            return
        self.previous_trigger_argument = value

        for callback in self.callbacks:
            # Adds this class name as the `event-type` attribute on the value object callback
            event = value.copy()
            event["event-class"] = self.name()

            # Sets the event value object as a property of the callback, so that the @on decorator
            # can pick it up and pass it as the first argument to the function call.
            # See `decorators.OnDecorator#apply`.
            callback.event_object = event
            await (callback.with_decorators())()

    async def start(self):
        """
        Executes the primary action for this EventListener. It is executed right after it is first
        required and instantiated. Usually, it is meant to start some sort of system listener and
        register the `trigger()` as a callback to it.
        """


class EventWatcher:
    """
    This is the main application object, it is responsible for loading the user configuration,
    dynamically registering EventListeners, adding callbacks to them and finally running an infinite
    event loop so that async functions can be executed on.
    """

    def __init__(self, config_file: str):
        self.config_file = config_file
        self.listeners = {}
        self.loop = None
        self.tasks = set()
        self.stopping = False

    def get_listener(self, listener: list[type, dict]) -> EventListener:
        """
        Get a registered EventListener if already instantiated, or register a new one and returns it
        """
        klass, attributes = listener
        lookup = ".".join([klass.__module__, klass.__name__])
        if attributes:
            lookup += f"[{str(attributes)}]"

        if lookup not in self.listeners:
            self.listeners[lookup] = klass(self)
            for attribute, value in attributes.items():
                setattr(self.listeners[lookup], attribute, value)

        return self.listeners[lookup]

    def add_callback(self, event: list[type, dict], callback: Coroutine):
        """
        Adds a function as a callback to an event listener. If that event listener is not yet
        registered, then it will be instantiated and registered accordingly before callback is set.
        """
        self.get_listener(event).add_callback(callback)

    def stop(self):
        """
        Gracefully stops the event loop
        """
        self.stopping = True

        for task in self.tasks:
            task.cancel()

        self.loop.stop()

    # pylint: disable-next=unused-argument
    def exception_handler(self, loop: asyncio.AbstractEventLoop, context: dict):
        """
        Default exception handler for every EventListener event loop.
        """
        if "exception" not in context:
            return

        traceback.print_exception(context["exception"])
        sys.stdout.flush()

        if isinstance(context["exception"], WMCompanionFatalError):
            if not self.stopping:
                self.stop()
            os._exit(1)  # pylint: disable=protected-access

    def load_user_config(self):
        """
        Loads the user config file and expects that at the final of this step, we will have several
        listeners activated, each with at least one callback.
        """
        try:
            loader = SourceFileLoader("config", self.config_file)
            mod = module_from_spec(spec_from_loader(loader.name, loader))
            loader.exec_module(mod)
        except FileNotFoundError as err:
            raise WMCompanionFatalError(
                f"Config file not found at '{self.config_file}'"
            ) from err

    def run_coro(self, coro: Coroutine) -> asyncio.Task:
        """
        As recommended by Python docs, add the coroutine to a set before adding it to the loop. This
        creates a strong reference and prevents it being garbage-collected before it is done.

        See: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
        See: https://stackoverflow.com/a/62520369
        See: https://bugs.python.org/issue21163
        """
        task = self.loop.create_task(coro)

        # Add it to the set, creating a strong reference
        self.tasks.add(task)
        # But then ensure we clear its reference after it's finished
        task.add_done_callback(self.tasks.discard)

        return task

    async def start_listener(self, listener: EventListener):
        """
        Encapsulate the initialization of the listener so it breaks if any exception is raised.
        """
        try:
            await listener.start()
        except Exception as exc:
            raise WMCompanionFatalError(
                f"Failure while initializing listener {listener.name()}"
            ) from exc

    def run(self):
        """
        Loads the user config, adds all required event listeners to the event loop and start it
        """
        self.loop = asyncio.new_event_loop()
        self.loop.set_exception_handler(self.exception_handler)

        # Load provided config with all definitions
        self.load_user_config()

        if len(self.listeners) == 0:
            logger.warning("No event listeners enabled. Exiting...")
            sys.exit()

        # Add signal handlers
        for sig in [signal.SIGINT, signal.SIGTERM]:
            self.loop.add_signal_handler(sig, self.stop)

        # Run all listeners in the event loop
        for name, listener in self.listeners.items():
            self.run_coro(self.start_listener(listener))
            logger.info("Listener %s started", name)

        # Run GC just to cleanup objects before starting
        gc.collect()

        # Then make sure we run until we hit `stop()`
        self.loop.run_forever()
