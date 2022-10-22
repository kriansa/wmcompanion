# wmcompanion - "Build your own DE"

You use a minimalist tiling window manager , yet you want to be able to tinker with your desktop more
easily and implement features like the ones available in full blown desktop environments?

More specifically, you want to react to system events (such as returning from sleep, or wifi signal
change) and easily automate your workflow or power your desktop user experience using a consistent
and centralized configuration so it is _actually_ easy to maintain?

## Show me

See below small examples of the broad idea that is `wmcompanion` and what you can achieve with small
amounts of code.

- Send a desktop notification and updates a given module on Polybar whenever a certain connection
  managed by NetworkManager changes statuses:
  ```python
  from wmcompanion import use, on
  from wmcompanion.modules.polybar import Polybar
  from wmcompanion.modules.notifications import Notify
  from wmcompanion.events.network import NetworkConnectionStatus

  @on(NetworkConnectionStatus, connection_name="Wired-Network")
  @use(Polybar)
  @use(Notify)
  async def network_status(status: dict, polybar: Polybar, notify: Notify):
      color = "blue" if status["connected"] else "gray"
      await polybar("eth", polybar.fmt("eth", color=color))

      msg = "connected" if status["connected"] else "disconnected"
      await notify(f"Hey, wired network is {msg}")
  ```

- Add a microphone volume level to Polybar:
  ```python
  from wmcompanion import use, on
  from wmcompanion.modules.polybar import Polybar
  from wmcompanion.events.audio import MainVolumeLevel

  @on(MainVolumeLevel)
  @use(Polybar)
  async def volume_level(volume: dict, polybar: Polybar):
     if not volume["input"]["available"]:
         return await polybar("mic", "")

     if not volume["muted"]:
         level = int(volume['level'] * 100)
         text = f"[mic: {level}]"
         color = "blue"
     else:
         text = "[mic: muted]"
         color = "gray"

     await polybar("mic", polybar.fmt(text, color=color))
  ```

- Set your monitor screen arrangement on plug/unplug events:
  ```python
  from wmcompanion import use, on
  from wmcompanion.modules.notifications import Notify
  from wmcompanion.events.x11 import DeviceState

  @on(DeviceState)
  @use(Notify)
  async def configure_screens(status: dict, notify: Notify):
      if status["event"] == DeviceState.ChangeEvent.SCREEN_CHANGE:
        await cmd("autorandr")
        await notify("Screen layout adjusted!")
  ```

- A [more complex example][polybar-example] of Polybar widgets powered by wmcompanion, in less than
  80 lines of code:

  ![image](docs/example-bar.png)

## Who is this for?

It is initially built for people using tiling window managers that don't have the many of the
features that a full `DE` provides, but still want some convenience and automation here and there
without having to rely on lots of unorganized shell scripts running without supervision. Things like
bluetooth status notifications, keyboard layout visualizer, volume, network manager status and so
on.

If you already have a desktop environment such as GNOME or KDE, this tool is probably not for you,
as most of its features are already built-in on those. However, there's absolutely nothing stopping
you from using it, as it is so flexible you may find it useful for other purposes (such as
notifications, for instance).

### Design rationale

You might want to ask: isn't most of that feature set already available on a status bar such as
Polybar, for instance? And some of them aren't just a matter of writing a simple shell script?

Generally, yes, but then you will be limited by the features of that status bar and how they are
implemented internally, and have a small room for customization. Ever wanted to have microphone
volume on Polybar? Or a `kbdd` widget? Or a built-in `dunst` pause toggle? You may be well served
with the default option your status bar provides, but you also might want more out of it and they
can not be as easily customizable or integrate well with, let's say, notifications, for instance.

Moreover, `wmcompanion` isn't designed to power status bars or simply serve as a notification
daemon. Instead it is modeled around listening to events and reacting to them. One of these
reactions might be to update a status bar, of course. But it can also be to send a notification, or
perhaps change a layout, update your monitor setup, etc. The important part is that it is meant to
be integrated and easily scriptable in a single service, and you won't have to maintain and manually
orchestrate several scripts to make your desktop experience more pleasant.

## Usage

### 1. Install

Currently it's available as an OS package for [Arch Linux on AUR][aur]. On other platforms, you can
pull this repository, install `poetry` and run `poetry run wmcompanion`.

### 2. Configure

First, you need to add a config file on `~/.config/wmcompanion/config.py`. For starters, you can use
the one below:

```python
from wmcompanion import use, on
from wmcompanion.modules.notifications import Notify
from wmcompanion.events.audio import MainVolumeLevel

@on(MainVolumeLevel)
@use(Notify)
async def volume_level(volume: dict, notify: Notify):
    await notify(f"Your volume levels: {volume=}")
```

