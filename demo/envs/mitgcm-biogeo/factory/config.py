"""Pinned source, final-state rows, and funnel policy for MITgcm biogeochemistry."""

import glob
import json
import os


REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
ENV_NAME = "mitgcm-biogeo"
ENV_ROOT = os.path.join(REPO, "envs", ENV_NAME)
ENV_ASSETS = os.path.join(ENV_ROOT, "env")
SOURCE_DIR = os.path.join(ENV_ASSETS, "source")
CASES = os.path.join(ENV_ASSETS, "cases")
CHECKS_DIR = os.path.join(ENV_ASSETS, "validation")
SCORING = os.path.join(ENV_ASSETS, "scoring")
GRADE_PY = os.path.join(SCORING, "grade.py")
TEST_SH = os.path.join(SCORING, "test.sh")
HARBOR_DIR = os.path.join(ENV_ASSETS, "harbor")
TASKS_ROOT = os.path.join(ENV_ROOT, "tasks")
BUILD_ROOT = os.path.join(REPO, "build", ENV_NAME)

WORK = os.path.join(REPO, ".work", ENV_NAME)
BASE = os.path.join(WORK, "base")
REF = os.path.join(WORK, "ref")
JOBS = os.path.join(WORK, "jobs")
BUILDS = os.path.join(WORK, "builds")
FILE_ROWS = os.path.join(ENV_ROOT, "factory", "FILE_ROWS.json")

MITGCM_REPO = "https://github.com/MITgcm/MITgcm"
MITGCM_COMMIT = "853761d8f46926cd8042d6e0ad252050561fd6fa"
MITGCM_RELEASE = "checkpoint69q"
MITGCM_LICENSE = "MIT"
MITGCM_ARCHIVE = os.path.join(
    SOURCE_DIR, f"mitgcm-{MITGCM_COMMIT}.tar.gz")
MITGCM_ARCHIVE_BYTES = 25887403
MITGCM_SHA256 = "7fc8abfc7bd58bc4c5a40c20213f8e3f2fb377c889a7ed0e3ddbfe1fe4358586"

ROW_ORDER = [
    "global-dic",
    "so-box-dic",
    "so-box-obcs-saphe",
    "so-box-calcite-keir",
    "so-box-calcite-naviaux",
    "global-bling",
    "cfc-online",
    "cfc-offline",
    "ptracer-advection-gyre",
]

BUILD_PROFILE = {check: check for check in ROW_ORDER}
for _check in ("so-box-dic", "so-box-obcs-saphe",
               "so-box-calcite-keir", "so-box-calcite-naviaux"):
    BUILD_PROFILE[_check] = "so-box"


def profile_check(profile):
    return next(check for check in ROW_ORDER if BUILD_PROFILE[check] == profile)


def rows():
    out = []
    for check in ROW_ORDER:
        path = os.path.join(CASES, check, "row.json")
        with open(path, encoding="utf-8") as handle:
            row = json.load(handle)
        if row["check"] != check:
            raise RuntimeError(f"row identity mismatch for {check}")
        if row.get("ranks") != 1:
            raise RuntimeError(f"row is not single-process: {check}")
        if float(row["timeout_sec"]) > 120.0:
            raise RuntimeError(f"row timeout exceeds 120 seconds: {check}")
        out.append(row)
    return out


def row(check):
    return next(item for item in rows() if item["check"] == check)


# The live authoring surface. FILE_ROWS.json, measured from generated build
# symlinks, decides which of the nine per-deck executables each file affects.
PHYSICS_FILES = [
    "pkg/dic/carbon_chem.F",
    "pkg/dic/dic_solvesaphe.F",
    "pkg/dic/calcite_saturation.F",
    "pkg/dic/car_flux_omega_top.F",
    "pkg/dic/dic_readparms.F",
    "pkg/dic/dic_biotic_forcing.F",
    "pkg/dic/bio_export.F",
    "pkg/dic/phos_flux.F",
    "pkg/dic/car_flux.F",
    "pkg/bling/bling_readparms.F",
    "pkg/bling/bling_bio.F",
    "pkg/bling/bling_bio_nitrogen.F",
    "pkg/bling/bling_carbon_chem.F",
    "pkg/bling/bling_carbonate_sys.F",
    "pkg/bling/bling_solvesaphe.F",
    "pkg/cfc/cfc_atmos.F",
    "pkg/cfc/cfc_param.F",
    "pkg/cfc/cfc11_surfforcing.F",
    "pkg/cfc/cfc12_surfforcing.F",
    "pkg/gchem/gchem_calc_tendency.F",
    "pkg/gchem/gchem_add_tendency.F",
    "pkg/ptracers/ptracers_integrate.F",
    "pkg/offline/offline_fields_load.F",
    "pkg/obcs/obcs_apply_ptracer.F",
    "pkg/generic_advdiff/gad_som_advect.F",
    "model/src/forward_step.F",
]

BUILD_JOBS = 4
SLOTS = 4
MAX_CHECKS = 9
TIMEOUT_FACTOR = 5.0
TIMEOUT_MIN = 15.0
ROW_TIMEOUT_MAX = 120.0
FLOOR_MAX = 0.65
MARGIN_MIN = 1.0e-13
DEDUP_PER_GROUP = 2
SEED = 20260904
TASK_PREFIX = "mitgcm-biogeo"
CANARY_PREFIX = "sciaccel-canary GUID"
AGENT_TIMEOUT_SEC = 3600.0

MASS_CAPS = {
    "sign": 4,
    "coef": 4,
    "dropterm": 3,
    "bounds": 3,
    "excise": 2,
}


def task_dirs():
    return sorted(glob.glob(os.path.join(TASKS_ROOT, "*", "*", "*")))
