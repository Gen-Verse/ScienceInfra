"""Compile sparse source tasks into self-contained harbor task dirs.

    python3 utils/harbor/to_harbor.py [--env envs/laps] [--out build/laps]
                                      [--only GLOB] [--apt-mirror URL]

Repo-agnostic. THE RULE: a source task is a SPARSE harbor task — it holds
only what is its own — and the compiler densifies it with env-level
defaults. What "densify" means for a given repo is the env's
factory/harbor_spec.py (templates, tokens, grader specialisation, vendored
assets); this file is the loop and the task contract:

    envs/<repo>/env/harbor/        templates + shared scripts
    envs/<repo>/factory/harbor_spec.py   the repo's compiler surface
    envs/<repo>/tasks/<cat>/<name>/      SOURCE tasks (committed)
        sparse:  task.toml, instruction.md, defect.json, fix.json,
                 authoring/provenance.json (+ eval/, never compiled)
        dense:   a complete harbor dir (environment/Dockerfile present) —
                 copied through verbatim
    build/<repo>/<cat>/<name>/     COMPILED harbor dirs (gitignored)
    build/<repo>/index.jsonl       per-task index for samplers

The repair/restore task contract the compiler implements for a sparse task:
task.toml / instruction.md / provenance verbatim; environment/Dockerfile and
tests/Dockerfile from the env templates; defect.json fanned into
environment/defect and tests/defect with apply_defect.py; fix.json into
solution/defect_fix.json with solve.sh + apply_defect.py; grade.py from the
spec; grade_floor.py and the spec's vendored assets copied in. Deterministic
and byte-stable: same source + same env -> same bytes.

`--base-image` is a reserved seam (prebuilt env images); it refuses until
the images exist — see envs/<repo>/env/harbor/README.md.
"""

import argparse
import fnmatch
import importlib.util
import json
import os
import shutil
import sys
import tomllib

sys.dont_write_bytecode = True

SPARSE_FILES = ("task.toml", "instruction.md", "defect.json", "fix.json",
                os.path.join("authoring", "provenance.json"))

# Opt-in apt mirror, consumed by every apt stage of the templates. The
# default is baked at compile time by `--apt-mirror` (empty unless asked for)
# and can still be overridden per build with `--build-arg APT_MIRROR=...`. It
# has to live in the Dockerfile: harbor clears `extra_docker_compose` when it
# builds the separate verifier environment, so a compose-level build arg
# reaches the agent image only.
APT_MIRROR_ARG = '''ARG APT_MIRROR=@MIRROR_DEFAULT@
RUN if [ -n "$APT_MIRROR" ]; then \\
      sed -i "s|http://deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; \\
    fi
'''


def load_spec(env_dir):
    path = os.path.join(env_dir, "factory", "harbor_spec.py")
    # Compiling several envs in one process: every factory does
    # `import config` after a sys.path.insert, so a cached sibling env's
    # `config` would silently leak in. Purge it and name the spec module
    # per env.
    sys.modules.pop("config", None)
    name = "harbor_spec_" + os.path.basename(os.path.abspath(env_dir))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules.pop("config", None)
    return mod


