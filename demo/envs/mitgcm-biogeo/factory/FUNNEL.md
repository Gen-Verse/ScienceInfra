# mitgcm-biogeo — measured factory funnel

This environment converts the ScienceAccelBench
`mitgcm/mitgcm-biogeochemistry` leaf into a native MITgcm repair bank. The
graded surface is end-to-end model evolution: only the final-iteration MITgcm
binary `.data` fields and their `.meta` layout are scored. Input decks,
stdout, package diagnostics, and intermediate iterations are not grading
surrogates.

## Source and build model

- MITgcm is pinned at commit
  `853761d8f46926cd8042d6e0ad252050561fd6fa` (`checkpoint69q`, MIT license).
  The consumed subset of the flat SAB source tree is archived deterministically as
  `mitgcm-853761d8f46926cd8042d6e0ad252050561fd6fa.tar.gz`; its SHA-256 is
  `7fc8abfc7bd58bc4c5a40c20213f8e3f2fb377c889a7ed0e3ddbfe1fe4358586`
  and its size is 25,887,403 bytes. `build_source_archive.py` fixes global
  member ordering, member time/owner/group, permissions, hard-link encoding,
  and the gzip header. It retains
  `LICENSE.txt`, `eesupp/`, `model/`, `pkg/`, and `tools/` intact, plus the
  six experiment directories used by the nine frozen decks; documentation,
  auxiliary top-level trees, and every other verification experiment are
  excluded.
- Builds use MITgcm's native `tools/genmake2` flow, GNU Fortran, one process,
  and `-ffp-contract=off`. The four Southern Ocean box rows share one build
  profile; the other five official decks retain their own profile.
- Agent and verifier images use
  `debian:bookworm-slim@sha256:1caf1c703c8f7e15dcf2e7769b35000c764e6f50e4d7401c355fb0248f3ddfdb`
  with exactly `build-essential python3 python3-numpy ca-certificates make
  gfortran`. No MPI or external solver library is present; SolveSAPHE is the
  vendored MITgcm implementation.
- `FILE_ROWS.json` maps all 26 authorable Fortran files to the profiles and
  official checks that compile and execute them. Every mapped file was
  confirmed in its generated dependency/build surface before authoring.

## Reference calibration

The nine rows are the leaf's nine official checks. Each was built and run
twice from the pinned tree, at rank 1, with a 120-second per-row ceiling.

| row | build profile | run 1 (s) | run 2 (s) | mean (s) | raw final state identical |
|---|---|---:|---:|---:|---|
| `global-dic` | `global-dic` | 1.7043 | 1.6928 | 1.6986 | yes |
| `so-box-dic` | `so-box` | 1.0693 | 1.1016 | 1.0854 | yes |
| `so-box-obcs-saphe` | `so-box` | 1.0837 | 1.1087 | 1.0962 | yes |
| `so-box-calcite-keir` | `so-box` | 1.3579 | 1.3578 | 1.3579 | yes |
| `so-box-calcite-naviaux` | `so-box` | 1.4479 | 1.3995 | 1.4237 | yes |
| `global-bling` | `global-bling` | 5.3063 | 5.2959 | 5.3011 | yes |
| `cfc-online` | `cfc-online` | 2.7832 | 2.7852 | 2.7842 | yes |
| `cfc-offline` | `cfc-offline` | 0.5934 | 0.5798 | 0.5866 | yes |
| `ptracer-advection-gyre` | `ptracer-advection-gyre` | 0.3234 | 0.3557 | 0.3396 | yes |

All 18 executions exited zero. For every row, the complete scored byte stream
was identical across runs, numeric drift was 0.0, and run 2 scored 1.0
against run 1. No canonicalization was needed. Because no planner or runtime
nondeterminism appeared on the graded surface, a sibling deterministic
variant was unnecessary. Native whole-suite anchors are oracle=1.0 and
nop=0.0. Evidence is in
`.work/mitgcm-biogeo/ref/{REPRO.json,ANCHORS.json,walltimes.json}`.

The grader first enforces dump conformance and the correct final iteration,
then compares every required field pointwise using the check's official
tolerances. Partial or malformed output cannot earn a scientific similarity
score. A complete but wrong final state retains bounded diagnostic credit;
the all-fields predicate is conjunctive.

## Authoring rounds

The capped mass generator scans fixed/free-form Fortran safely and uses loop
bounds, coefficients, signs, and whole-routine excision as mechanical
controls. Caps apply independently per file and family.

| mass family | raw after caps | survivor | silent | floor high | marginal | build reject | packaged |
|---|---:|---:|---:|---:|---:|---:|---:|
| loop bound | 62 | 25 | 23 | 14 | 0 | 0 | 18 |
| coefficient | 62 | 26 | 31 | 4 | 1 | 0 | 21 |
| sign | 72 | 25 | 42 | 5 | 0 | 0 | 20 |
| function excision | 22 | 2 | 0 | 0 | 0 | 20 | 2 |
| **mass total** | **218** | **78** | **96** | **23** | **1** | **20** | **61** |

