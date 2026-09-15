# Turns the builder stage's walltimes.txt ("<check> <t0_ns> <t1_ns>" per line)
# into incumbent_timing.json. Runs only at verifier-image build time.
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
rows = {}
with open(src) as f:
    for line in f:
        c, t0, t1 = line.split()
        rows[c] = round((int(t1) - int(t0)) / 1e9, 3)
with open(dst, "w") as f:
    json.dump(
        {
            "seconds": rows,
            "ranks": 4,
            "note": "measured on the machine that built this image; advisory",
        },
        f,
        indent=1,
    )
