"""Injection candidate generator: physics-anchored mutation sites.

    python3 operators.py [--base DIR] [--out PATH]

Emits candidates (schema: lib.py docstring) by scanning the live code paths of
both compressible trees with a RULES table. "Live" is decided against the
decks this factory grades: if_AEB / if_Hall / if_resis / if_visc are all F and
dealias_option = 1, so matches inside those branches (and inside subroutines
only reachable from them) are skipped instead of being screened to death.
The funnel remains the authority on symptoms — this filter only saves cycles.

Site families:
    sign      flip one spaced +/- in the RHS of a physics assignment
    coef      perturb one named coefficient (pressure, RK, CFL, dealias radius)
    dropterm  delete one additive physics term (+ ptot, tension, u.B transport)
    swapvel   swap the two velocity factors in one E-field component
    norm      FFT normalisation 1/n -> 1/(n-1)
    bounds    clip one loop upper bound by one
    rkorder   update fnl_rk before, not after, the RK state update

Every edit is exact-string-replace with `old` unique in its file; where a bare
site is not unique the edit grows by whole preceding lines (up to GROW_MAX)
until it is, or the site is dropped with a stderr note.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

GROW_MAX = 6

DEAD_FLAG = re.compile(r"\b(if_aeb|if_hall|if_resis|if_visc|if_corotating)\b", re.I)
DEAD_TEXT = re.compile(r"dealias_option\s*==\s*2")
DEAD_SUBS = {"calc_current_density_real"}  # reachable only under if_hall

IF_THEN = re.compile(r"^\s*(else\s+)?if\b.*\bthen\s*$", re.I)
ELSE = re.compile(r"^\s*else\b", re.I)
END_IF = re.compile(r"^\s*end\s*if\b", re.I)
SUB_START = re.compile(r"^\s*subroutine\s+(\w+)", re.I)
SUB_END = re.compile(r"^\s*end\s+subroutine\b", re.I)


def code_part(line):
    """The line with any trailing comment cut (this code has no '!' in strings)."""
    i = line.find("!")
    return line if i < 0 else line[:i]


def live_mask(lines):
    """True per line iff the line is reachable with this factory's decks."""
    mask = [True] * len(lines)
    stack = []  # per open if-construct: is the CURRENT branch dead?
    sub_dead = False
    for i, raw in enumerate(lines):
        t = code_part(raw).strip()
        m = SUB_START.match(t)
        if m:
            sub_dead = m.group(1).lower() in DEAD_SUBS
        dead_cond = bool(DEAD_FLAG.search(t) or DEAD_TEXT.search(t))
        if IF_THEN.match(t):
            if t.lower().lstrip().startswith("else"):
                if stack:
                    stack[-1] = dead_cond
            else:
                stack.append(dead_cond)
        elif ELSE.match(t) and not IF_THEN.match(t):
            if stack:
                stack[-1] = False  # plain else of a dead-if is the LIVE branch
        elif END_IF.match(t):
            if stack:
                stack.pop()
        in_dead = sub_dead or any(stack)
        # single-line `if (dead_flag) stmt` (no then)
        if (not IF_THEN.match(t) and t.lower().startswith("if") and dead_cond):
            mask[i] = False
            continue
        mask[i] = not in_dead
        if SUB_END.match(t):
            sub_dead = False
    return mask


def head_of(lines, i):
    """Index of the first line of the statement line i belongs to."""
    while i > 0 and code_part(lines[i - 1]).rstrip().endswith("&"):
        i -= 1
    return i


def lhs_of(lines, i):
    m = re.match(r"\s*(\w+)\s*(?:\([^=]*\))?\s*=[^=]", code_part(lines[head_of(lines, i)]))
    return m.group(1).lower() if m else None


