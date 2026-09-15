"""Select funnel survivors and emit SPARSE source task dirs.

    python3 package.py --candidates A.jsonl [...] --verdicts .work/funnel*/verdicts.jsonl [...]
                       [--all] [--out envs/laps/tasks] [--compile]

This is the task EMITTER of the layout (TAXONOMY.md production ladder;
envs/README.md for the layout). It owns everything that needs the factory's
working state (.work): survivor selection, the diversity dedup, symptom-text
rendering (which reads the native reference walltimes), the leak filter. Its
product is one sparse source task dir per survivor:

    envs/laps/tasks/<category>/<name>/
        task.toml  instruction.md  defect.json  fix.json  authoring/provenance.json

plus BANK.json / LEAK_EXCLUDED.json for reporting. Densifying into harbor
dirs is `utils/harbor/to_harbor.py` (`--compile` runs it), which needs only
the source tasks and the env assets, never .work.

Selection: status == "survivor", deduplicated to config.DEDUP_PER_GROUP per
(tree, defect file, family) with a per-group seeded draw (--all skips dedup;
per-group seeding keeps the capped subset stable when sources are added).

inject/history candidates become laps-repair-* (category repair); excise
candidates become laps-restore-* (category implementation, mode excision —
the memorization-taxed lower rung, stated in metadata).
"""

import argparse
import json
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import lib  # noqa: E402

import harbor_spec as spec  # noqa: E402
sys.path.insert(0, os.path.join(config.REPO, "utils", "harbor"))
import to_harbor as th  # noqa: E402  (generic: fill/write/compile_all)


def symptom_text(row):
    lines = []
    caps = json.load(open(os.path.join(config.REF, "walltimes.json")))
    for check in spec.checks_of(row["tree"]):
        v = row["verdicts"][check]
        run = row["runs"][check]
        if v.get("passed"):
            lines.append(f"- `{check}`: no observable symptom at the graded "
                         f"tolerance on this deck.")
            continue
        if run["exit"] == "timeout":
            cap = max(config.TIMEOUT_MIN, config.TIMEOUT_FACTOR * caps[check])
            lines.append(f"- `{check}`: the run does not terminate (killed "
                         f"after {cap:.0f} s; the incumbent finishes in "
                         f"~{caps[check]:.1f} s on the same hardware).")
            continue
        if run["exit"] != 0:
            lines.append(f"- `{check}`: the run aborts (exit {run['exit']}).")
            continue
        out = v.get("outcome")
        if out == "diverged" and v.get("value") is not None:
            lines.append(
                f"- `{check}`: the trajectory departs from the expected "
                f"physics — {v['frames_ok']} of {v['frames_scored']} output "
                f"frames within tolerance; worst pointwise deviation "
                f"{v['value']:.2e} in `{v['worst_variable']}` at frame "
                f"{v['worst_frame']} (graded bound 1e-10).")
        elif out == "time_base":
            dt = v.get("dt_abs")
            lines.append(
                f"- `{check}`: the timestep sequence departs from the "
                f"incumbent's (dt differs by up to "
                f"{dt:.2e})." if dt else
                f"- `{check}`: the timestep sequence departs from the "
                f"incumbent's ({v.get('error', 'time base mismatch')}).")
        elif out in ("wrong_shape", "nonconforming"):
            lines.append(f"- `{check}`: the run completes abnormally — "
                         f"{v.get('error', 'malformed or missing output')}.")
        elif out == "no_output":
            lines.append(f"- `{check}`: the run produces no usable output.")
        else:
            lines.append(f"- `{check}`: {v.get('error', out)}.")
    return "\n".join(lines)


def lean_symptom_text(row):
    """The lean tier: which decks fail and how the run ends — no variable,
    frame, or magnitude hints (DIFFICULTY.md medium/hard information dial)."""
    lines = []
    for check in spec.checks_of(row["tree"]):
        v, run = row["verdicts"][check], row["runs"][check]
        if v.get("passed"):
            lines.append(f"- `{check}`: no observable symptom at the graded "
                         f"tolerance on this deck.")
        elif run["exit"] == "timeout":
            lines.append(f"- `{check}`: the run does not terminate within "
                         f"the grading budget.")
        elif run["exit"] != 0:
            lines.append(f"- `{check}`: the run aborts (exit {run['exit']}).")
        else:
            lines.append(f"- `{check}`: the run completes, but the graded "
                         f"comparison against the incumbent fails.")
    return "\n".join(lines)


