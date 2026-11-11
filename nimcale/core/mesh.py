# SPDX-License-Identifier: GPL-3.0-or-later
"""Watertight solid mesh from a height field and an outline.

The solid is made of
  * the front (relief) surface: a regular grid restricted to the cells inside the outline,
  * the side walls: one quad per boundary edge of the front,
  * the flat bottom: triangulated row by row ("zipper" between two chains of points), sharing
    exactly the boundary vertices of the walls, so every edge is used by exactly two triangles.
Boundary vertices can be snapped onto the true (smooth) outline, removing the staircase effect.
"""
import numpy as np
from scipy import ndimage as ndi


# ---------------------------------------------------------------------------- sampling helpers
def sample_nodes(field, u, v):
    """Bilinear sample of a node-aligned field (plate convention) at uv in [0, 1]."""
    h, w = field.shape
    x = np.clip(np.asarray(u, np.float64) * (w - 1), 0, w - 1)
    y = np.clip(np.asarray(v, np.float64) * (h - 1), 0, h - 1)
    x0 = np.minimum(np.floor(x).astype(np.int64), w - 2 if w > 1 else 0)
    y0 = np.minimum(np.floor(y).astype(np.int64), h - 2 if h > 1 else 0)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    a = field[y0, x0] * (1 - fx) + field[y0, x1] * fx
    b = field[y1, x0] * (1 - fx) + field[y1, x1] * fx
    return (a * (1 - fy) + b * fy).astype(np.float32)


def cell_mask(sdf, nx, ny):
    u = (np.arange(nx, dtype=np.float64) + 0.5) / nx
    v = (np.arange(ny, dtype=np.float64) + 0.5) / ny
    U, V = np.meshgrid(u, v)
    return sample_nodes(sdf, U, V) > 0.0


def grid_dims(field_w, field_h, res):
    """Cells (nx, ny) with `res` cells on the longest side, never more than the field resolution."""
    m = max(field_w, field_h)
    res = int(max(8, min(res, m - 1)))
    k = res / float(m - 1)
    return max(4, int(round((field_w - 1) * k))), max(4, int(round((field_h - 1) * k)))


# ---------------------------------------------------------------------------- topology
def clean_cells(cells):
    """Remove diagonal-only contacts (non-manifold vertices) and fill holes."""
    c = np.ascontiguousarray(cells, dtype=bool).copy()
    for _ in range(64):
        a = c[:-1, :-1]; b = c[:-1, 1:]; cc = c[1:, :-1]; d = c[1:, 1:]
        fix = (a & d & ~b & ~cc) | (b & cc & ~a & ~d)
        if not fix.any():
            break
        c[:-1, :-1] |= fix; c[:-1, 1:] |= fix; c[1:, :-1] |= fix; c[1:, 1:] |= fix
        c = ndi.binary_fill_holes(c)
    c = ndi.binary_fill_holes(c)
    return c


def _run_ends(row):
    """Vertex x positions where a run of True cells starts or ends."""
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    return np.flatnonzero(d != 0)


def _runs(row):
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1)


