# The agent's room: LAPS at the pinned commit with the task's patches applied,
# the toolchain the incumbent needs, the three decks, and the public
# validators. NO prebuilt binaries — building the incumbent with the pinned
# flags is the floor of the task, and instruction.md hands over the recipe.
#
# Base PINNED BY DIGEST, and it is the same digest the source package's check
# images pin. This matters beyond reproducibility: the verifier's reference is
# built FROM THE SAME BASE with the same flags, so an unmodified incumbent
# built here reproduces the reference bitwise (LAPS is deterministic and
# rank-count invariant on these decks — measured in the source package).
FROM debian:bookworm-slim@sha256:1caf1c703c8f7e15dcf2e7769b35000c764e6f50e4d7401c355fb0248f3ddfdb

ENV DEBIAN_FRONTEND=noninteractive

# python3-numpy: so the agent can run the public validate.py against its own
# runs (self-comparison; there is no reference in this container to compare
# against, but conformance checking and incumbent-vs-port comparison are
# both open to it).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git make gfortran python3 python3-numpy \
        openmpi-bin libopenmpi-dev libfftw3-dev \
        time procps tmux \
 && rm -rf /var/lib/apt/lists/*

# The package distributes a link and a commit, never the codebase (GPL-2.0
# upstream; nothing is vendored).
ARG REPO=https://github.com/chenshihelio/LAPS
ARG SHA=a625806931a82ba3342f35906955e6806081d219
RUN git clone --quiet "$REPO" /app/LAPS \
 && git -C /app/LAPS checkout --quiet "$SHA"

# The task's two patches, applied to both compressible trees (2D and 3D):
#   apply-times-sidecar   additive full-precision (istep, time, dt) log —
#                         times.dat, part of the graded output contract
#   apply-gfortran-fix    upstream targets an older front end; one site is
#                         rejected outright by gfortran 12
# They are applied HERE, not left to the agent: they are part of the output
# contract and the reference carries them too. A port must keep the sidecar.
COPY patches/ /opt/task/patches/
RUN python3 /opt/task/patches/apply-times-sidecar.py /app/LAPS/src_compressible/2D/mhd.f90 \
 && python3 /opt/task/patches/apply-gfortran-fix.py  /app/LAPS/src_compressible/2D/mhd.f90 \
 && python3 /opt/task/patches/apply-times-sidecar.py /app/LAPS/src_compressible/mhd.f90 \
 && python3 /opt/task/patches/apply-gfortran-fix.py  /app/LAPS/src_compressible/mhd.f90

# The three decks, at the paths instruction.md names.
COPY decks/ /app/decks/

# The public validators — rubric.json states each check's bounds and the
# measured evidence behind them; validate.py is the exact function the
# verifier will run. Vendored byte-for-byte from the source package.
COPY checks/ /app/checks/

# Scratch for runs, and the publish directory the verifier reads (harbor
# mounts /logs/artifacts; creating it here just makes it exist for local
# `docker run` debugging too).
RUN mkdir -p /app/run /logs/artifacts

WORKDIR /app
