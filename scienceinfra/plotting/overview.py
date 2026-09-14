"""
Regenerate the ScienceInfra architecture overview figure.

Usage: `python -m scienceinfra.plotting.overview [--out-dir figures]`

This is a schematic, not a measurement. Box sizes and arrow lengths carry no
throughput, latency, or wall-clock meaning.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scienceinfra.plotting import style as st

WIDTH, HEIGHT = 760, 388
LEFT = 16
COL_W = 232
COL_GAP = 20

# Vertical geometry, in points. Rows are a fixed height so the three columns line
# up row for row even though they hold different counts.
ROW_H, ROW_GAP, PAD = 31, 6, 13
HEAD_H = 54

# Forward flow is blue, the reward path back to the trainer is orange. That is the
# only thing hue encodes here.
FLOW = st.BLUE
FEEDBACK = st.ORANGE

COLUMNS = [
    {
        "heading": "Task bank",
        "subheading": "Scientific codebases",
        "tint": st.BLUE_TINT,
        "icon": st.icon_beaker,
        "accent": st.BLUE,
        "rows": [
            ("Defects", "Planted in a real simulation"),
            ("Environments", "Built and run in a container"),
            ("Verifiers", "Decide numerical agreement"),
        ],
    },
    {
        "heading": "ScienceInfra",
        "subheading": "This package",
        "tint": st.ORANGE_TINT,
        "icon": st.icon_scientist,
        "accent": st.ORANGE,
        "rows": [
            ("Dataset builder", "Task bank to training data"),
            ("Agent loop", "One episode per prompt"),
            ("Episode runner", "Container lifecycle"),
            ("Reward", "Scored by the verifier"),
            ("Failure classifier", "Separates faults from failures"),
        ],
    },
    {
        "heading": "PSRL",
        "subheading": "RL backend",
        "tint": st.BLUE_TINT,
        "icon": st.icon_cpu,
        "accent": st.BLUE,
        "rows": [
            ("Rollout fleet", "Asynchronous generation"),
            ("Token capture", "Exactly what was served"),
            ("Trainer", "Policy optimization"),
        ],
    },
]


def _column_height(rows: list) -> float:
    """
    Height of a panel holding `rows`, including its heading and margins.
    """
    return len(rows) * ROW_H + (len(rows) - 1) * ROW_GAP + PAD * 2 + HEAD_H


def _stack(ax, x, top_y, column: dict) -> None:
    """
    Draw one titled panel, hanging its row stack down from `top_y`.

    Args:
        ax: The background axes.
        x: Panel left edge.
        top_y: Panel top edge. Columns are top-aligned so their first rows line up.
        column: Heading, subheading, tint, icon, accent, and `(label, detail)` rows.
    """
    height = _column_height(column["rows"])
    st.box(ax, x, top_y - height, COL_W, height, face=column["tint"], edge=None)

    column["icon"](ax, x + PAD + 13, top_y - 26, size=26, color=column["accent"])
    st.text(ax, x + PAD + 34, top_y - 20, column["heading"], size=12.5, weight="bold")
    st.text(ax, x + PAD + 34, top_y - 35, column["subheading"], size=9, color=st.MUTED)

    row_y = top_y - HEAD_H - PAD - ROW_H
    for label, detail in column["rows"]:
        st.box(ax, x + PAD, row_y, COL_W - PAD * 2, ROW_H, face=st.SURFACE, edge=st.LINE, radius=4)
        # A short accent rule stands in for a per-row icon, which at this size
        # would be too small to read as anything.
        ax.plot(
            [x + PAD + 9, x + PAD + 9],
            [row_y + 7, row_y + ROW_H - 7],
            color=column["accent"],
            linewidth=2.2,
            solid_capstyle="round",
            zorder=11,
        )
        st.text(ax, x + PAD + 18, row_y + ROW_H / 2 + 6, label, size=10, weight="bold")
        st.text(ax, x + PAD + 18, row_y + ROW_H / 2 - 6.5, detail, size=8.5, color=st.MUTED)
        row_y -= ROW_H + ROW_GAP


def draw() -> object:
    """
    Draw the three-column overview: task bank, ScienceInfra, RL backend.
    """
    fig, ax = st.canvas(WIDTH, HEIGHT)

    st.text(ax, LEFT, HEIGHT - 24, "ScienceInfra", size=16.5, weight="bold")
    st.text(
        ax,
        LEFT,
        HEIGHT - 44,
        "Agentic RL on real scientific codebases, graded by whether the simulation runs correctly again.",
        size=10,
        color=st.MUTED,
    )

    top = HEIGHT - 64
    xs = [LEFT + index * (COL_W + COL_GAP) for index in range(3)]
    for x, column in zip(xs, COLUMNS, strict=True):
        _stack(ax, x, top, column)

    # Both connectors sit on the second row, which every column has.
    flow_y = top - HEAD_H - PAD - ROW_H - ROW_GAP - ROW_H / 2
    for index in (0, 1):
        st.arrow(ax, (xs[index] + COL_W, flow_y), (xs[index + 1], flow_y), color=FLOW, lw=1.4)
    st.text(ax, xs[0] + COL_W + COL_GAP / 2, flow_y + 13, "tasks", size=8.5, color=st.MUTED, ha="center")
    st.text(ax, xs[1] + COL_W + COL_GAP / 2, flow_y + 13, "prompts", size=8.5, color=st.MUTED, ha="center")

    # The reward path, routed under the tallest column so it crosses nothing.
    tallest = max(_column_height(column["rows"]) for column in COLUMNS)
    bottom = top - tallest
    loop_y = bottom - 30
    st.arrow(
        ax,
        (xs[2] + COL_W / 2, top - _column_height(COLUMNS[2]["rows"])),
        (xs[1] + COL_W / 2, bottom),
        color=FEEDBACK,
        lw=1.4,
        waypoints=((xs[2] + COL_W / 2, loop_y), (xs[1] + COL_W / 2, loop_y)),
    )
    # The verifier's verdict rides on the return path, so the badge and its label
    # sit on the line with the surface knocked out behind them rather than
    # floating beside it.
    badge_x = (xs[1] + xs[2]) / 2 + COL_W / 2
    label_w = st.text_width("reward", 9) + 10
    st.box(ax, badge_x - 15, loop_y - 15, 30 + label_w, 30, face=st.SURFACE, edge=None, radius=0, zorder=10)
    st.icon_flask_check(ax, badge_x, loop_y, size=22, color=FEEDBACK)
    st.text(ax, badge_x + 19, loop_y, "reward", size=9, color=st.MUTED)
    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate the ScienceInfra overview figure.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "figures",
        help="destination directory (default: the repository's figures/)",
    )
    args = parser.parse_args()

    for path in st.save(draw(), "overview", args.out_dir):
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
