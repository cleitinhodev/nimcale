# SPDX-License-Identifier: GPL-3.0-or-later
"""Sculpt brushes painting an additive layer over the (processed) source height map."""
import math

import numpy as np
from scipy import ndimage as ndi

BRUSHES = ("raise", "lower", "smooth", "flatten", "erase")


class Sculptor:
    def __init__(self):
        self.layer = None         # image-convention float32 array (same shape as the working height map)
        self.rev = 0
        self.brush = "raise"
        self.radius = 0.05        # plate units (fraction of the longest side)
        self.strength = 0.5
        self.stroking = False
        self.flat_h = None
        self.last_px = None

    def reset(self):
        self.layer = None
        self.rev += 1

    def has_edits(self):
        return self.layer is not None and bool(np.any(self.layer))

    def begin(self, shape, base, cx, cy):
        """Start a stroke (copy-on-write so undo snapshots keep the previous layer)."""
        if self.layer is None or self.layer.shape != shape:
            self.layer = np.zeros(shape, np.float32)
        else:
            self.layer = self.layer.copy()
        self.stroking = True
        comp = self._composite_at(base, cx, cy)
        self.flat_h = comp
        self.last_px = None

    def end(self):
        self.stroking = False
        self.last_px = None

    def _composite_at(self, base, cx, cy):
        h, w = base.shape
        x = int(min(max(round(cx), 0), w - 1))
        y = int(min(max(round(cy), 0), h - 1))
        return float(base[y, x] + self.layer[y, x])

    def stroke_to(self, base, cx, cy, r_px, dt, invert=False):
        """Apply the brush from the previous position to (cx, cy) (source pixels, image convention)."""
        if self.layer is None:
            return
        pts = [(cx, cy)]
        if self.last_px is not None:
            lx, ly = self.last_px
            dist = math.hypot(cx - lx, cy - ly)
            step = max(1.0, r_px * 0.3)
            if dist > step:
                n = int(dist / step)
                pts = [(lx + (cx - lx) * (k + 1) / (n + 1), ly + (cy - ly) * (k + 1) / (n + 1)) for k in range(n)] + pts
                dt = dt / len(pts)
        for (x, y) in pts:
            self._stamp(base, x, y, r_px, dt, invert)
        self.last_px = (cx, cy)
        self.rev += 1

    def _stamp(self, base, cx, cy, r, dt, invert):
        h, w = self.layer.shape
        r = max(1.5, float(r))
        x0, x1 = int(max(0, math.floor(cx - r))), int(min(w, math.ceil(cx + r) + 1))
        y0, y1 = int(max(0, math.floor(cy - r))), int(min(h, math.ceil(cy + r) + 1))
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (r * r)
        f = np.clip(1.0 - d2, 0.0, 1.0) ** 2
        L = self.layer[y0:y1, x0:x1]
        s = self.strength
        b = self.brush
        if invert and b in ("raise", "lower"):
            b = "lower" if b == "raise" else "raise"
        if b == "raise":
            L += (0.6 * s * dt) * f
        elif b == "lower":
            L -= (0.6 * s * dt) * f
        elif b == "smooth":
            pad = int(max(2, r * 0.5))
            ya, yb = max(0, y0 - pad), min(h, y1 + pad)
            xa, xb = max(0, x0 - pad), min(w, x1 + pad)
            comp = base[ya:yb, xa:xb] + self.layer[ya:yb, xa:xb]
            bl = ndi.gaussian_filter(comp, max(1.0, r * 0.25), mode="nearest")
            diff = (bl - comp)[y0 - ya:y1 - ya, x0 - xa:x1 - xa]
            L += diff * min(1.0, 10.0 * s * dt) * f
        elif b == "flatten":
            comp = base[y0:y1, x0:x1] + L
            L += (self.flat_h - comp) * min(1.0, 8.0 * s * dt) * f
        elif b == "erase":
            L *= 1.0 - min(1.0, 8.0 * s * dt) * f
