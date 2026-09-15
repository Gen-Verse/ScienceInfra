"""Routine-body excision for MITgcm fixed-form .F sources."""

import os
import re

import operators


SUB_OPEN = re.compile(r"^\s*SUBROUTINE\s+([A-Za-z0-9_]+)", re.I)
SUB_CLOSE = re.compile(r"^\s*END\s*(?:!.*)?$", re.I)
DECL = re.compile(
    r"\s*(IMPLICIT|INTEGER|REAL|LOGICAL|CHARACTER|COMPLEX|DIMENSION|PARAMETER|"
    r"COMMON|SAVE|EXTERNAL|DATA|EQUIVALENCE|NAMELIST)\b", re.I)


def _subroutines(lines):
    index = 0
    while index < len(lines):
        match = SUB_OPEN.match(lines[index])
        if not match:
            index += 1
            continue
        stop = index + 1
        while stop < len(lines) and not SUB_CLOSE.match(lines[stop]):
            stop += 1
        if stop < len(lines):
            yield match.group(1), index, stop
        index = stop + 1


def _first_exec(body):
    in_signature = True
    for index, raw in enumerate(body):
        stripped = raw.strip()
        if in_signature and (raw.startswith("     ") and len(raw) > 5 and
                             raw[5:6] not in (" ", "0")):
            continue
        in_signature = False
        if (not stripped or raw[:1] in "Cc*!" or stripped.startswith("#") or
                stripped == "CEOP" or DECL.match(raw)):
            continue
        return index
    return None


def generate(base, relpaths):
    rows = []
    for relpath in relpaths:
        path = os.path.join(base, relpath)
        text = open(path, encoding="utf-8").read()
        lines = text.splitlines(keepends=True)
        for name, start, stop in _subroutines(lines):
            body = lines[start + 1:stop]
            first = _first_exec(body)
            if first is None:
                continue
            tail = len(body)
            while tail > first:
                stripped = body[tail - 1].strip()
                if (not stripped or body[tail - 1][:1] in "Cc*!" or
                        stripped.startswith("#endif")):
                    tail -= 1
                else:
                    break
            old = "".join(body[first:tail])
            if len(old.strip()) < 20 or text.count(old) != 1:
                continue
            indent = re.match(r"^\s*", body[first]).group()
            new = indent + "RETURN\n"
            if text.replace(old, new, 1).count(new) != 1:
                continue
            edit = {"file": relpath, "old": old, "new": new}
            cid = ("excise-" + operators.subsystem_of(relpath) + "-" +
                   os.path.basename(relpath).removesuffix(".F").lower() + "-" +
                   name.lower())
            rows.append({
                "id": cid, "source": "excise", "family": "excise",
                "tree": operators.subsystem_of(relpath),
                "note": f"excise the executable body of {name}",
                "break": {"edits": [edit]},
                "fix": {"edits": [{"file": relpath, "old": new, "new": old}]},
                "meta": {"file": relpath, "subroutine": name,
                         "body_lines": old.count("\n"),
                         "predicted_tier": "medium" if old.count("\n") >= 80 else "easy",
                         "prediction_rationale":
                             "Long incumbent floating-point bodies can resist bit-exact reconstruction."
                             if old.count("\n") >= 80 else
                             "Short routine restore is locally re-derivable and serves as an easy control."},
            })
    return sorted(rows, key=lambda row: row["id"])
