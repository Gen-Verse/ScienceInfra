"""LAPS medium/hard candidates: subtle coefficients + cross-file compositions.

    python3 compose.py [--base DIR] [--out PATH]

The DIFFICULTY.md dials, turned (PROBE.md run 3 set the direction: formula
sites are frontier-trivial; the ratchets are subtle magnitudes, lean
symptoms, multi-defect composition, state-defining routines):

  subtle   (repair, designed MEDIUM)  the COEF rules re-issued with the
           perturbation shrunk 1-2 orders of magnitude, so the symptom sits
           just above MARGIN_MIN — often time-base-only. Packaged with a
           LEAN symptom (deck named, nothing else).
  multi2/3 (repair, designed HARD)    2-3 funnel-proven single defects
           merged cross-file, cross-family, per-tree seeded. Lean symptom.
  xmulti   (implementation, designed MEDIUM/HARD)  2 excisions merged
           cross-file; HARD when a state-defining routine (the PROBE.md
           run-3 law: vardt / perturbation_initialize /
           background_fields_initialize / calc_flux) is in the pair,
           MEDIUM for transforming-routine pairs.

Components come from FUNNEL SURVIVORS only (a composition of proven
defects can still die in the funnel — it goes through the same gates).
Everything here is a rule table + seeded selection; the mechanics live in
utils/skills/lib/compose_defects.py.
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import lib  # noqa: E402
sys.path.insert(0, os.path.join(config.REPO, "utils", "skills", "lib"))
import compose_defects as cd  # noqa: E402

# ---- subtle coefficient rules (designed medium) ---------------------------
# Same sites as operators.COEF, perturbation shrunk so the worst-frame
# deviation lands near (but above) MARGIN_MIN; the funnel's margin gate is
# the arbiter — too-subtle variants die as `marginal`, never get packaged.
SUBTLE = {
    "rktmod.f90": [
        ("cc10 = 8.0/15.0", "cc10 = 8.0/15.002", "RK stage-1 coefficient (subtle)"),
        ("cc20=5.0/12.0", "cc20=5.0/12.002", "RK stage-2 coefficient (subtle)"),
        ("cc30=0.75", "cc30=0.7502", "RK stage-3 coefficient (subtle)"),
        ("dd20 = -17./60.", "dd20 = -17./60.1", "RK stage-2 correction (subtle)"),
        ("dd30=-5./12.", "dd30=-5./12.002", "RK stage-3 correction (subtle)"),
        ("time_step1 = 8./15.", "time_step1 = 8./15.002", "RK stage-1 fraction (subtle)"),
        ("time_step2 = 2./15.", "time_step2 = 2./15.002", "RK stage-2 fraction (subtle)"),
        ("time_step3 = 1./3.", "time_step3 = 1./3.002", "RK stage-3 fraction (subtle)"),
    ],
    "mhd.f90": [
        ("dtmin = dtmin * cfl", "dtmin = dtmin * cfl * 1.0002",
         "CFL safety factor (subtle, time-base only)"),
        ("dt<0.98*dtmin", "dt<0.9784*dtmin", "dt hysteresis window (subtle)"),
    ],
    "mhdrhs.f90": [
        ("0.5 * (Bx**2", "0.50005 * (Bx**2", "magnetic pressure coefficient (subtle)"),
        ("(adiabatic_index-1)", "(adiabatic_index-1.0002)", "pressure closure (subtle)"),
    ],
    "dealiasing.f90": [
        ("dealias_circle_radius = 1./3.", "dealias_circle_radius = 1./3.02",
         "dealias radius (subtle)"),
    ],
}

STATE_SUBS = {"vardt", "perturbation_initialize",
              "background_fields_initialize", "calc_flux"}

N_MULTI2 = 6   # per tree
N_MULTI3 = 2   # per tree
N_XHARD = 3    # per tree: excision pairs containing a state-defining routine
N_XMED = 2     # per tree: transforming-routine excision pairs


def gen_subtle(base):
    rows = []
    for tree, spec in sorted(config.TREES.items()):
        for fname, pairs in sorted(SUBTLE.items()):
            rel = os.path.join(spec["subdir"], fname)
            path = os.path.join(base, rel)
            if not os.path.isfile(path):
                continue
            text = open(path).read()
            stem = fname.removesuffix(".f90")
            for k, (old, new, note) in enumerate(pairs):
                if text.count(old) != 1:
                    print(f"skip subtle ({text.count(old)}x): {rel}: {old}",
                          file=sys.stderr)
                    continue
                line = text[:text.index(old)].count("\n") + 1
                rows.append({
                    "id": f"subtle-{tree}-{stem}-l{line}k{k}",
                    "source": "inject", "family": "subtle", "tree": tree,
                    "note": note,
                    "break": {"edits": [{"file": rel, "old": old, "new": new}]},
                    "fix": {"edits": [{"file": rel, "old": new, "new": old}]},
                    "meta": {"file": rel, "symptom_style": "lean",
                             "difficulty_design": "medium"},
                })
    return rows


def load_survivors(cand_path, verdict_path):
    cands = {c["id"]: c for c in lib.read_jsonl(cand_path)}
    ids = [r["id"] for r in lib.read_jsonl(verdict_path)
           if r["status"] == "survivor"]
    return [cands[i] for i in ids]


def short(cid):
    """Compact component tag for composed ids: file stem + site."""
    parts = cid.split("-")
    return "-".join(parts[0:1] + parts[2:])  # drop the tree token


def gen_multi(inject_survivors, excluded_tasks):
    """Cross-file, cross-family merges of inject survivors."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import harbor_spec as spec
    pool_all = [c for c in inject_survivors
                if spec.task_name(c) not in excluded_tasks]
    files_of = lambda c: [e["file"] for e in c["break"]["edits"]]  # noqa: E731
    rows = []
    for tree in sorted(config.TREES):
        pool = [c for c in pool_all if c["tree"] == tree]
        for k, n, tag in ((2, N_MULTI2, "multi2"), (3, N_MULTI3, "multi3")):
            rng = random.Random(f"{config.SEED}:{tag}:{tree}")
            for combo in cd.seeded_combos(rng, pool, k, n, files_of,
                                          key_of=lambda c: c["family"]):
                cid = f"{tag}-{tree}-" + "+".join(short(c["id"]) for c in combo)
                rows.append(cd.merge(list(combo), cid, "multi",
                                     {"symptom_style": "lean",
                                      "difficulty_design": "hard"}))
    return rows


