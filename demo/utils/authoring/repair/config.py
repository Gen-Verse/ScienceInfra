"""Knobs and paths for the repair/restore task factory. One place, no copies.

Thresholds here are MECHANISM defaults, not measured truths: FLOOR_MAX and
MARGIN_MIN were set a priori and should be revisited once a real fleet has
rolled tasks (the design_pipe lesson: mechanisms can be fixed early,
thresholds must wait for samples).
"""

import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))  # utils/authoring/repair/ -> repo
WORK = os.path.join(REPO, ".work")
BASE = os.path.join(WORK, "base")          # pin + the two task patches, pristine
REF = os.path.join(WORK, "ref")            # native reference outputs per check
JOBS = "/dev/shm/laps-funnel"              # per-candidate scratch (fast tmpfs)

LAPS_REPO = "https://github.com/chenshihelio/LAPS"
LAPS_SHA = "a625806931a82ba3342f35906955e6806081d219"

# The canonical env level, named for the scientists who browse it:
#   cases/            simulation configurations ("run a case", CFD-style)
#   validation/       per-case acceptance: comparator + evidence-backed bands
#   scoring/          validation verdict -> reward pricing
#   upstream-patches/ the two small patches applied to the pinned upstream
# Compiled task dirs keep the source benchmark's wire format (decks/, checks/,
# patches/, /app/decks in-container, ...) — that layer is generated output and
# an interface, not something people read. The hand-built donor task keeps its
# own vendored copies (a harbor task dir is self-contained); gate_pack checks
# donor == envs/laps for drift.
ENV_LAPS = os.path.join(REPO, "envs", "laps")
ENV_ASSETS = os.path.join(ENV_LAPS, "env")
DECKS = os.path.join(ENV_ASSETS, "cases")
CHECKS_DIR = os.path.join(ENV_ASSETS, "validation")
PATCHES = os.path.join(ENV_ASSETS, "upstream-patches")
GRADE_PY = os.path.join(ENV_ASSETS, "scoring", "grade.py")
TEST_SH = os.path.join(ENV_ASSETS, "scoring", "test.sh")
MAKE_TIMING = os.path.join(ENV_ASSETS, "scoring", "make_timing.py")
TASK_ROWS = os.path.join(ENV_LAPS, "tasks.jsonl")     # the canonical task rows
TASKS_ROOT = os.path.join(ENV_LAPS, "tasks")          # compiled, per category

DONOR = os.path.join(TASKS_ROOT, "acceleration", "laps-accel-cpu")

FLAGS = ("-O3 -fdefault-real-8 -ffp-contract=off "
         "-fallow-argument-mismatch -std=legacy -I/usr/include -L/usr/lib -lfftw3")
RANKS = 4

TREES = {
    "2d": {"subdir": "src_compressible/2D", "exe": "src_compressible/2D/mhd.exe",
           "checks": ["aw-2d-256", "aw-2d-512"]},
    "3d": {"subdir": "src_compressible", "exe": "src_compressible/mhd.exe",
           "checks": ["aw-128"]},
}
# Screening order: cheapest deck of the tree first.
SCREEN_CHECK = {"2d": "aw-2d-256", "3d": "aw-128"}

SEED = 20260828          # every sampled choice in the factory derives from this
SLOTS = 16               # concurrent candidates (each runs RANKS mpi ranks)
TIMEOUT_FACTOR = 25.0    # per-deck wall cap = max(TIMEOUT_MIN, factor x ref wall)
TIMEOUT_MIN = 45.0

# Funnel gates.
FLOOR_MAX = 0.65         # straw floor above this -> not packaged by default:
                         # the unfixed build already earns most of the ladder,
                         # so the raw reward has too little headroom (the
                         # normalised reward_repair still works, but tolerance-
                         # marginal frames make a high floor unstable too)
MARGIN_MIN = 1e-8        # a purely tolerance-mode symptom must diverge by at
                         # least this at its worst frame, or the mutant sits on
                         # the 1e-10 edge where compiler noise could flip it
DEDUP_PER_GROUP = 2      # packaged tasks per (tree, file, family) group
AGENT_TIMEOUT_SEC = 3600.0

CANARY_PREFIX = "sciaccel-canary GUID"