class Topology:
    def __init__(self, cells):
        self.cells = cells
        self.ny, self.nx = cells.shape
        ny, nx = self.ny, self.nx
        W = nx + 1
        self.W = W
        j, i = np.nonzero(cells)
        v00 = (j * W + i).astype(np.int64)
        v10, v01 = v00 + 1, v00 + W
        v11 = v01 + 1
        self.front = np.stack([np.stack([v00, v10, v11], 1), np.stack([v00, v11, v01], 1)], 1).reshape(-1, 3)
        # boundary directed edges (same direction as in the front triangles)
        pad = np.zeros((ny + 2, nx + 2), bool)
        pad[1:-1, 1:-1] = cells
        c = cells
        edges = []
        jj, ii = np.nonzero(c & ~pad[0:ny, 1:-1])            # empty below
        edges.append(np.stack([jj * W + ii, jj * W + ii + 1], 1))
        jj, ii = np.nonzero(c & ~pad[1:-1, 2:])              # empty right
        edges.append(np.stack([jj * W + ii + 1, (jj + 1) * W + ii + 1], 1))
        jj, ii = np.nonzero(c & ~pad[2:, 1:-1])              # empty above
        edges.append(np.stack([(jj + 1) * W + ii + 1, (jj + 1) * W + ii], 1))
        jj, ii = np.nonzero(c & ~pad[1:-1, 0:nx])            # empty left
        edges.append(np.stack([(jj + 1) * W + ii, jj * W + ii], 1))
        self.bedges = np.concatenate(edges).astype(np.int64)
        self.bottom = self._bottom(cells)

    def _bottom(self, c):
        ny, nx = c.shape
        W = nx + 1
        tris = []
        empty = np.zeros(nx, bool)
        for j in range(ny):
            row = c[j]
            if not row.any():
                continue
            below = c[j - 1] if j > 0 else empty
            above = c[j + 1] if j < ny - 1 else empty
            ends_row = _run_ends(row)
            ptb = np.zeros(nx + 1, bool)
            seg = row & ~below
            ptb[:-1] |= seg; ptb[1:] |= seg
            ptb[ends_row] = True
            ptb[_run_ends(below)] = True
            ptt = np.zeros(nx + 1, bool)
            seg = row & ~above
            ptt[:-1] |= seg; ptt[1:] |= seg
            ptt[ends_row] = True
            ptt[_run_ends(above)] = True
            starts, stops = _runs(row)
            xb_all = np.flatnonzero(ptb)
            xt_all = np.flatnonzero(ptt)
            for a, b in zip(starts.tolist(), stops.tolist()):
                B = xb_all[(xb_all >= a) & (xb_all <= b)]
                T = xt_all[(xt_all >= a) & (xt_all <= b)]
                Bi = (j * W + B).tolist()
                Ti = ((j + 1) * W + T).tolist()
                Bx = B.tolist(); Tx = T.tolist()
                ib, it = 0, 0
                nb, nt = len(Bi) - 1, len(Ti) - 1
                while ib < nb or it < nt:
                    if it >= nt or (ib < nb and Bx[ib + 1] <= Tx[it + 1]):
                        tris.append((Bi[ib], Ti[it], Bi[ib + 1]))       # facing -z
                        ib += 1
                    else:
                        tris.append((Bi[ib], Ti[it], Ti[it + 1]))
                        it += 1
        if not tris:
            return np.zeros((0, 3), np.int64)
        return np.asarray(tris, dtype=np.int64)

    def node_uv(self):
        W, ny, nx = self.W, self.ny, self.nx
        u = np.arange(W, dtype=np.float64) / nx
        v = np.arange(ny + 1, dtype=np.float64) / ny
        U, V = np.meshgrid(u, v)
        return U.ravel(), V.ravel()


def snap_boundary(topo, U, V, sdf, size, max_move=0.6, iters=4):
    """Move boundary nodes onto the zero level of the SDF (in place on U, V)."""
    ids = np.unique(topo.bedges)
    if len(ids) == 0:
        return ids
    sw, sh = size
    cu, cv = 1.0 / topo.nx, 1.0 / topo.ny
    u0 = U[ids].copy(); v0 = V[ids].copy()
    u = u0.copy(); v = v0.copy()
    eu, ev = cu * 0.5, cv * 0.5
    for _ in range(iters):
        d = sample_nodes(sdf, u, v)
        gx = (sample_nodes(sdf, u + eu, v) - sample_nodes(sdf, u - eu, v)) / (2 * eu * sw)
        gy = (sample_nodes(sdf, u, v + ev) - sample_nodes(sdf, u, v - ev)) / (2 * ev * sh)
        g2 = gx * gx + gy * gy
        ok = g2 > 1e-6
        step = np.where(ok, d / np.maximum(g2, 1e-6), 0.0)
        u = u - step * gx / sw
        v = v - step * gy / sh
        du = np.clip((u - u0) / cu, -max_move, max_move)
        dv = np.clip((v - v0) / cv, -max_move, max_move)
        u = u0 + du * cu
        v = v0 + dv * cv
    u = np.clip(u, 0.0, 1.0)
    v = np.clip(v, 0.0, 1.0)
    # never flip a triangle: halve the move of boundary nodes used by inverted triangles
    tris = [(topo.front, 1.0)]
    if len(topo.bottom):
        tris.append((topo.bottom, -1.0))
    def flipped_nodes():
        bad = np.zeros(len(U), bool)
        for T, sgn in tris:
            ax, ay = U[T[:, 0]], V[T[:, 0]]
            area = (U[T[:, 1]] - ax) * (V[T[:, 2]] - ay) - (U[T[:, 2]] - ax) * (V[T[:, 1]] - ay)
            flipped = (area * sgn) < 1e-3 * cu * cv
            if flipped.any():
                bad[T[flipped].ravel()] = True
        return bad[ids]

    for it in range(12):
        U[ids] = u; V[ids] = v
        sel = flipped_nodes()
        if not sel.any():
            return ids
        f = 0.5 if it < 8 else 0.0
        u[sel] = u0[sel] + (u[sel] - u0[sel]) * f
        v[sel] = v0[sel] + (v[sel] - v0[sel]) * f
    U[ids] = u; V[ids] = v
    if flipped_nodes().any():
        U[ids] = u0; V[ids] = v0
    return ids


