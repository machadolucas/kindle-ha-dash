#!/bin/sh
# Install over USB mass storage (no SSH needed): kindle/install-usb.sh [/Volumes/Kindle]
# Copies the extension and the library scriptlets; never overwrites config.sh.
set -eu
KHD_VOLUME=${1:-/Volumes/Kindle}
KHD_HERE=$(cd "$(dirname "$0")" && pwd)
KHD_SOURCE=$KHD_HERE/extensions/kindle-ha-dash
KHD_DEST=$KHD_VOLUME/extensions/kindle-ha-dash
[ -d "$KHD_VOLUME/documents" ] || { echo "No Kindle at $KHD_VOLUME" >&2; exit 1; }
mkdir -p "$KHD_DEST/bin"
cp "$KHD_SOURCE/config.sh.example" "$KHD_DEST/"
cp "$KHD_SOURCE/bin/"*.sh "$KHD_DEST/bin/"
cp "$KHD_HERE/scriptlets/"*.sh "$KHD_VOLUME/documents/"
[ -f "$KHD_DEST/config.sh" ] || cp "$KHD_SOURCE/config.sh.example" "$KHD_DEST/config.sh"
# macOS leaves AppleDouble files on FAT volumes; the Kindle would index them.
find "$KHD_DEST" "$KHD_VOLUME/documents" -maxdepth 2 -name '._*' -delete 2>/dev/null || true
sync
echo "Installed to $KHD_VOLUME. Edit extensions/kindle-ha-dash/config.sh, then eject."