Take a look at [examples][examples] if you want to get inspired, and you can get really creative by
reading the source files under `events` folder.

### 3. Run

You can simply run `wmcompanion` as it's an executable installed on your system, or use `poetry run
wmcompanion` in case you downloaded the codebase using git.

Most people already have many user daemons running as part of their `.xinit` file, and that's a
fine place for you to run it automatically on user login.

A recommendation is to keep it under a `systemd` user unit, so it's separate from your window
manager and you can manage logs and failures a bit better.

## Available event listeners

By default, `wmcompanion` is _accompanied_ by many _`EventListeners`_ already. An `EventListener` is
the heart of the application. Yet, they are simple Python classes that can listen to system events
asynchronously and notify the user configured callbacks whenever there's a change in the state.

Currently there are the following event listeners available:

* Main audio input/output volume level with WirePlumber (`events.audio.MainVolumeLevel`)
* Bluetooth status (`events.bluetooth.BluetoothRadioStatus`)
* [Kbdd][kbdd] currently selected layout (`events.keyboard.KbddChangeLayout`)
* NetworkManager connection status (`events.network.NetworkConnectionStatus`)
* NetworkManager Wi-Fi status/strength (`events.network.WifiStatus`)
* Dunst notification pause status (`events.notifications.DunstPausedStatus`)
* Power actions (`events.power.PowerActions`)
* Logind Idle status (`events.power.LogindIdleStatus`)
* X11 monitor and input device changes (`events.x11.DeviceState`) **[requires python-xcffib]**

The architecture allows for developing event listeners very easily and make them reusable by others,
even if they are not integrated in this codebase -- they just need to be classes extending
`wmcompanion.event_listening.EventListener` and you can even include them in your dotfiles.

## Built-in modules

Modules are built-in integrations with the most common desktop tooling so that you don't need to
reimplement them for your configurations. All you need is to inject them at runtime and they will be
available to you automatically, keeping your user configuration clean.

For instance, instead of playing with `notify-send` manually, there's a builtin module that you can
invoke from within Python script and it will work as you would expect.

* Polybar IPC _(replaces `polybar-msg action`)_ (`modules.polybar.Polybar`)
* Notifications _(replaces `notify-send`)_ (`modules.notifications.Notify`)

### Polybar IPC integration

In order to use Polybar integration, you need to create a module on Polybar using `custom/ipc` as
the type and then add an initial hook to it so it reads from wmcompanion's module upon
initialization. Here's an example below:

```ini
[module/kbdd]
type = custom/ipc
hook-0 = cat $XDG_RUNTIME_DIR/polybar/kbdd 2> /dev/null
initial = 1
```

Mind you that, for that example, `kbdd` must be the first string argument that you pass when
calling `polybar()` on a wmcompanion callback:

```python
@use(Polybar)
async def my_callback(status: dict, polybar: Polybar):
    await polybar("kbdd", "any string that will show up on polybar")
```

### Desktop notifications

We have a full implementation of the [desktop notifications spec][desktop-notifications], and it's
super easy to use:

```python
@use(Notify)
async def my_callback(status: dict, notify: Notify):
    await notify("Summary", "Body")
```

It also provides native support for Dunst-specific behaviors, such as progress bar and colors:

```python
await notify("Volume level", dunst_progress_bar: 20)
```


As always, refer to the [source code][notifications.py] if you want more details.

## Development

In order to run the daemon in development mode, just run:

```sh
$ poetry run wmcompanion
```

## Acknowledgements

* Main design is inspired by Vincent Bernat's [great i3-companion][i3-companion] script.
* The `DBusClient` util was partially extracted from [qtile utils][qtile-utils].
* The `INotify` util was partially extracted from Chris Billington's
  [inotify_simple][inotify-simple].

[i3-companion]: https://github.com/vincentbernat/i3wm-configuration/blob/master/bin/i3-companion
[qtile-utils]: https://github.com/qtile/qtile/blob/master/libqtile/utils.py
[inotify-simple]: https://github.com/chrisjbillington/inotify_simple/blob/master/inotify_simple.py
[kbdd]: https://github.com/qnikst/kbdd
[aur]: https://aur.archlinux.org/packages/wmcompanion
[desktop-notifications]: https://specifications.freedesktop.org/notification-spec/notification-spec-latest.html
[notifications.py]: ./wmcompanion/modules/notifications.py
[examples]: ./examples
[polybar-example]: ./examples/polybar_icons.py

## License

Apache V2.
