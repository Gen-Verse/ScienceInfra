"""Compile canonical task rows into self-contained harbor task directories.

    python3 adapters/to_harbor.py [--rows envs/laps/tasks.jsonl]
                                  [--out tasks/] [--only GLOB]

The two-level layout this adapter serves (the SWE-smith-shaped split):

    envs/laps/          ENV level — heavy, one per repo: canonical decks,
                        checks, patches, verifier base (grade.py/test.sh/
                        make_timing.py), and tasks.jsonl, the canonical rows.
    tasks/laps-*/       TASK level, COMPILED — one self-contained harbor task
                        dir per row, the format `harbor run -p` loads
                        natively. Regenerable at any time from the row; never
                        hand-edit a compiled dir.

A row fully determines its compiled dir (instruction symptom text included),
so compilation is deterministic and byte-stable: same row + same envs/laps
assets -> same bytes. The canary is uuid5 of the task name and is asserted,
not trusted.

Row schema (one JSON object per line):

    {"task": "laps-repair-...", "canary": "<uuid5(task)>",
     "category": "repair"|"implementation", "mode": "injected|excision|historical",
     "checks": ["aw-2d-256", ...], "symptom": "<markdown bullet block>",
     "candidate": {id, source, family, tree, note, break, fix, meta},
     "funnel":    {the full funnel verdict row, floor included}}

Everything the agent must never see (fix, funnel detail) stays out of the
compiled agent image by construction: the defect spec exists only in the env
Dockerfile's prep stage, solution/ is mounted only for oracle runs, and
authoring/provenance.json enters no image.
"""

import argparse
import fnmatch
import json
import os
import shutil
import sys
import uuid

sys.dont_write_bytecode = True
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "authoring", "repair"))
import config  # noqa: E402
import lib  # noqa: E402

DIGEST = "debian:bookworm-slim@sha256:1caf1c703c8f7e15dcf2e7769b35000c764e6f50e4d7401c355fb0248f3ddfdb"
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid5 namespace (DNS)

MAKE = ('make -C {root}/src_compressible{sub} fftwpath=/usr \\\n'
        '      OPTIONS="-O3 -fdefault-real-8 -ffp-contract=off \\\n'
        ' -fallow-argument-mismatch -std=legacy \\\n'
        ' -I/usr/include -L/usr/lib -lfftw3" \\\n'
        ' && test -x {root}/src_compressible{sub}/mhd.exe')

# Opt-in apt mirror, consumed by every apt stage below. The default is baked at
# generation time by `--apt-mirror` (empty unless asked for, so generated
# Dockerfiles behave exactly as upstream), and can still be overridden per build
# with `--build-arg APT_MIRROR=...`.
#
# The default has to live in the Dockerfile rather than arriving as a
# compose-level build arg: harbor clears `extra_docker_compose` when it builds
# the separate verifier environment (trial.py `_separate_verifier_env`), so a
# compose overlay reaches the agent image only. Clusters whose sole egress is a
# slow HTTP proxy need both halves: on one such box the toolchain stage took
# over three hours through the proxy and 54 s against an internal mirror.
APT_MIRROR_ARG = '''ARG APT_MIRROR=@MIRROR_DEFAULT@
RUN if [ -n "$APT_MIRROR" ]; then \\
      sed -i "s|http://deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; \\
    fi
'''


def checks_of(tree):
    if tree == "both":
        return config.TREES["2d"]["checks"] + config.TREES["3d"]["checks"]
    return list(config.TREES[tree]["checks"])


