"""LAPS excision candidates — the generic Fortran excision over config.TREES.

    python3 excise.py [--base DIR] [--out PATH]

Everything Fortran-level is utils/skills/lib/fortran_excise.py; this file only
says which trees of LAPS to walk.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
sys.path.insert(0, os.path.join(config.REPO, "utils", "skills", "lib"))
import fortran_excise  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=config.BASE)
    ap.add_argument("--out")
    args = ap.parse_args()
    rows = fortran_excise.excise_candidates(
        args.base, {t: s["subdir"] for t, s in config.TREES.items()})
    lines = [json.dumps(c, sort_keys=True) for c in rows]
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            f.write('\n'.join(lines) + ('\n' if lines else ''))
    else:
        for ln in lines:
            print(ln)


if __name__ == "__main__":
    sys.exit(main())
