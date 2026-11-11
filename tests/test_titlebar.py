# SPDX-License-Identifier: GPL-3.0-or-later
import sys

import pytest

from nimcale.ui import titlebar as tb


def test_colorref():
    assert tb.colorref((1, 0, 0)) == 0x0000FF
    assert tb.colorref((0, 1, 0)) == 0x00FF00
    assert tb.colorref((0, 0, 1)) == 0xFF0000
    assert tb.colorref((2, -1, 0.5)) == 0xFF | (0 << 8) | (128 << 16)


@pytest.mark.parametrize("mode,system,expected", [
    ("system", True, (True, False)), ("system", False, (False, False)), ("system", None, (True, False)),
    ("dark", False, (True, False)), ("light", True, (False, False)), ("theme", False, (True, True)),
    ("bogus", False, (False, False)),
])
def test_resolve(mode, system, expected):
    assert tb.resolve(mode, system) == expected


def test_system_detection_never_raises():
    assert tb.system_prefers_dark() in (True, False, None)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
def test_windows_registry_value():
    assert tb._windows_dark() in (True, False, None)


def test_follow_system_live(monkeypatch):
    """The bar is re-applied when the OS theme or the setting changes, and only then."""
    logs, applied = [], []
    state = {"dark": False, "mode": "system"}
    monkeypatch.setattr(tb, "system_prefers_dark", lambda: state["dark"])
    monkeypatch.setattr(tb, "apply_windows", lambda h, d, c: applied.append((d, c)) or "dwm20")
    bar = tb.TitleBar(lambda: state["mode"], log=logs.append)
    bar.POLL = 0.0
    bar.handle = ("win32", 1234)
    bar.update(force=True)
    assert applied == [(False, False)]
    bar.update()
    assert applied == [(False, False)]           # nothing changed -> not re-applied
    state["dark"] = True                           # user switches Windows to dark mode
    bar.update()
    assert applied[-1] == (True, False)
    state["mode"] = "theme"                        # user picks "theme colour" in Settings
    bar.update()
    assert applied[-1] == (True, True)
    assert all(m.startswith("title bar: mode=") for m in logs) and "applied=dwm20" in logs[-1]


def test_unsupported_platform_is_silent():
    logs = []
    bar = tb.TitleBar(lambda: "system", log=logs.append)
    bar.handle = ("other", None)
    bar.update(force=True)
    assert bar.how == "unsupported" and "applied=unsupported" in logs[-1]


def test_apply_failure_is_silent(monkeypatch):
    def boom(*a):
        raise OSError("no dwmapi")
    monkeypatch.setattr(tb, "apply_windows", boom)
    bar = tb.TitleBar(lambda: "dark", log=lambda m: None)
    bar.handle = ("win32", 1)
    bar.update(force=True)
    assert bar.how.startswith("failed")
