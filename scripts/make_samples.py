# SPDX-License-Identifier: GPL-3.0-or-later
"""Generates the sample surface models (nimcale/assets/samples/*.ply): small, closed (watertight), Z up, mm.

Run:  python scripts/make_samples.py
All models are generated procedurally by this script (GPL-3.0-or-later like the rest of Nimcale).
"""
import math
import os
import struct
import sys

import numpy as np

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nimcale", "assets", "samples")


def lathe(profile, seg=72, poly=False):
    """Revolve a closed (r, z) profile loop around Z. Points with r == 0 become poles."""
    prof = [(float(r), float(z)) for r, z in profile]
    ang = np.arange(seg) * 2 * math.pi / seg
    if poly:
        ang = ang + math.pi / seg
    V, ring = [], []
    for r, z in prof:
        if r <= 1e-9:
            ring.append([len(V)] * seg)
            V.append((0.0, 0.0, z))
        else:
            ids = list(range(len(V), len(V) + seg))
            ring.append(ids)
            V.extend((r * math.cos(a), r * math.sin(a), z) for a in ang)
    F = []
    n = len(prof)
    for i in range(n):
        A, B = ring[i], ring[(i + 1) % n]
        pa, pb = prof[i][0] <= 1e-9, prof[(i + 1) % n][0] <= 1e-9
        if pa and pb:
            continue
        for j in range(seg):
            j2 = (j + 1) % seg
            # profile goes "outwards-down then up" counter-clockwise in (r, z): faces point outwards
            if pa:
                F.append((A[j], B[j2], B[j]))
            elif pb:
                F.append((A[j], A[j2], B[j]))
            else:
                F.append((A[j], A[j2], B[j2]))
                F.append((A[j], B[j2], B[j]))
    return np.array(V, float), np.array(F, np.int64)


def orient_outwards(V, F):
    """Flip all faces if the signed volume is negative (generator convention check)."""
    tri = V[F]
    vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()
    return F[:, ::-1].copy() if vol < 0 else F


def rounded_box(sx, sy, sz, r, n=10):
    """Closed rounded box: a subdivided cube pushed onto the rounded shape (watertight grid)."""
    g = np.linspace(-1, 1, n + 1)
    V, F, idx = [], [], {}

    def vid(p):
        k = tuple(np.round(p, 6))
        if k not in idx:
            idx[k] = len(V)
            V.append(p)
        return idx[k]
    for axis in range(3):
        for sign in (-1, 1):
            for i in range(n):
                for j in range(n):
                    q = []
                    for (a, b) in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                        p = np.zeros(3)
                        p[axis] = sign
                        o = [k for k in range(3) if k != axis]
                        p[o[0]], p[o[1]] = g[a], g[b]
                        q.append(vid(p))
                    if sign < 0:
                        q = q[::-1]
                    if axis == 1:
                        q = q[::-1]
                    F.append((q[0], q[1], q[2]))
                    F.append((q[0], q[2], q[3]))
    V = np.array(V)
    half = np.array([sx, sy, sz]) / 2.0
    inner = np.maximum(half - r, 1e-6)
    P = V * half
    c = np.clip(P, -inner, inner)
    d = P - c
    ln = np.linalg.norm(d, axis=1, keepdims=True)
    P = c + np.where(ln > 1e-9, d / np.maximum(ln, 1e-9) * r, 0)
    F = np.array(F, np.int64)
    return P, orient_outwards(P, F)


def torus(R, r, seg=48, sides=16, center=(0, 0, 0), axis="y"):
    V, F = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for j in range(sides):
            b = 2 * math.pi * j / sides
            x = (R + r * math.cos(b)) * math.cos(a)
            y = (R + r * math.cos(b)) * math.sin(a)
            z = r * math.sin(b)
            V.append((x, z, y) if axis == "y" else (x, y, z))
    for i in range(seg):
        for j in range(sides):
            a = i * sides + j
            b = ((i + 1) % seg) * sides + j
            c = ((i + 1) % seg) * sides + (j + 1) % sides
            d = i * sides + (j + 1) % sides
            F.append((a, b, c))
            F.append((a, c, d))
    V = np.array(V) + np.array(center)
    F = np.array(F, np.int64)
    return V, orient_outwards(V, F)


