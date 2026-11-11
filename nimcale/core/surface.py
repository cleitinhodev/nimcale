# SPDX-License-Identifier: GPL-3.0-or-later
"""Surface layer: put the current texture + relief onto an imported 3D model (a cup, a bottle, a box...).

Pipeline
--------
1. ``load_surface``: any mesh trimesh can read (OBJ, STL, PLY, GLB/glTF, 3MF, OFF, DAE). Sub-meshes are merged
   (with their scene transforms), vertices are welded by position so that a closed input stays a closed
   (watertight) solid, the model's own UVs are kept per triangle corner.
2. ``transform_model``: up axis, rotation, real size (mm) and centring of the model.
3. ``subdivide``: conforming edge-split subdivision (no cracks) until every edge is shorter than the size of one
   relief sample, within a triangle budget.
4. ``project``: decal coordinates (plate uv) per vertex and per triangle corner - model UVs, cylindrical,
   spherical, planar, box (triplanar) or decal - with offset / scale / proportion / rotation / seam / mirror /
   tile and the decal mask.
5. ``displace``: vertices move along their normals by the relief height (mm), so a watertight input stays
   watertight.

Coordinates: millimetres, Z up. "Plate uv" is the uv space of the Nimcale plate (u right, v up, [0, 1]).
"""
import math
import os

import numpy as np

MESH_EXTS = (".obj", ".stl", ".ply", ".glb", ".gltf", ".3mf", ".off", ".dae")
PROJECTIONS = ("auto", "uv", "cylinder", "sphere", "planar", "box", "decal")
AXES = ("front", "back", "left", "right", "top", "bottom")
UP_AXES = ("z", "y", "x")
# view direction (we look along it) for planar / decal projections; cylinder axis = its line
AXIS_DIR = {"front": (0, 1, 0), "back": (0, -1, 0), "left": (1, 0, 0), "right": (-1, 0, 0),
            "top": (0, 0, -1), "bottom": (0, 0, 1)}
SAMPLES = ("cup", "mug", "bottle", "vase", "ball", "box", "can", "plate", "tag", "slab", "pen_holder", "lamp_shade")


def is_mesh_file(path):
    return os.path.splitext(path)[1].lower() in MESH_EXTS


class SurfaceModel:
    """Imported model (welded), in its own units converted to mm."""

    def __init__(self, V, F, corner_uv=None, path="", parts=1, unit=1.0, decimated=False):
        self.V = np.ascontiguousarray(V, dtype=np.float64)
        self.F = np.ascontiguousarray(F, dtype=np.int64)
        self.corner_uv = None if corner_uv is None else np.ascontiguousarray(corner_uv, dtype=np.float32)
        self.path = path
        self.name = os.path.basename(path) if path else ""
        self.parts = parts
        self.unit = unit                  # file units -> mm
        self.decimated = decimated
        ext = self.V.max(0) - self.V.min(0) if len(self.V) else np.ones(3)
        self.extent = ext * unit          # mm, before any transform
        from nimcale.core.mesh import check_closed
        self.watertight = bool(check_closed(self.F)["watertight"]) if len(self.F) else False
        self.up = default_up(path)

    @property
    def has_uv(self):
        return self.corner_uv is not None

    @property
    def n_faces(self):
        return int(len(self.F))

    @property
    def n_verts(self):
        return int(len(self.V))

    def default_size(self):
        m = float(self.extent.max())
        return float(min(500.0, max(5.0, m))) if np.isfinite(m) and m > 0 else 80.0


def default_up(path):
    ext = os.path.splitext(path or "")[1].lower()
    return "y" if ext in (".glb", ".gltf", ".obj", ".dae") else "z"


def guess_unit(extent_max):
    """Most files are in mm; models smaller than 1 unit are almost always in metres."""
    if extent_max <= 0 or not np.isfinite(extent_max):
        return 1.0
    if extent_max < 1.0:
        return 1000.0
    return 1.0


def weld(V, F, tol_rel=1e-6):
    """Merge vertices at the same position (keeps face order). Degenerate faces are dropped."""
    ext = float(np.max(V.max(0) - V.min(0))) if len(V) else 1.0
    q = np.round(V / max(ext * tol_rel, 1e-12)).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    Vw = V[first]
    Fw = inv[F]
    keep = (Fw[:, 0] != Fw[:, 1]) & (Fw[:, 1] != Fw[:, 2]) & (Fw[:, 2] != Fw[:, 0])
    return Vw, Fw, keep


