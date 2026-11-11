# SPDX-License-Identifier: GPL-3.0-or-later
"""Outline shapes as signed distance fields (positive inside, plate units)."""
import math

import numpy as np
from scipy import ndimage as ndi


def plate_coords(h, w, size):
    """Node coordinates (plate units) of a plate-convention field of shape (h, w)."""
    u = np.linspace(0.0, 1.0, w, dtype=np.float32)
    v = np.linspace(0.0, 1.0, h, dtype=np.float32)
    X = (u[None, :] - 0.5) * size[0]
    Y = (v[:, None] - 0.5) * size[1]
    return np.broadcast_to(X, (h, w)), np.broadcast_to(Y, (h, w))


def _local(X, Y, p):
    x = X - p.shape_cx
    y = Y - p.shape_cy
    if p.shape_rot:
        a = math.radians(p.shape_rot)
        c, s = math.cos(a), math.sin(a)
        x, y = c * x + s * y, -s * x + c * y
    return x, y


def sd_rect(X, Y, hx, hy):
    qx = np.abs(X) - hx
    qy = np.abs(Y) - hy
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    inside = np.minimum(np.maximum(qx, qy), 0)
    return -(outside + inside)


def sd_round_rect(X, Y, hx, hy, r):
    r = min(r, hx, hy)
    qx = np.abs(X) - hx + r
    qy = np.abs(Y) - hy + r
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    inside = np.minimum(np.maximum(qx, qy), 0)
    return -(outside + inside - r)


def sd_ellipse(X, Y, rx, ry):
    # cheap, smooth approximation (exact for circles)
    rx = max(rx, 1e-6); ry = max(ry, 1e-6)
    k0 = np.hypot(X / rx, Y / ry)
    k1 = np.hypot(X / (rx * rx), Y / (ry * ry))
    return -(k0 * (k0 - 1.0) / np.maximum(k1, 1e-9))


def sd_polygon(X, Y, r, n):
    """Regular n-gon with circumradius r (flat top)."""
    an = math.pi / n
    ang = np.arctan2(X, Y) + an
    sector = np.floor(ang / (2 * an))
    a = ang - (2 * sector + 1) * an
    rad = np.hypot(X, Y)
    px = rad * np.cos(a)
    py = rad * np.abs(np.sin(a))
    apo = r * math.cos(an)
    half = r * math.sin(an)
    dx = px - apo
    dy = np.maximum(py - half, 0)
    out = np.where(dx > 0, np.hypot(dx, dy), dx)
    return -out


def shape_sdf(p, X, Y, size):
    """Analytic SDF for the selected shape. Plate mode (no cutout) = whole rectangle."""
    if not p.cutout:
        return sd_rect(X, Y, size[0] / 2.0, size[1] / 2.0).astype(np.float32)
    x, y = _local(X, Y, p)
    rx, ry = max(1e-3, p.shape_rx), max(1e-3, p.shape_ry)
    if p.shape == "circle":
        d = rx - np.hypot(x, y)
    elif p.shape == "ellipse":
        d = sd_ellipse(x, y, rx, ry)
    elif p.shape == "rounded":
        d = sd_round_rect(x, y, rx, ry, p.shape_round * min(rx, ry))
    elif p.shape == "hexagon":
        d = sd_polygon(x, y, rx, 6)
    elif p.shape == "octagon":
        d = sd_polygon(x, y, rx, 8)
    else:
        raise ValueError(p.shape)
    return d.astype(np.float32)


def mask_sdf(mask, size, soft=0.8):
    """SDF (plate units) of a boolean plate-convention mask, via Euclidean distance transform."""
    h, w = mask.shape
    px = max(size[0] / max(1, w - 1), size[1] / max(1, h - 1))
    if mask.all():
        X, Y = plate_coords(h, w, size)
        return sd_rect(X, Y, size[0] / 2.0, size[1] / 2.0).astype(np.float32)
    if not mask.any():
        return np.full(mask.shape, -1.0, np.float32)
    din = ndi.distance_transform_edt(mask)
    dout = ndi.distance_transform_edt(~mask)
    d = np.where(mask, din - 0.5, -(dout - 0.5)).astype(np.float32) * px
    return ndi.gaussian_filter(d, max(0.3, float(soft)))


def clean_object_mask(m, close_px=2, min_frac=0.0005):
    """Threshold mask -> solid object mask (closing, hole filling, speck removal)."""
    if not m.any():
        return m
    r = max(1, int(round(close_px)))
    st = ndi.generate_binary_structure(2, 1)
    m = ndi.binary_closing(np.pad(m, r + 1), structure=st, iterations=r)[r + 1:-r - 1, r + 1:-r - 1]
    m = ndi.binary_fill_holes(m)
    lab, n = ndi.label(m)
    if n > 1:
        sizes = ndi.sum(m, lab, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, bool)
        keep[1:] = sizes >= max(16, min_frac * m.size)
        if not keep.any():
            keep[1 + int(np.argmax(sizes))] = True
        m = keep[lab]
    return m


def fit_shape(mask, size, shape):
    """Fit (cx, cy, rx, ry) of a shape to a plate-convention boolean mask."""
    h, w = mask.shape
    if not mask.any():
        return 0.0, 0.0, size[0] * 0.47, size[1] * 0.47
    X, Y = plate_coords(h, w, size)
    xs = X[mask]; ys = Y[mask]
    area = mask.mean() * size[0] * size[1]
    if shape == "circle":
        cx, cy = float(xs.mean()), float(ys.mean())
        r = math.sqrt(area / math.pi)
        return cx, cy, r, r
    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    rx, ry = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    if shape in ("hexagon", "octagon"):
        r = max(rx, ry)
        return cx, cy, r, r
    return cx, cy, rx, ry
