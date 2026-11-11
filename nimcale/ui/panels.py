# SPDX-License-Identifier: GPL-3.0-or-later
"""Properties panel (tabs) and inspector."""
import math
import os

import moderngl
import numpy as np
from imgui_bundle import imgui, icons_fontawesome_6 as fa
from PIL import Image

from nimcale.core.params import MATERIALS, MATERIAL_DEFS, BG_PRESETS, SHAPES, ModelParams
from nimcale.core import images
from nimcale.i18n import tr
from nimcale.tools.sculpt import BRUSHES
from nimcale.ui import theme, widgets as W

D = ModelParams()


def ui_texture(app, key, pil_img, size=256):
    t = app.ui_textures.get(key)
    if t is None:
        im = pil_img.copy()
        im.thumbnail((size, size), Image.LANCZOS)
        im = im.convert("RGBA")
        t = app.ctx.texture(im.size, 4, im.tobytes())
        t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        app.ui_textures[key] = t
    return t


def header(text, icon, default_open=True):
    imgui.push_style_color(imgui.Col_.text, theme.v4(theme.LILAC))
    flags = imgui.TreeNodeFlags_.default_open if default_open else 0
    o = imgui.collapsing_header("%s  %s###h_%s" % (icon, text, icon), flags)
    imgui.pop_style_color()
    return o


