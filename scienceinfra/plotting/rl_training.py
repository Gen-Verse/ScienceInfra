"""
Regenerate the per-environment RL training diagnostics figures.

Usage: `python -m scienceinfra.plotting.rl_training [--out-dir figures]`

One figure per environment. The environments are separate task banks with
separate defect families and their own reward scales, so a shared panel would
invite a comparison that is not meaningful.

Data provenance: every recorded training step of the reported runs, read from
the PSRL console logs those runs wrote. Columns are transcribed from these
metric keys, one row per step that emitted a complete metric line:

    step                 step:<n>
    mean_reward          critic/rewards/mean
    entropy              actor/entropy
    tokens_per_turn      response_length/mean / training/num_turns/mean
    truncation_percent   termination/masked_sample_fraction * 100

The table is committed rather than parsed so the figures stay reproducible
without the multi-gigabyte run logs. A handful of steps are absent because
their log line was incomplete, not because training paused. The series is
drawn through them, so the line reads as the continuous run it was. Nothing
here is smoothed, averaged across seeds, or estimated.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scienceinfra.plotting import style as st

WIDTH, HEIGHT = 720, 252
PANEL_W, PANEL_H = 167, 168
LEFT, GAP = 14, 9

RUNS = {
    "laps": {
        "stem": "rl_training_laps",
        "label": "LAPS",
        "detail": "Pseudo-spectral Hall-MHD, 85 train / 14 val. Qwen3.5-4B, GRPO at hint level L1.",
        "color": st.BLUE,
        "rows": [
            [1, 0.4867, 0.5859, 1095.3, 32.03],
            [2, 0.4016, 0.6250, 1127.9, 42.19],
            [3, 0.4383, 0.5898, 1133.2, 44.53],
            [4, 0.3961, 0.5898, 1057.8, 39.06],
            [5, 0.4109, 0.6211, 1100.8, 39.84],
            [6, 0.4015, 0.5039, 1099.3, 41.41],
            [7, 0.4164, 0.5781, 1085.2, 35.16],
            [8, 0.4703, 0.5898, 1172.7, 40.62],
            [9, 0.5000, 0.6445, 1141.4, 34.38],
            [10, 0.5312, 0.5586, 1188.1, 31.25],
            [11, 0.6680, 0.5078, 1144.0, 17.97],
            [13, 0.5867, 0.5273, 1169.4, 26.56],
            [14, 0.7188, 0.4746, 1181.8, 21.09],
            [16, 0.7812, 0.4844, 1179.6, 11.72],
            [17, 0.6586, 0.4902, 1233.8, 21.09],
            [18, 0.8203, 0.5430, 1134.5, 10.94],
            [19, 0.7430, 0.4688, 1170.8, 10.16],
            [20, 0.7000, 0.5312, 1177.2, 10.16],
            [21, 0.7766, 0.5117, 1203.9, 10.16],
            [22, 0.8461, 0.4277, 1208.6, 7.81],
            [23, 0.7734, 0.4199, 1168.3, 7.81],
            [24, 0.8320, 0.4160, 1122.7, 7.03],
            [25, 0.7699, 0.4668, 1194.8, 7.03],
            [26, 0.8367, 0.4121, 1140.5, 7.81],
            [27, 0.8203, 0.4219, 1159.8, 3.91],
            [28, 0.7820, 0.4375, 1152.0, 10.94],
            [29, 0.9141, 0.3125, 1089.9, 5.47],
            [30, 0.8516, 0.3477, 1164.8, 4.69],
            [31, 0.7734, 0.3848, 1109.5, 7.81],
        ],
    },
    "biogeo": {
        "stem": "rl_training_mitgcm_biogeo",
        "label": "MITgcm-biogeo",
        "detail": "Ocean biogeochemistry, 64 train / 23 val. Qwen3.5-4B, GRPO at hint level L1.",
        "color": st.ORANGE,
        "rows": [
            [1, 0.4187, 0.5156, 777.9, 30.47],
            [2, 0.3672, 0.5625, 843.2, 35.16],
            [3, 0.4062, 0.5664, 798.7, 32.81],
            [4, 0.3530, 0.6055, 735.1, 33.59],
            [6, 0.3594, 0.4941, 745.7, 38.28],
            [7, 0.4781, 0.5625, 818.3, 20.31],
            [8, 0.4688, 0.5195, 758.5, 24.22],
            [9, 0.4453, 0.4746, 807.3, 25.00],
            [10, 0.4453, 0.5273, 839.6, 22.66],
            [11, 0.5477, 0.5078, 817.8, 19.53],
            [12, 0.5117, 0.4883, 864.3, 15.62],
            [13, 0.5946, 0.4531, 765.3, 16.41],
            [14, 0.5469, 0.4551, 781.2, 17.97],
            [15, 0.5547, 0.3945, 886.4, 19.53],
            [16, 0.4766, 0.4375, 947.7, 21.09],
            [17, 0.4062, 0.4746, 934.1, 27.34],
            [18, 0.5977, 0.3789, 900.2, 20.31],
            [19, 0.6266, 0.3730, 811.2, 18.75],
            [20, 0.5312, 0.3262, 789.8, 20.31],
            [21, 0.5547, 0.3145, 840.0, 29.69],
            [22, 0.5008, 0.3848, 987.1, 32.03],
            [23, 0.4062, 0.3359, 855.0, 31.25],
            [24, 0.4922, 0.3730, 904.8, 40.62],
            [25, 0.7098, 0.3652, 961.9, 21.88],
            [26, 0.5547, 0.2949, 847.4, 25.00],
            [27, 0.6162, 0.3320, 957.7, 17.97],
            [28, 0.6875, 0.2754, 844.6, 21.09],
            [29, 0.6016, 0.3262, 995.1, 18.75],
            [30, 0.5259, 0.3340, 926.3, 35.94],
        ],
    },
}

COLUMNS = ["step", "mean_reward", "entropy", "tokens_per_turn", "truncation_percent"]

# One panel per metric, in reading order. The tint alternates so the row scans as
# pairs, and carries no meaning beyond that.
PANELS = [
    ("mean_reward", "Training reward", st.BLUE_TINT, False),
    ("truncation_percent", "Budget truncation (%)", st.ORANGE_TINT, True),
    ("tokens_per_turn", "Tokens per turn", st.BLUE_TINT, False),
    ("entropy", "Entropy", st.ORANGE_TINT, True),
]


def _series(run: dict, column: str) -> tuple[list[float], list[float]]:
    """
    Extract one metric against step.

    Steps missing from the table are steps whose log line was incomplete. The
    run itself was continuous, so the series is left unbroken and the x values
    carry the real step numbers, which keeps a skipped step visible as a wider
    segment rather than hiding it.

    Args:
        run: A `RUNS` entry.
        column: A name from `COLUMNS`.

    Returns:
        The step numbers and the metric values.
    """
    index = COLUMNS.index(column)
    steps = [float(row[0]) for row in run["rows"]]
    values = [float(row[index]) for row in run["rows"]]
    return steps, values


def draw(run: dict) -> object:
    """
    Draw the four-panel diagnostics figure for one environment.

    Args:
        run: A `RUNS` entry.

    Returns:
        The figure.
    """
    fig, ax = st.canvas(WIDTH, HEIGHT)

    st.text(ax, LEFT, HEIGHT - 26, run["label"], size=14.5, weight="bold")
    st.text(ax, LEFT, HEIGHT - 45, run["detail"], size=9.5, color=st.MUTED)

    last_step = run["rows"][-1][0]
    panel_y = HEIGHT - 45 - 22 - PANEL_H
    for index, (column, heading, tint, zero_floor) in enumerate(PANELS):
        panel_x = LEFT + index * (PANEL_W + GAP)
        st.box(ax, panel_x, panel_y, PANEL_W, PANEL_H, face=tint, edge=None)
        st.text(ax, panel_x + 14, panel_y + PANEL_H - 17, heading, size=10.5, weight="bold")

        plot = st.plot_panel(fig, WIDTH, HEIGHT, panel_x, panel_y, PANEL_W, PANEL_H)
        steps, values = _series(run, column)
        plot.plot(steps, values, color=run["color"], linewidth=1.7, solid_capstyle="round")

        plot.set_xlim(0, last_step + 1)
        plot.set_ylim(*st.nice_limits(values, zero_floor=zero_floor))
        plot.set_xlabel("GRPO step", fontsize=8.5, labelpad=2)

    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate the RL training diagnostics figures.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "figures",
        help="destination directory (default: the repository's figures/)",
    )
    args = parser.parse_args()

    for run in RUNS.values():
        for path in st.save(draw(run), run["stem"], args.out_dir):
            print(f"Wrote {path}")


if __name__ == "__main__":
    main()
