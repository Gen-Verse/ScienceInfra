"""Pinned source, exact-edit, per-deck build, and final-state row helpers."""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

sys.dont_write_bytecode = True

import config


class ApplyError(RuntimeError):
    pass


def die(message):
    print("FATAL: " + message, file=sys.stderr)
    raise SystemExit(1)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def seed_base():
    """Extract the deterministic, checksum-pinned source archive once."""
    marker = os.path.join(config.BASE, ".sciaccel-source.json")
    if os.path.isfile(marker):
        fact = json.load(open(marker, encoding="utf-8"))
        if (fact.get("archive_sha256") == config.MITGCM_SHA256 and
                fact.get("commit") == config.MITGCM_COMMIT):
            return config.BASE
        raise ApplyError(f"stale base marker at {marker}")
    if os.path.exists(config.BASE):
        raise ApplyError(f"base exists without a valid marker: {config.BASE}")
    got = sha256(config.MITGCM_ARCHIVE)
    if got != config.MITGCM_SHA256:
        raise ApplyError(f"source archive sha256 {got}, expected {config.MITGCM_SHA256}")
    os.makedirs(config.WORK, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="extract-", dir=config.WORK)
    try:
        with tarfile.open(config.MITGCM_ARCHIVE, "r:gz") as archive:
            members = archive.getmembers()
            if any(m.name.startswith("/") or ".." in m.name.split("/")
                   for m in members):
                raise ApplyError("unsafe member path in source archive")
            archive.extractall(scratch, filter="data")
        roots = [os.path.join(scratch, name) for name in os.listdir(scratch)
                 if os.path.isdir(os.path.join(scratch, name))]
        if len(roots) != 1:
            raise ApplyError(f"archive has {len(roots)} top-level directories")
        shutil.move(roots[0], config.BASE)
        if os.path.exists(os.path.join(config.BASE, ".git")):
            raise ApplyError("vendored source unexpectedly contains .git")
        for relpath in config.PHYSICS_FILES:
            if not os.path.isfile(os.path.join(config.BASE, relpath)):
                raise ApplyError(f"source archive lacks physics file {relpath}")
        with open(marker, "w", encoding="utf-8") as handle:
            json.dump({"archive_sha256": got, "commit": config.MITGCM_COMMIT},
                      handle, indent=1, sort_keys=True)
            handle.write("\n")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return config.BASE


def copy_tree(source, destination):
    """Cheap hard-link clone; edited files are detached before replacement."""
    shutil.rmtree(destination, ignore_errors=True)
    os.makedirs(destination)
    result = subprocess.run(["cp", "-al", source + "/.", destination],
                            capture_output=True, text=True)
    if result.returncode:
        shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(source, destination, symlinks=True)


def _detach(path):
    if os.stat(path).st_nlink <= 1:
        return
    tmp = path + ".sciaccel-detach"
    shutil.copy2(path, tmp)
    os.replace(tmp, path)


def apply_transform(transform, workdir):
    if "edits" not in transform:
        raise ApplyError("transform carries no exact edits")
    for edit in transform["edits"]:
        path = os.path.join(workdir, edit["file"])
        try:
            text = open(path, encoding="utf-8", errors="strict").read()
        except OSError as exc:
            raise ApplyError(f"cannot read {edit['file']}: {exc}") from exc
        count = text.count(edit["old"])
        if count != 1:
            raise ApplyError(
                f"{edit['file']}: old text occurs {count} times, need exactly 1")
        _detach(path)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(edit["old"], edit["new"], 1))


def roundtrip_ok(candidate, base=None):
    base = base or config.BASE
    scratch = os.path.join(config.JOBS, "_roundtrip", candidate["id"])
    os.makedirs(os.path.dirname(scratch), exist_ok=True)
    copy_tree(base, scratch)
    try:
        apply_transform(candidate["break"], scratch)
        apply_transform(candidate["fix"], scratch)
        # The upstream flat tree intentionally contains a few dangling
        # Tapenade symlinks, which recursive diff tries to dereference.  Exact
        # transforms can only touch their declared regular files, so compare
        # those bytes directly after break + fix.
        touched = sorted({edit["file"]
                          for side in ("break", "fix")
                          for edit in candidate[side]["edits"]})
        changed = []
        for relpath in touched:
            left = open(os.path.join(base, relpath), "rb").read()
            right = open(os.path.join(scratch, relpath), "rb").read()
            if left != right:
                changed.append(relpath)
        return not changed, ("roundtrip changed: " + ", ".join(changed))[:2000]
    except ApplyError as exc:
        return False, str(exc)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def build_profile(source, check, build_dir, timeout=900.0):
    """Generate and build one single-process MITgcm deck."""
    case_dir = os.path.join(config.CASES, check)
    shutil.rmtree(build_dir, ignore_errors=True)
    os.makedirs(build_dir)
    local = os.path.join(case_dir, "mods", "genmake_local")
    if os.path.isfile(local):
        shutil.copy2(local, os.path.join(build_dir, "genmake_local"))
    command = [
        os.path.join(source, "tools", "genmake2"),
        "-rootdir", source,
        "-mods", os.path.join(case_dir, "mods"),
        "-optfile", os.path.join(source, "tools", "build_options",
                                  "linux_amd64_gfortran"),
        "-extra_flag=-ffp-contract=off",
    ]
    started = time.monotonic()
    output = []
    try:
        for cmd in (command, ["make", "depend"],
                    ["make", "-j", str(config.BUILD_JOBS)]):
            result = subprocess.run(cmd, cwd=build_dir, text=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    timeout=max(1.0, timeout - (time.monotonic() - started)))
            output.append(result.stdout)
            if result.returncode:
                return {"exit": result.returncode,
                        "wall": round(time.monotonic() - started, 4),
                        "tail": "".join(output)[-6000:]}
    except subprocess.TimeoutExpired as exc:
        return {"exit": "timeout", "wall": round(time.monotonic() - started, 4),
                "tail": (exc.stdout or "")[-6000:]}
    binary = os.path.join(build_dir, "mitgcmuv")
    return {"exit": 0 if os.path.isfile(binary) else "missing_binary",
            "wall": round(time.monotonic() - started, 4),
            "tail": "".join(output)[-6000:], "binary": binary}


