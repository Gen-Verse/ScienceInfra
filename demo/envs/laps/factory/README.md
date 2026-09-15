# The repair/restore task factory

Mass-produces **Repair** (injected + historical defects) and **Restore**
(excised routines — Implementation via excision, the memorization-taxed lower
rung) tasks from the already-packaged LAPS machinery, with zero domain-expert
input per instance. This is the volume engine of TAXONOMY.md §3, built in the
style of the `design_pipe_skill` doctrine: **a rule without a script executing
it does not exist** — every claim below is enforced by a gate in this
directory, and thresholds live in `config.py`, nowhere else.

## The one-command story (run from the repo root)

```bash
F=envs/laps/factory
python3 $F/reference.py              # base tree + native reference + BOTH-WAYS
                                     # calibration (ref-vs-ref 1.0, empty 0.0)
python3 $F/operators.py    --out .work/cand-inject.jsonl     # injection sites
python3 $F/excise.py       --out .work/cand-excise.jsonl     # routine cuts
python3 $F/mine_history.py --out .work/cand-history.jsonl    # upstream reverts
python3 $F/funnel.py --candidates .work/cand-*.jsonl --out .work/funnel
python3 $F/package.py --candidates .work/cand-*.jsonl \
                      --verdicts .work/funnel/verdicts.jsonl --compile
                                     # -> SPARSE source tasks under
                                     # envs/laps/tasks/<category>/<name>/
                                     # (task.toml, instruction.md, defect.json,
                                     # fix.json, authoring/provenance.json);
                                     # --compile densifies them into build/laps
                                     # (or: python3 utils/harbor/to_harbor.py)
python3 $F/gate_pack.py              # gates over build/, facts from the sources
python3 $F/gate_pack.py --selftest   # the gate must fire on a planted leak
harbor run -p build/laps/repair/easy/<task> -a oracle  # reward 1.0, reward_repair 1.0
harbor run -p build/laps/repair/easy/<task> -a nop     # 0.0 everywhere
```

## What the funnel enforces (and why the thresholds)

Candidates (schema: `lib.py` docstring) go through, per candidate, in an
isolated tmpfs workdir: roundtrip (break+fix must reproduce the pristine base
byte-for-byte — the packaged oracle depends on it) → apply → build → run every
affected deck under a wall cap → validate against the native reference with
the donor task's own validators → classify:

- **silent** — every affected check passes: the mutation does not matter *on
  these decks*. This is the funnel's reason to exist: these decks are
  x-propagating Alfvén waves, so whole families of "obviously wrong" edits
  (anything multiplying a field that stays identically zero, e.g. `By`/`Uy`
  terms; bounds clips whose lost mode is dealiased anyway) are inert. In the
  first mass run **123 of 233 injection candidates were silent** — every one
  of them a broken task had they been packaged blind.
- **marginal** — symptomatic only via tolerance with worst divergence below
  `MARGIN_MIN` (1e-8): too close to the 1e-10 graded edge to survive a
  compiler change. A priori threshold, revisit with fleet data.
- **floor_high** — straw floor above `FLOOR_MAX` (0.65): the unfixed build
  already earns most of the ladder (e.g. a resolution-dependent dealias bug
  that only shows at 256²: floor 0.75). Kept in the report, not packaged.
- **survivor** — observable, stable symptom with real reward headroom.

The floor is *re-measured in situ* at verifier-image build (straw stage: the
defective tree is built and run by the same recipe, graded by the task's own
`grade.py`, result baked as `/tests/floor.json`); the funnel's native floor is
advisory metadata. The training signal is

    reward_repair = max(0, reward − floor) / (1 − floor)

so build-it-broken-and-deliver scores exactly 0.0, full repair 1.0, and the
donor ladder's frame-fraction shapes everything between.

## The exploit ledger (mechanisms, not requests)

| exploit | mechanism |
| --- | --- |
| diff against public upstream at runtime | `[environment] network_mode = "no-network"` (harbor-enforced; the default is public — set explicitly) |
| `git log` archaeology in the shipped tree | `.git` stripped in the env prep stage; defect applied in a prep stage the final image never carries |
| deliver the unfixed build's output | straw floor measured in situ; `reward_repair` zeroes it |
| defect text leaking into agent-visible files | `gate_pack.py` leak scan, self-tested with a planted leak |
| grader drift from the donor ladder | `grade.py` is generated from the donor file with two assert-guarded surgical edits — donor drift breaks packaging loudly |
| sibling-tree diff (pristine near-mirrors in the image; the probe model's actual solve path) | CLOSED: agent images strip every ungraded solver tree; gate_pack's content-anchored leak scan verifies no pristine copy of a defect site survives, and excluded 7 unfixable tasks (LEAK_EXCLUDED.json). The strip decision is single-sourced in harbor_spec.STRIP_MODEL (cmd + surviving globs) and its two views are proven coherent by experiment on every gate run. See PROBE.md |
| memorized upstream source (public repo) | not preventable for injected single-line defects either (physics knowledge finds them — that is the task); for **restore** tasks it is a real tax, so they are tagged `mode = "excision"` with a metadata note: curriculum lower rungs, never frontier-difficulty evidence |

## Files

    config.py      paths, pins, thresholds, quotas — the only number source
    lib.py         candidate schema; apply/build/run/validate/score, all
                   reusing the donor task's validators and ladder verbatim
    reference.py   base tree + native reference + both-ways calibration
    operators.py   injection sites: sign/coef/dropterm/swapvel/norm/bounds/
                   rkorder over the LIVE code paths (dead flag branches and
                   hall-only routines skipped by a block tracker)
    excise.py      routine excision -> restore-the-capability candidates
    mine_history.py upstream fix-commit reverts as historical defects
    funnel.py      the screen: parallel, tmpfs, classification above
    package.py     survivors -> tasks/laps-repair-* / laps-restore-*
    gate_pack.py   static + roundtrip gates over packaged tasks; --selftest
    BANK.json      the packaged bank manifest (task, id, family, floor, note)

Work products land in `.work/` (gitignored): candidates, verdicts.jsonl,
report.json. The packaged tasks in `tasks/` are the deliverable.

## Measured funnel numbers

See `FUNNEL.md` (generated per run) for the current bank's numbers — how many
candidates each source produced, what died at which gate, and what shipped.