def slug_of(cid):
    import re
    s = re.sub(r"[^a-z0-9]+", "-", cid.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def task_name(cand):
    restore = cand["source"] == "excise"
    kind = "laps-restore" if restore else "laps-repair"
    slug = slug_of(cand["id"].removeprefix("excise-") if restore else cand["id"])
    return f"{kind}-{slug}"


def canary_of(name):
    return str(uuid.uuid5(NS, "sciaccel-rl/" + name))


# ---------------------------------------------------------------- templates

APPLY_DEFECT = '''#!/usr/bin/env python3
"""Apply a transform spec to a source tree.

Spec: {"edits": [{"file","old","new"}]} (exact-string, old unique per file)
   or {"diff": "<unified diff>"} (applied with patch -p1).
Usage: apply_defect.py SPEC.json TREE_ROOT
"""
import json, os, subprocess, sys

spec, root = sys.argv[1], sys.argv[2]
t = json.load(open(spec))
if "edits" in t:
    for e in t["edits"]:
        p = os.path.join(root, e["file"])
        s = open(p, encoding="utf-8").read()
        n = s.count(e["old"])
        if n != 1:
            sys.exit(f"{p}: pattern occurs {n} times, need exactly 1")
        open(p, "w", encoding="utf-8").write(s.replace(e["old"], e["new"], 1))
elif "diff" in t:
    r = subprocess.run(["patch", "-p1", "--no-backup-if-mismatch", "-f"],
                       input=t["diff"], text=True, cwd=root)
    if r.returncode:
        sys.exit("patch failed")
else:
    sys.exit("transform carries neither edits nor diff")
print(f"applied {spec} to {root}")
'''

ENV_DOCKERFILE = '''# @NAME@: agent environment — LAPS at the pin with the task patches AND the
# generated defect applied. Multi-stage on purpose: the defect spec exists
# only in the prep stage; the final image carries the defective tree with no
# defect files and no .git, so there is nothing inside the container to diff
# the source against.
FROM @DIGEST@ AS prep

ENV DEBIAN_FRONTEND=noninteractive
@APT_MIRROR@RUN apt-get update && apt-get install -y --no-install-recommends \\
        ca-certificates git python3 patch \\
 && rm -rf /var/lib/apt/lists/*

ARG REPO=@REPO@
ARG SHA=@SHA@
RUN git clone --quiet "$REPO" /app/LAPS \\
 && git -C /app/LAPS checkout --quiet "$SHA"

# The donor task's two patches (times.dat sidecar is part of the graded
# output contract; gfortran front-end fix), applied to both trees.
COPY patches/ /opt/task/patches/
RUN python3 /opt/task/patches/apply-times-sidecar.py /app/LAPS/src_compressible/2D/mhd.f90 \\
 && python3 /opt/task/patches/apply-gfortran-fix.py  /app/LAPS/src_compressible/2D/mhd.f90 \\
 && python3 /opt/task/patches/apply-times-sidecar.py /app/LAPS/src_compressible/mhd.f90 \\
 && python3 /opt/task/patches/apply-gfortran-fix.py  /app/LAPS/src_compressible/mhd.f90

COPY defect/ /opt/defect/
# Apply the defect, strip .git, AND strip every ungraded sibling solver tree:
# src_incompressible carries byte-identical copies of several mutated files
# (rktmod diffs by 0 lines), and the other compressible tree is a near-mirror
# — pristine siblings in the image are the answer key. Content-anchored leak
# scan in gate_pack enforces this.
RUN python3 /opt/defect/apply_defect.py /opt/defect/defect.json /app/LAPS \\
 && rm -rf /app/LAPS/.git \\
 && @STRIP@

# ---- the agent's image: toolchain + the defective tree ---------------------
FROM @DIGEST@

ENV DEBIAN_FRONTEND=noninteractive
# tmux drives harbor's terminus-2 shell, while asciinema records that shell
# when record_terminal_session keeps its default value (true). Bake both in:
# [environment] network_mode is "no-network", so terminus-2's runtime apt/pip
# fallbacks cannot reach a mirror. Missing tmux kills the trial; missing
# asciinema lets it continue but adds failed installs and loses recording.cast.
@APT_MIRROR@RUN apt-get update && apt-get install -y --no-install-recommends \\
        ca-certificates git make gfortran python3 python3-numpy \\
        openmpi-bin libopenmpi-dev libfftw3-dev patch \\
        time procps tmux asciinema \\
 && rm -rf /var/lib/apt/lists/*

COPY --from=prep /app/LAPS /app/LAPS
COPY decks/ /app/decks/
COPY checks/ /app/checks/
RUN mkdir -p /app/run /logs/artifacts
WORKDIR /app
'''

TESTS_DOCKERFILE = '''# @NAME@: verifier. Three stages, everything produced in situ:
#   reference  clean pinned build runs the graded decks -> /ref
#   straw      the SAME build recipe with the defect applied runs the same
#              decks, and is graded against /ref by the task's own grade.py
#              -> /floor.json. The floor is measured where it is used; the
#              factory's native estimate is advisory metadata only.
#   grader     python + numpy + reference + floor.json + vendored checks.
FROM @DIGEST@ AS reference

ENV DEBIAN_FRONTEND=noninteractive
@APT_MIRROR@RUN apt-get update && apt-get install -y --no-install-recommends \\
        ca-certificates git make gfortran python3 python3-numpy patch \\
        openmpi-bin libopenmpi-dev libfftw3-dev \\
 && rm -rf /var/lib/apt/lists/*

ARG REPO=@REPO@
ARG SHA=@SHA@
RUN git clone --quiet "$REPO" /opt/LAPS \\
 && git -C /opt/LAPS checkout --quiet "$SHA"

COPY patches/ /opt/patches/
RUN python3 /opt/patches/apply-times-sidecar.py /opt/LAPS/src_compressible/2D/mhd.f90 \\
 && python3 /opt/patches/apply-gfortran-fix.py  /opt/LAPS/src_compressible/2D/mhd.f90 \\
 && python3 /opt/patches/apply-times-sidecar.py /opt/LAPS/src_compressible/mhd.f90 \\
 && python3 /opt/patches/apply-gfortran-fix.py  /opt/LAPS/src_compressible/mhd.f90

ARG FPCONTRACT=off
RUN @REF_BUILDS@

COPY decks/ /opt/decks/
COPY make_timing.py /opt/make_timing.py
RUN set -e; \\
    for c in @CHECKS_SH@; do \\
      case "$c" in \\
        aw-2d-*) EXE=/opt/LAPS/src_compressible/2D/mhd.exe ;; \\
        *)       EXE=/opt/LAPS/src_compressible/mhd.exe ;; \\
      esac; \\
      mkdir -p /ref/run-$c /ref/$c; \\
      cd /ref/run-$c; \\
      cp /opt/decks/$c/mhd.input ./mhd.input; \\
      t0=$(date +%s%N); \\
      mpirun --allow-run-as-root --oversubscribe -np 4 "$EXE"; \\
      t1=$(date +%s%N); \\
      echo "$c $t0 $t1" >> /ref/walltimes.txt; \\
      cp out*.dat times.dat /ref/$c/; \\
      cd /; rm -rf /ref/run-$c; \\
    done; \\
    python3 /opt/make_timing.py /ref/walltimes.txt /ref/incumbent_timing.json

# ---- straw: what the UNFIXED tree earns, measured by the task's own grader
FROM reference AS straw

COPY defect/ /opt/defect/
COPY grade.py grade_floor.py /opt/
COPY checks/ /opt/checks/
RUN set -e; \\
    cp -r /opt/LAPS /opt/LAPS-straw; \\
    python3 /opt/defect/apply_defect.py /opt/defect/defect.json /opt/LAPS-straw; \\
    find /opt/LAPS-straw \\( -name '*.o' -o -name '*.mod' -o -name 'mhd.exe' \\) -delete; \\
    @STRAW_BUILDS@; \\
    for c in @CHECKS_SH@; do \\
      case "$c" in \\
        aw-2d-*) EXE=/opt/LAPS-straw/src_compressible/2D/mhd.exe ;; \\
        *)       EXE=/opt/LAPS-straw/src_compressible/mhd.exe ;; \\
      esac; \\
      mkdir -p /straw/run-$c /straw/$c; \\
      cd /straw/run-$c; \\
      cp /opt/decks/$c/mhd.input ./mhd.input; \\
      timeout 600 mpirun --allow-run-as-root --oversubscribe -np 4 "$EXE" || true; \\
      cp out*.dat /straw/$c/ 2>/dev/null || true; \\
      cp times.dat /straw/$c/ 2>/dev/null || true; \\
      cd /; rm -rf /straw/run-$c; \\
    done; \\
    python3 /opt/grade_floor.py --grade /opt/grade.py --candidate /straw \\
      --reference /ref --checks-dir /opt/checks --out /floor.json; \\
    rm -rf /straw /opt/LAPS-straw

# ---- grader ---------------------------------------------------------------
FROM python:3.13-slim

RUN pip install --no-cache-dir numpy==2.1.3

COPY --from=reference /ref/ /tests/reference/
COPY --from=straw /floor.json /tests/floor.json

COPY checks/   /tests/checks/
COPY grade.py  /tests/grade.py
COPY test.sh   /tests/test.sh
RUN chmod +x /tests/test.sh \\
 && mkdir -p /logs/verifier /logs/artifacts
'''

GRADE_FLOOR = '''#!/usr/bin/env python3
"""Measure the straw floor: grade the unfixed build's delivery with the
task's own grade.py, keep reward + per-check scores as /floor.json.
Runs at verifier-image build; the straw outputs are deleted afterwards."""
import argparse, json, subprocess, sys, tempfile, os

ap = argparse.ArgumentParser()
ap.add_argument("--grade", required=True)
ap.add_argument("--candidate", required=True)
ap.add_argument("--reference", required=True)
ap.add_argument("--checks-dir", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

with tempfile.TemporaryDirectory() as td:
    out, rep = os.path.join(td, "r.json"), os.path.join(td, "rep.json")
    r = subprocess.run([sys.executable, a.grade, "--candidate", a.candidate,
                        "--reference", a.reference, "--checks-dir", a.checks_dir,
                        "--out", out, "--report", rep], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(out):
        sys.exit("floor grading failed:\\n" + r.stdout + r.stderr)
    g = json.load(open(out))

floor = {"floor": g["reward"],
         "per_check": {k: v for k, v in g.items() if k.startswith("check_")}}
json.dump(floor, open(a.out, "w"), indent=1, sort_keys=True)
print("straw floor:", json.dumps(floor, sort_keys=True))
'''

SOLVE_SH = '''#!/bin/bash
# @NAME@ oracle: apply the exact inverse of the generated defect, rebuild the
# affected tree(s) with the pinned flags, run the graded decks, deliver.
# Expect reward 1.0, reward_repair 1.0 (and the byte-identity warning: after
# the fix this IS the incumbent, same base, same flags).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$HERE/apply_defect.py" "$HERE/defect_fix.json" /app/LAPS

FLAGS="-O3 -fdefault-real-8 -ffp-contract=off -fallow-argument-mismatch -std=legacy -I/usr/include -L/usr/lib -lfftw3"
RANKS="${RANKS:-4}"

@BUILDS@

: > /tmp/walltimes.txt
for c in @CHECKS_SH@; do
  case "$c" in
    aw-2d-*) EXE=/app/LAPS/src_compressible/2D/mhd.exe ;;
    *)       EXE=/app/LAPS/src_compressible/mhd.exe ;;
  esac
  mkdir -p "/app/run/$c" "/logs/artifacts/$c"
  cd "/app/run/$c"
  cp "/app/decks/$c/mhd.input" ./mhd.input
  t0=$(date +%s%N)
  mpirun --allow-run-as-root --oversubscribe -np "$RANKS" "$EXE"
  t1=$(date +%s%N)
  echo "$c $t0 $t1" >> /tmp/walltimes.txt
  cp out*.dat times.dat "/logs/artifacts/$c/"
done

python3 - <<'EOF'
import json
rows = {}
for line in open('/tmp/walltimes.txt'):
    c, t0, t1 = line.split()
    rows[c] = round((int(t1) - int(t0)) / 1e9, 3)
with open('/logs/artifacts/timing.json', 'w') as f:
    json.dump(rows, f, indent=1)
EOF

echo "oracle: fixed, rebuilt, delivered"
'''

TASK_TOML = '''# @NAME@ — auto-generated by utils/authoring/repair (sciaccel-rl task factory).
# Machinery: envs/laps/env (cases, validation, scoring, upstream-patches);
# donor task: envs/laps/tasks/acceleration/laps-accel-cpu.
# Reference AND straw floor are produced in situ at verifier-image build.

schema_version = "1.4"

[task]
name = "sciaccel/@NAME@"
description = "@DESCRIPTION@"

[metadata.provenance]
derived_from = "sciaccel-rl envs/laps machinery (donor task laps-accel-cpu); defect generated and funnel-validated by utils/authoring/repair"
upstream_repo = "@REPO@"
upstream_commit = "@SHA@"
upstream_license = "GPL-2.0"

[metadata.taxonomy]
category = "@CATEGORY@"
mode = "@MODE@"
family = "@FAMILY@"
tree = "@TREE@"
affected_checks = @CHECKS_TOML@
defect_file = "@DEFECT_FILE@"
floor_native_estimate = @FLOOR@
canary = "@CANARY@"
# Memorization note: the upstream repository is public. A model may hold the
# pristine source in its weights; for excision tasks especially, treat these
# as curriculum lower rungs, not evidence of frontier difficulty (TAXONOMY.md
# section 3).

[environment]
cpus = 4
memory_mb = @MEM@
build_timeout_sec = 3600.0
# THE repair exploit is diffing against the public upstream at runtime; the
# pristine source is one `git clone` away. Enforced off, not asked off.
# (Image BUILDS still have network; this is the runtime policy.)
network_mode = "no-network"

[agent]
# The one clock the agent cannot forge. Enough to read, build (~1 min),
# run the graded decks many times over, and think between runs.
timeout_sec = @AGENT_TIMEOUT@

[verifier]
timeout_sec = 900.0
environment_mode = "separate"

[verifier.environment]
# Builds the clean reference AND the defective straw build, runs the graded
# decks twice over, grades the straw -> floor.json. Cached across rollouts.
cpus = 4
memory_mb = @MEM@
build_timeout_sec = 10800.0
network_mode = "no-network"
'''

INSTRUCTION_REPAIR = '''<!-- @CANARY@ -->
Find and fix a defect in LAPS — a pseudo-spectral MHD solver (Fortran 90 +
MPI + FFTW3). The @SCOPE@ in this container carries a single localized
defect in one source file. The symptom is described below; the root cause
and its location are yours to find. The verifier compares your rebuilt
solver's trajectories against the unmodified incumbent's, produced in situ
from the pinned build — the fix is correct when the physics is restored.

## Symptom

@SYMPTOM@

These decks are small Alfvén-wave configurations of ideal compressible MHD
on a periodic box (tmax = 0.1, dtout = 0.01). The incumbent solver
reproduces them to machine determinism; this build does not.

## What is in this container

    /app/LAPS                      the codebase at the pinned commit, task
                                   patches applied, DEFECT INCLUDED. No git
                                   history; ungraded sibling solver trees
                                   are removed. The graded scope: @SCOPE_PATHS@
    /app/decks/<check>/mhd.input   the graded decks: @CHECKS_LIST@
    /app/checks/<check>/           rubric.json (tolerances and their measured
                                   evidence) and validate.py — the exact
                                   function the verifier runs. You can and
                                   should run it yourself to compare two of
                                   your own runs; no reference outputs exist
                                   in this container.

## Build recipe

    FLAGS="-O3 -fdefault-real-8 -ffp-contract=off -fallow-argument-mismatch -std=legacy -I/usr/include -L/usr/lib -lfftw3"
@BUILD_LINES@

Run a deck from an empty directory containing the deck as `mhd.input`, on 4
MPI ranks (`mpirun --allow-run-as-root --oversubscribe -np 4 <exe>`). Output
is rank-count invariant.

## What you deliver

Fixing the code earns NOTHING on its own. Grading reads only
`/logs/artifacts/`, in a separate container after yours is gone. A correct
one-line fix that is never copied there scores 0.0, identical to no attempt.

For EVERY graded check (@CHECKS_LIST@), copy the solver output:

    mkdir -p /logs/artifacts/<check>
    cp <rundir>/out*.dat /logs/artifacts/<check>/
    cp <rundir>/times.dat /logs/artifacts/<check>/

so that afterwards:

    /logs/artifacts/<check>/out###.dat    every frame the solver writes,
                                          out000.dat included
    /logs/artifacts/<check>/times.dat     one line per step: istep time dt

`mkdir` alone delivers nothing; the `cp` is the part that scores. Before you
finish, verify with `ls -la /logs/artifacts/*/` and confirm you see `out000.dat`
and `times.dat` under each check. If that listing is empty, you have not
delivered and your score will be 0.0.

Optionally, self-report wall seconds per check to
`/logs/artifacts/timing.json` (advisory only).

## Grading

Grading happens after your container is gone, in a separate container
holding a reference produced from the UNMODIFIED pinned build. Per check:

    0.0   nothing usable      0.1   nonconforming
    0.2   conforming and complete, then
    + 0.5 x (frames within 1e-10 absolute, pointwise) / (eligible frames)
    + 0.3 if the time base matches: istep exact, dt and time within 1e-10
    = 1.0 exactly when everything passes

`reward` is the mean over the graded checks. The verifier also measures, at
its own build time, what this container's UNFIXED tree earns on that ladder
— the floor (about @FLOOR@ here). The training signal is

    reward_repair = max(0, reward - floor) / (1 - floor)

so delivering the unfixed build's output scores 0.0 on it, and only genuine
repair moves it. `equivalence_pass` is 1 only when every graded check fully
passes.

## Do not

- Do not fabricate or post-process output frames; fix the source. There is
  no reference in this container to copy, and hand-made frames that match a
  pseudo-spectral trajectory to 1e-10 do not happen.
- The numerical scheme is pinned: the fix restores the incumbent's
  behaviour. Do not redesign the solver, change the integrator, the
  dealiasing rule, or the CFL logic beyond what the defect requires.
- Do not hard-code grid sizes, rank counts, or frame counts.
- Assume no network access. Everything you need is in this container.
'''

INSTRUCTION_RESTORE = '''<!-- @CANARY@ -->
Restore a missing routine in LAPS — a pseudo-spectral MHD solver (Fortran 90
+ MPI + FFTW3). In this container's copy of the @SCOPE@, the executable body
of subroutine `@SUB@` in `@DEFECT_FILE@` has been removed and replaced by a
stub (marked in the source). Reimplement it so the solver reproduces the
incumbent's physics exactly — the verifier compares your rebuilt solver's
trajectories against the unmodified incumbent's, produced in situ from the
pinned build, to 1e-10 absolute pointwise plus an exact time base.

What the stub currently does to the solver:

@SYMPTOM@

These decks are small Alfvén-wave configurations of ideal compressible MHD
on a periodic box (tmax = 0.1, dtout = 0.01). Everything the routine needs
— the surrounding module, the arrays it must fill, its callers — is intact
and readable; the physics it must implement follows from them and from the
solver's structure.

## What is in this container

    /app/LAPS                      the codebase at the pinned commit, task
                                   patches applied, the routine body REMOVED.
                                   No git history; ungraded sibling solver
                                   trees are removed.
    /app/decks/<check>/mhd.input   the graded decks: @CHECKS_LIST@
    /app/checks/<check>/           rubric.json and validate.py — the exact
                                   function the verifier runs. Use it to
                                   compare two of your own runs; no reference
                                   outputs exist in this container.

## Build recipe

    FLAGS="-O3 -fdefault-real-8 -ffp-contract=off -fallow-argument-mismatch -std=legacy -I/usr/include -L/usr/lib -lfftw3"
@BUILD_LINES@

Run a deck from an empty directory containing the deck as `mhd.input`, on 4
MPI ranks (`mpirun --allow-run-as-root --oversubscribe -np 4 <exe>`).

## What you deliver

Restoring the subroutine earns NOTHING on its own. Grading reads only
`/logs/artifacts/`, in a separate container after yours is gone. A correct
restoration that is never copied there scores 0.0, identical to no attempt.

For EVERY graded check (@CHECKS_LIST@), copy the solver output:

    mkdir -p /logs/artifacts/<check>
    cp <rundir>/out*.dat /logs/artifacts/<check>/
    cp <rundir>/times.dat /logs/artifacts/<check>/

so that afterwards:

    /logs/artifacts/<check>/out###.dat    every frame, out000.dat included
    /logs/artifacts/<check>/times.dat     one line per step: istep time dt

`mkdir` alone delivers nothing; the `cp` is the part that scores. Before you
finish, verify with `ls -la /logs/artifacts/*/` and confirm you see `out000.dat`
and `times.dat` under each check. If that listing is empty, you have not
delivered and your score will be 0.0.

## Grading

Same ladder as every task in this family: per check 0.2 conformance
+ 0.5 x frame correctness + 0.3 time base, 1.0 on a full pass; `reward` is
the mean. The verifier measures what the stubbed tree earns (about @FLOOR@)
and the training signal is reward_repair = max(0, reward - floor)/(1 -
floor): the stub scores 0.0, only a working reimplementation moves it.

## Do not

- Do not fabricate output frames; implement the routine.
- Match the incumbent's numerical scheme exactly — this is a restoration,
  not a redesign. A better algorithm that diverges at truncation level
  fails.
- Do not hard-code grid sizes, rank counts, or frame counts.
- Assume no network access.
'''


# ------------------------------------------------------------------ builders

def scope_of(tree):
    return {"2d": "2D compressible solver (`src_compressible/2D/`)",
            "3d": "3D compressible solver (`src_compressible/`)",
            "both": "compressible solvers (`src_compressible/` and "
                    "`src_compressible/2D/`)"}[tree]


def scope_paths(tree):
    return {"2d": "src_compressible/2D/", "3d": "src_compressible/",
            "both": "src_compressible/ and src_compressible/2D/"}[tree]


def build_lines(tree, root, indent="    "):
    subs = {"2d": ["/2D"], "3d": [""], "both": ["/2D", ""]}[tree]
    return "\n".join(
        indent + f'make -C {root}/src_compressible{s} fftwpath=/usr OPTIONS="$FLAGS"'
        for s in subs)


def make_blocks(tree, root, joiner):
    subs = {"2d": ["/2D"], "3d": [""], "both": ["/2D", ""]}[tree]
    return joiner.join(MAKE.format(root=root, sub=s) for s in subs)


def strip_cmd(tree):
    """Remove every solver tree the task does not grade from the agent image.

    Ungraded siblings are pristine near-mirrors of the mutated code (the
    incompressible rktmod is byte-identical) — leaving them in ships the
    answer key. The graded tree builds standalone either way (verified)."""
    base = "rm -rf /app/LAPS/src_incompressible"
    if tree == "2d":
        return (base +
                " \\\n && find /app/LAPS/src_compressible -maxdepth 1 -type f -delete")
    if tree == "3d":
        return base + " /app/LAPS/src_compressible/2D"
    return base


def gen_grade_py(checks, canary):
    with open(config.GRADE_PY) as f:
        text = f.read()
    old_checks = 'CHECKS = ["aw-2d-256", "aw-2d-512", "aw-128"]'
    assert old_checks in text, "grade.py base CHECKS drifted; update to_harbor.py"
    text = text.replace(old_checks, "CHECKS = " + json.dumps(checks), 1)
    old_out = '''    rewards_out = {
        "reward": round(sum(scores) / len(scores), 6),
        "equivalence_pass": 1 if all_passed else 0,
        "speedup": speedup(args.candidate, args.reference, all_passed),
    }
    rewards_out.update(rewards)'''
    assert old_out in text, "grade.py base rewards block drifted; update to_harbor.py"
    new_out = '''    floor = 0.0
    floor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "floor.json")
    try:
        with open(floor_path) as f:
            floor = float(json.load(f).get("floor", 0.0))
    except (OSError, ValueError):
        pass
    reward = round(sum(scores) / len(scores), 6)
    rewards_out = {
        "reward": reward,
        # The training signal: what the unfixed build earns is the zero of
        # this scale. floor.json is measured in situ at verifier-image build
        # by grading the defective build with THIS file.
        "reward_repair": round(max(0.0, reward - floor) / max(1e-6, 1.0 - floor), 6),
        "floor": floor,
        "equivalence_pass": 1 if all_passed else 0,
        "speedup": speedup(args.candidate, args.reference, all_passed),
    }
    rewards_out.update(rewards)'''
    text = text.replace(old_out, new_out, 1)
    return f"# {config.CANARY_PREFIX} {canary}\n" + text


def write(path, content, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    if mode:
        os.chmod(path, mode)


def fill(template, **kw):
    out = template
    for k, v in kw.items():
        out = out.replace("@" + k + "@", str(v))
    assert "@" + "NAME@" not in out
    return out


def compile_one(row, out_root, apt_mirror=""):
    cand, fun = row["candidate"], row["funnel"]
    tree = cand["tree"]
    checks = row["checks"]
    restore = cand["source"] == "excise"
    name = row["task"]
    assert name == task_name(cand), f"row task name mismatch for {cand['id']}"
    canary = row["canary"]
    assert canary == canary_of(name), f"canary mismatch for {name}"
    assert checks == checks_of(tree), f"checks mismatch for {name}"

    # Layout level 2: one subdirectory per taxonomy category, so `harbor run
    # -p envs/laps/tasks/<category>` loads a category as a dataset dir.
    task_dir = os.path.join(out_root, row["category"], name)
    if os.path.isdir(task_dir):
        shutil.rmtree(task_dir)
    defect_file = cand.get("meta", {}).get("file") or \
        (cand.get("meta", {}).get("files") or ["?"])[0]
    floor = fun["floor"]
    mem = 8192 if tree == "2d" else 16384

    common = dict(
        NAME=name, DIGEST=DIGEST, REPO=config.LAPS_REPO, SHA=config.LAPS_SHA,
        CHECKS_SH=" ".join(checks), CANARY=f"{config.CANARY_PREFIX} {canary}",
        FLOOR=f"{floor:.2f}", DEFECT_FILE=defect_file, TREE=tree,
        APT_MIRROR=APT_MIRROR_ARG.replace("@MIRROR_DEFAULT@", apt_mirror),
    )

    # -- environment ---------------------------------------------------------
    write(os.path.join(task_dir, "environment", "Dockerfile"),
          fill(ENV_DOCKERFILE, **common, STRIP=strip_cmd(tree)))
    write(os.path.join(task_dir, "environment", "defect", "apply_defect.py"),
          APPLY_DEFECT, mode=0o755)
    write(os.path.join(task_dir, "environment", "defect", "defect.json"),
          json.dumps({**cand["break"], "_canary": canary}, indent=1, sort_keys=True))
    shutil.copytree(config.PATCHES, os.path.join(task_dir, "environment", "patches"))
    for c in checks:
        shutil.copytree(os.path.join(config.DECKS, c),
                        os.path.join(task_dir, "environment", "decks", c))
        shutil.copytree(os.path.join(config.CHECKS_DIR, c),
                        os.path.join(task_dir, "environment", "checks", c))

    # -- tests ---------------------------------------------------------------
    write(os.path.join(task_dir, "tests", "Dockerfile"),
          fill(TESTS_DOCKERFILE, **common,
               REF_BUILDS=make_blocks(tree, "/opt/LAPS", " \\\n && "),
               STRAW_BUILDS=make_blocks(tree, "/opt/LAPS-straw", "; \\\n    ")))
    write(os.path.join(task_dir, "tests", "defect", "apply_defect.py"),
          APPLY_DEFECT, mode=0o755)
    write(os.path.join(task_dir, "tests", "defect", "defect.json"),
          json.dumps({**cand["break"], "_canary": canary}, indent=1, sort_keys=True))
    write(os.path.join(task_dir, "tests", "grade.py"), gen_grade_py(checks, canary))
    write(os.path.join(task_dir, "tests", "grade_floor.py"), GRADE_FLOOR, mode=0o755)
    shutil.copy(config.MAKE_TIMING, os.path.join(task_dir, "tests", "make_timing.py"))
    shutil.copy(config.TEST_SH, os.path.join(task_dir, "tests", "test.sh"))
    os.chmod(os.path.join(task_dir, "tests", "test.sh"), 0o755)
    shutil.copytree(config.PATCHES, os.path.join(task_dir, "tests", "patches"))
    for c in checks:
        shutil.copytree(os.path.join(config.DECKS, c),
                        os.path.join(task_dir, "tests", "decks", c))
        shutil.copytree(os.path.join(config.CHECKS_DIR, c),
                        os.path.join(task_dir, "tests", "checks", c))

    # -- solution ------------------------------------------------------------
    write(os.path.join(task_dir, "solution", "solve.sh"),
          fill(SOLVE_SH, **common,
               BUILDS=make_blocks(tree, "/app/LAPS", "\n")), mode=0o755)
    write(os.path.join(task_dir, "solution", "apply_defect.py"),
          APPLY_DEFECT, mode=0o755)
    write(os.path.join(task_dir, "solution", "defect_fix.json"),
          json.dumps({**cand["fix"], "_canary": canary}, indent=1, sort_keys=True))

    # -- instruction ---------------------------------------------------------
    symptom = row["symptom"]
    if restore:
        instr = fill(INSTRUCTION_RESTORE, **common,
                     SCOPE=scope_of(tree), SUB=cand["meta"].get("subroutine", "?"),
                     SYMPTOM=symptom, CHECKS_LIST=", ".join(checks),
                     BUILD_LINES=build_lines(tree, "/app/LAPS"))
    else:
        instr = fill(INSTRUCTION_REPAIR, **common,
                     SCOPE=scope_of(tree), SCOPE_PATHS=scope_paths(tree),
                     SYMPTOM=symptom, CHECKS_LIST=", ".join(checks),
                     BUILD_LINES=build_lines(tree, "/app/LAPS"))
    write(os.path.join(task_dir, "instruction.md"), instr)

    # -- task.toml -----------------------------------------------------------
    what = ("the executable body of one subroutine removed"
            if restore else "a single localized defect injected")
    desc = (f"Auto-generated {'restore' if restore else 'repair'} task on LAPS "
            f"({scope_paths(tree)}): {what}; the graded decks "
            f"({', '.join(checks)}) must match the unmodified incumbent's "
            f"trajectories to 1e-10. Reference and straw floor produced in "
            f"situ by the verifier; train on reward_repair.")
    write(os.path.join(task_dir, "task.toml"),
          fill(TASK_TOML, **common, DESCRIPTION=desc,
               CATEGORY=row["category"], MODE=row["mode"],
               FAMILY=cand["family"], CHECKS_TOML=json.dumps(checks),
               MEM=mem, AGENT_TIMEOUT=config.AGENT_TIMEOUT_SEC))

    # -- authoring (no image ever reads this) --------------------------------
    write(os.path.join(task_dir, "authoring", "provenance.json"),
          json.dumps({"candidate": cand, "funnel": fun,
                      "thresholds": {"FLOOR_MAX": config.FLOOR_MAX,
                                     "MARGIN_MIN": config.MARGIN_MIN},
                      "generator": "sciaccel-rl authoring/repair",
                      "canary": canary}, indent=1, sort_keys=True))
    return name


def compile_rows(rows, out_root, only=None, apt_mirror=""):
    names = []
    for row in rows:
        if only and not fnmatch.fnmatch(row["task"], only):
            continue
        names.append(compile_one(row, out_root, apt_mirror=apt_mirror))
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default=config.TASK_ROWS)
    ap.add_argument("--out", default=config.TASKS_ROOT)
    ap.add_argument("--only", help="task-name glob to recompile a subset")
    ap.add_argument(
        "--apt-mirror", default="",
        help="bake this Debian mirror into every generated apt stage as the "
             "APT_MIRROR default (e.g. http://mirrors.tencentyun.com). Needed "
             "on clusters whose only egress is a slow HTTP proxy: harbor "
             "clears extra_docker_compose for the separate verifier "
             "environment, so a compose-level build arg cannot reach the "
             "verifier image and the default has to live in the Dockerfile.")
    args = ap.parse_args()
    rows = lib.read_jsonl(args.rows)
    names = compile_rows(rows, args.out, args.only, apt_mirror=args.apt_mirror)
    print(f"compiled {len(names)} harbor task dirs into {args.out}")


if __name__ == "__main__":
    main()