# ---------------------------------------------------------------------------- solid mesh
class Mesh:
    """Indexed triangle mesh in plate units (x, y in [-size/2, size/2], z up)."""

    def __init__(self, P, F, UV, VN, n_front, n_wall, n_bottom, size):
        self.P = P
        self.F = F
        self.UV = UV
        self.VN = VN
        self.n_front, self.n_wall, self.n_bottom = n_front, n_wall, n_bottom
        self.size = size

    @property
    def n_tris(self):
        return int(len(self.F))

    @property
    def n_verts(self):
        return int(len(self.P))

    def scaled(self, k):
        return Mesh(self.P * np.float32(k), self.F, self.UV, self.VN, self.n_front, self.n_wall, self.n_bottom,
                    self.size)

    def face_normals(self):
        tri = self.P[self.F]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        return (n / np.maximum(ln, 1e-20)).astype(np.float32)


def front_normals(Z, size):
    h, w = Z.shape
    dzdx = np.gradient(Z, size[0] / max(1, w - 1), axis=1)
    dzdy = np.gradient(Z, size[1] / max(1, h - 1), axis=0)
    N = np.stack([-dzdx, -dzdy, np.ones_like(Z)], axis=-1).astype(np.float32)
    N /= np.linalg.norm(N, axis=-1, keepdims=True)
    return N


def build_solid(hf, sdf, size, depth, thick, res=None, snap=True, progress=None):
    """Build the watertight solid.

    hf, sdf : plate-convention fields (same shape), hf in relief units, sdf in plate units.
    res     : cells on the longest side (None = one node per height-field sample).
    """
    def prog(f, msg=""):
        if progress:
            progress(f, msg)

    H, W = hf.shape
    if res is None:
        nx, ny = W - 1, H - 1
    else:
        nx, ny = grid_dims(W, H, res)
    prog(0.02, "outline")
    cells = clean_cells(cell_mask(sdf, nx, ny))
    if cells.sum() == 0:
        raise ValueError("empty outline")
    prog(0.10, "topology")
    topo = Topology(cells)
    U, V = topo.node_uv()
    if snap:
        snap_boundary(topo, U, V, sdf, size)
    prog(0.35, "vertices")
    direct = (nx == W - 1 and ny == H - 1)
    used_f = np.unique(topo.front)
    used_b = np.unique(topo.bottom) if len(topo.bottom) else np.unique(topo.bedges)
    if direct:
        Zgrid = hf.astype(np.float32) * np.float32(depth)
        Nf_grid = front_normals(Zgrid, size).reshape(-1, 3)
        Zf = Zgrid.ravel()[used_f]
        if snap:
            bids = np.unique(topo.bedges)
            Zb = sample_nodes(hf, U[bids], V[bids]) * np.float32(depth)
            zfull = Zgrid.ravel().copy()
            zfull[bids] = Zb
            Zf = zfull[used_f]
        Nf = Nf_grid[used_f]
        del Zgrid, Nf_grid
    else:
        Zf = sample_nodes(hf, U[used_f], V[used_f]) * np.float32(depth)
        Zs = (sample_nodes(hf, (np.arange(nx + 1) / nx)[None, :].repeat(ny + 1, 0),
                           (np.arange(ny + 1) / ny)[:, None].repeat(nx + 1, 1)) * depth).astype(np.float32)
        Nf = front_normals(Zs, size).reshape(-1, 3)[used_f]
        del Zs
    prog(0.55, "faces")
    sw, sh = size
    Xf = ((U[used_f] - 0.5) * sw).astype(np.float32)
    Yf = ((V[used_f] - 0.5) * sh).astype(np.float32)
    Pf = np.stack([Xf, Yf, Zf.astype(np.float32)], 1)
    Xb = ((U[used_b] - 0.5) * sw).astype(np.float32)
    Yb = ((V[used_b] - 0.5) * sh).astype(np.float32)
    Pb = np.stack([Xb, Yb, np.full_like(Xb, -float(thick))], 1)
    n_nodes = len(U)
    rf = np.full(n_nodes, -1, np.int64); rf[used_f] = np.arange(len(used_f))
    rb = np.full(n_nodes, -1, np.int64); rb[used_b] = np.arange(len(used_b)) + len(used_f)
    Ff = rf[topo.front]
    a, b = topo.bedges[:, 0], topo.bedges[:, 1]
    Fw = np.concatenate([np.stack([rf[b], rf[a], rb[a]], 1), np.stack([rf[b], rb[a], rb[b]], 1)])
    Fb = rb[topo.bottom]
    P = np.concatenate([Pf, Pb])
    UV = np.concatenate([np.stack([U[used_f], V[used_f]], 1), np.stack([U[used_b], V[used_b]], 1)]).astype(np.float32)
    VN = np.concatenate([Nf, np.tile(np.array([[0, 0, -1]], np.float32), (len(Pb), 1))])
    F = np.concatenate([Ff, Fw, Fb])
    if F.min() < 0:
        raise RuntimeError("internal mesh error (unmapped vertex)")
    F = F.astype(np.uint32 if len(P) < 2 ** 32 else np.int64)
    prog(0.95, "done")
    return Mesh(P.astype(np.float32), F, UV, VN.astype(np.float32), len(Ff), len(Fw), len(Fb), size)


