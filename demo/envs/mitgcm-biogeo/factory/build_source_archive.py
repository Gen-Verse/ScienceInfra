#!/usr/bin/env python3
"""Build the minimal deterministic MITgcm source archive used by this env."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

import config


# checkpoint69q's tag date, fixed for every member.  gzip -n separately fixes
# the gzip header timestamp and suppresses the output filename.
FIXED_MTIME = 1787529600  # 2026-08-24 00:00:00 UTC

# genmake2 and the six serial build profiles consume the four source/tool
# trees.  The complete source experiments are retained so the frozen case
# inputs and mods remain auditable against their upstream decks.
RETAINED = (
    "LICENSE.txt",
    "eesupp",
    "model",
    "pkg",
    "tools",
    "verification/cfc_example",
    "verification/global_oce_biogeo_bling",
    "verification/so_box_biogeo",
    "verification/tutorial_advection_in_gyre",
    "verification/tutorial_cfc_offline",
    "verification/tutorial_global_oce_biogeo",
)

# This is deliberately an allowlist build.  At the pinned commit, its inverse
# is the following top-level material plus every verification experiment not
# named above.  .git and the factory extraction marker are also never vendored.
EXCLUDED_TOP_LEVEL = (
    ".git",
    ".github",
    ".gitignore",
    ".readthedocs.yml",
    ".sciaccel-source.json",
    "README.md",
    "doc",
    "jobs",
    "lsopt",
    "optim",
    "utils",
)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_source(source):
    missing = [rel for rel in RETAINED if not (source / rel).exists()]
    if missing:
        raise SystemExit(f"source tree lacks retained paths: {missing}")
    if not (source / "tools/genmake2").is_file():
        raise SystemExit("source tree lacks tools/genmake2")
    for rel in config.PHYSICS_FILES:
        if not (source / rel).is_file():
            raise SystemExit(f"source tree lacks authorable file: {rel}")


def retained_members(source):
    """Return every allowlisted member in global bytewise name order."""
    members = set()
    for retained in RETAINED:
        path = source / retained
        members.add(retained)
        if path.is_dir() and not path.is_symlink():
            for directory, dirs, names in os.walk(path, followlinks=False):
                rel_dir = Path(directory).relative_to(source)
                for name in dirs + names:
                    members.add(os.fspath(rel_dir / name))
    return sorted(members, key=os.fsencode)


def validate_archive(path):
    prefix = f"mitgcm-{config.MITGCM_COMMIT}/"
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name.rstrip("/") for member in members]
        if names != sorted(names):
            raise SystemExit("archive member names are not sorted")
        if not members or any(not (name + "/").startswith(prefix)
                              for name in names):
            raise SystemExit("archive has an unexpected top-level path")
        if any((member.uid, member.gid) != (0, 0) for member in members):
            raise SystemExit("archive ownership is not numeric root:root")
        if any(member.mtime != FIXED_MTIME for member in members):
            raise SystemExit("archive member mtimes are not fixed")
        member_names = set(names)
        for rel in RETAINED:
            expected = f"mitgcm-{config.MITGCM_COMMIT}/{rel}"
            if expected not in member_names:
                raise SystemExit(f"archive lacks retained path: {rel}")
    return len(members)


def build(source, output):
    validate_source(source)
    members_to_add = retained_members(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    archive_root = f"mitgcm-{config.MITGCM_COMMIT}"
    with tempfile.TemporaryDirectory(prefix="mitgcm-archive-",
                                     dir=output.parent) as scratch:
        tar_path = Path(scratch) / "source.tar"
        gz_path = Path(scratch) / "source.tar.gz"
        subprocess.run([
            "tar",
            "--sort=name",
            f"--mtime=@{FIXED_MTIME}",
            "--owner=0",
            "--group=0",
            "--numeric-owner",
            # Git records only the executable bit.  Canonical permissions
            # avoid checkout umask and Python's safe-extraction filter from
            # influencing a rebuild.
            "--mode=u+rwX,go+rX,go-w",
            # Do not let incidental inode sharing (for example from the
            # factory's cp -al work trees) alter hard-link headers.
            "--hard-dereference",
            "--format=gnu",
            "--null",
            "--verbatim-files-from",
            "--no-recursion",
            # Prefix member names (and any hard-link targets) but leave
            # relative symbolic-link targets byte-for-byte intact.
            "--transform", f"flags=rh;s,^,{archive_root}/,",
            "-C", os.fspath(source),
            "-cf", os.fspath(tar_path),
            "--files-from=-",
        ], check=True, input=(b"\0".join(
            os.fsencode(member) for member in members_to_add) + b"\0"))
        with open(gz_path, "wb") as compressed:
            subprocess.run(["gzip", "-n", "-9", "-c", os.fspath(tar_path)],
                           check=True, stdout=compressed)
        members = validate_archive(gz_path)
        os.replace(gz_path, output)
    return {
        "archive": os.fspath(output),
        "bytes": output.stat().st_size,
        "members": members,
        "sha256": sha256(output),
        "fixed_mtime": FIXED_MTIME,
        "retained": list(RETAINED),
        "excluded_top_level": list(EXCLUDED_TOP_LEVEL),
        "unused_verification_experiments_excluded": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(config.BASE))
    parser.add_argument("--output", type=Path, default=Path(config.MITGCM_ARCHIVE))
    args = parser.parse_args()
    print(json.dumps(build(args.source.resolve(), args.output.resolve()),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
