# SPDX-License-Identifier: GPL-3.0-or-later
"""3D viewport window: renders the model, handles orbit / pan / zoom / sculpt and draws overlays."""
import math
import time

import numpy as np
from imgui_bundle import imgui, icons_fontawesome_6 as fa

from nimcale.core import mesh as meshmod
from nimcale.core.orient import Orient
from nimcale.i18n import tr
from nimcale.ui import theme, widgets


def pick_plate(app, cam, mx, my):
    """Ray-march the height field. Returns plate uv of the hit or None."""
    res = app.result
    if res is None:
        return None
    p = app.params
    o, d = cam.ray(mx, my)
    sw, sh = res.size
    hmax = float(res.hf.max()) * p.depth + 1e-4
    zlo = -p.thickness
    if abs(d[2]) < 1e-9:
        return None
    t_top = (hmax - o[2]) / d[2]
    t_bot = (zlo - o[2]) / d[2]
    t0, t1 = min(t_top, t_bot), max(t_top, t_bot)
    t0 = max(t0, 0.0)
    if t1 <= t0:
        return None
    n = 512
    ts = np.linspace(t0, t1, n)
    P = o[None, :] + ts[:, None] * d[None, :]
    u = P[:, 0] / sw + 0.5
    v = P[:, 1] / sh + 0.5
    inside = (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)
    hz = np.full(n, -1e9)
    if inside.any():
        hz[inside] = meshmod.sample_nodes(res.hf, u[inside], v[inside]) * p.depth
        sd = np.full(n, -1.0)
        sd[inside] = meshmod.sample_nodes(res.sdf, u[inside], v[inside])
        hz[sd <= 0] = -1e9
    below = P[:, 2] <= hz
    idx = np.flatnonzero(below)
    if len(idx) == 0:
        return None
    k = idx[0]
    if k == 0:
        return float(u[0]), float(v[0])
    a, b = ts[k - 1], ts[k]
    for _ in range(12):
        m = 0.5 * (a + b)
        q = o + m * d
        uu, vv = q[0] / sw + 0.5, q[1] / sh + 0.5
        hh = meshmod.sample_nodes(res.hf, np.array([uu]), np.array([vv]))[0] * p.depth
        if q[2] <= hh:
            b = m
        else:
            a = m
    q = o + b * d
    return float(q[0] / sw + 0.5), float(q[1] / sh + 0.5)


def plate_to_source_px(app, u, v):
    hmw = app.hm.work
    h, w = hmw.shape
    o = Orient(app.params, w, h)
    su, sv = o.plate_to_src(u, v)
    r_px = app.sculptor.radius * max(o.crop_px)
    return su * w - 0.5, (1.0 - sv) * h - 0.5, r_px


