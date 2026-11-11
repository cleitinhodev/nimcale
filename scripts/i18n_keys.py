#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""List every translation key used by the source code (static and generated) and check locale files.

usage: python scripts/i18n_keys.py [--check]
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PREFIXES = ("about", "act", "bg", "brush", "dlg", "drop", "err", "exp", "file", "fit", "fmt", "guide", "hd",
            "interp", "m", "mat", "menu", "mode", "msg", "p", "preset", "sc", "sculpt", "sec", "set", "shape",
            "stage", "status", "tab", "tip", "vp", "win", "srf", "beta", "proj", "axis", "sample", "cut", "fit")


def used_keys():
    from nimcale.core.params import SHAPES, MATERIALS
    from nimcale.tools.sculpt import BRUSHES
    from nimcale.ui.dialogs import EXPORT_FORMATS
    keys = set()
    pat = re.compile(r'"((?:%s)\.[a-z0-9_]+(?:\.[a-z0-9_]+)?)"' % "|".join(PREFIXES))
    for d, _, files in os.walk(os.path.join(ROOT, "nimcale")):
        for f in files:
            if f.endswith(".py"):
                src = open(os.path.join(d, f), encoding="utf-8").read()
                for k in pat.findall(src):
                    if not re.search(r"\.(png|json|npy|stl|txt|ico)$", k) and not k.endswith("_"):
                        keys.add(k)
    for f in EXPORT_FORMATS:
        keys.update({"fmt." + f, "fmt.%s.desc" % f})
    keys.update("shape." + s for s in SHAPES)
    from nimcale.core.cutout import SOURCES, BG_MODES
    keys.update("outline." + s for s in SOURCES)
    keys.update("bg." + b for b in BG_MODES)
    keys.update({"cut.detected", "p.shape"})
    from nimcale.core.surface import PROJECTIONS, AXES, SAMPLES
    keys.update("proj." + x for x in PROJECTIONS)
    keys.update("axis." + x for x in AXES)
    keys.update("sample." + x for x in SAMPLES)
    keys.update("srf.up_" + x for x in ("auto", "z", "y", "x"))
    keys.update("srf.rot_" + x for x in ("x", "y", "z"))
    keys.update("fit." + x for x in ("stretch", "width", "height"))
    keys.update("guide.%d" % i for i in range(1, 10))
    keys.update("mat." + m for m in MATERIALS)
    for b in BRUSHES:
        keys.update({"brush." + b, "brush.%s.tip" % b})
    for s in ("heightmap", "mesh", "simplify", "check", "texture", "write", "done", "frames"):
        keys.add("stage." + s)
    for k in ("coin", "medal", "plate", "outline", "tile"):
        keys.update({"preset." + k, "preset.%s.tip" % k})
    keys.update("guide.%d" % i for i in range(1, 8))
    keys.discard("preset.")
    return sorted(k for k in keys if not k.endswith("."))


def main():
    keys = used_keys()
    if "--check" not in sys.argv:
        print("\n".join(keys))
        return 0
    bad = 0
    loc = os.path.join(ROOT, "nimcale", "i18n", "locales")
    en = json.load(open(os.path.join(loc, "en.json"), encoding="utf-8"))
    for f in sorted(os.listdir(loc)):
        d = json.load(open(os.path.join(loc, f), encoding="utf-8"))
        miss = [k for k in keys if k not in d]
        extra = [k for k in d if k not in keys and not k.startswith("_")]
        fmt_bad = [k for k in d if k in en and set(re.findall(r"{(\w+)", d[k])) != set(re.findall(r"{(\w+)", en[k]))]
        print("%-10s %4d keys  missing %3d  extra %3d  format-mismatch %d" % (f, len(d), len(miss), len(extra),
                                                                           len(fmt_bad)))
        if miss:
            print("   missing:", " ".join(miss[:40]))
        if extra:
            print("   extra:", " ".join(extra[:40]))
        if fmt_bad:
            print("   fmt:", " ".join(fmt_bad))
        bad += len(miss) + len(fmt_bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
