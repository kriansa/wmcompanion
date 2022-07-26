# Copyright (c) 2022 Daniel Pereira
# 
# SPDX-License-Identifier: Apache-2.0

class WMCompanionError(Exception):
    """
    Base exception used for all module-based errors. When run inside the loop it will be logged but
    the application will still be running.
    """
    pass

class WMCompanionFatalError(WMCompanionError):
    """
    This exception is, as the name implies, fatal, therefore will stop the application when raised.
    """
    pass
