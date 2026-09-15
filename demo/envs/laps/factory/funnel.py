"""The LAPS funnel: the generic funnel loop driven by the LAPS harness.

    python3 funnel.py --candidates A.jsonl [B.jsonl ...] [--out DIR]
                      [--limit N] [--only ID] [--slots N]

Classification and isolation are utils/skills/lib/funnel_core.py (see its
docstring for the harness contract). This file is the harness: how LAPS is
built, which decks a candidate affects, how a run is validated and priced —
all delegated to lib.py, which reuses the env's validators and grade.py
verbatim.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import lib  # noqa: E402
sys.path.insert(0, os.path.join(config.REPO, "utils", "skills", "lib"))
import funnel_core  # noqa: E402


def checks_of(tree):
    if tree == "both":
        return config.TREES["2d"]["checks"] + config.TREES["3d"]["checks"]
    return list(config.TREES[tree]["checks"])


def tree_of_check(check):
    for t, spec in config.TREES.items():
        if check in spec["checks"]:
            return t
    raise KeyError(check)


class LapsHarness:
    BASE = config.BASE
    JOBS = config.JOBS
    FLOOR_MAX = config.FLOOR_MAX
    MARGIN_MIN = config.MARGIN_MIN
    ApplyError = lib.ApplyError

    def __init__(self):
        self._walls = None

    @property
    def walls(self):
        if self._walls is None:
            self._walls = json.load(open(os.path.join(config.REF, "walltimes.json")))
        return self._walls

    def roundtrip_ok(self, cand):
        return lib.roundtrip_ok(cand)

    def copy_tree(self, src, dst):
        lib.copy_tree(src, dst)

    def apply_transform(self, transform, workdir):
        lib.apply_transform(transform, workdir)

    def builds_of(self, cand):
        return ["2d", "3d"] if cand["tree"] == "both" else [cand["tree"]]

    def build(self, workdir, tree):
        return lib.build_tree(workdir, tree)

    def checks_of(self, cand):
        """Affected decks, cheapest first."""
        return sorted(checks_of(cand["tree"]), key=lambda c: self.walls[c])

    def run_check(self, workdir, cand, check, run_dir):
        cap = max(config.TIMEOUT_MIN, config.TIMEOUT_FACTOR * self.walls[check])
        return lib.run_deck(workdir, tree_of_check(check), check, run_dir, timeout=cap)

    def validate(self, check, run_dir):
        return lib.validate_run(check, run_dir)

    def floor(self, verdicts):
        return lib.floor_of(verdicts)

    def summarize(self, verdict):
        return lib.summarize_verdict(verdict)

    def tolerance_only(self, verdicts):
        """Every failing check failed by pointwise tolerance alone: the time
        base (dt, step count) still matched."""
        return (all(v.get("passed") or v.get("outcome") == "diverged"
                    for v in verdicts.values()) and
                all((v.get("dt_abs") or 0.0) <= v.get("time_bound", 0.0) and
                    v.get("nstep_match", True)
                    for v in verdicts.values() if not v.get("passed")))


HARNESS = LapsHarness()


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
    funnel_core.screen(cands, os.path.abspath(__file__), "HARNESS", args.out,
                       args.slots, {"FLOOR_MAX": config.FLOOR_MAX,
                                    "MARGIN_MIN": config.MARGIN_MIN})


if __name__ == "__main__":
    main()
