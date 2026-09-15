# The harness half of grading: what each check's verdict is WORTH.
#
# The measurement itself is not here. Each check's vendored validate.py — the
# same file the agent can read in its own container — decides conformance,
# per-frame pointwise error and the time base, exactly as in the source
# package. Its own docstring says the division of labour: "The check owns the
# measurement; the harness owns what it is worth." This file is that harness.
#
# THE LADDER, per check (weights sum to 1.0, so a full pass is exactly 1.0):
#
#   0.0   nothing usable was delivered (outcome: no_output)
#   0.1   something was delivered but it does not conform — malformed frames,
#         wrong grid, wrong frame count, unparseable times.dat
#         (outcome: wrong_shape | nonconforming)
#   else  0.2                          for a conforming, complete frame set
#       + 0.5 * frames_ok / expected   per-frame pointwise credit; a port
#                                      that stays within 1e-10 longer earns
#                                      more, which is the shaped signal an
#                                      outcome-reward trainer needs
#       + 0.3 * time_base_ok           istep exact, dt and time within bound
#
# Design notes, so nobody re-litigates them blind:
#   * frames_ok is normalised by the REFERENCE's eligible frame count, not
#     the candidate's — an early blow-up earns its prefix, no more.
#   * A stable, time-correct port that drifted scores 0.2 + partial + 0.3,
#     which orders it above a blow-up and below a pass. That ordering is the
#     point of the ladder.
#   * The strict all-checks gate ships separately as equivalence_pass, so
#     nothing about eval-grade pass/fail is blurred by the shaping.
#   * Speedup is self-reported by the agent (timing.json) against numbers
#     measured on the machine that BUILT the verifier image. Both caveats are
#     structural, so speedup is advisory: reported, never folded into
#     `reward` here. A trainer that wants to optimise it should gate it on
#     equivalence_pass and fold it in trainer-side, knowingly.
#
# LAPS-CUDA ADDITION — the GPU gate. `reward` alone would score the
# CPU-incumbent shortcut (build the original, run it on CPU, deliver) at
# 1.0, which an RL policy would learn immediately. So this variant also
# writes:
#   gpu_active   1 only if EVERY check delivered a telemetry.csv (written by
#                the task's gpu-wrap) holding plausible GPU-load samples:
#                >= MIN_SAMPLES parseable rows and >= MIN_UTIL % utilisation
#                in at least one row. A tripwire, not a proof — the agent
#                controls its container, so a determined forger can fabricate
#                the file; the exploit list says transcripts are audited for
#                exactly that. Thresholds are deliberately loose until tuned
#                under real cuFFT load on a GPU box.
#   reward_gpu   reward * gpu_active — the training default on a GPU fleet.
#                The oracle (CPU baseline) scores reward 1.0, reward_gpu 0.0
#                BY DESIGN.

import argparse
import importlib.util
import json
import os
import sys
import traceback

CHECKS = ["aw-2d-256", "aw-2d-512", "aw-128"]

W_CONFORM, W_FRAMES, W_TIME = 0.2, 0.5, 0.3

# Telemetry plausibility thresholds (loose on purpose; tune on a GPU box).
MIN_SAMPLES = 3
MIN_UTIL = 10.0


def telemetry_ok(cand_check_dir):
    """True if this check's telemetry.csv holds plausible GPU-load samples.

    gpu-wrap rows are `timestamp, utilisation.gpu, memory.used` (csv,
    nounits). Any unparseable line is skipped rather than fatal — nvidia-smi
    occasionally emits notices — but only parseable rows count toward the
    sample minimum.
    """
    path = os.path.join(cand_check_dir, "telemetry.csv")
    if not os.path.isfile(path):
        return False
    rows = 0
    peak_util = 0.0
    try:
        with open(path) as f:
            for line in f:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3:
                    continue
                try:
                    util = float(parts[1])
                except ValueError:
                    continue
                rows += 1
                peak_util = max(peak_util, util)
    except OSError:
        return False
    return rows >= MIN_SAMPLES and peak_util >= MIN_UTIL