def load_surface(path, max_faces=2_000_000):
    import trimesh
    scene = trimesh.load(path, force="scene", process=False)
    geoms = scene.dump(concatenate=False) if hasattr(scene, "dump") else [scene]
    Vs, Fs, UVs = [], [], []
    all_uv = True
    off = 0
    for g in geoms:
        if not hasattr(g, "faces") or g.faces is None or len(g.faces) == 0:
            continue
        v = np.asarray(g.vertices, np.float64)
        f = np.asarray(g.faces, np.int64)
        uv = None
        vis = getattr(g, "visual", None)
        if vis is not None and getattr(vis, "kind", None) == "texture" and getattr(vis, "uv", None) is not None \
                and len(vis.uv) == len(v):
            uv = np.asarray(vis.uv, np.float32)[f]
        if uv is None:
            all_uv = False
        Vs.append(v)
        Fs.append(f + off)
        UVs.append(uv)
        off += len(v)
    if not Fs:
        raise ValueError("no triangles in the file")
    V = np.concatenate(Vs)
    F = np.concatenate(Fs)
    CUV = np.concatenate([u if u is not None else np.zeros((len(f), 3, 2), np.float32)
                          for u, f in zip(UVs, Fs)]) if all_uv else None
    V, F, keep = weld(V, F)
    F = F[keep]
    if CUV is not None:
        CUV = CUV[keep]
    decimated = False
    if len(F) > max_faces:
        import fast_simplification
        P2, F2 = fast_simplification.simplify(V.astype(np.float32), F.astype(np.int32),
                                              target_reduction=1.0 - max_faces / float(len(F)))
        V, F, keep = weld(P2.astype(np.float64), F2.astype(np.int64))
        F = F[keep]
        CUV = None
        decimated = True
    # drop unused vertices
    used = np.zeros(len(V), bool)
    used[F.ravel()] = True
    remap = np.cumsum(used) - 1
    V, F = V[used], remap[F]
    unit = guess_unit(float(np.max(V.max(0) - V.min(0))))
    return SurfaceModel(V, F, CUV, path, parts=len(Fs), unit=unit, decimated=decimated)


# ---------------------------------------------------------------------------- transforms
def rot_matrix(rx, ry, rz):
    ax, ay, az = (math.radians(a) for a in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


UP_FIX = {"z": np.eye(3), "y": np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float),
          "x": np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)}


def model_matrix(model, p):
    up = p.srf_up if p.srf_up in UP_FIX else (model.up if model.up in UP_FIX else "z")
    R = rot_matrix(p.srf_rx, p.srf_ry, p.srf_rz) @ UP_FIX[up]
    return R


def transform_model(model, p):
    """Vertices in mm, rotated, scaled to srf_size (longest side) and centred (bottom at z = 0)."""
    R = model_matrix(model, p)
    V = (model.V - (model.V.max(0) + model.V.min(0)) * 0.5) @ R.T
    ext = float(np.max(V.max(0) - V.min(0)))
    k = (p.srf_size / ext) if ext > 0 else 1.0
    V = V * k
    c = (V.max(0) + V.min(0)) * 0.5
    V -= c
    return V