# ---------------------------------------------------------------------------- analysis
def check_closed(F):
    """Edge-manifold / orientation check. Returns dict(watertight, boundary_edges, duplicate_edges)."""
    F = np.asarray(F, dtype=np.int64)
    if len(F) == 0:
        return dict(watertight=False, boundary_edges=0, duplicate_edges=0, degenerate=0)
    n = int(F.max()) + 1
    e0 = np.concatenate([F[:, 0], F[:, 1], F[:, 2]])
    e1 = np.concatenate([F[:, 1], F[:, 2], F[:, 0]])
    degenerate = int(np.count_nonzero((F[:, 0] == F[:, 1]) | (F[:, 1] == F[:, 2]) | (F[:, 2] == F[:, 0])))
    kd = np.sort(e0 * n + e1)
    dup = int(np.count_nonzero(kd[1:] == kd[:-1]))
    rev = e1 * n + e0
    del e0, e1
    idx = np.searchsorted(kd, rev)
    idx = np.minimum(idx, len(kd) - 1)
    missing = int(np.count_nonzero(kd[idx] != rev))
    return dict(watertight=(missing == 0 and dup == 0 and degenerate == 0), boundary_edges=missing,
                duplicate_edges=dup, degenerate=degenerate)


def volume(P, F):
    P = P.astype(np.float64)
    tri = P[F]
    return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)


def estimate_triangles(sdf, res=None):
    """Estimated triangle count of build_solid (cheap)."""
    H, W = sdf.shape
    if res is None:
        nx, ny = W - 1, H - 1
    else:
        nx, ny = grid_dims(W, H, res)
    small = sdf if max(H, W) <= 512 else sdf[::max(1, H // 512), ::max(1, W // 512)]
    frac = float((small > 0).mean())
    cells = frac * nx * ny
    perim = 4.0 * np.sqrt(max(cells, 1.0)) * 1.2
    return int(2 * cells + 2 * perim + 2 * perim + 2 * ny)


def decimate(mesh, target_reduction, progress=None):
    """Adaptive simplification (quadric error); keeps detail where curvature is high."""
    import fast_simplification
    P, F = fast_simplification.simplify(mesh.P.astype(np.float32), mesh.F.astype(np.int32),
                                        target_reduction=float(target_reduction), agg=7)
    P = P.astype(np.float32)
    F = F.astype(np.uint32)
    m = Mesh(P, F, None, None, len(F), 0, 0, mesh.size)
    sw, sh = mesh.size
    m.UV = np.stack([P[:, 0] / sw + 0.5, P[:, 1] / sh + 0.5], 1).astype(np.float32)
    m.VN = vertex_normals(P, F)
    return m


def vertex_normals(P, F):
    tri = P[F].astype(np.float64)
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    vn = np.zeros((len(P), 3), np.float64)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    ln = np.linalg.norm(vn, axis=1, keepdims=True)
    return (vn / np.maximum(ln, 1e-20)).astype(np.float32)
