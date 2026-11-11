# SPDX-License-Identifier: GPL-3.0-or-later
"""Menus, toolbar, status bar, keyboard shortcuts and the action dispatcher."""
import math
import os
import time

from imgui_bundle import imgui, hello_imgui, icons_fontawesome_6 as fa

from nimcale import paths
from nimcale.core.align import auto_align
from nimcale.core.orient import Orient
from nimcale.export.job import ExportOptions
from nimcale.i18n import tr
from nimcale.ui import theme, widgets as W
from nimcale.ui import filedialog

K = imgui.Key


class Shell:
    def __init__(self, app, viewport, dialogs):
        self.app = app
        self.vp = viewport
        self.dlg = dialogs
        self.fullscreen = False

    # ================================================================== actions
    def do(self, act):
        app = self.app
        p = app.params
        folder = app.cfg.last_dir or os.path.dirname(app.hm.path or "") or paths.documents_dir()
        img_f = filedialog.image_filters(tr)
        if act == "imp_tex":
            f = filedialog.open_file(tr("dlg.open_texture"), img_f, folder)
            if f:
                app.import_texture(f)
        elif act == "imp_hm":
            f = filedialog.open_file(tr("dlg.open_heightmap"), img_f, folder)
            if f:
                app.import_heightmap(f)
        elif act == "imp_both":
            f1 = filedialog.open_file(tr("dlg.open_both_1"), img_f, folder)
            if f1:
                f2 = filedialog.open_file(tr("dlg.open_both_2"), img_f, os.path.dirname(f1))
                if f2:
                    app.commit_now()
                    app.import_texture(f1, commit=False)
                    app.import_heightmap(f2, commit=False)
        elif act == "open_project":
            f = filedialog.open_file(tr("dlg.open_project"), [tr("dlg.project"), "*.nimcale"], folder)
            if f:
                app.open_project(f)
        elif act in ("save_project", "save_project_as"):
            path = app.project_path if act == "save_project" else None
            if not path:
                path = filedialog.save_file(tr("dlg.save_project"), [tr("dlg.project"), "*.nimcale"],
                                            os.path.join(paths.output_dir(), "nimcale_project.nimcale"), "nimcale")
            if path:
                app.save_project(path)
        elif act.startswith("recent:"):
            app.open_project(act[7:])
        elif act == "shot":
            app.screenshot()
        elif act == "shot_hd":
            app.screenshot(scale=2)
        elif act == "shot_alpha":
            app.screenshot(transparent=True, scale=2)
        elif act == "shot_as":
            f = filedialog.save_file(tr("dlg.save_screenshot"), ["PNG", "*.png"],
                                     os.path.join(paths.output_dir("screenshots"), "nimcale.png"), "png")
            if f:
                app.screenshot(f)
        elif act == "export_dialog":
            app.show["export"] = True
        elif act == "export_now":
            self.dlg.start_export()
        elif act == "quick_stl":
            o = ExportOptions(fmt="stl", hd=True, hd_nodes=app.cfg.hd_nodes)
            path = filedialog.save_file(tr("act.quick_stl"), [tr("fmt.stl"), "*.stl"],
                                        os.path.join(app.cfg.export_dir or paths.output_dir("exports"), "nimcale.stl"),
                                        "stl")
            if path:
                app.cfg.export_dir = os.path.dirname(path)
                self.dlg.run_export(path, o)
        elif act == "save_align":
            f = filedialog.save_file(tr("act.save_align"), [tr("dlg.align"), "*.json"],
                                     os.path.join(folder, "align.json"), "json")
            if f:
                app.save_alignment(f)
        elif act == "load_align":
            f = filedialog.open_file(tr("act.load_align"), [tr("dlg.align"), "*.json", tr("dlg.all_files"), "*"], folder)
            if f:
                try:
                    app.load_alignment(f)
                except Exception as e:
                    app.say(tr("msg.open_error", err=str(e)), "error")
        elif act == "auto_align":
            app.commit_now()
            (sx, sy, ox, oy), score = auto_align(app.tex, app.hm.work, p, app.hm.work.shape[1], app.hm.work.shape[0])
            p.sx, p.sy, p.ox, p.oy = sx, sy, ox, oy
            app.say(tr("msg.auto_aligned", score=score * 100), "ok")
        elif act == "undo":
            app.undo()
        elif act == "redo":
            app.redo()
        elif act == "reset_all":
            app.reset_all()
        elif act == "reset_cam":
            app.view.reset_camera()
        elif act == "reset_settings":
            from nimcale.config import AppConfig
            keep_lang = app.cfg.language
            app.cfg.__dict__.update(AppConfig().__dict__)
            app.cfg.language = keep_lang
            theme.apply(app.cfg.neon, app.cfg.anim_speed)
            app.cfg.save()
        elif act == "flip_x":
            p.flip_x = not p.flip_x
        elif act == "flip_y":
            p.flip_y = not p.flip_y
        elif act == "rot_l":
            p.rot90 = (p.rot90 + 1) % 4
        elif act == "rot_r":
            p.rot90 = (p.rot90 + 3) % 4
        elif act == "sculpt_clear":
            if app.sculptor.layer is not None:
                app.commit_now()
                app.sculptor.layer = None
                app.sculptor.rev += 1
                app.say(tr("msg.sculpt_cleared"))
        elif act.startswith("preset."):
            self.preset(act[7:])
        elif act == "toggle_panels":
            vis = not app.show["props"]
            app.show["props"] = app.show["inspector"] = vis
            self.set_windows_visible()
        elif act == "fullscreen":
            self.toggle_fullscreen()
        elif act == "quit":
            hello_imgui.get_runner_params().app_shall_exit = True
        elif act == "help":
            app.show["about"] = True
            app.about_tab = 2
        elif act == "about":
            app.show["about"] = True
            app.about_tab = 1
        elif act == "settings":
            app.show["settings"] = True
        elif act == "donate":
            from nimcale import URL_DONATE
            from nimcale.ui.dialogs import open_url
            open_url(URL_DONATE)

    def preset(self, name):
        app = self.app
        p = app.params
        app.commit_now()
        mm = p.size_mm
        if name == "coin":
            p.cutout, p.shape = True, "circle"
            p.rim_width, p.rim_height, p.bevel = 0.0, 0.0, 0.0
            app.refit_shape(quiet=True)
        elif name == "medal":
            p.cutout, p.shape = True, "circle"
            app.refit_shape(quiet=True)
            p.rim_width, p.rim_height, p.bevel = 1.6 / mm, 0.9, 0.6 / mm
        elif name == "plate":
            p.cutout = False
            p.rim_width, p.rim_height, p.bevel = 2.0 / mm, 0.8, 0.0
        elif name == "outline":
            p.cutout, p.shape = True, "auto"
            p.rim_width, p.rim_height, p.bevel = 0.0, 0.0, 0.0
        elif name == "tile":
            p.cutout, p.shape = True, "rounded"
            app.refit_shape(quiet=True)
            p.shape_round = 0.2
            p.rim_width, p.rim_height, p.bevel = 1.2 / mm, 0.7, 0.0
        app.say(tr("msg.preset", name=tr("preset." + name)), "ok")

    def set_windows_visible(self):
        rp = hello_imgui.get_runner_params()
        for w in rp.docking_params.dockable_windows:
            if "###props" in w.label:
                w.is_visible = self.app.show["props"]
            elif "###inspector" in w.label:
                w.is_visible = self.app.show["inspector"]

    def toggle_fullscreen(self):
        try:
            import glfw
            from imgui_bundle import glfw_utils
            win = glfw_utils.glfw_window_hello_imgui()
            if not self.fullscreen:
                self._win_geom = glfw.get_window_pos(win) + glfw.get_window_size(win)
                mon = glfw.get_primary_monitor()
                mode = glfw.get_video_mode(mon)
                glfw.set_window_monitor(win, mon, 0, 0, mode.size.width, mode.size.height, mode.refresh_rate)
            else:
                x, y, w, h = self._win_geom
                glfw.set_window_monitor(win, None, x, y, w, h, 0)
            self.fullscreen = not self.fullscreen
        except Exception as e:
            self.app.say(str(e), "warn")

    # ================================================================== menus
    def menus(self):
        app = self.app
        p, v = app.params, app.view

        def item(label, act, shortcut="", selected=False, enabled=True):
            if imgui.menu_item(label, shortcut, selected, enabled)[0]:
                app.pending.append(act)
        if imgui.begin_menu(tr("menu.file")):
            item("%s  %s" % (fa.ICON_FA_IMAGE, tr("act.imp_tex")), "imp_tex", "Ctrl+T")
            item("%s  %s" % (fa.ICON_FA_MOUNTAIN, tr("act.imp_hm")), "imp_hm", "Ctrl+M")
            item("%s  %s" % (fa.ICON_FA_FILE_IMPORT, tr("act.import_both")), "imp_both", "Ctrl+O")
            imgui.separator()
            item("%s  %s" % (fa.ICON_FA_FOLDER_OPEN, tr("act.open_project")), "open_project", "Ctrl+Shift+O")
            item("%s  %s" % (fa.ICON_FA_FLOPPY_DISK, tr("act.save_project")), "save_project", "Ctrl+S")
            item("%s  %s" % (fa.ICON_FA_FLOPPY_DISK, tr("act.save_project_as")), "save_project_as", "")
            if imgui.begin_menu("%s  %s" % (fa.ICON_FA_CLOCK_ROTATE_LEFT, tr("menu.recent")), bool(app.cfg.recent)):
                for r in app.cfg.recent:
                    item(os.path.basename(r), "recent:" + r)
                imgui.end_menu()
            imgui.separator()
            item("%s  %s" % (fa.ICON_FA_CUBES, tr("act.export_dialog")), "export_dialog", "Ctrl+E")
            item("%s  %s" % (fa.ICON_FA_PRINT, tr("act.quick_stl")), "quick_stl", "Ctrl+Shift+E")
            imgui.separator()
            item("%s  %s" % (fa.ICON_FA_CAMERA, tr("act.screenshot")), "shot", "P")
            item("%s  %s" % (fa.ICON_FA_CAMERA, tr("act.screenshot_as")), "shot_as", "Ctrl+P")
            item("%s  %s" % (fa.ICON_FA_CAMERA, tr("act.screenshot_hd")), "shot_hd", "")
            item("%s  %s" % (fa.ICON_FA_CAMERA, tr("act.screenshot_alpha")), "shot_alpha", "")
            imgui.separator()
            item("%s  %s" % (fa.ICON_FA_FLOPPY_DISK, tr("act.save_align")), "save_align", "G")
            item("%s  %s" % (fa.ICON_FA_FOLDER_OPEN, tr("act.load_align")), "load_align", "Ctrl+L")
            imgui.separator()
            item("%s  %s" % (fa.ICON_FA_RIGHT_FROM_BRACKET, tr("act.quit")), "quit", "Ctrl+Q")
            imgui.end_menu()
        if imgui.begin_menu(tr("menu.edit")):
            item("%s  %s" % (fa.ICON_FA_ROTATE_LEFT, tr("act.undo")), "undo", "Ctrl+Z", enabled=app.history.can_undo())
            item("%s  %s" % (fa.ICON_FA_ROTATE_RIGHT, tr("act.redo")), "redo", "Ctrl+Y", enabled=app.history.can_redo())
            imgui.separator()
            item("%s  %s" % (fa.ICON_FA_LEFT_RIGHT, tr("act.flip_x")), "flip_x")
            item("%s  %s" % (fa.ICON_FA_UP_DOWN, tr("act.flip_y")), "flip_y")
            item("%s  %s" % (fa.ICON_FA_ROTATE_LEFT, tr("act.rot_l")), "rot_l")
            item("%s  %s" % (fa.ICON_FA_ROTATE_RIGHT, tr("act.rot_r")), "rot_r")
            imgui.separator()
            item("%s  %s" % (fa.ICON_FA_WAND_MAGIC_SPARKLES, tr("act.auto_align")), "auto_align")
            item("%s  %s" % (fa.ICON_FA_TRASH_CAN, tr("sculpt.clear")), "sculpt_clear")
            imgui.separator()
            item("%s  %s" % (fa.ICON_FA_ARROWS_ROTATE, tr("act.reset_all")), "reset_all", "R")
            imgui.separator()
            item("%s  %s" % (fa.ICON_FA_GEAR, tr("set.title")), "settings")
            imgui.end_menu()
        if imgui.begin_menu(tr("menu.view")):
            for i, k in enumerate(("mode.texture", "mode.height", "mode.mix")):
                if imgui.menu_item(tr(k), "T" if i == 0 else "", v.mode == i)[0]:
                    v.mode = i
            imgui.separator()
            if imgui.menu_item(tr("shape.plate"), "B", not p.cutout)[0]:
                p.cutout = False
            if imgui.menu_item(tr("shape.cutout"), "B", p.cutout)[0]:
                p.cutout = True
            imgui.separator()
            for attr, key, sc in (("wire", "p.wire", "F"), ("lit", "p.lit", "U"), ("axes", "p.axes", ""),
                                  ("grid", "p.grid", ""), ("dims", "p.dims", ""), ("turntable", "p.turntable", "Space")):
                if imgui.menu_item(tr(key), sc, getattr(v, attr))[0]:
                    setattr(v, attr, not getattr(v, attr))
            imgui.separator()
            if imgui.menu_item(tr("menu.panels"), "Tab", app.show["props"])[0]:
                app.pending.append("toggle_panels")
            item(tr("act.reset_cam"), "reset_cam", "Ctrl+R")
            item(tr("sc.fullscreen"), "fullscreen", "F11")
            imgui.end_menu()
        if imgui.begin_menu(tr("menu.tools")):
            if imgui.menu_item("%s  %s" % (fa.ICON_FA_PAINTBRUSH, tr("tab.sculpt")), "K", app.tool == "sculpt")[0]:
                app.toggle_sculpt()
            imgui.separator()
            for k in ("coin", "medal", "plate", "outline", "tile"):
                item(tr("preset." + k), "preset." + k)
            imgui.end_menu()
        if imgui.begin_menu(tr("menu.help")):
            item("%s  %s" % (fa.ICON_FA_KEYBOARD, tr("about.tab_shortcuts")), "help", "F1")
            item("%s  %s" % (fa.ICON_FA_CIRCLE_INFO, tr("about.title")), "about")
            imgui.separator()
            from nimcale import URL_SITE, URL_PROJECT, URL_DONATE
            from nimcale.ui.dialogs import open_url
            if imgui.menu_item("%s  %s" % (fa.ICON_FA_GLOBE, tr("about.site")), "", False)[0]:
                open_url(URL_SITE)
            if imgui.menu_item("%s  %s" % (fa.ICON_FA_CODE_BRANCH, tr("about.project")), "", False)[0]:
                open_url(URL_PROJECT)
            if imgui.menu_item("%s  %s" % (fa.ICON_FA_HEART, tr("about.donate")), "", False)[0]:
                open_url(URL_DONATE)
            imgui.end_menu()
        # gradient line under the menu bar
        dl = imgui.get_foreground_draw_list()
        vp = imgui.get_main_viewport()
        y = vp.pos.y + imgui.get_frame_height() - 1
        theme.gradient_bar(dl, imgui.ImVec2(vp.pos.x, y), imgui.ImVec2(vp.pos.x + vp.size.x, y + 2), alpha=0.95)

    # ================================================================== toolbar
    def toolbar(self):
        app = self.app
        p, v = app.params, app.view
        imgui.push_style_var(imgui.StyleVar_.frame_padding, imgui.ImVec2(8, 6))
        imgui.push_style_color(imgui.Col_.button, theme.v4((0.15, 0.07, 0.21), 1.0))
        imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 2)

        def b(uid, icon, tip, act=None, active=False, enabled=True):
            if W.icon_button(uid, icon, tip, active=active, enabled=enabled):
                if act:
                    app.pending.append(act)
                return True
            imgui.same_line()
            return False

        def sep():
            imgui.same_line()
            imgui.text_disabled("|")
            imgui.same_line()
        if b("tb_tex", fa.ICON_FA_IMAGE, tr("act.imp_tex") + " (Ctrl+T)", "imp_tex"):
            imgui.same_line()
        if b("tb_hm", fa.ICON_FA_MOUNTAIN, tr("act.imp_hm") + " (Ctrl+M)", "imp_hm"):
            imgui.same_line()
        if b("tb_open", fa.ICON_FA_FOLDER_OPEN, tr("act.open_project"), "open_project"):
            imgui.same_line()
        if b("tb_save", fa.ICON_FA_FLOPPY_DISK, tr("act.save_project") + " (Ctrl+S)", "save_project"):
            imgui.same_line()
        sep()
        if b("tb_undo", fa.ICON_FA_ROTATE_LEFT, tr("act.undo") + " (Ctrl+Z)", "undo", enabled=app.history.can_undo()):
            imgui.same_line()
        if b("tb_redo", fa.ICON_FA_ROTATE_RIGHT, tr("act.redo") + " (Ctrl+Y)", "redo", enabled=app.history.can_redo()):
            imgui.same_line()
        sep()
        for i, (ic, k) in enumerate(((fa.ICON_FA_IMAGE, "mode.texture"), (fa.ICON_FA_MOUNTAIN_SUN, "mode.height"),
                                     (fa.ICON_FA_CIRCLE_HALF_STROKE, "mode.mix"))):
            if b("tb_m%d" % i, ic, tr(k), active=v.mode == i):
                v.mode = i
                imgui.same_line()
        sep()
        if b("tb_plate", fa.ICON_FA_SQUARE, tr("shape.plate"), active=not p.cutout):
            p.cutout = False
            imgui.same_line()
        if b("tb_cut", fa.ICON_FA_COINS, tr("shape.cutout"), active=p.cutout):
            p.cutout = True
            imgui.same_line()
        sep()
        if b("tb_wire", fa.ICON_FA_BORDER_ALL, tr("p.wire") + " (F)", active=v.wire):
            v.wire = not v.wire
            imgui.same_line()
        if b("tb_lit", fa.ICON_FA_LIGHTBULB, tr("p.lit") + " (U)", active=v.lit):
            v.lit = not v.lit
            imgui.same_line()
        if b("tb_dims", fa.ICON_FA_RULER_COMBINED, tr("p.dims"), active=v.dims):
            v.dims = not v.dims
            imgui.same_line()
        if b("tb_turn", fa.ICON_FA_ROTATE, tr("p.turntable") + " (Space)", active=v.turntable):
            v.turntable = not v.turntable
            imgui.same_line()
        if b("tb_sculpt", fa.ICON_FA_PAINTBRUSH, tr("tab.sculpt") + " (K)", active=app.tool == "sculpt"):
            app.toggle_sculpt()
            imgui.same_line()
        sep()
        if b("tb_shot", fa.ICON_FA_CAMERA, tr("act.screenshot") + " (P)", "shot"):
            imgui.same_line()
        imgui.push_style_color(imgui.Col_.button, theme.v4((0.55, 0.20, 0.66), 1.0))
        if b("tb_export", fa.ICON_FA_FILE_EXPORT + "  " + tr("act.export_short"), tr("act.export_dialog") + " (Ctrl+E)",
             "export_dialog"):
            imgui.same_line()
        imgui.pop_style_color()
        # right side
        right_w = 3 * 40
        imgui.same_line(max(imgui.get_cursor_pos_x(), imgui.get_window_width() - right_w))
        if b("tb_set", fa.ICON_FA_GEAR, tr("set.title"), "settings"):
            imgui.same_line()
        if b("tb_help", fa.ICON_FA_CIRCLE_QUESTION, tr("about.title") + " (F1)", "help"):
            imgui.same_line()
        if b("tb_heart", fa.ICON_FA_HEART, tr("about.donate"), "donate"):
            imgui.same_line()
        imgui.new_line()
        imgui.pop_style_color()
        imgui.pop_style_var()

    # ================================================================== status bar
    def status(self):
        app = self.app
        msg, t, kind = app.status
        col = {"ok": theme.OK, "warn": theme.WARN, "error": theme.ERR}.get(kind, theme.TEXT)
        if msg and time.time() - t < 10.0:
            icon = {"ok": fa.ICON_FA_CIRCLE_CHECK, "warn": fa.ICON_FA_TRIANGLE_EXCLAMATION,
                    "error": fa.ICON_FA_CIRCLE_XMARK}.get(kind, fa.ICON_FA_CIRCLE_INFO)
            imgui.text_colored(theme.v4(col), "%s  %s" % (icon, msg))
        else:
            W.label(tr("status.ready"))
        right = []
        if app.export_job is not None and not app.export_job.done:
            right.append("%s %d %%" % (fa.ICON_FA_GEARS, app.export_job.progress * 100))
        st = app.stats
        if st:
            right.append("%s %s" % (fa.ICON_FA_CIRCLE_NODES, "{:,}".format(st["tris"]).replace(",", ".")))
            right.append("%.1f x %.1f x %.1f mm" % (st["w"], st["h"], st["total"]))
        if app.renderer:
            r = app.renderer.info.get("renderer", "")
            right.append(("%s %s" % (fa.ICON_FA_MICROCHIP, r[:38])) if r else "")
        if app.cfg.show_fps:
            right.append("%.0f FPS" % imgui.get_io().framerate)
        txt = "   ".join(x for x in right if x)
        w = imgui.calc_text_size(txt).x
        imgui.same_line(max(imgui.get_cursor_pos_x() + 20, imgui.get_window_width() - w - 16))
        W.label(txt)

    # ================================================================== keyboard
    def shortcuts(self):
        app = self.app
        io = imgui.get_io()
        if io.want_text_input or imgui.is_any_item_active():
            return
        p, v = app.params, app.view
        ctrl, shift = io.key_ctrl, io.key_shift

        def pressed(k, repeat=False):
            return imgui.is_key_pressed(k, repeat)
        if ctrl:
            m = {K.t: "imp_tex", K.m: "imp_hm", K.l: "load_align", K.r: "reset_cam", K.q: "quit", K.p: "shot_as"}
            for k, a in m.items():
                if pressed(k):
                    app.pending.append(a)
            if pressed(K.o):
                app.pending.append("open_project" if shift else "imp_both")
            if pressed(K.s):
                app.pending.append("save_project_as" if shift else "save_project")
            if pressed(K.e):
                app.pending.append("quick_stl" if shift else "export_dialog")
            if pressed(K.z, True):
                app.pending.append("redo" if shift else "undo")
            if pressed(K.y, True):
                app.pending.append("redo")
            return
        if pressed(K.escape):
            if app.tool == "sculpt":
                app.tool = "orbit"
            else:
                for k in ("about", "settings", "export"):
                    if app.show[k]:
                        app.show[k] = False
                        break
        if pressed(K.f1):
            app.pending.append("help")
        if pressed(K.f11):
            app.pending.append("fullscreen")
        if pressed(K.tab):
            app.pending.append("toggle_panels")
        if pressed(K.f):
            v.wire = not v.wire
        if pressed(K.t):
            v.mode = (v.mode + 1) % 3
        if pressed(K.u):
            v.lit = not v.lit
        if pressed(K.b):
            p.cutout = not p.cutout
        if pressed(K.r):
            app.pending.append("reset_all")
        if pressed(K.g):
            app.pending.append("save_align")
        if pressed(K.p):
            app.pending.append("shot")
        if pressed(K.k):
            app.toggle_sculpt()
        if pressed(K.space):
            v.turntable = not v.turntable
        for k, name in ((K._1, "front"), (K._2, "iso"), (K._3, "side"), (K._4, "top")):
            if pressed(k):
                self.vp.view_preset(name)
        if pressed(K.left_bracket, True):
            p.threshold = max(0.0, p.threshold - (0.01 if shift else 0.03))
        if pressed(K.right_bracket, True):
            p.threshold = min(0.95, p.threshold + (0.01 if shift else 0.03))
        if pressed(K.comma, True):
            p.blur = max(0.0, p.blur - (0.5 if shift else 1.0))
        if pressed(K.period, True):
            p.blur = min(20.0, p.blur + (0.5 if shift else 1.0))
        self.held_keys(io.delta_time, shift)

    def held_keys(self, dt, shift):
        app = self.app
        p, v = app.params, app.view
        fine = 0.2 if shift else 1.0
        down = imgui.is_key_down
        if down(K.equal) or down(K.keypad_add):
            p.depth = min(0.35, p.depth + 0.15 * dt * fine * max(0.3, p.depth))
        if down(K.minus) or down(K.keypad_subtract):
            p.depth = max(0.0, p.depth - 0.15 * dt * fine * max(0.3, p.depth))
        if down(K._9):
            p.thickness = max(0.002, p.thickness - 0.08 * dt * fine)
        if down(K._0):
            p.thickness = min(0.35, p.thickness + 0.08 * dt * fine)
        if down(K.left_arrow):
            v.light_phi = (v.light_phi + math.degrees(1.6 * dt * fine)) % 360
        if down(K.right_arrow):
            v.light_phi = (v.light_phi - math.degrees(1.6 * dt * fine)) % 360
        if down(K.up_arrow):
            v.light_theta = min(89.0, v.light_theta + math.degrees(1.0 * dt * fine))
        if down(K.down_arrow):
            v.light_theta = max(3.0, v.light_theta - math.degrees(1.0 * dt * fine))
        mv = 0.15 * dt * fine
        sc = 0.35 * dt * fine
        if down(K.a):
            p.ox -= mv
        if down(K.d):
            p.ox += mv
        if down(K.w):
            p.oy += mv
        if down(K.s):
            p.oy -= mv
        if down(K.q):
            p.sx *= (1 - sc); p.sy *= (1 - sc)
        if down(K.e):
            p.sx *= (1 + sc); p.sy *= (1 + sc)
        if down(K.z):
            p.sx *= (1 - sc)
        if down(K.x):
            p.sx *= (1 + sc)
        if down(K.c):
            p.sy *= (1 - sc)
        if down(K.v):
            p.sy *= (1 + sc)