# ---------------------------------------------------------------------------- subdivision
def subdivide(V, F, max_len, max_faces, corner_uv=None, max_iter=24):
    """Split every edge longer than max_len (shared midpoints -> no cracks, orientation kept)."""
    V = np.asarray(V, np.float64)
    F = np.asarray(F, np.int64)
    C = None if corner_uv is None else np.asarray(corner_uv, np.float32)
    for _ in range(max_iter):
        a = F
        b = F[:, [1, 2, 0]]
        L = np.linalg.norm(V[a] - V[b], axis=2)
        long = L > max_len
        if not long.any():
            break
        room = max_faces - len(F)
        if room <= 0:
            break
        n = len(V)
        key = np.minimum(a, b) * n + np.maximum(a, b)
        if long.sum() > room:
            # budget: split only the longest edges
            thr = np.sort(L[long])[::-1][min(room, long.sum()) - 1]
            long &= L >= thr
            # an edge must be split in both faces: use the unique keys
            lk = np.unique(key[long])
            long = np.isin(key, lk) & (L > max_len)
        lk, first = np.unique(key[long], return_index=True)
        la, lb = a[long][first], b[long][first]
        mid = (V[la] + V[lb]) * 0.5
        M = np.full(F.shape, -1, np.int64)
        M[long] = n + np.searchsorted(lk, key[long])
        V = np.concatenate([V, mid])
        cnt = long.sum(1)
        outF, outC = [F[cnt == 0]], [C[cnt == 0]] if C is not None else None
        for k in (1, 2, 3):
            sel = cnt == k
            if not sel.any():
                continue
            f, m, lg = F[sel], M[sel], long[sel]
            c = C[sel] if C is not None else None
            if k == 1:
                r = np.argmax(lg, 1)
            elif k == 2:
                r = (np.argmin(lg, 1) + 1) % 3
            else:
                r = np.zeros(len(f), np.int64)
            idx = (np.arange(3)[None, :] + r[:, None]) % 3
            f = np.take_along_axis(f, idx, 1)
            m = np.take_along_axis(m, idx, 1)
            v0, v1, v2, m0, m1, m2 = f[:, 0], f[:, 1], f[:, 2], m[:, 0], m[:, 1], m[:, 2]
            if c is not None:
                c = np.take_along_axis(c, idx[:, :, None], 1)
                c0, c1, c2 = c[:, 0], c[:, 1], c[:, 2]
                d0, d1, d2 = (c0 + c1) * 0.5, (c1 + c2) * 0.5, (c2 + c0) * 0.5
            if k == 1:
                tris = [(v0, m0, v2), (m0, v1, v2)]
                cts = [(c0, d0, c2), (d0, c1, c2)] if c is not None else None
            elif k == 2:
                tris = [(m0, v1, m1), (v0, m0, m1), (v0, m1, v2)]
                cts = [(d0, c1, d1), (c0, d0, d1), (c0, d1, c2)] if c is not None else None
            else:
                tris = [(v0, m0, m2), (m0, v1, m1), (m2, m1, v2), (m0, m1, m2)]
                cts = [(c0, d0, d2), (d0, c1, d1), (d2, d1, c2), (d0, d1, d2)] if c is not None else None
            for t in tris:
                outF.append(np.stack(t, 1))
            if c is not None:
                for t in cts:
                    outC.append(np.stack(t, 1))
        F = np.concatenate(outF)
        if C is not None:
            C = np.concatenate(outC)
    return V, F, C


def vertex_normals(V, F):
    tri = V[F]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    vn = np.zeros((len(V), 3))
    for k in range(3):
        for j in range(3):
            vn[:, j] += np.bincount(F[:, k], weights=fn[:, j], minlength=len(V))
    ln = np.linalg.norm(vn, axis=1, keepdims=True)
    return vn / np.maximum(ln, 1e-20)


def face_normals(V, F):
    tri = V[F]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    return fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-20)


# ---------------------------------------------------------------------------- projection
def frame_for(axis):
    """(e1, e2, d): screen right, screen up and view direction for a planar projection along `axis`."""
    d = np.array(AXIS_DIR.get(axis, AXIS_DIR["front"]), float)
    up = np.array([0, 0, 1.0]) if abs(d[2]) < 0.5 else np.array([0, 1.0, 0]) * (1 if d[2] < 0 else -1)
    e1 = np.cross(d, up)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(e1, d)
    return e1, e2, d


def cyl_frame(axis):
    """(e1, e2, a): cylinder axis a (unsigned line), e1/e2 span the cross section, angle -90 deg = front."""
    a = np.abs(np.array(AXIS_DIR.get(axis, AXIS_DIR["top"]), float))
    if a[2] > 0.5:
        return np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), a
    if a[0] > 0.5:
        return np.array([0, 1.0, 0]), np.array([0, 0, 1.0]), a
    return np.array([0, 0, 1.0]), np.array([1.0, 0, 0]), a


