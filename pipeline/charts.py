"""Standalone SVG charts, each carrying its source inside the image.

Every chart is written to its own file under ``_site/charts/`` and embedded on the
page with an ``<img>``, so an outlet that screenshots or saves it takes the credit
line with it. There is no plotting library: the SVG is written out directly, which
keeps the nightly build dependency-free and puts the credit exactly where it has to
be. The internal stylesheet carries its own dark-mode steps, so a chart embedded as
an image still follows the reader's theme.

Conventions, applied to every chart here: one series, so no legend (the title says
what is plotted); columns capped at 24px with a 4px rounded cap and a square foot on
the baseline; hairline gridlines a step off the surface; axis and value text in ink,
never in the series colour; a value printed only where it carries the story (the
tallest column) rather than on every mark; and a zero baseline always.
"""
from __future__ import annotations

import html
import math
from dataclasses import dataclass

# Surface, ink and series steps, chosen to match static/style.css in both modes.
LIGHT = {"surface": "#f6f6f2", "ink": "#1e2522", "muted": "#5a645e", "grid": "#d3d8d1", "series": "#0b5d3b"}
DARK = {"surface": "#151a17", "ink": "#e7eae5", "muted": "#a3aca6", "grid": "#2f3933", "series": "#6cc79b"}
FONT = '"Public Sans", system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif'

BAR_CAP = 24      # never thicker, however wide the band
RADIUS = 4        # rounded data-end
TICKS = 4


@dataclass(frozen=True)
class Chart:
    """A rendered chart and its intrinsic size, so the page can reserve the space."""
    svg: str
    width: int
    height: int


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _nice(top: float, ticks: int = TICKS) -> tuple[int, int]:
    """A clean axis maximum at or above ``top``, and its step."""
    if top <= 0:
        return 1, 1
    raw = top / ticks
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for mult in (1, 2, 2.5, 5, 10):
        step = mult * mag
        if step >= raw:
            break
    step = max(1, int(round(step)))
    return int(math.ceil(top / step) * step), step


def _fmt(n: float) -> str:
    return f"{int(round(n)):,}"


def _style() -> str:
    rules = [
        f"text{{font-family:{FONT};}}",
        ".bg{fill:%s;}" % LIGHT["surface"],
        ".ink{fill:%s;}" % LIGHT["ink"],
        ".mut{fill:%s;}" % LIGHT["muted"],
        ".grid{stroke:%s;stroke-width:1;}" % LIGHT["grid"],
        ".axis{stroke:%s;stroke-width:1;}" % LIGHT["muted"],
        ".bar{fill:%s;}" % LIGHT["series"],
        ".ttl{font-size:21px;font-weight:600;}",
        ".sub{font-size:13.5px;}",
        ".tick{font-size:12px;}",
        ".val{font-size:13px;font-weight:600;}",
        ".cred{font-size:12px;}",
        ".cred-site{font-size:12px;font-weight:600;}",
        "@media (prefers-color-scheme: dark){",
        ".bg{fill:%s;}" % DARK["surface"],
        ".ink{fill:%s;}" % DARK["ink"],
        ".mut{fill:%s;}" % DARK["muted"],
        ".grid{stroke:%s;}" % DARK["grid"],
        ".axis{stroke:%s;}" % DARK["muted"],
        ".bar{fill:%s;}" % DARK["series"],
        "}",
    ]
    return "".join(rules)


def _column_path(x: float, y: float, w: float, h: float) -> str:
    """A column with a rounded cap and a square foot on the baseline."""
    r = min(RADIUS, w / 2, h)
    if h <= 0.5:
        return ""
    if r <= 0.5:
        return f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>'
    d = (
        f"M{x:.1f},{y + h:.1f}V{y + r:.1f}"
        f"A{r:.1f},{r:.1f} 0 0 1 {x + r:.1f},{y:.1f}"
        f"H{x + w - r:.1f}"
        f"A{r:.1f},{r:.1f} 0 0 1 {x + w:.1f},{y + r:.1f}"
        f"V{y + h:.1f}Z"
    )
    return f'<path class="bar" d="{d}"/>'


def _bar_path(x: float, y: float, w: float, h: float) -> str:
    """A horizontal bar: square foot on the axis, rounded tip."""
    r = min(RADIUS, h / 2, w)
    if w <= 0.5:
        return ""
    if r <= 0.5:
        return f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>'
    d = (
        f"M{x:.1f},{y:.1f}H{x + w - r:.1f}"
        f"A{r:.1f},{r:.1f} 0 0 1 {x + w:.1f},{y + r:.1f}"
        f"V{y + h - r:.1f}"
        f"A{r:.1f},{r:.1f} 0 0 1 {x + w - r:.1f},{y + h:.1f}"
        f"H{x:.1f}Z"
    )
    return f'<path class="bar" d="{d}"/>'


