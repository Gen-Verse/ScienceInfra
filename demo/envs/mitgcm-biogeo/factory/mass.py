"""Capped mechanical round over the measured MITgcm biogeochemistry surface."""

import argparse
from collections import Counter, defaultdict
import json
import os

import config
import fixed_fortran_excise
import operators


def generate(base):
    rows = operators.generate(base)
    rows.extend(fixed_fortran_excise.generate(base, config.PHYSICS_FILES))
    return sorted(rows, key=lambda row: row["id"])


def capped(rows):
    kept, dropped = [], []
    counts = defaultdict(int)
    for candidate in rows:
        relpath = candidate["break"]["edits"][0]["file"]
        key = (relpath, candidate["family"])
        cap = config.MASS_CAPS.get(candidate["family"], 2)
        if counts[key] >= cap:
            dropped.append(candidate["id"])
            continue
        counts[key] += 1
        kept.append(candidate)
    return kept, {
        "raw": len(rows), "cap_dropped": len(dropped), "emitted": len(kept),
        "caps": config.MASS_CAPS,
        "per_family": dict(Counter(row["family"] for row in kept)),
        "per_file": dict(Counter(row["break"]["edits"][0]["file"] for row in kept)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=config.BASE)
    parser.add_argument("--out", default=os.path.join(config.WORK, "cand-mass.jsonl"))
    args = parser.parse_args()
    rows, stats = capped(generate(args.base))
    libdir = os.path.dirname(args.out)
    os.makedirs(libdir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with open(args.out + ".stats.json", "w", encoding="utf-8") as handle:
        json.dump(stats, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(json.dumps(stats, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
