#!/bin/bash
# The verifier's entry point. Harbor ignores this script's exit code; what it
# reads is /logs/verifier/reward.json. A grader that crashes must still leave
# a reward behind — a missing file reads as an infrastructure error and gets
# re-run, a zero reads as what it is. That is what the fallback below is for.
#
# The reward contract (every value numeric; harbor's 1D convention is the
# "reward" key, which is what outcome-reward RL should train on by default):
#
#   reward            0..1  graded correctness, mean over the three checks
#   equivalence_pass  0|1   the strict gate: every check fully passed
#   speedup           >=0   advisory; self-reported timing vs the baked
#                           incumbent numbers; 0.0 unless the gate passed
#   check_aw_2d_256   0..1  per-check scores, for reward re-weighting
#   check_aw_2d_512   0..1
#   check_aw_128      0..1
#
# The full verdicts (per-frame detail, worst error, margins) land in
# /logs/verifier/grading_report.json for humans and trainers to read.
#
# No installs here: numpy and the reference were baked into the image at
# build time; the verifier runs with no network dependence.

set -uo pipefail
mkdir -p /logs/verifier

python3 /tests/grade.py \
  --candidate /logs/artifacts \
  --reference /tests/reference \
  --checks-dir /tests/checks \
  --out /logs/verifier/reward.json \
  --report /logs/verifier/grading_report.json

if [ ! -f /logs/verifier/reward.json ]; then
  echo '{"reward": 0.0, "equivalence_pass": 0, "speedup": 0.0, "grader_error": 1}' \
    > /logs/verifier/reward.json
fi
