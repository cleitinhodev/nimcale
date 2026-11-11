# SPDX-License-Identifier: GPL-3.0-or-later
"""Small matrix helpers and the orbit camera."""
import math

import numpy as np


def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float64)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def translate(x, y, z):
    m = np.eye(4)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, -s, s, c
    return m


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    return m


def gl_bytes(m):
    return np.ascontiguousarray(np.asarray(m, np.float32).T).tobytes()


class Camera:
    """Orbit camera looking at the plate (plate in the XY plane, relief towards +Z)."""

    def __init__(self, view, w, h, extra_yaw=0.0):
        self.w, self.h = max(1, w), max(1, h)
        self.proj = perspective(view.fov, self.w / float(self.h), 0.02, 60.0)
        R = rot_x(view.pitch) @ rot_y(view.yaw + extra_yaw)
        self.view = translate(view.pan[0], view.pan[1], -view.dist) @ R
        self.mvp = self.proj @ self.view
        self.inv_view = np.linalg.inv(self.view)
        self.inv_mvp = np.linalg.inv(self.mvp)
        self.eye = (self.inv_view @ np.array([0, 0, 0, 1.0]))[:3]

    def project(self, p):
        """World point -> (x, y) pixels (origin top-left) or None when behind the camera."""
        v = self.mvp @ np.array([p[0], p[1], p[2], 1.0])
        if v[3] <= 1e-6:
            return None
        ndc = v[:3] / v[3]
        return ((ndc[0] * 0.5 + 0.5) * self.w, (1.0 - (ndc[1] * 0.5 + 0.5)) * self.h)

    def ray(self, x, y):
        """Pixel (origin top-left) -> (origin, direction) in world space."""
        nx = x / self.w * 2.0 - 1.0
        ny = 1.0 - y / self.h * 2.0
        a = self.inv_mvp @ np.array([nx, ny, -1.0, 1.0])
        b = self.inv_mvp @ np.array([nx, ny, 1.0, 1.0])
        a = a[:3] / a[3]
        b = b[:3] / b[3]
        d = b - a
        return a, d / np.linalg.norm(d)
