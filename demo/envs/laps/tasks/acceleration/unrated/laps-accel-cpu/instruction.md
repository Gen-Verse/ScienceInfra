Accelerate LAPS — a pseudo-spectral Hall-MHD solver (Fortran 90 + MPI +
FFTW3) — on this machine, preserving the numerical scheme and the output file
format exactly. Correctness is a trajectory match against the pinned build:
three configurations, every graded cell within 1e-10 absolute of the
incumbent's value, every frame, plus an exact time base.

## What is in this container

    /app/LAPS                 the codebase at the pinned commit, with the
                              task's two patches already applied (a
                              full-precision times.dat sidecar — part of the
                              graded output contract — and a gfortran-12
                              front-end fix). The compressible solvers are
                              the scope: src_compressible/ (3D) and
                              src_compressible/2D/.
    /app/decks/<check>/mhd.input   the three decks:
                              aw-2d-256   2D, 256^2
                              aw-2d-512   2D, 512^2
                              aw-128      3D, 128^3
                              All ideal MHD on a periodic box, tmax = 0.1,
                              dtout = 0.01. LAPS reads ./mhd.input from its
                              working directory.
    /app/checks/<check>/      that check's rubric.json — what is compared, to
                              what bound, and the measured evidence behind
                              the bound — and validate.py, the exact function
                              the verifier will run. You are meant to read
                              both. They are not withheld, and validate.py is
                              more precise than this file.

## The incumbent, and how to build it

The incumbent is LAPS itself, built with pinned arithmetic:

    FLAGS="-O3 -fdefault-real-8 -ffp-contract=off -fallow-argument-mismatch -std=legacy -I/usr/include -L/usr/lib -lfftw3"
    make -C /app/LAPS/src_compressible/2D fftwpath=/usr OPTIONS="$FLAGS"   # -> 2D/mhd.exe
    make -C /app/LAPS/src_compressible    fftwpath=/usr OPTIONS="$FLAGS"   # -> mhd.exe

Run a deck from an empty directory containing the deck as `mhd.input`, on 4
MPI ranks (`mpirun --allow-run-as-root --oversubscribe -np 4 <exe>`). The
incumbent's timing convention is 4 ranks; its output is rank-count invariant.

Building and running the unmodified incumbent and delivering its output is a
legitimate floor: it scores full correctness and a speedup of ~1.0. The task
is everything above that floor — make it faster on this machine's CPUs. Data
layout, FFT strategy, kernel fusion, communication, parallelisation are all
yours to change.

**The scheme is pinned.** You reimplement or accelerate LAPS's algorithm, you
do not replace it: same Runge-Kutta integrator, same dealiasing rule, same
CFL condition and the timestep it produces. Correctness is a trajectory
match, so a more accurate integrator diverges at truncation level and fails —
rejected for being better, which is not a judgement this task can make. The
state, the FFTs and the timestep reduction are FP64; reduced precision is
free anywhere it does not touch the graded state. Do not hard-code anything a
deck can set — the grid size above all.

## What you deliver

One directory per check under `/logs/artifacts/`:

    /logs/artifacts/<check>/out###.dat    every frame the incumbent writes
                                          for that deck, out000.dat included
    /logs/artifacts/<check>/times.dat     the full-precision sidecar: one
                                          line per step, istep time dt

Your product writes what the incumbent writes: same files, same formats. The
format is not restated here because the real thing is in front of you — build
the incumbent, run a deck, read what it produces — and `validate.py` is
precise about how each file is read. How many frames a deck produces, and at
what times, follows from the deck and the CFL condition; deriving it is part
of what is checked. A missing frame is a violation regardless of how good the
others are.

Optionally, self-report wall-clock seconds per check to
`/logs/artifacts/timing.json` as `{"aw-2d-256": <s>, "aw-2d-512": <s>,
"aw-128": <s>}`. It feeds the advisory `speedup` metric and nothing else.

## Grading

Grading happens after your container is gone, in a separate container you
never see, holding a reference produced from the pinned commit with the
pinned flags. Each check's vendored `validate.py` — the same file you have —
compares your delivery against that reference. Per check the score is:

    0.0                        nothing usable delivered
    0.1                        delivered but nonconforming: malformed frames,
                               wrong grid, wrong frame count, bad times.dat
    0.2                        conforming, complete frame set, and then
    + 0.5 x (frames within 1e-10) / (eligible frames)
    + 0.3 if the time base matches: istep exact, dt and time within 1e-10

    = 1.0 exactly when every frame and the time base pass

`reward` is the mean over the three checks. `equivalence_pass` is 1 only if
every check fully passes — that is the strict gate, unchanged from the source
benchmark. A frame of NaN fails; a port that stays correct longer scores
higher; a stable, time-correct run that drifted beyond tolerance scores above
a blow-up and below a pass.

## Do not

- Change the integrator, the dealiasing rule or the CFL timestep rule.
- Hard-code the grid size, the rank count or the device count.
- Fabricate output. There is nothing to copy from — no reference exists in
  this container — and hand-written frames that match a pseudo-spectral
  trajectory to 1e-10 do not happen. Byte-identity with the reference is
  flagged as a warning (it is what running the unmodified incumbent
  produces); a fast run whose output is wrong is worth 0.
- Assume network access. Everything you need is in this container.
