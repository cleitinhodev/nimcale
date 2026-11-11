#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Adds Nimcale to your application menu (current user only, no root needed):
#   ~/.local/share/applications/nimcale.desktop  +  icons in ~/.local/share/icons/hicolor
# Run it again after moving this folder. Remove with:  ./install.sh --uninstall
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS="$DATA/applications"
ICONS="$DATA/icons/hicolor"
if [ "$1" = "--uninstall" ]; then
    rm -f "$APPS/nimcale.desktop"
    for s in 64 128 256 512; do rm -f "$ICONS/${s}x${s}/apps/nimcale.png"; done
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" || true
    echo "Nimcale removed from the application menu (this folder was not touched)."
    exit 0
fi
chmod +x "$HERE/Nimcale"
mkdir -p "$APPS"
for s in 64 128 256 512; do
    if [ -f "$HERE/icons/nimcale_${s}.png" ]; then
        mkdir -p "$ICONS/${s}x${s}/apps"
        cp "$HERE/icons/nimcale_${s}.png" "$ICONS/${s}x${s}/apps/nimcale.png"
    fi
done
sed -e "s|^Exec=.*|Exec=\"$HERE/Nimcale\" %F|" -e "s|^TryExec=.*|TryExec=$HERE/Nimcale|" \
    "$HERE/nimcale.desktop" > "$APPS/nimcale.desktop"
chmod +x "$APPS/nimcale.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$ICONS" 2>/dev/null || true
echo "Nimcale added to the application menu: $APPS/nimcale.desktop"
