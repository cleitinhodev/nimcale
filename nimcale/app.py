# SPDX-License-Identifier: GPL-3.0-or-later
"""Nimcale application: model state, actions and the HelloImGui runner."""
import json
import math
import os
import sys
import time
import traceback
import zipfile

import numpy as np
from PIL import Image

from nimcale import APP_NAME, __version__, paths
from nimcale.config import AppConfig
from nimcale.core import images, mesh as meshmod
from nimcale.core.images import border_color
from nimcale.core.params import ModelParams, ViewParams
from nimcale.core.pipeline import Pipeline, cavity_ao, fit_shape_params
from nimcale.i18n import tr
from nimcale import i18n
from nimcale.tools.history import History, Snapshot
from nimcale.tools.sculpt import Sculptor

DEFAULT_TEX = paths.asset("defaults", "nimcale_textura.png")
DEFAULT_HM = paths.asset("defaults", "nimcale_relevo.webp")


def coin_defaults(p):
    """The default Nimcale coin look (mix view + object cutout, circular outline)."""
    p.cutout = True
    p.shape = "circle"
    p.depth = 0.045
    p.thickness = 0.035
    p.blur = 0.8
    p.threshold = 0.08
    p.smooth_edge = True
    p.rim_width = 0.0
    p.rim_height = 0.0
    p.bevel = 0.0
    p.size_mm = 40.0
    p.fit = 0
    return p