def write(path, content, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    if mode:
        os.chmod(path, mode)


def read(path):
    with open(path) as f:
        return f.read()


def fill(tmpl, **kw):
    out = tmpl
    for k, v in kw.items():
        out = out.replace("@" + k + "@", str(v))
    assert "@" + "NAME@" not in out
    return out


def is_dense(source_dir):
    return os.path.isfile(os.path.join(source_dir, "environment", "Dockerfile"))


def load_manifest(source_dir):
    with open(os.path.join(source_dir, "task.toml"), "rb") as f:
        return tomllib.load(f)


def compile_sparse(spec, source_dir, task_dir, apt_mirror=""):
    name = os.path.basename(source_dir)
    manifest = load_manifest(source_dir)
    spec.validate(manifest, name)
    src = lambda *a: os.path.join(source_dir, *a)  # noqa: E731
    dst = lambda *a: os.path.join(task_dir, *a)  # noqa: E731
    tmpl = lambda n: read(os.path.join(spec.HARBOR_DIR, n))  # noqa: E731
    tokens = spec.tokens(manifest, name,
                         APT_MIRROR_ARG.replace("@MIRROR_DEFAULT@", apt_mirror))
    defect, fix, apply_py = read(src("defect.json")), read(src("fix.json")), tmpl("apply_defect.py")

    write(dst("task.toml"), read(src("task.toml")))
    write(dst("instruction.md"), read(src("instruction.md")))
    write(dst("authoring", "provenance.json"), read(src("authoring", "provenance.json")))

    write(dst("environment", "Dockerfile"), fill(tmpl("agent.Dockerfile"), **tokens))
    write(dst("environment", "defect", "apply_defect.py"), apply_py, mode=0o755)
    write(dst("environment", "defect", "defect.json"), defect)

    write(dst("tests", "Dockerfile"), fill(tmpl("verifier.Dockerfile"), **tokens))
    write(dst("tests", "defect", "apply_defect.py"), apply_py, mode=0o755)
    write(dst("tests", "defect", "defect.json"), defect)
    write(dst("tests", "grade.py"), spec.grade_py(manifest))
    write(dst("tests", "grade_floor.py"), tmpl("grade_floor.py"), mode=0o755)

    write(dst("solution", "solve.sh"), fill(tmpl("solve.sh"), **tokens), mode=0o755)
    write(dst("solution", "apply_defect.py"), apply_py, mode=0o755)
    write(dst("solution", "defect_fix.json"), fix)

    for s, rel in spec.vendored(manifest):
        if os.path.isdir(s):
            shutil.copytree(s, dst(rel))
        else:
            shutil.copy(s, dst(rel))
    os.chmod(dst("tests", "test.sh"), 0o755)


def compile_dense(source_dir, task_dir):
    shutil.copytree(source_dir, task_dir,
                    ignore=shutil.ignore_patterns("__pycache__", "eval"))


def index_row(spec, source_dir, category, task_dir):
    tax = load_manifest(source_dir).get("metadata", {}).get("taxonomy", {})
    row = {"task": os.path.basename(source_dir), "category": category,
           "path": task_dir, "dense": is_dense(source_dir)}
    for k in spec.index_keys:
        if k in tax:
            row[k] = tax[k]
    return row


TIERS = ("easy", "medium", "hard", "unrated")


def source_tasks(tasks_root):
    """[(category, tier, task_dir)] under <cat>/<tier>/<task>. A task.toml at
    any other depth is a filing error — grade_difficulty.py is the mover."""
    out = []
    for cat in sorted(os.listdir(tasks_root)):
        cat_dir = os.path.join(tasks_root, cat)
        if not os.path.isdir(cat_dir):
            continue
        for entry in sorted(os.listdir(cat_dir)):
            d = os.path.join(cat_dir, entry)
            if not os.path.isdir(d):
                continue
            if os.path.isfile(os.path.join(d, "task.toml")):
                raise SystemExit(
                    f"{d}: task filed at category level — run "
                    f"utils/eval/grade_difficulty.py to file tasks by tier")
            if entry not in TIERS:
                continue
            for name in sorted(os.listdir(d)):
                t = os.path.join(d, name)
                if os.path.isfile(os.path.join(t, "task.toml")):
                    out.append((cat, entry, t))
    return out


def compile_all(env_dir, out_root, only=None, apt_mirror=""):
    spec = load_spec(env_dir)
    tasks_root = os.path.join(env_dir, "tasks")
    if not only and os.path.isdir(out_root):
        shutil.rmtree(out_root)  # full compiles start clean: no stale layouts
    rows = []
    for cat in sorted(os.listdir(tasks_root)):  # category dirs, empty ones too
        if os.path.isdir(os.path.join(tasks_root, cat)):
            os.makedirs(os.path.join(out_root, cat), exist_ok=True)
    for cat, tier, source_dir in source_tasks(tasks_root):
        name = os.path.basename(source_dir)
        if only and not fnmatch.fnmatch(name, only):
            continue
        tax = load_manifest(source_dir).get("metadata", {}).get("taxonomy", {})
        if tax.get("difficulty", "unrated") != tier:
            raise SystemExit(
                f"{source_dir}: tier dir `{tier}` != task.toml difficulty "
                f"`{tax.get('difficulty')}` — run utils/eval/grade_difficulty.py")
        task_dir = os.path.join(out_root, cat, tier, name)
        if os.path.isdir(task_dir):
            shutil.rmtree(task_dir)
        if is_dense(source_dir):
            compile_dense(source_dir, task_dir)
        else:
            compile_sparse(spec, source_dir, task_dir, apt_mirror=apt_mirror)
        rows.append(index_row(spec, source_dir, cat, task_dir))
    if not only:
        with open(os.path.join(out_root, "index.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")
    return rows


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=os.path.join(repo, "envs", "laps"),
                    help="env dir holding env/, factory/harbor_spec.py, tasks/")
    ap.add_argument("--out", default=None,
                    help="compiled harbor root (default build/<env name>)")
    ap.add_argument("--only", help="task-name glob to compile a subset")
    ap.add_argument("--apt-mirror", default="",
                    help="bake this Debian mirror into every generated apt "
                         "stage as the APT_MIRROR default")
    ap.add_argument("--base-image", default=None,
                    help="RESERVED: compile against a prebuilt env image "
                         "(not implemented)")
    args = ap.parse_args()
    if args.base_image:
        sys.exit("--base-image is a reserved seam: the env-level base images "
                 "are not built yet. See envs/<repo>/env/harbor/README.md.")
    env_dir = os.path.abspath(args.env)
    out = args.out or os.path.join(repo, "build", os.path.basename(env_dir))
    rows = compile_all(env_dir, out, args.only, apt_mirror=args.apt_mirror)
    print(f"compiled {len(rows)} harbor task dirs into {out}")


if __name__ == "__main__":
    main()