def _frame(width: int, height: int, title: str, subtitle: str, desc: str, body: str, credit_site: str, credit_right: str) -> str:
    rule_y = height - 40
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-labelledby="t d" preserveAspectRatio="xMidYMid meet">'
        f'<title id="t">{_esc(title)}</title><desc id="d">{_esc(desc)}</desc>'
        f"<style>{_style()}</style>"
        f'<rect class="bg" width="{width}" height="{height}"/>'
        f'<text class="ttl ink" x="20" y="30">{_esc(title)}</text>'
        f'<text class="sub mut" x="20" y="54">{_esc(subtitle)}</text>'
        f"{body}"
        f'<line class="grid" x1="20" y1="{rule_y}" x2="{width - 20}" y2="{rule_y}" shape-rendering="crispEdges"/>'
        f'<text class="cred-site ink" x="20" y="{height - 18}">{_esc(credit_site)}</text>'
        f'<text class="cred mut" x="{width - 20}" y="{height - 18}" text-anchor="end">{_esc(credit_right)}</text>'
        "</svg>"
    )


def columns(labels: list[str], values: list[float], *, title: str, subtitle: str, credit_site: str, credit_right: str,
            width: int = 960, height: int = 460, y_unit: str = "") -> str:
    """A column chart over time. One series, zero baseline, the peak labelled."""
    n = max(1, len(values))
    left, right = 56, width - 20
    top, floor_y = 86, height - 70
    plot_h = floor_y - top
    top_val, step = _nice(max(values) if values else 0)
    band = (right - left) / n
    bar_w = min(BAR_CAP, max(2.0, band - 2))
    peak = max(range(len(values)), key=lambda i: values[i]) if values else -1

    out: list[str] = []
    # Gridlines above the baseline, with their tick values.
    k = step
    while k <= top_val:
        y = floor_y - (k / top_val) * plot_h
        out.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" shape-rendering="crispEdges"/>')
        out.append(f'<text class="tick mut" x="{left - 10}" y="{y:.1f}" text-anchor="end" dominant-baseline="middle">{_fmt(k)}</text>')
        k += step
    out.append(f'<text class="tick mut" x="{left - 10}" y="{floor_y:.1f}" text-anchor="end" dominant-baseline="middle">0</text>')
    out.append(f'<line class="axis" x1="{left}" y1="{floor_y}" x2="{right}" y2="{floor_y}" shape-rendering="crispEdges"/>')

    # Label every nth category so the axis never collides with itself.
    every = 1 if n <= 14 else (2 if n <= 28 else max(1, n // 12))
    for i, (label, v) in enumerate(zip(labels, values)):
        h = (v / top_val) * plot_h if top_val else 0
        x = left + i * band + (band - bar_w) / 2
        out.append(_column_path(x, floor_y - h, bar_w, h))
        if i % every == 0 or i == n - 1:
            out.append(f'<text class="tick mut" x="{x + bar_w / 2:.1f}" y="{floor_y + 20}" text-anchor="middle">{_esc(label)}</text>')
        if i == peak and v > 0:
            out.append(f'<text class="val ink" x="{x + bar_w / 2:.1f}" y="{floor_y - h - 8:.1f}" text-anchor="middle">{_fmt(v)}</text>')

    total = _fmt(sum(values))
    unit = y_unit or "items"
    desc = f"Column chart. {total} {unit} in total across {n} periods, from {labels[0] if labels else ''} to {labels[-1] if labels else ''}; the highest is {_fmt(max(values) if values else 0)}."
    return Chart(_frame(width, height, title, subtitle, desc, "".join(out), credit_site, credit_right), width, height)


def bars(labels: list[str], values: list[float], *, title: str, subtitle: str, credit_site: str, credit_right: str,
         width: int = 960, label_width: int = 232, y_unit: str = "") -> Chart:
    """A horizontal bar chart by category, longest first, value at each tip."""
    n = max(1, len(values))
    row = 28.0
    thickness = 18.0
    top = 86
    height = int(top + n * row + 70)
    left = label_width
    right = width - 64            # room for the value at the tip
    top_val, step = _nice(max(values) if values else 0)
    label_font = 13 if max((len(x) for x in labels), default=0) <= 26 else 12

    out: list[str] = []
    k = step
    while k <= top_val:
        x = left + (k / top_val) * (right - left)
        out.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{top + n * row:.1f}" shape-rendering="crispEdges"/>')
        out.append(f'<text class="tick mut" x="{x:.1f}" y="{top - 18}" text-anchor="middle">{_fmt(k)}</text>')
        k += step
    out.append(f'<line class="axis" x1="{left}" y1="{top - 10}" x2="{left}" y2="{top + n * row:.1f}" shape-rendering="crispEdges"/>')

    for i, (label, v) in enumerate(zip(labels, values)):
        y = top + i * row + (row - thickness) / 2
        w = (v / top_val) * (right - left) if top_val else 0
        out.append(f'<text class="tick mut" x="{left - 12}" y="{y + thickness / 2:.1f}" text-anchor="end" dominant-baseline="middle" style="font-size:{label_font}px">{_esc(label)}</text>')
        out.append(_bar_path(left, y, w, thickness))
        out.append(f'<text class="val ink" x="{left + w + 8:.1f}" y="{y + thickness / 2:.1f}" dominant-baseline="middle">{_fmt(v)}</text>')

    unit = y_unit or "items"
    top_label = labels[0] if labels else ""
    desc = f"Horizontal bar chart of {n} categories. The largest is {top_label} with {_fmt(max(values) if values else 0)} {unit}."
    return Chart(_frame(width, height, title, subtitle, desc, "".join(out), credit_site, credit_right), width, height)