def surface_samples(V, F, n=6000, seed=0):
    """Area-weighted random points on the surface with their face normals."""
    tri = V[F]
    cr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(cr, axis=1)
    if area.sum() <= 0:
        return V[:1], np.array([[0, 0, 1.0]])
    rng = np.random.default_rng(seed)
    fi = rng.choice(len(F), size=n, p=area / area.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s1 = np.sqrt(r1)
    w = np.stack([1 - s1, s1 * (1 - r2), s1 * r2], 1)
    P = np.einsum("ij,ijk->ik", w, tri[fi])
    N = cr[fi] / np.maximum(area[fi, None], 1e-20)
    return P, N


def circle_fit(q, iters=3):
    """Robust centre of points lying on a circle (Kasa fit, refitted on inliers). q: (n, 2)."""
    c = np.median(q, 0)
    sel = np.ones(len(q), bool)
    for _ in range(iters):
        x, y = q[sel, 0], q[sel, 1]
        if len(x) < 6:
            break
        A = np.stack([x, y, np.ones_like(x)], 1)
        b = -(x * x + y * y)
        try:
            D, E, Fc = np.linalg.lstsq(A, b, rcond=None)[0]
        except np.linalg.LinAlgError:
            break
        c = np.array([-D / 2, -E / 2])
        R2 = c @ c - Fc
        if R2 <= 0:
            break
        R = np.sqrt(R2)
        r = np.linalg.norm(q - c, axis=1)
        sel = np.abs(r - R) < 0.12 * R
    return c


def axis_center(V, F, axis):
    """Centre of the cylinder cross-section in the (e1, e2) plane (handles of mugs do not move it)."""
    e1, e2, a = cyl_frame(axis)
    P, N = surface_samples(V, F, 4000, seed=1)
    q = np.stack([P @ e1, P @ e2], 1)
    nq = np.stack([N @ e1, N @ e2], 1)
    side = np.abs(N @ a) < 0.4
    if side.sum() < 12:
        return np.zeros(2)
    c = circle_fit(q[side])
    rq = q - c
    out = side & (np.einsum("ij,ij->i", nq, rq) > 0)
    return circle_fit(q[out]) if out.sum() > 12 else c


def auto_projection(V, F, VN, has_uv):
    """'uv' when the model has UVs, else a guess from its shape: sphere, cylinder (cups, bottles, cans),
    planar from the top for flat objects (plates, tags, slabs) or box (triplanar)."""
    if has_uv:
        return "uv", None
    P, N = surface_samples(V, F)
    c = (V.max(0) + V.min(0)) * 0.5
    P = P - c
    ext = V.max(0) - V.min(0)
    d = np.linalg.norm(P, axis=1)
    if d.mean() > 0 and d.std() / d.mean() < 0.05:
        return "sphere", "top"
    k = int(np.argmin(ext))
    if ext[k] < 0.25 * float(ext.max()):
        return "planar", ("left", "front", "top")[k]     # flat objects: plates, tags, slabs
    best, best_axis = 9.0, None
    for ax, name in ((2, "top"), (0, "left"), (1, "front")):
        others = [k for k in range(3) if k != ax]
        diam = float(max(ext[others]))
        if ext[ax] < 0.3 * diam:
            continue                                   # flat along this axis: not a cylinder
        q = P[:, others]
        sidep = np.abs(N[:, ax]) < 0.4
        if sidep.sum() > 12:
            q = q - circle_fit(q[sidep])
        r = np.linalg.norm(q, axis=1)
        # outer wall: side faces whose normal points away from the axis (cups have an inner wall too)
        radial = np.einsum("ij,ij->i", N[:, others], q) / np.maximum(r, 1e-9)
        side = (np.abs(N[:, ax]) < 0.4) & (radial > 0.5)
        if side.mean() < 0.25:
            continue
        z, rr = P[side, ax], r[side]
        bins = np.minimum(((z - z.min()) / max(1e-9, np.ptp(z)) * 8).astype(int), 7)
        scores, weights = [], []
        for bb in range(8):
            rb = rr[bins == bb]
            if len(rb) < 20:
                continue
            q25, q50, q75 = np.percentile(rb, [25, 50, 75])
            scores.append((q75 - q25) / max(1e-9, q50))
            weights.append(len(rb))
        if not scores:
            continue
        sc = float(np.average(scores, weights=weights)) + (0.0 if ax == 2 else 0.01)
        if sc < best:
            best, best_axis = sc, name
    if best < 0.1:
        return "cylinder", best_axis
    return "box", None


class Placement:
    """Offsets / scale / rotation of the decal in its projection space (plate uv after transform)."""

    def __init__(self, p):
        self.ou, self.ov = p.srf_ou, p.srf_ov
        s = max(1e-3, p.srf_scale)
        self.kx = s * max(1e-3, p.srf_sx)
        self.ky = s * max(1e-3, (p.srf_sx if p.srf_lock else p.srf_sy))
        self.rot = math.radians(p.srf_rot)
        self.mirror = p.srf_mirror

    def apply(self, raw):
        q = raw - 0.5
        q = q - np.array([self.ou, self.ov], np.float64)
        c, s = math.cos(-self.rot), math.sin(-self.rot)
        x = c * q[..., 0] - s * q[..., 1]
        y = s * q[..., 0] + c * q[..., 1]
        u = x / self.kx + 0.5
        v = y / self.ky + 0.5
        if self.mirror:
            u = 1.0 - u
        return np.stack([u, v], -1)


def side_band(V, VN, axis, center):
    """(z0, z1, R): axial range and radius of the outer side wall of a cylinder-like model."""
    e1, e2, a = cyl_frame(axis)
    c = center if center is not None else np.zeros(2)
    q = np.stack([V @ e1 - c[0], V @ e2 - c[1]], 1)
    r = np.linalg.norm(q, axis=1)
    Z = V @ a
    nq = np.stack([VN @ e1, VN @ e2], 1)
    radial = np.einsum("ij,ij->i", nq, q) / np.maximum(r, 1e-9)
    side = (np.abs(VN @ a) < 0.5) & (radial > 0.2)
    if side.sum() < 3:
        side = np.ones(len(V), bool)
    return float(Z[side].min()), float(Z[side].max()), float(np.percentile(r[side], 90))


def raw_coords(mode, axis, V, F, VN, corner_uv, asp, seam_deg, center=None, fit="stretch"):
    """Raw projection coordinates (before placement): per vertex (n, 2) and per corner (F, 3, 2)."""
    if mode == "uv":
        cu = corner_uv.astype(np.float64)
        vu = np.zeros((len(V), 2))
        vu[F[:, 0]] = cu[:, 0]
        vu[F[:, 1]] = cu[:, 1]
        vu[F[:, 2]] = cu[:, 2]
        return vu, cu
    if mode in ("cylinder", "sphere"):
        e1, e2, a = cyl_frame(axis)
        X, Y, Z = V @ e1, V @ e2, V @ a
        if center is not None and mode == "cylinder":
            X, Y = X - center[0], Y - center[1]
        th0 = math.radians(-90.0 + seam_deg)
        th = np.arctan2(Y, X)
        t = np.mod((th - th0) / (2 * math.pi) + 0.5, 1.0)
        ku = 1.0
        if mode == "cylinder":
            z0, z1, R = side_band(V, VN, axis, center)
            Hs = max(z1 - z0, 1e-6)
            zc = 0.5 * (z0 + z1)
            circ = 2 * math.pi * max(R, 1e-6)
            if fit == "width":
                v = (Z - zc) / (circ * asp) + 0.5
            elif fit == "height":
                v = (Z - zc) / Hs + 0.5
                ku = circ / (Hs / asp)
            else:
                v = (Z - zc) / Hs + 0.5
        else:
            v = np.arctan2(Z, np.hypot(X, Y)) / math.pi + 0.5
        vt = np.stack([t, v], 1)
        ct = vt[F].copy()
        # faces crossing the seam: unwrap their u so the texture is not squeezed backwards
        span = ct[:, :, 0].max(1) - ct[:, :, 0].min(1)
        wrap = span > 0.5
        cw = ct[wrap]
        cw[:, :, 0] = np.where(cw[:, :, 0] < 0.5, cw[:, :, 0] + 1.0, cw[:, :, 0])
        ct[wrap] = cw
        vt[:, 0] = (vt[:, 0] - 0.5) * ku + 0.5
        ct[:, :, 0] = (ct[:, :, 0] - 0.5) * ku + 0.5
        return vt, ct
    if mode in ("planar", "decal"):
        e1, e2, d = frame_for(axis)
        X, Y = V @ e1, V @ e2
        X = X - 0.5 * (X.max() + X.min())
        Y = Y - 0.5 * (Y.max() + Y.min())
        W = float(X.max() - X.min()) or 1.0
        Hh = float(Y.max() - Y.min()) or 1.0
        if fit == "width":
            Wu, Hv = W, W * asp
        elif fit == "height":
            Wu, Hv = Hh / asp, Hh
        else:
            Wu, Hv = W, Hh
        vu = np.stack([X / Wu + 0.5, Y / Hv + 0.5], 1)
        return vu, vu[F]
    # box / triplanar: dominant axis of the (face / vertex) normal
    ext = V.max(0) - V.min(0)
    Wr = float(ext.max()) or 1.0
    axes_names = (("right", "left"), ("back", "front"), ("top", "bottom"))   # (+n, -n) faces
    frames = {}

    def proj(P, nrm):
        k = np.argmax(np.abs(nrm), 1)
        sgn = np.take_along_axis(nrm, k[:, None], 1)[:, 0] >= 0
        out = np.zeros((len(P), 2))
        for ax in range(3):
            for si, pos in ((0, True), (1, False)):
                sel = (k == ax) & (sgn == pos)
                if not sel.any():
                    continue
                name = axes_names[ax][si]
                if name not in frames:
                    frames[name] = frame_for(name)
                e1, e2, _ = frames[name]
                out[sel, 0] = P[sel] @ e1 / Wr + 0.5
                out[sel, 1] = P[sel] @ e2 / (Wr * asp) + 0.5
        return out
    vu = proj(V, VN)
    FN = face_normals(V, F)
    cu = proj(V[F].reshape(-1, 3), np.repeat(FN, 3, 0)).reshape(-1, 3, 2)
    return vu, cu


def sample_field(field, uv):
    """Bilinear sample of a plate-convention field (row 0 = v 0) at plate uv in [0, 1]."""
    h, w = field.shape
    x = np.clip(uv[..., 0], 0, 1) * (w - 1)
    y = np.clip(uv[..., 1], 0, 1) * (h - 1)
    x0 = np.minimum(np.floor(x).astype(np.int64), w - 2) if w > 1 else np.zeros_like(x, np.int64)
    y0 = np.minimum(np.floor(y).astype(np.int64), h - 2) if h > 1 else np.zeros_like(y, np.int64)
    fx, fy = x - x0, y - y0
    f00 = field[y0, x0]
    f01 = field[y0, np.minimum(x0 + 1, w - 1)]
    f10 = field[np.minimum(y0 + 1, h - 1), x0]
    f11 = field[np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)]
    return (f00 * (1 - fx) + f01 * fx) * (1 - fy) + (f10 * (1 - fx) + f11 * fx) * fy