def make_row(cand, fun):
    restore = cand["source"] == "excise"
    meta = cand.get("meta", {})
    multi = len(meta.get("components", [])) > 1
    name = spec.task_name(cand)
    mode = ("excision" if restore else
            ("historical" if cand["source"] == "history" else "injected"))
    return {
        "task": name,
        "canary": spec.canary_of(name),
        "category": "implementation" if restore else "repair",
        "mode": mode + ("-multi" if multi else ""),
        "checks": spec.checks_of(cand["tree"]),
        "symptom": (lean_symptom_text(fun)
                    if meta.get("symptom_style") == "lean" else symptom_text(fun)),
        "candidate": cand,
        "funnel": fun,
    }


def emit_source(row, tasks_root):
    """Write the sparse source task dir for one row."""
    cand, fun = row["candidate"], row["funnel"]
    tree, checks, name, canary = cand["tree"], row["checks"], row["task"], row["canary"]
    restore = cand["source"] == "excise"
    # Tasks are filed by measured difficulty tier (grade_difficulty.py is the
    # mover): re-emission keeps a task where it is filed; a new task starts
    # in unrated/ until it is probed.
    import glob as _glob
    existing = _glob.glob(os.path.join(tasks_root, row["category"], "*", name))
    tier = os.path.basename(os.path.dirname(existing[0])) if existing else "unrated"
    task_dir = os.path.join(tasks_root, row["category"], tier, name)
    # eval/ (probe records, utils/eval) is the one non-source subtree a task
    # accumulates; re-emission rewrites the five source files and keeps it.
    kept = os.path.join(task_dir, "eval")
    stash = os.path.join(tasks_root, f".stash-{name}-eval")
    if os.path.isdir(kept):
        shutil.move(kept, stash)
    if os.path.isdir(task_dir):
        shutil.rmtree(task_dir)
    if os.path.isdir(stash):
        os.makedirs(task_dir, exist_ok=True)
        shutil.move(stash, kept)
    meta = cand.get("meta", {})
    multi = len(meta.get("components", [])) > 1
    lean = meta.get("symptom_style") == "lean"
    files = sorted({e["file"] for e in cand["break"]["edits"]})
    defect_file = ", ".join(files) if multi else (meta.get("file") or files[0])
    floor = fun["floor"]

    common = dict(
        NAME=name, REPO=config.LAPS_REPO, SHA=config.LAPS_SHA,
        CANARY=f"{config.CANARY_PREFIX} {canary}",
        FLOOR=f"{floor:.2f}", DEFECT_FILE=defect_file, TREE=tree,
    )

    if restore and multi:
        sub_list = "\n".join(f"- `{s}` in `{f}`" for s, f in meta["subs"])
        instr = th.fill(spec.template("instruction-restore-multi.md"), **common,
                        SCOPE=spec.scope_of(tree), SUB_LIST=sub_list,
                        SYMPTOM=row["symptom"], CHECKS_LIST=", ".join(checks),
                        BUILD_LINES=spec.build_lines(tree, "/app/LAPS"))
    elif restore:
        instr = th.fill(spec.template("instruction-restore.md"), **common,
                        SCOPE=spec.scope_of(tree), SUB=cand["meta"].get("subroutine", "?"),
                        SYMPTOM=row["symptom"], CHECKS_LIST=", ".join(checks),
                        BUILD_LINES=spec.build_lines(tree, "/app/LAPS"))
    elif lean:
        count = ("the defects — there may be more than one, in different "
                 "source files —" if multi else "one localized defect")
        instr = th.fill(spec.template("instruction-repair-lean.md"), **common,
                        COUNT_PHRASE=count,
                        SCOPE=spec.scope_of(tree), SCOPE_PATHS=spec.scope_paths(tree),
                        SYMPTOM=row["symptom"], CHECKS_LIST=", ".join(checks),
                        BUILD_LINES=spec.build_lines(tree, "/app/LAPS"))
    else:
        instr = th.fill(spec.template("instruction-repair.md"), **common,
                        SCOPE=spec.scope_of(tree), SCOPE_PATHS=spec.scope_paths(tree),
                        SYMPTOM=row["symptom"], CHECKS_LIST=", ".join(checks),
                        BUILD_LINES=spec.build_lines(tree, "/app/LAPS"))
    th.write(os.path.join(task_dir, "instruction.md"), instr)

    n_comp = max(1, len(meta.get("components", [])))
    if restore:
        what = (f"the executable bodies of {n_comp} subroutines removed"
                if multi else "the executable body of one subroutine removed")
    else:
        what = (f"{n_comp} localized defects injected across files"
                if multi else "a single localized defect injected")
        if lean and not multi:
            what += " (lean symptom)"
    desc = (f"Auto-generated {'restore' if restore else 'repair'} task on LAPS "
            f"({spec.scope_paths(tree)}): {what}; the graded decks "
            f"({', '.join(checks)}) must match the unmodified incumbent's "
            f"trajectories to 1e-10. Reference and straw floor produced in "
            f"situ by the verifier; train on reward_repair.")
    th.write(os.path.join(task_dir, "task.toml"),
             th.fill(spec.template("task.toml"), **common, DESCRIPTION=desc,
                     CATEGORY=row["category"], MODE=row["mode"],
                     FAMILY=cand["family"], CHECKS_TOML=json.dumps(checks),
                     MEM=8192 if tree == "2d" else 16384,
                     AGENT_TIMEOUT=config.AGENT_TIMEOUT_SEC,
                     # one defect / one routine, rich symptom: the designed
                     # "easy" rung of DIFFICULTY.md; measured tiers are
                     # written afterwards by utils/eval/grade_difficulty.py
                     DIFFICULTY_DESIGN="easy"))
    th.write(os.path.join(task_dir, "defect.json"),
             json.dumps({**cand["break"], "_canary": canary}, indent=1, sort_keys=True))
    th.write(os.path.join(task_dir, "fix.json"),
             json.dumps({**cand["fix"], "_canary": canary}, indent=1, sort_keys=True))
    th.write(os.path.join(task_dir, "authoring", "provenance.json"),
             json.dumps({"candidate": cand, "funnel": fun,
                         "thresholds": {"FLOOR_MAX": config.FLOOR_MAX,
                                        "MARGIN_MIN": config.MARGIN_MIN},
                         "generator": "sciaccel-rl authoring/repair",
                         "canary": canary}, indent=1, sort_keys=True))
    return task_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", nargs="+", required=True)
    ap.add_argument("--verdicts", nargs="+", required=True)
    ap.add_argument("--out", default=config.TASKS_ROOT)
    ap.add_argument("--all", action="store_true",
                    help="package every survivor (skip the diversity dedup)")
    ap.add_argument("--compile", action="store_true",
                    help="also densify into build/ via to_harbor")
    args = ap.parse_args()

    cands = {}
    for p in args.candidates:
        for c in lib.read_jsonl(p):
            cands[c["id"]] = c
    rows = []
    for p in args.verdicts:
        rows.extend(lib.read_jsonl(p))
    survivors = [r for r in rows if r["status"] == "survivor"]
    missing = [r["id"] for r in survivors if r["id"] not in cands]
    if missing:
        lib.die(f"verdicts without candidates: {missing[:5]} ...")

    if not args.all:
        groups = {}
        for r in sorted(survivors, key=lambda r: r["id"]):
            key = (r["tree"], (r.get("meta") or {}).get("file")
                   or str((r.get("meta") or {}).get("files")), r["family"])
            groups.setdefault(key, []).append(r)
        survivors = []
        for key in sorted(groups, key=str):
            g = groups[key]
            # Seeded PER GROUP so adding or removing one source never
            # reshuffles which candidates the other groups keep.
            rng = random.Random(f"{config.SEED}:{key}")
            survivors.extend(g if len(g) <= config.DEDUP_PER_GROUP
                             else rng.sample(g, config.DEDUP_PER_GROUP))
        survivors.sort(key=lambda r: r["id"])

    task_rows = [make_row(cands[r["id"]], r) for r in survivors]

    # Content-anchored leak filter (see gate_pack.leak_scan): a task whose
    # pristine defect-site text survives elsewhere in the agent-visible tree
    # is solvable by grep-diff, not physics — excluded from the bank. The
    # funnel verdict stays on record; the exclusion is a packaging decision.
    import gate_pack
    leaky = []
    for t in list(task_rows):
        errs = []
        gate_pack.leak_scan(t["task"], t, errs)
        if errs:
            leaky.append({"task": t["task"], "findings": errs})
            task_rows.remove(t)
    here = os.path.dirname(os.path.abspath(__file__))
    if leaky:
        th.write(os.path.join(here, "LEAK_EXCLUDED.json"),
                 json.dumps(leaky, indent=1, sort_keys=True))
        print(f"{len(leaky)} tasks excluded by the leak scan "
              f"(LEAK_EXCLUDED.json)")

    task_rows.sort(key=lambda t: t["task"])
    for t in task_rows:
        emit_source(t, args.out)
    print(f"{len(task_rows)} source tasks -> {args.out}")

    manifest = [{"task": t["task"], "id": t["funnel"]["id"],
                 "family": t["funnel"]["family"], "tree": t["funnel"]["tree"],
                 "floor_native": t["funnel"]["floor"],
                 "note": t["funnel"]["note"]}
                for t in task_rows]
    th.write(os.path.join(here, "BANK.json"),
             json.dumps(manifest, indent=1, sort_keys=True))

    if args.compile:
        n = len(th.compile_all(config.ENV_LAPS, config.BUILD_ROOT))
        print(f"compiled {n} harbor task dirs into {config.BUILD_ROOT}")


if __name__ == "__main__":
    main()
