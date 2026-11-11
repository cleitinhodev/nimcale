# SPDX-License-Identifier: GPL-3.0-or-later
"""Writers for 3D formats (STL, OBJ, glTF/GLB, PLY, 3MF, OFF) and images.

All writers receive a Mesh already scaled to the output unit (millimetres, or metres for glTF).
`progress(fraction, message)` is optional; `cancel()` returning True aborts with Cancelled.
"""
import io
import json
import os
import struct
import zipfile

import numpy as np
from PIL import Image

from nimcale import APP_NAME, __version__

GENERATOR = "%s %s" % (APP_NAME, __version__)
CHUNK = 250000


class Cancelled(Exception):
    pass


def _cb(progress, cancel, base, span):
    def f(frac, msg=""):
        if cancel and cancel():
            raise Cancelled()
        if progress:
            progress(base + span * min(1.0, max(0.0, frac)), msg)
    return f


def _chunks(n, size=CHUNK):
    for s in range(0, n, size):
        yield s, min(n, s + size)


def _savetxt_chunked(f, arr, fmt, step):
    n = len(arr)
    for s, e in _chunks(n):
        np.savetxt(f, arr[s:e], fmt=fmt)
        step(e / max(1, n))


# ---------------------------------------------------------------------------- STL
def write_stl(path, mesh, ascii=False, progress=None, cancel=None):
    P, F = mesh.P, mesh.F
    n = len(F)
    step = _cb(progress, cancel, 0.0, 1.0)
    if ascii:
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write("solid nimcale\n")
            for s, e in _chunks(n, 100000):
                tri = P[F[s:e]]
                nn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
                nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-20)
                rows = np.concatenate([nn, tri.reshape(-1, 9)], axis=1)
                np.savetxt(f, rows, fmt=("facet normal %.6e %.6e %.6e\n outer loop\n  vertex %.6f %.6f %.6f\n"
                                         "  vertex %.6f %.6f %.6f\n  vertex %.6f %.6f %.6f\n endloop\nendfacet"))
                step(e / max(1, n))
            f.write("endsolid nimcale\n")
        return
    dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    with open(path, "wb") as f:
        f.write(("%s binary STL (mm)" % GENERATOR).encode("ascii")[:80].ljust(80, b" "))
        f.write(struct.pack("<I", n))
        for s, e in _chunks(n):
            tri = P[F[s:e]]
            nn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-20)
            rec = np.zeros(e - s, dtype=dt)
            rec["n"] = nn
            rec["v"] = tri
            f.write(rec.tobytes())
            step(e / max(1, n))


# ---------------------------------------------------------------------------- OBJ
def write_obj(path, mesh, texture=None, progress=None, cancel=None, mat_name="nimcale"):
    base = os.path.splitext(path)[0]
    mtl_path = base + ".mtl"
    png_name = os.path.basename(base) + ".png"
    if texture is not None:
        texture.save(base + ".png")
    with open(mtl_path, "w", encoding="utf-8") as f:
        f.write("# %s\nnewmtl %s\nKa 1 1 1\nKd 1 1 1\nKs 0.15 0.15 0.15\nNs 30\nd 1\nillum 2\n" % (GENERATOR, mat_name))
        if texture is not None:
            f.write("map_Kd %s\n" % png_name)
    P, F = mesh.P, mesh.F.astype(np.int64)
    step_v = _cb(progress, cancel, 0.0, 0.45)
    step_f = _cb(progress, cancel, 0.45, 0.55)
    nv = len(P)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# %s\n# units: millimetres\nmtllib %s\no nimcale\n" % (GENERATOR, os.path.basename(mtl_path)))
        _savetxt_chunked(f, P, "v %.5f %.5f %.5f", lambda x: step_v(x * 0.5))
        has_uv = mesh.UV is not None
        if has_uv:
            _savetxt_chunked(f, mesh.UV, "vt %.6f %.6f", lambda x: step_v(0.5 + x * 0.25))
        VN = mesh.VN if mesh.VN is not None else np.zeros((nv, 3), np.float32)
        nw0, nw1 = mesh.n_front, mesh.n_front + mesh.n_wall
        wall_n = mesh.face_normals()[nw0:nw1] if mesh.n_wall else np.zeros((0, 3), np.float32)
        _savetxt_chunked(f, np.concatenate([VN, wall_n]), "vn %.4f %.4f %.4f", lambda x: step_v(0.75 + x * 0.25))
        f.write("usemtl %s\ns 1\n" % mat_name)
        idx = F + 1
        ni = np.empty((len(F), 3), np.int64)
        ni[:] = idx
        if mesh.n_wall:
            ni[nw0:nw1] = (nv + 1 + np.arange(mesh.n_wall))[:, None]
        if has_uv:
            rows = np.stack([idx[:, 0], idx[:, 0], ni[:, 0], idx[:, 1], idx[:, 1], ni[:, 1],
                             idx[:, 2], idx[:, 2], ni[:, 2]], axis=1)
            _savetxt_chunked(f, rows, "f %d/%d/%d %d/%d/%d %d/%d/%d", step_f)
        else:
            rows = np.stack([idx[:, 0], ni[:, 0], idx[:, 1], ni[:, 1], idx[:, 2], ni[:, 2]], axis=1)
            _savetxt_chunked(f, rows, "f %d//%d %d//%d %d//%d", step_f)