def sphere(R, n=48):
    prof = [(0, -R)] + [(R * math.sin(t), -R * math.cos(t)) for t in np.linspace(0, math.pi, n + 1)[1:-1]] + [(0, R)]
    return lathe(prof, seg=2 * n)


def merge(*parts):
    V, F, off = [], [], 0
    for v, f in parts:
        V.append(v)
        F.append(f + off)
        off += len(v)
    return np.concatenate(V), np.concatenate(F)


def shell_profile(outer, wall, bottom):
    """Open-top vessel profile from an outer (r, z) polyline (bottom -> rim), wall thickness and bottom thickness."""
    out = [(0.0, 0.0)] + list(outer)
    rim_r, rim_z = outer[-1]
    inner = []
    for r, z in reversed(outer[1:]):
        if z <= bottom:
            continue
        inner.append((max(0.5, r - wall), z))
    inner.append((max(0.5, outer[0][0] - wall), bottom))
    inner.append((0.0, bottom))
    return out + inner


def write_ply(path, V, F):
    with open(path, "wb") as f:
        f.write(("ply\nformat binary_little_endian 1.0\ncomment Nimcale sample model (GPL-3.0-or-later), mm, Z up\n"
                 "element vertex %d\nproperty float x\nproperty float y\nproperty float z\n"
                 "element face %d\nproperty list uchar int vertex_indices\nend_header\n" % (len(V), len(F)))
                .encode("ascii"))
        f.write(np.asarray(V, "<f4").tobytes())
        rec = np.zeros(len(F), dtype=[("n", "u1"), ("i", "<i4", 3)])
        rec["n"] = 3
        rec["i"] = F
        f.write(rec.tobytes())


def models():
    M = {}
    # cup: straight, slightly conical
    M["cup"] = lathe(shell_profile([(36, 0), (38, 40), (40, 95)], 3, 4))
    # mug with handle (separate closed handle shell touching the wall)
    body = lathe(shell_profile([(40, 0), (40, 95)], 3.5, 5))
    handle = torus(26, 5, 40, 14, center=(48, 0, 50), axis="y")
    M["mug"] = merge(body, handle)
    # bottle
    prof = [(0, 0), (32, 0), (34, 3), (34, 120), (30, 140), (14, 165), (12, 180), (13, 182), (13, 190), (0, 190)]
    M["bottle"] = lathe(prof)
    # vase
    out = [(28, 0)] + [(28 + 20 * math.sin(t * math.pi) * (1 - 0.4 * t), 6 + 170 * t) for t in np.linspace(0, 1, 18)]
    M["vase"] = lathe(shell_profile(out, 3, 6), seg=96)
    M["ball"] = sphere(50, n=32)
    M["box"] = rounded_box(80, 80, 80, 4, n=8)
    # can
    M["can"] = lathe([(0, 0), (28, 0), (33, 6), (33, 110), (27, 118), (27, 122), (0, 122)])
    # plate / dish
    M["plate"] = lathe([(0, 0), (60, 0), (110, 14), (112, 18), (109, 18), (58, 4), (0, 4)], seg=120)
    # keychain tag: rounded slab + ring
    tag = rounded_box(50, 30, 4, 1.5, n=10)
    ring = torus(7, 1.8, 36, 12, center=(-31, 0, 0), axis="z")
    M["tag"] = merge(tag, ring)
    # phone case like slab
    M["slab"] = rounded_box(75, 155, 10, 4.5, n=12)
    # hexagonal pen holder
    M["pen_holder"] = lathe(shell_profile([(40, 0), (40, 100)], 3, 5), seg=6, poly=True)
    # lamp shade (open frustum, thick wall, no bottom)
    out = [(90, 0), (60, 140)]
    M["lamp_shade"] = lathe([(90, 0), (60, 140), (57, 140), (87, 0)], seg=96)
    return M


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, (V, F) in models().items():
        F = orient_outwards(V, F)
        path = os.path.join(OUT, name + ".ply")
        write_ply(path, V, F)
        print("%-12s %6d tris  %6.1f KB" % (name, len(F), os.path.getsize(path) / 1024.0))


if __name__ == "__main__":
    sys.exit(main())
