"""Static, roundtrip, lifecycle-tolerant gates for compiled MITgcm tasks."""

import argparse
import filecmp
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

import config
import harbor_spec as spec
import lib


def finding(errors, task, code, detail):
    errors.append(f"{task}: {code}|{detail}")


def has_code(errors, code):
    return any(item.split(": ", 1)[-1].split("|", 1)[0] == code
               for item in errors)


_normal_cache = {}


def _normal(text):
    return re.sub(r"\s+", " ", text).strip()


def _normal_file(path):
    if path not in _normal_cache:
        _normal_cache[path] = _normal(open(
            path, encoding="utf-8", errors="ignore").read())
    return _normal_cache[path]


def leak_scan(task, row, errors, survivors=None):
    """Reject a pristine answer-site copy in another agent-visible file."""
    candidate = row["candidate"]
    edits = candidate.get("break", {}).get("edits", [])
    defect_files = {edit["file"] for edit in edits}
    files = survivors if survivors is not None else \
        spec.surviving_sources(config.BASE, candidate["tree"])
    for edit in edits:
        needle = _normal(edit["old"])
        if len(needle) < 16:
            continue
        for path in files:
            relpath = os.path.relpath(path, config.BASE)
            if relpath in defect_files:
                continue
            if needle in _normal_file(path):
                finding(errors, task, "pristine_source_copy",
                        f"exact answer-site text survives in {relpath}")
                break


def _same_tree(left, right):
    if not os.path.isdir(left) or not os.path.isdir(right):
        return False
    compare = filecmp.dircmp(left, right)
    if compare.left_only or compare.right_only or compare.funny_files:
        return False
    for name in compare.common_files:
        a, b = os.path.join(left, name), os.path.join(right, name)
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        # Copied task inputs retain timestamps. Small text files get a strict
        # comparison; large binary inputs use size + preserved copy metadata.
        if os.path.getsize(a) < 1024 * 1024 and not filecmp.cmp(a, b, shallow=False):
            return False
    return all(_same_tree(os.path.join(left, name), os.path.join(right, name))
               for name in compare.common_dirs)


def task_dirs(root):
    out = []
    if not os.path.isdir(root):
        return out
    for directory, dirs, names in os.walk(root):
        if "task.toml" in names and os.path.basename(directory).startswith(
                config.TASK_PREFIX + "-"):
            out.append(directory)
            dirs[:] = []
    return sorted(out)


def source_dir_of(compiled):
    tier = os.path.basename(os.path.dirname(compiled))
    category = os.path.basename(os.path.dirname(os.path.dirname(compiled)))
    return os.path.join(config.TASKS_ROOT, category, tier,
                        os.path.basename(compiled))


