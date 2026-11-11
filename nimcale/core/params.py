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
        self.rot90 %= 4

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