The mass scan found 1,938 raw sites and dropped 1,720 through the per-file
caps, leaving the 218 candidates above. All candidates passed exact-once
break/fix round-trip checks before behavioral screening.

The reviewed semantic round authored exactly 40 candidates. Each carries a
design-only predicted tier, a one-line rationale, an explicit vein, and the
scientific variant expected to expose it.

| semantic vein | authored | survivor | silent | build reject | packaged |
|---|---:|---:|---:|---:|---:|
| non-rederivable DATA | 28 | 26 | 2 | 0 | 26 |
| subsystem protocol | 9 | 5 | 3 | 1 | 5 |
| locally re-derivable control | 3 | 1 | 2 | 0 | 1 |
| **semantic total** | **40** | **32** | **7** | **1** | **32** |

DATA is the primary difficult vein in this disciplined codebase. The sample
covers carbonate dissociation fits, SolveSAPHE polynomial entries, Keir and
Naviaux calcite rate laws, CFC Schmidt/solubility tables, BLING nutrient and
iron-ligand constants, and Redfield ratios. Protocol candidates cover
SolveSAPHE bracketing, calcite pressure propagation, biogeochemistry
dispatch, offline forcing windows, ptracer coupling/mixing, OBCS application,
and second-order moment transport. Exact published/table entries are not
reconstructible from adjacent arithmetic, while their symptoms appear only
after remote model evolution; this supplies both factors in the difficulty
model.

## Behavioral funnel

Every candidate was applied to a fresh pinned tree, built by `genmake2` in
all mapped profiles, run serially, and scored against the frozen reference.
Screening used four native workers, `FLOOR_MAX=0.65`, and
`MARGIN_MIN=1e-13`.

The first universal mapped-row pass screened all 258 candidates in 548.7
seconds:

| verdict | count |
|---|---:|
| survivor | 94 |
| silent | 103 |
| floor high | 39 |
| marginal | 1 |
| build reject | 21 |

For semantic DATA and branch-protocol candidates, averaging unaffected
sibling scientific variants can erase reward headroom even though the
authored symptom row is strongly discriminating. The semantic manifest
therefore names subsystem variants with `target_checks`; the funnel first
confirms the edit compiles in its mapped build, then measures precisely those
end-to-end variants. That 40-candidate refinement took 68.0 seconds and
produced 32 survivors, 7 silent candidates, and 1 build reject. It supersedes
the semantic statuses from the broad audit rather than adding candidates.

The final funnel set is consequently 78 mechanical survivors plus 32
semantic survivors, or 110. Here `survivor` means an observable end-to-end
defect with floor at most 0.65 and numeric divergence at least `1e-13`;
`silent` means the final-state rows did not expose the edit; `floor high`
means insufficient reward headroom; and `marginal` means the observed drift
was below the stable margin.

## Packaging verdict

The agent-visible strip model removes unrelated package siblings for each
subsystem as well as ungraded verification/documentation material. A
content-anchored scan nevertheless rejected 17 otherwise viable mechanical
candidates whose pristine answer-site text remained in a surviving source
file. `LEAK_EXCLUDED.json` records every rejection. No semantic survivor was
lost to this gate.

The remaining **93 tasks were packaged and compiled**:

| packaged dimension | count |
|---|---:|
| repair | 91 |
| implementation / routine restoration | 2 |
| mechanical repair | 59 |
| semantic repair | 32 |
| predicted easy | 61 |
| predicted medium | 1 |
| predicted hard | 31 |
| **total** | **93** |

Predicted tiers are design metadata, separate from lifecycle difficulty. All
new tasks begin at `difficulty="unrated"` and `difficulty_basis="none"`;
later evaluation may add `eval/` evidence and move a task to a measured tier.
The factory has no frozen package-count, birth-state, or empty-evaluation
assertion. Packaged native floors range from 0.0 to 0.611111 (mean 0.467957).

## Verification and anchors

- The clean reference leg is fail-hard. A defective straw build failure,
  crash, timeout, missing dump, or failed floor grader resolves to floor 0.0
  and cannot abort verification as a false infrastructure error.
- Planted gate selftests detect instruction path leakage, inverse corruption,
  a pristine sibling copy, and preserve a legal post-evaluation lifecycle
  state. The timeout/crash straw predicate was exercised and returned 0.0.
- `gate_pack.py` checks archive identity, all nine row contracts, break/fix
  round trips, instruction scope/canaries, sparse sources, strip-model parity,
  exact serial image dependencies, reward normalization, compiled/source
  correspondence, leak scans, and lifecycle rules.
- A real compiled Harbor oracle run on
  `mitgcm-biogeo-repair-sem-data-cfc11-schmidt-leading` produced reward 1.0,
  `reward_repair=1.0`, and `equivalence_pass=1`, with no exception. The
  matching cached nop run produced reward 0.0, `reward_repair=0.0`, and
  `equivalence_pass=0`, also with no exception. Evidence is under
  `.work/mitgcm-biogeo/harbor-{oracle,nop}/` and summarized in
  `HARBOR_ANCHORS.json`.

No Harbor waves, Luna/model probes, MPI runs, commits, or edits outside this
environment's assigned lanes were used.