class NimcaleApp:
    def __init__(self, args, cfg=None):
        self.args = args
        self.cfg = cfg or AppConfig.load()
        self.params = ModelParams()
        self.view = ViewParams()
        self.hm = None
        self.tex = None
        self.pipeline = Pipeline()
        self.sculptor = Sculptor()
        self.history = History()
        self.result = None
        self.renderer = None
        self.ctx = None
        self.status = ("", 0.0, "info")
        self.project_path = None
        self.dirty = False
        # ui state
        self.tool = "orbit"
        self.show = dict(props=True, inspector=True, export=False, settings=False, about=False, drop=False,
                         progress=False, welcome=False)
        self.about_tab = 0
        self.drop_queue = []
        self.drop_pending = None
        self.export_job = None
        self.export_report = None
        self.pending = []
        self.turn_angle = 0.0
        self.last_frame_t = time.time()
        self.fps = 0.0
        self.anim_needed = False
        self.ao = None
        self.ao_rev = -1
        self.field_rev = -1
        self.topo_key = None
        self.topo = None
        self.last_refresh = 0.0
        self.stats = {}
        self.vp_size = (800, 600)
        self.vp_scene = None
        self.render_sig = None
        self.brush_uv = None
        self.running = True
        self.ui_textures = {}
        self.icon_tex = None
        self.gl_failed = None
        # undo bookkeeping
        self._committed = None
        self._seen_key = None
        self._seen_t = 0.0

    def toggle_sculpt(self, on=None):
        on = (self.tool != "sculpt") if on is None else on
        self.tool = "sculpt" if on else "orbit"
        if on:
            self.props_tab_req = "sculpt"
            self.view.turntable = False

    # ======================================================================== messages
    def say(self, msg, kind="info"):
        self.status = (msg, time.time(), kind)
        if kind == "error":
            self.error_count = getattr(self, "error_count", 0) + 1
        print("[%s] %s" % (kind, msg), flush=True)

    # ======================================================================== loading
    def load_initial(self):
        a = self.args
        tex = a.texture or DEFAULT_TEX
        hm = a.heightmap or DEFAULT_HM
        try:
            self.tex = images.load_texture(tex)
            self.hm = images.load_heightmap(hm)
        except Exception as e:
            self.say(tr("msg.open_error", err=str(e)), "error")
            self.tex = images.load_texture(DEFAULT_TEX)
            self.hm = images.load_heightmap(DEFAULT_HM)
        coin_defaults(self.params)
        self.shape_user_set = False
        if a.heightmap or (a.texture and not a.project):
            self.auto_outline_for_new_image()      # images given on the command line: not the coin
        self.refit_shape(quiet=True)
        if a.project:
            self.open_project(a.project)
        self._committed = self.snapshot()

    def auto_outline_for_new_image(self):
        """A new image is not the default coin: follow the object's own outline (detected background)
        and drop the coin-only edge settings - unless the user picked a shape / preset explicitly."""
        p = self.params
        p.cutout = True
        p.shape = "auto"
        p.outline_src, p.bg_mode = "auto", "auto"
        p.rim_width = p.rim_height = p.bevel = 0.0
        p.mask_grow = p.mask_feather = 0.0
        p.keep_largest = False
        p.fill_holes = True

    def mark_shape_choice(self):
        """Called when the user explicitly chooses an outline, preset or edge setting."""
        self.shape_user_set = True

    def refit_shape(self, quiet=False, shape=None):
        p = self.params
        if shape:
            p.shape = shape
        if p.shape == "auto":
            return
        cx, cy, rx, ry = fit_shape_params(self.hm, p, p.shape, tex=self.tex)
        if p.shape == "circle":
            rx = ry = rx * 0.995
        p.shape_cx, p.shape_cy, p.shape_rx, p.shape_ry = cx, cy, rx, ry
        if not quiet:
            self.say(tr("msg.shape_fitted"), "ok")

    def import_texture(self, path, commit=True):
        try:
            t = images.load_texture(path)
        except Exception as e:
            self.say(tr("msg.open_error", err=str(e)), "error")
            return False
        if commit:
            self.commit_now()
        self.tex = t
        self.params.reset_align()
        self.cfg.last_dir = os.path.dirname(os.path.abspath(path))
        self.say(tr("msg.texture_loaded", name=os.path.basename(path), w=t.orig_size[0], h=t.orig_size[1]), "ok")
        self.check_aspect()
        self.dirty = True
        return True

    def import_heightmap(self, path, commit=True):
        try:
            h = images.load_heightmap(path)
        except Exception as e:
            self.say(tr("msg.open_error", err=str(e)), "error")
            return False
        if commit:
            self.commit_now()
        self.hm = h
        self.sculptor.reset()
        self.params.reset_align()
        self.cfg.last_dir = os.path.dirname(os.path.abspath(path))
        if not getattr(self, "shape_user_set", False):
            self.auto_outline_for_new_image()
        elif self.params.cutout and self.params.shape != "auto":
            self.refit_shape(quiet=True)
        self.say(tr("msg.height_loaded", name=os.path.basename(path), w=h.orig_size[0], h=h.orig_size[1]), "ok")
        self.check_aspect()
        self.dirty = True
        return True

    def check_aspect(self):
        if self.tex is None or self.hm is None:
            return
        tw, th = self.tex.size
        hh, hw = self.hm.shape
        ta, pa = tw / float(th), hw / float(hh)
        if abs(ta - pa) / pa > 0.05:
            self.say(tr("msg.aspect_differs", a=ta, b=pa), "warn")

    def handle_drops(self, files):
        imgs = [f for f in files if os.path.isfile(f) and images.is_image_file(f)]
        projs = [f for f in files if f.lower().endswith(".nimcale")]
        if projs:
            self.open_project(projs[0])
            return
        if not imgs:
            if files:
                self.say(tr("msg.unsupported", name=os.path.basename(files[0])), "warn")
            return
        if len(imgs) >= 2:
            hm_h = ("height", "altura", "depth", "displace", "disp", "bump", "relevo", "gray", "grey", "cinza",
                    "hm", "z_", "relief", "relieve")
            tx_h = ("textur", "tex", "color", "colour", "cor", "diffuse", "albedo", "base", "foto", "photo")

            def score(f):
                n = os.path.basename(f).lower()
                return sum(h in n for h in hm_h) - sum(h in n for h in tx_h)
            a_, b_ = imgs[0], imgs[1]
            tex_p, hm_p = (b_, a_) if score(a_) > score(b_) else (a_, b_)
            self.commit_now()
            ok1 = self.import_texture(tex_p, commit=False)
            ok2 = self.import_heightmap(hm_p, commit=False)
            if ok1 and ok2:
                self.say(tr("msg.dropped_both", tex=os.path.basename(tex_p), hm=os.path.basename(hm_p)), "ok")
        else:
            self.drop_pending = imgs[0]
            self.show["drop"] = True

    # ======================================================================== undo / redo
    def snapshot(self, label=""):
        return Snapshot(self.params, self.sculptor.layer, self.tex, self.hm, label)

    def restore(self, s):
        self.params = s.params.copy()
        self.sculptor.layer = s.sculpt
        self.sculptor.rev += 1
        self.tex = s.tex
        self.hm = s.hm
        self._committed = s
        self._seen_key = self.params.key()
        self.dirty = True

    def commit_now(self, label=""):
        """Record the current committed state before an explicit change (import, stroke...)."""
        cur = self.snapshot(label)
        if self._committed is not None and not self._committed.same(cur):
            self.history.push(self._committed)
        elif self._committed is not None:
            self.history.push(self._committed)
        self._committed = cur

    def track_changes(self, interacting):
        """Called every frame: parameter edits become undo steps once they settle."""
        key = self.params.key()
        now = time.time()
        if key != self._seen_key:
            self._seen_key = key
            self._seen_t = now
            self.dirty = True
            return
        if interacting or now - self._seen_t < 0.35:
            return
        cur = self.snapshot()
        if self._committed is not None and not self._committed.same(cur):
            self.history.push(self._committed)
            self._committed = cur

    def after_stroke(self):
        cur = self.snapshot("sculpt")
        self.history.push(self._committed)
        self._committed = cur
        self.dirty = True

    def undo(self):
        cur = self.snapshot()
        if not self._committed.same(cur):
            self.history.push(self._committed)
            self._committed = cur
        s = self.history.undo(cur)
        if s is None:
            self.say(tr("msg.nothing_undo"))
            return
        self.restore(s)
        self.say(tr("msg.undone"))

    def redo(self):
        s = self.history.redo(self.snapshot())
        if s is None:
            self.say(tr("msg.nothing_redo"))
            return
        self.restore(s)
        self.say(tr("msg.redone"))

    # ======================================================================== model refresh
    def refresh(self, interacting=False, force=False):
        if self.hm is None:
            return
        now = time.time()
        if interacting and not force and now - self.last_refresh < 0.06:
            return
        res = self.pipeline.compute(self.hm, self.params, self.sculptor.layer, self.sculptor.rev, tex=self.tex)
        self.result = res
        if self.renderer is None:
            return
        rev = self.pipeline.revision
        p = self.params
        tkey = (id(res.sdf), p.mesh_res, p.smooth_edge, res.hf.shape)
        if tkey != self.topo_key:
            hh, ww = res.hf.shape
            nx, ny = meshmod.grid_dims(ww, hh, p.mesh_res)
            cells = meshmod.clean_cells(meshmod.cell_mask(res.sdf, nx, ny))
            if not cells.any():
                cells[:] = True
            topo = meshmod.Topology(cells)
            U, V = topo.node_uv()
            if p.smooth_edge:
                meshmod.snap_boundary(topo, U, V, res.sdf, res.size)
            self.renderer.set_topology(topo, U.astype(np.float32), V.astype(np.float32), res.size)
            self.topo = topo
            self.topo_key = tkey
            self.update_stats()
        if rev != self.field_rev:
            busy = interacting or self.sculptor.stroking
            if self.ao is None or self.ao.shape != res.hf.shape or (not busy):
                self.ao = cavity_ao(res.hf, res.size, p.depth) if self.view.ao > 0.001 else np.ones_like(res.hf)
                self.ao_rev = rev
            self.renderer.set_field(res.hf, self.ao)
            self.field_rev = rev
            self.update_stats()
        elif self.ao_rev != rev and not interacting and not self.sculptor.stroking:
            self.ao = cavity_ao(res.hf, res.size, p.depth) if self.view.ao > 0.001 else np.ones_like(res.hf)
            self.ao_rev = rev
            self.renderer.set_field(res.hf, self.ao)

    def upload_texture(self):
        if self.renderer is None or self.tex is None:
            return
        if getattr(self, "_tex_uploaded", None) is not self.tex:
            self.renderer.set_texture(self.tex.img, border_color(self.tex.img))
            self._tex_uploaded = self.tex
            self.ui_textures.pop("thumb_tex", None)
        if getattr(self, "_hm_thumb", None) is not self.hm:
            self.ui_textures.pop("thumb_hm", None)
            self._hm_thumb = self.hm

    def update_stats(self):
        res, p = self.result, self.params
        if res is None or self.topo is None:
            return
        sw, sh = res.size
        inside = res.sdf > 0
        if not inside.any():
            inside = np.ones_like(inside)
        rows = np.flatnonzero(inside.any(1))
        cols = np.flatnonzero(inside.any(0))
        hh, ww = inside.shape
        x0, x1 = cols[0] / (ww - 1) * sw, cols[-1] / (ww - 1) * sw
        y0, y1 = rows[0] / (hh - 1) * sh, rows[-1] / (hh - 1) * sh
        hmax = float(res.hf[inside].max()) if inside.any() else 0.0
        mm = p.size_mm
        area_frac = float(inside.mean())
        mean_h = float(res.hf[inside].mean()) if inside.any() else 0.0
        vol = area_frac * sw * sh * (p.thickness + mean_h * p.depth) * mm ** 3   # mm^3
        self.stats = dict(w=(x1 - x0) * mm, h=(y1 - y0) * mm, relief=hmax * p.depth * mm,
                          base=p.thickness * mm, total=(hmax * p.depth + p.thickness) * mm,
                          volume=vol, tris=getattr(self.renderer, "n_tris", 0),
                          cells=self.topo.cells.shape,
                          bbox=((x0 - sw / 2, y0 - sh / 2, -p.thickness), (x1 - sw / 2, y1 - sh / 2,
                                                                         hmax * p.depth)))

    # ======================================================================== scene / rendering
    def scene(self, t):
        res = self.result
        anim = self.cfg.anim_bg
        brush = None
        if self.tool == "sculpt" and self.brush_uv is not None:
            brush = (self.brush_uv[0], self.brush_uv[1], self.sculptor.radius, 1.0)
        return dict(params=self.params, view=self.view, size=res.size, orient=res.orient, time=t,
                    anim_bg=anim, brush=brush, bbox=self.stats.get("bbox"),
                    grid_step=10.0 / max(1.0, self.params.size_mm))

    def screenshot(self, path=None, scale=1, transparent=False):
        if self.renderer is None or self.result is None:
            return None
        if path is None:
            path = paths.unique_path(paths.output_dir("screenshots"), "nimcale", "png")
        w, h = self.vp_size
        try:
            img = self.renderer.render_offscreen(self.scene(0.0), int(w * scale), int(h * scale),
                                                 transparent=transparent, extra_yaw=math.radians(self.turn_angle))
            img.save(path)
            self.say(tr("msg.screenshot_saved", path=path), "ok")
            return path
        except Exception as e:
            self.say(tr("msg.screenshot_error", err=str(e)), "error")
            return None

    def export_gif(self, path, frames=48, size=480, progress=None):
        imgs = []
        s = self.scene(0.0)
        for k in range(frames):
            img = self.renderer.render_offscreen(s, size, size, extra_yaw=2 * math.pi * k / frames)
            imgs.append(img.convert("P", palette=Image.ADAPTIVE, colors=255))
            if progress:
                progress((k + 1) / frames)
        imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=int(4000 / frames), loop=0,
                     optimize=True, disposal=2)
        return path

    # ======================================================================== projects
    def save_project(self, path):
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                meta = dict(app=APP_NAME, version=__version__, params=self.params.to_dict(),
                            view=self.view.to_dict(), texture_name=os.path.basename(self.tex.path or "texture.png"),
                            heightmap_name=os.path.basename(self.hm.path or "heightmap.png"),
                            tex_orig=list(self.tex.orig_size), hm_orig=list(self.hm.orig_size))
                z.writestr("project.json", json.dumps(meta, indent=2, ensure_ascii=False))
                import io
                b = io.BytesIO()
                self.tex.img.save(b, "PNG")
                z.writestr("texture.png", b.getvalue())
                b = io.BytesIO()
                np.save(b, self.hm.full.astype(np.float32))
                z.writestr("heightmap.npy", b.getvalue())
                if getattr(self.hm, "alpha_full", None) is not None:
                    b = io.BytesIO()
                    np.save(b, self.hm.alpha_full.astype(np.float32))
                    z.writestr("heightmap_alpha.npy", b.getvalue())
                if self.sculptor.has_edits():
                    b = io.BytesIO()
                    np.save(b, self.sculptor.layer.astype(np.float32))
                    z.writestr("sculpt.npy", b.getvalue())
            self.project_path = path
            self.dirty = False
            self.cfg.add_recent(path)
            self.say(tr("msg.project_saved", name=os.path.basename(path)), "ok")
            return True
        except Exception as e:
            self.say(tr("msg.project_error", err=str(e)), "error")
            return False

    def open_project(self, path):
        import io
        try:
            with zipfile.ZipFile(path, "r") as z:
                meta = json.loads(z.read("project.json").decode("utf-8"))
                tex_img = Image.open(io.BytesIO(z.read("texture.png")))
                tex_img.load()
                hm_arr = np.load(io.BytesIO(z.read("heightmap.npy")))
                sculpt = np.load(io.BytesIO(z.read("sculpt.npy"))) if "sculpt.npy" in z.namelist() else None
                hm_alpha = np.load(io.BytesIO(z.read("heightmap_alpha.npy"))) \
                    if "heightmap_alpha.npy" in z.namelist() else None
            self.commit_now()
            self.tex = images.TextureImage(tex_img.convert("RGB"), tuple(meta.get("tex_orig", tex_img.size)),
                                           meta.get("texture_name", ""))
            self.hm = images.HeightImage(hm_arr, tuple(meta.get("hm_orig", hm_arr.shape[::-1])),
                                         meta.get("heightmap_name", ""), hm_alpha)
            self.shape_user_set = True
            self.params = ModelParams.from_dict(meta.get("params", {}))
            self.view.update(meta.get("view", {}))
            self.sculptor.layer = sculpt.astype(np.float32) if sculpt is not None else None
            self.sculptor.rev += 1
            self.project_path = path
            self.dirty = False
            self.cfg.add_recent(path)
            self._committed = self.snapshot()
            self._seen_key = self.params.key()
            self.say(tr("msg.project_opened", name=os.path.basename(path)), "ok")
            return True
        except Exception as e:
            traceback.print_exc()
            self.say(tr("msg.project_error", err=str(e)), "error")
            return False

    def save_alignment(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.params.align_dict(), f, indent=2)
        self.say(tr("msg.align_saved", name=os.path.basename(path)), "ok")

    def load_alignment(self, path):
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        self.commit_now()
        # placa3d files have no "fit"/"rot": they were calibrated with "stretch" and no rotation
        a = dict(fit=0, sx=1.0, sy=1.0, ox=0.0, oy=0.0, rot=0.0)
        for k in a:
            if k in d:
                a[k] = int(d[k]) if k == "fit" else float(d[k])
        self.params.update(a)
        self.say(tr("msg.align_loaded", name=os.path.basename(path)), "ok")

    def reset_all(self):
        self.commit_now()
        self.params = coin_defaults(ModelParams())
        self.shape_user_set = False
        self.refit_shape(quiet=True)
        self.view = ViewParams()
        self.sculptor.reset()
        self.say(tr("msg.reset_all"))

    def export_data(self):
        return dict(hm=self.hm, tex=self.tex, params=self.params.copy(),
                    sculpt=self.sculptor.layer.copy() if self.sculptor.layer is not None else None,
                    preview_result=self.result, outcol=border_color(self.tex.img), mix=self.view.mix)
