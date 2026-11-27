# SPDX-License-Identifier: GPL-3.0-or-later
"""Back side ("Verso") of the plate / coin.

The back is described as a second height field `zb` (absolute z of the bottom surface, plate units, same grid
as the front field) plus optional through holes. The solid stays a single closed surface:
front grid + side walls + back grid (see core/mesh.build_solid), so every back mode is watertight by
construction as long as zb < front everywhere (enforced here with a minimum material gap).

Modes (bk_mode): flat (the classic flat back, default), mirror (two-faced coin: mirrored front relief),
coin2 (heads and tails: own back image, falls back to the front), hollow (shell with rim and roof),
ribs (hollow with a square grid / honeycomb / line ribs).
Add-ons usable with every mode: keychain hole, magnet recess, keyhole hanger recess, engraved / embossed text,
stand (flat cut + wedge), chamfer of the back edge.
Feature positions (bk_*_x / bk_*_y) are given as seen from the back (x = -X of the plate).
"""
import math
import os

import numpy as np
from scipy import ndimage as ndi

from nimcale.core import shapes

BACK_MODES = ("flat", "mirror", "coin2", "hollow", "ribs")
RIB_PATTERNS = ("grid", "honeycomb", "lines")
TEXT_MODES = ("engrave", "emboss")
KEYS = ("bk_mode", "bk_depth", "bk_invert", "bk_wall", "bk_top", "bk_ribs", "bk_cell", "bk_rib", "bk_rib_angle",
        "bk_hole", "bk_hole_x", "bk_hole_y", "bk_hole_d",
        "bk_magnet", "bk_mag_x", "bk_mag_y", "bk_mag_d", "bk_mag_depth",
        "bk_hang", "bk_hang_x", "bk_hang_y", "bk_hang_d", "bk_hang_slot", "bk_hang_len", "bk_hang_depth",
        "bk_text", "bk_text_mode", "bk_text_size", "bk_text_depth", "bk_text_x", "bk_text_y", "bk_text_rot",
        "bk_stand", "bk_stand_cut", "bk_stand_depth", "bk_stand_h", "bk_chamfer",
        # the back depends on these model values too
        "depth", "thickness", "size_mm", "blur")
MIN_GAP_MM = 0.4          # material always left between a back pocket and the front surface


def is_active(p):
    return (p.bk_mode != "flat" or p.bk_hole or p.bk_magnet or p.bk_hang or bool(p.bk_text.strip())
            or p.bk_stand or p.bk_chamfer > 1e-4)


def uses_back_image(p):
    return p.bk_mode == "coin2"


class BackResult:
    def __init__(self, zb, sdf, holes, info):
        self.zb = zb            # absolute z of the back surface (plate units), shape of the front field
        self.sdf = sdf          # outline (may be cut flat by the stand)
        self.holes = holes      # > 0 outside the through holes (None = no hole)
        self.info = info


def _sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0) if e1 != e0 else (x >= e0).astype(np.float32)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def _font_path():
    from nimcale import paths
    return paths.asset("fonts", "NimcaleSans-Bold.ttf")


