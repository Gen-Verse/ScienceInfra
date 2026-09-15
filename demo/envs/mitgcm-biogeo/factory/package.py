"""Select funnel survivors and emit sparse MITgcm repair/restore tasks."""

import argparse
import glob
import json
import os
import random
import shutil
import sys
import tomllib

import config
import harbor_spec as spec
import lib

sys.path.insert(0, os.path.join(config.REPO, "utils", "harbor"))
import to_harbor as harbor  # noqa: E402


def walls():
    return json.load(open(os.path.join(config.REF, "walltimes.json"),
                          encoding="utf-8"))


def defect_scope(candidate):
    count = len(candidate["break"]["edits"])
    words = {1: "one", 2: "two", 3: "three"}
    number = words.get(count, str(count))
    return f"exactly {number} localized source {'defect' if count == 1 else 'defects'}"


def symptom_text(funnel_row):
    caps = walls()
    lines = []
    for check in sorted(funnel_row["verdicts"], key=lambda item: caps[item]):
        verdict = funnel_row["verdicts"][check]
        run = funnel_row["runs"][check]
        if verdict.get("passed"):
            lines.append(f"- `{check}`: no observable final-state difference.")
        elif run["exit"] == "timeout":
            lines.append(f"- `{check}`: does not terminate within its measured "
                         f"budget (incumbent about {caps[check]:.3f} s).")
        elif run["exit"] != 0:
            lines.append(f"- `{check}`: aborts with exit {run['exit']}.")
        elif verdict.get("outcome") == "diverged":
            value = verdict.get("value")
            delta = f"{value:.6e}" if isinstance(value, (int, float)) else "unknown"
            lines.append(
                f"- `{check}`: completes at the expected iteration, but its "
                f"pointwise final state differs (worst absolute delta {delta} "
                f"in `{verdict.get('worst_file')}`; "
                f"{verdict.get('files_ok', 0)}/{verdict.get('files_scored', 0)} "
                "graded fields pass).")
        else:
            lines.append(f"- `{check}`: {verdict.get('outcome', 'fails')} — "
                         f"{verdict.get('error') or 'final state is unusable'}.")
    return "\n".join(lines)


def make_row(candidate, funnel_row):
    restore = candidate["source"] == "excise"
    return {
        "task": spec.task_name(candidate),
        "category": "implementation" if restore else "repair",
        "mode": ("excision" if restore else
                 "semantic" if candidate["source"] == "semantic" else "injected"),
        "checks": sorted(funnel_row["verdicts"],
                         key=lambda item: walls()[item]),
        "candidate": candidate,
        "funnel": funnel_row,
        "symptom": symptom_text(funnel_row),
    }


def _existing_state(tasks_root, category, name):
    found = glob.glob(os.path.join(tasks_root, category, "*", name))
    if not found:
        return "unrated", "none", None
    if len(found) != 1:
        raise RuntimeError(f"multiple lifecycle locations for {name}: {found}")
    with open(os.path.join(found[0], "task.toml"), "rb") as handle:
        taxonomy = tomllib.load(handle).get("metadata", {}).get("taxonomy", {})
    return (taxonomy.get("difficulty", os.path.basename(os.path.dirname(found[0]))),
            taxonomy.get("difficulty_basis", "none"), found[0])


