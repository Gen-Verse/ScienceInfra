"""Static + roundtrip gates over packaged repair/restore tasks.

    python3 gate_pack.py [--tasks DIR] [--selftest]

Checks every tasks/laps-repair-* and tasks/laps-restore-* directory:

  manifest    task.toml parses; name matches the directory; taxonomy block
              complete; agent runtime network is "no-network" (the
              diff-against-upstream exploit is closed by mechanism)
  leak        no defect content in anything the agent can see: the edit
              strings and (for repair) the defect file path must not appear
              in instruction.md; the env Dockerfile's FINAL stage mentions
              no defect path; .git removal present
  vendoring   checks/ under environment/ and tests/ are byte-identical to
              the donor task's copies for exactly the graded checks
  grading     tests/grade.py carries the right CHECKS subset, reward_repair,
              and the task canary; the straw/floor stage is wired
  roundtrip   BEHAVIORAL: defect.json then defect_fix.json applied to a
              pristine base copy reproduce it byte-for-byte

--selftest plants a known leak in a scratch copy of one task and requires
the gate to fail it; a gate that cannot fail a known positive does not gate.
Exit code: 0 all green, 1 any red.
"""

import argparse
import filecmp
import json
import os
import shutil
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import lib  # noqa: E402


def fail(errors, task, what):
    errors.append(f"{task}: {what}")


# ---- content-anchored leak scan --------------------------------------------
# The lesson that forced this check: a probe model solved a mutation task by
# diffing the mutated file against its pristine sibling INSIDE the container
# (src_incompressible/rktmod.f90 is byte-identical to the compressible one).
# Text-anchored scans cannot see that; this one anchors on content: the
# pristine text of every defect site must not exist anywhere in the
# agent-visible tree. The compiler strips ungraded sibling trees; this gate
# models the stripped tree and verifies both the model and the strip wiring.

import re as _re

_norm_cache = {}


def _norm(s):
    return _re.sub(r"\s+", " ", s).strip()


def _norm_file(path):
    if path not in _norm_cache:
        _norm_cache[path] = _norm(open(path, encoding="utf-8",
                                       errors="ignore").read())
    return _norm_cache[path]


def surviving_f90(tree):
    """The .f90 files the agent image keeps after the per-tree strip."""
    import glob
    if tree == "2d":
        return glob.glob(os.path.join(config.BASE, "src_compressible", "2D", "*.f90"))
    if tree == "3d":
        return glob.glob(os.path.join(config.BASE, "src_compressible", "*.f90"))
    return (surviving_f90("2d") + surviving_f90("3d"))


def leak_scan(task, row, errors, survivors=None):
    cand = row["candidate"]
    edits = cand.get("break", {}).get("edits", [])
    defect_files = {e["file"] for e in edits}
    files = survivors if survivors is not None else surviving_f90(cand["tree"])
    for e in edits:
        needle = _norm(e["old"])
        if len(needle) < 8:
            continue
        for f in files:
            rel = os.path.relpath(f, config.BASE)
            if rel in defect_files:
                continue
            if needle in _norm_file(f):
                fail(errors, task,
                     f"pristine copy of the defect site survives in the "
                     f"agent tree: {rel}")
                break


