#!/bin/bash
# The oracle: build the incumbent from the tree the agent was handed, with the
# pinned flags, and run the three decks — writing exactly the artifacts
# instruction.md asks a solver for.
#
#   harbor run -p tasks/laps-cpu -a oracle   -> reward 1.0, equivalence_pass 1
#   harbor run -p tasks/laps-cpu -a nop      -> reward 0.0, equivalence_pass 0
#
# The first proves the task is solvable and the criteria accept a correct
# answer (expect the byte-identity warning in the grading report: same base
# image, same flags, same deterministic code as the reference build — that is
# what the self-check produces by construction). The second proves the
# criteria discriminate. An oracle speedup of ~1.0 is correct and expected:
# the incumbent is exactly as fast as itself.
#
# This script is also executable documentation of the build recipe the
# instruction states. If it drifts from instruction.md, one of them is wrong.

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

echo "oracle: delivered"
ls -la /logs/artifacts/ /logs/artifacts/*/ | head -40
