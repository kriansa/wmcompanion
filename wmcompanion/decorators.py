# Copyright (c) 2022 Daniel Pereira
# 
# SPDX-License-Identifier: Apache-2.0

import functools, types
from .object_container import ObjectContainer
from .event import EventWatcher

class SoftDecorator:
    """
    Traditionally, a decorator intent in Python is to change a function at runtime and its name will
    be automatically referenced to the new changed one, if changed by a decorator. Moreover, a
    decorator runs from inside out, meaning that the last declared decorator will run first, in a
    stack-based fashion, similarly as you would expect when you have a nested function call.

    While this behavior is very convenient and makes writing behavior-changing decorators very
    easily, it is not always wanted in case we want to stack up multiple decorators that may be
    dependent and require some coordination such as order of execution. As a parallel, in languages
    such as Java for instance, there's no such thing as "behavior-changing metadata", and instead we
    have annotations which are used in a similar way to decorators, but they don't automatically
    wrap and modify functions as a decorator in Python would, instead that is up to the application
    to read that metadata and act upon it.

    This class is the simplest implementation I could think of to create the idea of `annotation`
    you have on Java, using Python decorators. The naming embodies the idea of being `soft` as a way
    to state that this does not automatically change the function, instead it only creates a new
    function with the expected behavior applied when you call `with_decorators()` on the function.
    """
    FUNCTION_ATTR_KEY_NAME = '_annotation_decorators'

    def __call__(self, *args, **kwargs):
        """
        Makes this object callable. It is supposed to be called when applied to a function as a
        decorator.
        When called, it saves the arguments passed to the decorator as internal properties (args and
        kwargs) and adds this decorator to the function metadata.
        """
        def decorator(function):
            self.args = args
            self.kwargs = kwargs
            self.add_self_reference(function)
            self.after_declared()
            return function

        return decorator

    def after_declared(self):
        """
        Hook called after a decorator has been added to the function. It is convenient so that we
        can i.e. add the function to a callback list, but it can't change the function behavior, for
        that use `apply` instead.

        This is useful so we don't end up overriding `__call__`
        """
        pass

    def add_self_reference(self, function):
        """
        Links the function to this decorator and vice-versa. Adds a new method (with_decorators) to
        the function object so that when called, it will return a new function with all decorators
        applied.
        """
        if not hasattr(function, self.FUNCTION_ATTR_KEY_NAME):
            setattr(function, self.FUNCTION_ATTR_KEY_NAME, [])

            function_attr_key_name = self.FUNCTION_ATTR_KEY_NAME
            def with_decorators(self) -> callable:
                """
                Returns a new function, with all soft decorators applied in the order they have been
                declared.
                """
                function = self
                for decorator in reversed(getattr(self, function_attr_key_name)):
                    function = decorator.apply(function)
                return function

            function.with_decorators = types.MethodType(with_decorators, function)


        # Add a doubly linked reference between the function and the decorator object
        self.original_function = function
        getattr(function, self.FUNCTION_ATTR_KEY_NAME).append(self)

    def apply(self, function: callable):
        """
        This is the decorator logic that should be applied to the function. It is only applied after
        calling `with_decorators()` method on the function object.
        """
        return function

class UseDecorator(SoftDecorator):
    """
    Inject dependencies on the function at runtime by means of an ObjectContainer.
    """
    def __init__(self, object_container: ObjectContainer):
        self.object_container = object_container

    def apply(self, function: callable):
        curried_function = function
        for dep in self.args:
            obj = self.object_container.get(dep)
            # Set the object to the leftmost parameter of the function
            curried_function = functools.partial(curried_function, obj)
            # Wraps it and make it look like the original function
            curried_function = functools.update_wrapper(curried_function, function)
        return curried_function

class OnDecorator(SoftDecorator):
    """
    Adds the function as a callback to a given event type. If that event is not yet started, then
    also starts it.
    The event callback param will be injected as the first parameter of the function, regardless of
    its value (i.e. if no callback param is passed, None will be passed as the first parameter to
    the function).
    When the EventListener have specific attributes, they can be passed as keyword arguments, after
    the name of the listener, for instance:
        ```
        @on(NetworkChange, ifname="eth0")
        ```
    """
    event_object: any = None

    def __init__(self, event_watcher: EventWatcher):
        self.event_watcher = event_watcher

    def after_declared(self):
        event_klass = self.args[0]
        attributes = self.kwargs
        self.event_watcher.add_callback([event_klass, attributes], self.original_function)

    def apply(self, function: callable):
        # Set the event object to the leftmost parameter of the function. The `event_object` is an
        # attribute set to the function by the EventListener when it triggers the function. After
        # used, let's clean it up so we don't end up with a property we don't want to keep around.
        event_object = function.event_object if hasattr(function, 'event_object') else None
        curried_function = functools.partial(function, event_object)
        if event_object: del function.event_object
        # Now wrap it and make it look like the original function
        return functools.update_wrapper(curried_function, self.original_function)
