#!/usr/bin/env python3
"""Render lexicon-vs-LLM comparison charts as dependency-free SVG.

Reads a comparison artifact written by the analysis step
(``data/compare/<run>.json``, containing the ``lexicon`` and ``llm`` aggregate
metrics) and emits three SVGs under ``docs/charts/``:

  radar_feelings.svg    emotional profile (7 axes)
  radar_aspects.svg     documentation-aspect profile (10 axes)
  bar_expectation.svg   expectation outcomes (grouped bars)

Standard library only, so it stays reproducible and needs nothing installed.
Charts use a white card background so they render on light and dark GitHub.
"""

from __future__ import annotations

import json
import math
import os
import sys

LEX = "#4E79A7"   # blue  - lexicon
LLM = "#E15759"   # red   - LLM
GRID = "#d0d0d0"
INK = "#222222"
MUTE = "#666666"

FEELING_AXES = ["frustration", "confusion", "anxiety", "resignation",
                "relief", "delight", "gratitude"]
ASPECT_AXES = ["completeness", "discoverability", "accuracy", "onboarding",
               "explanation", "examples", "structure", "search",
               "unofficial_reliance", "tooling"]
EXPECT_ORDER = ["not_met", "unclear", "met", "no_baseline", "exceeded"]


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def feeling_ratios(m: dict) -> dict:
    n = m["total_relevant"] or 1
    return {k: m["by_feeling"].get(k, 0) / n for k in FEELING_AXES}


def aspect_ratios(m: dict) -> dict:
    n = m["total_relevant"] or 1
    return {k: m["by_aspect"].get(k, {}).get("count", 0) / n for k in ASPECT_AXES}


def expect_ratios(m: dict) -> dict:
    n = m["total_relevant"] or 1
    return {k: m["by_expectation"].get(k, 0) / n for k in EXPECT_ORDER}


def _nice_max(v: float, step: int = 10) -> int:
    return max(step, int(math.ceil(v * 100 / step) * step))