# ---------------------------------------------------------------------------- glTF / GLB
def _pad4(b, pad=b"\0"):
    return b + pad * ((4 - len(b) % 4) % 4)


def _gltf_arrays(mesh):
    """Split vertices so that the side walls get flat normals."""
    P, F = mesh.P, mesh.F.astype(np.int64)
    VN = mesh.VN if mesh.VN is not None else np.tile(np.array([[0, 0, 1]], np.float32), (len(P), 1))
    UV = mesh.UV if mesh.UV is not None else np.zeros((len(P), 2), np.float32)
    nw0, nw1 = mesh.n_front, mesh.n_front + mesh.n_wall
    if mesh.n_wall:
        Fw = F[nw0:nw1]
        fn = mesh.face_normals()[nw0:nw1]
        Pw = P[Fw].reshape(-1, 3)
        Nw = np.repeat(fn, 3, axis=0)
        UVw = UV[Fw].reshape(-1, 2)
        base = len(P)
        Fw_new = (base + np.arange(len(Fw) * 3)).reshape(-1, 3)
        P = np.concatenate([P, Pw]); VN = np.concatenate([VN, Nw]); UV = np.concatenate([UV, UVw])
        F = np.concatenate([F[:nw0], Fw_new, F[nw1:]])
    UV = UV.astype(np.float32).copy()
    UV[:, 1] = 1.0 - UV[:, 1]
    # glTF is Y-up: rotate (x, y, z) -> (x, z, -y)
    P = np.stack([P[:, 0], P[:, 2], -P[:, 1]], 1)
    VN = np.stack([VN[:, 0], VN[:, 2], -VN[:, 1]], 1)
    return (np.ascontiguousarray(P, np.float32), np.ascontiguousarray(VN, np.float32),
            np.ascontiguousarray(UV, np.float32), np.ascontiguousarray(F, np.uint32))


def _gltf_doc(P, N, UV, F, png_len, bin_len, views, texture, uri=None):
    doc = {
        "asset": {"version": "2.0", "generator": GENERATOR},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "nimcale"}],
        "meshes": [{"name": "nimcale", "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                                                       "indices": 3, "material": 0, "mode": 4}]}],
        "materials": [{"name": "nimcale", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.7}}],
        "buffers": [{"byteLength": bin_len}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(P), "type": "VEC3",
             "min": P.min(0).tolist(), "max": P.max(0).tolist()},
            {"bufferView": 1, "componentType": 5126, "count": len(N), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": len(UV), "type": "VEC2"},
            {"bufferView": 3, "componentType": 5125, "count": int(F.size), "type": "SCALAR"},
        ],
    }
    if uri:
        doc["buffers"][0]["uri"] = uri
    if texture is not None:
        doc["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 0}
        doc["textures"] = [{"source": 0, "sampler": 0}]
        doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}]
    return doc


