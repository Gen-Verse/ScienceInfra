"""Build the pristine base tree and the native reference outputs.

    python3 reference.py

Produces:
    .work/base/              pin + the two task patches, no .git, never built in
    .work/ref/<check>/       out###.dat + times.dat from the clean build
    .work/ref/walltimes.json per-check native wall seconds (sets funnel caps)

Then calibrates the grading path both ways (the checker must fire on a known
negative and stay quiet on a known positive, or nothing downstream means
anything): reference-vs-reference must score 1.0 per check, and an empty
delivery must score 0.0.
"""

import json
import os
import shutil
import subprocess
import sys

import config
import lib


def ensure_clone():
    clone = os.path.join(config.WORK, "LAPS")
    if not os.path.isdir(os.path.join(clone, ".git")):
        subprocess.run(["git", "clone", "--quiet", config.LAPS_REPO, clone],
                       check=True)
    subprocess.run(["git", "-C", clone, "checkout", "--quiet", config.LAPS_SHA],
                   check=True)
    return clone


def make_base(clone):
    shutil.rmtree(config.BASE, ignore_errors=True)
    shutil.copytree(clone, config.BASE, ignore=shutil.ignore_patterns(".git"))
    for tree in ("src_compressible/2D", "src_compressible"):
        f90 = os.path.join(config.BASE, tree, "mhd.f90")
        for patch in ("apply-times-sidecar.py", "apply-gfortran-fix.py"):
            subprocess.run(
                ["python3", os.path.join(config.PATCHES, patch), f90],
                check=True, capture_output=True)


def main():
    clone = ensure_clone()
    make_base(clone)
    print("base ready:", config.BASE)

    build = os.path.join(config.WORK, "refbuild")
    lib.copy_tree(config.BASE, build)
    for tree in ("2d", "3d"):
        ok, log = lib.build_tree(build, tree)
        if not ok:
            lib.die(f"reference build failed for {tree}:\n{log}")
    print("clean trees built")

    walls = {}
    os.makedirs(config.REF, exist_ok=True)
    for tree, spec in config.TREES.items():
        for check in spec["checks"]:
            run_dir = os.path.join(config.WORK, "refrun", check)
            shutil.rmtree(run_dir, ignore_errors=True)
            res = lib.run_deck(build, tree, check, run_dir, timeout=1800)
            if res["exit"] != 0:
                lib.die(f"reference run failed for {check}: {res}")
            out = os.path.join(config.REF, check)
            shutil.rmtree(out, ignore_errors=True)
            os.makedirs(out)
            for f in sorted(os.listdir(run_dir)):
                if (f.startswith("out") and f.endswith(".dat")) or f == "times.dat":
                    shutil.copy(os.path.join(run_dir, f), os.path.join(out, f))
            walls[check] = res["wall"]
            print(f"reference {check}: wall {res['wall']}s, "
                  f"{lib.eligible_frames(out)} eligible frames")
    with open(os.path.join(config.REF, "walltimes.json"), "w") as f:
        json.dump(walls, f, indent=1)

    # Calibration, both directions. A checker that cannot fail a known
    # negative, or fails a known positive, is worse than none.
    for tree, spec in config.TREES.items():
        for check in spec["checks"]:
            ref = os.path.join(config.REF, check)
            v_pos = lib.validator(check).validate([ref], [ref])
            s_pos = lib.score(v_pos, lib.eligible_frames(ref))
            empty = os.path.join(config.WORK, "empty")
            os.makedirs(empty, exist_ok=True)
            v_neg = lib.validator(check).validate([ref], [empty])
            s_neg = lib.score(v_neg, lib.eligible_frames(ref))
            if s_pos != 1.0 or not v_pos.get("passed"):
                lib.die(f"calibration: ref-vs-ref for {check} scored {s_pos}")
            if s_neg != 0.0:
                lib.die(f"calibration: empty-vs-ref for {check} scored {s_neg}")
            print(f"calibration {check}: positive 1.0, negative 0.0  ok")
    print("reference ready")


if __name__ == "__main__":
    sys.exit(main())