class SurfaceGeometry:
    """Transformed + subdivided model (depends on the model transform and the detail only)."""

    def __init__(self, model, p, detail_nodes, max_faces, asp):
        V = transform_model(model, p)
        F = model.F
        VN0 = vertex_normals(V, F)
        mode, axis = p.srf_proj, p.srf_axis
        if mode == "auto":
            mode, ax = auto_projection(V, F, VN0, model.has_uv)
            axis = ax or axis
        if mode == "uv" and not model.has_uv:
            mode = "box"
        self.mode, self.axis = mode, axis
        self.center = axis_center(V, F, axis) if mode == "cylinder" else None
        # one relief sample ~ (decal width) / detail_nodes
        ext = V.max(0) - V.min(0)
        if mode in ("cylinder", "sphere"):
            e1, e2, a = cyl_frame(axis)
            c0 = self.center if self.center is not None else np.zeros(2)
            r = np.hypot(V @ e1 - c0[0], V @ e2 - c0[1])
            ref = 2 * math.pi * float(np.percentile(r, 90))
        else:
            ref = float(ext.max())
        ref *= min(1.0, max(0.05, p.srf_scale))
        self.max_len = max(ref / max(16, detail_nodes), float(ext.max()) / 4000.0)
        Vs, Fs, C = subdivide(V, F, self.max_len, max_faces, model.corner_uv if mode == "uv" else None)
        self.V, self.F, self.corner_uv = Vs, Fs, C
        self.VN = vertex_normals(Vs, Fs)
        self.asp = asp


