# Demo task bank

Two scientific environments, ready to run. Point `--repo demo` at this directory
and every command in the repository works without a separate checkout.

| Environment | Science | Language | Tasks | Runs from a clean checkout |
|---|---|---|---|---|
| `laps` | Pseudo-spectral Hall-MHD | Fortran 90 + MPI | 192 | Yes |
| `mitgcm-biogeo` | Ocean biogeochemistry | Fortran 77/90 | 93 | Needs binary inputs restored |

These are the two environments the reported results were measured on. **For the
full collection of scientific environments and tasks, see
[ScienceIDE](https://github.com/aitofound/ScienceIDE).**

## Run the LAPS demo

LAPS clones its upstream at image-build time and vendors no binaries, so it
works immediately after cloning this repository.

```bash
# 1. Compile the authored tasks into Harbor tasks.
cd demo && python utils/harbor/to_harbor.py --env envs/laps && cd ..

# 2. Build a dataset from the compiled tree.
python -m scienceinfra.datasets.build_dataset --repo demo \
    --out-dir data/laps/repair_easy --env laps \
    --categories repair --difficulty easy --hint-level all

# 3. Anchor the harness. Neither step needs a GPU.
bash scripts/eval/eval_standalone.sh --agent oracle \
    --dataset data/laps/repair_easy/all/L1.parquet --task-glob '<one-task>' -n 1
```

`build/` is a local product, not source: a compiled task embeds absolute paths
from the machine that compiled it, so compile wherever the episodes will run.

## Restoring the MITgcm binary inputs

`mitgcm-biogeo` needs three kinds of large binary file that are not committed:
the vendored MITgcm source archive, the restart `pickup*` files, and the gridded
forcing fields (`*.bin`, `*.data`). Each environment records what it needs in
`envs/mitgcm-biogeo/env/source/source.json`, which pins the origin URL, the
upstream commit, the release tag, and a sha256 for the archive.

Restore them from the upstream project named in that file, or obtain the
prepared inputs from [ScienceIDE](https://github.com/aitofound/ScienceIDE). The
LAPS path above is the one to use for a first run.

## What an environment contains

```
envs/<env>/
  env/
    cases/            graded configurations, one directory per deck
    validation/       per-case validators and rubrics, with the tolerances
    scoring/          the reward ladder
    harbor/           image templates for the agent and the verifier
    source/           pinned upstream archive, where an env vendors one
  factory/            generators and the screening harness for this env
  tasks/<category>/<tier>/<task>/
    task.toml         taxonomy, resources, timeouts, network policy
    instruction.md    the prompt the agent receives
    defect.json       the break
    fix.json          its exact inverse, which the oracle applies
    authoring/        the candidate record and the screening verdict
```

A task directory is sparse source. `utils/harbor/to_harbor.py` compiles it into
a self-contained Harbor task with an agent image, a verifier image that builds
the clean reference and the broken baseline in situ, and a `solution/` the
oracle runs.

## Where difficulty comes from

Tasks are filed by measured tier, and the tier directory *is* the tier. A tier
is assigned from a reference solver's pass rate over at least three attempts,
not declared by the author. `repair/easy/` is the curriculum floor for a frontier
solver, which is not the same as the floor for a policy being trained.

## Provenance

Both environments are built on public scientific codebases, pinned by commit.
`envs/<env>/env/source/source.json` and the harbor Dockerfiles record the origin,
the commit, and the license for each. Per-task screening verdicts live in
`tasks/<...>/authoring/provenance.json`.

Per-task measurement history is not included here. It is large and belongs to
the bank that produced it.
