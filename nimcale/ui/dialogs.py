# SPDX-License-Identifier: GPL-3.0-or-later
"""Export, settings, help & about, drop chooser windows."""
import math
import os
import platform
import sys
import webbrowser

import moderngl
import numpy as np
from imgui_bundle import imgui, icons_fontawesome_6 as fa
from PIL import Image, ImageFilter

from nimcale import APP_NAME, __version__, URL_SITE, URL_PROJECT, URL_DONATE, URL_ISSUES, URL_LICENSE, paths
from nimcale.core import mesh as meshmod
from nimcale.core.pipeline import Pipeline
from nimcale.export import formats
from nimcale.export.job import ExportJob, ExportOptions
from nimcale.i18n import tr, LANGUAGES
from nimcale import i18n
from nimcale.ui import theme, widgets as W, fonts
from nimcale.ui import filedialog

EXPORT_FORMATS = ["stl", "stl_ascii", "obj", "glb", "gltf", "ply", "3mf", "off", "height_png", "normal_png",
                  "texture_png", "gif"]
EXT = {"stl": "stl", "stl_ascii": "stl", "obj": "obj", "glb": "glb", "gltf": "gltf", "ply": "ply", "3mf": "3mf",
       "off": "off", "height_png": "png", "normal_png": "png", "texture_png": "png", "gif": "gif"}
HD_PRESETS = [0, 1024, 2048, 3072, 4096, -1]


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024.0


def fmt_int(n):
    return "{:,}".format(int(n)).replace(",", ".")


def center_next(w, h):
    vp = imgui.get_main_viewport()
    imgui.set_next_window_pos(imgui.ImVec2(vp.work_pos.x + vp.work_size.x * 0.5, vp.work_pos.y + vp.work_size.y * 0.5),
                              imgui.Cond_.appearing, imgui.ImVec2(0.5, 0.5))
    w = min(w, vp.work_size.x - 40)
    if h:
        h = min(h, vp.work_size.y - 40)
    imgui.set_next_window_size(imgui.ImVec2(w, h), imgui.Cond_.appearing)


def glow_window_frame(phase=0.0):
    dl = imgui.get_foreground_draw_list()
    p = imgui.get_window_pos()
    s = imgui.get_window_size()
    theme.glow_rect(dl, p, imgui.ImVec2(p.x + s.x, p.y + s.y), 8.0, 0.9, phase, layers=5)