def text_mask(text, h, w, size, mm, p):
    """Anti-aliased text mask (0..1) in plate convention, mirrored so it reads correctly from the back."""
    from PIL import Image, ImageDraw, ImageFont
    sw, sh = size
    px_per_unit = (w - 1) / float(sw)
    px_per_mm = px_per_unit / mm
    font_px = max(4, int(round(p.bk_text_size * px_per_mm * 1.36)))     # cap height ~ text size
    ss = 1 if font_px > 40 else 2                                          # supersample tiny text
    try:
        font = ImageFont.truetype(_font_path(), font_px * ss)
    except Exception:
        font = ImageFont.load_default()
    lines = p.bk_text.replace("\\n", "\n").split("\n")
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    boxes = [probe.textbbox((0, 0), ln or " ", font=font) for ln in lines]
    lh = int(font_px * ss * 1.18)
    tw = max(b[2] - b[0] for b in boxes) + 8 * ss
    th = lh * len(lines) + 8 * ss
    im = Image.new("L", (tw, th), 0)
    d = ImageDraw.Draw(im)
    for i, (ln, b) in enumerate(zip(lines, boxes)):
        d.text(((tw - (b[2] - b[0])) / 2 - b[0], 4 * ss + i * lh), ln, fill=255, font=font)
    if abs(p.bk_text_rot) > 0.01:
        im = im.rotate(p.bk_text_rot, resample=Image.BICUBIC, expand=True)
    if ss > 1:
        im = im.resize((max(1, im.size[0] // ss), max(1, im.size[1] // ss)), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float32) / 255.0          # image convention (row 0 = top), as seen from back
    canvas = np.zeros((h, w), np.float32)
    # centre in pixels of the back view: back x = -X  ->  column of the mirrored field
    cx = (0.5 + p.bk_text_x / sw) * (w - 1)
    cy = (0.5 - p.bk_text_y / sh) * (h - 1)
    ih, iw = a.shape
    x0 = int(round(cx - iw / 2.0)); y0 = int(round(cy - ih / 2.0))
    xs0, ys0 = max(0, x0), max(0, y0)
    xs1, ys1 = min(w, x0 + iw), min(h, y0 + ih)
    if xs1 > xs0 and ys1 > ys0:
        canvas[ys0:ys1, xs0:xs1] = a[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
    # canvas is the back view in image convention -> plate convention (flip rows) and back -> plate (flip cols)
    return canvas[::-1, ::-1].copy()


def rib_distance(XB, Y, p, u):
    """Distance (plate units) from each point to the nearest rib centre line."""
    c = max(0.5, p.bk_cell) * u
    a = math.radians(p.bk_rib_angle)
    ca, sa = math.cos(a), math.sin(a)
    x = XB * ca + Y * sa
    y = -XB * sa + Y * ca
    if p.bk_ribs == "lines":
        return np.abs(y / c - np.round(y / c)) * c
    if p.bk_ribs == "honeycomb":
        q = np.stack([x / c, y / c], -1)                      # hexagons with inradius 0.5 (cell = across flats)
        s = np.array([1.0, math.sqrt(3.0)])
        hh = s * 0.5
        A = np.mod(q, s) - hh
        B = np.mod(q - hh, s) - hh
        g = np.where((np.sum(A * A, -1) < np.sum(B * B, -1))[..., None], A, B)
        ag = np.abs(g)
        hexd = np.maximum(ag[..., 0] * 0.5 + ag[..., 1] * (math.sqrt(3.0) / 2.0), ag[..., 0])
        return np.maximum(0.0, 0.5 - hexd) * c
    gx = np.abs(x / c - np.round(x / c)) * c
    gy = np.abs(y / c - np.round(y / c)) * c
    return np.minimum(gx, gy)


def keyhole_sdf(XB, Y, p, u):
    """Signed distance (< 0 inside) of a keyhole: head circle + slot going up to a rounded end."""
    r1 = max(0.5, p.bk_hang_d) * 0.5 * u
    r2 = max(0.3, min(p.bk_hang_slot, p.bk_hang_d)) * 0.5 * u
    L = max(0.0, p.bk_hang_len) * u
    x = XB - p.bk_hang_x
    y = Y - p.bk_hang_y
    d1 = np.hypot(x, y) - r1
    yy = np.clip(y, 0.0, L)
    d2 = np.hypot(x, y - yy) - r2
    return np.minimum(d1, d2)


def back_image_field(back_hm, h, w, p):
    """Back relief from its own height map (image convention) -> plate convention, mirrored, 0..1."""
    from nimcale.core.images import resize_field
    g = resize_field(np.clip(back_hm.work, 0.0, 1.0), (w, h), "bilinear")
    if p.blur > 0.05:
        px = w / float(max(1, back_hm.orig_size[0]))
        g = ndi.gaussian_filter(g, p.blur * px, mode="nearest")
    if p.bk_invert:
        g = 1.0 - g
    return np.ascontiguousarray(g[::-1, ::-1], dtype=np.float32)


def compute(res, p, back_hm=None):
    """BackResult for a pipeline Result (front field hf, outline sdf, plate size)."""
    hf, sdf = res.hf, res.sdf
    h, w = hf.shape
    size = res.size
    sw, sh = size
    mm = max(1e-6, p.size_mm)
    u = 1.0 / mm                                   # plate units per millimetre
    X, Y = shapes.plate_coords(h, w, size)
    X = np.asarray(X, np.float32); Y = np.asarray(Y, np.float32)
    XB = -X                                        # x as seen from the back
    cell = max(sw / max(1, w - 1), sh / max(1, h - 1))
    e = 1.2 * cell                                 # anti-aliasing width of every step
    info = {}
    zf = hf.astype(np.float32) * np.float32(p.depth)
    thick = float(p.thickness)
    # ---- outline: the stand cuts the bottom of the outline flat so the piece stands upright
    out = sdf
    inside = sdf > 0
    if p.bk_stand and inside.any():
        rows = np.flatnonzero(inside.any(1))
        ymin = float(Y[rows[0], 0])
        ycut = ymin + max(0.0, p.bk_stand_cut) * u
        out = np.minimum(sdf, (Y - ycut)).astype(np.float32)
        if not (out > 0).any():
            out = sdf
        info["stand_y"] = ycut
    raise_ = np.zeros((h, w), np.float32)          # pockets (back surface moves up into the solid)
    prot = np.zeros((h, w), np.float32)            # protrusions (back surface moves down)
    edge = _sstep(0.0, 2.0 * e, out)
    # ---- two-faced modes
    if p.bk_mode == "mirror" or (p.bk_mode == "coin2" and back_hm is None):
        g = hf[:, ::-1] * _sstep(0.0, 2.0 * e, sdf[:, ::-1])
        prot += np.float32(p.bk_depth) * g * edge
    elif p.bk_mode == "coin2":
        g = back_image_field(back_hm, h, w, p)
        prot += np.float32(p.bk_depth) * g * edge
    # ---- hollow shell / ribs
    if p.bk_mode in ("hollow", "ribs"):
        inner = out - max(0.2, p.bk_wall) * u
        pm = _sstep(0.0, e, inner)
        sigma = max(1.0, 1.5 * u / cell)            # roof follows the front, smoothed (~1.5 mm)
        roof = ndi.gaussian_filter(zf, sigma, mode="nearest") - max(0.2, p.bk_top) * u
        roof = np.minimum(roof, ndi.minimum_filter(zf, size=3) - max(0.2, p.bk_top) * u)
        pocket = np.maximum(0.0, roof + thick).astype(np.float32)
        if p.bk_mode == "ribs":
            d = rib_distance(XB, Y, p, u)
            half = max(0.2, p.bk_rib) * 0.5 * u
            pm = pm * _sstep(half, half + e, d)
        raise_ = np.maximum(raise_, pm * pocket)
    # ---- recesses
    if p.bk_magnet:
        r = max(0.5, p.bk_mag_d) * 0.5 * u
        dd = np.hypot(XB - p.bk_mag_x, Y - p.bk_mag_y) - r
        raise_ = np.maximum(raise_, _sstep(e, -e, dd) * np.float32(max(0.0, p.bk_mag_depth) * u))
    if p.bk_hang:
        dd = keyhole_sdf(XB, Y, p, u)
        raise_ = np.maximum(raise_, _sstep(e, -e, dd) * np.float32(max(0.0, p.bk_hang_depth) * u))
    if p.bk_text.strip():
        m = text_mask(p.bk_text, h, w, size, mm, p)
        if m.any():
            if p.bk_text_mode == "emboss":
                prot = prot + m * np.float32(max(0.0, p.bk_text_depth) * u) * edge
            else:
                raise_ = np.maximum(raise_, m * np.float32(max(0.0, p.bk_text_depth) * u))
    # ---- stand wedge: thicker towards the bottom edge, so the piece has a deep footprint
    if p.bk_stand and "stand_y" in info:
        y0 = info["stand_y"]
        y1 = y0 + max(1.0, p.bk_stand_h) * u
        t = np.clip((y1 - Y) / max(1e-6, y1 - y0), 0.0, 1.0)
        prot = prot + (t * np.float32(max(0.0, p.bk_stand_depth) * u)).astype(np.float32)
    # ---- chamfer of the back edge (45 degrees)
    if p.bk_chamfer > 1e-4:
        c = p.bk_chamfer * u
        raise_ = raise_ + np.clip(c - np.maximum(out, 0.0), 0.0, c).astype(np.float32)
    zb = (-thick + raise_ - prot).astype(np.float32)
    gap = MIN_GAP_MM * u
    lim = zf - gap
    clamped = zb > lim
    ins = out > 0
    info["clamped"] = float(np.count_nonzero(clamped & ins)) / max(1, np.count_nonzero(ins))
    zb = np.minimum(zb, lim).astype(np.float32)
    holes = None
    if p.bk_hole:
        r = max(0.5, p.bk_hole_d) * 0.5 * u
        holes = (np.hypot(XB - p.bk_hole_x, Y - p.bk_hole_y) - r).astype(np.float32)
        if not (holes > 0).any():
            holes = None
    info["zmin"] = float(zb[ins].min()) if ins.any() else -thick
    info["pocket_max_mm"] = float((zb[ins] + thick).max() / u) if ins.any() else 0.0
    return BackResult(zb, out.astype(np.float32, copy=False), holes, info)


def back_bake(p, front_bake, back_tex=None):
    """Texture of the back in plate-u order (what you see from behind, mirrored onto the plate grid),
    or None when the back has no colours of its own (flat / pockets: the front texture shows through)."""
    from PIL import Image
    if p.bk_mode == "mirror" or (p.bk_mode == "coin2" and back_tex is None):
        return front_bake.transpose(Image.FLIP_LEFT_RIGHT)
    if p.bk_mode == "coin2":
        img = back_tex.img if hasattr(back_tex, "img") else back_tex
        return img.convert("RGB").resize(front_bake.size, Image.LANCZOS).transpose(Image.FLIP_LEFT_RIGHT)
    return None


def back_texture_atlas(front_img, back_img):
    """Front and back textures side by side (front | back). back_img is already in plate-u order."""
    from PIL import Image
    w, h = front_img.size
    b = back_img.convert("RGB").resize((w, h), Image.LANCZOS)
    atlas = Image.new("RGB", (w * 2, h))
    atlas.paste(front_img.convert("RGB"), (0, 0))
    atlas.paste(b, (w, 0))
    return atlas


def default_positions(p, res):
    """Sensible positions (as seen from the back) for the hole / magnet / hanger / text inside the outline."""
    sdf = res.sdf
    h, w = sdf.shape
    X, Y = shapes.plate_coords(h, w, res.size)
    ins = sdf > 0
    if not ins.any():
        return
    ys = np.asarray(Y)[ins]; xs = -np.asarray(X)[ins]
    cx = float((xs.min() + xs.max()) / 2.0)
    cy = float((ys.min() + ys.max()) / 2.0)
    top = float(ys.max())
    u = 1.0 / max(1e-6, p.size_mm)
    p.bk_hole_x = cx
    p.bk_hole_y = top - (p.bk_hole_d * 0.5 + 2.5) * u
    p.bk_mag_x, p.bk_mag_y = cx, cy
    p.bk_hang_x = cx
    p.bk_hang_y = top - (p.bk_hang_d * 0.5 + p.bk_hang_len + 4.0) * u
    p.bk_text_x, p.bk_text_y = cx, cy - 0.45 * (top - cy)
