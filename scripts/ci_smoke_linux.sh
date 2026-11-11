#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Smoke tests of the frozen Linux build, run under a virtual X server (xvfb-run) with Mesa.
# Each run fails on a non-zero exit code, a Python traceback or an error line in nimcale.log.
# usage: scripts/ci_smoke_linux.sh <folder with Nimcale binary> [AppImage] [screenshot dir]
set -uo pipefail
DIR="$(cd "${1:-dist/Nimcale}" && pwd)"
APPIMAGE="${2:-}"
SHOTS="${3:-$PWD}"
EXE="$DIR/Nimcale"
WORK="$(mktemp -d)"
PY="${PYTHON:-python3}"
export NIMCALE_NO_DIALOGS=1
FAILED=()
mkdir -p "$SHOTS"

run() {   # run <name> <cfg> <must-contain...> -- <args...>
    local name="$1" cfg="$WORK/$2"; shift 2
    local must=()
    while [ "$1" != "--" ]; do must+=("$1"); shift; done; shift
    mkdir -p "$cfg"
    echo "=== $name : $*"
    NIMCALE_CONFIG_DIR="$cfg" timeout 300 xvfb-run -a -s "-screen 0 1700x1100x24" "$@" > "$cfg/stdout.txt" 2>&1
    local code=$?
    local log="$cfg/nimcale.log"
    cat "$log" 2>/dev/null; cat "$cfg/stdout.txt"
    local errs=""
    [ $code -ne 0 ] && errs="$errs exit=$code;"
    for bad in "Traceback" "[error]" "ERROR:" "AttributeError" "Failed to load GLFW" "PROBE ERROR"; do
        grep -qF "$bad" "$log" "$cfg/stdout.txt" 2>/dev/null && errs="$errs log has '$bad';"
    done
    for m in "${must[@]}"; do
        grep -qF "$m" "$log" "$cfg/stdout.txt" 2>/dev/null || errs="$errs log lacks '$m';"
    done
    if [ -n "$errs" ]; then FAILED+=("$name:$errs"); echo "FAILED $name:$errs"; else echo "OK $name"; fi
}

check_png() {   # the screenshot exists and is not a blank / single-colour frame
    "$PY" - "$1" <<'PYEOF' || FAILED+=("screenshot $1 blank or missing")
import sys
from PIL import Image, ImageStat
im = Image.open(sys.argv[1]).convert("RGB")
sd = sum(ImageStat.Stat(im).stddev) / 3
print("screenshot", sys.argv[1], im.size, "stddev %.1f" % sd)
sys.exit(0 if im.size[0] >= 800 and sd > 10 else 1)
PYEOF
}

"$EXE" --version || FAILED+=("--version")

# 1) GL probes (software must work; GPU probe must give a real answer)
for mode in software gpu; do
    out="$WORK/probe_$mode.txt"
    extra=(); [ $mode = software ] && extra=(--software)
    NIMCALE_CONFIG_DIR="$WORK/cfg_probe" timeout 60 xvfb-run -a "$EXE" --probe-gl "${extra[@]}" --probe-out "$out"
    echo "$mode probe: $(cat "$out" 2>/dev/null)"
    grep -q "PROBE OK" "$out" 2>/dev/null || FAILED+=("$mode probe: $(cat "$out" 2>/dev/null)")
done

# 2) first start like a user (automatic renderer, default coin, no surface), then a second start
run "first start" cfg_user "renderer:" "OpenGL:" "title bar: mode=system" "quit-after:" -- "$EXE" --quit-after 90
run "second start (saved settings + layout)" cfg_user "renderer:" "OpenGL:" "quit-after:" -- "$EXE" --quit-after 90
grep -q "beta" "$WORK/cfg_user/nimcale.log" && grep -q "Test version" "$WORK/cfg_user/nimcale.log" && FAILED+=("stable build shows the test-version notice")

# 3) software renderer + screenshot of the main window
run "software + screenshot" cfg_sw "renderer: software" "OpenGL:" "shot:" -- \
    "$EXE" --software --frames 40 --size 1440x900 --shot "$SHOTS/ci_shot_linux.png"
check_png "$SHOTS/ci_shot_linux.png"

# 4) surface layer in the GUI (sample mug) + screenshot
run "surface sample" cfg_srf "Surface loaded" "shot:" -- \
    "$EXE" --surface mug --frames 40 --size 1440x900 --shot "$SHOTS/ci_shot_linux_surface.png"
check_png "$SHOTS/ci_shot_linux_surface.png"

# 5) non-GUI self test (plate mesh + every surface import format + watertight export)
run "selftest" cfg_self "'watertight': True" "selftest surface: obj:" "dae:" "watertight=True" -- "$EXE" --selftest

# 6) the AppImage starts too (extract-and-run: no FUSE on CI runners)
if [ -n "$APPIMAGE" ]; then
    chmod +x "$APPIMAGE"
    APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" --version || FAILED+=("AppImage --version")
    APPIMAGE_EXTRACT_AND_RUN=1 run "AppImage start" cfg_appimage "OpenGL:" "shot:" -- \
        env APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" --frames 30 --shot "$SHOTS/ci_shot_linux_appimage.png"
    check_png "$SHOTS/ci_shot_linux_appimage.png"
fi

rm -rf "$WORK"
if [ ${#FAILED[@]} -gt 0 ]; then
    echo; echo "SMOKE TEST FAILURES:"; printf ' - %s\n' "${FAILED[@]}"; exit 1
fi
echo; echo "All Linux smoke tests passed."
