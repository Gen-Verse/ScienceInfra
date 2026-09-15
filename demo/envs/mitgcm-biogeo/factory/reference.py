"""Build each genmake2 profile once and calibrate all nine rows twice."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import shutil
import sys

import config
import lib


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _build(profile):
    check = config.profile_check(profile)
    return profile, lib.build_profile(
        config.BASE, check, os.path.join(config.BUILDS, profile))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only")
    parser.add_argument("--build-slots", type=int, default=2)
    args = parser.parse_args()
    lib.seed_base()
    selected = [row for row in config.rows()
                if not args.only or row["check"] == args.only]
    if not selected:
        lib.die(f"unknown row {args.only}")
    profiles = sorted({config.BUILD_PROFILE[row["check"]] for row in selected})
    os.makedirs(config.BUILDS, exist_ok=True)
    build_facts = {}
    with ThreadPoolExecutor(max_workers=max(1, args.build_slots)) as pool:
        futures = {pool.submit(_build, profile): profile for profile in profiles}
        for future in as_completed(futures):
            profile, result = future.result()
            build_facts[profile] = result
            print(f"build {profile}: {result['exit']} in {result['wall']:.1f}s", flush=True)
            if result["exit"] != 0:
                lib.die(f"build failed for {profile}:\n{result['tail']}")

    results = {row["check"]: {"walls": []} for row in selected}
    for tag in ("ref", "ref2"):
        for row in selected:
            check = row["check"]
            profile = config.BUILD_PROFILE[check]
            binary = os.path.join(config.BUILDS, profile, "mitgcmuv")
            out_dir = os.path.join(config.WORK, tag, check)
            status = lib.run_profile(binary, check, out_dir,
                                     timeout=float(row["timeout_sec"]), strict=True)
            results[check]["walls"].append(status["wall"])
            print(f"{tag} {check}: {status['wall']:.3f}s", flush=True)

    grade = lib.grade_module()
    repro, bad = {}, []
    for row in selected:
        check = row["check"]
        first = os.path.join(config.WORK, "ref", check)
        second = os.path.join(config.WORK, "ref2", check)
        left, right = lib.stable_bytes(first), lib.stable_bytes(second)
        value, verdict = grade.grade_check(check, second, first, config.CHECKS_DIR)
        finding = {
            "raw_final_state_byte_identical": left == right,
            "scored_bytes_identical": left == right,
            "run_sha256": {"run1_scored": _sha(left), "run2_scored": _sha(right)},
            "validator_score_run2_vs_run1": value,
            "worst_numeric_abs_drift": verdict.get("value"),
            "canonicalization": "none; only final-iteration .data/.meta files are graded",
            "nondeterminism_action": "kept" if left == right else "drop-row-required",
        }
        repro[check] = finding
        row["build_profile"] = config.BUILD_PROFILE[check]
        row["reference_calibration"] = {
            "build_wall_sec": build_facts[config.BUILD_PROFILE[check]]["wall"],
            "wall_times_sec": results[check]["walls"],
            "mean_wall_sec": round(sum(results[check]["walls"]) / 2.0, 4),
            "nondeterminism": finding,
        }
        with open(os.path.join(config.CASES, check, "row.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(row, handle, indent=2, sort_keys=True)
            handle.write("\n")
        if value != 1.0 or not left or left != right:
            bad.append(check)

    os.makedirs(config.REF, exist_ok=True)
    walls = {check: round(sum(fact["walls"]) / 2.0, 4)
             for check, fact in results.items()}
    with open(os.path.join(config.REF, "walltimes.json"), "w",
              encoding="utf-8") as handle:
        json.dump(walls, handle, indent=1, sort_keys=True)
        handle.write("\n")
    with open(os.path.join(config.REF, "REPRO.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"commit": config.MITGCM_COMMIT, "release": config.MITGCM_RELEASE,
                   "rows": repro}, handle, indent=1, sort_keys=True)
        handle.write("\n")

    checks = [row["check"] for row in selected]
    oracle, _ = grade.grade_all(os.path.join(config.WORK, "ref2"),
                                os.path.join(config.WORK, "ref"),
                                config.CHECKS_DIR, checks)
    nop_dir = os.path.join(config.WORK, "nop")
    shutil.rmtree(nop_dir, ignore_errors=True)
    os.makedirs(nop_dir)
    nop, _ = grade.grade_all(nop_dir, os.path.join(config.WORK, "ref"),
                             config.CHECKS_DIR, checks)
    anchors = {"oracle": oracle, "nop": nop, "checks": checks}
    with open(os.path.join(config.REF, "ANCHORS.json"), "w",
              encoding="utf-8") as handle:
        json.dump(anchors, handle, indent=1, sort_keys=True)
        handle.write("\n")
    if oracle.get("reward") != 1.0 or oracle.get("equivalence_pass") != 1:
        bad.append("oracle-anchor")
    if nop.get("reward") != 0.0 or nop.get("equivalence_pass") != 0:
        bad.append("nop-anchor")
    print(f"anchors: oracle={oracle['reward']:.1f} nop={nop['reward']:.1f}")
    print(f"{len(selected) - len([x for x in bad if x in checks])}/{len(selected)} "
          "rows twice-run byte-identical")
    if bad:
        lib.die(f"reference calibration failed: {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
