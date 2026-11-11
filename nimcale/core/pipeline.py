# SPDX-License-Identifier: GPL-3.0-or-later
"""Height pipeline: source height map + parameters (+ sculpt layer) -> final plate height field."""
import numpy as np
from scipy import ndimage as ndi

from nimcale.core.images import resize_field
from nimcale.core.orient import Orient
from nimcale.core import shapes


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / max(1e-9, (e1 - e0)), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def fbm(h, w, scale, seed, octaves=4):
    """Fractal value noise in [-1, 1], resolution independent (same lattice for any h, w)."""
    rng = np.random.default_rng(int(seed))
    asp = w / float(max(1, h))
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = max(2.0, scale * (2 ** o))
        gx = int(round(n * (asp if asp >= 1 else 1.0))) + 3
        gy = int(round(n * (1.0 / asp if asp < 1 else 1.0))) + 3
        lat = rng.random((gy, gx), dtype=np.float32) * 2.0 - 1.0
        out += amp * resize_field(lat, (w, h), "bicubic")
        tot += amp
        amp *= 0.5
    return out / tot


def adjust_levels(g, p):
    if p.level_lo != 0.0 or p.level_hi != 1.0:
        lo, hi = p.level_lo, max(p.level_lo + 1e-3, p.level_hi)
        g = np.clip((g - lo) / (hi - lo), 0.0, 1.0)
    if abs(p.gamma - 1.0) > 1e-4:
        g = np.power(np.clip(g, 0.0, 1.0), p.gamma)
    if p.brightness != 0.0 or p.contrast != 1.0:
        g = np.clip((g - 0.5) * p.contrast + 0.5 + p.brightness, 0.0, 1.0)
    return g.astype(np.float32, copy=False)


class Result:
    def __init__(self, hf, sdf, orient, mask_plate=None):
        self.hf = hf                 # plate convention (row 0 = v 0), relief units (0..1 nominal)
        self.sdf = sdf               # plate units, > 0 inside the outline
        self.orient = orient
        self.size = orient.size
        self.mask_plate = mask_plate

    @property
    def shape(self):
        return self.hf.shape