def gen_xmulti(excise_survivors):
    """Excision pairs: state-defining anchor -> hard; transforming -> medium."""
    files_of = lambda c: [e["file"] for e in c["break"]["edits"]]  # noqa: E731
    sub_of = lambda c: c["meta"]["subroutine"].lower()  # noqa: E731
    rows = []
    for tree in sorted(config.TREES):
        pool = [c for c in excise_survivors if c["tree"] == tree]
        state = sorted((c for c in pool if sub_of(c) in STATE_SUBS),
                       key=lambda c: c["id"])
        other = sorted((c for c in pool if sub_of(c) not in STATE_SUBS),
                       key=lambda c: c["id"])
        rng = random.Random(f"{config.SEED}:xmulti:{tree}")
        # hard: each state routine paired with a partner from another file
        # (prefer another state routine, else a transforming one)
        used = set()
        for anchor in state:
            if len([r for r in rows if r["tree"] == tree and
                    r["meta"]["difficulty_design"] == "hard"]) >= N_XHARD:
                break
            if anchor["id"] in used:
                continue
            partners = [c for c in state + other
                        if c["id"] != anchor["id"] and c["id"] not in used
                        and not set(files_of(c)) & set(files_of(anchor))]
            if not partners:
                continue
            partner = partners[0] if partners[0] in state else rng.choice(partners)
            used.update({anchor["id"], partner["id"]})
            pair = sorted([anchor, partner], key=lambda c: c["id"])
            cid = f"xmulti2-{tree}-" + "+".join(sub_of(c).replace("_", "-")
                                                for c in pair)
            rows.append(cd.merge(pair, cid, "excise-multi",
                                 {"subs": [[c["meta"]["subroutine"],
                                            c["meta"]["file"]] for c in pair],
                                  "difficulty_design": "hard"}))
        # medium: transforming-routine pairs, cross-file, seeded
        med = cd.seeded_combos(rng, [c for c in other if c["id"] not in used],
                               2, N_XMED, files_of)
        for combo in med:
            pair = list(combo)
            cid = f"xmulti2-{tree}-" + "+".join(sub_of(c).replace("_", "-")
                                                for c in pair)
            rows.append(cd.merge(pair, cid, "excise-multi",
                                 {"subs": [[c["meta"]["subroutine"],
                                            c["meta"]["file"]] for c in pair],
                                  "difficulty_design": "medium"}))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=config.BASE)
    ap.add_argument("--out")
    args = ap.parse_args()

    inject = load_survivors(os.path.join(config.WORK, "cand-inject.jsonl"),
                            os.path.join(config.WORK, "funnel-inject", "verdicts.jsonl"))
    excise = load_survivors(os.path.join(config.WORK, "cand-excise.jsonl"),
                            os.path.join(config.WORK, "funnel-excise", "verdicts.jsonl"))
    here = os.path.dirname(os.path.abspath(__file__))
    excluded = set()
    leak_path = os.path.join(here, "LEAK_EXCLUDED.json")
    if os.path.isfile(leak_path):
        excluded = {t["task"] for t in json.load(open(leak_path))}

    rows = gen_subtle(args.base) + gen_multi(inject, excluded) + gen_xmulti(excise)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate composed ids"
    payload = "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n"
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w") as f:
            f.write(payload)
    else:
        sys.stdout.write(payload)
    from collections import Counter
    print(f"{len(rows)} composed candidates "
          f"{dict(Counter(r['family'] for r in rows))}", file=sys.stderr)


if __name__ == "__main__":
    main()
