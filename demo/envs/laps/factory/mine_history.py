"""LAPS history mining — the generic git miner with LAPS's file filter.

    python3 mine_history.py [--clone DIR] [--base DIR] [--out PATH]

LAPS-specific: which paths count (src_compressible/**/*.f90) and how a
file set maps to a tree label. The mining is utils/skills/lib/git_mining.py.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import lib  # noqa: E402
sys.path.insert(0, os.path.join(config.REPO, "utils", "skills", "lib"))
import git_mining  # noqa: E402


def is_compressible_f90(path):
    return path.startswith("src_compressible/") and path.endswith(".f90")


def tree_of(files):
    under_2d = [f.startswith("src_compressible/2D/") for f in files]
    if all(under_2d):
        return "2d"
    if not any(under_2d):
        return "3d"
    return "both"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clone", default=os.path.join(config.WORK, "LAPS"))
    ap.add_argument("--base", default=config.BASE)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if not os.path.isdir(os.path.join(args.clone, ".git")):
        lib.die(f"not a git clone: {args.clone}")
    if not os.path.isdir(args.base):
        lib.die(f"base tree not found: {args.base}")

    cands, scanned, touching, dropped = git_mining.mine(
        args.clone, args.base, is_compressible_f90, tree_of,
        lambda cand, base: lib.roundtrip_ok(cand, base=base))
    if args.out:
        lib.write_jsonl(args.out, cands)
    else:
        for c in cands:
            sys.stdout.write(json.dumps(c, sort_keys=True) + "\n")
    sys.stderr.write(
        f"history mining: {scanned} commits scanned, {touching} touched "
        f"src_compressible/*.f90, {len(cands)} candidates emitted, "
        f"{dropped} dropped\n")


if __name__ == "__main__":
    sys.exit(main())