class Panels:
    def __init__(self, app):
        self.app = app

    # ================================================================== properties
    def properties(self):
        app = self.app
        req = getattr(app, "props_tab_req", None)
        app.props_tab_req = None
        if imgui.begin_tab_bar("##props_tabs", imgui.TabBarFlags_.fitting_policy_shrink | imgui.TabBarFlags_.no_tooltip):
            for key, icon, fn in (("tab.model", fa.ICON_FA_MOUNTAIN, self.tab_model),
                                  ("tab.shape", fa.ICON_FA_COINS, self.tab_shape),
                                  ("tab.texture", fa.ICON_FA_IMAGE, self.tab_texture),
                                  ("tab.sculpt", fa.ICON_FA_PAINTBRUSH, self.tab_sculpt),
                                  ("tab.scene", fa.ICON_FA_LIGHTBULB, self.tab_scene)):
                flags = imgui.TabItemFlags_.set_selected if req == key.split(".")[1] else 0
                cur = getattr(self, "cur_tab", "tab.model")
                text = "%s  %s" % (icon, tr(key)) if cur == key else " %s " % icon
                sel, _ = imgui.begin_tab_item("%s###%s" % (text, key), None, flags)
                if cur != key:
                    W.tooltip(tr(key))
                if sel:
                    self.cur_tab = key
                if sel:
                    imgui.begin_child("##scroll_" + key, imgui.ImVec2(0, 0), 0, imgui.WindowFlags_.none)
                    fn()
                    imgui.dummy(imgui.ImVec2(1, 8))
                    imgui.end_child()
                    imgui.end_tab_item()
            imgui.end_tab_bar()

    # ------------------------------------------------------------------ model
    def tab_model(self):
        app, p = self.app, self.app.params
        mm = p.size_mm
        if header(tr("sec.files"), fa.ICON_FA_FOLDER_OPEN):
            self.file_cards()
        if header(tr("sec.size"), fa.ICON_FA_RULER_COMBINED):
            p.size_mm = W.slider("size_mm", tr("p.size_mm"), p.size_mm, 5.0, 500.0, 40.0, "%.1f mm", log=True,
                                 tip=tr("tip.size_mm"))
        if header(tr("sec.relief"), fa.ICON_FA_MOUNTAIN):
            p.depth = W.slider("depth", tr("p.depth"), p.depth, 0.0, 0.35, D.depth, "%.2f mm", scale=mm,
                               tip=tr("tip.depth"))
            p.thickness = W.slider("thick", tr("p.thickness"), p.thickness, 0.002, 0.35, D.thickness, "%.2f mm",
                                   scale=mm, tip=tr("tip.thickness"))
            p.blur = W.slider("blur", tr("p.blur"), p.blur, 0.0, 20.0, 1.0, "%.1f px", tip=tr("tip.blur"))
            p.detail = W.slider("detail", tr("p.detail"), p.detail, 0.0, 4.0, 0.0, "%.2f", tip=tr("tip.detail"))
            if p.detail > 0:
                p.detail_radius = W.slider("detail_r", tr("p.detail_radius"), p.detail_radius, 1.0, 40.0, 6.0,
                                           "%.1f px")
            p.invert = W.checkbox("invert", tr("p.invert"), p.invert, tip=tr("tip.invert"))
            p.mesh_res = W.slider("res", tr("p.mesh_res"), p.mesh_res, 64, 1500, 600, "%d", integer=True,
                                  tip=tr("tip.mesh_res"))
        if header(tr("sec.levels"), fa.ICON_FA_SLIDERS, default_open=False):
            p.brightness = W.slider("bright", tr("p.brightness"), p.brightness, -0.5, 0.5, 0.0, "%+.2f")
            p.contrast = W.slider("contrast", tr("p.contrast"), p.contrast, 0.2, 4.0, 1.0, "%.2f", log=True)
            p.gamma = W.slider("gamma", tr("p.gamma"), p.gamma, 0.25, 4.0, 1.0, "%.2f", log=True, tip=tr("tip.gamma"))
            p.level_lo = W.slider("lvl_lo", tr("p.level_lo"), p.level_lo, 0.0, 0.95, 0.0, "%.2f", tip=tr("tip.levels"))
            p.level_hi = W.slider("lvl_hi", tr("p.level_hi"), p.level_hi, 0.05, 1.0, 1.0, "%.2f", tip=tr("tip.levels"))
            if p.level_hi <= p.level_lo + 0.02:
                p.level_hi = min(1.0, p.level_lo + 0.02)
            p.threshold = W.slider("thr", tr("p.threshold"), p.threshold, 0.0, 0.95, D.threshold, "%.2f",
                                   tip=tr("tip.threshold"))
        if header(tr("sec.noise"), fa.ICON_FA_WAND_MAGIC_SPARKLES, default_open=False):
            p.noise_amp = W.slider("noise_amp", tr("p.noise_amp"), p.noise_amp, 0.0, 0.2, 0.0, "%.3f",
                                   tip=tr("tip.noise"))
            p.noise_scale = W.slider("noise_scale", tr("p.noise_scale"), p.noise_scale, 2.0, 400.0, 60.0, "%.0f",
                                     log=True)
            p.noise_seed = W.slider("noise_seed", tr("p.noise_seed"), p.noise_seed, 0, 999, 7, "%d", integer=True)

    def file_cards(self):
        app = self.app
        avail = imgui.get_content_region_avail().x
        sz = (avail - 10) / 2.0
        for i, (key, title, obj) in enumerate((("thumb_tex", tr("file.texture"), app.tex),
                                               ("thumb_hm", tr("file.heightmap"), app.hm))):
            if i:
                imgui.same_line()
            imgui.begin_group()
            if obj is not None:
                if key == "thumb_tex":
                    pil = obj.img
                else:
                    pil = Image.fromarray((np.clip(obj.work, 0, 1) * 255).astype(np.uint8), "L")
                t = ui_texture(app, key, pil)
                asp = t.size[1] / float(t.size[0])
                ih = min(sz, sz * asp)
                iw = ih / asp
                if imgui.image_button("##" + key, imgui.ImTextureRef(t.glo), imgui.ImVec2(iw, ih)):
                    app.pending.append("imp_tex" if key == "thumb_tex" else "imp_hm")
                W.tooltip(tr("file.click_to_replace"))
                imgui.text_colored(theme.v4(theme.LILAC), title)
                name = os.path.basename(obj.path or "-")
                if len(name) > 22:
                    name = name[:10] + "…" + name[-10:]
                W.label(name)
                W.label("%d x %d px" % tuple(obj.orig_size))
            imgui.end_group()
        if W.wide_button("%s  %s" % (fa.ICON_FA_FILE_IMPORT, tr("act.import_both")), "imp_both"):
            app.pending.append("imp_both")
        W.label(tr("file.drop_hint"))

    # ------------------------------------------------------------------ shape
    def tab_shape(self):
        app, p = self.app, self.app.params
        mm = p.size_mm
        theme.section_title(tr("sec.presets"), fa.ICON_FA_STAR)
        cols = [("preset.coin", fa.ICON_FA_COINS), ("preset.medal", fa.ICON_FA_MEDAL),
                ("preset.plate", fa.ICON_FA_SQUARE), ("preset.outline", fa.ICON_FA_DRAW_POLYGON),
                ("preset.tile", fa.ICON_FA_TABLE_CELLS_LARGE)]
        avail = imgui.get_content_region_avail().x
        bw = (avail - 4 * 4) / 5.0
        for i, (k, ic) in enumerate(cols):
            if i:
                imgui.same_line(0, 4)
            if imgui.button("%s##%s" % (ic, k), imgui.ImVec2(bw, 34)):
                app.pending.append(k)
            W.tooltip(tr(k) + "\n" + tr(k + ".tip"))
        imgui.dummy(imgui.ImVec2(1, 2))
        if header(tr("sec.outline"), fa.ICON_FA_DRAW_POLYGON):
            mode = W.segmented("cut", [tr("shape.plate"), tr("shape.cutout")], 1 if p.cutout else 0,
                               tip=tr("tip.cutout"))
            p.cutout = bool(mode)
            if p.cutout:
                names = [tr("shape." + s) for s in SHAPES]
                W.label(tr("p.shape"))
                imgui.set_next_item_width(-1)
                ch, idx = imgui.combo("##shape", SHAPES.index(p.shape), names)
                if ch:
                    p.shape = SHAPES[idx]
                    if p.shape != "auto":
                        app.refit_shape()
                if p.shape == "auto":
                    p.threshold = W.slider("thr2", tr("p.threshold"), p.threshold, 0.0, 0.95, D.threshold, "%.2f",
                                           tip=tr("tip.threshold"))
                else:
                    if W.wide_button("%s  %s" % (fa.ICON_FA_CROSSHAIRS, tr("act.fit_shape")), "fit_shape",
                                     tip=tr("tip.fit_shape")):
                        app.refit_shape()
                    if p.shape in ("circle", "hexagon", "octagon"):
                        r = W.slider("rx", tr("p.radius"), p.shape_rx, 0.02, 0.8, 0.47, "%.2f mm", scale=mm)
                        p.shape_rx = p.shape_ry = r
                    else:
                        p.shape_rx = W.slider("rx", tr("p.half_w"), p.shape_rx, 0.02, 0.8, 0.47, "%.2f mm", scale=mm)
                        p.shape_ry = W.slider("ry", tr("p.half_h"), p.shape_ry, 0.02, 0.8, 0.47, "%.2f mm", scale=mm)
                    if p.shape == "rounded":
                        p.shape_round = W.slider("round", tr("p.corner"), p.shape_round, 0.0, 1.0, 0.25, "%.2f")
                    p.shape_cx = W.slider("cx", tr("p.center_x"), p.shape_cx, -0.5, 0.5, 0.0, "%+.2f mm", scale=mm)
                    p.shape_cy = W.slider("cy", tr("p.center_y"), p.shape_cy, -0.5, 0.5, 0.0, "%+.2f mm", scale=mm)
                    if p.shape != "circle":
                        p.shape_rot = W.slider("srot", tr("p.shape_rot"), p.shape_rot, -180.0, 180.0, 0.0, "%+.1f°")
            p.smooth_edge = W.checkbox("smooth", tr("p.smooth_edge"), p.smooth_edge, tip=tr("tip.smooth_edge"))
        if header(tr("sec.edge"), fa.ICON_FA_RING):
            p.rim_width = W.slider("rim_w", tr("p.rim_width"), p.rim_width, 0.0, 0.15, 0.0, "%.2f mm", scale=mm,
                                   tip=tr("tip.rim"))
            p.rim_height = W.slider("rim_h", tr("p.rim_height"), p.rim_height, -1.0, 1.5, 0.0, "%.0f %%", scale=100.0,
                                    tip=tr("tip.rim_h"))
            p.bevel = W.slider("bevel", tr("p.bevel"), p.bevel, 0.0, 0.15, 0.0, "%.2f mm", scale=mm,
                               tip=tr("tip.bevel"))

    # ------------------------------------------------------------------ texture
    def tab_texture(self):
        app, p, v = self.app, self.app.params, self.app.view
        if header(tr("sec.view_mode"), fa.ICON_FA_EYE):
            v.mode = W.segmented("mode", [tr("mode.texture"), tr("mode.height"), tr("mode.mix")], v.mode)
            if v.mode == 2:
                v.mix = W.slider("mix", tr("p.mix"), v.mix, 0.0, 1.0, 0.5, "%.2f", tip=tr("tip.mix"))
        if header(tr("sec.align"), fa.ICON_FA_UP_DOWN_LEFT_RIGHT):
            W.label(tr("p.fit"))
            p.fit = W.segmented("fit", [tr("fit.stretch"), tr("fit.fill"), tr("fit.contain")], p.fit)
            su = math.sqrt(p.sx * p.sy)
            ra = p.sx / p.sy
            nsu = W.slider("su", tr("p.tex_scale"), su, 0.1, 5.0, 1.0, "%.3f", log=True)
            nra = W.slider("ra", tr("p.tex_ratio"), ra, 0.4, 2.5, 1.0, "%.3f", log=True)
            if nsu != su or nra != ra:
                p.sx = nsu * math.sqrt(nra)
                p.sy = nsu / math.sqrt(nra)
            p.ox = W.slider("ox", tr("p.tex_x"), p.ox, -1.0, 1.0, 0.0, "%+.4f")
            p.oy = W.slider("oy", tr("p.tex_y"), p.oy, -1.0, 1.0, 0.0, "%+.4f")
            p.rot = W.slider("trot", tr("p.tex_rot"), p.rot, -180.0, 180.0, 0.0, "%+.2f°")
            avail = imgui.get_content_region_avail().x
            bw = (avail - 8) / 2
            if imgui.button("%s %s##al0" % (fa.ICON_FA_ARROWS_ROTATE, tr("act.zero")), imgui.ImVec2(bw, 0)):
                p.reset_align()
            imgui.same_line()
            if imgui.button("%s %s##al1" % (fa.ICON_FA_WAND_MAGIC_SPARKLES, tr("act.auto_align")), imgui.ImVec2(bw, 0)):
                app.pending.append("auto_align")
            W.tooltip(tr("tip.auto_align"))
            if imgui.button("%s %s##al2" % (fa.ICON_FA_FLOPPY_DISK, tr("act.save_align")), imgui.ImVec2(bw, 0)):
                app.pending.append("save_align")
            imgui.same_line()
            if imgui.button("%s %s##al3" % (fa.ICON_FA_FOLDER_OPEN, tr("act.load_align")), imgui.ImVec2(bw, 0)):
                app.pending.append("load_align")
            W.label(tr("tip.align_keys"))
        if header(tr("sec.transform"), fa.ICON_FA_CROP_SIMPLE, default_open=False):
            avail = imgui.get_content_region_avail().x
            bw = (avail - 3 * 6) / 4
            for i, (act, ic, k) in enumerate((("flip_x", fa.ICON_FA_LEFT_RIGHT, "act.flip_x"),
                                              ("flip_y", fa.ICON_FA_UP_DOWN, "act.flip_y"),
                                              ("rot_l", fa.ICON_FA_ROTATE_LEFT, "act.rot_l"),
                                              ("rot_r", fa.ICON_FA_ROTATE_RIGHT, "act.rot_r"))):
                if i:
                    imgui.same_line(0, 6)
                if imgui.button("%s##%s" % (ic, act), imgui.ImVec2(bw, 30)):
                    app.pending.append(act)
                W.tooltip(tr(k))
            W.label(tr("p.crop"))
            p.crop_l = W.slider("cl", tr("p.crop_l"), p.crop_l, 0.0, 0.45, 0.0, "%.0f %%", scale=100.0)
            p.crop_r = W.slider("cr", tr("p.crop_r"), p.crop_r, 0.0, 0.45, 0.0, "%.0f %%", scale=100.0)
            p.crop_t = W.slider("ct", tr("p.crop_t"), p.crop_t, 0.0, 0.45, 0.0, "%.0f %%", scale=100.0)
            p.crop_b = W.slider("cb", tr("p.crop_b"), p.crop_b, 0.0, 0.45, 0.0, "%.0f %%", scale=100.0)

    # ------------------------------------------------------------------ sculpt
    def tab_sculpt(self):
        app = self.app
        sc = app.sculptor
        on = app.tool == "sculpt"
        if on:
            imgui.push_style_color(imgui.Col_.button, theme.v4((0.70, 0.25, 0.75), 1.0))
        if W.wide_button("%s  %s" % (fa.ICON_FA_PAINTBRUSH, tr("sculpt.on") if on else tr("sculpt.off")),
                         "sculpt_toggle", height=34):
            app.tool = "orbit" if on else "sculpt"
        if on:
            imgui.pop_style_color()
        theme.section_title(tr("sculpt.brush"), fa.ICON_FA_BRUSH)
        icons = {"raise": fa.ICON_FA_ARROW_UP, "lower": fa.ICON_FA_ARROW_DOWN, "smooth": fa.ICON_FA_WATER,
                 "flatten": fa.ICON_FA_GRIP_LINES, "erase": fa.ICON_FA_ERASER}
        avail = imgui.get_content_region_avail().x
        bw = (avail - 4 * 4) / 5.0
        for i, b in enumerate(BRUSHES):
            if i:
                imgui.same_line(0, 4)
            sel = sc.brush == b
            if sel:
                imgui.push_style_color(imgui.Col_.button, theme.v4((0.70, 0.25, 0.75), 1.0))
            if imgui.button("%s##br_%s" % (icons[b], b), imgui.ImVec2(bw, 34)):
                sc.brush = b
                app.tool = "sculpt"
            if sel:
                imgui.pop_style_color()
            W.tooltip(tr("brush." + b) + "\n" + tr("brush.%s.tip" % b))
        imgui.text_colored(theme.v4(theme.LILAC), tr("brush." + sc.brush))
        mm = app.params.size_mm
        sc.radius = W.slider("br_r", tr("sculpt.radius"), sc.radius, 0.003, 0.5, 0.05, "%.2f mm", scale=mm, log=True,
                             tip=tr("tip.brush_radius"))
        sc.strength = W.slider("br_s", tr("sculpt.strength"), sc.strength, 0.02, 2.0, 0.5, "%.2f", log=True)
        imgui.dummy(imgui.ImVec2(1, 4))
        if W.wide_button("%s  %s" % (fa.ICON_FA_TRASH_CAN, tr("sculpt.clear")), "sculpt_clear"):
            app.pending.append("sculpt_clear")
        imgui.dummy(imgui.ImVec2(1, 4))
        imgui.push_text_wrap_pos(0)
        W.label(tr("sculpt.help"))
        imgui.pop_text_wrap_pos()

    # ------------------------------------------------------------------ scene
    def tab_scene(self):
        app, v = self.app, self.app.view
        if header(tr("sec.material"), fa.ICON_FA_GEM):
            avail = imgui.get_content_region_avail().x
            n = len(MATERIALS)
            per = 4
            bw = (avail - (per - 1) * 6) / per
            for i, m in enumerate(MATERIALS):
                if i % per:
                    imgui.same_line(0, 6)
                tint = MATERIAL_DEFS[m][0]
                sel = v.material == m
                imgui.push_style_color(imgui.Col_.button, theme.v4(tuple(c * 0.55 for c in tint), 1.0))
                imgui.push_style_color(imgui.Col_.button_hovered, theme.v4(tuple(c * 0.75 for c in tint), 1.0))
                imgui.push_style_var(imgui.StyleVar_.frame_border_size, 2.0 if sel else 0.0)
                imgui.push_style_color(imgui.Col_.border, theme.v4(theme.PINK))
                if imgui.button("%s##mat_%s" % (tr("mat." + m), m), imgui.ImVec2(bw, 28)):
                    v.material = m
                imgui.pop_style_color(3)
                imgui.pop_style_var()
        if header(tr("sec.light"), fa.ICON_FA_SUN):
            v.lit = W.checkbox("lit", tr("p.lit"), v.lit)
            v.light_int = W.slider("lint", tr("p.light_int"), v.light_int, 0.0, 2.5, 1.1, "%.2f")
            v.ambient = W.slider("amb", tr("p.ambient"), v.ambient, 0.0, 1.0, 0.30, "%.2f")
            v.spec = W.slider("spec", tr("p.spec"), v.spec, 0.0, 3.0, 1.0, "%.2f")
            v.ao = W.slider("ao", tr("p.ao"), v.ao, 0.0, 1.0, 0.6, "%.2f", tip=tr("tip.ao"))
            v.light_phi = W.slider("phi", tr("p.light_phi"), v.light_phi % 360.0, 0.0, 360.0, 125.0, "%.0f°")
            v.light_theta = W.slider("theta", tr("p.light_theta"), v.light_theta, 3.0, 89.0, 48.0, "%.0f°")
        if header(tr("sec.background"), fa.ICON_FA_PALETTE):
            v.bg_mode = W.segmented("bgm", [tr("bg.gradient"), tr("bg.solid")], v.bg_mode)
            for i, (c0, c1) in enumerate(BG_PRESETS):
                if i:
                    imgui.same_line(0, 5)
                if W.color_swatch("bgp%d" % i, c1 if v.bg_mode == 0 else c0, 24,
                                  selected=list(c0) == list(v.bg)):
                    v.bg = list(c0)
                    v.bg2 = list(c1)
            ch, c = imgui.color_edit3(tr("bg.color1") + "##bg1", list(v.bg), imgui.ColorEditFlags_.no_inputs)
            if ch:
                v.bg = list(c)
            if v.bg_mode == 0:
                imgui.same_line()
                ch, c = imgui.color_edit3(tr("bg.color2") + "##bg2", list(v.bg2), imgui.ColorEditFlags_.no_inputs)
                if ch:
                    v.bg2 = list(c)
        if header(tr("sec.display"), fa.ICON_FA_DISPLAY):
            v.wire = W.checkbox("wire", tr("p.wire"), v.wire)
            v.axes = W.checkbox("axes", tr("p.axes"), v.axes)
            v.grid = W.checkbox("grid", tr("p.grid"), v.grid, tip=tr("tip.grid"))
            v.dims = W.checkbox("dims", tr("p.dims"), v.dims)
        if header(tr("sec.camera"), fa.ICON_FA_CAMERA):
            v.fov = W.slider("fov", tr("p.fov"), v.fov, 10.0, 80.0, 32.0, "%.0f°")
            v.turntable = W.checkbox("turn", tr("p.turntable"), v.turntable)
            v.turntable_speed = W.slider("turn_s", tr("p.turntable_speed"), v.turntable_speed, -180.0, 180.0, 25.0,
                                         "%.0f °/s")
            if W.wide_button("%s  %s" % (fa.ICON_FA_CAMERA_ROTATE, tr("act.reset_cam")), "rcam"):
                v.reset_camera()

    # ================================================================== inspector
    def inspector(self):
        app = self.app
        st = app.stats
        p = app.params
        theme.section_title(tr("sec.measures"), fa.ICON_FA_RULER)
        if st:
            vol_cm3 = st["volume"] / 1000.0
            W.kv_table("##meas", [
                (tr("m.width"), "%.2f mm" % st["w"]),
                (tr("m.height"), "%.2f mm" % st["h"]),
                (tr("m.total"), "%.2f mm" % st["total"]),
                (tr("m.relief"), "%.2f mm" % st["relief"]),
                (tr("m.base"), "%.2f mm" % st["base"]),
                (tr("m.volume"), "%.2f cm³" % vol_cm3),
                (tr("m.pla"), "%.1f g" % (vol_cm3 * 1.24), theme.LILAC),
                (tr("m.silver"), "%.1f g" % (vol_cm3 * 10.49)),
                (tr("m.gold"), "%.1f g" % (vol_cm3 * 19.32)),
            ])
        theme.section_title(tr("sec.mesh"), fa.ICON_FA_CIRCLE_NODES)
        if st:
            ny, nx = st["cells"]
            n = st["tris"]
            hd = app.cfg.hd_nodes
            W.kv_table("##mesh", [
                (tr("m.preview"), "{:,}".format(n).replace(",", ".")),
                (tr("m.grid"), "%d x %d" % (nx, ny)),
                (tr("m.hd_estimate", n=hd), "~{:,}".format(int(n * (hd / float(max(nx, ny))) ** 2)).replace(",", "."),
                 theme.PINK),
            ])
        theme.section_title(tr("sec.history"), fa.ICON_FA_CLOCK_ROTATE_LEFT)
        avail = imgui.get_content_region_avail().x
        bw = (avail - 8) / 2
        if W.icon_button("undo_i", "%s %s" % (fa.ICON_FA_ROTATE_LEFT, tr("act.undo")), tr("act.undo") + " (Ctrl+Z)",
                         size=imgui.ImVec2(bw, 0), enabled=app.history.can_undo()):
            app.pending.append("undo")
        imgui.same_line()
        if W.icon_button("redo_i", "%s %s" % (fa.ICON_FA_ROTATE_RIGHT, tr("act.redo")), tr("act.redo") + " (Ctrl+Y)",
                         size=imgui.ImVec2(bw, 0), enabled=app.history.can_redo()):
            app.pending.append("redo")
        W.label(tr("m.history", u=len(app.history.undo_stack), r=len(app.history.redo_stack)))
        theme.section_title(tr("sec.quick_export"), fa.ICON_FA_FILE_EXPORT)
        imgui.push_style_color(imgui.Col_.button, theme.v4((0.62, 0.22, 0.72), 1.0))
        if W.wide_button("%s  %s" % (fa.ICON_FA_CUBES, tr("act.export_dialog")), "exp_dlg", height=32):
            app.show["export"] = True
        imgui.pop_style_color()
        if W.wide_button("%s  %s" % (fa.ICON_FA_PRINT, tr("act.quick_stl")), "exp_stl", tip=tr("tip.quick_stl")):
            app.pending.append("quick_stl")
        if W.wide_button("%s  %s" % (fa.ICON_FA_CAMERA, tr("act.screenshot")), "shot_i"):
            app.pending.append("shot")