def write_gltf(path, mesh, texture=None, binary=True, progress=None, cancel=None):
    step = _cb(progress, cancel, 0.0, 1.0)
    P, N, UV, F = _gltf_arrays(mesh)
    step(0.3)
    pngb = b""
    if texture is not None:
        buf = io.BytesIO()
        texture.save(buf, "PNG")
        pngb = buf.getvalue()
    step(0.5)
    chunks = [P.tobytes(), N.tobytes(), UV.tobytes(), F.tobytes()]
    targets = [34962, 34962, 34962, 34963]
    if binary and pngb:
        chunks.append(pngb)
        targets.append(None)
    views, off, parts = [], 0, []
    for ch, tg in zip(chunks, targets):
        bv = {"buffer": 0, "byteOffset": off, "byteLength": len(ch)}
        if tg:
            bv["target"] = tg
        views.append(bv)
        padded = _pad4(ch)
        parts.append(padded)
        off += len(padded)
    blob = b"".join(parts)
    step(0.7)
    if binary:
        doc = _gltf_doc(P, N, UV, F, len(pngb), len(blob), views, texture)
        if texture is not None:
            doc["images"] = [{"bufferView": 4, "mimeType": "image/png"}]
        js = _pad4(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
        total = 12 + 8 + len(js) + 8 + len(blob)
        with open(path, "wb") as f:
            f.write(struct.pack("<4sII", b"glTF", 2, total))
            f.write(struct.pack("<I4s", len(js), b"JSON"))
            f.write(js)
            f.write(struct.pack("<I4s", len(blob), b"BIN\0"))
            f.write(blob)
    else:
        base = os.path.splitext(path)[0]
        bin_name = os.path.basename(base) + ".bin"
        with open(base + ".bin", "wb") as f:
            f.write(blob)
        doc = _gltf_doc(P, N, UV, F, 0, len(blob), views, texture, uri=bin_name)
        if texture is not None:
            png_name = os.path.basename(base) + ".png"
            with open(base + ".png", "wb") as f:
                f.write(pngb)
            doc["images"] = [{"uri": png_name, "mimeType": "image/png"}]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
    step(1.0)


# ---------------------------------------------------------------------------- PLY
def sample_colors(texture, UV):
    arr = np.asarray(texture.convert("RGB"), dtype=np.uint8)
    h, w = arr.shape[:2]
    x = np.clip((UV[:, 0] * w).astype(np.int64), 0, w - 1)
    y = np.clip(((1.0 - UV[:, 1]) * h).astype(np.int64), 0, h - 1)
    return arr[y, x]


def write_ply(path, mesh, texture=None, progress=None, cancel=None):
    step = _cb(progress, cancel, 0.0, 1.0)
    P, F = mesh.P, mesh.F
    nv, nf = len(P), len(F)
    has_c = texture is not None and mesh.UV is not None
    vdt = [("x", "<f4"), ("y", "<f4"), ("z", "<f4")]
    if mesh.VN is not None:
        vdt += [("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4")]
    if has_c:
        vdt += [("red", "u1"), ("green", "u1"), ("blue", "u1")]
    V = np.zeros(nv, dtype=vdt)
    V["x"], V["y"], V["z"] = P[:, 0], P[:, 1], P[:, 2]
    if mesh.VN is not None:
        V["nx"], V["ny"], V["nz"] = mesh.VN[:, 0], mesh.VN[:, 1], mesh.VN[:, 2]
    if has_c:
        C = sample_colors(texture, mesh.UV)
        V["red"], V["green"], V["blue"] = C[:, 0], C[:, 1], C[:, 2]
    step(0.3)
    props = "".join("property %s %s\n" % ({"<f4": "float", "u1": "uchar"}[t], n) for n, t in vdt)
    header = ("ply\nformat binary_little_endian 1.0\ncomment %s (units: mm)\nelement vertex %d\n%s"
              "element face %d\nproperty list uchar int vertex_indices\nend_header\n") % (GENERATOR, nv, props, nf)
    fdt = np.dtype([("n", "u1"), ("i", "<i4", 3)])
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        f.write(V.tobytes())
        for s, e in _chunks(nf):
            rec = np.zeros(e - s, dtype=fdt)
            rec["n"] = 3
            rec["i"] = F[s:e]
            f.write(rec.tobytes())
            step(0.3 + 0.7 * e / max(1, nf))


# ---------------------------------------------------------------------------- OFF
def write_off(path, mesh, progress=None, cancel=None):
    step = _cb(progress, cancel, 0.0, 1.0)
    with open(path, "w", encoding="ascii", newline="\n") as f:
        f.write("OFF\n# %s (units: mm)\n%d %d 0\n" % (GENERATOR, len(mesh.P), len(mesh.F)))
        _savetxt_chunked(f, mesh.P, "%.5f %.5f %.5f", lambda x: step(x * 0.4))
        _savetxt_chunked(f, mesh.F.astype(np.int64), "3 %d %d %d", lambda x: step(0.4 + x * 0.6))


# ---------------------------------------------------------------------------- 3MF
_3MF_TYPES = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
              '</Types>')
