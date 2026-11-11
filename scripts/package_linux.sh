#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Package the PyInstaller one-folder build (dist/Nimcale) for Linux x86_64:
#   Nimcale-<ver>-linux-x86_64.tar.gz   folder with the program, icons, .desktop file and install.sh
#   Nimcale-<ver>-x86_64.AppImage       single file (needs appimagetool; skipped with --no-appimage)
# usage: scripts/package_linux.sh [dist_dir] [out_dir] [--no-appimage]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="${1:-$ROOT/dist/Nimcale}"
OUT="${2:-$ROOT}"
APPIMAGE=1
for a in "$@"; do [ "$a" = "--no-appimage" ] && APPIMAGE=0; done
PY="${PYTHON:-python3}"
VER="$(cd "$ROOT" && "$PY" -c 'import nimcale; print(nimcale.__version__)')"
NAME="Nimcale-$VER-linux-x86_64"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
[ -x "$DIST/Nimcale" ] || { echo "no build at $DIST (run PyInstaller first)"; exit 1; }

# icons in the usual sizes
mkdir -p "$WORK/icons"
"$PY" - "$ROOT/nimcale/assets/icons/nimcale_icon_512.png" "$WORK/icons" <<'PYEOF'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGBA")
for s in (64, 128, 256, 512):
    im.resize((s, s), Image.LANCZOS).save("%s/nimcale_%d.png" % (sys.argv[2], s))
PYEOF

# ---- tar.gz: Nimcale-<ver>-linux-x86_64/{Nimcale,_internal,nimcale.desktop,nimcale.png,icons,install.sh}
T="$WORK/$NAME"
cp -a "$DIST" "$T"
cp "$ROOT/packaging/linux/nimcale.desktop" "$T/"
cp "$ROOT/packaging/linux/install.sh" "$T/"
cp -r "$WORK/icons" "$T/icons"
cp "$WORK/icons/nimcale_256.png" "$T/nimcale.png"
cp "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$T/" 2>/dev/null || true
cat > "$T/LEIA-ME_README.txt" <<TXT
Nimcale $VER - Linux x86_64

PT: Execute ./Nimcale (se preciso: chmod +x Nimcale). Para adicionar ao menu de aplicativos: ./install.sh
    Configurações e log: ~/.config/Nimcale   Exportações: ~/Documents/Nimcale (ou ~/Nimcale)
EN: Run ./Nimcale (if needed: chmod +x Nimcale). To add it to the application menu: ./install.sh
    Settings and log: ~/.config/Nimcale   Exports: ~/Documents/Nimcale (or ~/Nimcale)

Requires glibc 2.35+ (Ubuntu 22.04, Debian 12, Fedora 36, Mint 21 or newer) and OpenGL 3.3
(Mesa or the GPU vendor driver). Without a working GPU driver: ./Nimcale --software
Website: https://www.bugzinho.com/  Project: https://github.com/cleitinhodev/nimcale  Donate: https://www.bugzinho.com/donate
TXT
chmod +x "$T/Nimcale" "$T/install.sh"
tar -C "$WORK" -czf "$OUT/$NAME.tar.gz" "$NAME"
echo "tar.gz: $OUT/$NAME.tar.gz ($(du -h "$OUT/$NAME.tar.gz" | cut -f1))"

# ---- AppImage
if [ "$APPIMAGE" = 1 ]; then
    TOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
    if [ -z "$TOOL" ]; then
        echo "appimagetool not found: AppImage skipped"; exit 0
    fi
    A="$WORK/Nimcale.AppDir"
    mkdir -p "$A/usr/lib" "$A/usr/share/applications"
    cp -a "$DIST" "$A/usr/lib/nimcale"
    for s in 64 128 256 512; do
        mkdir -p "$A/usr/share/icons/hicolor/${s}x${s}/apps"
        cp "$WORK/icons/nimcale_$s.png" "$A/usr/share/icons/hicolor/${s}x${s}/apps/nimcale.png"
    done
    cp "$WORK/icons/nimcale_256.png" "$A/nimcale.png"
    cp "$WORK/icons/nimcale_256.png" "$A/.DirIcon"
    sed -e 's|^TryExec=.*||' "$ROOT/packaging/linux/nimcale.desktop" | sed '/^$/d' > "$A/nimcale.desktop"
    cp "$A/nimcale.desktop" "$A/usr/share/applications/"
    cat > "$A/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/nimcale/Nimcale" "$@"
RUN
    chmod +x "$A/AppRun"
    ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$A" "$OUT/Nimcale-$VER-x86_64.AppImage"
    chmod +x "$OUT/Nimcale-$VER-x86_64.AppImage"
    echo "AppImage: $OUT/Nimcale-$VER-x86_64.AppImage ($(du -h "$OUT/Nimcale-$VER-x86_64.AppImage" | cut -f1))"
fi