def check_task(task_dir, errors, row=None):
    task = os.path.basename(task_dir)
    p = lambda *a: os.path.join(task_dir, *a)  # noqa: E731

    # manifest
    try:
        with open(p("task.toml"), "rb") as f:
            toml = tomllib.load(f)
    except Exception as ex:
        fail(errors, task, f"task.toml unreadable: {ex}")
        return None
    if toml.get("task", {}).get("name") != "sciaccel/" + task:
        fail(errors, task, "task.toml name does not match directory")
    tax = toml.get("metadata", {}).get("taxonomy", {})
    for key in ("category", "mode", "family", "tree", "affected_checks",
                "defect_file", "floor_native_estimate", "canary"):
        if key not in tax:
            fail(errors, task, f"taxonomy missing {key}")
    if toml.get("environment", {}).get("network_mode") != "no-network":
        fail(errors, task, "agent environment is not no-network")
    checks = tax.get("affected_checks", [])
    canary = tax.get("canary", "")

    # defect + roundtrip (behavioral)
    try:
        defect = json.load(open(p("environment", "defect", "defect.json")))
        fix = json.load(open(p("solution", "defect_fix.json")))
        tdefect = json.load(open(p("tests", "defect", "defect.json")))
    except Exception as ex:
        fail(errors, task, f"defect specs unreadable: {ex}")
        return canary
    if {k: v for k, v in defect.items() if k != "_canary"} != \
       {k: v for k, v in tdefect.items() if k != "_canary"}:
        fail(errors, task, "environment and tests defect.json differ")
    cand = {"id": task,
            "break": {k: v for k, v in defect.items() if k != "_canary"},
            "fix": {k: v for k, v in fix.items() if k != "_canary"}}
    ok, why = lib.roundtrip_ok(cand)
    if not ok:
        fail(errors, task, f"break+fix roundtrip does not restore base: {why[:200]}")

    # leak scan: agent-visible text must not carry the defect
    instr = open(p("instruction.md")).read()
    if canary not in instr:
        fail(errors, task, "canary missing from instruction.md")
    restore = task.startswith("laps-restore-")
    for e in cand["break"].get("edits", []):
        for side in ("old", "new"):
            s = e[side].strip()
            if len(s) >= 12 and s in instr and not restore:
                fail(errors, task, f"instruction leaks defect text ({side})")
        if not restore and e["file"] in instr:
            fail(errors, task, "instruction names the defect file")
    env_docker = open(p("environment", "Dockerfile")).read()
    final_stage = env_docker[env_docker.rfind("\nFROM "):]
    if "defect" in final_stage:
        fail(errors, task, "env Dockerfile final stage references defect/")
    if "rm -rf /app/LAPS/.git" not in env_docker:
        fail(errors, task, "env Dockerfile does not strip .git")

    # sibling-tree strip wiring + content-anchored leak scan (see above)
    if "rm -rf /app/LAPS/src_incompressible" not in env_docker:
        fail(errors, task, "env Dockerfile does not strip src_incompressible")
    tree = tax.get("tree")
    if tree == "2d" and \
            "find /app/LAPS/src_compressible -maxdepth 1 -type f -delete" not in env_docker:
        fail(errors, task, "2d task does not strip the 3D sources")
    if tree == "3d" and "/app/LAPS/src_compressible/2D" not in env_docker:
        fail(errors, task, "3d task does not strip the 2D tree")
    if row is not None:
        leak_scan(task, row, errors)
    else:
        fail(errors, task, "no canonical row found for leak scan")

    # vendoring: checks byte-identical to the canonical envs/laps copy,
    # exactly the graded subset (donor-vs-envs drift is checked once in run())
    for side, donor_side in (("environment", config.CHECKS_DIR),
                             ("tests", config.CHECKS_DIR)):
        have = sorted(os.listdir(p(side, "checks"))) if os.path.isdir(p(side, "checks")) else []
        if have != sorted(checks):
            fail(errors, task, f"{side}/checks holds {have}, graded {sorted(checks)}")
        for c in checks:
            dcmp = filecmp.dircmp(os.path.join(donor_side, c), p(side, "checks", c))
            if dcmp.diff_files or dcmp.left_only or dcmp.right_only:
                fail(errors, task, f"{side}/checks/{c} differs from donor")
        decks = sorted(os.listdir(p(side, "decks"))) if os.path.isdir(p(side, "decks")) else []
        if decks != sorted(checks):
            fail(errors, task, f"{side}/decks holds {decks}")

    # grading wiring
    grade = open(p("tests", "grade.py")).read()
    if f"CHECKS = {json.dumps(sorted(checks, key=checks.index))}" not in grade:
        fail(errors, task, "grade.py CHECKS does not match affected_checks")
    for needle, what in (("reward_repair", "reward_repair missing from grade.py"),
                         (canary, "canary missing from grade.py")):
        if needle not in grade:
            fail(errors, task, what)
    tests_docker = open(p("tests", "Dockerfile")).read()
    for needle in ("AS straw", "grade_floor.py", "/floor.json /tests/floor.json"):
        if needle not in tests_docker:
            fail(errors, task, f"tests Dockerfile missing `{needle}`")
    if not os.access(p("solution", "solve.sh"), os.X_OK):
        fail(errors, task, "solution/solve.sh missing or not executable")
    if not os.path.isfile(p("authoring", "provenance.json")):
        fail(errors, task, "authoring/provenance.json missing")
    return canary


