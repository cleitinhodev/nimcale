# SPDX-License-Identifier: GPL-3.0-or-later
"""moderngl renderer: draws the relief model into an offscreen framebuffer shown by the UI."""
import math

import moderngl
import numpy as np
from PIL import Image

from nimcale.core.align import align_params, src_size
from nimcale.core.params import MATERIAL_DEFS
from nimcale.render import shaders
from nimcale.render.camera import Camera, gl_bytes


def _u(prog, name, value):
    try:
        u = prog[name]
    except KeyError:
        return
    if isinstance(value, (bytes, bytearray)):
        u.write(value)
    else:
        u.value = value


class Renderer:
    def __init__(self, ctx, samples=4):
        self.ctx = ctx
        self.samples = samples
        self.prog = ctx.program(vertex_shader=shaders.MODEL_VERT, fragment_shader=shaders.MODEL_FRAG)
        self.bgprog = ctx.program(vertex_shader=shaders.BG_VERT, fragment_shader=shaders.BG_FRAG)
        self.lprog = ctx.program(vertex_shader=shaders.LINE_VERT, fragment_shader=shaders.LINE_FRAG)
        self.bg_vao = ctx.vertex_array(self.bgprog, [])
        self.line_vbo = ctx.buffer(reserve=4096 * 7 * 4, dynamic=True)
        self.line_vao = ctx.vertex_array(self.lprog, [(self.line_vbo, "3f 4f", "in_pos", "in_col")])
        self.height_tex = None
        self.hdim = (2.0, 2.0)
        self.color_tex = None
        self.outcol = (1.0, 1.0, 1.0)
        self.tex_size = (1, 1)
        self.vaos = {}
        self.bufs = []
        self.counts = {}
        self.fbo = self.fbo_ms = self.color = None
        self.fbo_size = (0, 0)
        self.info = dict(renderer=ctx.info.get("GL_RENDERER", "?"), version=ctx.info.get("GL_VERSION", "?"),
                         vendor=ctx.info.get("GL_VENDOR", "?"))

    # ------------------------------------------------------------------ resources
    def set_texture(self, img, outcol):
        if self.color_tex is not None:
            self.color_tex.release()
        data = np.asarray(img.transpose(Image.FLIP_TOP_BOTTOM).convert("RGB"), dtype=np.uint8)
        self.color_tex = self.ctx.texture(img.size, 3, np.ascontiguousarray(data).tobytes())
        self.color_tex.build_mipmaps()
        self.color_tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        try:
            self.color_tex.anisotropy = 8.0
        except Exception:
            pass
        self.color_tex.repeat_x = self.color_tex.repeat_y = False
        self.outcol = outcol
        self.tex_size = img.size

    def set_field(self, hf, ao):
        h, w = hf.shape
        data = np.ascontiguousarray(np.stack([hf, ao], -1), dtype=np.float32)
        if self.height_tex is not None and self.height_tex.size == (w, h):
            self.height_tex.write(data.tobytes())
        else:
            if self.height_tex is not None:
                self.height_tex.release()
            self.height_tex = self.ctx.texture((w, h), 2, data.tobytes(), dtype="f4")
            self.height_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self.height_tex.repeat_x = self.height_tex.repeat_y = False
        self.hdim = (float(w), float(h))

    def set_topology(self, topo, U, V, size):
        for b in self.bufs:
            b.release()
        self.bufs = []
        self.vaos = {}
        nodes = np.zeros((len(U), 6), np.float32)
        nodes[:, 0] = U
        nodes[:, 1] = V
        nodes[:, 2] = 1.0
        vbo = self.ctx.buffer(nodes.tobytes())
        fmt = [(vbo, "2f 1f 3f", "in_uv", "in_top", "in_nrm")]
        self.bufs.append(vbo)

        def add(name, idx, vb_fmt=None):
            idx = np.ascontiguousarray(idx, dtype=np.uint32).ravel()
            if len(idx) == 0:
                self.counts[name] = 0
                return
            ibo = self.ctx.buffer(idx.tobytes())
            self.bufs.append(ibo)
            self.vaos[name] = self.ctx.vertex_array(self.prog, vb_fmt or fmt, ibo)
            self.counts[name] = len(idx)
        add("front", topo.front)
        add("bottom", topo.bottom)
        # walls: quads (a_top, b_top, b_bottom, a_bottom) with outward normals from the (snapped) edge
        a, b = topo.bedges[:, 0], topo.bedges[:, 1]
        sw, sh = size
        ex = (U[b] - U[a]) * sw
        ey = (V[b] - V[a]) * sh
        ln = np.maximum(np.hypot(ex, ey), 1e-12)
        nxx, nyy = ey / ln, -ex / ln
        n = len(a)
        q = np.zeros((n, 4, 6), np.float32)
        for k, (ids, top) in enumerate(((a, 1), (b, 1), (b, 0), (a, 0))):
            q[:, k, 0] = U[ids]
            q[:, k, 1] = V[ids]
            q[:, k, 2] = top
            q[:, k, 3] = nxx
            q[:, k, 4] = nyy
        if n:
            wvbo = self.ctx.buffer(q.tobytes())
            self.bufs.append(wvbo)
            base = (np.arange(n, dtype=np.uint32) * 4)[:, None]
            widx = base + np.array([1, 0, 3, 1, 3, 2], np.uint32)[None, :]
            add("walls", widx, [(wvbo, "2f 1f 3f", "in_uv", "in_top", "in_nrm")])
        else:
            self.counts["walls"] = 0
        # coarse wireframe (lines)
        ny, nx = topo.cells.shape
        W = nx + 1
        K = max(1, int(round(max(nx, ny) / 90.0)))
        cells = topo.cells
        lines = []
        for j in range(0, ny + 1, K):
            up = cells[min(j, ny - 1)]
            dn = cells[max(j - 1, 0)]
            row = up | dn
            ii = np.flatnonzero(row)
            if len(ii):
                lines.append(np.stack([j * W + ii, j * W + ii + 1], 1))
        for i in range(0, nx + 1, K):
            col = cells[:, min(i, nx - 1)] | cells[:, max(i - 1, 0)]
            jj = np.flatnonzero(col)
            if len(jj):
                lines.append(np.stack([jj * W + i, (jj + 1) * W + i], 1))
        if lines:
            add("wire", np.concatenate(lines))
        self.n_tris = (self.counts.get("front", 0) + self.counts.get("bottom", 0) + self.counts.get("walls", 0)) // 3

    # ------------------------------------------------------------------ framebuffers
    def ensure_fbo(self, w, h):
        w, h = max(8, int(w)), max(8, int(h))
        if self.fbo is not None and self.fbo_size == (w, h):
            return
        for o in (self.fbo, self.fbo_ms, self.color):
            if o is not None:
                o.release()
        self.color = self.ctx.texture((w, h), 4)
        self.color.filter = (moderngl.LINEAR, moderngl.LINEAR)
        depth = self.ctx.depth_renderbuffer((w, h))
        self.fbo = self.ctx.framebuffer([self.color], depth)
        self.fbo_ms = None
        if self.samples > 1:
            try:
                rb = self.ctx.renderbuffer((w, h), 4, samples=self.samples)
                drb = self.ctx.depth_renderbuffer((w, h), samples=self.samples)
                self.fbo_ms = self.ctx.framebuffer([rb], drb)
            except Exception:
                self.samples = 0
                self.fbo_ms = None
        self.fbo_size = (w, h)

    # ------------------------------------------------------------------ drawing
    def render(self, s, fbo=None, size=None, transparent=False, extra_yaw=0.0):
        """s: scene dict (params, view, plate size, depth, orient, time, anim, brush, dims...)."""
        ctx = self.ctx
        if size is None:
            size = self.fbo_size
        w, h = size
        target = fbo if fbo is not None else (self.fbo_ms or self.fbo)
        target.use()
        ctx.viewport = (0, 0, w, h)
        v, p = s["view"], s["params"]
        if transparent:
            ctx.clear(0.0, 0.0, 0.0, 0.0)
        else:
            ctx.clear(v.bg[0], v.bg[1], v.bg[2], 1.0)
            c1 = v.bg2 if v.bg_mode == 0 else v.bg
            ctx.disable(moderngl.DEPTH_TEST)
            _u(self.bgprog, "u_c0", tuple(v.bg))
            _u(self.bgprog, "u_c1", tuple(c1))
            _u(self.bgprog, "u_time", float(s.get("time", 0.0)))
            _u(self.bgprog, "u_anim", 1 if (s.get("anim_bg") and v.bg_mode == 0) else 0)
            _u(self.bgprog, "u_res", (float(w), float(h)))
            self.bg_vao.render(moderngl.TRIANGLES, vertices=3)
        cam = Camera(v, w, h, extra_yaw)
        s["camera"] = cam
        if self.height_tex is None or self.color_tex is None or "front" not in self.vaos:
            return cam
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.CULL_FACE)
        ctx.disable(moderngl.BLEND)
        pr = self.prog
        sw, sh = s["size"]
        _u(pr, "u_mvp", gl_bytes(cam.mvp))
        _u(pr, "u_hdim", self.hdim)
        _u(pr, "u_hscale", float(p.depth))
        _u(pr, "u_thick", float(p.thickness))
        _u(pr, "u_size", (float(sw), float(sh)))
        orient = s["orient"]
        M = orient.matrix_plate_to_src()
        _u(pr, "u_plate2src", np.ascontiguousarray(M.T, np.float32).tobytes())
        _u(pr, "u_srcsize", src_size(orient.src_w, orient.src_h))
        tc, ts, rot = align_params(p, self.tex_size[0], self.tex_size[1], orient.src_w, orient.src_h)
        _u(pr, "u_tc", tc)
        _u(pr, "u_ts", ts)
        _u(pr, "u_rot", rot)
        _u(pr, "u_outcol", tuple(self.outcol))
        _u(pr, "u_mode", int(v.mode))
        _u(pr, "u_mix", float(v.mix))
        _u(pr, "u_unlit", 0 if v.lit else 1)
        phi, th = math.radians(v.light_phi), math.radians(v.light_theta)
        L = np.array([math.cos(th) * math.cos(phi), math.cos(th) * math.sin(phi), math.sin(th)])
        _u(pr, "u_light", tuple(float(x) for x in L))
        _u(pr, "u_cam", tuple(float(x) for x in cam.eye))
        _u(pr, "u_lint", float(v.light_int))
        _u(pr, "u_amb", float(v.ambient))
        _u(pr, "u_specmul", float(v.spec))
        tint, metal, rough = MATERIAL_DEFS.get(v.material, MATERIAL_DEFS["original"])
        _u(pr, "u_tint", tuple(tint))
        _u(pr, "u_metal", float(metal))
        _u(pr, "u_rough", float(rough))
        _u(pr, "u_ao", float(v.ao))
        br = s.get("brush")
        _u(pr, "u_brush", tuple(br) if br else (0.0, 0.0, 0.0, 0.0))
        _u(pr, "u_brushcol", (1.0, 0.45, 0.92))
        _u(pr, "u_env_top", (0.95, 0.90, 1.0))
        _u(pr, "u_env_bot", (0.22, 0.10, 0.30))
        _u(pr, "u_wirecol", (1.0, 0.55, 0.95, 1.0))
        _u(pr, "u_height", 0)
        _u(pr, "u_tex", 1)
        self.height_tex.use(0)
        self.color_tex.use(1)
        _u(pr, "u_kind", 0)
        self.vaos["front"].render(moderngl.TRIANGLES)
        if self.counts.get("walls"):
            _u(pr, "u_kind", 2)
            self.vaos["walls"].render(moderngl.TRIANGLES)
        if self.counts.get("bottom") and cam.eye[2] < 0.05:
            _u(pr, "u_kind", 1)
            self.vaos["bottom"].render(moderngl.TRIANGLES)
        if v.wire and self.counts.get("wire"):
            _u(pr, "u_kind", 3)
            self.vaos["wire"].render(moderngl.LINES)
        self._overlays(s, cam)
        if fbo is None and self.fbo_ms is not None:
            ctx.copy_framebuffer(self.fbo, self.fbo_ms)
        return cam

    def _overlays(self, s, cam):
        v, p = s["view"], s["params"]
        sw, sh = s["size"]
        pts = []

        def seg(a, b, c):
            pts.append((*a, *c))
            pts.append((*b, *c))
        z0 = -float(p.thickness)
        if v.grid:
            step = s.get("grid_step", 0.1)
            ext = max(sw, sh) * 1.0
            n = int(ext / step) + 1
            col = (0.75, 0.45, 1.0, 0.35)
            for k in range(-n, n + 1):
                x = k * step
                seg((x, -n * step, z0 - 0.001), (x, n * step, z0 - 0.001), col)
                seg((-n * step, x, z0 - 0.001), (n * step, x, z0 - 0.001), col)
        if v.axes:
            o = (-sw / 2 - 0.05, -sh / 2 - 0.05, z0)
            L = 0.3
            seg(o, (o[0] + L, o[1], o[2]), (1, .3, .35, 1))
            seg(o, (o[0], o[1] + L, o[2]), (.3, 1, .45, 1))
            seg(o, (o[0], o[1], o[2] + L), (.4, .6, 1, 1))
        if v.dims and s.get("bbox") is not None:
            (x0, y0, za), (x1, y1, zb) = s["bbox"]
            col = (1.0, 0.6, 0.95, 0.95)
            off = 0.04
            seg((x0, y0 - off, za), (x1, y0 - off, za), col)
            seg((x0, y0 - off * 1.5, za), (x0, y0 - off * 0.5, za), col)
            seg((x1, y0 - off * 1.5, za), (x1, y0 - off * 0.5, za), col)
            seg((x1 + off, y0, za), (x1 + off, y1, za), col)
            seg((x1 + off * 0.5, y0, za), (x1 + off * 1.5, y0, za), col)
            seg((x1 + off * 0.5, y1, za), (x1 + off * 1.5, y1, za), col)
            seg((x1 + off, y1 + off, za), (x1 + off, y1 + off, zb), col)
        if not pts:
            return
        arr = np.asarray(pts, np.float32)
        if arr.nbytes > self.line_vbo.size:
            self.line_vbo.orphan(arr.nbytes)
        self.line_vbo.write(arr.tobytes())
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        _u(self.lprog, "u_mvp", gl_bytes(cam.mvp))
        self.line_vao.render(moderngl.LINES, vertices=len(arr))
        self.ctx.disable(moderngl.BLEND)

    # ------------------------------------------------------------------ capture
    def read_image(self, transparent=False):
        comps = 4
        data = self.fbo.read(components=comps, alignment=1)
        img = Image.frombytes("RGBA", self.fbo_size, data).transpose(Image.FLIP_TOP_BOTTOM)
        return img if transparent else img.convert("RGB")

    def render_offscreen(self, s, w, h, transparent=False, extra_yaw=0.0):
        """Render at an arbitrary size (high resolution screenshots, GIF frames)."""
        ctx = self.ctx
        color = ctx.texture((w, h), 4)
        depth = ctx.depth_renderbuffer((w, h))
        fbo = ctx.framebuffer([color], depth)
        ms = None
        try:
            if self.samples > 1:
                ms = ctx.framebuffer([ctx.renderbuffer((w, h), 4, samples=self.samples)],
                                     ctx.depth_renderbuffer((w, h), samples=self.samples))
        except Exception:
            ms = None
        self.render(s, fbo=ms or fbo, size=(w, h), transparent=transparent, extra_yaw=extra_yaw)
        if ms is not None:
            ctx.copy_framebuffer(fbo, ms)
        data = fbo.read(components=4, alignment=1)
        img = Image.frombytes("RGBA", (w, h), data).transpose(Image.FLIP_TOP_BOTTOM)
        for o in (fbo, color, depth) + ((ms,) if ms else ()):
            o.release()
        return img if transparent else img.convert("RGB")