def grow_unique(text, lines, li, old_line, new_line):
    """(old, new) covering whole lines, grown upward until old is unique."""
    old, new = old_line, new_line
    lo = li
    while text.count(old) != 1 and li - lo < GROW_MAX and lo > 0:
        lo -= 1
        old = lines[lo] + "\n" + old
        new = lines[lo] + "\n" + new
    return (old, new) if text.count(old) == 1 else (None, None)


class Emitter:
    def __init__(self, base):
        self.base = base
        self.out = []
        self.seen = set()
        self.files = {}

    def load(self, relpath):
        if relpath not in self.files:
            with open(os.path.join(self.base, relpath), encoding="utf-8") as f:
                text = f.read()
            lines = text.split("\n")
            self.files[relpath] = (text, lines, live_mask(lines))
        return self.files[relpath]

    def emit(self, family, tree, relpath, li, old, new, note, variant=""):
        if old is None or old == new:
            return
        stem = os.path.basename(relpath).replace(".f90", "")
        cid = f"{family}-{tree}-{stem}-L{li + 1}{variant}"
        if cid in self.seen:
            for suf in "bcdefgh":
                if cid + suf not in self.seen:
                    cid += suf
                    break
        self.seen.add(cid)
        self.out.append({
            "id": cid, "source": "inject", "family": family, "tree": tree,
            "note": note,
            "break": {"edits": [{"file": relpath, "old": old, "new": new}]},
            "fix": {"edits": [{"file": relpath, "old": new, "new": old}]},
            "meta": {"file": relpath, "line": li + 1},
        })

    def line_edit(self, family, tree, relpath, li, new_line, note, variant=""):
        text, lines, _ = self.load(relpath)
        old, new = grow_unique(text, lines, li, lines[li], new_line)
        if old is None:
            print(f"skip (not unique within {GROW_MAX} lines): "
                  f"{relpath}:{li + 1}", file=sys.stderr)
            return
        self.emit(family, tree, relpath, li, old, new, note, variant)


# ------------------------------------------------------------------- families

SIGN_LHS = {
    "mhdrhs.f90": {"flux", "fnl", "ptot", "udotb", "uu_prim"},
    "rktmod.f90": {"uu_fourier"},
    "mhd.f90": {"csound2", "cms2", "cnsx2", "cnsy2", "cnsz2",
                "cmaxx", "cmaxy", "cmaxz", "dtx", "dty", "dtz"},
}

SPACED_SIGN = re.compile(r"(?<= )([+-])(?= )")


def gen_sign(em, tree, relpath):
    fname = os.path.basename(relpath)
    allowed = SIGN_LHS.get(fname, set())
    text, lines, live = em.load(relpath)
    for li, raw in enumerate(lines):
        if not live[li]:
            continue
        code = code_part(raw)
        lhs = lhs_of(lines, li)
        if lhs not in allowed:
            continue
        eq = code.find("=") if head_of(lines, li) == li else -1
        for m in SPACED_SIGN.finditer(code):
            if m.start() <= eq:
                continue
            flipped = "-" if m.group(1) == "+" else "+"
            new_line = raw[:m.start()] + flipped + raw[m.end():]
            em.line_edit("sign", tree, relpath, li, new_line,
                         f"flipped `{m.group(1)}` to `{flipped}` in the "
                         f"`{lhs}` statement", variant=f"c{m.start()}-")


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


def gen_coef(em, tree, relpath):
    fname = os.path.basename(relpath)
    text, lines, live = em.load(relpath)
    for k, (old_s, new_s, what) in enumerate(COEF.get(fname, [])):
        if text.count(old_s) != 1:
            if text.count(old_s) > 1:
                print(f"skip coef (ambiguous): {relpath} `{old_s}`", file=sys.stderr)
            continue
        li = text[:text.index(old_s)].count("\n")
        if not live[li]:
            continue
        em.emit("coef", tree, relpath, li,
                old_s, new_s, f"perturbed the {what}", variant=f"k{k}-")