def emit_source(row, tasks_root):
    candidate, funnel_row = row["candidate"], row["funnel"]
    name, category, checks = row["task"], row["category"], row["checks"]
    canary = spec.canary_of(name)
    difficulty, basis, existing = _existing_state(tasks_root, category, name)
    tier = (os.path.basename(os.path.dirname(existing)) if existing
            else difficulty if difficulty in ("easy", "medium", "hard")
            else "unrated")
    task_dir = os.path.join(tasks_root, category, tier, name)
    stash = os.path.join(config.WORK, "package-eval-stash", name)
    eval_dir = os.path.join(task_dir, "eval")
    if os.path.isdir(eval_dir):
        if os.path.exists(stash):
            raise RuntimeError(f"stale eval stash: {stash}")
        os.makedirs(os.path.dirname(stash), exist_ok=True)
        shutil.move(eval_dir, stash)
    if os.path.isdir(task_dir):
        shutil.rmtree(task_dir)
    if os.path.isdir(stash):
        os.makedirs(task_dir, exist_ok=True)
        shutil.move(stash, os.path.join(task_dir, "eval"))

    meta = candidate.get("meta", {})
    predicted = meta.get("predicted_tier", "easy")
    rationale = meta.get(
        "prediction_rationale",
        "Mechanical control whose local arithmetic is directly re-derivable.")
    files = sorted({edit["file"] for edit in candidate["break"]["edits"]})
    caps = walls()
    straw_cap = int(min(config.ROW_TIMEOUT_MAX, max(
        config.TIMEOUT_MIN,
        config.TIMEOUT_FACTOR * max(caps[check] for check in checks))))
    common = {
        "NAME": name,
        "MITGCM_COMMIT": config.MITGCM_COMMIT,
        "MITGCM_SHA256": config.MITGCM_SHA256,
        "CANARY": f"{config.CANARY_PREFIX} {canary}",
        "FLOOR": f"{float(funnel_row['floor']):.6f}",
        "STRAW_TIMEOUT": straw_cap,
        "DEFECT_FILE": ", ".join(files),
        "TREE": candidate["tree"],
        "PREDICTED_TIER": predicted,
        "PREDICTION_RATIONALE": rationale.replace('"', "'"),
        "DIFFICULTY_DESIGN": predicted,
        "AGENT_TIMEOUT": config.AGENT_TIMEOUT_SEC,
    }
    profiles = spec._profiles(checks)
    instruction_common = {
        **common,
        "SCOPE": spec.scope_of(candidate["tree"]),
        "SYMPTOM": row["symptom"],
        "CHECKS_LIST": ", ".join(checks),
        "BUILD_LINES": spec.build_lines(profiles),
    }
    if candidate["source"] == "excise":
        instruction = harbor.fill(
            spec.template("instruction-restore.md"), **instruction_common,
            SUB=meta.get("subroutine", "the excised routine"))
    else:
        instruction = harbor.fill(
            spec.template("instruction-repair.md"), **instruction_common,
            DEFECT_SCOPE=defect_scope(candidate))
    harbor.write(os.path.join(task_dir, "instruction.md"), instruction)

    action = ("one routine body excised" if candidate["source"] == "excise"
              else f"{len(candidate['break']['edits'])} localized defect"
                   + ("" if len(candidate["break"]["edits"]) == 1 else "s"))
    description = (
        f"Generated MITgcm biogeochemistry {row['mode']} task at checkpoint69q: "
        f"{action}; {len(checks)} final-state row"
        f"{'s' if len(checks) != 1 else ''} grade pointwise equivalence.")
    manifest = harbor.fill(
        spec.template("task.toml"), **common, DESCRIPTION=description,
        CATEGORY=category, MODE=row["mode"], FAMILY=candidate["family"],
        CHECKS_TOML=json.dumps(checks))
    manifest = manifest.replace('difficulty = "unrated"',
                                "difficulty = " + json.dumps(difficulty), 1)
    manifest = manifest.replace('difficulty_basis = "none"',
                                "difficulty_basis = " + json.dumps(basis), 1)
    harbor.write(os.path.join(task_dir, "task.toml"), manifest)
    harbor.write(os.path.join(task_dir, "defect.json"), json.dumps(
        {**candidate["break"], "_canary": canary}, indent=1, sort_keys=True))
    harbor.write(os.path.join(task_dir, "fix.json"), json.dumps(
        {**candidate["fix"], "_canary": canary}, indent=1, sort_keys=True))
    provenance = {
        "candidate": candidate,
        "funnel": funnel_row,
        "thresholds": {"FLOOR_MAX": config.FLOOR_MAX,
                       "MARGIN_MIN": config.MARGIN_MIN},
        "source": {"commit": config.MITGCM_COMMIT,
                   "release": config.MITGCM_RELEASE,
                   "archive_sha256": config.MITGCM_SHA256},
        "generator": "sciaccel-rl envs/mitgcm-biogeo/factory",
        "canary": canary,
    }
    harbor.write(os.path.join(task_dir, "authoring", "provenance.json"),
                 json.dumps(provenance, indent=1, sort_keys=True))
    return task_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", nargs="+", required=True)
    parser.add_argument("--verdicts", nargs="+", required=True)
    parser.add_argument("--out", default=config.TASKS_ROOT)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()

    candidates = {}
    for path in args.candidates:
        for candidate in lib.read_jsonl(path):
            candidates[candidate["id"]] = candidate
    verdicts = {}
    for path in args.verdicts:
        for verdict in lib.read_jsonl(path):
            verdicts[verdict["id"]] = verdict
    survivors = [row for row in verdicts.values()
                 if row["status"] == "survivor"]
    missing = [row["id"] for row in survivors if row["id"] not in candidates]
    if missing:
        lib.die(f"survivor verdicts lack candidates: {missing[:5]}")

    if not args.all:
        groups = {}
        for verdict in sorted(survivors, key=lambda item: item["id"]):
            key = (verdict["tree"], verdict.get("meta", {}).get("file"),
                   verdict["family"])
            groups.setdefault(key, []).append(verdict)
        selected = []
        for key in sorted(groups, key=str):
            group = groups[key]
            rng = random.Random(f"{config.SEED}:{key}")
            selected.extend(group if len(group) <= config.DEDUP_PER_GROUP
                            else rng.sample(group, config.DEDUP_PER_GROUP))
        survivors = sorted(selected, key=lambda item: item["id"])

    rows = [make_row(candidates[item["id"]], item) for item in survivors]
    import gate_pack
    excluded = []
    for row in list(rows):
        findings = []
        gate_pack.leak_scan(row["task"], row, findings)
        if findings:
            excluded.append({"task": row["task"], "findings": findings})
            rows.remove(row)

    factory_dir = os.path.dirname(os.path.abspath(__file__))
    harbor.write(os.path.join(factory_dir, "LEAK_EXCLUDED.json"),
                 json.dumps(excluded, indent=1, sort_keys=True))
    for row in sorted(rows, key=lambda item: item["task"]):
        emit_source(row, args.out)
    bank = [{
        "task": row["task"],
        "id": row["funnel"]["id"],
        "family": row["funnel"]["family"],
        "tree": row["funnel"]["tree"],
        "checks": row["checks"],
        "floor_native": row["funnel"]["floor"],
        "note": row["funnel"]["note"],
        "predicted_tier": row["candidate"].get("meta", {}).get(
            "predicted_tier", "easy"),
        "prediction_rationale": row["candidate"].get("meta", {}).get(
            "prediction_rationale"),
    } for row in sorted(rows, key=lambda item: item["task"])]
    harbor.write(os.path.join(factory_dir, "BANK.json"),
                 json.dumps(bank, indent=1, sort_keys=True))
    print(f"{len(rows)} source tasks -> {args.out}; "
          f"{len(excluded)} leak-excluded")
    if args.compile:
        count = len(harbor.compile_all(config.ENV_ROOT, config.BUILD_ROOT))
        print(f"compiled {count} Harbor task dirs into {config.BUILD_ROOT}")


if __name__ == "__main__":
    main()
