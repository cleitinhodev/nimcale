# SPDX-License-Identifier: GPL-3.0-or-later
"""HelloImGui runner setup: docking layout, callbacks, window icon, drag & drop."""
import os
import sys
import time

import moderngl
from imgui_bundle import imgui, hello_imgui

from nimcale import APP_NAME, __version__, paths
from nimcale.app import NimcaleApp
from nimcale.i18n import tr
from nimcale import i18n
from nimcale.render.renderer import Renderer
from nimcale.ui import theme, fonts, widgets
from nimcale.ui.dialogs import Dialogs
from nimcale.ui.panels import Panels
from nimcale.ui.shell import Shell
from nimcale.ui.viewport import Viewport


def set_windows_icons(hwnd):
    """Small title-bar icon = favicon, big (taskbar / Alt+Tab) icon = main icon."""
    import ctypes
    user32 = ctypes.windll.user32
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_uint]
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x10, 0x80
    sm = user32.GetSystemMetrics
    small = user32.LoadImageW(None, paths.asset("icons", "nimcale_window.ico"), IMAGE_ICON, sm(49), sm(50),
                              LR_LOADFROMFILE)
    big = user32.LoadImageW(None, paths.asset("icons", "nimcale.ico"), IMAGE_ICON, sm(11), sm(12), LR_LOADFROMFILE)
    if small:
        user32.SendMessageW(hwnd, WM_SETICON, 0, small)
    if big:
        user32.SendMessageW(hwnd, WM_SETICON, 1, big)


