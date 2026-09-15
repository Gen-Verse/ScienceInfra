"""MITgcm-specific surface for the repository-generic Harbor compiler."""

import json
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402


HARBOR_DIR = config.HARBOR_DIR
DIGEST = ("debian:bookworm-slim@sha256:"
          "1caf1c703c8f7e15dcf2e7769b35000c764e6f50e4d7401c355fb0248f3ddfdb")
NS = uuid.UUID("331e35fb-f785-46b4-b016-2d66751874e6")

index_keys = ("mode", "family", "tree", "affected_checks",
              "floor_native_estimate", "canary", "difficulty",
              "difficulty_basis", "difficulty_design", "predicted_tier",
              "prediction_rationale")


def slug_of(candidate_id):
    slug = re.sub(r"[^a-z0-9]+", "-", candidate_id.lower()).strip("-")
    return re.sub(r"-+", "-", slug)


def task_name(candidate):
    kind = "restore" if candidate["source"] == "excise" else "repair"
    return f"{config.TASK_PREFIX}-{kind}-{slug_of(candidate['id'])}"


def canary_of(name):
    return str(uuid.uuid5(NS, "sciaccel-rl/" + name))


def template(name):
    return open(os.path.join(HARBOR_DIR, name), encoding="utf-8").read()


SCOPES = {
    "dic-carbonate": "DIC carbonate-equilibrium and coefficient subsystem",
    "dic-solvesaphe": "DIC SolveSAPHE equilibrium-solver subsystem",
    "dic-calcite": "DIC calcite-saturation and dissolution subsystem",
    "bling-biogeochemistry": "BLING nutrient, iron, and carbonate subsystem",
    "cfc-gas-exchange": "CFC atmospheric interpolation and gas-exchange subsystem",
    "gchem-dispatch": "GCHEM tendency-dispatch and application subsystem",
    "ptracer-transport": "passive-tracer transport, mixing, and boundary subsystem",
    "coupled-biogeochemistry": "coupled tracer-transport and biogeochemistry subsystems",
}


def scope_of(tree):
    if tree not in SCOPES:
        raise ValueError(f"unknown subsystem scope: {tree}")
    return SCOPES[tree]


COMMON_STRIP_PATHS = (".github", "doc", "jobs", "verification")
SCOPE_STRIP_PATHS = {
    "dic-carbonate": ("pkg/bling", "pkg/cfc", "pkg/offline"),
    "dic-solvesaphe": ("pkg/bling", "pkg/cfc", "pkg/offline"),
    "dic-calcite": ("pkg/bling", "pkg/cfc", "pkg/offline"),
    "bling-biogeochemistry": ("pkg/dic", "pkg/cfc", "pkg/offline"),
    "cfc-gas-exchange": ("pkg/dic", "pkg/bling"),
    "gchem-dispatch": (),
    "ptracer-transport": (),
    "coupled-biogeochemistry": (),
}


def strip_paths(tree):
    return COMMON_STRIP_PATHS + SCOPE_STRIP_PATHS[tree]


def strip_cmd(tree, root="/app/MITgcm"):
    return "rm -rf " + " ".join(os.path.join(root, item)
                                 for item in strip_paths(tree))


def surviving_sources(base, tree):
    """Agent-visible source-like files after the one declared strip model."""
    suffixes = (".F", ".F90", ".f", ".f90", ".h", ".H", ".c", ".inc")
    stripped_paths = strip_paths(tree)
    out = []
    for directory, dirs, names in os.walk(base):
        rel_dir = os.path.relpath(directory, base)
        dirs[:] = [name for name in dirs
                   if (name if rel_dir == "." else rel_dir + "/" + name)
                   not in stripped_paths]
        for name in names:
            path = os.path.join(directory, name)
            rel = os.path.relpath(path, base)
            if any(rel == item or rel.startswith(item + "/")
                   for item in stripped_paths):
                continue
            if name.endswith(suffixes) and not os.path.islink(path):
                out.append(path)
    return sorted(out)


def _taxonomy(manifest):
    return manifest["metadata"]["taxonomy"]


