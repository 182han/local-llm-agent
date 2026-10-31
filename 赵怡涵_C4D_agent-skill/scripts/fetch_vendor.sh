#!/usr/bin/env bash
# Fetch the Leaflet assets that get inlined into the generated map.
#
# WHY VENDOR AT ALL: the map must be ONE self-contained .html file that opens
# with no CDN and no npm — that is the point of a local-first challenge.
#
# NOTE ON THIS MACHINE: unpkg.com fails TLS verification here
# ("certificate is not yet valid" — the system clock reads 2026), so jsdelivr
# is used instead. Both serve the identical upstream npm artifact.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:-$HERE/../agent/vendor/leaflet}"
VERSION="1.9.4"
BASE="https://cdn.jsdelivr.net/npm/leaflet@${VERSION}/dist"

mkdir -p "$DEST/images"
echo "Fetching Leaflet ${VERSION} -> $DEST"

for f in leaflet.js leaflet.css; do
  curl -fsSL -o "$DEST/$f" "$BASE/$f"
  echo "  $f  $(wc -c < "$DEST/$f") bytes"
done
for i in marker-icon.png marker-icon-2x.png marker-shadow.png layers.png layers-2x.png; do
  curl -fsSL -o "$DEST/images/$i" "$BASE/images/$i"
  echo "  images/$i  $(wc -c < "$DEST/images/$i") bytes"
done

echo
echo "SHA-256:"
( cd "$DEST" && shasum -a 256 leaflet.js leaflet.css )
echo
echo "Leaflet is BSD-2-Clause, (c) Volodymyr Agafonkin and Leaflet contributors."
echo "Done."
