# SPDX-License-Identifier: GPL-3.0-or-later
"""Native window title bar colour: follow the OS light/dark theme (or force dark / light / theme colour).

* Windows 10 1809+ / 11: DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE = 20, or 19 on old Windows 10
  builds). Windows 11 (build 22000+) also gets caption / border / text colours in "theme" mode.
  The system setting is read from HKCU\\...\\Themes\\Personalize\\AppsUseLightTheme and polled every ~2 s,
  so switching Windows between light and dark updates the window live.
* macOS: GLFW windows already follow the system appearance; nothing to do.
* Linux: depends on the window manager / desktop. Best effort: the _GTK_THEME_VARIANT hint (honoured by
  GNOME/Mutter, Budgie and other GTK-based window managers) is set with xprop when available (X11/XWayland).
Every failure is silent: the title bar simply keeps the default look.
"""
import os
import subprocess
import sys
import time

MODES = ("system", "dark", "light", "theme")

DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWA_COLOR_DEFAULT = 0xFFFFFFFF

# "theme" mode colours (same as the menu bar / toolbar of the purple theme)
THEME_CAPTION = (0.075, 0.040, 0.105)
THEME_BORDER = (0.62, 0.30, 1.00)
THEME_TEXT = (0.95, 0.80, 1.00)


def colorref(rgb):
    """(r, g, b) floats 0..1 -> Win32 COLORREF 0x00BBGGRR."""
    r, g, b = [max(0, min(255, int(round(c * 255)))) for c in rgb]
    return r | (g << 8) | (b << 16)


# ---------------------------------------------------------------------------- system theme detection
def _windows_dark():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return int(v) == 0
    except Exception:
        return None


def _mac_dark():
    try:
        out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True,
                             timeout=2).stdout
        return "dark" in out.lower()
    except Exception:
        return None


def _env():
    from nimcale import paths
    return paths.host_env()


def _linux_dark():
    if os.environ.get("GTK_THEME"):
        return "dark" in os.environ["GTK_THEME"].lower()
    for key in (("org.gnome.desktop.interface", "color-scheme"), ("org.gnome.desktop.interface", "gtk-theme")):
        try:
            out = subprocess.run(["gsettings", "get", key[0], key[1]], capture_output=True, text=True,
                                 timeout=2, env=_env()).stdout.strip().lower()
        except Exception:
            continue
        if out:
            if "dark" in out:
                return True
            if key[1] == "color-scheme" and ("light" in out or "default" in out):
                return False
    return None


def system_prefers_dark():
    """True / False, or None when the OS does not tell."""
    if sys.platform == "win32":
        return _windows_dark()
    if sys.platform == "darwin":
        return _mac_dark()
    return _linux_dark()


def resolve(mode, system_dark):
    """-> (dark: bool, theme_colours: bool). Unknown system theme counts as dark (the app itself is dark)."""
    if mode not in MODES:
        mode = "system"
    if mode == "dark":
        return True, False
    if mode == "light":
        return False, False
    if mode == "theme":
        return True, True
    return (True if system_dark is None else bool(system_dark)), False


# ---------------------------------------------------------------------------- applying
def _windows_build():
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def apply_windows(hwnd, dark, theme_colors):
    import ctypes
    from ctypes import wintypes
    dwm = ctypes.windll.dwmapi
    dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    dwm.DwmSetWindowAttribute.restype = ctypes.c_long

    def set_attr(attr, value):
        v = ctypes.c_uint32(value)
        return dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0

    build = _windows_build()
    how = "unsupported"
    if build >= 17763 or build == 0:
        if set_attr(DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0):
            how = "dwm20"
        elif set_attr(DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1 if dark else 0):
            how = "dwm19"
    if build >= 22000:                          # Windows 11: explicit colours (or back to default)
        if theme_colors:
            ok = set_attr(DWMWA_CAPTION_COLOR, colorref(THEME_CAPTION))
            set_attr(DWMWA_BORDER_COLOR, colorref(THEME_BORDER))
            set_attr(DWMWA_TEXT_COLOR, colorref(THEME_TEXT))
            if ok:
                how += "+colors"
        else:
            for a in (DWMWA_CAPTION_COLOR, DWMWA_BORDER_COLOR, DWMWA_TEXT_COLOR):
                set_attr(a, DWMWA_COLOR_DEFAULT)
    # repaint the non-client area so the change is visible immediately
    try:
        u = ctypes.windll.user32
        SWP = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020      # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED
        u.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP)
        u.RedrawWindow(hwnd, None, None, 0x0001 | 0x0400 | 0x0100)   # INVALIDATE|FRAME|UPDATENOW
    except Exception:
        pass
    return how


def apply_x11(xid, dark):
    try:
        r = subprocess.run(["xprop", "-id", str(int(xid)), "-f", "_GTK_THEME_VARIANT", "8u", "-set",
                            "_GTK_THEME_VARIANT", "dark" if dark else "light"], capture_output=True, timeout=3,
                           env=_env())
        return "x11-gtk-variant" if r.returncode == 0 else "unsupported"
    except Exception:
        return "unsupported"


class TitleBar:
    """Keeps the native title bar in sync with the setting and the OS theme."""
    POLL = 2.0

    def __init__(self, get_mode, log=print):
        self.get_mode = get_mode
        self.log = log
        self.handle = None          # ("win32", hwnd) | ("x11", xid) | ("cocoa", None)
        self.applied = None
        self.last_poll = 0.0
        self.system_dark = None
        self.how = "unsupported"

    def attach_glfw(self, glfw_window):
        import glfw
        try:
            if sys.platform == "win32":
                self.handle = ("win32", glfw.get_win32_window(glfw_window))
            elif sys.platform == "darwin":
                self.handle = ("cocoa", None)
            else:
                xid = None
                try:
                    xid = glfw.get_x11_window(glfw_window)
                except Exception:
                    pass
                self.handle = ("x11", xid) if xid else ("other", None)
        except Exception as e:
            self.handle = ("other", None)
            self.log("title bar: no native handle (%s)" % e)
        self.update(force=True)

    def update(self, force=False):
        """Call every frame; cheap (polls the OS theme at most every POLL seconds)."""
        if self.handle is None:
            return
        now = time.time()
        if not force and now - self.last_poll < self.POLL:
            return
        self.last_poll = now
        mode = self.get_mode()
        if mode == "system" or force:
            self.system_dark = system_prefers_dark()
        dark, colors = resolve(mode, self.system_dark)
        state = (mode, dark, colors)
        if state == self.applied and not force:
            return
        self.applied = state
        kind, h = self.handle
        try:
            if kind == "win32" and h:
                self.how = apply_windows(h, dark, colors)
            elif kind == "x11" and h:
                self.how = apply_x11(h, dark)
            elif kind == "cocoa":
                self.how = "macos-system-appearance"
            else:
                self.how = "unsupported"
        except Exception as e:
            self.how = "failed (%s)" % e
        self.log("title bar: mode=%s system_dark=%s dark=%s theme_colors=%s applied=%s"
                 % (mode, self.system_dark, dark, colors, self.how))
