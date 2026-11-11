# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen-executable entry point (PyInstaller)."""
import sys

from nimcale.launcher import main

if __name__ == "__main__":
    sys.exit(main())
