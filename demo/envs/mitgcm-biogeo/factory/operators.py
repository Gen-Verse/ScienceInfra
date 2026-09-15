"""Mechanical fixed/free-form Fortran mutations over measured live files."""

import os
import re

import config


FLOAT = re.compile(
    r"(?<![A-Za-z0-9_.])((?:[0-9]+[.][0-9]*|[.][0-9]+)(?:[dDeE][+-]?[0-9]+)?)(?![A-Za-z0-9_.])")
SPACED_SIGN = re.compile(r"(?<= )([+-])(?= )")
ASSIGN = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*(?:\([^=]*\))?\s*=(?!=)")
DO_BOUND = re.compile(r"^(\s*[dD][oO]\s+[A-Za-z][A-Za-z0-9_]*\s*=\s*[^,]+,\s*)([A-Za-z][A-Za-z0-9_]*(?:\([^)]*\))?)(\s*)$")


def subsystem_of(relpath):
    if relpath.startswith("pkg/dic/"):
        return "dic-carbonate"
    if relpath.startswith("pkg/bling/"):
        return "bling-biogeochemistry"
    if relpath.startswith("pkg/cfc/"):
        return "cfc-gas-exchange"
    if relpath.startswith("pkg/gchem/"):
        return "gchem-dispatch"
    return "ptracer-transport"


def _code(line):
    if not line or line[0] in "Cc*!#":
        return ""
    return line.split("!", 1)[0]


def _unique_context(text, lines, index, old_line, new_line):
    old, new, lower = old_line, new_line, index
    while text.count(old) != 1 and index - lower < 8 and lower > 0:
        lower -= 1
        old = lines[lower] + "\n" + old
        new = lines[lower] + "\n" + new
    return (old, new) if text.count(old) == 1 else (None, None)


def _candidate(family, relpath, line, old, new, note, suffix):
    stem = re.sub(r"[^a-z0-9]+", "-", os.path.basename(relpath).lower()).strip("-")
    cid = f"{family}-{subsystem_of(relpath)}-{stem}-L{line + 1}-{suffix}"
    return {
        "id": cid,
        "source": "inject",
        "family": family,
        "tree": subsystem_of(relpath),
        "note": note,
        "break": {"edits": [{"file": relpath, "old": old, "new": new}]},
        "fix": {"edits": [{"file": relpath, "old": new, "new": old}]},
        "meta": {"file": relpath, "line": line + 1,
                 "predicted_tier": "easy",
                 "prediction_rationale":
                     "Mechanical single-site control; the local arithmetic is re-derivable."},
    }


def _perturb(token):
    value = float(token.replace("d", "e").replace("D", "E"))
    if value == 0.0:
        return None
    changed = value * (1.01 if value > 0 else 0.99)
    out = f"{changed:.12g}"
    if "d" in token.lower():
        out = out.replace("e", "d").replace("E", "D")
    elif "e" not in out.lower() and "." not in out:
        out += ".0"
    return out


def generate_file(base, relpath):
    text = open(os.path.join(base, relpath), encoding="utf-8").read()
    lines = text.split("\n")
    rows = []
    for line_index, raw in enumerate(lines):
        code = _code(raw)
        match = ASSIGN.match(code)
        if match:
            rhs_start = match.end()
            for number_index, number in enumerate(FLOAT.finditer(code[rhs_start:])):
                old_token = number.group(1)
                new_token = _perturb(old_token)
                if not new_token:
                    continue
                start = rhs_start + number.start(1)
                stop = rhs_start + number.end(1)
                new_line = raw[:start] + new_token + raw[stop:]
                old, new = _unique_context(text, lines, line_index, raw, new_line)
                if old:
                    rows.append(_candidate(
                        "coef", relpath, line_index, old, new,
                        f"perturb a numeric coefficient in {match.group(1)} by one percent",
                        f"n{number_index}"))
            for sign_index, sign in enumerate(SPACED_SIGN.finditer(code[rhs_start:])):
                start = rhs_start + sign.start(1)
                stop = rhs_start + sign.end(1)
                flipped = "+" if sign.group(1) == "-" else "-"
                new_line = raw[:start] + flipped + raw[stop:]
                old, new = _unique_context(text, lines, line_index, raw, new_line)
                if old:
                    rows.append(_candidate(
                        "sign", relpath, line_index, old, new,
                        f"flip one arithmetic sign in {match.group(1)}", f"s{sign_index}"))
        bound = DO_BOUND.match(code)
        if bound and len(code) + 2 <= 132:
            new_line = bound.group(1) + bound.group(2) + "-1" + bound.group(3)
            old, new = _unique_context(text, lines, line_index, raw, new_line)
            if old:
                rows.append(_candidate(
                    "bounds", relpath, line_index, old, new,
                    "clip a loop upper bound by one", "b0"))
    return rows


def generate(base):
    rows = []
    for relpath in config.PHYSICS_FILES:
        rows.extend(generate_file(base, relpath))
    return sorted(rows, key=lambda row: row["id"])