DROP = [
    (re.compile(r" \+ ptot\b"), "dropped the total-pressure term"),
    (re.compile(r" - udotb \* B[xyz]\b"), "dropped the u.B transport term"),
    (re.compile(r" - B[xyz] \* B[xyz]\b"), "dropped a magnetic tension term"),
]


def gen_dropterm(em, tree, relpath):
    text, lines, live = em.load(relpath)
    for li, raw in enumerate(lines):
        if not live[li] or lhs_of(lines, li) != "flux":
            continue
        code = code_part(raw)
        for pat, what in DROP:
            for m in pat.finditer(code):
                new_line = raw[:m.start()] + raw[m.end():]
                em.line_edit("dropterm", tree, relpath, li, new_line, what,
                             variant=f"c{m.start()}-")


SWAPVEL = re.compile(r"= (u[xyz]) \* (B[xyz]) - (u[xyz]) \* (B[xyz])")


def gen_swapvel(em, tree, relpath):
    text, lines, live = em.load(relpath)
    for li, raw in enumerate(lines):
        if not live[li] or lhs_of(lines, li) != "flux":
            continue
        m = SWAPVEL.search(code_part(raw))
        if not m:
            continue
        new_line = (raw[:m.start()] +
                    f"= {m.group(3)} * {m.group(2)} - {m.group(1)} * {m.group(4)}" +
                    raw[m.end():])
        em.line_edit("swapvel", tree, relpath, li, new_line,
                     "swapped the velocity factors of one E-field component")


NORM_LHS = {"w_xyz", "w_zxy", "w_xy", "w_yx", "w_yxz"}
NORM = re.compile(r"/ n([xyz])\b")


def gen_norm(em, tree, relpath):
    text, lines, live = em.load(relpath)
    for li, raw in enumerate(lines):
        if not live[li] or lhs_of(lines, li) not in NORM_LHS:
            continue
        m = NORM.search(code_part(raw))
        if not m:
            continue
        new_line = raw[:m.start()] + f"/ (n{m.group(1)} - 1)" + raw[m.end():]
        em.line_edit("norm", tree, relpath, li, new_line,
                     f"FFT normalisation 1/n{m.group(1)} -> 1/(n{m.group(1)}-1)")


BOUNDS = [
    (re.compile(r"^(\s*i([xyz])max = n\2)\s*$"), r"\1 - 1"),
    (re.compile(r"^(\s*i[xyz]max = \w+_offset\(myid_[ij]\+1\) \+ \w+_size\(myid_[ij]\+1\))\s*$"),
     r"\1 - 1"),
]


def gen_bounds(em, tree, relpath):
    text, lines, live = em.load(relpath)
    for li, raw in enumerate(lines):
        if not live[li]:
            continue
        for pat, repl in BOUNDS:
            m = pat.match(code_part(raw))
            if m:
                em.line_edit("bounds", tree, relpath, li,
                             pat.sub(repl, code_part(raw)),
                             "clipped a loop upper bound by one")


def gen_rkorder(em, tree, relpath):
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


GENERATORS = {
    "mhdrhs.f90": [gen_sign, gen_coef, gen_dropterm, gen_swapvel, gen_norm,
                   gen_bounds],
    "rktmod.f90": [gen_sign, gen_coef, gen_rkorder],
    "mhd.f90": [gen_sign, gen_coef],
    "dealiasing.f90": [gen_coef],
    "fftw.f90": [gen_norm],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=config.BASE)
    ap.add_argument("--out")
    args = ap.parse_args()

    em = Emitter(args.base)
    for tree, spec in sorted(config.TREES.items()):
        for fname, gens in sorted(GENERATORS.items()):
            relpath = os.path.join(spec["subdir"], fname)
            if not os.path.isfile(os.path.join(args.base, relpath)):
                print(f"skip missing {relpath}", file=sys.stderr)
                continue
            for g in gens:
                g(em, tree, relpath)

    rows = sorted(em.out, key=lambda c: c["id"])
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
