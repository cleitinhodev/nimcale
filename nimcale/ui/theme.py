# SPDX-License-Identifier: GPL-3.0-or-later
"""Purple / pink "elf goddess" theme and animated neon helpers."""
import math
import time

from imgui_bundle import imgui

# palette (taken from the Nimcale icon)
VIOLET = (0.62, 0.30, 1.00)
PINK = (1.00, 0.33, 0.86)
LILAC = (0.95, 0.80, 1.00)
TEXT = (0.96, 0.93, 1.00)
TEXT_DIM = (0.68, 0.61, 0.78)
BG0 = (0.065, 0.035, 0.090)
BG1 = (0.095, 0.055, 0.130)
BG2 = (0.140, 0.080, 0.190)
FRAME = (0.170, 0.095, 0.235)
OK = (0.45, 0.95, 0.65)
WARN = (1.00, 0.80, 0.35)
ERR = (1.00, 0.42, 0.50)

_t0 = time.time()
state = {"neon": True, "speed": 1.0}


def v4(c, a=1.0):
    return imgui.ImVec4(c[0], c[1], c[2], a)


def col32(c, a=1.0):
    return imgui.get_color_u32(imgui.ImVec4(c[0], c[1], c[2], a))


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def now():
    return (time.time() - _t0) * state["speed"]


def neon_color(phase=0.0):
    """Animated violet <-> pink color (static violet-pink mix when effects are disabled)."""
    if not state["neon"]:
        return lerp(VIOLET, PINK, 0.45)
    t = 0.5 + 0.5 * math.sin(now() * 1.3 + phase)
    return lerp(VIOLET, PINK, t)


def apply(neon=True, speed=1.0, font_scale=1.0):
    state["neon"] = neon
    state["speed"] = speed
    st = imgui.get_style()
    st.window_rounding = 8.0
    st.child_rounding = 8.0
    st.frame_rounding = 6.0
    st.popup_rounding = 8.0
    st.scrollbar_rounding = 8.0
    st.grab_rounding = 6.0
    st.tab_rounding = 6.0
    st.window_border_size = 1.0
    st.frame_border_size = 0.0
    st.popup_border_size = 1.0
    st.window_padding = imgui.ImVec2(10, 10)
    st.frame_padding = imgui.ImVec2(8, 5)
    st.item_spacing = imgui.ImVec2(8, 6)
    st.item_inner_spacing = imgui.ImVec2(6, 5)
    st.indent_spacing = 16
    st.scrollbar_size = 12
    st.grab_min_size = 10
    st.window_title_align = imgui.ImVec2(0.02, 0.5)
    st.separator_text_border_size = 2.0
    C = imgui.Col_
    c = {
        C.text: v4(TEXT),
        C.text_disabled: v4(TEXT_DIM),
        C.window_bg: v4(BG0, 0.98),
        C.child_bg: v4(BG1, 0.60),
        C.popup_bg: v4(BG1, 0.98),
        C.border: v4((0.42, 0.22, 0.58), 0.65),
        C.border_shadow: v4((0, 0, 0), 0.0),
        C.frame_bg: v4(FRAME, 1.0),
        C.frame_bg_hovered: v4((0.26, 0.13, 0.36), 1.0),
        C.frame_bg_active: v4((0.34, 0.16, 0.46), 1.0),
        C.title_bg: v4(BG0, 1.0),
        C.title_bg_active: v4((0.17, 0.07, 0.24), 1.0),
        C.title_bg_collapsed: v4(BG0, 0.8),
        C.menu_bar_bg: v4((0.085, 0.045, 0.12), 1.0),
        C.scrollbar_bg: v4(BG0, 0.4),
        C.scrollbar_grab: v4((0.36, 0.18, 0.50), 1.0),
        C.scrollbar_grab_hovered: v4((0.50, 0.24, 0.70), 1.0),
        C.scrollbar_grab_active: v4(PINK, 1.0),
        C.check_mark: v4(PINK, 1.0),
        C.slider_grab: v4((0.60, 0.30, 0.84), 0.95),
        C.slider_grab_active: v4(PINK, 1.0),
        C.button: v4((0.30, 0.13, 0.42), 1.0),
        C.button_hovered: v4((0.48, 0.20, 0.66), 1.0),
        C.button_active: v4((0.80, 0.28, 0.75), 1.0),
        C.header: v4((0.36, 0.15, 0.50), 0.75),
        C.header_hovered: v4((0.52, 0.22, 0.70), 0.85),
        C.header_active: v4((0.70, 0.28, 0.80), 1.0),
        C.separator: v4((0.42, 0.22, 0.58), 0.7),
        C.separator_hovered: v4(VIOLET, 0.9),
        C.separator_active: v4(PINK, 1.0),
        C.resize_grip: v4(VIOLET, 0.25),
        C.resize_grip_hovered: v4(VIOLET, 0.65),
        C.resize_grip_active: v4(PINK, 0.95),
        C.tab: v4((0.16, 0.07, 0.22), 1.0),
        C.tab_hovered: v4((0.52, 0.22, 0.70), 1.0),
        C.tab_selected: v4((0.38, 0.15, 0.54), 1.0),
        C.tab_selected_overline: v4(PINK, 1.0),
        C.tab_dimmed: v4((0.10, 0.05, 0.14), 1.0),
        C.tab_dimmed_selected: v4((0.24, 0.10, 0.34), 1.0),
        C.docking_preview: v4(PINK, 0.45),
        C.docking_empty_bg: v4(BG0, 1.0),
        C.plot_lines: v4(PINK),
        C.plot_histogram: v4(VIOLET),
        C.table_header_bg: v4((0.20, 0.09, 0.28), 1.0),
        C.table_border_strong: v4((0.42, 0.22, 0.58), 0.8),
        C.table_border_light: v4((0.30, 0.16, 0.42), 0.6),
        C.table_row_bg: v4((0, 0, 0), 0.0),
        C.table_row_bg_alt: v4((1, 1, 1), 0.03),
        C.text_selected_bg: v4(PINK, 0.35),
        C.drag_drop_target: v4(PINK, 0.9),
        C.nav_cursor: v4(PINK, 1.0),
        C.modal_window_dim_bg: v4((0.03, 0.0, 0.05), 0.55),
        C.text_link: v4((1.0, 0.55, 0.92), 1.0),
    }
    for k, val in c.items():
        try:
            st.set_color_(k, val)
        except Exception:
            pass


