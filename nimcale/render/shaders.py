# SPDX-License-Identifier: GPL-3.0-or-later
"""GLSL 3.30 core shaders."""

MODEL_VERT = """
#version 330
uniform mat4  u_mvp;
uniform sampler2D u_height;
uniform vec2  u_hdim;
uniform float u_hscale;
uniform float u_thick;
uniform vec2  u_size;
uniform int   u_kind;      // 0 front, 1 bottom, 2 walls, 3 wire overlay
in vec2  in_uv;
in float in_top;
in vec3  in_nrm;
out vec2  v_uv;
out vec3  v_pos;
out vec3  v_nrm;
out float v_top;
vec2 node(vec2 uv) { return (uv * (u_hdim - 1.0) + 0.5) / u_hdim; }
void main() {
    float top = (u_kind == 0 || u_kind == 3) ? 1.0 : ((u_kind == 1) ? 0.0 : in_top);
    float h = textureLod(u_height, node(in_uv), 0.0).r;
    float z = (top > 0.5) ? h * u_hscale : -u_thick;
    vec3 p = vec3((in_uv - 0.5) * u_size, z);
    v_uv = in_uv;
    v_pos = p;
    v_nrm = in_nrm;
    v_top = top;
    gl_Position = u_mvp * vec4(p, 1.0);
    if (u_kind == 3) gl_Position.z -= 0.0012 * gl_Position.w;
}
"""