_3MF_RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
             'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')


def write_3mf(path, mesh, color="#B9A6D6", progress=None, cancel=None):
    step = _cb(progress, cancel, 0.0, 1.0)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as z:
        z.writestr("[Content_Types].xml", _3MF_TYPES)
        z.writestr("_rels/.rels", _3MF_RELS)
        with z.open("3D/3dmodel.model", "w", force_zip64=True) as raw:
            f = io.TextIOWrapper(raw, encoding="utf-8", newline="\n")
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<model unit="millimeter" xml:lang="en-US" '
                    'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
                    '<metadata name="Application">%s</metadata>\n<resources>\n'
                    '<basematerials id="1"><base name="Nimcale" displaycolor="%s"/></basematerials>\n'
                    '<object id="2" name="nimcale" type="model" pid="1" pindex="0">\n<mesh>\n<vertices>\n'
                    % (GENERATOR, color))
            _savetxt_chunked(f, mesh.P, '<vertex x="%.4f" y="%.4f" z="%.4f"/>', lambda x: step(x * 0.4))
            f.write("</vertices>\n<triangles>\n")
            _savetxt_chunked(f, mesh.F.astype(np.int64), '<triangle v1="%d" v2="%d" v3="%d"/>',
                             lambda x: step(0.4 + x * 0.6))
            f.write('</triangles>\n</mesh>\n</object>\n</resources>\n<build><item objectid="2"/></build>\n</model>\n')
            f.flush()
            f.detach()


# ---------------------------------------------------------------------------- images
def heightmap_png16(hf):
    """Plate field (row 0 = bottom) -> 16-bit grayscale PIL image, normalised to the full range."""
    a = np.asarray(hf, np.float32)[::-1]
    lo, hi = float(a.min()), float(a.max())
    a = (a - lo) / max(1e-9, hi - lo)
    return Image.fromarray((a * 65535.0 + 0.5).astype(np.uint16))


def normal_map(hf, size, depth, strength=1.0):
    a = np.asarray(hf, np.float32)
    h, w = a.shape
    dzdx = np.gradient(a * depth * strength, size[0] / max(1, w - 1), axis=1)
    dzdy = np.gradient(a * depth * strength, size[1] / max(1, h - 1), axis=0)
    n = np.stack([-dzdx, -dzdy, np.ones_like(a)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    rgb = ((n * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8)[::-1]
    return Image.fromarray(np.ascontiguousarray(rgb), "RGB")


# ---------------------------------------------------------------------------- registry
MESH_FORMATS = [
    # id, extension, needs texture, unit scale (per mm)
    ("stl", "stl", False, 1.0),
    ("stl_ascii", "stl", False, 1.0),
    ("obj", "obj", True, 1.0),
    ("glb", "glb", True, 0.001),
    ("gltf", "gltf", True, 0.001),
    ("ply", "ply", True, 1.0),
    ("3mf", "3mf", False, 1.0),
    ("off", "off", False, 1.0),
]
IMAGE_FORMATS = [("height_png", "png"), ("normal_png", "png"), ("texture_png", "png")]


def format_info(fid):
    for f in MESH_FORMATS:
        if f[0] == fid:
            return f
    return None


def write_mesh(fid, path, mesh, texture=None, progress=None, cancel=None):
    if fid == "stl":
        write_stl(path, mesh, False, progress, cancel)
    elif fid == "stl_ascii":
        write_stl(path, mesh, True, progress, cancel)
    elif fid == "obj":
        write_obj(path, mesh, texture, progress, cancel)
    elif fid == "glb":
        write_gltf(path, mesh, texture, True, progress, cancel)
    elif fid == "gltf":
        write_gltf(path, mesh, texture, False, progress, cancel)
    elif fid == "ply":
        write_ply(path, mesh, texture, progress, cancel)
    elif fid == "3mf":
        write_3mf(path, mesh, progress=progress, cancel=cancel)
    elif fid == "off":
        write_off(path, mesh, progress, cancel)
    else:
        raise ValueError("unknown format: %s" % fid)


def estimate_bytes(fid, n_tris):
    per = {"stl": 50, "stl_ascii": 260, "obj": 75, "glb": 60, "gltf": 60, "ply": 33, "3mf": 22, "off": 45}
    return int(per.get(fid, 50) * n_tris)
