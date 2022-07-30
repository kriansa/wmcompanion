# wmcompanion

You want to react to your system events to easily automate your workflow or power your desktop user
experience? All that using highly customizable code that is not just a bunch of scripts around that
you don't even remember where to change?

```python
@on(NetworkConnectionStatus, connection_name="Wired-Network")
@use(Polybar)
@use(Notify)
async def network_status(status: dict, polybar: Polybar, notify: Notify):
    color = "blue" if status["connected"] else "gray"
    await polybar("eth", polybar.fmt("eth", color=color))
    msg = "connected" if status["connected"] else "disconnected"
    await notify(f"Hey, wired network is {msg}")
```

Initially built for people using tiling window managers that don't have the many of the features
that a full `DE` provides, but still want some convenience and automation here and there without
having to rely on lots of unorganized shell scripts running without supervision. Things like
bluetooth status notifications, keyboard layout visualizer, volume, network manager status and etc.

![image](docs/example-bar.png)
> Example of Polybar widgets powered by wmcompanion, in less than 80 lines of code.

## Usage

### Install

Currently it's available as an OS package for Arch Linux. On other platforms, you can pull this
repository, install `poetry` and run `poetry run wmcompanion`.

* [AUR][aur]

### Configure

You must add a config file on `~/.config/wmcompanion/config.py`. For starters, you can use the one
below:

```python
from wmcompanion import use, on
from wmcompanion.modules.notifications import Notify
from wmcompanion.events.audio import MainVolumeLevel

@on(MainVolumeLevel)
@use(Notify)
async def volume_level(volume: dict, notify: Notify):
    await notify(f"Your volume levels: {volume=}")
```

You can get really creative by reading the source files under `events` folder.

## Why not X?

One might ask: But isn't most of that feature set already available on a status bar such as Polybar,
for instance?

Generally, yes, but then you will be limited by the features of that status bar and how they are
implemented internally, and have a small room for customization. Ever wanted to have microphone
volume on Polybar? Or a `kbdd` widget? Or a built-in `dunst` pause toggle? You may be well served
with the default option your status bar provides, but you also might want more out of it and they
can not be as easily customizable or integrate well with, let's say, notifications, for instance.

Moreover, `wmcompanion` isn't designed to power status bars, instead it is modeled around listening
to events and reacting to them. One of these reactions might be to update a status bar. But it can
also be to send a notification, or perhaps change a layout, update your monitor setup, etc. The
important part is that it is meant to be integrated and easily scriptable in a single service, and
you won't have to maintain and manually orchestrate several scripts to make your desktop experience
more pleasant.

## Available events

By default, `wmcompanion` is _accompanied_ by many _`EventListeners`_ already. An `EventListener` is
the heart of the application. But they are simply Python classes that can listen to system events
asynchronously and notify the user configured callbacks whenever there's a change in the state.

Currently there are the following event listeners available:

* Main audio input/output volume level (`events.audio.MainVolumeLevel`)
* Bluetooth status (`events.bluetooth.BluetoothRadioStatus`)
* [Kbdd][kbdd] selected layout (`events.keyboard.KbddChangeLayout`)
* NetworkManager connection status (`events.network.NetworkConnectionStatus`)
* NetworkManager Wi-Fi status/strength (`events.network.WifiStatus`)
* Dunst notification pause status (`events.notifications.DunstPausedStatus`)
* Power actions (`events.power.PowerActions`)

The general idea is to develop events very easily and they can be reused by others, even if they are
not integrated in this codebase -- they just need to extend the `event_listening.EventListener`
class.

## Built-in modules

Modules are built-in integrations with the most common desktop tooling so that you don't need to
reimplement them for your configurations. All you need is to inject them at runtime and they will be
available to you automatically, keeping your user configuration clean.

For instance, instead of playing with `notify-send` manually, there's a builtin module that you can
invoke from within Python script and it will work as you would expect.

* Polybar IPC _(replaces `polybar-msg action`)_ (`modules.polybar.Polybar`)
* Notifications _(replaces `notify-send`)_ (`modules.notifications.Notify`)

## Development

In order to run the daemon in development mode, just run:

```sh
$ poetry run wmcompanion
```

## Acknowledgements

The main design is based on Vincent Bernat's [great i3-companion][i3-companion] script. The
`DBusClient` util was partially extracted from [qtile utils][qtile-utils]. The `INotify` util was
extracted from Chris Billington's [inotify_simple][inotify-simple].

[i3-companion]: https://github.com/vincentbernat/i3wm-configuration/blob/master/bin/i3-companion
[qtile-utils]: https://github.com/qtile/qtile/blob/master/libqtile/utils.py
[inotify-simple]: https://github.com/chrisjbillington/inotify_simple/blob/master/inotify_simple.py
[kbdd]: https://github.com/qnikst/kbdd
[aur]: https://aur.archlinux.org/packages/wmcompanion