MODEL_FRAG = """
#version 330
uniform sampler2D u_height;
uniform sampler2D u_tex;
uniform vec2  u_hdim;
uniform vec2  u_size;
uniform float u_hscale;
uniform mat3  u_plate2src;
uniform vec2  u_srcsize;
uniform vec2  u_tc;
uniform vec2  u_ts;
uniform float u_rot;
uniform vec3  u_outcol;
uniform int   u_mode;
uniform float u_mix;
uniform int   u_unlit;
uniform int   u_kind;
uniform vec3  u_light;
uniform vec3  u_cam;
uniform float u_lint;
uniform float u_amb;
uniform float u_specmul;
uniform vec3  u_tint;
uniform float u_metal;
uniform float u_rough;
uniform float u_ao;
uniform vec4  u_brush;      // u, v, radius (plate units), enabled
uniform vec3  u_brushcol;
uniform vec3  u_env_top;
uniform vec3  u_env_bot;
uniform vec4  u_wirecol;
in vec2  v_uv;
in vec3  v_pos;
in vec3  v_nrm;
in float v_top;
out vec4 f_color;

vec2 node(vec2 uv) { return (uv * (u_hdim - 1.0) + 0.5) / u_hdim; }

vec3 texcolor(vec2 uv) {
    vec2 src = (u_plate2src * vec3(uv, 1.0)).xy;
    vec2 p = (src - u_tc) * u_srcsize;
    float cr = cos(u_rot), sr = sin(u_rot);
    vec2 q = vec2(cr * p.x + sr * p.y, -sr * p.x + cr * p.y);
    vec2 tuv = q / (u_srcsize * u_ts) + 0.5;
    vec3 tc = texture(u_tex, tuv).rgb;
    vec2 od = max(-tuv, tuv - 1.0);
    float ow = smoothstep(0.0, 0.03, max(od.x, od.y));
    return mix(tc, u_outcol, ow);
}

void main() {
    if (u_kind == 3) { f_color = u_wirecol; return; }
    vec2 nuv = node(v_uv);
    vec2 hv = texture(u_height, nuv).rg;
    float h = hv.r;
    vec3 tc = texcolor(v_uv);
    vec3 n;
    vec3 base;
    float ao = 1.0;
    if (u_kind == 0) {
        vec2 e = 1.0 / u_hdim;
        float hl = texture(u_height, nuv - vec2(e.x, 0.0)).r;
        float hr = texture(u_height, nuv + vec2(e.x, 0.0)).r;
        float hd = texture(u_height, nuv - vec2(0.0, e.y)).r;
        float hu = texture(u_height, nuv + vec2(0.0, e.y)).r;
        float dhx = (hr - hl) * u_hscale / (2.0 * e.x * u_size.x);
        float dhy = (hu - hd) * u_hscale / (2.0 * e.y * u_size.y);
        n = normalize(vec3(-dhx, -dhy, 1.0));
        float g = clamp(h, 0.0, 1.0);
        if (u_mode == 0)      base = tc;
        else if (u_mode == 1) base = vec3(0.80, 0.78, 0.82);
        else                  base = mix(tc, vec3(g), u_mix);
        ao = mix(1.0, hv.g, u_ao);
    } else if (u_kind == 1) {
        n = vec3(0.0, 0.0, -1.0);
        base = vec3(0.42, 0.40, 0.45);
    } else {
        n = normalize(v_nrm);
        base = (u_mode == 1) ? vec3(0.66, 0.64, 0.68) : mix(tc, vec3(0.75), (u_mode == 2) ? u_mix : 0.0) * 0.85;
        ao = mix(1.0, 0.75 + 0.25 * v_top, u_ao);
    }
    vec3 albedo = base * u_tint;
    vec3 col;
    if (u_unlit == 1) {
        col = albedo;
    } else {
        vec3 L = normalize(u_light);
        vec3 V = normalize(u_cam - v_pos);
        vec3 H = normalize(L + V);
        float diff = max(dot(n, L), 0.0);
        float shin = mix(220.0, 10.0, clamp(u_rough, 0.0, 1.0));
        float spec = (diff > 0.0) ? pow(max(dot(n, H), 0.0), shin) * (shin + 8.0) / 60.0 : 0.0;
        vec3 F0 = mix(vec3(0.045), albedo, u_metal);
        float fres = pow(1.0 - max(dot(n, V), 0.0), 5.0);
        vec3 F = F0 + (1.0 - F0) * fres * (1.0 - u_rough) * 0.6;
        vec3 R = reflect(-V, n);
        vec3 env = mix(u_env_bot, u_env_top, clamp(R.z * 0.5 + 0.5 + R.y * 0.25, 0.0, 1.0));
        vec3 diffuse = albedo * (1.0 - u_metal) * (u_amb * ao + 0.9 * diff * u_lint * mix(0.6, 1.0, ao));
        vec3 envc = env * F * (0.35 + 0.65 * u_metal) * ao * 1.4;
        vec3 metalc = albedo * u_metal * (u_amb * 0.9 * ao + 0.75 * diff * u_lint);
        col = diffuse + metalc + envc + F * spec * u_lint * u_specmul;
    }
    if (u_brush.w > 0.5 && u_kind == 0) {
        float d = length((v_uv - u_brush.xy) * u_size);
        float r = u_brush.z;
        float px = fwidth(d) * 1.5;
        float ring = 1.0 - smoothstep(px * 0.5, px * 1.5, abs(d - r));
        float fill = (d < r) ? 0.10 : 0.0;
        col = mix(col, u_brushcol, clamp(ring * 0.95 + fill, 0.0, 1.0));
    }
    f_color = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""

BG_VERT = """
#version 330
out vec2 v_uv;
void main() {
    vec2 p = vec2((gl_VertexID == 1) ? 3.0 : -1.0, (gl_VertexID == 2) ? 3.0 : -1.0);
    v_uv = p * 0.5 + 0.5;
    gl_Position = vec4(p, 0.999, 1.0);
}
"""

BG_FRAG = """
#version 330
uniform vec3 u_c0;
uniform vec3 u_c1;
uniform float u_time;
uniform int u_anim;
uniform vec2 u_res;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec2 uv = v_uv;
    float t = (u_anim == 1) ? u_time : 0.0;
    float g = uv.y;
    vec3 col = mix(u_c0, u_c1, smoothstep(0.0, 1.0, g));
    if (u_anim == 1) {
        vec2 a = vec2(0.5 + 0.35 * cos(t * 0.21), 0.55 + 0.25 * sin(t * 0.17));
        vec2 b = vec2(0.5 + 0.40 * sin(t * 0.13 + 1.7), 0.35 + 0.20 * cos(t * 0.19 + 0.4));
        float asp = u_res.x / max(1.0, u_res.y);
        vec2 da = (uv - a) * vec2(asp, 1.0);
        vec2 db = (uv - b) * vec2(asp, 1.0);
        col += vec3(0.55, 0.15, 0.85) * 0.22 * exp(-dot(da, da) * 3.0);
        col += vec3(0.95, 0.25, 0.75) * 0.16 * exp(-dot(db, db) * 4.0);
    }
    float vig = smoothstep(1.25, 0.35, length(uv - 0.5));
    col *= mix(0.78, 1.0, vig);
    // tiny dithering against banding
    float n = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453);
    col += (n - 0.5) / 255.0;
    f_color = vec4(col, 1.0);
}
"""

LINE_VERT = """
#version 330
uniform mat4 u_mvp;
in vec3 in_pos;
in vec4 in_col;
out vec4 v_col;
void main() { gl_Position = u_mvp * vec4(in_pos, 1.0); v_col = in_col; }
"""

LINE_FRAG = """
#version 330
in vec4 v_col;
out vec4 f_color;
void main() { f_color = v_col; }
"""

# ---------------------------------------------------------------------------- surface layer (imported model)
SURF_VERT = """
#version 330
uniform mat4  u_mvp;
uniform mat4  u_model;      // mm -> view units (scale + centring + upright)
uniform mat3  u_nrot;
in vec3  in_pos;
in vec3  in_nrm;
in vec2  in_uv;
in float in_w;
in float in_h;
out vec3  v_pos;
out vec3  v_nrm;
out vec2  v_uv;
out float v_w;
out float v_h;
void main() {
    vec4 p = u_model * vec4(in_pos, 1.0);
    v_pos = p.xyz;
    v_nrm = u_nrot * in_nrm;
    v_uv = in_uv;
    v_w = in_w;
    v_h = in_h;
    gl_Position = u_mvp * p;
}
"""

SURF_FRAG = """
#version 330
uniform sampler2D u_tex;
uniform mat3  u_plate2src;
uniform vec2  u_srcsize;
uniform vec2  u_tc;
uniform vec2  u_ts;
uniform float u_rot;
uniform vec3  u_outcol;
uniform int   u_mode;
uniform float u_mix;
uniform int   u_unlit;
uniform int   u_tile;
uniform vec3  u_base;
uniform vec3  u_light;
uniform vec3  u_cam;
uniform float u_lint;
uniform float u_amb;
uniform float u_specmul;
uniform vec3  u_tint;
uniform float u_metal;
uniform float u_rough;
uniform vec3  u_env_top;
uniform vec3  u_env_bot;
uniform int   u_wire;
uniform vec4  u_wirecol;
in vec3  v_pos;
in vec3  v_nrm;
in vec2  v_uv;
in float v_w;
in float v_h;
out vec4 f_color;

