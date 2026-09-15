"""Mine LAPS history for reversible bug candidates.

    python3 mine_history.py [--clone DIR] [--base DIR] [--out PATH]

Every upstream commit that touched the compressible solver is a candidate
historical defect: reverting its changes on top of BASE recreates an older,
possibly-buggy state of exactly the files it touched, and the commit's own
forward diff is the fix. A downstream build+run funnel decides which
candidates actually produce an observable symptom; this script only
enumerates commits and pre-filters to those whose break/fix diffs apply
cleanly to BASE and round-trip back to a byte-identical tree.

Non-merge commits on the history of HEAD are walked oldest first. For each,
the changed-file set is restricted to paths under src_compressible/ ending
in .f90; commits with no such files are skipped. Emits JSONL, one candidate
per line (schema: lib.py's module docstring), to --out or else stdout.

stdlib + the `git` and `patch` CLIs only. No network: the clone must
already exist.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import lib


def is_compressible_f90(path):
    return path.startswith("src_compressible/") and path.endswith(".f90")


def run_git(clone, *args):
    r = subprocess.run(["git", "-C", clone, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("git " + " ".join(args) + ": " + r.stderr.strip())
    return r.stdout


def list_commits(clone):
    """Non-merge commits on the history of HEAD, oldest first."""
    out = run_git(clone, "log", "--no-merges", "--reverse", "--pretty=format:%H", "HEAD")
    return [ln for ln in out.splitlines() if ln]


def resolve_parent(clone, sha):
    """sha^, or git's empty-tree object if sha is the root commit."""
    r = subprocess.run(["git", "-C", clone, "rev-parse", "--verify", "-q", sha + "^"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.strip()
    return run_git(clone, "hash-object", "-t", "tree", os.devnull).strip()


def changed_files(clone, parent, sha):
    out = run_git(clone, "diff", "--name-only", parent, sha)
    return sorted(f for f in out.splitlines() if is_compressible_f90(f))


def diff_text(clone, a, b, files):
    return run_git(clone, "diff", a, b, "--", *files)


def diffstat(clone, a, b, files):
    """(insertions, deletions) of a->b restricted to files."""
    ins = dele = 0
    for line in run_git(clone, "diff", "--numstat", a, b, "--", *files).splitlines():
        added, deleted, _ = line.split("\t", 2)
        if added != "-" and deleted != "-":     # "-" marks a binary file
            ins += int(added)
            dele += int(deleted)
    return ins, dele


def tree_of(files):
    under_2d = [f.startswith("src_compressible/2D/") for f in files]
    if all(under_2d):
        return "2d"
    if not any(under_2d):
        return "3d"
    return "both"


def dry_run_applies(diff, base):
    """Does `diff` apply cleanly to a scratch copy of base, per `patch --dry-run`?

    On failure, the reason is which file(s)/hunk(s) rejected, e.g.
    "src_compressible/mhd.f90: 1 out of 1 hunk FAILED" -- patch only prints a
    per-file summary line (lowercase "hunk(s) FAILED") when something in that
    file didn't apply cleanly; a hunk applying at its exact expected location
    prints nothing.
    """
    scratch = tempfile.mkdtemp(prefix="mine-history-")
    tree = os.path.join(scratch, "tree")
    try:
        shutil.copytree(base, tree)
        r = subprocess.run(["patch", "-p1", "--dry-run", "-f"],
                           input=diff, text=True, cwd=tree, capture_output=True)
        if r.returncode == 0:
            return True, ""
        cur, reasons = "", []
        for ln in (r.stdout + r.stderr).splitlines():
            if ln.startswith("checking file "):
                cur = ln[len("checking file "):]
            elif "hunk" in ln and "FAILED" in ln:
                reasons.append(f"{cur}: {ln.strip()}")
        return False, "; ".join(reasons) if reasons else "patch reported failure"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def build_candidate(clone, sha, parent, files):
    subject = run_git(clone, "log", "-1", "--format=%s", sha).strip()
    date = run_git(clone, "log", "-1", "--format=%as", sha).strip()
    ins, dele = diffstat(clone, parent, sha, files)
    return {
        "id": "history-" + sha[:7],
        "source": "history",
        "family": "history",
        "tree": tree_of(files),
        "note": subject[:100],
        "break": {"diff": diff_text(clone, sha, parent, files)},   # C..C^: new -> old
        "fix": {"diff": diff_text(clone, parent, sha, files)},     # C^..C: old -> new
        "meta": {
            "commit": sha,
            "subject": subject,
            "date": date,
            "files": files,
            "insertions": ins,
            "deletions": dele,
        },
    }


def mine(clone, base):
    """-> (candidates, scanned, touching, dropped)"""
    candidates = []
    scanned = touching = dropped = 0
    for sha in list_commits(clone):
        scanned += 1
        try:
            parent = resolve_parent(clone, sha)
        except RuntimeError as ex:
            sys.stderr.write(f"skip {sha[:7]} (root commit): {ex}\n")
            continue

        files = changed_files(clone, parent, sha)
        if not files:
            continue
        touching += 1

        cand = build_candidate(clone, sha, parent, files)

        ok, reason = dry_run_applies(cand["break"]["diff"], base)
        if not ok:
            dropped += 1
            sys.stderr.write(f"drop {cand['id']}: break does not apply to base: {reason}\n")
            continue

        ok, reason = lib.roundtrip_ok(cand, base=base)
        if not ok:
            dropped += 1
            sys.stderr.write(f"drop {cand['id']}: roundtrip mismatch: {reason}\n")
            continue

        candidates.append(cand)

    return candidates, scanned, touching, dropped


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clone", default=os.path.join(config.WORK, "LAPS"))
    ap.add_argument("--base", default=config.BASE)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.isdir(os.path.join(args.clone, ".git")):
        lib.die(f"not a git clone: {args.clone}")
    if not os.path.isdir(args.base):
        lib.die(f"base tree not found: {args.base}")

    candidates, scanned, touching, dropped = mine(args.clone, args.base)

    if args.out:
        lib.write_jsonl(args.out, candidates)
    else:
        for c in candidates:
            sys.stdout.write(json.dumps(c, sort_keys=True) + "\n")

    sys.stderr.write(
        f"history mining: {scanned} commits scanned, {touching} touched "
        f"src_compressible/*.f90, {len(candidates)} candidates emitted, "
        f"{dropped} dropped\n")


if __name__ == "__main__":
    sys.exit(main())
