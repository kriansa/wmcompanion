# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from ..utils.dbus_client import DBusClient, Variant

class Urgency(Enum):
    LOW = 0
    NORMAL = 1
    CRITICAL = 2

class Category(Enum):
    DEVICE = "device"
    DEVICE_ADDED = "device.added"
    DEVICE_ERROR = "device.error"
    DEVICE_REMOVED = "device.removed"
    EMAIL = "email"
    EMAIL_ARRIVED = "email.arrived"
    EMAIL_BOUNCED = "email.bounced"
    IM = "im"
    IM_ERROR = "im.error"
    IM_RECEIVED = "im.received"
    NETWORK = "network"
    NETWORK_CONNECTED = "network.connected"
    NETWORK_DISCONNECTED = "network.disconnected"
    NETWORK_ERROR = "network.error"
    PRESENCE = "presence"
    PRESENCE_OFFLINE = "presence.offline"
    PRESENCE_ONLINE = "presence.online"
    TRANSFER = "transfer"
    TRANSFER_COMPLETE = "transfer.complete"
    TRANSFER_ERROR = "transfer.error"

class Action:
    def __init__(self, identifier: str, message: str):
        self.identifier = identifier
        self.message = message

    def to_value(self):
        return [self.identifier, self.message]

class HintABC:
    """
    Hints are a way to provide extra data to a notification server that the server may be able to
    make use of.

    Usage:
    hints = [Hint.ActionIcons(False), Hint.Urgency(Urgency.LOW)]
    """

    def __init__(self, value: any):
        self.value = value

    def to_value(self):
        raw = self.value_type(self.value)
        if hasattr(raw, 'value'): raw = raw.value # Unwrap Enums
        return [self.name, Variant(self.signature, raw)]

class Hint:
    class ActionIcons(HintABC):
        """
        When set, a server that has the "action-icons" capability will attempt to interpret any
        action identifier as a named icon. The localized display name will be used to annotate
        the icon for accessibility purposes. The icon name should be compliant with the
        Freedesktop.org Icon Naming Specification.
        """
        name = "action-icons"
        value_type = bool
        signature = "b"

    class Category(HintABC):
        """
        The type of notification this is.
        """
        name = "category"
        value_type = Category
        signature = "s"

    class DesktopEntry(HintABC):
        """
        This specifies the name of the desktop filename representing the calling program. This
        should be the same as the prefix used for the application's .desktop file. An example would
        be "rhythmbox" from "rhythmbox.desktop". This can be used by the daemon to retrieve the
        correct icon for the application, for logging purposes, etc.
        """
        name = "desktop-entry"
        value_type = str
        signature = "s"

    class ImageData(HintABC):
        """
        This is a raw data image format which describes the width, height, rowstride, has alpha,
        bits per sample, channels and image data respectively.

        Usage: ImageData([width, height, rowstride, alpha_bool, bits, channels, imgdata_bytes])
        """
        name = "image-data"
        value_type = list
        signature = "(iiibiiay)"

    class ImagePath(HintABC):
        """
        Alternative way to define the notification image.

        It should be either an URI (file:// is the only URI schema supported right now) or a name in
        a freedesktop.org-compliant icon theme (not a GTK+ stock ID).

        See: https://specifications.freedesktop.org/notification-spec/notification-spec-latest.html#icons-and-images
        """
        name = "image-path"
        value_type = str
        signature = "s"

    class Resident(HintABC):
        """
        The server will not automatically remove the notification when an action has been
        invoked. The notification will remain resident in the server until it is explicitly removed
        by the user or by the sender. This hint is likely only useful when the server has the
        "persistence" capability.
        """
        name = "resident"
        value_type = bool
        signature = "b"

    class SoundFile(HintABC):
        """
        The path to a sound file to play when the notification pops up.
        """
        name = "sound-file"
        value_type = str
        signature = "s"

    class SoundName(HintABC):
        """
        A themeable named sound from the freedesktop.org sound naming specification to play when the
        notification pops up. Similar to icon-name, only for sounds. An example would be
        "message-new-instant".
        """
        name = "sound-file"
        value_type = str
        signature = "s"

    class SuppressSound(HintABC):
        """
        Causes the server to suppress playing any sounds, if it has that ability. This is usually
        set when the client itself is going to play its own sound.
        """
        name = "suppress-sound"
        value_type = bool
        signature = "b"

    class Transient(HintABC):
        """
        When set the server will treat the notification as transient and by-pass the server's
        persistence capability, if it should exist.
        """
        name = "transient"
        value_type = bool
        signature = "b"

    class PositionX(HintABC):
        """
        Specifies the X location on the screen that the notification should point to. The "y" hint
        must also be specified.
        """
        name = "x"
        value_type = int
        signature = "i"

    class PositionY(HintABC):
        """
        Specifies the Y location on the screen that the notification should point to. The "x" hint
        must also be specified.
        """
        name = "y"
        value_type = int
        signature = "i"

    class Urgency(HintABC):
        """
        The urgency level.

        Usage: Hints.Urgency(Urgency.LOW)
        """
        name = "urgency"
        value_type = Urgency
        signature = "y"

    # Non-standard hints. All prependend with X and the vendor name.
    # For now, only Dunst ones, but in the future it might also accomodate hints for other servers.
    #
    # See: https://dunst-project.org/documentation

    class XDunstProgressBarValue(HintABC):
        """
        Non-standard hint, used by Dunst.

        A progress bar will be drawn at the bottom of the notification.
        """
        name = "value"
        value_type = int
        signature = "i"

    class XDunstFgColor(HintABC):
        """
        Non-standard hint, used by Dunst.

        Foreground color in the format #RRGGBBAA.
        """
        name = "fgcolor"
        value_type = str
        signature = "s"

    class XDunstBgColor(HintABC):
        """
        Non-standard hint, used by Dunst.

        Background color in the format #RRGGBBAA.
        """
        name = "bgcolor"
        value_type = str
        signature = "s"

    class XDunstFrColor(HintABC):
        """
        Non-standard hint, used by Dunst.

        Frame color in the format #RRGGBBAA.
        """
        name = "frcolor"
        value_type = str
        signature = "s"

    class XDunstHlColor(HintABC):
        """
        Non-standard hint, used by Dunst.

        Highlight color (also sets the color of the progress bar) in the format #RRGGBBAA.
        """
        name = "hlcolor"
        value_type = str
        signature = "s"

    class XDunstStackTag(HintABC):
        """
        Non-standard hint, used by Dunst.

        Notifications with the same (non-empty) stack tag and the same appid will replace each-other
        so only the newest one is visible. This can be useful for example in volume or brightness
        notifications where you only want one of the same type visible.
        """
        name = "x-dunst-stack-tag"
        value_type = str
        signature = "s"

