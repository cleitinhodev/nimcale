#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Cross-build the Windows release on Linux with Wine + Windows Python.
#   WINPY  Windows python.exe inside the Wine prefix (default: C:/nimcale_venv/Scripts/python.exe)
# The venv must already contain: pip install -r requirements.txt pyinstaller
# Needs 7z/7zz on PATH (Mesa download) and zip.
set -euo pipefail
cd "$(dirname "$0")/.."
WINPY="${WINPY:-C:/nimcale_venv/Scripts/python.exe}"
export WINEDEBUG=-all
python3 scripts/fetch_mesa.py
rm -rf build/Nimcale dist/Nimcale
wine "$WINPY" -m PyInstaller --noconfirm --clean nimcale.spec
VER=$(python3 -c "import nimcale; print(nimcale.__version__)")
ZIP="dist/Nimcale-${VER}-windows-x64.zip"
rm -f "$ZIP"
(cd dist && zip -qr9 "$(basename "$ZIP")" Nimcale)
echo "OK -> $ZIP ($(du -h "$ZIP" | cut -f1))"