def load_validator(checks_dir, check):
    path = os.path.join(checks_dir, check, "validate.py")
    name = "validate_" + check.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def eligible_frames(ref_dir):
    """The reference's scored-frame count: every out###.dat after out000."""
    n = 0
    for f in os.listdir(ref_dir):
        if f.startswith("out") and f.endswith(".dat"):
            try:
                if int(f[3:-4]) > 0:
                    n += 1
            except ValueError:
                continue
    return n


def score(verdict, expected):
    outcome = verdict.get("outcome")
    if outcome == "no_output":
        return 0.0
    if outcome in ("wrong_shape", "nonconforming"):
        return 0.1
    frames_frac = (verdict.get("frames_ok", 0) / expected) if expected else 0.0
    time_ok = bool(
        verdict.get("nstep_match")
        and verdict.get("dt_abs") is not None
        and verdict.get("dt_abs") <= verdict.get("time_bound", 0.0)
        and verdict.get("time_abs") is not None
        and verdict.get("time_abs") <= verdict.get("time_bound", 0.0)
    )
    s = W_CONFORM + W_FRAMES * frames_frac + W_TIME * (1.0 if time_ok else 0.0)
    if verdict.get("passed"):
        s = 1.0
    return round(min(s, 1.0), 6)


def speedup(candidate_dir, reference_dir, all_passed):
    """Advisory: total incumbent seconds / total self-reported seconds."""
    if not all_passed:
        return 0.0
    try:
        with open(os.path.join(reference_dir, "incumbent_timing.json")) as f:
            ref = json.load(f)["seconds"]
        with open(os.path.join(candidate_dir, "timing.json")) as f:
            cand = json.load(f)
    except (OSError, ValueError, KeyError):
        return 0.0
    try:
        ref_total = sum(float(ref[c]) for c in CHECKS)
        cand_total = sum(float(cand[c]) for c in CHECKS)
    except (KeyError, TypeError, ValueError):
        return 0.0
    if cand_total <= 0 or ref_total <= 0:
        return 0.0
    return round(ref_total / cand_total, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--checks-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    rewards = {}
    report = {"checks": {}}
    scores = []
    all_passed = True
    gpu_active = True

    for check in CHECKS:
        ref_dir = os.path.join(args.reference, check)
        cand_dir = os.path.join(args.candidate, check)
        key = "check_" + check.replace("-", "_")
        try:
            mod = load_validator(args.checks_dir, check)
            verdict = mod.validate([ref_dir], [cand_dir])
            expected = eligible_frames(ref_dir)
            s = score(verdict, expected)
        except Exception:
            # A validator crash on one check must not zero the others: score
            # that check 0, record the traceback, keep grading.
            verdict = {"outcome": "grader_exception",
                       "traceback": traceback.format_exc()}
            s = 0.0
        t_ok = telemetry_ok(cand_dir)
        gpu_active = gpu_active and t_ok
        verdict["telemetry_ok"] = t_ok
        scores.append(s)
        all_passed = all_passed and bool(verdict.get("passed"))
        rewards[key] = s
        report["checks"][check] = verdict

    reward = round(sum(scores) / len(scores), 6)
    rewards_out = {
        "reward": reward,
        "gpu_active": 1 if gpu_active else 0,
        "reward_gpu": reward if gpu_active else 0.0,
        "equivalence_pass": 1 if all_passed else 0,
        "speedup": speedup(args.candidate, args.reference, all_passed),
    }
    rewards_out.update(rewards)

    with open(args.report, "w") as f:
        json.dump(report, f, indent=1, sort_keys=True, default=str)
    with open(args.out, "w") as f:
        json.dump(rewards_out, f, indent=1, sort_keys=True)

    print(json.dumps(rewards_out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
