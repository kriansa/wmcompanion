# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

from .errors import WMCompanionError


class ObjectContainerError(WMCompanionError):
    """
    Base exception class for all object_container module based errors
    """


class ObjectContainer:
    """
    A minimalist implementation of an IoC container for managing dependencies at runtime.
    """

    def __init__(self):
        self.objects = {}

    def register(self, value: any, name: str | type = None):
        """
        Adds a new object to the container. If no name is given, then it tries to guess a name for
        that object, but if not possible then an exception is raised instead.
        """
        if not name:
            # If it's a class, then register it directly
            if isinstance(value, type):
                name = value.__name__
                value = value()  # We always instantiate it without args
            else:
                type_name = type(value).__name__
                raise ObjectContainerError(
                    f"You must provide a name to register this object type ({type_name})."
                )

        self.objects[name] = value

    def get(self, dependency: str | type):
        """
        Fetch an object which name matches the specified argument. If there's no object available
        for that name, it registers them before usage.
        Raises an exception if such name is not found.
        """
        if hasattr(dependency, "__name__"):
            lookup = dependency.__name__
        else:
            lookup = dependency

        if lookup not in self.objects:
            try:
                self.register(dependency)
            except ObjectContainerError as err:
                raise ObjectContainerError(
                    f"Object named {lookup} was not found in the container."
                ) from err

        return self.objects[lookup]
