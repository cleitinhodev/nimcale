# SPDX-License-Identifier: GPL-3.0-or-later
"""Export job: builds the (optionally high-definition) solid and writes it, with progress reporting."""
import os
import threading
import time
import traceback
from dataclasses import dataclass

import numpy as np

from nimcale.core import mesh as meshmod
from nimcale.core.align import bake_texture
from nimcale.core.pipeline import Pipeline
from nimcale.export import formats


@dataclass
class ExportOptions:
    fmt: str = "stl"
    path: str = ""
    hd: bool = True
    hd_nodes: int = 2048          # samples on the longest side (HD)
    interp: str = "bicubic"
    snap: bool = True
    decimate: float = 0.0         # 0 = off, else fraction of triangles removed (adaptive)
    check: bool = True
    tex_res: int = 2048
    tex_mix: bool = False


class ExportJob:
    def __init__(self, data, opts):
        """data: dict(hm, tex, params, sculpt, preview_result, outcol, mix)."""
        self.data = data
        self.opts = opts
        self.progress = 0.0
        self.stage = ""
        self.done = False
        self.error = None
        self.report = None
        self.cancelled = False
        self._cancel = False
        self.t0 = time.time()
        self.thread = None

    # ------------------------------------------------------------------ control
    def start(self):
        self.thread = threading.Thread(target=self._run_safe, daemon=True)
        self.thread.start()
        return self

    def cancel(self):
        self._cancel = True

    def is_cancelled(self):
        return self._cancel

    def _set(self, frac, stage):
        if self._cancel:
            raise formats.Cancelled()
        self.progress = float(frac)
        if stage:
            self.stage = stage

    def _run_safe(self):
        try:
            self.report = self.run()
        except formats.Cancelled:
            self.cancelled = True
        except MemoryError:
            self.error = "memory"
        except Exception as e:      # reported to the user
            self.error = "%s\n%s" % (e, traceback.format_exc(limit=4))
        finally:
            self.done = True

    # ------------------------------------------------------------------ work
    def run(self):
        d, o = self.data, self.opts
        p = d["params"]
        hm = d["hm"]
        if o.fmt in ("height_png", "normal_png", "texture_png"):
            return self._run_image()
        self._set(0.01, "heightmap")
        if o.hd:
            res = Pipeline().compute_hd(hm, p, o.hd_nodes, d.get("sculpt"), o.interp, tex=d.get("tex"))
            cells = None
        else:
            res = d["preview_result"]
            cells = p.mesh_res
        self._set(0.15, "mesh")
        m = meshmod.build_solid(res.hf, res.sdf, res.size, p.depth, p.thickness, res=cells, snap=o.snap,
                                progress=lambda f, s: self._set(0.15 + 0.30 * f, "mesh"))
        report = {"triangles_full": m.n_tris}
        if o.decimate > 0.01:
            self._set(0.46, "simplify")
            m = meshmod.decimate(m, o.decimate)
        fid, ext, needs_tex, unit = formats.format_info(o.fmt)
        k = p.size_mm * unit
        m = m.scaled(k)
        zmin = float(m.P[:, 2].min())
        m.P[:, 2] -= zmin
        self._set(0.55, "check")
        if o.check:
            report.update(meshmod.check_closed(m.F))
        tex = None
        if needs_tex and d.get("tex") is not None:
            self._set(0.62, "texture")
            tex = bake_texture(d["tex"], p, res.orient, o.tex_res, d.get("outcol", (1, 1, 1)),
                               hf=res.hf if o.tex_mix else None, mix=d.get("mix", 0.5) if o.tex_mix else 0.0)
        self._set(0.66, "write")
        formats.write_mesh(fid, o.path, m, tex, progress=lambda f, s="": self._set(0.66 + 0.33 * f, "write"),
                           cancel=self.is_cancelled)
        ext_ = m.P.max(0) - m.P.min(0)
        report.update(dict(path=o.path, triangles=m.n_tris, vertices=m.n_verts,
                           size=os.path.getsize(o.path) if os.path.exists(o.path) else 0,
                           seconds=time.time() - self.t0, dims=[float(x) / unit for x in ext_],
                           volume_mm3=abs(meshmod.volume(m.P, m.F)) / (unit ** 3) if o.fmt != "x" else 0.0))
        self._set(1.0, "done")
        return report

    def _run_image(self):
        d, o = self.data, self.opts
        p = d["params"]
        self._set(0.05, "heightmap")
        if o.hd:
            res = Pipeline().compute_hd(d["hm"], p, o.hd_nodes, d.get("sculpt"), o.interp, tex=d.get("tex"))
        else:
            res = d["preview_result"]
        self._set(0.6, "write")
        if o.fmt == "height_png":
            img = formats.heightmap_png16(res.hf)
        elif o.fmt == "normal_png":
            img = formats.normal_map(res.hf, res.size, p.depth)
        else:
            img = bake_texture(d["tex"], p, res.orient, o.tex_res, d.get("outcol", (1, 1, 1)),
                               hf=res.hf if o.tex_mix else None, mix=d.get("mix", 0.5) if o.tex_mix else 0.0)
        img.save(o.path)
        self._set(1.0, "done")
        return dict(path=o.path, size=os.path.getsize(o.path), seconds=time.time() - self.t0,
                    pixels=img.size, triangles=0)