class SurfaceResult:
    def __init__(self, geo, P, VN, uv_v, w_v, h_v, uv_c, w_c, h_c, tile):
        self.geo = geo
        self.P, self.F, self.VN = P, geo.F, VN
        self.uv_v, self.w_v, self.h_v = uv_v, w_v, h_v
        self.uv_c, self.w_c, self.h_c = uv_c, w_c, h_c
        self.tile = tile
        self.mode, self.axis = geo.mode, geo.axis

    @property
    def n_tris(self):
        return int(len(self.F))

    def bounds(self):
        return self.P.min(0), self.P.max(0)


def displace(geo, p, hf, sdf, relief_mm):
    """Decal coordinates + relief displacement on a SurfaceGeometry."""
    V, F, VN = geo.V, geo.F, geo.VN
    vu, cu = raw_coords(geo.mode, geo.axis, V, F, VN, geo.corner_uv, geo.asp, p.srf_seam, geo.center, p.srf_fit)
    pl = Placement(p)
    uv_v = pl.apply(vu)
    uv_c = pl.apply(cu)
    tile = bool(p.srf_tile) and geo.mode != "decal"
    if tile:
        uv_v = np.mod(uv_v, 1.0)
        sh = np.floor(uv_c.min(1, keepdims=True))
        uv_c = uv_c - sh
        w_v = np.ones(len(V))
        w_c = np.ones(uv_c.shape[:2])
    else:
        def inside(uv):
            return ((uv[..., 0] >= 0) & (uv[..., 0] <= 1) & (uv[..., 1] >= 0) & (uv[..., 1] <= 1)).astype(float)
        w_v = inside(uv_v)
        w_c = inside(uv_c)
        if geo.mode == "decal":
            d = frame_for(geo.axis)[2]
            front_v = (VN @ d) < -0.05
            w_v *= front_v
            FN = face_normals(V, F)
            w_c *= ((FN @ d) < -0.05)[:, None]
    if geo.mode == "cylinder" and (p.srf_outer or not p.srf_caps):
        e1, e2, a = cyl_frame(geo.axis)
        c = geo.center if geo.center is not None else np.zeros(2)
        FN = face_normals(V, F)
        R_body = side_band(V, VN, geo.axis, geo.center)[2]

        def keep(P, N):
            q = np.stack([P @ e1 - c[0], P @ e2 - c[1]], 1)
            r = np.linalg.norm(q, axis=1)
            radial = np.einsum("ij,ij->i", np.stack([N @ e1, N @ e2], 1), q) / np.maximum(r, 1e-9)
            ok = np.ones(len(P), bool)
            if p.srf_outer:
                ok &= radial > -0.2           # not the inner wall of cups / vases
                ok &= r < 1.12 * R_body       # nor handles / parts sticking out of the body
            if not p.srf_caps:
                ok &= np.abs(N @ a) < 0.75    # not the top / bottom faces
            return ok
        w_v = w_v * keep(V, VN)
        w_c = w_c * keep(V[F].mean(1), FN)[:, None]
    if p.srf_use_cut and sdf is not None:
        w_v = w_v * (sample_field(sdf, np.mod(uv_v, 1.0) if tile else uv_v) > 0)
        w_c = w_c * (sample_field(sdf, np.mod(uv_c, 1.0) if tile else uv_c) > 0)
    h_v = sample_field(hf, uv_v) * w_v
    h_c = sample_field(hf, np.mod(uv_c, 1.0) if tile else uv_c) * w_c
    P = V + VN * (h_v * relief_mm)[:, None]
    VN2 = vertex_normals(P, F)
    return SurfaceResult(geo, P, VN2, uv_v, w_v, h_v, uv_c, w_c, h_c, tile)


