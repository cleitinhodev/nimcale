# SPDX-License-Identifier: GPL-3.0-or-later
"""Texture alignment (texture -> source height map) and texture baking in plate uv space."""
import math

import numpy as np
from PIL import Image

from nimcale.core.images import fit_base_scale


def src_size(hm_w, hm_h):
    m = float(max(hm_w, hm_h))
    return hm_w / m, hm_h / m


def align_params(p, tex_w, tex_h, hm_w, hm_h):
    """(tc, ts, rot): centre (source uv), total scale, rotation (radians)."""
    ss = src_size(hm_w, hm_h)
    bx, by = fit_base_scale(p.fit, tex_w / float(tex_h), ss[0] / ss[1])
    return (0.5 + p.ox, 0.5 + p.oy), (bx * p.sx, by * p.sy), math.radians(p.rot)


def plate_uv_to_tex_uv(pu, pv, p, orient, tex_w, tex_h):
    M = orient.matrix_plate_to_src()
    su = M[0, 0] * pu + M[0, 1] * pv + M[0, 2]
    sv = M[1, 0] * pu + M[1, 1] * pv + M[1, 2]
    ss = src_size(orient.src_w, orient.src_h)
    tc, ts, rot = align_params(p, tex_w, tex_h, orient.src_w, orient.src_h)
    px = (su - tc[0]) * ss[0]
    py = (sv - tc[1]) * ss[1]
    c, s = math.cos(rot), math.sin(rot)
    qx = c * px + s * py
    qy = -s * px + c * py
    return qx / (ss[0] * ts[0]) + 0.5, qy / (ss[1] * ts[1]) + 0.5


def bake_texture(tex, p, orient, long_side=2048, outcol=(1, 1, 1), hf=None, mix=0.0):
    """Texture resampled in plate uv space (what the 3D model shows). Returns PIL RGB."""
    img = tex.img if hasattr(tex, "img") else tex
    tw, th = img.size
    arr = np.asarray(img, dtype=np.float32) / 255.0
    sw, sh = orient.size
    ow = max(16, int(round(long_side * sw / max(sw, sh))))
    oh = max(16, int(round(long_side * sh / max(sw, sh))))
    u = (np.arange(ow, dtype=np.float64) + 0.5) / ow
    v = 1.0 - (np.arange(oh, dtype=np.float64) + 0.5) / oh
    U, V = np.meshgrid(u, v)
    tu, tv = plate_uv_to_tex_uv(U, V, p, orient, tw, th)
    x = np.clip(tu * tw - 0.5, 0, tw - 1)
    y = np.clip((1.0 - tv) * th - 0.5, 0, th - 1)
    x0 = np.floor(x).astype(np.int32); y0 = np.floor(y).astype(np.int32)
    x1 = np.minimum(x0 + 1, tw - 1); y1 = np.minimum(y0 + 1, th - 1)
    fx = (x - x0)[..., None].astype(np.float32); fy = (y - y0)[..., None].astype(np.float32)
    col = (arr[y0, x0] * (1 - fx) + arr[y0, x1] * fx) * (1 - fy) + (arr[y1, x0] * (1 - fx) + arr[y1, x1] * fx) * fy
    od = np.maximum(np.maximum(-tu, tu - 1.0), np.maximum(-tv, tv - 1.0))
    t = np.clip(od / 0.03, 0, 1)
    w = (t * t * (3 - 2 * t))[..., None].astype(np.float32)
    col = col * (1 - w) + np.asarray(outcol, dtype=np.float32)[None, None, :] * w
    if hf is not None and mix > 0.0:
        from nimcale.core.images import resize_field
        g = resize_field(np.clip(hf, 0, 1), (ow, oh), "bilinear")[::-1][..., None]
        col = col * (1 - mix) + g * mix
    return Image.fromarray((np.clip(col, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


def auto_align(tex, hm_work, p, orient_src_w, orient_src_h, iters=60):
    """Refine sx, sy, ox, oy by maximising edge correlation between texture and height map."""
    from scipy import ndimage as ndi, optimize
    N = 256
    img = tex.img if hasattr(tex, "img") else tex
    t = np.asarray(img.convert("L").resize((N, N), Image.LANCZOS), dtype=np.float32) / 255.0
    hm = np.asarray(Image.fromarray(hm_work, "F").resize((N, N), Image.BILINEAR), dtype=np.float32)

    def edges(a):
        a = ndi.gaussian_filter(a, 1.5)
        return np.hypot(ndi.sobel(a, 0), ndi.sobel(a, 1))
    et, eh = edges(t), edges(hm)
    tw, th = img.size
    ss = src_size(orient_src_w, orient_src_h)
    yy, xx = np.mgrid[0:N, 0:N]
    su = (xx + 0.5) / N
    sv = 1.0 - (yy + 0.5) / N
    q = p.copy()

    def cost(x):
        q.sx, q.sy, q.ox, q.oy = x
        tc, ts, rot = align_params(q, tw, th, orient_src_w, orient_src_h)
        px = (su - tc[0]) * ss[0]; py = (sv - tc[1]) * ss[1]
        c, s = math.cos(rot), math.sin(rot)
        tu = (c * px + s * py) / (ss[0] * ts[0]) + 0.5
        tv = (-s * px + c * py) / (ss[1] * ts[1]) + 0.5
        w = ndi.map_coordinates(et, [(1 - tv) * N - 0.5, tu * N - 0.5], order=1, mode="constant")
        a = w.ravel(); b = eh.ravel()
        sa, sb = a.std(), b.std()
        if sa < 1e-9 or sb < 1e-9:
            return 0.0
        return -float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))
    x0 = [p.sx, p.sy, p.ox, p.oy]
    c0 = cost(x0)
    res = optimize.minimize(cost, x0, method="Nelder-Mead",
                            options=dict(maxiter=iters * 4, xatol=1e-4, fatol=1e-6))
    if res.fun < c0:
        return tuple(float(v) for v in res.x), -res.fun
    return tuple(x0), -c0
