# The verifier's container, built from tests/ as its own context. It runs
# AFTER the agent's container is gone; harbor transfers only the agent's
# publish directory /logs/artifacts/ into it. task.toml declares
# [verifier] environment_mode = "separate" — without that line the grader
# would run inside the agent's container, with the reference sitting beside
# the answer it checks.
#
# THE REFERENCE IS PRODUCED IN SITU, HERE, AT IMAGE BUILD TIME: stage one is
# byte-for-byte the source package's check recipe (same base digest, same
# clone at the same pin, same patches, same pinned arithmetic flags), and it
# runs the three decks. No reference is stored anywhere else — rebuilding the
# image reproduces it, and perturbing a deck moves it. The image builds once
# and is cached across every rollout, which is what makes this shape cheap
# for RL: verification is file comparison, never simulation.

# ---- stage 1: build the incumbent and produce the reference ---------------
# Base digest IDENTICAL to environment/Dockerfile and to the source package's
# check images. The arithmetic is pinned by -ffp-contract=off (FMA fuses
# differently on amd64 vs arm64 otherwise); the front-end flags are what
# upstream needs under gfortran 12. Deviating from any of this builds a
# different reference than the one the evidence bands were measured for.
FROM debian:bookworm-slim@sha256:1caf1c703c8f7e15dcf2e7769b35000c764e6f50e4d7401c355fb0248f3ddfdb AS reference

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git make gfortran python3 \
        openmpi-bin libopenmpi-dev libfftw3-dev \
 && rm -rf /var/lib/apt/lists/*

ARG REPO=https://github.com/chenshihelio/LAPS
ARG SHA=a625806931a82ba3342f35906955e6806081d219
RUN git clone --quiet "$REPO" /opt/LAPS \
 && git -C /opt/LAPS checkout --quiet "$SHA"

COPY patches/ /opt/patches/
RUN python3 /opt/patches/apply-times-sidecar.py /opt/LAPS/src_compressible/2D/mhd.f90 \
 && python3 /opt/patches/apply-gfortran-fix.py  /opt/LAPS/src_compressible/2D/mhd.f90 \
 && python3 /opt/patches/apply-times-sidecar.py /opt/LAPS/src_compressible/mhd.f90 \
 && python3 /opt/patches/apply-gfortran-fix.py  /opt/LAPS/src_compressible/mhd.f90

ARG FPCONTRACT=off
RUN make -C /opt/LAPS/src_compressible/2D fftwpath=/usr \
      OPTIONS="-O3 -fdefault-real-8 -ffp-contract=$FPCONTRACT \
 -fallow-argument-mismatch -std=legacy \
 -I/usr/include -L/usr/lib -lfftw3" \
 && test -x /opt/LAPS/src_compressible/2D/mhd.exe \
 && make -C /opt/LAPS/src_compressible fftwpath=/usr \
      OPTIONS="-O3 -fdefault-real-8 -ffp-contract=$FPCONTRACT \
 -fallow-argument-mismatch -std=legacy \
 -I/usr/include -L/usr/lib -lfftw3" \
 && test -x /opt/LAPS/src_compressible/mhd.exe

# Run the three decks — 4 ranks, like the source package's check images (the
# output is bitwise rank-invariant; 4 is the timing convention). Wall times
# land in incumbent_timing.json: measured on whatever machine built this
# image, recorded because a measured number beats an absent one, and labelled
# advisory because the agent's rollout may run on a different machine.
COPY decks/ /opt/decks/
COPY make_timing.py /opt/make_timing.py
RUN set -e; \
    for c in aw-2d-256 aw-2d-512 aw-128; do \
      case "$c" in \
        aw-2d-*) EXE=/opt/LAPS/src_compressible/2D/mhd.exe ;; \
        *)       EXE=/opt/LAPS/src_compressible/mhd.exe ;; \
      esac; \
      mkdir -p /ref/run-$c /ref/$c; \
      cd /ref/run-$c; \
      cp /opt/decks/$c/mhd.input ./mhd.input; \
      t0=$(date +%s%N); \
      mpirun --allow-run-as-root --oversubscribe -np 4 "$EXE"; \
      t1=$(date +%s%N); \
      echo "$c $t0 $t1" >> /ref/walltimes.txt; \
      cp out*.dat times.dat /ref/$c/; \
      cd /; rm -rf /ref/run-$c; \
    done; \
    python3 /opt/make_timing.py /ref/walltimes.txt /ref/incumbent_timing.json

# ---- stage 2: the grader ---------------------------------------------------
# Slim runtime: python + a pinned numpy (a verifier whose numerics drift is a
# verifier that fails last month's passing port), the reference, and the
# vendored validators. Harbor runs /tests/test.sh; there is no network.
FROM python:3.13-slim

RUN pip install --no-cache-dir numpy==2.1.3

COPY --from=reference /ref/ /tests/reference/

COPY checks/   /tests/checks/
COPY grade.py  /tests/grade.py
COPY test.sh   /tests/test.sh
RUN chmod +x /tests/test.sh \
 && mkdir -p /logs/verifier /logs/artifacts
