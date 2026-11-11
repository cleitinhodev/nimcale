# SPDX-License-Identifier: GPL-3.0-or-later
"""Font loading: Noto Sans (Latin/Greek/Cyrillic) + CJK subsets + Font Awesome icons, merged."""
import os

from imgui_bundle import hello_imgui

from nimcale.paths import asset

FONTS = {"regular": None, "bold": None, "title": None}
MERGE = ["fonts/NimcaleCJK-SC.otf", "fonts/NimcaleCJK-JP.otf", "fonts/NimcaleCJK-KR.otf"]
ICONS = "fonts/fa-solid-900.otf"


def _merge_order():
    """Han characters exist in all three CJK fonts with different regional shapes; merge the font of
    the current language first so it wins (ImGui keeps the first glyph found)."""
    try:
        from nimcale import i18n
        cur = i18n.current()
    except Exception:
        cur = ""
    first = {"ja": "fonts/NimcaleCJK-JP.otf", "ko": "fonts/NimcaleCJK-KR.otf"}.get(cur)
    if not first:
        return list(MERGE)
    return [first] + [m for m in MERGE if m != first]


def _merge(size):
    for f in _merge_order() + [ICONS]:
        if not os.path.isfile(asset(f)):
            continue
        p = hello_imgui.FontLoadingParams()
        p.merge_to_last_font = True
        if f == ICONS:
            try:
                p.font_config.glyph_offset.y = size * 0.06
                p.font_config.glyph_min_advance_x = size * 1.15
            except Exception:
                pass
        hello_imgui.load_font(f, size * (0.92 if f == ICONS else 1.0), p)


def load(size=16.0):
    FONTS["regular"] = hello_imgui.load_font("fonts/NimcaleSans-Regular.ttf", size)
    _merge(size)
    FONTS["bold"] = hello_imgui.load_font("fonts/NimcaleSans-Bold.ttf", size)
    _merge(size)
    FONTS["title"] = FONTS["bold"]
    return FONTS
