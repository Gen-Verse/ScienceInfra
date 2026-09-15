"""Shared machinery for the repair/restore task factory.

THE CANDIDATE SCHEMA (one JSON object per line in a candidates .jsonl):

    {
      "id":     "sign-2d-mhdrhs-L67-a",      # unique, filesystem-safe
      "source": "inject" | "excise" | "history",
      "family": "sign|coef|swapidx|kswap|dropterm|bounds|rk|norm|prim|cfl|excise|history",
      "tree":   "2d" | "3d",                  # which compressible tree it edits
      "note":   "one line: what was changed, for authoring eyes only",
      "break":  TRANSFORM,                    # pristine tree  -> defective tree
      "fix":    TRANSFORM,                    # defective tree -> pristine tree
      "meta":   { ... family-specific ... }
    }

    TRANSFORM = {"edits": [{"file": "src_compressible/...", "old": "...", "new": "..."}]}
              | {"diff": "<unified diff, applied with patch -p1>"}

Edit semantics are exact-string-replace and `old` MUST occur exactly once in
the file — apply_transform refuses otherwise, so a candidate that would be
ambiguous dies at apply time instead of producing an unintended tree. `fix`
must be the exact inverse of `break`: package.py bakes `break` into the agent
image and the straw build, and `fix` into solution/solve.sh; the funnel
verifies round-trip identity before a candidate is ever screened.

Grading reuses the donor task's machinery verbatim: each check's vendored
validate.py measures, the env-level scoring/grade.py:score() prices the
verdict. Nothing in this factory re-implements a comparison.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # never litter __pycache__ into vendored checks

import config


# ---------------------------------------------------------------- donor code

def _import_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_grade = _import_from(config.GRADE_PY, "donor_grade")
score = _grade.score                      # (verdict, expected_frames) -> 0..1
eligible_frames = _grade.eligible_frames  # (ref_dir) -> int

_validators = {}

def validator(check):
    if check not in _validators:
        _validators[check] = _import_from(
            os.path.join(config.CHECKS_DIR, check, "validate.py"),
            "validate_" + check.replace("-", "_"))
    return _validators[check]


# ---------------------------------------------------------------- transforms

class ApplyError(Exception):
    pass


def apply_transform(transform, workdir):
    """Apply a TRANSFORM to a tree copy. Raises ApplyError on any mismatch."""
    if "edits" in transform:
        for e in transform["edits"]:
            p = os.path.join(workdir, e["file"])
            try:
                with open(p, encoding="utf-8", errors="strict") as f:
                    text = f.read()
            except OSError as ex:
                raise ApplyError(f"cannot read {e['file']}: {ex}")
            n = text.count(e["old"])
            if n != 1:
                raise ApplyError(
                    f"{e['file']}: `old` occurs {n} times, need exactly 1")
            with open(p, "w", encoding="utf-8") as f:
                f.write(text.replace(e["old"], e["new"], 1))
    elif "diff" in transform:
        r = subprocess.run(["patch", "-p1", "--no-backup-if-mismatch", "-f"],
                           input=transform["diff"], text=True, cwd=workdir,
                           capture_output=True)
        if r.returncode != 0:
            raise ApplyError("patch failed:\n" + r.stdout + r.stderr)
    else:
        raise ApplyError("transform carries neither edits nor diff")


def roundtrip_ok(cand, base=None):
    """break then fix on a scratch copy must reproduce the pristine tree."""
    base = base or config.BASE
    scratch = os.path.join(config.JOBS, "_roundtrip", cand["id"])
    copy_tree(base, scratch)
    try:
        apply_transform(cand["break"], scratch)
        apply_transform(cand["fix"], scratch)
        r = subprocess.run(["diff", "-r", "-q", base, scratch],
                           capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr)[:2000]
    except ApplyError as ex:
        return False, str(ex)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------- build & run

def copy_tree(src, dst):
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.dirname(dst) or "/", exist_ok=True)
    shutil.copytree(src, dst)


def build_tree(workdir, tree, log_path=None):
    """make the tree's solver with the pinned flags. -> (ok, tail_of_log)"""
    sub = os.path.join(workdir, config.TREES[tree]["subdir"])
    r = subprocess.run(
        ["make", "fftwpath=/usr", f"OPTIONS={config.FLAGS}"],
        cwd=sub, capture_output=True, text=True)
    out = (r.stdout + r.stderr)[-4000:]
    if log_path:
        with open(log_path, "w") as f:
            f.write(out)
    exe = os.path.join(workdir, config.TREES[tree]["exe"])
    return r.returncode == 0 and os.path.isfile(exe), out


def run_deck(workdir, tree, check, run_dir, timeout):
    """Run one deck. -> {"exit": int|"timeout", "wall": s} ; outputs in run_dir."""
    os.makedirs(run_dir, exist_ok=True)
    shutil.copy(os.path.join(config.DECKS, check, "mhd.input"),
                os.path.join(run_dir, "mhd.input"))
    exe = os.path.join(workdir, config.TREES[tree]["exe"])
    import time
    t0 = time.monotonic()
    try:
        r = subprocess.run(
            ["mpirun", "--bind-to", "none", "--oversubscribe",
             "-np", str(config.RANKS), exe],
            cwd=run_dir, capture_output=True, text=True, timeout=timeout)
        code = r.returncode
        tail = (r.stdout + r.stderr)[-1500:]
    except subprocess.TimeoutExpired:
        code, tail = "timeout", ""
    return {"exit": code, "wall": round(time.monotonic() - t0, 3), "tail": tail}


def validate_run(check, run_dir):
    """The donor validator's verdict for run_dir against the native reference."""
    ref = os.path.join(config.REF, check)
    return validator(check).validate([ref], [run_dir])


def floor_of(verdicts):
    """Mean ladder score over the affected checks — the straw floor."""
    vals = []
    for check, v in verdicts.items():
        expected = eligible_frames(os.path.join(config.REF, check))
        vals.append(score(v, expected))
    return round(sum(vals) / len(vals), 6), {
        c: round(score(v, eligible_frames(os.path.join(config.REF, c))), 6)
        for c, v in verdicts.items()}


def summarize_verdict(v):
    """The funnel's record of a verdict — enough to write a symptom from."""
    keep = ["outcome", "passed", "frames_ok", "frames_scored", "value",
            "worst_frame", "worst_variable", "dt_abs", "time_abs",
            "nstep_match", "error"]
    return {k: v.get(k) for k in keep if k in v}


# ---------------------------------------------------------------- io helpers

def read_jsonl(path):
    out = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def die(msg):
    sys.stderr.write("FATAL: " + msg + "\n")
    sys.exit(1)
