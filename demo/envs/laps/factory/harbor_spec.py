"""What the generic harbor compiler needs to know about LAPS.

utils/harbor/to_harbor.py is repo-agnostic: it reads sparse source tasks,
fills the env's templates, fans defect/fix into the build contexts, and
vendors env assets. Everything that is *this* repo — how it is built, which
cases a tree grades, what to strip from the agent image, how the scoring
base is specialised per task, how tasks are named — is here. A second repo
ships its own harbor_spec.py with the same surface:

    HARBOR_DIR                  template directory
    task_name(cand)             factory naming (also used by package.py)
    canary_of(name)
    checks_of(tree)
    validate(manifest, name)    assert the manifest is internally consistent
    tokens(manifest, name, apt_mirror) -> {TOKEN: value} for the templates
    grade_py(manifest) -> str   the task's specialised grader
    vendored(manifest) -> [(src, dst_rel)]  env assets copied into the task
    index_keys                  taxonomy keys surfaced in build/index.jsonl
"""

import json
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

HARBOR_DIR = config.HARBOR_DIR
DIGEST = "debian:bookworm-slim@sha256:1caf1c703c8f7e15dcf2e7769b35000c764e6f50e4d7401c355fb0248f3ddfdb"
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid5 namespace (DNS)

MAKE = ('make -C {root}/src_compressible{sub} fftwpath=/usr \\\n'
        '      OPTIONS="-O3 -fdefault-real-8 -ffp-contract=off \\\n'
        ' -fallow-argument-mismatch -std=legacy \\\n'
        ' -I/usr/include -L/usr/lib -lfftw3" \\\n'
        ' && test -x {root}/src_compressible{sub}/mhd.exe')

index_keys = ("mode", "family", "tree", "affected_checks",
              "floor_native_estimate", "canary",
              "difficulty", "difficulty_basis", "difficulty_design")


# ---------------------------------------------------------------- naming

def checks_of(tree):
    if tree == "both":
        return config.TREES["2d"]["checks"] + config.TREES["3d"]["checks"]
    return list(config.TREES[tree]["checks"])


