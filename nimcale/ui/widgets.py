# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable widgets with consistent look: label above, reset on right-click, tooltips."""
from imgui_bundle import imgui

from nimcale.ui import theme

SETTINGS = {"tooltips": True}


def tooltip(text):
    if text and SETTINGS["tooltips"] and imgui.is_item_hovered(imgui.HoveredFlags_.delay_normal):
        imgui.set_next_window_size_constraints(imgui.ImVec2(0, 0), imgui.ImVec2(380, 600))
        imgui.begin_tooltip()
        imgui.push_text_wrap_pos(360)
        imgui.text_unformatted(text)
        imgui.pop_text_wrap_pos()
        imgui.end_tooltip()


def label(text, dim=True):
    if dim:
        imgui.push_style_color(imgui.Col_.text, theme.v4(theme.TEXT_DIM))
    imgui.text_unformatted(text)
    if dim:
        imgui.pop_style_color()


def slider(uid, text, value, lo, hi, default, fmt="%.2f", scale=1.0, log=False, tip=None, integer=False):
    """Float/int slider; `scale` converts the stored value to the displayed unit."""
    label(text)
    imgui.set_next_item_width(-1)
    flags = imgui.SliderFlags_.always_clamp
    if log:
        flags |= imgui.SliderFlags_.logarithmic
    if integer:
        ch, nv = imgui.slider_int("##" + uid, int(value), int(lo), int(hi), fmt, flags)
    else:
        ch, nv = imgui.slider_float("##" + uid, float(value) * scale, lo * scale, hi * scale, fmt, flags)
        nv = nv / scale if scale else nv
    if imgui.is_item_clicked(imgui.MouseButton_.right):
        nv, ch = default, True
    tooltip(tip)
    return nv if ch else value


def checkbox(uid, text, value, tip=None):
    ch, nv = imgui.checkbox(text + "##" + uid, bool(value))
    tooltip(tip)
    return nv


def segmented(uid, options, current, tip=None, width=-1.0):
    """Row of toggle buttons; returns the selected index."""
    n = len(options)
    avail = imgui.get_content_region_avail().x if width < 0 else width
    sp = imgui.get_style().item_spacing.x * 0.5
    bw = (avail - sp * (n - 1)) / max(1, n)
    res = current
    for i, opt in enumerate(options):
        if i:
            imgui.same_line(0, sp)
        sel = (i == current)
        if sel:
            imgui.push_style_color(imgui.Col_.button, theme.v4((0.66, 0.26, 0.80), 1.0))
            imgui.push_style_color(imgui.Col_.button_hovered, theme.v4((0.78, 0.32, 0.86), 1.0))
        if imgui.button("%s##%s%d" % (opt, uid, i), imgui.ImVec2(bw, 0)):
            res = i
        if sel:
            imgui.pop_style_color(2)
        tooltip(tip)
    return res


def icon_button(uid, icon, tip=None, active=False, size=None, enabled=True):
    if active:
        imgui.push_style_color(imgui.Col_.button, theme.v4((0.66, 0.26, 0.80), 1.0))
    if not enabled:
        imgui.begin_disabled()
    clicked = imgui.button("%s##%s" % (icon, uid), size or imgui.ImVec2(0, 0))
    if not enabled:
        imgui.end_disabled()
    if active:
        imgui.pop_style_color()
    if tip and imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
        imgui.set_tooltip(tip)
    return clicked and enabled


def wide_button(text, uid=None, tip=None, height=0.0):
    c = imgui.button(text + ("##" + uid if uid else ""), imgui.ImVec2(-1, height))
    tooltip(tip)
    return c


def color_swatch(uid, c, size=22, selected=False):
    imgui.push_style_var(imgui.StyleVar_.frame_rounding, 5)
    imgui.push_style_var(imgui.StyleVar_.frame_border_size, 2.0 if selected else 0.0)
    imgui.push_style_color(imgui.Col_.border, theme.v4(theme.PINK))
    ch = imgui.color_button("##" + uid, imgui.ImVec4(c[0], c[1], c[2], 1.0),
                            imgui.ColorEditFlags_.no_tooltip | imgui.ColorEditFlags_.no_border,
                            imgui.ImVec2(size, size))
    imgui.pop_style_color()
    imgui.pop_style_var(2)
    return ch


def kv_table(uid, rows):
    """Two-column table of (name, value[, color]) rows."""
    if imgui.begin_table(uid, 2, imgui.TableFlags_.sizing_stretch_prop | imgui.TableFlags_.row_bg):
        imgui.table_setup_column("k", imgui.TableColumnFlags_.width_stretch, 1.2)
        imgui.table_setup_column("v", imgui.TableColumnFlags_.width_stretch, 1.0)
        for r in rows:
            imgui.table_next_row()
            imgui.table_next_column()
            label(r[0])
            imgui.table_next_column()
            if len(r) > 2 and r[2]:
                imgui.text_colored(theme.v4(r[2]), r[1])
            else:
                imgui.text_unformatted(r[1])
        imgui.end_table()
