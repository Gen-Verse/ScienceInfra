"""Excision candidates for the repair/restore task factory.

For every SUBROUTINE in the .f90 files of both compressible trees, emit one
candidate whose `break` replaces the subroutine's EXECUTABLE body with a
stub (declarations kept, so the tree still compiles) and whose `fix` is the
exact inverse -- lib.apply_transform's edits with old/new swapped. These
become "restore the missing routine" repair tasks.

    python3 excise.py [--base DIR] [--out PATH]

Writes candidates as JSONL, sorted by id, to PATH or (default) stdout.

Parsing is a line-oriented heuristic tuned to this codebase, not a general
Fortran parser. It relies on two properties verified against the LAPS
sources: subroutines never nest (one module-level `contains` per file, no
internal procedures, no interface blocks), and a subroutine's signature
never spans multiple lines. It does tolerate the merged-keyword spellings
gfortran accepts under -std=legacy, e.g. `endsubroutine` with no space
(src_compressible/2D/mhd.f90's checkNan ends this way).
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

SUB_OPEN = re.compile(r'^\s*(?:recursive\s+)?subroutine\s+(\w+)', re.I)
SUB_CLOSE = re.compile(r'^\s*end\s*subroutine\b', re.I)
INDENT = re.compile(r'^ *')

# Statement kinds that belong to a subroutine's declaration part, per the
# spec: use, implicit, type declarations (classic or `::` form), parameter,
# save, external, intrinsic, namelist, data, equivalence, common.
DECL_KW = re.compile(
    r'(use|implicit|parameter|save|external|intrinsic|namelist|data|'
    r'equivalence|common|integer|real|complex|logical|character|dimension)\b'
    r'|type\s*\(', re.I)

STUB_TEXT = [
    "! ============================================================",
    "! The body of this subroutine has been removed.",
    "! Restore it so the solver reproduces the correct physics.",
    "! ============================================================",
    "return",
]


def warn(msg):
    print(f"excise: {msg}", file=sys.stderr)


def iter_subroutines(text, relfile):
    """Yield (name, body_start, body_end) for each top-level `subroutine
    ... end subroutine` span in `text`, where body_start/body_end index the
    keepends-lines of `text` such that lines[body_start:body_end] is
    everything strictly between the signature line and `end subroutine`
    (declarations first, then the executable statements to excise).
    `relfile` is only used to label warnings.
    """
    lines = text.splitlines(keepends=True)
    i, n = 0, len(lines)
    while i < n:
        m = SUB_OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        j = i + 1
        while j < n and not SUB_CLOSE.match(lines[j]) and not SUB_OPEN.match(lines[j]):
            j += 1
        if j >= n or SUB_OPEN.match(lines[j]):
            where = "EOF" if j >= n else f"line {j + 1}"
            warn(f"{relfile}: {name}: no matching `end subroutine` before "
                 f"{where} -- skipping")
            i = j  # re-examine lines[j]: may be the next subroutine's opener
            continue
        yield name, i + 1, j
        i = j + 1


def first_exec_line(body):
    """Index into `body` of its first executable statement, skipping blank
    lines, comments, declaration statements and their `&` continuations.
    None if the body has no executable statement at all.
    """
    cont = False
    for i, ln in enumerate(body):
        s = ln.strip()
        if not s or s.startswith('!'):
            continue
        if cont:
            cont = s.endswith('&')
            continue
        if DECL_KW.match(s):
            cont = s.endswith('&')
            continue
        return i
    return None


def unique_span(text, body, exec_i):
    """Index of the smallest suffix of `body` starting at or before
    `exec_i` whose joined text occurs exactly once in `text`. None if even
    the whole body isn't unique (shouldn't happen -- the whole body
    includes the signature-adjacent declarations too). Extending left over
    declaration lines is safe: those lines re-appear unchanged at the front
    of `new` (see make_edit), so nothing declared is actually lost, only
    the replaced span grows.
    """
    for cut_start in range(exec_i, -1, -1):
        if text.count(''.join(body[cut_start:])) == 1:
            return cut_start
    return None


def make_edit(body, cut_start, exec_i):
    indent = INDENT.match(body[exec_i]).group()
    stub = ''.join(indent + s + '\n' for s in STUB_TEXT)
    old = ''.join(body[cut_start:])
    new = ''.join(body[cut_start:exec_i]) + stub
    return old, new


def call_sites(tree_text, name):
    pat = re.compile(r'\bcall\s+' + re.escape(name) + r'\b', re.I)
    return len(pat.findall(tree_text))


def gen_candidates(base):
    candidates = []
    for tree, spec in config.TREES.items():
        tree_dir = os.path.join(base, spec["subdir"])
        fpaths = sorted(glob.glob(os.path.join(tree_dir, "*.f90")))
        texts = {fp: open(fp, encoding="utf-8").read() for fp in fpaths}
        tree_text = ''.join(texts.values())
        for fp in fpaths:
            text = texts[fp]
            lines = text.splitlines(keepends=True)
            relfile = os.path.join(spec["subdir"], os.path.basename(fp))
            stem = os.path.splitext(os.path.basename(fp))[0]
            for name, bstart, bend in iter_subroutines(text, relfile):
                body = lines[bstart:bend]
                exec_i = first_exec_line(body)
                if exec_i is None:
                    warn(f"{relfile}: {name}: empty executable body -- skipping")
                    continue
                cut_start = unique_span(text, body, exec_i)
                if cut_start is None:
                    warn(f"{relfile}: {name}: no unique `old` span found -- skipping")
                    continue
                old, new = make_edit(body, cut_start, exec_i)
                edit = {"file": relfile, "old": old, "new": new}
                candidates.append({
                    "id": f"excise-{tree}-{stem}-{name}".lower(),
                    "source": "excise",
                    "family": "excise",
                    "tree": tree,
                    "note": f"excise the executable body of {name} ({relfile})",
                    "break": {"edits": [edit]},
                    "fix": {"edits": [{"file": relfile, "old": new, "new": old}]},
                    "meta": {
                        "subroutine": name,
                        "file": relfile,
                        "body_lines": len(body) - exec_i,
                        "call_sites": call_sites(tree_text, name),
                    },
                })

    dupes = [k for k, v in Counter(c["id"] for c in candidates).items() if v > 1]
    if dupes:
        sys.exit("FATAL: duplicate candidate ids: " + ", ".join(sorted(dupes)))
    candidates.sort(key=lambda c: c["id"])
    return candidates


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=config.BASE,
                     help="pristine tree root (default: config.BASE)")
    ap.add_argument("--out", help="write JSONL here (default: stdout)")
    args = ap.parse_args()

    rows = gen_candidates(args.base)
    lines = [json.dumps(c, sort_keys=True) for c in rows]
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            f.write('\n'.join(lines) + ('\n' if lines else ''))
    else:
        for ln in lines:
            print(ln)


if __name__ == "__main__":
    sys.exit(main())
