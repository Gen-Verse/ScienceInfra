"""
Shared visual grammar for every ScienceInfra figure.

Figures are laid out in a point space, not in axes fractions: `canvas()` returns
a figure whose single background axes spans `0..width` by `0..height` with
`aspect='equal'`, so a coordinate is a point on the page and a box drawn at
`(x, y, w, h)` lands exactly there. Plot panels are `add_axes` insets placed in
the same units.

Text is kept as text (`svg.fonttype='none'`) so labels stay selectable and
searchable rather than being outlined into paths.
"""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

# --- Palette -----------------------------------------------------------------
# Two categorical hues, in fixed order. Validated as a pair against a white
# surface: normal-vision dE 33.6, worst CVD dE 24.7, both above 3:1 contrast.
# Adding a third series means re-validating, not picking a hue that looks free.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
SERIES = (BLUE, ORANGE)

# Panel washes. Backgrounds only, never a series or a status.
BLUE_TINT = "#EEF4FC"
ORANGE_TINT = "#FDF1EC"

# Ink. Text wears these and never a series color, so hue only ever means identity.
INK = "#111111"
MUTED = "#6B6B6B"
LINE = "#DCDCD8"
SURFACE = "#FFFFFF"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "text.color": INK,
        "axes.edgecolor": LINE,
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "svg.fonttype": "none",
    }
)


def canvas(width: float, height: float) -> tuple[plt.Figure, plt.Axes]:
    """
    Open a figure whose coordinates are points on the page.

    Args:
        width: Canvas width in points.
        height: Canvas height in points.

    Returns:
        The figure and its background axes, spanning `0..width` by `0..height`.
    """
    fig = plt.figure(figsize=(width / 72, height / 72), facecolor=SURFACE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, width), ylim=(0, height), aspect="equal")
    ax.axis("off")
    return fig, ax


def text(
    ax: plt.Axes,
    x: float,
    y: float,
    label: str,
    *,
    size: float = 11,
    color: str = INK,
    weight: str = "normal",
    ha: str = "left",
    va: str = "center",
    zorder: float = 10,
) -> None:
    """
    Place a text run at a point.
    """
    ax.text(x, y, label, fontsize=size, color=color, fontweight=weight, ha=ha, va=va, zorder=zorder)


def text_width(label: str, size: float, *, weight: str = "normal") -> float:
    """
    Measure a text run in points, so a following run can be offset past it.

    Args:
        label: The text to measure.
        size: Font size in points.
        weight: `normal` or `bold`.

    Returns:
        The advance width in points.
    """
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath

    prop = FontProperties(family="DejaVu Sans", weight=weight)
    return TextPath((0, 0), label, size=size, prop=prop).get_extents().width


# --- Icons -------------------------------------------------------------------
# Each icon is drawn from primitives into a square of side `size` centered on
# `(x, y)`, so a caller places one the same way it places text. They are line
# drawings in a single ink, which keeps hue free to mean what it means elsewhere.


def icon_beaker(ax, x: float, y: float, *, size: float = 20, color: str = INK) -> None:
    """
    A beaker with a fill line, for the scientific codebase being repaired.
    """
    unit = size / 20
    lw = 1.3
    neck_half, body_half = 2.6 * unit, 6.2 * unit
    top, waist, base = y + 8 * unit, y + 2.5 * unit, y - 7.5 * unit
    outline = [
        (x - neck_half, top),
        (x - neck_half, waist),
        (x - body_half, base + 2 * unit),
        (x - body_half + 1.4 * unit, base),
        (x + body_half - 1.4 * unit, base),
        (x + body_half, base + 2 * unit),
        (x + neck_half, waist),
        (x + neck_half, top),
    ]
    ax.add_patch(Polygon(outline, closed=False, fill=False, edgecolor=color, linewidth=lw, zorder=11))
    # The liquid, drawn as a chord across the body rather than a filled shape.
    level = base + 3.4 * unit
    half = body_half - 0.9 * unit
    ax.plot([x - half, x + half], [level, level], color=color, linewidth=lw, zorder=11)
    for offset, rise in ((-2.2, 2.1), (1.9, 3.2)):
        ax.add_patch(Circle((x + offset * unit, level + rise * unit), 0.7 * unit, facecolor=color, edgecolor="none", zorder=11))
    ax.plot([x - neck_half - 1.1 * unit, x + neck_half + 1.1 * unit], [top, top], color=color, linewidth=lw, zorder=11)


