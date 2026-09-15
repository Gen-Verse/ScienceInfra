#!/bin/bash
# @NAME@ oracle: apply the exact inverse of the generated defect, rebuild the
# affected tree(s) with the pinned flags, run the graded decks, deliver.
# Expect reward 1.0, reward_repair 1.0 (and the byte-identity warning: after
# the fix this IS the incumbent, same base, same flags).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$HERE/apply_defect.py" "$HERE/defect_fix.json" /app/LAPS

FLAGS="-O3 -fdefault-real-8 -ffp-contract=off -fallow-argument-mismatch -std=legacy -I/usr/include -L/usr/lib -lfftw3"
RANKS="${RANKS:-4}"

@BUILDS@

: > /tmp/walltimes.txt
for c in @CHECKS_SH@; do
  case "$c" in
    aw-2d-*) EXE=/app/LAPS/src_compressible/2D/mhd.exe ;;
    *)       EXE=/app/LAPS/src_compressible/mhd.exe ;;
  esac
  mkdir -p "/app/run/$c" "/logs/artifacts/$c"
  cd "/app/run/$c"
  cp "/app/decks/$c/mhd.input" ./mhd.input
  t0=$(date +%s%N)
  mpirun --allow-run-as-root --oversubscribe -np "$RANKS" "$EXE"
  t1=$(date +%s%N)
  echo "$c $t0 $t1" >> /tmp/walltimes.txt
  cp out*.dat times.dat "/logs/artifacts/$c/"
done

python3 - <<'EOF'
import json
rows = {}
for line in open('/tmp/walltimes.txt'):
    c, t0, t1 = line.split()
    rows[c] = round((int(t1) - int(t0)) / 1e9, 3)
with open('/logs/artifacts/timing.json', 'w') as f:
    json.dump(rows, f, indent=1)
EOF

echo "oracle: fixed, rebuilt, delivered"