vec3 texcolor(vec2 uv) {
    vec2 src = (u_plate2src * vec3(uv, 1.0)).xy;
    vec2 p = (src - u_tc) * u_srcsize;
    float cr = cos(u_rot), sr = sin(u_rot);
    vec2 q = vec2(cr * p.x + sr * p.y, -sr * p.x + cr * p.y);
    vec2 tuv = q / (u_srcsize * u_ts) + 0.5;
    vec3 tc = texture(u_tex, tuv).rgb;
    vec2 od = max(-tuv, tuv - 1.0);
    float ow = smoothstep(0.0, 0.03, max(od.x, od.y));
    return mix(tc, u_outcol, ow);
}

void main() {
    if (u_wire == 1) { f_color = u_wirecol; return; }
    vec3 n = normalize(v_nrm);
    if (!gl_FrontFacing) n = -n;
    vec2 uv = (u_tile == 1) ? fract(v_uv) : v_uv;
    vec3 base = u_base;
    if (v_w > 0.5) {
        vec3 tc = texcolor(uv);
        float g = clamp(v_h, 0.0, 1.0);
        if (u_mode == 0)      base = tc;
        else if (u_mode == 1) base = vec3(0.80, 0.78, 0.82);
        else                  base = mix(tc, vec3(g), u_mix);
    } else if (u_mode == 1) {
        base = vec3(0.70, 0.68, 0.72);
    }
    vec3 albedo = base * u_tint;
    vec3 col;
    if (u_unlit == 1) {
        col = albedo;
    } else {
        vec3 L = normalize(u_light);
        vec3 V = normalize(u_cam - v_pos);
        vec3 H = normalize(L + V);
        float diff = max(dot(n, L), 0.0);
        float shin = mix(220.0, 10.0, clamp(u_rough, 0.0, 1.0));
        float spec = (diff > 0.0) ? pow(max(dot(n, H), 0.0), shin) * (shin + 8.0) / 60.0 : 0.0;
        vec3 F0 = mix(vec3(0.045), albedo, u_metal);
        float fres = pow(1.0 - max(dot(n, V), 0.0), 5.0);
        vec3 F = F0 + (1.0 - F0) * fres * (1.0 - u_rough) * 0.6;
        vec3 R = reflect(-V, n);
        vec3 env = mix(u_env_bot, u_env_top, clamp(R.z * 0.5 + 0.5 + R.y * 0.25, 0.0, 1.0));
        vec3 diffuse = albedo * (1.0 - u_metal) * (u_amb + 0.9 * diff * u_lint);
        vec3 envc = env * F * (0.35 + 0.65 * u_metal) * 1.4;
        vec3 metalc = albedo * u_metal * (u_amb * 0.9 + 0.75 * diff * u_lint);
        col = diffuse + metalc + envc + F * spec * u_lint * u_specmul;
    }
    f_color = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""
