# SPDX-License-Identifier: GPL-3.0-or-later
"""Locations of bundled resources and per-user folders."""
import os
import sys

from nimcale import APP_ID


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def package_dir():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "nimcale")
    return os.path.dirname(os.path.abspath(__file__))


def assets_dir():
    return os.path.join(package_dir(), "assets")


def asset(*parts):
    return os.path.join(assets_dir(), *parts)


def app_dir():
    """Folder of the executable (frozen) or of the repository checkout."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(package_dir())


def config_dir():
    """%APPDATA%\\Nimcale on Windows, ~/.config/Nimcale elsewhere (override: NIMCALE_CONFIG_DIR)."""
    d = os.environ.get("NIMCALE_CONFIG_DIR")
    if not d:
        if sys.platform == "win32":
            d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_ID)
        elif sys.platform == "darwin":
            d = os.path.expanduser("~/Library/Application Support/" + APP_ID)
        else:
            d = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), APP_ID)
    os.makedirs(d, exist_ok=True)
    return d


def documents_dir():
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return buf.value
        except Exception:
            pass
    d = os.path.expanduser("~/Documents")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def output_dir(sub=""):
    """Default folder for screenshots and exports: Documents/Nimcale[/sub]."""
    d = os.path.join(documents_dir(), APP_ID, sub) if sub else os.path.join(documents_dir(), APP_ID)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = config_dir()
    return d


def unique_path(folder, stem, ext):
    n = 1
    while True:
        p = os.path.join(folder, "%s_%03d.%s" % (stem, n, ext))
        if not os.path.exists(p):
            return p
        n += 1


def host_env():
    """Environment for launching system programs (xdg-open, zenity, gsettings, xprop...).

    The frozen Linux build runs with LD_LIBRARY_PATH pointing at its bundled libraries; system programs
    must get the user's original value back (PyInstaller keeps it in *_ORIG), or they may fail to start."""
    env = dict(os.environ)
    if is_frozen() and not sys.platform.startswith(("win", "darwin")):
        for k in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
            orig = env.pop(k + "_ORIG", None)
            if orig is not None:
                env[k] = orig
            else:
                env.pop(k, None)
    return env
