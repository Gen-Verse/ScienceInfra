# The agent's room for the GPU-port task: LAPS at the pinned commit with the
# task's patches applied, the CPU toolchain the incumbent needs, the CUDA
# toolchain the port needs, the three decks, the public validators, and the
# GPU telemetry wrapper. No prebuilt binaries.
#
# Base: CUDA 12.6.2 devel on Ubuntu 24.04, pinned by INDEX digest — the same
# pin the v1 sa-0001 package used. The index carries linux/amd64 and
# linux/arm64, so this builds natively on an x86 GPU fleet and on an
# Apple-silicon dev machine alike (the arm64 variant has no GPU driver
# userspace at runtime unless the host injects one — which is exactly what
# lets oracle/nop verification run on a GPU-less machine).
#
# NOTE the deliberate asymmetry with the verifier: the REFERENCE is built in
# the verifier image from the benchmark's canonical recipe (debian bookworm
# digest, gfortran 12). This container carries Ubuntu 24.04 / gfortran 13 —
# a legitimately different build. MEASURED (2026-08-26, arm64): the oracle
# built here reproduced the reference BITWISE on all three decks anyway;
# with -ffp-contract=off these two toolchains emit identical arithmetic for
# LAPS. So the oracle passes with the byte-identity warning, and the 1e-10
# band's cross-build headroom (floors 1e-17..6e-16 in the source package)
# remains unexercised by it — no bound is at risk either way.
FROM nvidia/cuda:12.6.2-devel-ubuntu24.04@sha256:738fba0fbdb225b7a2931c58a5c8f03a84d3cd2f6a84975826a157339ef750b8

ENV DEBIAN_FRONTEND=noninteractive

# gfortran/OpenMPI/FFTW3: the incumbent's stack (the CPU baseline must remain
# buildable — it is the correctness anchor and the thing being ported).
# nvcc + the CUDA libraries (cuFFT included) come with the devel base; that
# is the provided GPU toolchain. CUDA Fortran (nvfortran) is NOT shipped —
# the HPC SDK adds ~15 GB; a port in CUDA C/C++ against cuFFT, driven from
# or replacing the Fortran, is the expected route.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git make gfortran python3 python3-numpy \
        openmpi-bin libopenmpi-dev libfftw3-dev \
        time procps \
 && rm -rf /var/lib/apt/lists/*

# The package distributes a link and a commit, never the codebase (GPL-2.0).
ARG REPO=https://github.com/chenshihelio/LAPS
ARG SHA=a625806931a82ba3342f35906955e6806081d219
RUN git clone --quiet "$REPO" /app/LAPS \
 && git -C /app/LAPS checkout --quiet "$SHA"

# The task's two patches, applied to both compressible trees. The times.dat
# sidecar is part of the graded output contract — a port must emit it too.
COPY patches/ /opt/task/patches/
RUN python3 /opt/task/patches/apply-times-sidecar.py /app/LAPS/src_compressible/2D/mhd.f90 \
 && python3 /opt/task/patches/apply-gfortran-fix.py  /app/LAPS/src_compressible/2D/mhd.f90 \
 && python3 /opt/task/patches/apply-times-sidecar.py /app/LAPS/src_compressible/mhd.f90 \
 && python3 /opt/task/patches/apply-gfortran-fix.py  /app/LAPS/src_compressible/mhd.f90

# Decks, public validators, and the GPU telemetry wrapper (see instruction.md
# — every graded run goes through it; its output is part of the delivery).
COPY decks/  /app/decks/
COPY checks/ /app/checks/
COPY bin/    /opt/task/bin/
RUN chmod +x /opt/task/bin/* && mkdir -p /app/run /logs/artifacts

ENV PATH="/opt/task/bin:${PATH}"

WORKDIR /app