class Runner:
    def __init__(self, args, cfg):
        self.args = args
        self.cfg = cfg
        self.app = NimcaleApp(args, cfg)
        self.app.load_initial()
        self.vp = Viewport(self.app)
        self.panels = Panels(self.app)
        self.dialogs = Dialogs(self.app)
        self.shell = Shell(self.app, self.vp, self.dialogs)
        self.frame = 0
        self.shot_done = False
        self.drop_cb = None
        self.started = False

    # ------------------------------------------------------------------ callbacks
    def post_init(self):
        app = self.app
        app.ctx = moderngl.create_context(require=330)
        samples = 4 if self.cfg.msaa else 0
        app.renderer = Renderer(app.ctx, samples=samples)
        info = app.renderer.info
        print("OpenGL:", info["version"], "|", info["renderer"], flush=True)
        self.cfg.gl_status = "ok"
        self.cfg.save()
        marker = os.path.join(paths.config_dir(), "starting.lock")
        try:
            os.remove(marker)
        except OSError:
            pass
        try:
            import glfw
            from imgui_bundle import glfw_utils
            win = glfw_utils.glfw_window_hello_imgui()

            def on_drop(window, files):
                app.drop_queue.extend(files)
            self.drop_cb = on_drop
            glfw.set_drop_callback(win, self.drop_cb)
            if sys.platform == "win32":
                set_windows_icons(glfw.get_win32_window(win))
        except Exception as e:
            print("window setup:", e, flush=True)
        app.upload_texture()
        app.refresh(force=True)
        self.started = True

    def setup_style(self):
        theme.apply(self.cfg.neon, self.cfg.anim_speed)
        imgui.get_style().font_scale_main = self.cfg.font_size / 16.0

    def load_fonts(self):
        fonts.load(16.0)

    def before_exit(self):
        self.cfg.save()

    def show_gui(self):
        app = self.app
        self.frame += 1
        if app.drop_queue:
            files, app.drop_queue = app.drop_queue, []
            app.handle_drops(files)
        while app.pending:
            act = app.pending.pop(0)
            try:
                self.shell.do(act)
            except Exception as e:
                import traceback
                traceback.print_exc()
                app.say(str(e), "error")
        interacting = imgui.is_any_item_active() or self.vp.dragging is not None
        app.upload_texture()
        try:
            app.refresh(interacting=interacting)
        except Exception as e:
            import traceback
            traceback.print_exc()
            app.say(str(e), "error")
        self.update_labels()
        self.dialogs.export_window()
        self.dialogs.settings_window()
        self.dialogs.about_window()
        self.dialogs.drop_window()
        self.dialogs.poll_export()
        self.shell.shortcuts()
        app.track_changes(interacting)
        rp = hello_imgui.get_runner_params()
        busy = (app.view.turntable or (app.export_job is not None) or self.vp.dragging is not None
                or app.tool == "sculpt")
        anim = (self.cfg.neon or self.cfg.anim_bg)
        rp.fps_idling.enable_idling = not busy
        rp.fps_idling.fps_idle = 30.0 if anim else 6.0
        self.scripted()

    def update_labels(self):
        rp = hello_imgui.get_runner_params()
        for w in rp.docking_params.dockable_windows:
            if w.label.endswith("###props"):
                w.label = tr("win.properties") + "###props"
            elif w.label.endswith("###inspector"):
                w.label = tr("win.inspector") + "###inspector"
            elif w.label.endswith("###viewport"):
                w.label = tr("win.viewport") + "###viewport"

    def viewport_window(self):
        imgui.push_style_var(imgui.StyleVar_.window_padding, imgui.ImVec2(0, 0))
        flags = imgui.WindowFlags_.no_scrollbar | imgui.WindowFlags_.no_scroll_with_mouse | \
            imgui.WindowFlags_.no_collapse
        rp = hello_imgui.get_runner_params()
        label = rp.docking_params.dockable_windows[0].label
        opened = imgui.begin(label, None, flags)
        imgui.pop_style_var()
        if opened[0] if isinstance(opened, tuple) else opened:
            self.vp.gui()
        imgui.end()

    # ------------------------------------------------------------------ scripted runs (tests / screenshots)
    def scripted(self):
        a = self.args
        app = self.app
        if a.open and self.frame == 2:
            for w in a.open.split(","):
                if w in app.show:
                    app.show[w] = True
            if a.tab is not None:
                app.about_tab = a.tab
        if a.props_tab and self.frame == 2:
            app.props_tab_req = a.props_tab
        if a.do and self.frame == a.do_at:
            for act in a.do.split(","):
                if act.startswith("view:"):
                    self.vp.view_preset(act[5:])
                elif act.startswith("set:"):
                    k, v = act[4:].split("=")
                    obj = app.view if hasattr(app.view, k) else app.params
                    cur = getattr(obj, k)
                    setattr(obj, k, type(cur)(float(v)) if not isinstance(cur, (str, bool)) else
                            (v == "1" if isinstance(cur, bool) else v))
                elif act.startswith("call:"):
                    # call:method|arg1|arg2  (automated tests: save/open project, alignment, GIF...)
                    name, *args = act[5:].split("|")

                    def conv(x):
                        for t in (int, float):
                            try:
                                return t(x)
                            except ValueError:
                                pass
                        return x
                    args = [conv(x) for x in args]
                    try:
                        r = getattr(app, name)(*args)
                        print("call %s -> %r" % (name, r), flush=True)
                    except Exception as e:
                        print("call %s FAILED: %s" % (name, e), flush=True)
                elif act.startswith("drop:"):
                    app.handle_drops(act[5:].split(";"))
                else:
                    app.pending.append(act)
        if a.demo_sculpt and self.frame == 4:
            self.demo_sculpt()
        if a.shot and self.frame == a.frames:
            self.want_shot = True

    def demo_sculpt(self):
        """Paint a few strokes programmatically (used by tests/screenshots)."""
        import numpy as np
        from nimcale.ui.viewport import plate_to_source_px
        app = self.app
        app.refresh(force=True)
        base = app.pipeline.cache.get("gA")
        sc = app.sculptor
        sc.brush = "raise"
        sc.radius = 0.06
        sc.strength = 1.0
        sc.begin(base.shape, base, 0, 0)
        for k in range(40):
            a = k / 39.0 * np.pi * 1.5
            u, v = 0.5 + 0.30 * np.cos(a), 0.5 + 0.30 * np.sin(a)
            cx, cy, r = plate_to_source_px(app, u, v)
            sc.stroke_to(base, cx, cy, r, 0.05)
        sc.end()
        app.after_stroke()
        app.tool = "sculpt"
        app.brush_uv = (0.5 + 0.30, 0.5)

    def before_swap(self):
        if getattr(self, "want_shot", False) and not self.shot_done:
            from PIL import Image
            ctx = self.app.ctx
            ctx.screen.use()
            w, h = ctx.screen.viewport[2], ctx.screen.viewport[3]
            data = ctx.screen.read(viewport=(0, 0, w, h), components=3, alignment=1)
            Image.frombytes("RGB", (w, h), data).transpose(Image.FLIP_TOP_BOTTOM).save(self.args.shot)
            print("shot:", self.args.shot, flush=True)
            self.shot_done = True
            if not self.args.keep_open:
                hello_imgui.get_runner_params().app_shall_exit = True

    # ------------------------------------------------------------------ run
    def params(self):
        rp = hello_imgui.RunnerParams()
        rp.app_window_params.window_title = "%s %s" % (APP_NAME, __version__)
        w, h = self.args.size
        rp.app_window_params.window_geometry.size = (w, h)
        rp.app_window_params.restore_previous_geometry = not self.args.shot
        rp.ini_folder_type = hello_imgui.IniFolderType.absolute_path
        rp.ini_filename = os.path.join(paths.config_dir(), "layout.ini")
        if self.args.shot or self.args.reset_layout:
            rp.ini_clear_previous_settings = True
        iw = rp.imgui_window_params
        iw.default_imgui_window_type = hello_imgui.DefaultImGuiWindowType.provide_full_screen_dock_space
        iw.show_menu_bar = True
        iw.show_menu_app = False
        iw.show_menu_view = False
        iw.show_status_bar = True
        iw.show_status_fps = False
        iw.remember_theme = False
        iw.config_windows_move_from_title_bar_only = True
        iw.background_color = imgui.ImVec4(0.05, 0.03, 0.07, 1.0)
        cb = rp.callbacks
        cb.post_init = self.post_init
        cb.load_additional_fonts = self.load_fonts
        cb.setup_imgui_style = self.setup_style
        cb.show_gui = self.show_gui
        cb.show_menus = self.shell.menus
        cb.show_status = self.shell.status
        cb.before_exit = self.before_exit
        cb.before_swap = self.before_swap
        opts = hello_imgui.EdgeToolbarOptions()
        opts.size_em = 2.6
        opts.window_bg = imgui.ImVec4(0.075, 0.04, 0.105, 1.0)
        cb.add_edge_toolbar(hello_imgui.EdgeToolbarType.top, self.shell.toolbar, opts)
        # docking layout
        d = rp.docking_params
        s1 = hello_imgui.DockingSplit()
        s1.initial_dock, s1.new_dock, s1.direction, s1.ratio = "MainDockSpace", "LeftSpace", imgui.Dir.left, 0.25
        s2 = hello_imgui.DockingSplit()
        s2.initial_dock, s2.new_dock, s2.direction, s2.ratio = "MainDockSpace", "RightSpace", imgui.Dir.right, 0.22
        d.docking_splits = [s1, s2]
        vw = hello_imgui.DockableWindow()
        vw.label = tr("win.viewport") + "###viewport"
        vw.dock_space_name = "MainDockSpace"
        vw.gui_function = self.viewport_window
        vw.call_begin_end = False
        vw.can_be_closed = False
        pw = hello_imgui.DockableWindow()
        pw.label = tr("win.properties") + "###props"
        pw.dock_space_name = "LeftSpace"
        pw.gui_function = self.panels.properties
        pw.can_be_closed = True
        iw_ = hello_imgui.DockableWindow()
        iw_.label = tr("win.inspector") + "###inspector"
        iw_.dock_space_name = "RightSpace"
        iw_.gui_function = self.panels.inspector
        iw_.can_be_closed = True
        d.dockable_windows = [vw, pw, iw_]
        d.layout_condition = hello_imgui.DockingLayoutCondition.application_start if self.args.shot else \
            hello_imgui.DockingLayoutCondition.first_use_since_app_start
        rp.fps_idling.enable_idling = not bool(self.args.shot)
        rp.fps_idling.fps_idle = 30.0
        return rp

    def run(self):
        hello_imgui.set_assets_folder(paths.assets_dir())
        rp = self.params()
        hello_imgui.run(rp)
