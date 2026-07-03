"""Cross-run reporting: turn accumulated metrics snapshots into a trend view.

The metrics directory *is* the time series. This reads every snapshot, prints a
chronological indicator table, a per-aspect breakdown for the latest run, and
explicit deltas between the two most recent runs.
"""

from __future__ import annotations

from nixdoc_sentiment.store import Layout, read_json


def _load_all(layout: Layout) -> list[dict]:
    d = layout.metrics_dir()
    if not d.exists():
        return []
    files = sorted(p for p in d.iterdir() if p.is_file() and p.suffix == ".json")
    return [read_json(p) for p in files]


def _fmt_delta(cur: float, prev: float) -> str:
    d = cur - prev
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.4f}"


def format_report(layout: Layout) -> str:
    runs = _load_all(layout)
    if not runs:
        return "No metrics snapshots found. Run `nixdoc-sentiment run` first."

    lines: list[str] = []
    lines.append("NixOS documentation sentiment - trend across runs")
    lines.append("=" * 64)
    lines.append(f"{'run_id':<18} {'n':>5} {'mean_pol':>9} {'not_met':>8} {'scheme':>8}")
    lines.append("-" * 64)
    for m in runs:
        lines.append(
            f"{m['run_id']:<18} {m['total_relevant']:>5} "
            f"{m['mean_polarity']:>9.4f} {m['not_met_rate']:>8.2%} "
            f"{m['scheme_version']:>8}")

    latest = runs[-1]
    lines.append("")
    lines.append(f"Latest run {latest['run_id']} - sources: " +
                 ", ".join(f"{k}={v}" for k, v in sorted(latest["by_source"].items())))
    if latest.get("dropped_non_relevant"):
        lines.append(f"(dropped {latest['dropped_non_relevant']} non-doc-relevant "
                     f"of {latest['total_labeled']} collected)")

    lines.append("")
    lines.append("Aspect breakdown (most discussed first):")
    lines.append(f"  {'aspect':<20} {'n':>5} {'mean_pol':>9} {'not_met_rate':>13}")
    aspects = sorted(latest["by_aspect"].items(),
                     key=lambda kv: kv[1]["count"], reverse=True)
    for name, a in aspects:
        lines.append(f"  {name:<20} {a['count']:>5} {a['mean_polarity']:>9.4f} "
                     f"{a['not_met_rate']:>12.1%}")

    lines.append("")
    lines.append("Feelings:")
    for f, c in sorted(latest["by_feeling"].items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"  {f:<20} {c:>5}")

    lines.append("")
    lines.append("Expectation outcomes:")
    for e, c in sorted(latest["by_expectation"].items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"  {e:<20} {c:>5}")

    if len(runs) >= 2:
        prev = runs[-2]
        lines.append("")
        lines.append(f"Change vs previous run {prev['run_id']}:")
        lines.append(f"  mean_polarity : {_fmt_delta(latest['mean_polarity'], prev['mean_polarity'])}")
        lines.append(f"  not_met_rate  : {_fmt_delta(latest['not_met_rate'], prev['not_met_rate'])}")
        lines.append(f"  n (relevant)  : {latest['total_relevant'] - prev['total_relevant']:+d}")

    return "\n".join(lines)