class SurfaceBuilder:
    """Cached builder used by the preview (geometry is only rebuilt when the model / detail change)."""
    GEO_KEYS = ("srf_up", "srf_rx", "srf_ry", "srf_rz", "srf_size", "srf_proj", "srf_axis", "srf_detail")

    def __init__(self):
        self.geo = None
        self.geo_key = None
        self.res = None
        self.res_key = None

    def build(self, model, p, res, max_faces=350_000, detail=None, force_geo=False):
        sw, sh = res.size
        asp = sh / float(sw)
        det = int(detail or p.srf_detail)
        gk = (id(model), tuple(getattr(p, k) for k in self.GEO_KEYS), det, max_faces, round(asp, 4),
              round(min(1.0, max(0.05, p.srf_scale)), 2))
        if force_geo or gk != self.geo_key or self.geo is None:
            self.geo = SurfaceGeometry(model, p, det, max_faces, asp)
            self.geo_key = gk
            self.res_key = None
        relief = p.depth * p.size_mm
        rk = (gk, tuple(getattr(p, f) for f in PLACE_KEYS), id(res.hf), id(res.sdf), relief, p.cutout)
        if rk != self.res_key or self.res is None:
            self.res = displace(self.geo, p, res.hf, res.sdf if p.cutout else None, relief)
            self.res_key = rk
        return self.res


