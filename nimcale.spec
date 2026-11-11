# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# PyInstaller spec for Nimcale (one-folder build):
# Windows: dist/Nimcale/Nimcale.exe  (python scripts/fetch_mesa.py && pyinstaller --noconfirm nimcale.spec)
# Linux:   dist/Nimcale/Nimcale      (pyinstaller --noconfirm nimcale.spec && scripts/package_linux.sh)
import os
import sys
import imgui_bundle

WIN = sys.platform == "win32"

ROOT = os.path.abspath(SPECPATH)
IB = os.path.dirname(imgui_bundle.__file__)

datas = [
    (os.path.join(ROOT, "nimcale", "assets"), "nimcale/assets"),
    (os.path.join(ROOT, "nimcale", "i18n", "locales"), "nimcale/i18n/locales"),
    (os.path.join(ROOT, "LICENSE"), "."),
    (os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), "."),
]
from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = []
# imgui-bundle's own GLFW (used by the window) - pyGLFW is pointed at this same file at run time
for name in ("glfw3.dll", "libglfw.so.3", "libglfw.3.dylib"):
    p = os.path.join(IB, name)
    if os.path.exists(p):
        binaries.append((p, "imgui_bundle"))
# pyGLFW's bundled DLLs (glfw/glfw3.dll, msvcr120.dll): loaded with ctypes, so PyInstaller misses them
binaries += collect_dynamic_libs("glfw", destdir="glfw")
if not any(os.path.basename(b[0]).lower().startswith(("glfw3", "libglfw")) for b in binaries):
    raise SystemExit("nimcale.spec: no GLFW shared library found - the GPU probe would fail")

# Mesa llvmpipe software OpenGL (optional). Kept in its own "mesa" folder so the real GPU driver
# is used by default; Nimcale loads it only in software mode.
mesa = os.path.join(ROOT, "third_party", "mesa")
if WIN and os.path.isdir(mesa):
    for f in os.listdir(mesa):
        datas.append((os.path.join(mesa, f), "mesa"))

hiddenimports = ["glcontext", "moderngl", "fast_simplification", "scipy.ndimage", "scipy.special._cdflib",
                 "PIL.WebPImagePlugin", "glfw"]
# surface layer (3D model import): trimesh loads its exchange modules lazily and needs its resources
# (glTF / 3MF schemas); pycollada reads .dae; lxml + networkx are used by the 3MF loader
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
hiddenimports += collect_submodules("trimesh.exchange") + collect_submodules("collada") +     ["trimesh", "networkx", "lxml.etree", "dateutil"]
datas += collect_data_files("trimesh") + collect_data_files("collada")

a = Analysis(
    [os.path.join(ROOT, "scripts", "nimcale_entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "pandas", "PyQt5", "PySide6",
              "imgui_bundle.demos_python", "pydantic"],
    noarchive=False,
)
if not WIN:
    # use the system C++ runtime: the user's Mesa / GPU drivers need it at least as new as they were built with
    a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).startswith(("libstdc++.so", "libgcc_s.so"))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Nimcale",
    icon=os.path.join(ROOT, "nimcale", "assets", "icons", "nimcale.ico") if WIN else None,
    version=os.path.join(ROOT, "scripts", "version_info.txt") if WIN else None,
    console=False,
    debug=False,
    strip=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Nimcale")
