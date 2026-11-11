# SPDX-License-Identifier: GPL-3.0-or-later
"""Start-up path tests (no window needed): renderer choice, GLFW lookup, runner parameters."""
import os

import pytest

from nimcale import launcher
from nimcale.config import AppConfig


def test_glfw_library_found():
    p = launcher.glfw_library()
    assert p and os.path.isfile(p)
    assert "imgui_bundle" in p          # the same GLFW the window uses


@pytest.mark.parametrize("res,software", [("ok", False), ("fail", True), ("crash", True), ("error", False)])
def test_choose_renderer_probe(monkeypatch, res, software):
    monkeypatch.setenv("NIMCALE_FORCE_PROBE", "1")
    monkeypatch.setattr(launcher, "run_probe", lambda sw=False, timeout=25: (res, "test"))
    cfg = AppConfig.load()
    cfg.renderer, cfg.gl_status = "auto", ""
    a = launcher.parse_args([])
    assert launcher.choose_renderer(a, cfg) is software


def test_forced_renderers():
    cfg = AppConfig.load()
    cfg.renderer = "auto"
    assert launcher.choose_renderer(launcher.parse_args(["--software"]), cfg) is True
    assert launcher.choose_renderer(launcher.parse_args(["--gpu"]), cfg) is False


def test_message_box_never_blocks_in_ci(monkeypatch):
    monkeypatch.setenv("NIMCALE_NO_DIALOGS", "1")
    assert launcher.message_box("t", "x", yes_no=True) is False


@pytest.mark.parametrize("argv", [[], ["--shot", "x.png"], ["--reset-layout"], ["--quit-after", "5"]])
def test_runner_params_build(argv):
    """Builds the real hello_imgui RunnerParams for the normal (double-click) path and the test paths."""
    from nimcale.runner import Runner
    a = launcher.parse_args(argv)
    r = Runner(a, AppConfig.load())
    rp = r.params()
    assert len(rp.docking_params.dockable_windows) == 3
    assert rp.docking_params.layout_condition is not None


def test_compat_enum_value():
    from imgui_bundle import hello_imgui
    from nimcale.compat import enum_value
    c = hello_imgui.DockingLayoutCondition
    assert enum_value(c, "no_such_name", "application_start") == c.application_start
    with pytest.raises(AttributeError):
        enum_value(c, "nope1", "nope2")