class Pipeline:
    """Cached height pipeline. compute() for the interactive preview, compute_hd() for exports."""

    SRC_KEYS = ("level_lo", "level_hi", "gamma", "brightness", "contrast", "invert", "threshold",
                "blur", "detail", "detail_radius", "noise_amp", "noise_scale", "noise_seed")
    ORIENT_KEYS = ("crop_l", "crop_r", "crop_t", "crop_b", "rot90", "flip_x", "flip_y")
    SHAPE_KEYS = ("cutout", "shape", "shape_cx", "shape_cy", "shape_rx", "shape_ry", "shape_round", "shape_rot")
    EDGE_KEYS = ("rim_width", "rim_height", "bevel")

    def __init__(self):
        self.cache = {}

    def clear(self):
        self.cache.clear()

    @staticmethod
    def _k(p, keys):
        return tuple(getattr(p, k) for k in keys)

    # ------------------------------------------------------------------ source space
    def source_stage(self, raw, p, px_scale, need_mask):
        """raw: image-convention array at the target resolution. px_scale = pixels per original pixel."""
        g = adjust_levels(raw, p)
        mask = None
        if need_mask or p.invert:
            mask = shapes.clean_object_mask(g > p.threshold, close_px=2 * max(1.0, px_scale))
        if p.invert:
            g = ((1.0 - g) * mask).astype(np.float32)
        if p.blur > 0.05:
            g = ndi.gaussian_filter(g, p.blur * px_scale, mode="nearest").astype(np.float32)
        if p.detail > 0.001:
            gb = ndi.gaussian_filter(g, max(0.5, p.detail_radius * px_scale), mode="nearest")
            g = (g + p.detail * (g - gb)).astype(np.float32)
        if p.noise_amp > 0.0005:
            h, w = g.shape
            g = (g + p.noise_amp * fbm(h, w, p.noise_scale, p.noise_seed)).astype(np.float32)
        return g, mask

    # ------------------------------------------------------------------ plate space
    @staticmethod
    def plate_stage(g, mask, p, o):
        hp = o.apply(g)
        h, w = hp.shape
        mask_p = o.apply(mask) if mask is not None else None
        if p.cutout and p.shape == "auto":
            sdf = shapes.mask_sdf(mask_p if mask_p is not None else np.ones_like(hp, bool), o.size)
        else:
            X, Y = shapes.plate_coords(h, w, o.size)
            sdf = shapes.shape_sdf(p, X, Y, o.size)
        hp = Pipeline.edge_stage(hp, sdf, p)
        return hp, sdf, mask_p

    @staticmethod
    def edge_stage(hp, sdf, p):
        if p.bevel > 1e-4:
            hp = hp * smoothstep(0.0, p.bevel, sdf)
        if p.rim_width > 1e-4 and abs(p.rim_height) > 1e-4:
            prof = p.rim_height * (1.0 - smoothstep(p.rim_width * 0.55, p.rim_width, sdf))
            hp = np.maximum(hp, prof) if p.rim_height > 0 else hp + prof
        return np.clip(hp, 0.0, 4.0).astype(np.float32)

    # ------------------------------------------------------------------ preview
    def compute(self, hm, p, sculpt=None, sculpt_rev=0):
        need_mask = p.cutout and p.shape == "auto"
        kA = (id(hm), self._k(p, self.SRC_KEYS), need_mask)
        c = self.cache
        if c.get("kA") != kA:
            px = hm.work.shape[1] / float(max(1, hm.orig_size[0]))
            c["gA"], c["mask"] = self.source_stage(hm.work, p, px, need_mask)
            c["kA"] = kA
            c.pop("kS", None)
        kS = (kA, id(sculpt), sculpt_rev)
        if c.get("kS") != kS:
            c["gS"] = c["gA"] + sculpt if sculpt is not None else c["gA"]
            c["kS"] = kS
            c.pop("kP", None)
        kP = (kS, self._k(p, self.ORIENT_KEYS), self._k(p, self.SHAPE_KEYS), self._k(p, self.EDGE_KEYS))
        if c.get("kP") != kP:
            h, w = c["gS"].shape
            o = Orient(p, w, h)
            kO = (kA, self._k(p, self.ORIENT_KEYS), self._k(p, self.SHAPE_KEYS))
            if c.get("kO") != kO:
                hp = o.apply(c["gS"])
                mask_p = o.apply(c["mask"]) if c["mask"] is not None else None
                if p.cutout and p.shape == "auto":
                    sdf = shapes.mask_sdf(mask_p if mask_p is not None else np.ones_like(hp, bool), o.size)
                else:
                    X, Y = shapes.plate_coords(hp.shape[0], hp.shape[1], o.size)
                    sdf = shapes.shape_sdf(p, X, Y, o.size)
                c["sdf"], c["mask_p"], c["kO"] = sdf, mask_p, kO
            else:
                hp = o.apply(c["gS"])
            hf = self.edge_stage(hp, c["sdf"], p)
            c["res"] = Result(hf, c["sdf"], o, c["mask_p"])
            c["kP"] = kP
            c["rev"] = c.get("rev", 0) + 1
        return c["res"]

    @property
    def revision(self):
        return self.cache.get("rev", 0)

    # ------------------------------------------------------------------ HD export
    @staticmethod
    def hd_source_dims(hm, p, longest_nodes):
        """Source resolution (w, h) such that the plate's longest side has ~longest_nodes samples."""
        h0, w0 = hm.work.shape
        o = Orient(p, w0, h0)
        ph, pw = o.plate_shape(h0, w0)
        f = float(longest_nodes) / float(max(ph, pw))
        return max(8, int(round(w0 * f))), max(8, int(round(h0 * f))), f

    def compute_hd(self, hm, p, longest_nodes, sculpt=None, method="bicubic"):
        w, h, f = self.hd_source_dims(hm, p, longest_nodes)
        fh, fw = hm.full.shape
        if abs(f - 1.0) < 1e-6:
            raw = hm.work
        elif fw >= w:
            raw = resize_field(hm.full, (w, h), "lanczos" if fw > w else "box")
        else:
            raw = resize_field(hm.full, (w, h), method)
        raw = np.clip(raw, 0.0, 1.0)
        px = w / float(max(1, hm.orig_size[0]))
        need_mask = p.cutout and p.shape == "auto"
        g, mask = self.source_stage(raw, p, px, need_mask)
        if sculpt is not None:
            g = g + (sculpt if sculpt.shape == g.shape else resize_field(sculpt, (w, h), method))
        o = Orient(p, w, h)
        hp, sdf, mask_p = self.plate_stage(g, mask, p, o)
        return Result(hp, sdf, o, mask_p)


def object_mask_plate(hm, p):
    """Cleaned threshold mask of the object in plate convention (for shape fitting)."""
    px = hm.work.shape[1] / float(max(1, hm.orig_size[0]))
    g = adjust_levels(hm.work, p)
    m = shapes.clean_object_mask(g > p.threshold, close_px=2 * max(1.0, px))
    h, w = m.shape
    o = Orient(p, w, h)
    return o.apply(m), o.size


def fit_shape_params(hm, p, shape=None):
    shape = shape or p.shape
    m, size = object_mask_plate(hm, p)
    cx, cy, rx, ry = shapes.fit_shape(m, size, shape if shape != "auto" else "ellipse")
    return cx, cy, rx, ry


def cavity_ao(hf, size, depth, radius_frac=0.012, strength=1.0):
    """Cheap ambient occlusion from the height field (cavities get darker)."""
    h, w = hf.shape
    r = max(1.0, radius_frac * max(w, h))
    b = ndi.gaussian_filter(hf, r, mode="nearest")
    k = depth / max(1e-6, radius_frac) * 6.0 * strength
    ao = 1.0 - np.clip((b - hf) * k, 0.0, 0.85)
    return ao.astype(np.float32)