class Viewport:
    def __init__(self, app):
        self.app = app
        self.dragging = None
        self.last_t = time.time()
        self.hover = False

    def view_preset(self, name):
        v = self.app.view
        presets = {"front": (0.0, 0.0), "iso": (-0.55, -0.62), "side": (-1.25, -0.25), "top": (0.0, -1.45),
                   "default": (math.radians(-18.0), math.radians(-24.0))}
        v.yaw, v.pitch = presets[name]
        v.pan = [0.0, 0.0]
        if name != "default":
            v.dist = 2.25

    def gui(self):
        app = self.app
        now = time.time()
        dt = min(0.1, now - self.last_t)
        self.last_t = now
        io = imgui.get_io()
        avail = imgui.get_content_region_avail()
        w, h = max(32, int(avail.x)), max(32, int(avail.y))
        fb = io.display_framebuffer_scale
        pw, ph = int(w * fb.x), int(h * fb.y)
        app.vp_size = (pw, ph)
        if app.renderer is None:
            imgui.text(tr("vp.no_gl"))
            return
        if app.view.turntable:
            app.turn_angle = (app.turn_angle + app.view.turntable_speed * dt) % 360.0
        else:
            app.turn_angle = 0.0
        p0 = imgui.get_cursor_screen_pos()
        r = app.renderer
        r.ensure_fbo(pw, ph)
        sc = app.scene(theme.now())
        sig = (app.params.key(), tuple(sorted((k, str(vv)) for k, vv in app.view.to_dict().items())),
               (pw, ph), app.pipeline.revision, app.ao_rev, sc["brush"], app.turn_angle,
               id(app.renderer.color_tex), app.topo_key,
               round(sc["time"], 2) if (app.cfg.anim_bg and app.view.bg_mode == 0) else 0)
        if sig != app.render_sig:
            cam = r.render(sc, extra_yaw=math.radians(app.turn_angle))
            app.vp_cam = cam
            app.render_sig = sig
            app.ctx.screen.use()
        cam = getattr(app, "vp_cam", None)
        imgui.image(imgui.ImTextureRef(r.color.glo), imgui.ImVec2(w, h), imgui.ImVec2(0, 1), imgui.ImVec2(1, 0))
        hovered_img = imgui.is_item_hovered()
        dl = imgui.get_window_draw_list()
        p1 = imgui.ImVec2(p0.x + w, p0.y + h)
        if app.cfg.neon:
            theme.glow_rect(dl, imgui.ImVec2(p0.x + 2, p0.y + 2), imgui.ImVec2(p1.x - 2, p1.y - 2), 6.0, 0.8)
        self.overlays(dl, p0, w, h, cam, fb)
        hovered = hovered_img and not imgui.is_any_item_hovered() and not imgui.is_any_item_active()
        self.hover = hovered
        mx, my = (io.mouse_pos.x - p0.x) * fb.x, (io.mouse_pos.y - p0.y) * fb.y
        self.handle_input(hovered, mx, my, dt, cam)

    # ------------------------------------------------------------------ input
    def handle_input(self, hovered, mx, my, dt, cam):
        app = self.app
        io = imgui.get_io()
        v = app.view
        sculpt = app.tool == "sculpt"
        if hovered and not self.dragging:
            for btn in (0, 1, 2):
                if imgui.is_mouse_clicked(btn):
                    if sculpt and btn == 0:
                        self.dragging = "sculpt"
                        self.begin_stroke(cam, mx, my)
                    elif btn == 0 or (sculpt and btn == 1):
                        self.dragging = "orbit"
                    else:
                        self.dragging = "pan"
                    self.drag_btn = btn
        if self.dragging and not imgui.is_mouse_down(self.drag_btn):
            if self.dragging == "sculpt":
                app.sculptor.end()
                app.after_stroke()
            self.dragging = None
        d = io.mouse_delta
        if self.dragging == "orbit":
            v.yaw += d.x * 0.008
            v.pitch = max(-math.pi / 2 + 0.01, min(math.pi / 2 - 0.01, v.pitch + d.y * 0.008))
        elif self.dragging == "pan":
            f = v.dist * 0.0012
            v.pan[0] += d.x * f
            v.pan[1] -= d.y * f
        if hovered and io.mouse_wheel != 0.0:
            if sculpt and (io.key_ctrl or io.key_alt):
                app.sculptor.radius = float(np.clip(app.sculptor.radius * (1.1 ** io.mouse_wheel), 0.003, 0.5))
            elif io.mouse_wheel > 0:
                v.dist = max(0.25, v.dist * (0.9 ** io.mouse_wheel))
            else:
                v.dist = min(25.0, v.dist * (1.1 ** -io.mouse_wheel))
        # brush preview + painting
        app.brush_uv = None
        if sculpt and cam is not None and (hovered or self.dragging == "sculpt"):
            uv = pick_plate(app, cam, mx, my)
            app.brush_uv = uv
            if self.dragging == "sculpt" and uv is not None:
                cx, cy, rpx = plate_to_source_px(app, uv[0], uv[1])
                app.sculptor.stroke_to(app.pipeline.cache.get("gA"), cx, cy, rpx, dt, invert=io.key_shift)

    def begin_stroke(self, cam, mx, my):
        app = self.app
        if cam is None:
            return
        uv = pick_plate(app, cam, mx, my)
        base = app.pipeline.cache.get("gA")
        if base is None:
            return
        if uv is None:
            cx = cy = 0.0
        else:
            cx, cy, _ = plate_to_source_px(app, uv[0], uv[1])
        app.sculptor.begin(base.shape, base, cx, cy)

    # ------------------------------------------------------------------ overlays
    def overlays(self, dl, p0, w, h, cam, fb):
        app = self.app
        pad = 10
        # view presets (top-left)
        imgui.set_cursor_screen_pos(imgui.ImVec2(p0.x + pad, p0.y + pad))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, imgui.ImVec2(6, 4))
        imgui.push_style_color(imgui.Col_.button, theme.v4((0.12, 0.05, 0.17), 0.72))
        for name, icon, key in (("front", fa.ICON_FA_CIRCLE_DOT, "vp.front"), ("iso", fa.ICON_FA_CUBE, "vp.iso"),
                                ("side", fa.ICON_FA_GRIP_LINES_VERTICAL, "vp.side"),
                                ("top", fa.ICON_FA_ARROW_DOWN, "vp.top")):
            if widgets.icon_button("vp_" + name, icon, tr(key)):
                self.view_preset(name)
            imgui.same_line()
        if widgets.icon_button("vp_reset", fa.ICON_FA_EXPAND, tr("vp.reset")):
            app.view.reset_camera()
        imgui.same_line()
        if widgets.icon_button("vp_turn", fa.ICON_FA_ROTATE, tr("vp.turntable"), active=app.view.turntable):
            app.view.turntable = not app.view.turntable
        imgui.same_line()
        if widgets.icon_button("vp_sculpt", fa.ICON_FA_PAINTBRUSH, tr("vp.sculpt"), active=app.tool == "sculpt"):
            app.toggle_sculpt()
        imgui.pop_style_color()
        imgui.pop_style_var()
        # info (top-right)
        st = app.stats
        if st:
            lines = ["%.1f x %.1f x %.1f mm" % (st["w"], st["h"], st["total"]),
                     tr("vp.triangles", n="{:,}".format(st["tris"]).replace(",", "."))]
            if app.tool == "sculpt":
                lines.append(tr("vp.sculpt_hint"))
            y = p0.y + pad
            for ln in lines:
                tw = imgui.calc_text_size(ln).x
                x = p0.x + w - tw - pad - 4
                dl.add_rect_filled(imgui.ImVec2(x - 6, y - 2), imgui.ImVec2(x + tw + 6, y + imgui.get_text_line_height() + 2),
                                   theme.col32((0.08, 0.03, 0.12), 0.62), 5.0)
                dl.add_text(imgui.ImVec2(x, y), theme.col32(theme.TEXT, 0.95), ln)
                y += imgui.get_text_line_height() + 6
        # dimension labels
        if app.view.dims and cam is not None and st.get("bbox"):
            (x0, y0, za), (x1, y1, zb) = st["bbox"]
            off = 0.04
            items = [((0.5 * (x0 + x1), y0 - off * 2.2, za), "%.1f mm" % st["w"]),
                     ((x1 + off * 2.6, 0.5 * (y0 + y1), za), "%.1f mm" % st["h"]),
                     ((x1 + off * 2.2, y1 + off, 0.5 * (za + zb)), "%.2f mm" % st["total"])]
            for pt, text in items:
                q = cam.project(pt)
                if q is None:
                    continue
                sx, sy = p0.x + q[0] / fb.x, p0.y + q[1] / fb.y
                tw = imgui.calc_text_size(text).x
                dl.add_rect_filled(imgui.ImVec2(sx - tw / 2 - 5, sy - 10), imgui.ImVec2(sx + tw / 2 + 5, sy + 10),
                                   theme.col32((0.25, 0.06, 0.30), 0.85), 4.0)
                dl.add_text(imgui.ImVec2(sx - tw / 2, sy - 8), theme.col32((1, 1, 1), 1.0), text)
        # hint (bottom-left)
        hint = tr("vp.hint_sculpt") if app.tool == "sculpt" else tr("vp.hint")
        y = p0.y + h - imgui.get_text_line_height() - pad
        dl.add_text(imgui.ImVec2(p0.x + pad + 1, y + 1), theme.col32((0, 0, 0), 0.6), hint)
        dl.add_text(imgui.ImVec2(p0.x + pad, y), theme.col32(theme.TEXT_DIM, 0.95), hint)
