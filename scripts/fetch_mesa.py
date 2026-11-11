#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Download the Mesa3D llvmpipe OpenGL DLLs for Windows (software fallback renderer).

Source: https://github.com/pal1000/mesa-dist-win (MIT licensed Mesa builds).
Result: third_party/mesa/{opengl32.dll, libgallium_wgl.dll, MESA_LICENSE.txt}
Needs a 7-Zip executable (7z / 7zz / 7za) on PATH or in the default Windows location
(the archive uses the BCJ2 filter, which pure-Python extractors do not support).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

VERSION = os.environ.get("NIMCALE_MESA_VERSION", "26.2.5")
URL = "https://github.com/pal1000/mesa-dist-win/releases/download/{v}/mesa3d-{v}-release-msvc.7z"
FILES = ("opengl32.dll", "libgallium_wgl.dll")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "third_party", "mesa")

MESA_LICENSE = """Mesa 3-D graphics library  (https://www.mesa3d.org/)
Windows build by pal1000/mesa-dist-win (https://github.com/pal1000/mesa-dist-win), version %s

Copyright (C) 1999-2007  Brian Paul   All Rights Reserved.
Copyright (C) The Mesa 3D contributors.

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

LLVM (used by llvmpipe) is distributed under the Apache License v2.0 with LLVM Exceptions.
"""


def find_7z():
    for name in ("7z", "7zz", "7za"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if os.path.exists(p):
            return p
    return None


def main():
    if all(os.path.exists(os.path.join(DEST, f)) for f in FILES):
        print("Mesa already present in", DEST)
        return 0
    sz = find_7z()
    if not sz:
        print("ERROR: 7-Zip not found (install 7-Zip or put 7z/7zz on PATH)")
        return 1
    tmp = tempfile.mkdtemp(prefix="nimcale_mesa_")
    arc = os.path.join(tmp, "mesa.7z")
    url = URL.format(v=VERSION)
    print("downloading", url)
    urllib.request.urlretrieve(url, arc)
    subprocess.check_call([sz, "x", "-y", "-o" + tmp, arc] + ["x64/" + f for f in FILES],
                          stdout=subprocess.DEVNULL)
    os.makedirs(DEST, exist_ok=True)
    for f in FILES:
        shutil.copy2(os.path.join(tmp, "x64", f), os.path.join(DEST, f))
    with open(os.path.join(DEST, "MESA_LICENSE.txt"), "w", encoding="utf-8") as fh:
        fh.write(MESA_LICENSE % VERSION)
    shutil.rmtree(tmp, ignore_errors=True)
    print("Mesa %s ->" % VERSION, DEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
