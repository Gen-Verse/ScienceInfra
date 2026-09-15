#!/bin/bash
# The oracle for laps-cuda: the CPU incumbent, built and run in the agent's
# container, delivered through the same contract a port must follow —
# telemetry wrapper included.
#
#   harbor run -p tasks/laps-cuda -a oracle --override-gpus 0
#     -> reward 1.0, gpu_active 0, reward_gpu 0.0
#   harbor run -p tasks/laps-cuda -a nop --override-gpus 0
#     -> everything 0
#
# reward 1.0 proves the task is solvable and the correctness criteria accept
# a correct answer. The build here is gfortran 13 / Ubuntu against the
# reference's gfortran 12 / Debian — a legitimately different build — yet
# measured 2026-08-26 it reproduced the reference BITWISE on all three decks
# (-ffp-contract=off pins the arithmetic hard for LAPS), so expect the
# byte-identity warning rather than a small real error.
#
# reward_gpu 0.0 is BY DESIGN, not a failure: the oracle is the CPU baseline,
# its telemetry shows no GPU load, and reward_gpu exists precisely to score
# that shortcut at zero. There is no oracle for the GPU half until a real
# port exists; the difficulty floor on a GPU box plays that role.

set -euo pipefail

RANKS="${RANKS:-4}"
FLAGS="-O3 -fdefault-real-8 -ffp-contract=off -fallow-argument-mismatch -std=legacy -I/usr/include -L/usr/lib -lfftw3"

make -C /app/LAPS/src_compressible/2D fftwpath=/usr OPTIONS="$FLAGS"
test -x /app/LAPS/src_compressible/2D/mhd.exe
make -C /app/LAPS/src_compressible fftwpath=/usr OPTIONS="$FLAGS"
test -x /app/LAPS/src_compressible/mhd.exe

: > /tmp/walltimes.txt
for c in aw-2d-256 aw-2d-512 aw-128; do
  case "$c" in
    aw-2d-*) EXE=/app/LAPS/src_compressible/2D/mhd.exe ;;
    *)       EXE=/app/LAPS/src_compressible/mhd.exe ;;
  esac
  mkdir -p "/app/run/$c" "/logs/artifacts/$c"
  cd "/app/run/$c"
  cp "/app/decks/$c/mhd.input" ./mhd.input
  t0=$(date +%s%N)
  gpu-wrap "/logs/artifacts/$c/telemetry.csv" -- \
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

echo "oracle: delivered (CPU baseline through the port's own contract)"
ls -la /logs/artifacts/ /logs/artifacts/*/ | head -40
