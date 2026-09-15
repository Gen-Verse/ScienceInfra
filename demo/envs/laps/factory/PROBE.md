# Probe run 1 — no-hint solver difficulty, 2026-08-29

The CLI-Universe-style anti-triviality filter, run for real: a strong model
attempts each task WITHOUT the answer (our hint-guided half is the oracle,
mechanically guaranteed), and tasks it cracks trivially are curriculum
rungs, not difficulty band. Probe layer per the ale practice: codex CLI +
`gpt-5.6-luna`, `reasoning_effort=max`, ChatGPT-subscription auth
(`CODEX_FORCE_AUTH_JSON=1`), one attempt per task, default 3600 s budget,
10 concurrent harbor trials on this box.

## Result: 10/10 pass@1

| task | family | floor | wall (s) | reward_repair |
| --- | --- | --- | --- | --- |
| laps-repair-sign-2d-mhdrhs-l69c63 | sign | 0.5 | 361 | 1.0 |
| laps-repair-sign-3d-mhdrhs-l290c33 | sign | 0.5 | 338 | 1.0 |
| laps-repair-coef-2d-rktmod-l18k4 | coef | 0.5 | 389 | 1.0 |
| laps-repair-coef-2d-mhd-l404k0 | coef | 0.2 | 332 | 1.0 |
| laps-repair-dropterm-2d-mhdrhs-l69c62 | dropterm | 0.5 | 458 | 1.0 |
| laps-repair-norm-2d-fftw-l59 | norm | 0.5 | 350 | 1.0 |
| laps-repair-bounds-2d-mhdrhs-l35 | bounds | 0.35 | 415 | 1.0 |
| laps-repair-bounds-3d-mhdrhs-l137 | bounds | 0.1 | 352 | 1.0 |
| laps-repair-rkorder-2d-rktmod-l39 | rkorder | 0.5 | 383 | 1.0 |
| laps-repair-swapvel-2d-mhdrhs-l84 | swapvel | 0.5 | 392 | 1.0 |

Plus a serial smoke on laps-repair-coef-2d-rktmod-l17k1: 1.0 in 4m21s.
Wall times include ~2 min of in-container codex bootstrap.

**Audit** (network was opened for the codex toolchain — debian, npm, nvm's
github path — so upstream-diff was possible): zero `git clone` /
`githubusercontent` fetches across all trajectories. Four trajectories
mention the upstream URL only because the in-container LAPS README cites
itself. All solves are in-container work. Anchor audits on actions, not
string presence.

## Why they fell, and what changed because of it

The observed solve path (explicit in the l17k1 trajectory): **diff the
mutated file against its pristine siblings inside the container** —
src_incompressible/rktmod.f90 is byte-identical to the compressible one,
and the other compressible tree is a near-mirror. The answer key was in the
image. Consequences, all landed:

1. Agent images now **strip every ungraded solver tree** (src_incompressible
   always; the non-graded compressible tree per task).
2. gate_pack gained a **content-anchored leak scan**: the pristine text of
   every defect site must not survive anywhere in the agent-visible tree
   (needles normalized; selftested against the unstripped tree, where the
   rktmod case must fire).
3. The scan, run as a packaging filter, **excluded 7 tasks** whose defect
   site has a pristine in-tree copy that cannot be stripped (SPMD bounds
   boilerplate duplicated in mhdinit; the FFT normalization line duplicated
   in mhdrhs) — bank 150 -> 143 (LEAK_EXCLUDED.json).

## Standing conclusions

- **This probe ran on the PRE-strip images.** 10/10 is therefore an upper
  bound on triviality-with-the-leak; the post-strip bank must be re-probed
  before any difficulty claim. Expect it to stay easy for frontier models:
  the defects are single-line, the physics is textbook, and the models know
  it.
- For a frontier model the current bank is a **warmup/curriculum tier**, not
  a difficulty band. That is not a verdict for RL training: the training
  policy (10-100x smaller) sets the relevant band — probe with the actual
  policy before concluding there is no gradient.
- Difficulty ratchets, in order of cost: re-probe post-strip -> lean
  symptoms (drop the variable/frame hint from instructions) -> multi-defect
  compositions -> subtler magnitudes near MARGIN_MIN -> tighter budgets.

## Probe run 2 — post-strip re-probe, same day

Same config, same 10 slots (norm-2d-fftw-l59 fell to the leak filter;
replaced by norm-2d-mhdrhs-l155). Agent images now carry NO sibling trees.

**Result: still 10/10 pass@1**, wall 296-549 s, zero upstream fetches.

The trajectories show the strip worked as intended — the solve path changed
from sibling-diff to pure physics: read the deck to identify the active
physics path, check the implementation against the governing equations
(the swapvel case: E = -u x B has a fixed cross-product structure; the
mutated x-component is visibly wrong), patch, rebuild, and self-verify by
inventing a rank-invariance oracle (1-rank vs 4-rank bitwise comparison).
One trajectory also grepped for injection markers (defect/todo/sciaccel) —
and found none.

**Standing conclusion:** single-line defects in textbook physics are
intrinsically pass@1 for a frontier model; the leak made it faster, not
possible. For frontier-difficulty claims the bank needs the next ratchets
— lean symptoms (drop the variable/frame hint), multi-defect compositions,
magnitudes near MARGIN_MIN, tighter budgets. For RL training the relevant
band is set by the (much smaller) training policy: probe with that policy
before concluding anything about gradient.

