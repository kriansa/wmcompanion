# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

from argparse import ArgumentParser
from . import __version__
from .app import App


def main():
    """
    wmcompanion is an event listener focused on desktop activities and user customization.

    It leverages the power of Python to create useful hooks to several system events, such as
    NetworkManager connection, Bluetooth activation and many others.

    The focus is being easily customizable and highly flexible, being able to
    power status bars such as Polybar or i3bar, as well as to manage monitor
    arrangements using xrandr.
    """

    parser = ArgumentParser(description=main.__doc__)
    parser.add_argument("-c", "--config-file", help="user config file path")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--verbose", action="store_true", help="increase the log verbosity"
    )

    args = parser.parse_args()
    App(config_file=args.config_file, verbose=args.verbose).start()
