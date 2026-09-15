"""Emit MITgcm fixed-form subroutine excisions only."""

import argparse
import json
import os

import config
import fixed_fortran_excise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=config.BASE)
    parser.add_argument("--out")
    args = parser.parse_args()
    rows = fixed_fortran_excise.generate(args.base, config.PHYSICS_FILES)
    payload = "\n".join(json.dumps(row, sort_keys=True) for row in rows)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(payload + ("\n" if payload else ""))
    else:
        print(payload)


if __name__ == "__main__":
    main()
