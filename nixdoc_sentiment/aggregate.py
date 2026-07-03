"""Aggregate labeled rows into a per-run metrics snapshot.

Only documentation-relevant rows count toward the indicators; the rest are
reported as ``dropped_non_relevant`` for transparency. Output keys are sorted
(via store.write_json) so identical input yields byte-identical metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _round(x: float) -> float:
    return round(x, 4)


def aggregate(labeled: list[dict], run_id: str, scheme_version: str) -> dict:
    relevant = [r for r in labeled if r.get("doc_relevant")]
    n = len(relevant)

    by_source: dict[str, int] = {}
    by_feeling: dict[str, int] = {}
    by_expectation: dict[str, int] = {}
    aspect_count: dict[str, int] = {}
    aspect_polsum: dict[str, float] = {}
    aspect_notmet: dict[str, int] = {}
    pol_sum = 0.0

    for r in relevant:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        exp = r.get("expectation", "unclear")
        by_expectation[exp] = by_expectation.get(exp, 0) + 1
        pol = float(r.get("polarity", 0.0))
        pol_sum += pol
        for f in r.get("feelings", []):
            by_feeling[f] = by_feeling.get(f, 0) + 1
        for a in r.get("aspects", []):
            aspect_count[a] = aspect_count.get(a, 0) + 1
            aspect_polsum[a] = aspect_polsum.get(a, 0.0) + pol
            if exp == "not_met":
                aspect_notmet[a] = aspect_notmet.get(a, 0) + 1

    by_aspect = {
        a: {
            "count": c,
            "mean_polarity": _round(aspect_polsum[a] / c),
            "not_met": aspect_notmet.get(a, 0),
            "not_met_rate": _round(aspect_notmet.get(a, 0) / c),
        }
        for a, c in aspect_count.items()
    }

    not_met = by_expectation.get("not_met", 0)
    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scheme_version": scheme_version,
        "total_labeled": len(labeled),
        "total_relevant": n,
        "dropped_non_relevant": len(labeled) - n,
        "mean_polarity": _round(pol_sum / n) if n else 0.0,
        "not_met_rate": _round(not_met / n) if n else 0.0,
        "by_source": by_source,
        "by_expectation": by_expectation,
        "by_feeling": by_feeling,
        "by_aspect": by_aspect,
    }