PLACE_KEYS = ("srf_ou", "srf_ov", "srf_scale", "srf_sx", "srf_sy", "srf_lock", "srf_rot", "srf_seam", "srf_tile",
              "srf_mirror", "srf_use_cut", "srf_fit", "srf_outer", "srf_caps")


def build_hd(model, p, res_hd, nodes, max_faces=4_000_000):
    sw, sh = res_hd.size
    geo = SurfaceGeometry(model, p, int(nodes), max_faces, sh / float(sw))
    return displace(geo, p, res_hd.hf, res_hd.sdf if p.cutout else None, p.depth * p.size_mm)


# ---------------------------------------------------------------------------- export helpers
def export_meshes(sr, plate_img, base_rgb, margin=0.03):
    """(welded Mesh for STL/3MF/OFF/PLY, split Mesh for OBJ/glTF, atlas texture PIL image)."""
    from PIL import Image
    from nimcale.core.mesh import Mesh
    P = sr.P.astype(np.float32)
    F = sr.F
    VN = sr.VN.astype(np.float32)
    W, H = plate_img.size
    if sr.tile:
        atlas = Image.new("RGB", (W * 2, H * 2))
        for i in (0, 1):
            for j in (0, 1):
                atlas.paste(plate_img, (i * W, j * H))
        uvc = np.clip(sr.uv_c, 0.0, 2.0) / 2.0
        uvv = sr.uv_v / 2.0
        base_uv = None
    else:
        mw, mh = int(round(W * margin)), int(round(H * margin))
        col = tuple(int(round(c * 255)) for c in base_rgb)
        atlas = Image.new("RGB", (W + 2 * mw, H + 2 * mh), col)
        atlas.paste(plate_img, (mw, mh))
        kx, ky = W / float(W + 2 * mw), H / float(H + 2 * mh)
        ox, oy = mw / float(W + 2 * mw), mh / float(H + 2 * mh)
        base_uv = np.array([ox * 0.5, oy * 0.5])

        def to_atlas(uv, w):
            q = np.stack([np.clip(uv[..., 0], -margin, 1 + margin) * kx + ox,
                          np.clip(uv[..., 1], -margin, 1 + margin) * ky + oy], -1)
            q[w < 0.5] = base_uv
            return q
        uvc = to_atlas(sr.uv_c, sr.w_c)
        uvv = to_atlas(sr.uv_v, sr.w_v)
    welded = Mesh(P, F.astype(np.uint32), uvv.astype(np.float32), VN, len(F), 0, 0, (1.0, 1.0))
    # split vertices where a vertex has different texture coordinates in its triangles (seams)
    q = np.round(uvc.reshape(-1, 2) * 65536).astype(np.int64)
    keys = np.stack([F.reshape(-1), q[:, 0], q[:, 1]], 1)
    uk, inv = np.unique(keys, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    vid = uk[:, 0]
    UV = np.zeros((len(uk), 2), np.float32)
    UV[inv] = uvc.reshape(-1, 2)
    split = Mesh(P[vid], inv.reshape(-1, 3).astype(np.uint32), UV, VN[vid], len(F), 0, 0, (1.0, 1.0))
    return welded, split, atlas
