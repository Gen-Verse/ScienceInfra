"""Build, run, and grade every MITgcm mutation against its live decks."""

import argparse
import json
import os
import sys

import config
import lib

sys.path.insert(0, os.path.join(config.REPO, "utils", "skills", "lib"))
import funnel_core  # noqa: E402


class MitgcmHarness:
    BASE = config.BASE
    JOBS = config.JOBS
    FLOOR_MAX = config.FLOOR_MAX
    MARGIN_MIN = config.MARGIN_MIN
    ApplyError = lib.ApplyError

    def __init__(self):
        self._file_rows = None
        self._walls = None

    @property
    def file_rows(self):
        if self._file_rows is None:
            self._file_rows = json.load(open(
                config.FILE_ROWS, encoding="utf-8"))["rows"]
        return self._file_rows

    @property
    def walls(self):
        if self._walls is None:
            self._walls = json.load(open(
                os.path.join(config.REF, "walltimes.json"), encoding="utf-8"))
        return self._walls

    def roundtrip_ok(self, cand):
        return lib.roundtrip_ok(cand)

    def copy_tree(self, source, destination):
        lib.copy_tree(source, destination)

    def apply_transform(self, transform, workdir):
        lib.apply_transform(transform, workdir)

    def checks_of(self, cand):
        affected = set()
        for edit in cand["break"]["edits"]:
            affected.update(self.file_rows.get(edit["file"], []))
        targeted = set(cand.get("meta", {}).get("target_checks", []))
        if targeted:
            unknown = targeted - affected
            if unknown:
                raise ValueError(
                    f"{cand['id']}: target rows do not compile the edit: {sorted(unknown)}")
            affected = targeted
        return sorted(affected, key=lambda check: self.walls[check])

    def builds_of(self, cand):
        return sorted({config.BUILD_PROFILE[check]
                       for check in self.checks_of(cand)})

    def build(self, workdir, profile):
        result = lib.build_incremental(
            workdir, profile,
            os.path.join(workdir, ".sciaccel-build", profile))
        return result["exit"] == 0, result.get("tail", "")

    def run_check(self, workdir, cand, check, run_dir):
        profile = config.BUILD_PROFILE[check]
        binary = os.path.join(workdir, ".sciaccel-build", profile, "mitgcmuv")
        cap = min(config.ROW_TIMEOUT_MAX,
                  max(config.TIMEOUT_MIN,
                      config.TIMEOUT_FACTOR * self.walls[check]))
        return lib.run_profile(binary, check, run_dir, timeout=cap)

    def validate(self, check, run_dir):
        return lib.validate_run(check, run_dir)

    def floor(self, verdicts):
        return lib.floor_of(verdicts)

    def summarize(self, verdict):
        return lib.summarize_verdict(verdict)

    @staticmethod
    def tolerance_only(verdicts):
        return all(verdict.get("passed") or
                   verdict.get("outcome") == "diverged"
                   for verdict in verdicts.values())


HARNESS = MitgcmHarness()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", nargs="+", required=True)
    parser.add_argument("--out", default=os.path.join(config.WORK, "funnel"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only")
    parser.add_argument("--slots", type=int, default=config.SLOTS)
    args = parser.parse_args()

    candidates, seen = [], set()
    for path in args.candidates:
        for cand in lib.read_jsonl(path):
            if cand["id"] in seen:
                lib.die(f"duplicate candidate id {cand['id']}")
            seen.add(cand["id"])
            candidates.append(cand)
    if args.only:
        candidates = [cand for cand in candidates if cand["id"] == args.only]
    if args.limit is not None:
        candidates = candidates[:args.limit]
    if not candidates:
        lib.die("no candidates selected")
    if not os.path.isfile(os.path.join(config.REF, "REPRO.json")):
        lib.die("native reference is missing; run reference.py first")
    funnel_core.screen(
        candidates, os.path.abspath(__file__), "HARNESS", args.out,
        max(1, args.slots),
        {"FLOOR_MAX": config.FLOOR_MAX,
         "MARGIN_MIN": config.MARGIN_MIN})


if __name__ == "__main__":
    main()