def slug_of(cid):
    s = re.sub(r"[^a-z0-9]+", "-", cid.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def task_name(cand):
    restore = cand["source"] == "excise"
    kind = "laps-restore" if restore else "laps-repair"
    slug = slug_of(cand["id"].removeprefix("excise-") if restore else cand["id"])
    return f"{kind}-{slug}"


def canary_of(name):
    return str(uuid.uuid5(NS, "sciaccel-rl/" + name))


def template(name):
    with open(os.path.join(HARBOR_DIR, name)) as f:
        return f.read()


# ---------------------------------------------------------------- prose bits (package.py)

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


# ---- THE STRIP MODEL: single source for "what does the agent image keep" --
# Ungraded sibling trees are pristine near-mirrors of the mutated code (the
# incompressible rktmod is byte-identical) — leaving them in ships the answer
# key. One entry per tree, two views of the same decision: `cmd` (Dockerfile
# lines that remove the siblings) and `surviving` (glob patterns for the
# source files that stay agent-visible; the content-anchored leak scan models
# the stripped image with them). No consumer restates either view: the
# compiler renders cmd via strip_cmd(), gate_pack asserts THAT rendering
# verbatim in every env Dockerfile and scans against surviving_f90() — and
# adjacency is not trusted: verify_strip_model() PROVES the two views agree
# by experiment (apply cmd to a copy of the base tree, compare the .f90 set),
# and gate_pack runs that experiment on every invocation.
STRIP_MODEL = {
    "2d": {"cmd": ("rm -rf {root}/src_incompressible \\\n"
                   " && find {root}/src_compressible -maxdepth 1 -type f -delete"),
           "surviving": ["src_compressible/2D/*.f90"]},
    "3d": {"cmd": "rm -rf {root}/src_incompressible {root}/src_compressible/2D",
           "surviving": ["src_compressible/*.f90"]},
    "both": {"cmd": "rm -rf {root}/src_incompressible",
             "surviving": ["src_compressible/*.f90",
                           "src_compressible/2D/*.f90"]},
}


def strip_cmd(tree, root="/app/LAPS"):
    return STRIP_MODEL[tree]["cmd"].format(root=root)


def surviving_f90(tree, base):
    """Absolute paths of the .f90 files the agent image keeps, per the model."""
    import glob as _glob
    return sorted({p for pat in STRIP_MODEL[tree]["surviving"]
                   for p in _glob.glob(os.path.join(base, pat))})


def verify_strip_model(base, model=None, scratch="/dev/shm"):
    """The experiment that keeps cmd and surviving honest: apply each tree's
    cmd to a copy of the base tree; the .f90 files that remain must equal the
    model's surviving expansion EXACTLY. Returns mismatch strings (empty =
    coherent). model is injectable so the selftest can prove this detector
    fails a wrong model."""
    import glob as _glob
    import shutil as _shutil
    import subprocess as _sub
    import tempfile as _tmp
    model = model if model is not None else STRIP_MODEL
    problems = []
    with _tmp.TemporaryDirectory(dir=scratch) as td:
        for tree, m in model.items():
            root = os.path.join(td, tree)
            _shutil.copytree(base, root, ignore=_shutil.ignore_patterns(".git"))
            # `want` is the model's CLAIM about what survives — expand it on
            # the PRE-strip tree. (Expanding post-strip made any deletion
            # self-consistent; the selftest's wrong-model probe caught that.)
            want = sorted({os.path.relpath(f, root)
                           for pat in m["surviving"]
                           for f in _glob.glob(os.path.join(root, pat))})
            cmd = m["cmd"].format(root=root).replace("\\\n", " ")
            r = _sub.run(["sh", "-ce", cmd], capture_output=True, text=True)
            if r.returncode != 0:
                problems.append(f"{tree}: strip cmd failed: {r.stderr[:200]}")
                continue
            got = sorted(os.path.relpath(f, root) for f in
                         _glob.glob(os.path.join(root, "**", "*.f90"),
                                    recursive=True))
            if got != want:
                extra = sorted(set(got) - set(want))[:3]
                missing = sorted(set(want) - set(got))[:3]
                problems.append(f"{tree}: surviving set mismatch: "
                                f"extra={extra} missing={missing}")
    return problems


# ---------------------------------------------------------------- compiler surface

def _tax(manifest):
    return manifest["metadata"]["taxonomy"]


def validate(manifest, name):
    assert manifest["task"]["name"] == "sciaccel/" + name, f"manifest name mismatch: {name}"
    tax = _tax(manifest)
    canary = tax["canary"].removeprefix(config.CANARY_PREFIX + " ")
    assert canary == canary_of(name), f"canary mismatch for {name}"
    assert list(tax["affected_checks"]) == checks_of(tax["tree"]), f"checks mismatch for {name}"


def tokens(manifest, name, apt_mirror_snippet):
    tax = _tax(manifest)
    tree, checks = tax["tree"], list(tax["affected_checks"])
    return dict(
        NAME=name, DIGEST=DIGEST, REPO=config.LAPS_REPO, SHA=config.LAPS_SHA,
        CHECKS_SH=" ".join(checks), APT_MIRROR=apt_mirror_snippet,
        STRIP=strip_cmd(tree),
        REF_BUILDS=make_blocks(tree, "/opt/LAPS", " \\\n && "),
        STRAW_BUILDS=make_blocks(tree, "/opt/LAPS-straw", "; \\\n    "),
        BUILDS=make_blocks(tree, "/app/LAPS", "\n"),
    )


def grade_py(manifest):
    """The env scoring base with two assert-guarded surgical edits: the
    graded-checks subset and the floor-normalised reward_repair."""
    tax = _tax(manifest)
    checks = list(tax["affected_checks"])
    canary = tax["canary"].removeprefix(config.CANARY_PREFIX + " ")
    with open(config.GRADE_PY) as f:
        text = f.read()
    old_checks = 'CHECKS = ["aw-2d-256", "aw-2d-512", "aw-128"]'
    assert old_checks in text, "grade.py base CHECKS drifted; update harbor_spec.py"
    text = text.replace(old_checks, "CHECKS = " + json.dumps(checks), 1)
    old_out = '''    rewards_out = {
        "reward": round(sum(scores) / len(scores), 6),
        "equivalence_pass": 1 if all_passed else 0,
        "speedup": speedup(args.candidate, args.reference, all_passed),
    }
    rewards_out.update(rewards)'''
    assert old_out in text, "grade.py base rewards block drifted; update harbor_spec.py"
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


def vendored(manifest):
    """Env assets copied into the task, per build context (src, dst_rel)."""
    checks = list(_tax(manifest)["affected_checks"])
    out = []
    for side in ("environment", "tests"):
        out.append((config.PATCHES, os.path.join(side, "patches")))
        for c in checks:
            out.append((os.path.join(config.DECKS, c), os.path.join(side, "decks", c)))
            out.append((os.path.join(config.CHECKS_DIR, c), os.path.join(side, "checks", c)))
    out.append((config.MAKE_TIMING, os.path.join("tests", "make_timing.py")))
    out.append((config.TEST_SH, os.path.join("tests", "test.sh")))
    return out
