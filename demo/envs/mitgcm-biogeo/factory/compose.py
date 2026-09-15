"""Optional seeded compositions of independently funnel-proven defects."""

import argparse
import json
import os
import random
import sys

import config
import lib

sys.path.insert(0, os.path.join(config.REPO, "utils", "skills", "lib"))
import compose_defects as compose  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", nargs="+", required=True)
    parser.add_argument("--verdicts", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()

    candidates = {}
    for path in args.candidates:
        for candidate in lib.read_jsonl(path):
            candidates[candidate["id"]] = candidate
    verdicts = {}
    for path in args.verdicts:
        for verdict in lib.read_jsonl(path):
            verdicts[verdict["id"]] = verdict
    pool = [candidates[cid] for cid, verdict in verdicts.items()
            if verdict["status"] == "survivor" and cid in candidates
            and candidates[cid]["source"] != "excise"]
    rng = random.Random(f"{config.SEED}:compose")
    combos = compose.seeded_combos(
        rng, sorted(pool, key=lambda row: row["id"]), 2, args.limit,
        lambda row: [edit["file"] for edit in row["break"]["edits"]],
        key_of=lambda row: (row["tree"], row["family"]))
    rows = []
    for index, combo in enumerate(combos):
        row = compose.merge(
            list(combo), f"compose-coupled-{index:02d}", "coupled-protocol",
            {"predicted_tier": "hard",
             "prediction_rationale":
                 "Two independently observed defects must be localized across "
                 "coupled subsystems and neither repair is implied by the other.",
             "semantic": True, "vein": "composed"},
            tree="coupled-biogeochemistry")
        row["source"] = "semantic"
        rows.append(row)
    lib.write_jsonl(args.out, rows)
    print(f"{len(rows)} optional composed candidates -> {args.out}")


if __name__ == "__main__":
    main()