## Probe run 3 — the full bank, 2026-08-29

All 143 tasks (99 repair + 44 restore), same config (codex +
gpt-5.6-luna@max, 1 attempt, 10 concurrent), two harbor jobs
(fullbank-repair, fullbank-implementation), ~1.5 h wall total.
**Leakage audit: zero upstream-fetch ACTIONS across all 143 trajectories**
(action-anchored: git clone / curl / wget of the upstream; URL mentions in
read files don't count).

**repair: 99/99 pass@1** (median 363 s, max 606 s; every family 100%).
The run-2 conclusion holds at full scale: single-line defects in
closed-form physics are below the frontier floor.

**restore: 38/44**, with a REAL reward distribution — the ladder shaping
works (frame-fraction credit, not bimodal):

| task | reward_repair | wall |
| --- | --- | --- |
| laps-restore-3d-mhdrhs-calc-flux | 0.000 | 541 s |
| laps-restore-3d-mhd-vardt | 0.181 | 629 s |
| laps-restore-2d-mhdinit-perturbation-initialize | 0.375 | 1089 s |
| laps-restore-2d-mhdinit-background-fields-initialize | 0.444 | 453 s |
| laps-restore-3d-mhdinit-perturbation-initialize | 0.444 | 762 s |
| laps-restore-2d-mhd-vardt | 0.750 | 670 s |

**The empirical difficulty law this run establishes:** what a frontier
model can RE-DERIVE is trivial (textbook equations, structured physics
routines); what it must INFER FROM DOWNSTREAM CONSTRAINTS is hard —
authorial conventions (initial-condition normalization/phase choices) and
procedural exactness (the CFL machinery whose dt sequence is a per-step
fingerprint: wave-speed maxima per direction plus the hysteresis window).
Those have no closed-form reference; they are reconstructed from symptoms,
times.dat, and output formats — genuine research-code archaeology.

Consequences for the factory: aim new task families at the CONVENTION
LAYER (excise/mutate initial conditions, diagnostics, CFL variants —
mhdinit alone holds 900+ lines of ifield/ipert branches), rather than at
formula sites; and pick the next repo big, messy, and sparsely commented.
At frontier level the in-band fraction is 6/143 (4.2%) overall and 6/44
(13.6%) among restore tasks; a smaller training policy will sit in a wider
band — probe with the actual policy before wiring GRPO.

## Probe run 4 — the dial calibration, 2026-08-30

The 37 dial-turned tasks (compose.py) + the 6 old hard restores backfilled
to n=3. codex gpt-5.6-luna@max, k=3, 10 concurrent; 123/123 valid attempts
(ENOSPC and one subscription-quota outage cost a few hours; both surface as
ERRORED trials — NonZeroAgentExitCodeError / NetworkConnectionError — never
as fake zero-reward attempts, so the measurement stayed clean; resume with
`-f <ErrorType>`).

**Pass rates are bimodal: every task landed on 0.00, 0.67, or 1.00 — the
medium band (exactly 1/3) is empty.** Luna either cracks a task reliably
or not at all; solve variance on this repo is tiny.

| family (designed) | tasks | pass 1.0 | pass 2/3 | pass 0 | measured |
| --- | --- | --- | --- | --- | --- |
| subtle, lean symptom (medium) | 13 | 12 | 1 | 0 | 13 easy |
| multi2 cross-file (hard) | 12 | 9 | 1 | 2 | 10 easy, 2 hard |
| multi3 cross-file (hard) | 4 | 0 | 3 | 1 | 3 easy, 1 hard |
| xmulti2 state-defining (hard) | 4 | 0 | 0 | 4 | 4 hard |
| xmulti2 transforming (medium) | 4 | 4 | 0 | 0 | 4 easy |
| old 6 hard restores, n 1->3 | 6 | 0 | 1 | 5 | 5 hard, 1 easy |

### What the calibration says about the dials

1. **The information dial is dead against a frontier model.** Lean
   symptoms + coefficients shrunk to just above MARGIN_MIN changed
   nothing (13/13 easy): luna re-derives the equations and diffs its own
   two runs; it does not need the symptom hints. Drop lean/subtle from
   the recipe as a difficulty lever (keep lean templates for realism).
2. **Composition is not additive — it is gated by WHAT is in the mix.**
   Every hard multi task contains the CFL/time-base component
   (`dtmin = dtmin * cfl` site); compositions of formula-layer defects
   (sign+coef+dropterm+norm) stay easy at any count. Composition works as
   a difficulty lever only when at least one component is
   convention-layer.
3. **The state-defining law is now exact.** 8/8 excision tasks anchored
   on vardt / perturbation_initialize / background_fields_initialize /
   calc_flux(2d) are hard; 8/8 transforming-routine tasks (FFTs,
   transposes, output, grid) are easy. One flip at n=3:
   calc_flux(3d) fell to easy (2/3) — the 3D flux is more regular than
   the 2D one.
4. **"Medium" may not exist on this repo for this solver.** The bimodal
   distribution means the frontier tier boundary is a cliff, not a slope.
   The medium band will come from the training policy's probes (a smaller
   model has real variance), not from more frontier attempts.

**The recipe for the next repo, in one line: difficulty = convention-layer
content (CFL/time-base, initial conditions, authorial normalisation), not
defect count, not information hiding.** Formula-layer mutations are
curriculum floor at any composition depth.
