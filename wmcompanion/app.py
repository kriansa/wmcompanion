# Copyright (c) 2022 Daniel Pereira
# 
# SPDX-License-Identifier: Apache-2.0

import os, sys, logging
from .object_container import ObjectContainer
from .event import EventWatcher
from .decorators import UseDecorator, OnDecorator

class App:
    """
    Orchestrate the application functionality into a single unit.

    Instantiate then hit `start()` to have it running.
    """
    def __init__(self, config_file: str, verbose: bool = False):
        self.config_file = config_file or self._default_config_file_path()
        self.event_watcher = None
        self.object_container = None
        self.verbose = verbose

    def _default_config_file_path(self) -> str:
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return f"{config_home}/wmcompanion/config.py"

    def setup_logging(self):
        """
        Setup the global application logging
        """
        log_level = "DEBUG" if self.verbose else "INFO"
        log_format = "[%(levelname)s] [%(filename)s:%(funcName)s():L%(lineno)d] %(message)s"
        logging.basicConfig(level = log_level, format = log_format)

    def setup_index_module_exports(self):
        """
        Dynamically assigns export values for the `wmcompanion` module, so that the user config file
        can pick up only the values already instantiated by this application.
        """
        decorators = self.create_decorators()
        for name, decorator in decorators.items():
            setattr(sys.modules['wmcompanion'], name, decorator)

    def create_decorators(self):
        """
        Instantiate all decorators that will be useful for the user config file
        """
        return {
            "use": UseDecorator(self.object_container),
            "on": OnDecorator(self.event_watcher)
        }

    def start(self):
        """
        Instantiate all required application classes then run it

        It will stop gracefully when receiving a SIGINT or SIGTERM
        """
        self.object_container = ObjectContainer()
        self.event_watcher = EventWatcher(self.config_file)
        self.setup_logging()
        self.setup_index_module_exports()
        self.event_watcher.run()
