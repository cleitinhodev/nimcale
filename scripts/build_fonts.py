#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the compact UI fonts shipped in nimcale/assets/fonts.

* NimcaleSans-Regular/Bold.ttf: Noto Sans (variable) instanced at 400/700, subset to Latin, Latin
  Extended, Greek, Cyrillic and common symbols.
* NimcaleCJK-SC/JP/KR.otf: Noto Sans CJK subsets with exactly the characters used by the
  zh-CN / ja / ko locale files (+ kana and CJK punctuation).
* fa-solid-900.otf: Font Awesome 6 Free Solid (copied from imgui-bundle).

usage: python scripts/build_fonts.py [--noto-sans PATH] [--noto-cjk PATH.ttc]
"""
import argparse
import glob
import json
import os
import shutil
import sys

from fontTools import subset
from fontTools.ttLib import TTFont, TTCollection
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "nimcale", "assets", "fonts")
LOC = os.path.join(ROOT, "nimcale", "i18n", "locales")

LATIN_RANGES = [(0x20, 0x7E), (0xA0, 0x24F), (0x2B0, 0x2FF), (0x300, 0x36F), (0x370, 0x3FF), (0x400, 0x52F),
                (0x1E00, 0x1EFF), (0x2000, 0x206F), (0x20A0, 0x20BF), (0x2100, 0x214F), (0x2190, 0x21FF),
                (0x2200, 0x22FF), (0x25A0, 0x25FF), (0x2122, 0x2122)]


def find(pattern_list):
    for p in pattern_list:
        hits = glob.glob(p, recursive=True)
        if hits:
            return hits[0]
    return None


def subset_font(font, codepoints, out, flavor=None):
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.glyph_names = False
    opts.hinting = False
    opts.desubroutinize = True
    s = subset.Subsetter(opts)
    s.populate(unicodes=codepoints)
    s.subset(font)
    font.save(out)
    print("  %-28s %7.1f KB" % (os.path.basename(out), os.path.getsize(out) / 1024))


def locale_chars(code):
    p = os.path.join(LOC, code + ".json")
    if not os.path.exists(p):
        return set()
    d = json.load(open(p, encoding="utf-8"))
    s = set()
    for v in d.values():
        s.update(ord(c) for c in v)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--noto-sans", default=find([
        "/usr/share/fonts/**/NotoSans-VariableFont_wdth,wght.ttf", "/usr/share/fonts/**/NotoSans[wdth,wght].ttf"]))
    ap.add_argument("--noto-cjk", default=find(["/usr/share/fonts/**/NotoSansCJK-Regular.ttc"]))
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    latin = set()
    for lo, hi in LATIN_RANGES:
        latin.update(range(lo, hi + 1))
    for code in ("en", "pt-BR", "es", "fr", "de", "it", "ru", "pl", "tr"):
        latin |= locale_chars(code)
    print("Noto Sans:", a.noto_sans)
    for wght, name in ((400, "Regular"), (700, "Bold")):
        vf = TTFont(a.noto_sans)
        f = instancer.instantiateVariableFont(vf, {"wght": wght, "wdth": 100})
        subset_font(f, latin, os.path.join(OUT, "NimcaleSans-%s.ttf" % name))
    # CJK: TTC indices of NotoSansCJK-Regular.ttc: 0 JP, 1 KR, 2 SC, 3 TC, 4 HK
    print("Noto Sans CJK:", a.noto_cjk)
    common = set(range(0x3000, 0x3040)) | set(range(0xFF00, 0xFFF0))
    kana = set(range(0x3040, 0x3100))
    for code, idx, tag in (("ja", 0, "JP"), ("ko", 1, "KR"), ("zh-CN", 2, "SC")):
        chars = {c for c in locale_chars(code) if c > 0x2E7F} | common
        if code == "ja":
            chars |= kana
        coll = TTCollection(a.noto_cjk)
        f = coll.fonts[idx]
        subset_font(f, chars, os.path.join(OUT, "NimcaleCJK-%s.otf" % tag))
    import imgui_bundle
    fa = os.path.join(os.path.dirname(imgui_bundle.__file__), "assets", "fonts", "Font_Awesome_6_Free-Solid-900.otf")
    shutil.copy(fa, os.path.join(OUT, "fa-solid-900.otf"))
    print("  fa-solid-900.otf copied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