def icon_cpu(ax, x: float, y: float, *, size: float = 20, color: str = INK) -> None:
    """
    A processor die with pins, for the compute the rollout fleet runs on.
    """
    unit = size / 20
    lw = 1.3
    half = 6.0 * unit
    ax.add_patch(
        Rectangle((x - half, y - half), half * 2, half * 2, fill=False, edgecolor=color, linewidth=lw, zorder=11)
    )
    inner = 2.6 * unit
    ax.add_patch(
        Rectangle((x - inner, y - inner), inner * 2, inner * 2, fill=False, edgecolor=color, linewidth=lw * 0.85, zorder=11)
    )
    for fraction in (-0.5, 0, 0.5):
        offset = fraction * 2 * half * 0.55
        ax.plot([x + offset, x + offset], [y + half, y + half + 2.4 * unit], color=color, linewidth=lw, zorder=11)
        ax.plot([x + offset, x + offset], [y - half, y - half - 2.4 * unit], color=color, linewidth=lw, zorder=11)
        ax.plot([x - half, x - half - 2.4 * unit], [y + offset, y + offset], color=color, linewidth=lw, zorder=11)
        ax.plot([x + half, x + half + 2.4 * unit], [y + offset, y + offset], color=color, linewidth=lw, zorder=11)


def icon_scientist(ax, x: float, y: float, *, size: float = 20, color: str = INK) -> None:
    """
    A head and shoulders, for the agent acting in the environment.
    """
    unit = size / 20
    lw = 1.3
    head_r = 3.5 * unit
    head_y = y + 3.2 * unit
    ax.add_patch(Circle((x, head_y), head_r, fill=False, edgecolor=color, linewidth=lw, zorder=11))
    # Shoulders, a half-sine sampled left to right so the bust reads as one stroke.
    span, depth, base = 7.0 * unit, 5.0 * unit, y - 7.5 * unit
    steps = 24
    points = [
        (x - span + 2 * span * (index / steps), base + depth * math.sin(math.pi * (index / steps)))
        for index in range(steps + 1)
    ]
    ax.add_patch(Polygon(points, closed=False, fill=False, edgecolor=color, linewidth=lw, zorder=11))


def icon_flask_check(ax, x: float, y: float, *, size: float = 20, color: str = INK) -> None:
    """
    A checkmark inside a rounded square, for the verifier's numerical verdict.
    """
    unit = size / 20
    lw = 1.3
    half = 6.2 * unit
    ax.add_patch(
        FancyBboxPatch(
            (x - half, y - half),
            half * 2,
            half * 2,
            boxstyle=f"round,pad=0,rounding_size={2.0 * unit}",
            fill=False,
            edgecolor=color,
            linewidth=lw,
            zorder=11,
        )
    )
    ax.plot(
        [x - 3.0 * unit, x - 0.8 * unit, x + 3.2 * unit],
        [y + 0.2 * unit, y - 2.4 * unit, y + 2.8 * unit],
        color=color,
        linewidth=lw * 1.15,
        solid_capstyle="round",
        solid_joinstyle="round",
        zorder=11,
    )


def box(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    face: str = SURFACE,
    edge: str = LINE,
    radius: float = 5,
    lw: float = 0.7,
    zorder: float = 1,
) -> None:
    """
    Draw a rounded panel with its lower-left corner at `(x, y)`.
    """
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle=f"round,pad=0,rounding_size={radius}",
            facecolor=face,
            edgecolor="none" if edge is None else edge,
            linewidth=0 if edge is None else lw,
            zorder=zorder,
        )
    )


def arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = BLUE,
    lw: float = 1.2,
    waypoints: tuple[tuple[float, float], ...] = (),
) -> None:
    """
    Draw an orthogonal connector from `start` to `end`.

    Every segment must be horizontal or vertical. Diagonals read as a different
    kind of relationship than the orthogonal flow, so they are rejected rather
    than silently drawn.

    Args:
        start: First point.
        end: Last point.
        color: Line and head color.
        lw: Line width in points.
        waypoints: Intermediate corners, in order.
    """
    points = [start, *waypoints, end]
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if abs(x1 - x0) > 0.5 and abs(y1 - y0) > 0.5:
            raise ValueError(f"Arrow segment is diagonal: {(x0, y0)} to {(x1, y1)}. Add a waypoint.")
    for (x0, y0), (x1, y1) in zip(points, points[1:-1], strict=False):
        ax.plot([x0, x1], [y0, y1], color=color, linewidth=lw, solid_capstyle="round", zorder=5)
    ax.add_patch(
        FancyArrowPatch(
            points[-2],
            points[-1],
            arrowstyle="-|>",
            mutation_scale=9,
            color=color,
            linewidth=lw,
            shrinkA=0,
            shrinkB=0,
            zorder=5,
        )
    )


def plot_panel(
    fig: plt.Figure,
    width: float,
    height: float,
    x: float,
    y: float,
    panel_w: float,
    panel_h: float,
    *,
    pad_left: float = 38,
    pad_bottom: float = 32,
    pad_right: float = 12,
    pad_top: float = 30,
) -> plt.Axes:
    """
    Add a transparent plot axes inset into a panel drawn in point space.

    Args:
        fig: The figure the panel belongs to.
        width: Canvas width in points.
        height: Canvas height in points.
        x: Panel lower-left x, in points.
        y: Panel lower-left y, in points.
        panel_w: Panel width in points.
        panel_h: Panel height in points.
        pad_left: Gutter reserved for the y tick labels.
        pad_bottom: Gutter reserved for the x tick labels.
        pad_right: Right inset, keeping the last mark off the panel edge.
        pad_top: Top inset, reserving room for the panel heading.

    Returns:
        The plot axes, with a transparent face and recessive spines.
    """
    ax = fig.add_axes(
        [
            (x + pad_left) / width,
            (y + pad_bottom) / height,
            (panel_w - pad_left - pad_right) / width,
            (panel_h - pad_bottom - pad_top) / height,
        ]
    )
    ax.set_facecolor("none")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)
        ax.spines[side].set_linewidth(0.7)
    ax.tick_params(labelsize=8.5, length=2.5, width=0.7, pad=2, colors=MUTED)
    ax.grid(True, color=LINE, linewidth=0.5, alpha=0.8)
    ax.set_axisbelow(True)
    return ax


def nice_limits(values, *, pad: float = 0.10, zero_floor: bool = False) -> tuple[float, float]:
    """
    Round an axis range outward to readable bounds.

    Args:
        values: The series values the axis must contain.
        pad: Fraction of the span to add on each side before rounding.
        zero_floor: Clamp the lower bound at zero, for quantities that cannot
            go negative and read wrong when the axis implies they could.

    Returns:
        The lower and upper bound.
    """
    low, high = min(values), max(values)
    span = high - low or abs(high) or 1.0
    low -= span * pad
    high += span * pad
    if zero_floor:
        low = max(0.0, low)
    step = 10.0 ** (len(str(int(abs(high) or 1))) - 1)
    while (high - low) / step < 3:
        step /= 2
    return (low // step) * step, -(-high // step) * step


def save(fig: plt.Figure, stem: str, out_dir, *, formats=("svg", "png"), dpi: int = 160) -> list:
    """
    Write the figure and assert nothing escaped the canvas.

    No outer frame is drawn. The figure is trusted to read as a composition of
    its own panels against the page, so a border would only box it in.

    Args:
        fig: The figure to write.
        stem: Filename without an extension.
        out_dir: Destination directory, created if absent.
        formats: Extensions to write.
        dpi: Raster resolution, applied to `png` only.

    Returns:
        The paths written.
    """
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    background = fig.axes[0]
    x_lo, x_hi = background.get_xlim()
    y_lo, y_hi = background.get_ylim()
    for artist in background.texts:
        x, y = artist.get_position()
        if not (x_lo <= x <= x_hi and y_lo <= y <= y_hi):
            raise ValueError(f"Text escapes the canvas at {(x, y)}: {artist.get_text()!r}.")

    written = []
    for extension in formats:
        path = out_dir / f"{stem}.{extension}"
        fig.savefig(path, dpi=dpi, facecolor=SURFACE)
        written.append(path)
    plt.close(fig)
    return written