# ---------------------------------------------------------------------------- neon drawing
def glow_rect(dl, p0, p1, rounding=8.0, intensity=1.0, phase=0.0, layers=6):
    """Soft neon frame around a rectangle."""
    c = neon_color(phase)
    if not state["neon"]:
        dl.add_rect(p0, p1, col32(c, 0.55 * intensity), rounding, 1.5)
        return
    pulse = 0.75 + 0.25 * math.sin(now() * 2.1 + phase)
    for i in range(layers, 0, -1):
        a = (0.10 / i) * intensity * pulse * 1.6
        e = i * 1.6
        dl.add_rect(imgui.ImVec2(p0.x - e, p0.y - e), imgui.ImVec2(p1.x + e, p1.y + e), col32(c, a),
                    rounding + e, 2.0)
    dl.add_rect(p0, p1, col32(lerp(c, (1, 1, 1), 0.25), 0.85 * intensity), rounding, 1.5)


def gradient_bar(dl, p0, p1, phase=0.0, alpha=1.0):
    """Horizontal violet -> pink bar; the gradient slides when animations are on."""
    t = now() * 0.6 + phase if state["neon"] else 0.0
    a = lerp(VIOLET, PINK, 0.5 + 0.5 * math.sin(t))
    b = lerp(PINK, VIOLET, 0.5 + 0.5 * math.sin(t))
    ca, cb = col32(a, alpha), col32(b, alpha)
    dl.add_rect_filled_multi_color(p0, p1, ca, cb, cb, ca)


def section_title(text, icon=""):
    """Separator with a gradient underline."""
    dl = imgui.get_window_draw_list()
    p = imgui.get_cursor_screen_pos()
    w = imgui.get_content_region_avail().x
    imgui.push_style_color(imgui.Col_.text, v4(LILAC))
    imgui.text((icon + "  " if icon else "") + text)
    imgui.pop_style_color()
    h = imgui.get_text_line_height()
    y = p.y + h + 3
    gradient_bar(dl, imgui.ImVec2(p.x, y), imgui.ImVec2(p.x + w, y + 2), alpha=0.9)
    imgui.dummy(imgui.ImVec2(1, 4))
