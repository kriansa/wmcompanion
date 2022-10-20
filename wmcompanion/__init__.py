# Copyright (c) 2022 Daniel Pereira
#
# SPDX-License-Identifier: Apache-2.0

# This is the `index` of wmcompanion module, and this file is supposed to hold the most used names
# that the user config may need.
#
# Due to the architecture of wmcompanion, it was chosen not to have any initialized value here, and
# instead this would be done dynamically, after the application start.
#
# In short, this means that names on this module will be dynamically set by
# `app.App#setup_index_module_exports`, so if you need to find out what they are, just go and read
# that method.

__version__ = "0.6.0"

# Below are the names that this module exports. They are here for static reference so linters can
# find out what names this module exports.
# They are actually defined on `app.py` - remember to keep the back ref when changing that file.
#
# pylint: disable=invalid-name
use = "static-export"
on = "static-export"
