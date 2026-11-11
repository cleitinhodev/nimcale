# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent application settings (config.json in %APPDATA%\\Nimcale)."""
import json
import os
from dataclasses import dataclass, field, fields, asdict

from nimcale.paths import config_dir


@dataclass
class AppConfig:
    language: str = "auto"
    neon: bool = True              # animated neon glow borders
    anim_bg: bool = True           # animated gradient background in the viewport
    anim_speed: float = 1.0
    font_size: float = 16.0
    renderer: str = "auto"         # auto | gpu | software
    msaa: bool = True
    show_fps: bool = False
    gl_status: str = "unknown"     # result of the last OpenGL start-up
    recent: list = field(default_factory=list)
    last_dir: str = ""
    export_dir: str = ""
    hd_nodes: int = 2048
    export_fmt: str = "stl"
    tooltips: bool = True
    confirm_exit: bool = False
    first_run: bool = True

    @staticmethod
    def path():
        return os.path.join(config_dir(), "config.json")

    @classmethod
    def load(cls):
        c = cls()
        try:
            with open(cls.path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            for fl in fields(c):
                if fl.name in d and isinstance(d[fl.name], type(getattr(c, fl.name))):
                    setattr(c, fl.name, d[fl.name])
                elif fl.name in d and isinstance(getattr(c, fl.name), float) and isinstance(d[fl.name], int):
                    setattr(c, fl.name, float(d[fl.name]))
        except (OSError, ValueError, TypeError):
            pass
        if c.renderer not in ("auto", "gpu", "software"):
            c.renderer = "auto"
        c.font_size = min(28.0, max(11.0, c.font_size))
        return c

    def save(self):
        try:
            tmp = self.path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path())
        except OSError:
            pass

    def add_recent(self, path):
        path = os.path.abspath(path)
        self.recent = [p for p in self.recent if p != path]
        self.recent.insert(0, path)
        del self.recent[10:]