def radar_svg(title: str, meta: str, caption: str, axes: list[str],
              lex: dict, llm: dict) -> str:
    W, H = 740, 640
    cx, cy, R = 370, 330, 200
    top = -math.pi / 2
    n = len(axes)
    maxpct = _nice_max(max(max(lex.values()), max(llm.values())))

    def pt(i: int, frac: float) -> tuple[float, float]:
        a = top + i * 2 * math.pi / n
        return cx + R * frac * math.cos(a), cy + R * frac * math.sin(a)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" font-family="Segoe UI,Helvetica,Arial,sans-serif">',
        f'<rect x="0" y="0" width="{W}" height="{H}" rx="14" fill="#ffffff"/>',
        f'<text x="{cx}" y="32" text-anchor="middle" font-size="20" '
        f'font-weight="700" fill="{INK}">{_esc(title)}</text>',
        f'<text x="{cx}" y="52" text-anchor="middle" font-size="13" '
        f'fill="{INK}">{_esc(caption)}</text>',
        f'<text x="{cx}" y="70" text-anchor="middle" font-size="11" '
        f'fill="{MUTE}">{_esc(meta)}</text>',
    ]

    # concentric rings + ring % labels on the top axis
    for val in range(10, maxpct + 1, 10):
        frac = val / maxpct
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, frac) for i in range(n)))
        parts.append(f'<polygon points="{poly}" fill="none" stroke="{GRID}" stroke-width="1"/>')
        tx, ty = pt(0, frac)
        parts.append(f'<text x="{tx+4:.0f}" y="{ty-2:.0f}" font-size="9" '
                     f'fill="{MUTE}">{val}%</text>')

    # spokes + axis labels
    for i, name in enumerate(axes):
        ex, ey = pt(i, 1.0)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        lx, ly = pt(i, 1.14)
        a = top + i * 2 * math.pi / n
        anchor = "middle" if abs(math.cos(a)) < 0.3 else ("start" if math.cos(a) > 0 else "end")
        parts.append(f'<text x="{lx:.1f}" y="{ly+4:.1f}" text-anchor="{anchor}" '
                     f'font-size="12" fill="{INK}">{_esc(name)}</text>')

    # series polygons (lexicon under, LLM on top)
    for data, color in ((lex, LEX), (llm, LLM)):
        poly = " ".join(f"{x:.1f},{y:.1f}"
                        for x, y in (pt(i, data[axes[i]] * 100 / maxpct) for i in range(n)))
        parts.append(f'<polygon points="{poly}" fill="{color}" fill-opacity="0.18" '
                     f'stroke="{color}" stroke-width="2.5"/>')
        for i in range(n):
            x, y = pt(i, data[axes[i]] * 100 / maxpct)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')

    # legend
    ly = H - 24
    parts.append(f'<rect x="{cx-196}" y="{ly-12}" width="14" height="14" rx="3" fill="{LEX}" fill-opacity="0.6" stroke="{LEX}"/>')
    parts.append(f'<text x="{cx-176}" y="{ly}" font-size="13" fill="{INK}">lexicon (keyword)</text>')
    parts.append(f'<rect x="{cx+40}" y="{ly-12}" width="14" height="14" rx="3" fill="{LLM}" fill-opacity="0.6" stroke="{LLM}"/>')
    parts.append(f'<text x="{cx+60}" y="{ly}" font-size="13" fill="{INK}">LLM (sub-agents)</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def bar_svg(title: str, meta: str, caption: str, cats: list[str],
            lex: dict, llm: dict) -> str:
    W, H = 640, 392
    left, right, top = 160, 60, 108
    plot_w = W - left - right
    maxpct = _nice_max(max(max(lex.values()), max(llm.values())))
    rows = len(cats)
    row_h = (H - top - 40) / rows
    bh = row_h * 0.32

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" font-family="Segoe UI,Helvetica,Arial,sans-serif">',
        f'<rect x="0" y="0" width="{W}" height="{H}" rx="14" fill="#ffffff"/>',
        f'<text x="{W//2}" y="30" text-anchor="middle" font-size="20" '
        f'font-weight="700" fill="{INK}">{_esc(title)}</text>',
        f'<text x="{W//2}" y="50" text-anchor="middle" font-size="13" '
        f'fill="{INK}">{_esc(caption)}</text>',
        f'<text x="{W//2}" y="68" text-anchor="middle" font-size="11" '
        f'fill="{MUTE}">{_esc(meta)}</text>',
    ]
    # x gridlines
    for val in range(0, maxpct + 1, 10):
        x = left + plot_w * val / maxpct
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{H-40}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{H-24}" text-anchor="middle" '
                     f'font-size="10" fill="{MUTE}">{val}%</text>')

    for r, cat in enumerate(cats):
        yc = top + r * row_h + row_h / 2
        parts.append(f'<text x="{left-10}" y="{yc+4:.1f}" text-anchor="end" '
                     f'font-size="13" fill="{INK}">{_esc(cat)}</text>')
        for data, color, off in ((lex, LEX, -bh - 1), (llm, LLM, 1)):
            w = plot_w * data[cat] * 100 / maxpct
            y = yc + off
            parts.append(f'<rect x="{left}" y="{y:.1f}" width="{w:.1f}" height="{bh:.1f}" '
                         f'rx="2" fill="{color}"/>')
            parts.append(f'<text x="{left+w+5:.1f}" y="{y+bh-1:.1f}" font-size="10" '
                         f'fill="{MUTE}">{data[cat]*100:.0f}%</text>')

    ly = 90
    parts.append(f'<rect x="{left}" y="{ly-12}" width="13" height="13" rx="3" fill="{LEX}"/>')
    parts.append(f'<text x="{left+18}" y="{ly}" font-size="12" fill="{INK}">lexicon</text>')
    parts.append(f'<rect x="{left+90}" y="{ly-12}" width="13" height="13" rx="3" fill="{LLM}"/>')
    parts.append(f'<text x="{left+108}" y="{ly}" font-size="12" fill="{INK}">LLM</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else None
    if not path:
        d = "data/compare"
        files = sorted(f for f in os.listdir(d)) if os.path.isdir(d) else []
        if not files:
            print("no data/compare/*.json found; run the comparison first", file=sys.stderr)
            return 1
        path = os.path.join(d, files[-1])
    blob = json.load(open(path))
    lex, llm = blob["lexicon"], blob["llm"]
    run = blob["run"]
    meta = (f"N_lexicon={lex['total_relevant']}  ·  N_llm={llm['total_relevant']}"
            f"  ·  snapshot {run}  (Hacker News + NixOS Discourse)")

    os.makedirs("docs/charts", exist_ok=True)
    outs = {
        "docs/charts/radar_feelings.svg": radar_svg(
            "Emotional profile: lexicon vs LLM", meta,
            "% of doc-relevant records expressing each feeling (multi-label)",
            FEELING_AXES, feeling_ratios(lex), feeling_ratios(llm)),
        "docs/charts/radar_aspects.svg": radar_svg(
            "Documentation-aspect profile: lexicon vs LLM", meta,
            "% of doc-relevant records that discuss each facet — higher = talked about more, not better",
            ASPECT_AXES, aspect_ratios(lex), aspect_ratios(llm)),
        "docs/charts/bar_expectation.svg": bar_svg(
            "Expectation outcomes: lexicon vs LLM", meta,
            "% of doc-relevant records by whether the docs met expectations",
            EXPECT_ORDER, expect_ratios(lex), expect_ratios(llm)),
    }
    for p, svg in outs.items():
        with open(p, "w", encoding="utf-8") as f:
            f.write(svg + "\n")
        print("wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
