#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

shopt -s extglob nullglob
vim !(__*).sh scripts/!(__*).sh !(__*).py src/!(__*)/!(__*).py \
/etc/systemd/system/balloon-main.service \
/etc/systemd/system/balloon-udp-spectrometer.service \
/etc/systemd/system/balloon-udp@.service \
docs/* config/README \
-c "vsplit" \
-c "wincmd h" \
-c "b main.py" \
-c "wincmd l" \
-c "b docs/todo" \
-c "term" \
-c "wincmd J" \
-c "resize 20"
