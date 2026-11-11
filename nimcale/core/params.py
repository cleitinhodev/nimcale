# SPDX-License-Identifier: GPL-3.0-or-later
"""Model and view parameters.

Internal unit: the longest side of the plate (after crop/rotation) is 1.0.
Physical size in millimetres = value * size_mm.
"""
from dataclasses import dataclass, field, fields, asdict
import math

SHAPES = ("auto", "circle", "ellipse", "rounded", "hexagon", "octagon")
MATERIALS = ("original", "silver", "gold", "bronze", "copper", "clay", "jade", "amethyst")
# name -> (tint rgb, metallic, roughness)
MATERIAL_DEFS = {
    "original": ((1.00, 1.00, 1.00), 0.00, 0.55),
    "silver":   ((0.94, 0.93, 0.98), 0.85, 0.32),
    "gold":     ((1.00, 0.80, 0.42), 0.90, 0.30),
    "bronze":   ((0.86, 0.58, 0.36), 0.80, 0.40),
    "copper":   ((0.98, 0.62, 0.50), 0.85, 0.34),
    "clay":     ((0.86, 0.80, 0.74), 0.00, 0.85),
    "jade":     ((0.55, 0.88, 0.70), 0.15, 0.30),
    "amethyst": ((0.80, 0.55, 1.00), 0.35, 0.28),
}


@dataclass
class ModelParams:
    # --- relief
    depth: float = 0.045          # relief height (fraction of the longest side)
    thickness: float = 0.035      # base thickness below the relief
    blur: float = 1.0             # smoothing (pixels of the original image)
    threshold: float = 0.08       # background threshold (automatic outline / invert)
    brightness: float = 0.0
    contrast: float = 1.0
    gamma: float = 1.0
    level_lo: float = 0.0
    level_hi: float = 1.0
    invert: bool = False
    detail: float = 0.0           # unsharp-mask amount (detail enhancement)
    detail_radius: float = 6.0    # pixels of the original image
    noise_amp: float = 0.0
    noise_scale: float = 60.0     # noise cells across the plate
    noise_seed: int = 7
    mesh_res: int = 600           # preview mesh cells on the longest side
    # --- shape / outline
    cutout: bool = True
    shape: str = "circle"
    shape_cx: float = 0.0         # plate units, 0 = centre
    shape_cy: float = 0.0
    shape_rx: float = 0.47
    shape_ry: float = 0.47
    shape_round: float = 0.25     # corner radius (rounded rectangle), fraction of the smaller half side
    shape_rot: float = 0.0        # degrees
    smooth_edge: bool = True
    # --- automatic outline (shape == "auto"), see core/cutout.py
    outline_src: str = "auto"     # auto | height | tex_alpha | tex_color
    bg_mode: str = "auto"         # auto | dark | white | transparent | color
    bg_r: float = 1.0             # picked background colour (bg_mode == "color")
    bg_g: float = 1.0
    bg_b: float = 1.0
    mask_smooth: float = 0.0      # smoothing of the outline mask (original px)
    mask_feather: float = 0.0     # extra softness of the outline edge (original px)
    mask_grow: float = 0.0        # grow (+) / shrink (-) the outline (original px)
    fill_holes: bool = True
    min_island: float = 0.05      # remove separate pieces smaller than this % of the image
    keep_largest: bool = False
    # --- coin edge
    rim_width: float = 0.0
    rim_height: float = 0.0
    bevel: float = 0.0
    # --- transform (applied to height map and texture together)
    flip_x: bool = False
    flip_y: bool = False
    rot90: int = 0
    crop_l: float = 0.0
    crop_r: float = 0.0
    crop_t: float = 0.0
    crop_b: float = 0.0
    # --- texture alignment (relative to the source height map)
    fit: int = 1
    sx: float = 1.0
    sy: float = 1.0
    ox: float = 0.0
    oy: float = 0.0
    rot: float = 0.0
    # --- real world
    size_mm: float = 40.0
    # --- surface layer (core/surface.py): texture + relief on an imported 3D model
    srf_proj: str = "auto"        # auto | uv | cylinder | sphere | planar | box | decal
    srf_axis: str = "top"         # front | back | left | right | top | bottom
    srf_ou: float = 0.0           # offset of the image (fraction of its width / height)
    srf_ov: float = 0.0
    srf_scale: float = 1.0
    srf_sx: float = 1.0           # width proportion
    srf_sy: float = 1.0           # height proportion (when not locked)
    srf_lock: bool = True         # keep the image proportion
    srf_rot: float = 0.0          # degrees
    srf_seam: float = 0.0         # degrees (cylinder / sphere: where the image starts)
    srf_tile: bool = False        # repeat the image instead of a single copy
    srf_mirror: bool = False
    srf_use_cut: bool = False     # use the plate outline (cutout) as the decal mask
    srf_fit: str = "stretch"      # stretch (cover the whole side) | width (around, keep proportion) | height
    srf_outer: bool = True        # cylinder: only the outer wall (not the inside of cups)
    srf_caps: bool = False        # cylinder: also the top / bottom faces
    srf_detail: int = 320         # preview relief samples across the image (subdivision density)
    srf_up: str = "auto"          # auto | z | y | x  (up axis of the file)
    srf_rx: float = 0.0           # model rotation (degrees)
    srf_ry: float = 0.0
    srf_rz: float = 0.0
    srf_size: float = 80.0        # model size: longest side (mm)
    srf_r: float = 0.86           # model colour where the image does not cover it
    srf_g: float = 0.84
    srf_b: float = 0.88

    def copy(self):
        return ModelParams(**asdict(self))

    def key(self):
        return tuple(getattr(self, f.name) for f in fields(self))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        p = cls()
        p.update(d)
        return p

    def update(self, d):
        for f in fields(self):
            if f.name in d:
                v = d[f.name]
                try:
                    if f.type in (bool, "bool"):
                        v = bool(v)
                    elif f.type in (int, "int"):
                        v = int(v)
                    elif f.type in (float, "float"):
                        v = float(v)
                    else:
                        v = str(v)
                except (TypeError, ValueError):
                    continue
                setattr(self, f.name, v)
        if self.shape not in SHAPES:
            self.shape = "auto"
        if self.outline_src not in ("auto", "height", "tex_alpha", "tex_color"):
            self.outline_src = "auto"
        if self.bg_mode not in ("auto", "dark", "white", "transparent", "color"):
            self.bg_mode = "auto"
        self.rot90 %= 4
        from nimcale.core.surface import PROJECTIONS, AXES
        if self.srf_proj not in PROJECTIONS:
            self.srf_proj = "auto"
        if self.srf_axis not in AXES:
            self.srf_axis = "top"
        if self.srf_fit not in ("stretch", "width", "height"):
            self.srf_fit = "stretch"
        if self.srf_up not in ("auto", "z", "y", "x"):
            self.srf_up = "auto"

    def align_dict(self):
        return dict(fit=self.fit, sx=self.sx, sy=self.sy, ox=self.ox, oy=self.oy, rot=self.rot)

    def reset_align(self):
        d = ModelParams()
        self.sx, self.sy, self.ox, self.oy, self.rot = d.sx, d.sy, d.ox, d.oy, d.rot