def source_row(source_dir):
    try:
        with open(os.path.join(source_dir, "task.toml"), "rb") as handle:
            taxonomy = tomllib.load(handle)["metadata"]["taxonomy"]
        defect = json.load(open(os.path.join(source_dir, "defect.json"),
                                encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None
    return {"candidate": {
        "tree": taxonomy["tree"],
        "source": taxonomy.get("mode"),
        "break": {key: value for key, value in defect.items()
                  if key != "_canary"},
    }}


def check_source(source_dir, errors):
    task = os.path.basename(source_dir)
    required = {"task.toml", "instruction.md", "defect.json", "fix.json",
                "authoring/provenance.json"}
    if not os.path.isdir(source_dir):
        finding(errors, task, "source_missing", str(source_dir))
        return
    have = set()
    disallowed = []
    for directory, _, names in os.walk(source_dir):
        rel_dir = os.path.relpath(directory, source_dir)
        for name in names:
            rel = name if rel_dir == "." else rel_dir + "/" + name
            have.add(rel)
            if rel not in required and not rel.startswith(("eval/", "authoring/")):
                disallowed.append(rel)
    if not required <= have or disallowed:
        finding(errors, task, "source_not_sparse",
                f"missing={sorted(required-have)} extra={sorted(disallowed)}")
    # Lifecycle state is allowed to evolve. Only the allowed vocabulary and
    # the presence of evidence for a rated state are checked; birth-state
    # counts and an empty eval/ directory are deliberately not frozen.
    try:
        with open(os.path.join(source_dir, "task.toml"), "rb") as handle:
            taxonomy = tomllib.load(handle)["metadata"]["taxonomy"]
        difficulty = taxonomy.get("difficulty")
        if difficulty not in ("unrated", "easy", "medium", "hard"):
            finding(errors, task, "lifecycle_value", str(difficulty))
        if difficulty != "unrated":
            eval_dir = os.path.join(source_dir, "eval")
            evidence = [path for directory, _, names in os.walk(eval_dir)
                        for name in names
                        for path in [os.path.join(directory, name)]] \
                if os.path.isdir(eval_dir) else []
            if not evidence:
                finding(errors, task, "lifecycle_evidence_missing",
                        "rated task has no eval record")
    except Exception as exc:
        finding(errors, task, "source_manifest_unreadable", str(exc))


def check_task(task_dir, errors, row):
    task = os.path.basename(task_dir)
    path = lambda *parts: os.path.join(task_dir, *parts)
    try:
        with open(path("task.toml"), "rb") as handle:
            manifest = tomllib.load(handle)
    except Exception as exc:
        finding(errors, task, "manifest_unreadable", str(exc))
        return None
    if manifest.get("task", {}).get("name") != "sciaccel/" + task:
        finding(errors, task, "manifest_name", "name differs from directory")
    taxonomy = manifest.get("metadata", {}).get("taxonomy", {})
    required = ("category", "mode", "family", "tree", "affected_checks",
                "defect_file", "floor_native_estimate", "straw_timeout_sec",
                "canary", "difficulty", "difficulty_basis",
                "difficulty_design", "predicted_tier",
                "prediction_rationale")
    for key in required:
        if key not in taxonomy:
            finding(errors, task, "taxonomy_missing", key)
    checks = list(taxonomy.get("affected_checks", []))
    if not checks or not set(checks) <= set(config.ROW_ORDER):
        finding(errors, task, "checks_invalid", repr(checks))
    if manifest.get("environment", {}).get("network_mode") != "no-network":
        finding(errors, task, "agent_network", "must be no-network")
    if manifest.get("verifier", {}).get("environment_mode") != "separate":
        finding(errors, task, "verifier_separation", "must be separate")
    if taxonomy.get("difficulty") not in ("unrated", "easy", "medium", "hard"):
        finding(errors, task, "lifecycle_value", str(taxonomy.get("difficulty")))
    if taxonomy.get("mode") == "semantic":
        if taxonomy.get("predicted_tier") not in ("easy", "medium", "hard"):
            finding(errors, task, "semantic_prediction", "invalid predicted tier")
        if not str(taxonomy.get("prediction_rationale", "")).strip():
            finding(errors, task, "semantic_prediction", "missing rationale")

    try:
        defect = json.load(open(path("environment", "defect", "defect.json"),
                                encoding="utf-8"))
        test_defect = json.load(open(path("tests", "defect", "defect.json"),
                                     encoding="utf-8"))
        fix = json.load(open(path("solution", "defect_fix.json"),
                             encoding="utf-8"))
    except Exception as exc:
        finding(errors, task, "transform_unreadable", str(exc))
        return taxonomy.get("canary")
    clean_defect = {key: value for key, value in defect.items()
                    if key != "_canary"}
    if clean_defect != {key: value for key, value in test_defect.items()
                        if key != "_canary"}:
        finding(errors, task, "defect_fanout", "agent and verifier differ")
    roundtrip = {"id": task, "break": clean_defect,
                 "fix": {key: value for key, value in fix.items()
                         if key != "_canary"}}
    ok, why = lib.roundtrip_ok(roundtrip)
    if not ok:
        finding(errors, task, "roundtrip_failed", why[:300])

    canary = taxonomy.get("canary", "")
    instruction = open(path("instruction.md"), encoding="utf-8").read()
    if canary not in instruction:
        finding(errors, task, "instruction_canary", "missing")
    for edit in clean_defect.get("edits", []):
        if edit["file"] in instruction:
            finding(errors, task, "instruction_scope_path", edit["file"])
        old, new = _normal(edit["old"]), _normal(edit["new"])
        normalized_instruction = _normal(instruction)
        if len(old) >= 24 and old in normalized_instruction:
            finding(errors, task, "instruction_answer_text", "pristine edit text")
        if len(new) >= 24 and new in normalized_instruction:
            finding(errors, task, "instruction_answer_text", "defective edit text")

    agent_docker = open(path("environment", "Dockerfile"),
                        encoding="utf-8").read()
    final_stage = agent_docker[agent_docker.rfind("\nFROM "):]
    for forbidden in ("defect/", "mitgcm.tar.gz", config.MITGCM_ARCHIVE):
        if forbidden in final_stage:
            finding(errors, task, "agent_final_leak", forbidden)
    if "rm -rf /app/MITgcm/.git" not in agent_docker:
        finding(errors, task, "git_not_stripped", "agent prep")
    if spec.strip_cmd(taxonomy.get("tree")) not in agent_docker:
        finding(errors, task, "strip_model", "compiled command differs")
    docker_text = agent_docker + open(path("tests", "Dockerfile"),
                                      encoding="utf-8").read()
    if re.search(r"\b(?:openmpi|mpirun|mpi-bin|libmpi)\b", docker_text, re.I):
        finding(errors, task, "mpi_dependency", "leaf images must be serial")
    apt = ("build-essential python3 python3-numpy ca-certificates make "
           "gfortran")
    if docker_text.count(apt) < 4:
        finding(errors, task, "apt_stack", "exact serial Fortran line missing")

    if row is None:
        finding(errors, task, "canonical_row_missing", "cannot leak-scan")
    else:
        leak_scan(task, row, errors)

    for side in ("environment", "tests"):
        have_checks = sorted(os.listdir(path(side, "checks"))) \
            if os.path.isdir(path(side, "checks")) else []
        have_cases = sorted(os.listdir(path(side, "cases"))) \
            if os.path.isdir(path(side, "cases")) else []
        if have_checks != sorted(checks):
            finding(errors, task, "vendored_checks", f"{side}: {have_checks}")
        if have_cases != sorted(checks):
            finding(errors, task, "vendored_cases", f"{side}: {have_cases}")
        for check in checks:
            if not _same_tree(os.path.join(config.CHECKS_DIR, check),
                              path(side, "checks", check)):
                finding(errors, task, "vendored_check_drift", f"{side}/{check}")
            if not _same_tree(os.path.join(config.CASES, check),
                              path(side, "cases", check)):
                finding(errors, task, "vendored_case_drift", f"{side}/{check}")
        archive = path(side, "source", os.path.basename(config.MITGCM_ARCHIVE))
        if not os.path.isfile(archive) or os.path.getsize(archive) != \
                config.MITGCM_ARCHIVE_BYTES:
            finding(errors, task, "source_archive_missing", side)

    grade = open(path("tests", "grade.py"), encoding="utf-8").read()
    expected = "CHECKS = " + json.dumps(checks)
    for needle, code in ((expected, "grade_checks"),
                         ("reward_repair", "grade_reward_repair"),
                         (canary, "grade_canary")):
        if needle not in grade:
            finding(errors, task, code, "missing")
    tests_docker = open(path("tests", "Dockerfile"), encoding="utf-8").read()
    for needle in ("AS straw", "grade_floor.py", "/floor.json /tests/floor.json",
                   "rowtool.py"):
        if needle not in tests_docker:
            finding(errors, task, "straw_wiring", needle)
    floor_tool = open(path("tests", "grade_floor.py"), encoding="utf-8").read()
    if "straw_crash_hang_or_missing_output" not in floor_tool:
        finding(errors, task, "straw_crash_policy", "floor-zero mapping absent")
    if not os.access(path("solution", "solve.sh"), os.X_OK):
        finding(errors, task, "oracle_executable", "solve.sh")
    return canary


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_env(errors):
    if os.path.getsize(config.MITGCM_ARCHIVE) != config.MITGCM_ARCHIVE_BYTES:
        errors.append("ENV: archive_size|pinned source archive size changed")
    if sha256(config.MITGCM_ARCHIVE) != config.MITGCM_SHA256:
        errors.append("ENV: archive_hash|pinned source archive changed")
    try:
        anchors = json.load(open(os.path.join(config.REF, "ANCHORS.json"),
                                 encoding="utf-8"))
        repro = json.load(open(os.path.join(config.REF, "REPRO.json"),
                               encoding="utf-8"))
    except Exception as exc:
        errors.append(f"ENV: calibration_unreadable|{exc}")
        return
    if anchors.get("oracle", {}).get("reward") != 1.0:
        errors.append("ENV: native_oracle|not 1.0")
    if anchors.get("nop", {}).get("reward") != 0.0:
        errors.append("ENV: native_nop|not 0.0")
    if len(config.rows()) not in range(5, 10):
        errors.append("ENV: row_count|must be 5--9")
    for row in config.rows():
        finding_data = row.get("reference_calibration", {}).get(
            "nondeterminism", {})
        if not finding_data.get("raw_final_state_byte_identical"):
            errors.append(f"ENV: deterministic_row|{row['check']}")
        if max(row.get("reference_calibration", {}).get(
                "wall_times_sec", [999])) > config.ROW_TIMEOUT_MAX:
            errors.append(f"ENV: row_wall|{row['check']}")
        if row["check"] not in repro.get("rows", {}):
            errors.append(f"ENV: repro_missing|{row['check']}")
    try:
        harbor = json.load(open(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "HARBOR_ANCHORS.json"),
            encoding="utf-8"))
        runs = {(row["task"], row["agent"]): row
                for row in harbor.get("runs", [])}
        tasks = {key[0] for key in runs}
        if not tasks:
            errors.append("ENV: harbor_anchor_missing|no anchored task")
        for task in tasks:
            oracle = runs.get((task, "oracle"), {})
            nop = runs.get((task, "nop"), {})
            if (oracle.get("reward"), oracle.get("reward_repair")) != (1.0, 1.0):
                errors.append(f"ENV: harbor_oracle|{task}")
            if (nop.get("reward"), nop.get("reward_repair")) != (0.0, 0.0):
                errors.append(f"ENV: harbor_nop|{task}")
    except Exception as exc:
        errors.append(f"ENV: harbor_anchor_unreadable|{exc}")


def run(root):
    dirs = task_dirs(root)
    if not dirs:
        lib.die(f"no compiled tasks under {root}")
    errors, canaries = [], {}
    check_env(errors)
    for task_dir in dirs:
        source = source_dir_of(task_dir)
        check_source(source, errors)
        canary = check_task(task_dir, errors, source_row(source))
        if canary:
            canaries.setdefault(canary, []).append(os.path.basename(task_dir))
    for canary, tasks in canaries.items():
        if len(tasks) > 1:
            errors.append(f"ENV: duplicate_canary|{tasks}")
    return dirs, errors


def selftest(root):
    dirs = task_dirs(root)
    if not dirs:
        lib.die("selftest needs a compiled task")
    chosen = dirs[0]
    canonical = source_row(source_dir_of(chosen))
    scratch = os.path.join(config.WORK, "gate-selftest")
    shutil.rmtree(scratch, ignore_errors=True)
    os.makedirs(scratch)

    tampered = os.path.join(scratch, "instruction", os.path.basename(chosen))
    shutil.copytree(chosen, tampered)
    edit = canonical["candidate"]["break"]["edits"][0]
    with open(os.path.join(tampered, "instruction.md"), "a", encoding="utf-8") as handle:
        handle.write("\n" + edit["file"] + "\n")
    errors = []
    check_task(tampered, errors, canonical)
    if not has_code(errors, "instruction_scope_path"):
        lib.die("SELFTEST FAILED: planted instruction path leak was accepted")
    print("selftest: planted instruction path leak detected")

    broken = os.path.join(scratch, "roundtrip", os.path.basename(chosen))
    shutil.copytree(chosen, broken)
    fix_path = os.path.join(broken, "solution", "defect_fix.json")
    fix = json.load(open(fix_path, encoding="utf-8"))
    fix["edits"][0]["old"] += "__PLANTED__"
    with open(fix_path, "w", encoding="utf-8") as handle:
        json.dump(fix, handle)
    errors = []
    check_task(broken, errors, canonical)
    if not has_code(errors, "roundtrip_failed"):
        lib.die("SELFTEST FAILED: planted inverse corruption was accepted")
    print("selftest: planted inverse corruption detected")

    leaked = os.path.join(scratch, "pristine-copy.F")
    with open(leaked, "w", encoding="utf-8") as handle:
        handle.write(edit["old"])
    errors = []
    leak_scan("synthetic", canonical, errors, survivors=[leaked])
    if not has_code(errors, "pristine_source_copy"):
        lib.die("SELFTEST FAILED: planted pristine source copy was accepted")
    print("selftest: planted pristine source copy detected")

    source_copy = os.path.join(scratch, "source", os.path.basename(
        source_dir_of(chosen)))
    shutil.copytree(source_dir_of(chosen), source_copy)
    os.makedirs(os.path.join(source_copy, "eval"), exist_ok=True)
    with open(os.path.join(source_copy, "eval", "probe.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"probe": "selftest"}, handle)
    errors = []
    check_source(source_copy, errors)
    if has_code(errors, "source_not_sparse"):
        lib.die("SELFTEST FAILED: eval lifecycle record was rejected")
    print("selftest: eval lifecycle record tolerated")

    floor_root = os.path.join(scratch, "floor")
    os.makedirs(os.path.join(floor_root, "candidate", "row"), exist_ok=True)
    with open(os.path.join(floor_root, "candidate", "row", "_run_status.json"),
              "w", encoding="utf-8") as handle:
        json.dump({"check": "row", "status": "timeout"}, handle)
    fake = os.path.join(floor_root, "fake_grade.py")
    with open(fake, "w", encoding="utf-8") as handle:
        handle.write(
            "import argparse,json\n"
            "p=argparse.ArgumentParser()\n"
            "[p.add_argument(x,required=True) for x in "
            "['--candidate','--reference','--checks-dir','--out','--report']]\n"
            "a=p.parse_args();json.dump({'reward':0.5},open(a.out,'w'));"
            "json.dump({},open(a.report,'w'))\n")
    floor_out = os.path.join(floor_root, "floor.json")
    subprocess.run([
        sys.executable, os.path.join(config.HARBOR_DIR, "grade_floor.py"),
        "--grade", fake, "--candidate", os.path.join(floor_root, "candidate"),
        "--reference", floor_root, "--checks-dir", floor_root,
        "--out", floor_out], check=True, capture_output=True)
    floor = json.load(open(floor_out, encoding="utf-8"))
    if floor.get("floor") != 0.0 or floor.get("raw_grader_floor") != 0.5:
        lib.die("SELFTEST FAILED: timeout straw was not mapped to floor zero")
    print("selftest: timeout straw mapped to floor zero")
    shutil.rmtree(scratch, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default=config.BUILD_ROOT)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest(args.tasks)
        return
    dirs, errors = run(args.tasks)
    for error in errors:
        print("RED", error)
    red_tasks = {error.split(":", 1)[0] for error in errors}
    print(f"{len(dirs)} tasks gated; {len(errors)} findings; "
          f"{len(red_tasks)} red subjects")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