def build_incremental(source, profile, build_dir, timeout=180.0):
    """Clone a calibrated genmake2 build and rebuild against an edited tree."""
    template = os.path.join(config.BUILDS, profile)
    shutil.rmtree(build_dir, ignore_errors=True)
    os.makedirs(os.path.dirname(build_dir), exist_ok=True)
    copied = subprocess.run(["cp", "-a", "--reflink=auto", template, build_dir],
                            capture_output=True, text=True)
    if copied.returncode:
        return {"exit": copied.returncode, "wall": 0.0, "tail": copied.stderr[-4000:]}
    base_prefix = os.path.realpath(config.BASE) + os.sep
    for name in os.listdir(build_dir):
        path = os.path.join(build_dir, name)
        if not os.path.islink(path):
            continue
        target = os.path.realpath(path)
        if target.startswith(base_prefix):
            relpath = os.path.relpath(target, config.BASE)
            os.unlink(path)
            os.symlink(os.path.join(source, relpath), path)
    started = time.monotonic()
    try:
        result = subprocess.run(["make", "-j", str(config.BUILD_JOBS)],
                                cwd=build_dir, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
        tail = result.stdout[-6000:]
        code = result.returncode
    except subprocess.TimeoutExpired as exc:
        code, tail = "timeout", (exc.stdout or "")[-6000:]
    binary = os.path.join(build_dir, "mitgcmuv")
    return {"exit": 0 if code == 0 and os.path.isfile(binary) else code,
            "wall": round(time.monotonic() - started, 4),
            "tail": tail, "binary": binary}


def run_profile(binary, check, out_dir, timeout=None, strict=False):
    """Run one frozen deck and retain only its final-state DATA/META pairs."""
    import glob
    import re
    row = config.row(check)
    timeout = min(float(timeout or row["timeout_sec"]), float(row["timeout_sec"]))
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    run_dir = out_dir + ".run"
    shutil.rmtree(run_dir, ignore_errors=True)
    shutil.copytree(os.path.join(config.CASES, check, "input"), run_dir,
                    symlinks=True)
    status = {"check": check, "status": "crash", "exit": None,
              "ranks": 1, "command": [binary]}
    started = time.monotonic()
    try:
        result = subprocess.run([binary], cwd=run_dir, capture_output=True,
                                text=True, timeout=timeout)
        status["exit"] = result.returncode
        normal = "PROGRAM MAIN: Execution ended Normally" in result.stdout
        status["status"] = "ok" if result.returncode == 0 and normal else "crash"
        status["tail"] = (result.stdout + result.stderr)[-1500:]
    except subprocess.TimeoutExpired as exc:
        status.update(status="timeout", exit="timeout",
                      tail=((exc.stdout or "") + (exc.stderr or ""))[-1500:])
    status["wall"] = round(time.monotonic() - started, 4)
    if status["status"] == "ok":
        pattern = re.compile(r"^[A-Za-z_0-9]+[.](\d{10})[.]data$")
        by_iteration = {}
        for path in glob.glob(os.path.join(run_dir, "*.data")):
            match = pattern.match(os.path.basename(path))
            if match:
                by_iteration.setdefault(match.group(1), []).append(path)
        if not by_iteration:
            status["status"] = "missing_output"
        else:
            final = max(by_iteration)
            status["final_iteration"] = final
            for data_path in sorted(by_iteration[final]):
                meta_path = data_path[:-5] + ".meta"
                if not os.path.isfile(meta_path):
                    status["status"] = "missing_output"
                    break
                shutil.copy2(data_path, os.path.join(out_dir, os.path.basename(data_path)))
                shutil.copy2(meta_path, os.path.join(out_dir, os.path.basename(meta_path)))
    with open(os.path.join(out_dir, "_run_status.json"), "w",
              encoding="utf-8") as handle:
        json.dump(status, handle, indent=1, sort_keys=True)
        handle.write("\n")
    shutil.rmtree(run_dir, ignore_errors=True)
    if strict and status["status"] != "ok":
        raise RuntimeError(f"{check} failed: {status}")
    return status


def load_grade():
    spec = importlib.util.spec_from_file_location("mitgcm_biogeo_grade", config.GRADE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_grade = None


def grade_module():
    global _grade
    if _grade is None:
        _grade = load_grade()
    return _grade


def validate_run(check, run_dir):
    return grade_module().grade_check(
        check, run_dir, os.path.join(config.REF, check), config.CHECKS_DIR)[1]


def floor_of(verdicts):
    values = {check: grade_module().score(verdict)
              for check, verdict in verdicts.items()}
    return round(sum(values.values()) / len(values), 6), values


def summarize_verdict(verdict):
    keys = ("outcome", "passed", "files_ok", "files_scored", "value",
            "worst_file", "final_iteration_match", "error")
    return {key: verdict.get(key) for key in keys if key in verdict}


def stable_bytes(directory):
    payload = bytearray()
    for name in sorted(os.listdir(directory)):
        if name.endswith((".data", ".meta")):
            encoded = name.encode("utf-8")
            data = open(os.path.join(directory, name), "rb").read()
            payload.extend(len(encoded).to_bytes(4, "big"))
            payload.extend(encoded)
            payload.extend(len(data).to_bytes(8, "big"))
            payload.extend(data)
    return bytes(payload)
