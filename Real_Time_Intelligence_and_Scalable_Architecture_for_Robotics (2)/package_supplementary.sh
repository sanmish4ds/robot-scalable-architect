#!/usr/bin/env bash
# Package blind supplementary material (no author-identifying README paths).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/supplementary_blind.zip"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/supplementary"

cp -R "$ROOT/artifacts" "$STAGE/supplementary/"

# TIC monitor (exclude caches and local run outputs)
TIC_SRC="$ROOT/../tic_monitor"
TIC_DST="$STAGE/supplementary/tic_monitor"
mkdir -p "$TIC_DST"
tar -C "$TIC_SRC" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='artifacts/run_out' \
  --exclude='.egg-info' \
  -cf - . | tar -C "$TIC_DST" -xf -

cat > "$STAGE/supplementary/README.txt" <<'EOF'
Supplementary material for double-blind review.
- artifacts/: discrete-event simulation outputs and plotting script
- tic_monitor/: reference TIC monitor + CAAI supervisor (Python)
Repository identity withheld during peer review.
EOF

if [ -f "$TIC_DST/schema/tic.schema.json" ]; then
  export STAGE
  python3 - <<'PY'
import os, pathlib
p = pathlib.Path(os.environ["STAGE"]) / "supplementary/tic_monitor/schema/tic.schema.json"
text = p.read_text()
text = text.replace(
    "https://github.com/sanmish4ds/robot-scalable-architect",
    "https://example.org/tic-schema",
)
p.write_text(text)
PY
fi

rm -f "$OUT"
(cd "$STAGE" && zip -r "$OUT" supplementary)
echo "Created $OUT"
