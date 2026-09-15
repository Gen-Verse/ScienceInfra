"""Select funnel survivors, emit the canonical task rows, compile to harbor.

    python3 package.py --candidates A.jsonl [...] --verdicts .work/funnel*/verdicts.jsonl [...]
                       [--all] [--out tasks/] [--rows-only]

This is the row EMITTER of the two-level layout (TAXONOMY.md production
ladder; envs/README.md for the layout). It owns everything that needs the
factory's working state (.work): survivor selection, the diversity dedup,
symptom-text rendering (which reads the native reference walltimes). Its
product is `envs/laps/tasks.jsonl` — one canonical row per task, fully
determining the compiled task — plus BANK.json for reporting. Compilation to
self-contained harbor dirs is `adapters/to_harbor.py`, which needs only the
rows and the envs/laps assets, never .work.

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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import lib  # noqa: E402

sys.path.insert(0, os.path.join(config.REPO, "utils", "adapters"))
import to_harbor  # noqa: E402


def symptom_text(row):
    lines = []
    caps = json.load(open(os.path.join(config.REF, "walltimes.json")))
    for check in to_harbor.checks_of(row["tree"]):
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


def make_row(cand, fun):
    restore = cand["source"] == "excise"
    name = to_harbor.task_name(cand)
    return {
        "task": name,
        "canary": to_harbor.canary_of(name),
        "category": "implementation" if restore else "repair",
        "mode": ("excision" if restore else
                 ("historical" if cand["source"] == "history" else "injected")),
        "checks": to_harbor.checks_of(cand["tree"]),
        "symptom": symptom_text(fun),
        "candidate": cand,
        "funnel": fun,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", nargs="+", required=True)
    ap.add_argument("--verdicts", nargs="+", required=True)
    ap.add_argument("--out", default=config.TASKS_ROOT)
    ap.add_argument("--all", action="store_true",
                    help="package every survivor (skip the diversity dedup)")
    ap.add_argument("--rows-only", action="store_true",
                    help="emit tasks.jsonl and BANK.json without compiling")
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
    if leaky:
        to_harbor.write(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "LEAK_EXCLUDED.json"),
                        json.dumps(leaky, indent=1, sort_keys=True))
        print(f"{len(leaky)} tasks excluded by the leak scan "
              f"(LEAK_EXCLUDED.json)")

    task_rows.sort(key=lambda t: t["task"])
    lib.write_jsonl(config.TASK_ROWS, task_rows)
    print(f"{len(task_rows)} canonical rows -> {config.TASK_ROWS}")

    manifest = [{"task": t["task"], "id": t["funnel"]["id"],
                 "family": t["funnel"]["family"], "tree": t["funnel"]["tree"],
                 "floor_native": t["funnel"]["floor"],
                 "note": t["funnel"]["note"]}
                for t in task_rows]
    to_harbor.write(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "BANK.json"),
                    json.dumps(manifest, indent=1, sort_keys=True))

    if args.rows_only:
        return
    for t in task_rows:
        to_harbor.compile_one(t, args.out)
        print("packaged", t["task"], f"(floor {t['funnel']['floor']})")
    print(f"\n{len(task_rows)} tasks packaged into {args.out}; BANK.json written")


if __name__ == "__main__":
    main()