class Dialogs:
    def __init__(self, app):
        self.app = app
        self.opts = ExportOptions(fmt=app.cfg.export_fmt if app.cfg.export_fmt in EXPORT_FORMATS else "stl",
                                  hd_nodes=app.cfg.hd_nodes)
        self.hd_choice = HD_PRESETS.index(app.cfg.hd_nodes) if app.cfg.hd_nodes in HD_PRESETS else 2
        self.custom_nodes = app.cfg.hd_nodes
        self.decimate_on = False
        self.decimate_pct = 50.0
        self.gif_frames = 48
        self.gif_size = 480
        self.estimate_cache = (None, 0)
        self.glow_tex = None
        self.shine = None
        self.lang_idx = None

    # ================================================================== export
    def hd_nodes(self):
        c = HD_PRESETS[self.hd_choice]
        if c == 0:
            return None
        if c == -1:
            return int(self.custom_nodes)
        return c

    def estimate(self):
        app = self.app
        res = app.result
        if res is None:
            return 0
        nodes = self.hd_nodes()
        key = (nodes, app.pipeline.revision, app.params.mesh_res)
        if self.estimate_cache[0] == key:
            return self.estimate_cache[1]
        if nodes is None:
            n = app.stats.get("tris", 0)
        else:
            h, w = res.hf.shape
            k = nodes / float(max(w, h))
            n = meshmod.estimate_triangles(res.sdf, None) * k * k
        self.estimate_cache = (key, int(n))
        return int(n)

    def export_window(self):
        app = self.app
        if not app.show["export"]:
            return
        center_next(560, 640)
        opened, app.show["export"] = imgui.begin("%s  %s###export" % (fa.ICON_FA_FILE_EXPORT, tr("exp.title")),
                                                 app.show["export"], imgui.WindowFlags_.no_collapse)
        if opened:
            if app.cfg.neon:
                glow_window_frame()
            job = app.export_job
            if job is not None and not job.done:
                self.export_progress(job)
            else:
                self.export_form()
        imgui.end()

    def export_form(self):
        app, o = self.app, self.opts
        theme.section_title(tr("exp.format"), fa.ICON_FA_FILE)
        names = [tr("fmt." + f) for f in EXPORT_FORMATS]
        imgui.set_next_item_width(-1)
        ch, idx = imgui.combo("##fmt", EXPORT_FORMATS.index(o.fmt), names, 14)
        if ch:
            o.fmt = EXPORT_FORMATS[idx]
            app.cfg.export_fmt = o.fmt
        imgui.push_text_wrap_pos(0)
        W.label(tr("fmt.%s.desc" % o.fmt))
        imgui.pop_text_wrap_pos()
        is_mesh = formats.format_info(o.fmt) is not None
        if o.fmt == "gif":
            theme.section_title(tr("exp.animation"), fa.ICON_FA_FILM)
            self.gif_frames = W.slider("gif_n", tr("exp.frames"), self.gif_frames, 12, 120, 48, "%d", integer=True)
            self.gif_size = W.slider("gif_s", tr("exp.gif_size"), self.gif_size, 200, 1024, 480, "%d px", integer=True)
        else:
            theme.section_title(tr("exp.quality"), fa.ICON_FA_GEM)
            labels = [tr("hd.preview", n=app.params.mesh_res), tr("hd.high", n=1024), tr("hd.very_high", n=2048),
                      tr("hd.ultra", n=3072), tr("hd.max", n=4096), tr("hd.custom")]
            for i, lab in enumerate(labels):
                if imgui.radio_button(lab + "##hd%d" % i, self.hd_choice == i):
                    self.hd_choice = i
            if HD_PRESETS[self.hd_choice] == -1:
                self.custom_nodes = W.slider("hd_custom", tr("hd.custom_nodes"), self.custom_nodes, 256, 6144, 2048,
                                             "%d", integer=True)
            nodes = self.hd_nodes()
            o.hd = nodes is not None
            o.hd_nodes = nodes or app.params.mesh_res
            if nodes:
                app.cfg.hd_nodes = int(nodes)
            if o.hd:
                W.label(tr("exp.interp"))
                o.interp = ["bicubic", "bilinear"][W.segmented("interp", [tr("interp.bicubic"), tr("interp.bilinear")],
                                                               0 if o.interp == "bicubic" else 1)]
            if is_mesh:
                o.snap = W.checkbox("snap", tr("p.smooth_edge"), o.snap, tip=tr("tip.smooth_edge"))
                self.decimate_on = W.checkbox("dec", tr("exp.decimate"), self.decimate_on, tip=tr("tip.decimate"))
                if self.decimate_on:
                    self.decimate_pct = W.slider("dec_p", tr("exp.decimate_pct"), self.decimate_pct, 10.0, 95.0, 50.0,
                                                 "%.0f %%")
                o.decimate = self.decimate_pct / 100.0 if self.decimate_on else 0.0
                o.check = W.checkbox("chk", tr("exp.check"), o.check, tip=tr("tip.check"))
                n = self.estimate() * (1.0 - o.decimate)
                imgui.dummy(imgui.ImVec2(1, 2))
                W.kv_table("##est", [
                    (tr("exp.est_tris"), "~" + fmt_int(n), theme.PINK),
                    (tr("exp.est_size"), "~" + fmt_bytes(formats.estimate_bytes(o.fmt, n))),
                    (tr("exp.units"), tr("exp.units_m") if o.fmt in ("glb", "gltf") else "mm"),
                    (tr("exp.dims"), "%.1f x %.1f x %.1f mm" % (app.stats.get("w", 0), app.stats.get("h", 0),
                                                              app.stats.get("total", 0))),
                ])
                if n > 12e6:
                    imgui.text_colored(theme.v4(theme.WARN), fa.ICON_FA_TRIANGLE_EXCLAMATION + "  " + tr("exp.warn_big"))
            needs_tex = (is_mesh and formats.format_info(o.fmt)[2]) or o.fmt == "texture_png"
            if needs_tex:
                theme.section_title(tr("exp.texture"), fa.ICON_FA_IMAGE)
                tex_opts = [1024, 2048, 4096]
                k = W.segmented("texres", ["1024", "2048", "4096"], tex_opts.index(o.tex_res) if o.tex_res in tex_opts else 1)
                o.tex_res = tex_opts[k]
                o.tex_mix = W.checkbox("texmix", tr("exp.tex_mix"), o.tex_mix)
        imgui.dummy(imgui.ImVec2(1, 6))
        if app.export_report is not None:
            self.export_result(app.export_report)
        imgui.push_style_color(imgui.Col_.button, theme.v4((0.66, 0.24, 0.76), 1.0))
        if imgui.button("%s  %s###do_export" % (fa.ICON_FA_FLOPPY_DISK, tr("exp.export_btn")), imgui.ImVec2(-1, 38)):
            app.pending.append("export_now")
        imgui.pop_style_color()

    def export_progress(self, job):
        stage = tr("stage." + (job.stage or "mesh"))
        imgui.text(tr("exp.working"))
        imgui.progress_bar(job.progress, imgui.ImVec2(-1, 26), "%d %%  -  %s" % (int(job.progress * 100), stage))
        import time
        imgui.text_disabled(tr("exp.elapsed", s=time.time() - job.t0))
        if imgui.button("%s  %s" % (fa.ICON_FA_XMARK, tr("act.cancel")), imgui.ImVec2(-1, 30)):
            job.cancel()

    def export_result(self, rep):
        if rep.get("error"):
            imgui.push_text_wrap_pos(0)
            imgui.text_colored(theme.v4(theme.ERR), fa.ICON_FA_CIRCLE_XMARK + "  " + rep["error"])
            imgui.pop_text_wrap_pos()
            return
        if rep.get("cancelled"):
            imgui.text_colored(theme.v4(theme.WARN), tr("exp.cancelled"))
            return
        rows = [(tr("exp.saved"), os.path.basename(rep["path"]), theme.OK)]
        if rep.get("triangles"):
            rows.append((tr("exp.tris"), fmt_int(rep["triangles"])))
        rows.append((tr("exp.file_size"), fmt_bytes(rep.get("size", 0))))
        rows.append((tr("exp.time"), "%.1f s" % rep.get("seconds", 0)))
        if "watertight" in rep:
            rows.append((tr("exp.watertight"), tr("exp.yes") + "  " + fa.ICON_FA_CHECK if rep["watertight"]
                         else tr("exp.no") + "  (%d)" % rep.get("boundary_edges", 0),
                         theme.OK if rep["watertight"] else theme.ERR))
        W.kv_table("##rep", rows)
        if imgui.button("%s  %s" % (fa.ICON_FA_FOLDER_OPEN, tr("act.open_folder")), imgui.ImVec2(-1, 0)):
            open_folder(os.path.dirname(rep["path"]))
        imgui.dummy(imgui.ImVec2(1, 4))

    def start_export(self):
        app, o = self.app, self.opts
        ext = EXT[o.fmt]
        folder = app.cfg.export_dir or paths.output_dir("exports")
        stem = os.path.splitext(os.path.basename(app.hm.path or "nimcale"))[0] or "nimcale"
        default = os.path.join(folder, "%s.%s" % (stem, ext))
        path = filedialog.save_file(tr("exp.title"), [tr("fmt." + o.fmt), "*." + ext], default, ext)
        if not path:
            return
        app.cfg.export_dir = os.path.dirname(path)
        self.run_export(path)

    def run_export(self, path, opts=None):
        app = self.app
        o = opts or self.opts
        o.path = path
        app.export_report = None
        if o.fmt == "gif":
            try:
                import time
                t0 = time.time()
                app.export_gif(path, self.gif_frames, self.gif_size)
                app.export_report = dict(path=path, size=os.path.getsize(path), seconds=time.time() - t0)
                app.say(tr("msg.exported", name=os.path.basename(path)), "ok")
            except Exception as e:
                app.export_report = dict(error=str(e))
            return
        from dataclasses import replace
        app.export_job = ExportJob(app.export_data(), replace(o)).start()
        app.show["export"] = True

    def poll_export(self):
        app = self.app
        job = app.export_job
        if job is None or not job.done:
            return
        app.export_job = None
        if job.error:
            msg = tr("exp.out_of_memory") if job.error == "memory" else job.error.splitlines()[0]
            app.export_report = dict(error=msg)
            app.say(tr("msg.export_error", err=msg), "error")
        elif job.cancelled:
            app.export_report = dict(cancelled=True)
            app.say(tr("exp.cancelled"), "warn")
        else:
            app.export_report = job.report
            r = job.report
            extra = ""
            if "watertight" in r:
                extra = " - " + (tr("exp.watertight_ok") if r["watertight"] else tr("exp.watertight_bad"))
            app.say(tr("msg.exported_tris", name=os.path.basename(r["path"]), n=fmt_int(r.get("triangles", 0))) + extra,
                    "ok")

    # ================================================================== settings
    def settings_window(self):
        app = self.app
        if not app.show["settings"]:
            return
        cfg = app.cfg
        center_next(520, 560)
        opened, app.show["settings"] = imgui.begin("%s  %s###settings" % (fa.ICON_FA_GEAR, tr("set.title")),
                                                   app.show["settings"], imgui.WindowFlags_.no_collapse)
        if opened:
            if cfg.neon:
                glow_window_frame(1.0)
            theme.section_title(tr("set.language"), fa.ICON_FA_LANGUAGE)
            codes = ["auto"] + [c for c, _, _ in LANGUAGES]
            names = [tr("set.lang_auto")] + ["%s  (%s)" % (n, e) for _, n, e in LANGUAGES]
            cur = codes.index(cfg.language) if cfg.language in codes else 0
            imgui.set_next_item_width(-1)
            ch, idx = imgui.combo("##lang", cur, names, 14)
            if ch:
                cfg.language = codes[idx]
                i18n.set_language(cfg.language)
                cfg.save()
            theme.section_title(tr("set.appearance"), fa.ICON_FA_PALETTE)
            cfg.neon = W.checkbox("neon", tr("set.neon"), cfg.neon, tip=tr("tip.neon"))
            cfg.anim_bg = W.checkbox("animbg", tr("set.anim_bg"), cfg.anim_bg, tip=tr("tip.anim_bg"))
            cfg.anim_speed = W.slider("animsp", tr("set.anim_speed"), cfg.anim_speed, 0.1, 3.0, 1.0, "%.1fx")
            theme.state["neon"] = cfg.neon
            theme.state["speed"] = cfg.anim_speed
            W.label(tr("set.titlebar"))
            tb_modes = ["system", "dark", "light", "theme"]
            cur_tb = tb_modes.index(cfg.titlebar) if cfg.titlebar in tb_modes else 0
            k = W.segmented("titlebar", [tr("set.tb_system"), tr("set.tb_dark"), tr("set.tb_light"),
                                         tr("set.tb_theme")], cur_tb, tip=tr("tip.titlebar"))
            if tb_modes[k] != cfg.titlebar:
                cfg.titlebar = tb_modes[k]
                cfg.save()
                tb = getattr(app, "titlebar", None)
                if tb is not None:
                    tb.update(force=True)
            fs = W.slider("fsize", tr("set.font_size"), cfg.font_size, 11.0, 28.0, 16.0, "%.0f px")
            if fs != cfg.font_size:
                cfg.font_size = fs
            imgui.get_style().font_scale_main = cfg.font_size / 16.0
            cfg.tooltips = W.checkbox("tips", tr("set.tooltips"), cfg.tooltips)
            W.SETTINGS["tooltips"] = cfg.tooltips
            cfg.show_fps = W.checkbox("fps", tr("set.show_fps"), cfg.show_fps)
            theme.section_title(tr("set.rendering"), fa.ICON_FA_MICROCHIP)
            modes = ["auto", "gpu", "software"]
            k = W.segmented("rmode", [tr("set.r_auto"), tr("set.r_gpu"), tr("set.r_soft")], modes.index(cfg.renderer))
            if modes[k] != cfg.renderer:
                cfg.renderer = modes[k]
                app.say(tr("msg.restart_needed"), "warn")
            imgui.push_text_wrap_pos(0)
            W.label(tr("set.r_help"))
            imgui.pop_text_wrap_pos()
            cfg.msaa = W.checkbox("msaa", tr("set.msaa"), cfg.msaa, tip=tr("msg.restart_needed"))
            info = app.renderer.info if app.renderer else {}
            W.kv_table("##gl", [("OpenGL", info.get("version", "-")), (tr("set.gpu"), info.get("renderer", "-"))])
            theme.section_title(tr("set.files"), fa.ICON_FA_FOLDER)
            W.kv_table("##dirs", [(tr("set.config_dir"), paths.config_dir()),
                                  (tr("set.output_dir"), paths.output_dir())])
            avail = imgui.get_content_region_avail().x
            if imgui.button("%s  %s" % (fa.ICON_FA_FOLDER_OPEN, tr("set.open_config")), imgui.ImVec2((avail - 8) / 2, 0)):
                open_folder(paths.config_dir())
            imgui.same_line()
            if imgui.button("%s  %s" % (fa.ICON_FA_ROTATE_LEFT, tr("set.reset")), imgui.ImVec2((avail - 8) / 2, 0)):
                app.pending.append("reset_settings")
        imgui.end()
        if not app.show["settings"]:
            cfg.save()

    # ================================================================== about / help
    def ensure_glow(self):
        if self.glow_tex is not None:
            return
        ctx = self.app.ctx
        icon = Image.open(paths.asset("icons", "nimcale_icon_512.png")).convert("RGBA")
        self.icon_tex = ctx.texture(icon.size, 4, icon.tobytes())
        self.icon_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        # soft glow: blurred, brightened alpha
        a = icon.split()[3].filter(ImageFilter.GaussianBlur(28))
        glow = Image.new("RGBA", icon.size, (255, 120, 235, 0))
        glow.putalpha(a.point(lambda x: min(255, int(x * 1.6))))
        pad = 96
        big = Image.new("RGBA", (icon.size[0] + 2 * pad, icon.size[1] + 2 * pad), (0, 0, 0, 0))
        big.paste(glow, (pad, pad))
        big = big.filter(ImageFilter.GaussianBlur(20))
        self.glow_tex = ctx.texture(big.size, 4, big.tobytes())
        self.glow_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.glow_pad = pad / float(icon.size[0])
        # shine sweep frames (diagonal light band masked by the icon alpha)
        arr = np.asarray(icon.resize((256, 256), Image.LANCZOS), dtype=np.float32) / 255.0
        n = 32
        yy, xx = np.mgrid[0:256, 0:256] / 255.0
        frames = []
        for k in range(n):
            c = -0.6 + 2.2 * k / (n - 1)
            band = np.exp(-((xx + yy * 0.6 - c) / 0.07) ** 2)
            out = arr.copy()
            out[..., :3] = np.clip(out[..., :3] + band[..., None] * 0.75 * arr[..., 3:4], 0, 1)
            frames.append((out * 255).astype(np.uint8))
        atlas = np.concatenate(frames, axis=1)
        self.shine = ctx.texture((256 * n, 256), 4, np.ascontiguousarray(atlas).tobytes())
        self.shine.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.shine_n = n

    def shining_icon(self, size):
        """The Nimcale goddess with a pulsing glow, orbiting sparkles and a light sweep."""
        self.ensure_glow()
        t = theme.now()
        anim = self.app.cfg.neon
        dl = imgui.get_window_draw_list()
        p = imgui.get_cursor_screen_pos()
        avail = imgui.get_content_region_avail().x
        x0 = p.x + (avail - size) / 2
        y0 = p.y + size * 0.12
        cx, cy = x0 + size / 2, y0 + size / 2
        pulse = (0.65 + 0.35 * math.sin(t * 2.0)) if anim else 0.75
        g = size * (1 + 2 * self.glow_pad)
        gx, gy = cx - g / 2, cy - g / 2
        tint = theme.col32((1, 1, 1), pulse)
        dl.add_image(imgui.ImTextureRef(self.glow_tex.glo), imgui.ImVec2(gx, gy), imgui.ImVec2(gx + g, gy + g),
                     imgui.ImVec2(0, 0), imgui.ImVec2(1, 1), tint)
        # rotating rays
        if anim:
            for i in range(12):
                a = t * 0.35 + i * math.pi / 6
                r0, r1 = size * 0.52, size * (0.62 + 0.06 * math.sin(t * 3 + i))
                c = theme.col32(theme.lerp(theme.VIOLET, theme.PINK, (i % 2) * 0.8), 0.35 * pulse)
                dl.add_line(imgui.ImVec2(cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                            imgui.ImVec2(cx + math.cos(a) * r1, cy + math.sin(a) * r1), c, 3.0)
        # icon (shine frame)
        if anim:
            period = 3.2
            ph = (t % period) / period
            k = min(self.shine_n - 1, int(ph * 1.6 * self.shine_n)) if ph < 0.62 else self.shine_n - 1
            uv0 = imgui.ImVec2(k / float(self.shine_n), 0)
            uv1 = imgui.ImVec2((k + 1) / float(self.shine_n), 1)
            dl.add_image(imgui.ImTextureRef(self.shine.glo), imgui.ImVec2(x0, y0), imgui.ImVec2(x0 + size, y0 + size),
                         uv0, uv1)
        else:
            dl.add_image(imgui.ImTextureRef(self.icon_tex.glo), imgui.ImVec2(x0, y0), imgui.ImVec2(x0 + size, y0 + size))
        # sparkles
        if anim:
            for i in range(7):
                a = t * (0.5 + 0.07 * i) + i * 0.9
                rr = size * (0.56 + 0.05 * math.sin(t * 1.7 + i))
                sx, sy = cx + math.cos(a) * rr, cy + math.sin(a) * rr
                s = size * 0.018 * (0.6 + 0.4 * math.sin(t * 4 + i * 1.3))
                col = theme.col32((1, 0.9, 1), 0.9)
                dl.add_line(imgui.ImVec2(sx - s * 2, sy), imgui.ImVec2(sx + s * 2, sy), col, 1.5)
                dl.add_line(imgui.ImVec2(sx, sy - s * 2), imgui.ImVec2(sx, sy + s * 2), col, 1.5)
                dl.add_circle_filled(imgui.ImVec2(sx, sy), s * 0.8, col)
        imgui.dummy(imgui.ImVec2(avail, size * 1.24))

    def about_window(self):
        app = self.app
        if not app.show["about"]:
            return
        center_next(620, 700)
        opened, app.show["about"] = imgui.begin("%s  %s###about" % (fa.ICON_FA_CIRCLE_QUESTION, tr("about.title")),
                                                app.show["about"], imgui.WindowFlags_.no_collapse)
        if opened:
            if app.cfg.neon:
                glow_window_frame(2.0)
            if imgui.begin_tab_bar("##about_tabs"):
                tabs = (("about.tab_about", self.tab_about), ("about.tab_shortcuts", self.tab_shortcuts),
                        ("about.tab_guide", self.tab_guide), ("about.tab_system", self.tab_system))
                for i, (k, fn) in enumerate(tabs):
                    flags = imgui.TabItemFlags_.set_selected if app.about_tab == i + 1 else 0
                    sel, _ = imgui.begin_tab_item("%s###%s" % (tr(k), k), None, flags)
                    if sel:
                        imgui.begin_child("##ab_" + k)
                        fn()
                        imgui.end_child()
                        imgui.end_tab_item()
                app.about_tab = 0
                imgui.end_tab_bar()
        imgui.end()

    def link_button(self, icon, text, url, primary=False):
        if primary:
            imgui.push_style_color(imgui.Col_.button, theme.v4((0.78, 0.25, 0.70), 1.0))
            imgui.push_style_color(imgui.Col_.button_hovered, theme.v4((0.92, 0.35, 0.82), 1.0))
        clicked = imgui.button("%s  %s##%s" % (icon, text, url), imgui.ImVec2(-1, 34))
        if primary:
            imgui.pop_style_color(2)
        if imgui.is_item_hovered():
            imgui.set_tooltip(url)
            imgui.set_mouse_cursor(imgui.MouseCursor_.hand)
        if clicked:
            open_url(url)

    def centered(self, text, color=None, font=None, size=None):
        if font is not None:
            imgui.push_font(font, size or 0.0)
        w = imgui.calc_text_size(text).x
        imgui.set_cursor_pos_x(max(0, (imgui.get_content_region_avail().x - w) / 2 + imgui.get_cursor_pos_x()))
        if color:
            imgui.text_colored(theme.v4(color), text)
        else:
            imgui.text_unformatted(text)
        if font is not None:
            imgui.pop_font()

    def tab_about(self):
        self.shining_icon(min(250, imgui.get_content_region_avail().x * 0.5))
        bold = fonts.FONTS.get("bold")
        self.centered("Nimcale", theme.LILAC, bold, imgui.get_font_size() * 2.2)
        self.centered(tr("about.version", v=__version__), theme.TEXT_DIM)
        from nimcale import IS_TEST_BUILD
        if IS_TEST_BUILD:
            self.centered("%s  %s" % (fa.ICON_FA_FLASK, tr("beta.about")), theme.WARN)
        imgui.dummy(imgui.ImVec2(1, 4))
        imgui.push_text_wrap_pos(0)
        imgui.text_unformatted(tr("about.description"))
        imgui.pop_text_wrap_pos()
        imgui.dummy(imgui.ImVec2(1, 6))
        theme.section_title(tr("about.links"), fa.ICON_FA_LINK)
        self.link_button(fa.ICON_FA_GLOBE, "%s: %s" % (tr("about.site"), URL_SITE), URL_SITE)
        self.link_button(fa.ICON_FA_CODE_BRANCH, "%s: %s" % (tr("about.project"), URL_PROJECT), URL_PROJECT)
        self.link_button(fa.ICON_FA_HEART, "%s: %s" % (tr("about.donate"), URL_DONATE), URL_DONATE, primary=True)
        self.link_button(fa.ICON_FA_BUG, tr("about.issues"), URL_ISSUES)
        imgui.dummy(imgui.ImVec2(1, 6))
        theme.section_title(tr("about.license"), fa.ICON_FA_SCALE_BALANCED)
        imgui.push_text_wrap_pos(0)
        W.label(tr("about.license_text"))
        imgui.pop_text_wrap_pos()
        imgui.text_link_open_url("GNU GPL v3.0", URL_LICENSE)
        imgui.dummy(imgui.ImVec2(1, 4))
        imgui.push_text_wrap_pos(0)
        W.label(tr("about.credits"))
        imgui.pop_text_wrap_pos()

    SHORTCUTS = [
        ("sc.group_files", None),
        ("Ctrl+T", "sc.imp_tex"), ("Ctrl+M", "sc.imp_hm"), ("Ctrl+O", "sc.imp_both"),
        ("Ctrl+Shift+U", "sc.imp_surface"), ("Ctrl+Shift+O", "sc.open_project"), ("Ctrl+S", "sc.save_project"), ("Ctrl+E", "sc.export"),
        ("Ctrl+Shift+E", "sc.quick_stl"), ("P / Ctrl+P", "sc.screenshot"), ("G / Ctrl+L", "sc.align_io"),
        ("sc.group_edit", None),
        ("Ctrl+Z", "sc.undo"), ("Ctrl+Y / Ctrl+Shift+Z", "sc.redo"), ("R", "sc.reset_all"), ("K", "sc.sculpt"),
        ("sc.group_view", None),
        ("Tab", "sc.panels"), ("T", "sc.mode"), ("B", "sc.cutout"), ("F", "sc.wire"), ("U", "sc.light"),
        ("Space", "sc.turntable"), ("1 / 2 / 3 / 4", "sc.views"), ("Ctrl+R", "sc.reset_cam"), ("F11", "sc.fullscreen"),
        ("F1", "sc.help"), ("Esc", "sc.escape"), ("Ctrl+Q", "sc.quit"),
        ("sc.group_relief", None),
        ("+ / -", "sc.depth"), ("9 / 0", "sc.thickness"), (", / .", "sc.blur"), ("[ / ]", "sc.threshold"),
        ("← → ↑ ↓", "sc.light_dir"),
        ("sc.group_align", None),
        ("W A S D", "sc.align_move"), ("Q / E", "sc.align_scale"), ("Z / X", "sc.align_w"), ("C / V", "sc.align_h"),
        ("Shift", "sc.fine"),
        ("sc.group_mouse", None),
        ("sc.mouse_left", "sc.mouse_orbit"), ("sc.mouse_right", "sc.mouse_pan"), ("sc.mouse_wheel", "sc.mouse_zoom"),
        ("sc.mouse_sculpt", "sc.mouse_sculpt_desc"), ("sc.mouse_rclick", "sc.mouse_reset"),
    ]

    def tab_shortcuts(self):
        flags = imgui.TableFlags_.row_bg | imgui.TableFlags_.borders_inner_h | imgui.TableFlags_.sizing_stretch_prop
        if imgui.begin_table("##sc", 2, flags):
            imgui.table_setup_column("k", imgui.TableColumnFlags_.width_stretch, 0.9)
            imgui.table_setup_column("v", imgui.TableColumnFlags_.width_stretch, 1.6)
            for k, v in self.SHORTCUTS:
                imgui.table_next_row()
                imgui.table_next_column()
                if v is None:
                    imgui.text_colored(theme.v4(theme.PINK), tr(k))
                    imgui.table_next_column()
                    continue
                imgui.text_colored(theme.v4(theme.LILAC), tr(k) if k.startswith("sc.") else k)
                imgui.table_next_column()
                imgui.text_unformatted(tr(v))
            imgui.end_table()

    def tab_guide(self):
        imgui.push_text_wrap_pos(0)
        for i in range(1, 10):
            k = "guide.%d" % i
            imgui.text_colored(theme.v4(theme.PINK), "%d." % i)
            imgui.same_line()
            imgui.text_unformatted(tr(k))
            imgui.dummy(imgui.ImVec2(1, 2))
        imgui.pop_text_wrap_pos()

    def system_info(self):
        app = self.app
        info = app.renderer.info if app.renderer else {}
        import numpy
        import PIL
        try:
            from imgui_bundle import __version__ as ibv
        except Exception:
            ibv = "?"
        return [
            ("Nimcale", __version__), ("Python", platform.python_version()), ("OS", platform.platform()),
            ("OpenGL", info.get("version", "-")), ("GPU", info.get("renderer", "-")), ("Vendor", info.get("vendor", "-")),
            (tr("set.r_mode"), app.cfg.renderer), ("imgui-bundle", ibv), ("moderngl", moderngl.__version__),
            ("numpy", numpy.__version__), ("Pillow", PIL.__version__), (tr("set.language"), i18n.current()),
            (tr("set.config_dir"), paths.config_dir()),
        ]

    def tab_system(self):
        rows = self.system_info()
        W.kv_table("##sys", rows)
        if imgui.button("%s  %s" % (fa.ICON_FA_COPY, tr("act.copy_info")), imgui.ImVec2(-1, 0)):
            imgui.set_clipboard_text("\n".join("%s: %s" % r for r in rows))
            self.app.say(tr("msg.copied"), "ok")

    # ================================================================== drop chooser
    def drop_window(self):
        app = self.app
        if not app.show["drop"] or not app.drop_pending:
            return
        center_next(440, 0)
        if not imgui.is_popup_open("###dropq"):
            imgui.open_popup("###dropq")
        if imgui.begin_popup_modal("%s###dropq" % tr("drop.title"), None,
                                   imgui.WindowFlags_.always_auto_resize | imgui.WindowFlags_.no_saved_settings)[0]:
            imgui.text_colored(theme.v4(theme.LILAC), os.path.basename(app.drop_pending))
            imgui.text_unformatted(tr("drop.question"))
            imgui.dummy(imgui.ImVec2(1, 6))
            choice = None
            if imgui.button("%s  %s" % (fa.ICON_FA_IMAGE, tr("file.texture")), imgui.ImVec2(200, 34)):
                choice = "tex"
            imgui.same_line()
            if imgui.button("%s  %s" % (fa.ICON_FA_MOUNTAIN, tr("file.heightmap")), imgui.ImVec2(200, 34)):
                choice = "hm"
            if imgui.button(tr("act.cancel"), imgui.ImVec2(408, 0)) or imgui.is_key_pressed(imgui.Key.escape):
                choice = "cancel"
            if choice:
                path = app.drop_pending
                app.drop_pending = None
                app.show["drop"] = False
                imgui.close_current_popup()
                if choice == "tex":
                    app.import_texture(path)
                elif choice == "hm":
                    app.import_heightmap(path)
            imgui.end_popup()


def open_url(url):
    try:
        webbrowser.open(url)
    except Exception:
        pass


def open_folder(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
