#!/usr/bin/env python3
"""Apply a transform spec to a source tree.

Spec: {"edits": [{"file","old","new"}]} (exact-string, old unique per file)
   or {"diff": "<unified diff>"} (applied with patch -p1).
Usage: apply_defect.py SPEC.json TREE_ROOT
"""
import json, os, subprocess, sys

spec, root = sys.argv[1], sys.argv[2]
t = json.load(open(spec))
if "edits" in t:
    for e in t["edits"]:
        p = os.path.join(root, e["file"])
        s = open(p, encoding="utf-8").read()
        n = s.count(e["old"])
        if n != 1:
            sys.exit(f"{p}: pattern occurs {n} times, need exactly 1")
        open(p, "w", encoding="utf-8").write(s.replace(e["old"], e["new"], 1))
elif "diff" in t:
    r = subprocess.run(["patch", "-p1", "--no-backup-if-mismatch", "-f"],
                       input=t["diff"], text=True, cwd=root)
    if r.returncode:
        sys.exit("patch failed")
else:
    sys.exit("transform carries neither edits nor diff")
print(f"applied {spec} to {root}")