class Notify:
    """
    Send desktop notifications according to the Freedesktop spec.
    See: https://specifications.freedesktop.org/notification-spec/notification-spec-latest.html
    """

    def __init__(self):
        self.dbus_client = DBusClient()

    async def notify(
        self, summary: str, body: str = "",
        urgency: Urgency = None, category: Category = None, transient: bool = False,
        dunst_progress_bar: int = -1, dunst_stack_tag: str = "", dunst_fg_color: str = "",
        dunst_bg_color: str = "", dunst_fr_color: str = "", dunst_hl_color: str = "",
        icon: str = "", expire_time_ms: int = -1, app_name: str = "", replaces_id: int = 0,
        hints: list[Hint] = [], actions: list[Action] = [],
    ) -> dict:
        """
        Parse arguments and convert them to hints if applicable, then send the desktop notification
        using DBus.
        """
        if urgency: hints.append(Hint.Urgency(urgency))
        if category: hints.append(Hint.Category(category))
        if transient: hints.append(Hint.Transient(transient))
        if dunst_progress_bar >= 0: hints.append(Hint.XDunstProgressBarValue(dunst_progress_bar))
        if dunst_stack_tag: hints.append(Hint.XDunstStackTag(dunst_stack_tag))
        if dunst_fg_color: hints.append(Hint.XDunstFgColor(dunst_fg_color))
        if dunst_bg_color: hints.append(Hint.XDunstBgColor(dunst_bg_color))
        if dunst_fr_color: hints.append(Hint.XDunstFrColor(dunst_fr_color))
        if dunst_hl_color: hints.append(Hint.XDunstHlColor(dunst_hl_color))

        return await self.send(
            summary=summary, body=body, icon=icon, expire_time_ms=expire_time_ms,
            app_name=app_name, replaces_id=replaces_id, actions=actions, hints=hints,
        )

    # Make this object callable by invoking notify
    __call__ = notify

    async def send(
        self,
        summary: str,
        body: str = "",
        icon: str = "",
        expire_time_ms: int = -1,
        app_name: str = __name__,
        replaces_id: int = 0,
        actions: list[Action] = [],
        hints: list[Hint] = [],
    ) -> int:
        """
        Send the notification to the Desktop Notifications Daemon via DBus
        """
        if hints:
            hints = dict([hint.to_value() for hint in hints])
        else:
            hints = {}

        if actions:
            actions = [action.to_value() for action in actions]

        params = [
            app_name,
            replaces_id,
            icon,
            summary,
            body,
            actions,
            hints,
            expire_time_ms,
        ]

        id = await self.dbus_client.call_method(
            destination = "org.freedesktop.Notifications",
            interface = "org.freedesktop.Notifications",
            path = "/org/freedesktop/Notifications",
            member = "Notify",
            signature = "susssasa{sv}i",
            body = params,
        )

        return id
