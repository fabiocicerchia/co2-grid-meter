#!/usr/bin/env bash
# Lay out the KUAL extension in dist/kindle/extensions/co2meter. Copy the
# `extensions` folder onto the Kindle's USB drive, merging with the one there.
#
# pico/settings.json, if you have one, is copied in: it is the same file the
# Pico reads. dist/ is gitignored for that reason.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/dist/kindle/extensions/co2meter"

rm -rf "$OUT"
mkdir -p "$OUT/app"
cp -r "$ROOT/kindle/extension/." "$OUT/"
cp "$ROOT/kindle/run.py" "$OUT/"
cp -r "$ROOT/kindle/shims" "$OUT/"
cp "$ROOT"/pico/*.py "$OUT/app/"
cp -r "$ROOT/pico/providers" "$OUT/app/"
# The Pico's own server, boot and panel driver: the shims replace the driver,
# and http.py would shadow the stdlib package of the same name.
rm -f "$OUT"/app/{http,main,boot,epd_driver,ota,pages,staticfiles}.py
cp "$ROOT/pico/settings.example.json" "$OUT/"
[ -f "$ROOT/pico/settings.json" ] && cp "$ROOT/pico/settings.json" "$OUT/"
find "$OUT" -name __pycache__ -prune -exec rm -rf {} +

echo "Built $OUT"
[ -f "$OUT/settings.json" ] || echo "No settings.json: copy settings.example.json to settings.json there and fill it in."