def check_env_consistency(errors):
    """The hand-built donor task must agree byte-for-byte with the canonical
    envs/laps assets it predates — a drift here means two sources of truth."""
    pairs = [
        (os.path.join(config.DONOR, "tests", "checks"), config.CHECKS_DIR),
        (os.path.join(config.DONOR, "environment", "decks"), config.DECKS),
        (os.path.join(config.DONOR, "environment", "patches"), config.PATCHES),
        (os.path.join(config.DONOR, "tests", "grade.py"), config.GRADE_PY),
        (os.path.join(config.DONOR, "tests", "test.sh"), config.TEST_SH),
        (os.path.join(config.DONOR, "tests", "make_timing.py"), config.MAKE_TIMING),
    ]
    import subprocess
    for donor_side, env_side in pairs:
        if os.path.isdir(donor_side):
            r = subprocess.run(["diff", "-r", "-q", "-x", "__pycache__",
                                donor_side, env_side], capture_output=True,
                               text=True)
            if r.returncode != 0:
                errors.append(f"envs/laps drift vs donor {donor_side}: "
                              f"{(r.stdout + r.stderr).strip()[:300]}")
        elif not filecmp.cmp(donor_side, env_side, shallow=False):
            errors.append(f"envs/laps drift vs donor file {donor_side}")


def generated_task_dirs(tasks_root):
    """Compiled task dirs, one category level down: tasks/<category>/<task>."""
    out = []
    for cat in sorted(os.listdir(tasks_root)):
        cat_dir = os.path.join(tasks_root, cat)
        if not os.path.isdir(cat_dir):
            continue
        for d in sorted(os.listdir(cat_dir)):
            if d.startswith(("laps-repair-", "laps-restore-")) and \
                    os.path.isdir(os.path.join(cat_dir, d)):
                out.append(os.path.join(cat_dir, d))
    return out


def run(tasks_root):
    dirs = generated_task_dirs(tasks_root)
    if not dirs:
        lib.die(f"no packaged tasks under {tasks_root}")
    errors, canaries = [], {}
    check_env_consistency(errors)
    rows = {r["task"]: r for r in lib.read_jsonl(config.TASK_ROWS)} \
        if os.path.isfile(config.TASK_ROWS) else {}
    for d in dirs:
        c = check_task(d, errors, rows.get(os.path.basename(d)))
        if c:
            canaries.setdefault(c, []).append(os.path.basename(d))
    for c, ds in canaries.items():
        if len(ds) > 1:
            errors.append(f"canary shared by {ds}")
    return dirs, errors


def selftest(tasks_root):
    """Plant a known leak; the gate must catch it."""
    dirs = [d for d in generated_task_dirs(tasks_root)
            if os.path.basename(d).startswith("laps-repair-")]
    if not dirs:
        lib.die("selftest needs at least one packaged laps-repair task")
    src = dirs[0]
    scratch = os.path.join(config.WORK, "gate-selftest")
    shutil.rmtree(scratch, ignore_errors=True)
    tampered = os.path.join(scratch, os.path.basename(dirs[0]))
    shutil.copytree(src, tampered)
    defect = json.load(open(os.path.join(tampered, "environment", "defect", "defect.json")))
    edit = defect["edits"][0]
    with open(os.path.join(tampered, "instruction.md"), "a") as f:
        f.write(f"\n{edit['file']}\n{edit['old']}\n")
    errors = []
    check_task(tampered, errors)
    shutil.rmtree(scratch, ignore_errors=True)
    hits = [e for e in errors if "leak" in e or "names the defect" in e]
    if not hits:
        lib.die("SELFTEST FAILED: planted leak not detected — the gate has no teeth")
    print(f"selftest: planted leak detected ({len(hits)} findings) — gate fires")

    # Positive control for the content-anchored scan: a rktmod defect scanned
    # against an UNSTRIPPED tree must fire (src_incompressible/rktmod.f90 is
    # byte-identical to the pristine compressible one — the case that got
    # solved by sibling diff in the wild).
    import glob
    rows = lib.read_jsonl(config.TASK_ROWS)
    rk = next(r for r in rows if "rktmod" in r["candidate"].get("meta", {})
              .get("file", "") and r["candidate"]["source"] == "inject")
    unstripped = glob.glob(os.path.join(config.BASE, "**", "*.f90"),
                           recursive=True)
    errors2 = []
    leak_scan(rk["task"], rk, errors2, survivors=unstripped)
    if not errors2:
        lib.die("SELFTEST FAILED: sibling-copy leak not detected on an "
                "unstripped tree — the content scan has no teeth")
    print(f"selftest: sibling-copy leak detected on unstripped tree "
          f"({len(errors2)} findings) — content scan fires")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=config.TASKS_ROOT)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest(args.tasks)
        return
    dirs, errors = run(args.tasks)
    for e in errors:
        print("RED ", e)
    print(f"{len(dirs)} tasks gated: {len(dirs) - len(set(e.split(':')[0] for e in errors))} green, "
          f"{len(set(e.split(':')[0] for e in errors))} red")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
