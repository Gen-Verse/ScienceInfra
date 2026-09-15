"""The funnel: candidate -> validated, floor-measured, symptomatic defect.

    python3 funnel.py --candidates A.jsonl [B.jsonl ...] [--out DIR]
                      [--limit N] [--only ID] [--slots N]

Per candidate, in an isolated tmpfs workdir:
    roundtrip   break+fix must reproduce the pristine base byte-for-byte
    apply       break applies cleanly
    build       the affected tree(s) compile with the pinned flags
    run         every affected deck runs under a wall cap (timeout = symptom)
    validate    each run vs the native reference, via the donor validators
    classify    silent | marginal | floor_high | survivor  (+ the fail states)

Classification:
    silent      every affected check passed -> the mutation does not matter
                on these decks; discarded (dead branch, cancelled term, ...)
    marginal    symptomatic ONLY via tolerance and worst divergence
                < MARGIN_MIN: too close to the 1e-10 edge to survive a
                compiler change; discarded
    floor_high  straw floor > FLOOR_MAX: the unfixed build already earns most
                of the ladder; kept in the report, not packaged by default
    survivor    an observable, non-marginal symptom with real reward headroom

Everything measured lands in <out>/verdicts.jsonl; <out>/report.json holds
the stage counts the whole exercise exists to produce.
"""

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import lib  # noqa: E402


def checks_of(tree):
    if tree == "both":
        return config.TREES["2d"]["checks"] + config.TREES["3d"]["checks"]
    return list(config.TREES[tree]["checks"])


def trees_of(tree):
    return ["2d", "3d"] if tree == "both" else [tree]


def tree_of_check(check):
    for t, spec in config.TREES.items():
        if check in spec["checks"]:
            return t
    raise KeyError(check)


def screen_order(tree):
    """Affected checks, cheapest first (per-tree screen check leads)."""
    chks = checks_of(tree)
    walls = json.load(open(os.path.join(config.REF, "walltimes.json")))
    return sorted(chks, key=lambda c: walls[c])


def worker(cand):
    t_start = time.monotonic()
    cid = cand["id"]
    work = os.path.join(config.JOBS, cid)
    row = {"id": cid, "source": cand["source"], "family": cand["family"],
           "tree": cand["tree"], "note": cand["note"], "meta": cand.get("meta", {})}
    walls = json.load(open(os.path.join(config.REF, "walltimes.json")))
    try:
        ok, why = lib.roundtrip_ok(cand)
        if not ok:
            row.update(status="roundtrip_fail", detail=why[:800])
            return row
        lib.copy_tree(config.BASE, work)
        try:
            lib.apply_transform(cand["break"], work)
        except lib.ApplyError as ex:
            row.update(status="apply_fail", detail=str(ex)[:800])
            return row
        for t in trees_of(cand["tree"]):
            ok, log = lib.build_tree(work, t)
            if not ok:
                row.update(status="build_fail", detail=log[-800:])
                return row
        verdicts, runs = {}, {}
        for check in screen_order(cand["tree"]):
            t = tree_of_check(check)
            cap = max(config.TIMEOUT_MIN, config.TIMEOUT_FACTOR * walls[check])
            run_dir = os.path.join(work, "run", check)
            res = lib.run_deck(work, t, check, run_dir, timeout=cap)
            v = lib.validate_run(check, run_dir)
            verdicts[check] = v
            runs[check] = {"exit": res["exit"], "wall": res["wall"]}
        floor, per_check = lib.floor_of(verdicts)
        summary = {c: lib.summarize_verdict(v) for c, v in verdicts.items()}
        crashed = any(r["exit"] != 0 for r in runs.values())
        all_passed = all(v.get("passed") for v in verdicts.values())
        tol_only = (not crashed and
                    all(v.get("passed") or v.get("outcome") == "diverged"
                        for v in verdicts.values()) and
                    all((v.get("dt_abs") or 0.0) <= v.get("time_bound", 0.0) and
                        v.get("nstep_match", True)
                        for v in verdicts.values() if not v.get("passed")))
        worst = max((v.get("value") or 0.0)
                    for v in verdicts.values() if not v.get("passed")) \
            if not all_passed else 0.0
        row.update(runs=runs, verdicts=summary, floor=floor,
                   floor_per_check=per_check, crashed=crashed)
        if all_passed:
            row["status"] = "silent"
        elif tol_only and worst < config.MARGIN_MIN:
            row["status"] = "marginal"
        elif floor > config.FLOOR_MAX:
            row["status"] = "floor_high"
        else:
            row["status"] = "survivor"
        return row
    except Exception as ex:  # a worker crash is a row, never a lost candidate
        import traceback
        row.update(status="worker_error", detail=traceback.format_exc()[-1200:])
        return row
    finally:
        row["wall_total"] = round(time.monotonic() - t_start, 1)
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", nargs="+", required=True)
    ap.add_argument("--out", default=os.path.join(config.WORK, "funnel"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only")
    ap.add_argument("--slots", type=int, default=config.SLOTS)
    args = ap.parse_args()

    cands, seen = [], set()
    for path in args.candidates:
        for c in lib.read_jsonl(path):
            if c["id"] in seen:
                lib.die(f"duplicate candidate id {c['id']}")
            seen.add(c["id"])
            cands.append(c)
    if args.only:
        cands = [c for c in cands if c["id"] == args.only]
    if args.limit:
        cands = cands[:args.limit]
    if not os.path.isdir(config.REF):
        lib.die("no native reference; run reference.py first")
    print(f"screening {len(cands)} candidates on {args.slots} slots")

    rows = []
    t0 = time.monotonic()
    with cf.ProcessPoolExecutor(max_workers=args.slots) as ex:
        futs = {ex.submit(worker, c): c["id"] for c in cands}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            row = fut.result()
            rows.append(row)
            if i % 20 == 0 or i == len(cands):
                print(f"  {i}/{len(cands)}  ({time.monotonic() - t0:.0f}s)")

    rows.sort(key=lambda r: r["id"])
    os.makedirs(args.out, exist_ok=True)
    lib.write_jsonl(os.path.join(args.out, "verdicts.jsonl"), rows)

    stages = {}
    for r in rows:
        stages.setdefault(r["status"], []).append(r["id"])
    by_source = {}
    for r in rows:
        d = by_source.setdefault(r["source"], {})
        d[r["status"]] = d.get(r["status"], 0) + 1
    report = {
        "candidates": len(rows),
        "by_status": {k: len(v) for k, v in sorted(stages.items())},
        "by_source": by_source,
        "survivors": stages.get("survivor", []),
        "floor_high": stages.get("floor_high", []),
        "wall_seconds": round(time.monotonic() - t0, 1),
        "thresholds": {"FLOOR_MAX": config.FLOOR_MAX,
                       "MARGIN_MIN": config.MARGIN_MIN},
    }
    with open(os.path.join(args.out, "report.json"), "w") as f:
        json.dump(report, f, indent=1, sort_keys=True)
    print(json.dumps(report["by_status"], indent=1, sort_keys=True))
    print("by_source:", json.dumps(by_source, sort_keys=True))
    print("out:", args.out)


if __name__ == "__main__":
    main()
