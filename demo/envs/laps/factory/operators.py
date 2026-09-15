"""LAPS injection candidates: the RULES, composed over the generic engine.

    python3 operators.py [--base DIR] [--out PATH]

What is LAPS-specific lives in this file — which files carry physics, which
left-hand sides are physics statements, which coefficients matter, which
flags are dead under the graded decks (if_AEB / if_Hall / if_resis /
if_visc are all F, dealias_option = 1). The mechanics (liveness, statement
heads, uniqueness growth, candidate records) are utils/skills/lib/mutation_engine.py.

Families: sign, coef, dropterm, swapvel, norm, bounds, rkorder.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
sys.path.insert(0, os.path.join(config.REPO, "utils", "skills", "lib"))
import mutation_engine as me  # noqa: E402

DEAD_FLAG = re.compile(r"\b(if_aeb|if_hall|if_resis|if_visc|if_corotating)\b", re.I)
DEAD_TEXT = re.compile(r"dealias_option\s*==\s*2")
DEAD_SUBS = {"calc_current_density_real"}  # reachable only under if_hall

SIGN_LHS = {
    "mhdrhs.f90": {"flux", "fnl", "ptot", "udotb", "uu_prim"},
    "rktmod.f90": {"uu_fourier"},
    "mhd.f90": {"csound2", "cms2", "cnsx2", "cnsy2", "cnsz2",
                "cmaxx", "cmaxy", "cmaxz", "dtx", "dty", "dtz"},
}

COEF = {
    "mhdrhs.f90": [
        ("0.5 * (Bx**2", "0.505 * (Bx**2", "magnetic pressure coefficient"),
        ("(adiabatic_index-1)", "(adiabatic_index-1.02)", "pressure closure gamma-1"),
    ],
    "rktmod.f90": [
        ("cc10 = 8.0/15.0", "cc10 = 8.0/15.2", "RK stage-1 coefficient"),
        ("cc20=5.0/12.0", "cc20=5.0/12.2", "RK stage-2 coefficient"),
        ("cc30=0.75", "cc30=0.752", "RK stage-3 coefficient"),
        ("dd20 = -17./60.", "dd20 = -17./61.", "RK stage-2 correction"),
        ("dd30=-5./12.", "dd30=-5./12.2", "RK stage-3 correction"),
        ("time_step1 = 8./15.", "time_step1 = 8./15.2", "RK stage-1 fraction"),
        ("time_step2 = 2./15.", "time_step2 = 2./15.2", "RK stage-2 fraction"),
        ("time_step3 = 1./3.", "time_step3 = 1./3.02", "RK stage-3 fraction"),
    ],
    "mhd.f90": [
        ("dtmin = dtmin * cfl", "dtmin = dtmin * cfl * 1.02", "CFL safety factor"),
        ("dt<0.98*dtmin", "dt<0.90*dtmin", "dt hysteresis window"),
    ],
    "dealiasing.f90": [
        ("dealias_circle_radius = 1./3.", "dealias_circle_radius = 1./3.2",
         "dealias radius shrunk"),
        ("radius > dealias_circle_radius", "radius >= 0.9 * dealias_circle_radius",
         "dealias mask over-truncates"),
    ],
}

DROP = [
    (re.compile(r" \+ ptot\b"), "dropped the total-pressure term"),
    (re.compile(r" - udotb \* B[xyz]\b"), "dropped the u.B transport term"),
    (re.compile(r" - B[xyz] \* B[xyz]\b"), "dropped a magnetic tension term"),
]

SWAPVEL = re.compile(r"= (u[xyz]) \* (B[xyz]) - (u[xyz]) \* (B[xyz])")
NORM_LHS = {"w_xyz", "w_zxy", "w_xy", "w_yx", "w_yxz"}
NORM = re.compile(r"/ n([xyz])\b")
BOUNDS = [
    (re.compile(r"^(\s*i([xyz])max = n\2)\s*$"), r"\1 - 1"),
    (re.compile(r"^(\s*i[xyz]max = \w+_offset\(myid_[ij]\+1\) \+ \w+_size\(myid_[ij]\+1\))\s*$"),
     r"\1 - 1"),
]


def gen_rkorder(em, tree, relpath):
    """fnl_rk saved before, not after, the RK state update (LAPS-specific)."""
    text, lines, live = em.load(relpath)
    pat = re.compile(
        r"(?P<upd>^(?P<ind>\s*)uu_fourier\(:,:,:,:\) = cc1\(irk\)\*fnl.*&\n.*\n)"
        r"(?P<save>^\s*fnl_rk\(:,:,:,:\) = fnl\(:,:,:,:\)[ \t]*\n)",
        re.M)
    m = pat.search(text)
    if not m:
        print(f"skip rkorder (no match): {relpath}", file=sys.stderr)
        return
    old = m.group(0)
    new = m.group("ind") + m.group("save").strip() + "\n" + m.group("upd")
    li = text[:m.start()].count("\n")
    em.emit("rkorder", tree, relpath, li, old, new,
            "fnl_rk is saved before, not after, the RK state update")


def generate(em, tree, relpath):
    fname = os.path.basename(relpath)
    if fname == "mhdrhs.f90":
        me.gen_sign(em, tree, relpath, SIGN_LHS[fname])
        me.gen_pairs(em, tree, relpath, COEF[fname])
        me.gen_delete(em, tree, relpath, "flux", DROP)
        me.gen_replace(em, tree, relpath, {"flux"}, SWAPVEL,
                       lambda m: f"= {m.group(3)} * {m.group(2)} - {m.group(1)} * {m.group(4)}",
                       lambda m: "swapped the velocity factors of one E-field component",
                       family="swapvel")
        me.gen_replace(em, tree, relpath, NORM_LHS, NORM,
                       lambda m: f"/ (n{m.group(1)} - 1)",
                       lambda m: f"FFT normalisation 1/n{m.group(1)} -> 1/(n{m.group(1)}-1)",
                       family="norm")
        me.gen_line_sub(em, tree, relpath, BOUNDS, "clipped a loop upper bound by one")
    elif fname == "rktmod.f90":
        me.gen_sign(em, tree, relpath, SIGN_LHS[fname])
        me.gen_pairs(em, tree, relpath, COEF[fname])
        gen_rkorder(em, tree, relpath)
    elif fname == "mhd.f90":
        me.gen_sign(em, tree, relpath, SIGN_LHS[fname])
        me.gen_pairs(em, tree, relpath, COEF[fname])
    elif fname == "dealiasing.f90":
        me.gen_pairs(em, tree, relpath, COEF[fname])
    elif fname == "fftw.f90":
        me.gen_replace(em, tree, relpath, NORM_LHS, NORM,
                       lambda m: f"/ (n{m.group(1)} - 1)",
                       lambda m: f"FFT normalisation 1/n{m.group(1)} -> 1/(n{m.group(1)}-1)",
                       family="norm")


FILES = ["dealiasing.f90", "fftw.f90", "mhd.f90", "mhdrhs.f90", "rktmod.f90"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=config.BASE)
    ap.add_argument("--out")
    args = ap.parse_args()

    em = me.Emitter(args.base, DEAD_FLAG, DEAD_TEXT, DEAD_SUBS)
    for tree, spec in sorted(config.TREES.items()):
        for fname in FILES:
            relpath = os.path.join(spec["subdir"], fname)
            if not os.path.isfile(os.path.join(args.base, relpath)):
                print(f"skip missing {relpath}", file=sys.stderr)
                continue
            generate(em, tree, relpath)

    rows = em.sorted()
    payload = "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n"
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w") as f:
            f.write(payload)
    else:
        sys.stdout.write(payload)
    print(f"{len(rows)} injection candidates", file=sys.stderr)


if __name__ == "__main__":
    main()
