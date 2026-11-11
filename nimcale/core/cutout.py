# SPDX-License-Identifier: GPL-3.0-or-later
"""Automatic object outline ("auto" cutout): where is the object, where is the background?

The mask is computed in source-image space (row 0 = top) at the working or HD resolution from:

* the height map (levels-adjusted) against its background: dark, white, transparent (alpha) or a
  picked colour, with ``threshold`` as the distance / tolerance from the background;
* or the texture, aligned onto the height map: its alpha channel, or a colour key.

It is then cleaned: smoothing, closing, hole filling, removal of small islands, optionally only the
largest object, and grown / shrunk by a number of pixels. All pixel sizes are in pixels of the original
height map, so the result is the same in the preview and in the HD export.
"""
import math

import numpy as np
from scipy import ndimage as ndi

SOURCES = ("auto", "height", "tex_alpha", "tex_color")
BG_MODES = ("auto", "dark", "white", "transparent", "color")


# ---------------------------------------------------------------------------- texture in source space
def texture_in_source(tex, p, w, h, src_w, src_h):
    """Texture (RGB 0..1 float, alpha 0..1 or None) resampled onto a (h, w) source-image grid.

    Outside the texture: rgb = NaN, alpha = 0."""
    from nimcale.core.align import align_params, src_size
    img = tex.img
    tw, th = img.size
    arr = np.asarray(img, dtype=np.float32) / 255.0
    al = np.asarray(tex.alpha, dtype=np.float32) / 255.0 if getattr(tex, "alpha", None) is not None else None
    su = (np.arange(w, dtype=np.float64) + 0.5) / w
    sv = 1.0 - (np.arange(h, dtype=np.float64) + 0.5) / h
    SU, SV = np.meshgrid(su, sv)
    ss = src_size(src_w, src_h)
    tc, ts, rot = align_params(p, tw, th, src_w, src_h)
    px = (SU - tc[0]) * ss[0]
    py = (SV - tc[1]) * ss[1]
    c, s = math.cos(rot), math.sin(rot)
    tu = (c * px + s * py) / (ss[0] * ts[0]) + 0.5
    tv = (-s * px + c * py) / (ss[1] * ts[1]) + 0.5
    inside = (tu >= 0) & (tu <= 1) & (tv >= 0) & (tv <= 1)
    x = np.clip(np.rint(tu * tw - 0.5), 0, tw - 1).astype(np.int32)
    y = np.clip(np.rint((1.0 - tv) * th - 0.5), 0, th - 1).astype(np.int32)
    rgb = arr[y, x]
    rgb[~inside] = np.nan
    alpha = None
    if al is not None:
        ah, aw = al.shape[:2]
        ax = np.clip(np.rint(tu * aw - 0.5), 0, aw - 1).astype(np.int32)
        ay = np.clip(np.rint((1.0 - tv) * ah - 0.5), 0, ah - 1).astype(np.int32)
        alpha = al[ay, ax]
        alpha[~inside] = 0.0
    return rgb, alpha


# ---------------------------------------------------------------------------- background detection
def border_values(a):
    return np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]], axis=0)


def detect_height_background(g, alpha):
    """'transparent' | 'white' | 'dark' for a levels-adjusted height map g (0..1)."""
    if alpha is not None and float(alpha.min()) < 0.5 and float((alpha < 0.5).mean()) > 0.01:
        return "transparent"
    b = border_values(g)
    return "white" if float(np.median(b)) > 0.55 else "dark"


def bg_rgb(p):
    return np.array([p.bg_r, p.bg_g, p.bg_b], dtype=np.float32)


def luminance(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def resolve_source(p, hm_alpha, tex):
    src = p.outline_src if p.outline_src in SOURCES else "auto"
    if src == "auto":
        if hm_alpha is not None and float(hm_alpha.min()) < 0.5:
            return "height"
        if tex is not None and getattr(tex, "alpha", None) is not None:
            return "tex_alpha"
        return "height"
    if src in ("tex_alpha", "tex_color") and tex is None:
        return "height"
    if src == "tex_alpha" and getattr(tex, "alpha", None) is None:
        return "tex_color"
    return src


def raw_mask(g, p, hm_alpha=None, tex=None, src_wh=None):
    """Boolean object mask before cleaning + info dict (source, background actually used)."""
    h, w = g.shape
    src = resolve_source(p, hm_alpha, tex)
    thr = float(p.threshold)
    info = {"source": src}
    if src == "height":
        mode = p.bg_mode if p.bg_mode in BG_MODES else "auto"
        if mode == "auto":
            mode = detect_height_background(g, hm_alpha)
        if mode == "transparent" and hm_alpha is None:
            mode = "dark"
        info["bg"] = mode
        if mode == "transparent":
            m = hm_alpha > 0.5
        elif mode == "white":
            m = g < 1.0 - thr
        elif mode == "color":
            m = np.abs(g - float(luminance(bg_rgb(p)))) > thr
        else:
            m = g > thr
        return m, info
    sw, sh = src_wh if src_wh else (w, h)
    rgb, alpha = texture_in_source(tex, p, w, h, sw, sh)
    if src == "tex_alpha":
        info["bg"] = "transparent"
        return alpha > 0.5, info
    # colour key: distance from the background colour (picked, or the texture border colour)
    valid = ~np.isnan(rgb[..., 0])
    if p.bg_mode == "color":
        key = bg_rgb(p)
        info["bg"] = "color"
    else:
        from nimcale.core.images import border_color
        key = np.asarray(border_color(tex.img), dtype=np.float32)
        info["bg"] = "border"
    d = np.sqrt(((np.nan_to_num(rgb) - key[None, None, :]) ** 2).sum(-1) / 3.0)
    return (d > thr) & valid, info


def clean_mask(m, p, px_scale):
    """Smoothing, closing, holes, islands, largest object, grow / shrink (pixel sizes in original px)."""
    if not m.any():
        return m
    px = max(1e-6, float(px_scale))
    if p.mask_smooth > 0.05:
        m = ndi.gaussian_filter(m.astype(np.float32), p.mask_smooth * px) > 0.5
        if not m.any():
            return m
    r = max(1, int(round(2 * max(1.0, px))))
    st = ndi.generate_binary_structure(2, 1)
    m = ndi.binary_closing(np.pad(m, r + 1), structure=st, iterations=r)[r + 1:-r - 1, r + 1:-r - 1]
    if p.fill_holes:
        m = ndi.binary_fill_holes(m)
    lab, n = ndi.label(m)
    if n > 1:
        sizes = ndi.sum(m, lab, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, bool)
        if p.keep_largest:
            keep[1 + int(np.argmax(sizes))] = True
        else:
            keep[1:] = sizes >= max(4, p.min_island / 100.0 * m.size)
            if not keep.any():
                keep[1 + int(np.argmax(sizes))] = True
        m = keep[lab]
    g = p.mask_grow * px
    if g > 0.25:
        m = ndi.distance_transform_edt(~m) <= g
    elif g < -0.25:
        m2 = ndi.distance_transform_edt(m) > -g
        m = m2 if m2.any() else m
    return m


def object_mask(g, p, px_scale, hm_alpha=None, tex=None, src_wh=None):
    """Cleaned object mask (source-image space) + info."""
    m, info = raw_mask(g, p, hm_alpha, tex, src_wh)
    m = clean_mask(m, p, px_scale)
    info["coverage"] = float(m.mean()) if m.size else 0.0
    if not m.any():
        info["empty"] = True
    return m, info
