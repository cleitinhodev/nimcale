# SPDX-License-Identifier: GPL-3.0-or-later
"""Crop / 90-degree rotation / mirror applied together to the height map and the texture.

Conventions
-----------
* "image" arrays: row 0 is the top of the picture.
* "plate" arrays: row 0 is v = 0 (bottom of the plate), as uploaded to OpenGL.
* uv coordinates are v-up in both the source and the plate space.
"""
import numpy as np


class Orient:
    def __init__(self, p, src_w, src_h):
        self.l = float(min(max(p.crop_l, 0.0), 0.95))
        self.r = float(min(max(p.crop_r, 0.0), 0.95 - self.l))
        self.t = float(min(max(p.crop_t, 0.0), 0.95))
        self.b = float(min(max(p.crop_b, 0.0), 0.95 - self.t))
        self.k = int(p.rot90) % 4
        self.fx = bool(p.flip_x)
        self.fy = bool(p.flip_y)
        self.src_w, self.src_h = int(src_w), int(src_h)
        cw = self.src_w * (1.0 - self.l - self.r)
        ch = self.src_h * (1.0 - self.t - self.b)
        if self.k % 2:
            cw, ch = ch, cw
        m = max(cw, ch)
        self.size = (cw / m, ch / m)              # plate size, longest side = 1
        self.crop_px = (cw, ch)                   # plate extent in source pixels (after rotation)

    @property
    def identity(self):
        return self.l == self.r == self.t == self.b == 0.0 and self.k == 0 and not self.fx and not self.fy

    # ------------------------------------------------------------------ arrays
    def apply(self, img):
        """Image-convention array (source) -> plate-convention array (row 0 = v 0)."""
        h, w = img.shape[:2]
        x0 = int(round(self.l * w)); x1 = max(x0 + 2, int(round((1.0 - self.r) * w)))
        y0 = int(round(self.t * h)); y1 = max(y0 + 2, int(round((1.0 - self.b) * h)))
        a = img[y0:y1, x0:x1]
        if self.k:
            a = np.rot90(a, self.k)
        if self.fx:
            a = a[:, ::-1]
        if self.fy:
            a = a[::-1]
        return np.ascontiguousarray(a[::-1])

    def plate_shape(self, h, w):
        """Shape of apply(img) for a source of shape (h, w)."""
        x0 = int(round(self.l * w)); x1 = max(x0 + 2, int(round((1.0 - self.r) * w)))
        y0 = int(round(self.t * h)); y1 = max(y0 + 2, int(round((1.0 - self.b) * h)))
        hh, ww = y1 - y0, x1 - x0
        return (ww, hh) if self.k % 2 else (hh, ww)

    # ------------------------------------------------------------------ coordinates
    def matrix_src_to_plate(self):
        """3x3 affine matrix mapping source uv (v-up) to plate uv."""
        su = 1.0 / max(1e-6, 1.0 - self.l - self.r)
        sv = 1.0 / max(1e-6, 1.0 - self.t - self.b)
        M = np.array([[su, 0, -self.l * su], [0, sv, -self.b * sv], [0, 0, 1]], dtype=np.float64)
        R = np.array([[0, -1, 1], [1, 0, 0], [0, 0, 1]], dtype=np.float64)   # CCW: (u,v) -> (1-v, u)
        for _ in range(self.k):
            M = R @ M
        if self.fx:
            M = np.array([[-1, 0, 1], [0, 1, 0], [0, 0, 1]], dtype=np.float64) @ M
        if self.fy:
            M = np.array([[1, 0, 0], [0, -1, 1], [0, 0, 1]], dtype=np.float64) @ M
        return M

    def matrix_plate_to_src(self):
        return np.linalg.inv(self.matrix_src_to_plate())

    def plate_to_src(self, u, v):
        M = self.matrix_plate_to_src()
        return M[0, 0] * u + M[0, 1] * v + M[0, 2], M[1, 0] * u + M[1, 1] * v + M[1, 2]

    def src_to_plate(self, u, v):
        M = self.matrix_src_to_plate()
        return M[0, 0] * u + M[0, 1] * v + M[0, 2], M[1, 0] * u + M[1, 1] * v + M[1, 2]