def validate(manifest, name):
    assert manifest["task"]["name"] == "sciaccel/" + name
    taxonomy = _taxonomy(manifest)
    canary = taxonomy["canary"].removeprefix(config.CANARY_PREFIX + " ")
    assert canary == canary_of(name), f"canary mismatch for {name}"
    known = set(config.ROW_ORDER)
    checks = list(taxonomy["affected_checks"])
    assert checks and set(checks) <= known, f"unknown checks: {checks}"
    assert taxonomy["tree"] in SCOPES
    assert taxonomy["difficulty"] in ("unrated", "easy", "medium", "hard")
    assert taxonomy["predicted_tier"] in ("easy", "medium", "hard")
    assert str(taxonomy["prediction_rationale"]).strip()
    assert 0 < float(taxonomy["straw_timeout_sec"]) <= config.ROW_TIMEOUT_MAX


def _profiles(checks):
    used = {config.BUILD_PROFILE[check] for check in checks}
    canonical = []
    for check in config.ROW_ORDER:
        profile = config.BUILD_PROFILE[check]
        if profile in used and profile not in canonical:
            canonical.append(profile)
    return canonical


def build_lines(profiles, root="/app/MITgcm", cases="/app/cases",
                builds="/app/builds"):
    return "\n".join(
        f"python3 /app/rowtool.py build {root} {cases} {profile} "
        f"{builds}/{profile} --jobs 4 --strict"
        for profile in profiles)


def tokens(manifest, name, apt_mirror_snippet):
    taxonomy = _taxonomy(manifest)
    checks = list(taxonomy["affected_checks"])
    profiles = _profiles(checks)
    timeout = min(int(taxonomy["straw_timeout_sec"]),
                  int(config.ROW_TIMEOUT_MAX))
    return {
        "NAME": name,
        "DIGEST": DIGEST,
        "APT_MIRROR": apt_mirror_snippet,
        "MITGCM_ARCHIVE": os.path.basename(config.MITGCM_ARCHIVE),
        "MITGCM_SHA256": config.MITGCM_SHA256,
        "MITGCM_COMMIT": config.MITGCM_COMMIT,
        "STRIP": strip_cmd(taxonomy["tree"]),
        "CHECKS_SH": " ".join(checks),
        "BUILD_PROFILES_SH": " ".join(profiles),
        "BUILD_LINES": build_lines(profiles),
        "ROW_TIMEOUT": int(config.ROW_TIMEOUT_MAX),
        "STRAW_TIMEOUT": timeout,
    }


def grade_py(manifest):
    taxonomy = _taxonomy(manifest)
    checks = list(taxonomy["affected_checks"])
    canary = taxonomy["canary"].removeprefix(config.CANARY_PREFIX + " ")
    text = open(config.GRADE_PY, encoding="utf-8").read()
    pattern = re.compile(
        r"# BEGIN SPECIALISED CHECKS\n.*?# END SPECIALISED CHECKS", re.S)
    replacement = ("# BEGIN SPECIALISED CHECKS\nCHECKS = " +
                   json.dumps(checks) + "\n# END SPECIALISED CHECKS")
    text, count = pattern.subn(replacement, text, count=1)
    assert count == 1, "grade.py check marker drifted"
    return f"# {config.CANARY_PREFIX} {canary}\n" + text


def vendored(manifest):
    checks = list(_taxonomy(manifest)["affected_checks"])
    out = []
    for side in ("environment", "tests"):
        out.append((config.SOURCE_DIR, os.path.join(side, "source")))
        for check in checks:
            out.append((os.path.join(config.CASES, check),
                        os.path.join(side, "cases", check)))
            out.append((os.path.join(config.CHECKS_DIR, check),
                        os.path.join(side, "checks", check)))
        out.append((os.path.join(HARBOR_DIR, "rowtool.py"),
                    os.path.join(side, "rowtool.py")))
        out.append((os.path.join(HARBOR_DIR, "runtime_lib.py"),
                    os.path.join(side, "runtime_lib.py")))
    out.append((config.TEST_SH, os.path.join("tests", "test.sh")))
    return out
