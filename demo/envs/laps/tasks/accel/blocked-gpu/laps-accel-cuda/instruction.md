Port LAPS — a pseudo-spectral Hall-MHD solver (Fortran 90 + MPI + FFTW3) —
to the GPU in this container, preserving the numerical scheme and the output
file format exactly. Correctness is a trajectory match against the pinned CPU
build: three configurations, every graded cell within 1e-10 absolute of the
incumbent's value, every frame, plus an exact time base. The port must
actually run on the GPU, and it must prove that: every graded run goes
through the telemetry wrapper, and GPU-idle telemetry zeroes the training
reward.

## What is in this container

    /app/LAPS                 the codebase at the pinned commit, patches
                              applied (full-precision times.dat sidecar —
                              part of the graded output contract — and a
                              gfortran front-end fix). Scope is the
                              compressible solvers: src_compressible/ (3D)
                              and src_compressible/2D/.
    /app/decks/<check>/mhd.input   the three decks:
                              aw-2d-256   2D, 256^2
                              aw-2d-512   2D, 512^2
                              aw-128      3D, 128^3
                              All ideal MHD, tmax = 0.1, dtout = 0.01. LAPS
                              reads ./mhd.input from its working directory.
    /app/checks/<check>/      that check's rubric.json (what is compared, to
                              what bound, and the measured evidence behind
                              the bound) and validate.py — the exact function
                              the verifier runs. Read both; validate.py is
                              more precise than this file.
    nvcc + CUDA 12.6 libraries (cuFFT included) — the GPU toolchain.
                              CUDA Fortran (nvfortran) is NOT installed; a
                              port in CUDA C/C++ against cuFFT, driven from
                              or replacing the Fortran, is the expected
                              route. HIP/SYCL are acceptable if you can make
                              them run here.
    gpu-wrap                  on PATH. `gpu-wrap <out.csv> -- <command...>`
                              samples GPU utilisation while the command runs.

## The incumbent — your baseline and your specification

The CPU incumbent builds with:

    FLAGS="-O3 -fdefault-real-8 -ffp-contract=off -fallow-argument-mismatch -std=legacy -I/usr/include -L/usr/lib -lfftw3"
    make -C /app/LAPS/src_compressible/2D fftwpath=/usr OPTIONS="$FLAGS"   # -> 2D/mhd.exe
    make -C /app/LAPS/src_compressible    fftwpath=/usr OPTIONS="$FLAGS"   # -> mhd.exe

Run a deck from an empty directory containing it as `mhd.input`
(`mpirun --allow-run-as-root --oversubscribe -np 4 <exe>`). Build it, run
it, read what it writes — the incumbent is the output specification, and its
trajectory is what your port must reproduce.

**The scheme is pinned.** Same Runge-Kutta integrator, same dealiasing rule,
same CFL condition and the timestep it produces. The state, the FFTs and the
timestep reduction are FP64 on the device; reduced precision is free
anywhere it does not touch the graded state. Everything else — data layout,
batching, kernel fusion, how much of the Fortran survives — is yours. Do
not hard-code anything a deck can set, the grid size above all.

## What you deliver

One directory per check under `/logs/artifacts/`:

    /logs/artifacts/<check>/out###.dat      every frame the incumbent writes
                                            for that deck, out000.dat included
    /logs/artifacts/<check>/times.dat       one line per step: istep time dt
    /logs/artifacts/<check>/telemetry.csv   the gpu-wrap output for the run
                                            that produced those files

Produce the graded outputs with your port running on the GPU, through the
wrapper:

    gpu-wrap /logs/artifacts/aw-128/telemetry.csv -- <your port> ...

Frame counts and frame times follow from the deck and the CFL condition;
deriving them is part of what is checked. A missing frame is a violation.
Optionally self-report wall seconds per check to
`/logs/artifacts/timing.json` (`{"aw-2d-256": <s>, ...}`) — advisory only.

## Grading

A separate container you never see holds a reference produced from the
pinned commit with the pinned flags (canonical gfortran-12 build — a
different correct build than this container produces, so byte-identity is
neither expected nor required). Each check's vendored `validate.py` decides
correctness; per check:

    0.0 nothing usable · 0.1 nonconforming · else
    0.2 + 0.5 x (frames within 1e-10)/(eligible frames) + 0.3 x (time base)

Two aggregate rewards are written:

    reward      = mean over checks — correctness alone
    gpu_active  = 1 only if every check's telemetry.csv holds plausible
                  GPU-load samples (enough rows, utilisation above idle)
    reward_gpu  = reward x gpu_active — the score that counts on a GPU fleet

Running the unmodified CPU incumbent and delivering its output scores
`reward` 1.0 and `reward_gpu` 0.0: correct, and not the task.

## Do not

- Change the integrator, the dealiasing rule or the CFL timestep rule.
- Hard-code the grid size, the rank count or the device count.
- Fabricate output or telemetry. There is no reference in this container to
  copy; hand-written frames matching a pseudo-spectral trajectory to 1e-10
  do not happen; and a telemetry file claiming GPU load for a CPU run is the
  first thing the grading transcript is audited for.
- Assume network access at run time.