@dataclass
class ViewParams:
    mode: int = 2                 # 0 texture, 1 height, 2 mix
    mix: float = 0.5
    material: str = "silver"
    lit: bool = True
    show_outline: bool = True     # outline overlay in the Shape tab preview
    wire: bool = False
    axes: bool = False
    grid: bool = False
    dims: bool = False
    ao: float = 0.6
    light_int: float = 1.1
    ambient: float = 0.30
    spec: float = 1.0
    light_phi: float = 125.0
    light_theta: float = 48.0
    bg_mode: int = 0              # 0 gradient, 1 solid
    bg: list = field(default_factory=lambda: [0.07, 0.04, 0.11])
    bg2: list = field(default_factory=lambda: [0.20, 0.07, 0.27])
    turntable: bool = False
    turntable_speed: float = 25.0
    yaw: float = math.radians(-18.0)
    pitch: float = math.radians(-24.0)
    dist: float = 2.25
    pan: list = field(default_factory=lambda: [0.0, 0.0])
    fov: float = 32.0

    def to_dict(self):
        return asdict(self)

    def update(self, d):
        for f in fields(self):
            if f.name in d:
                setattr(self, f.name, d[f.name])
        if self.material not in MATERIALS:
            self.material = "original"

    def reset_camera(self):
        d = ViewParams()
        self.yaw, self.pitch, self.dist, self.pan, self.fov = d.yaw, d.pitch, d.dist, [0.0, 0.0], d.fov


BG_PRESETS = [
    ((0.07, 0.04, 0.11), (0.20, 0.07, 0.27)),   # Nimcale night
    ((0.02, 0.02, 0.03), (0.10, 0.04, 0.16)),
    ((0.16, 0.05, 0.20), (0.45, 0.12, 0.40)),   # neon rose
    ((0.09, 0.10, 0.13), (0.09, 0.10, 0.13)),
    ((0.35, 0.37, 0.42), (0.55, 0.57, 0.62)),
    ((0.92, 0.90, 0.95), (0.75, 0.70, 0.85)),
    ((1.0, 1.0, 1.0), (1.0, 1.0, 1.0)),
    ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
]
