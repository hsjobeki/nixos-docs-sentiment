"""Deterministic classifier: Record -> labeled row (dict).

Pure and offline. Given identical input and ``SCHEME_VERSION`` it always
produces byte-identical output, which is what makes cross-run comparison valid.
"""

from __future__ import annotations

import re

from nixdoc_sentiment import categories as C
from nixdoc_sentiment.schema import Record

_CLAUSE = re.compile(r"[.;:!?]")
_WINDOW = 28  # chars of preceding context checked for a negation/conditional


def _clean_hit(rx: re.Pattern[str], text: str) -> bool:
    """True if rx matches at least once with no suppressor just before it.

    Negation/conditional words (categories.SUPPRESSORS) within the same clause
    and a short window suppress that occurrence, so "not helpful" / "would love"
    do not count. A cue counts if it has any clean (unsuppressed) occurrence.
    """
    for m in rx.finditer(text):
        pre = text[max(0, m.start() - _WINDOW):m.start()]
        pre = _CLAUSE.split(pre)[-1]  # only the current clause precedes the cue
        if C.CONTRACTION_NEG.search(pre) or any(s.search(pre) for _, s in C.SUPPRESSORS):
            continue
        return True
    return False


def _match_map(compiled, text: str, suppress: bool = False):
    # suppress=True for feelings (negation-sensitive); False for aspects, where
    # "no examples"/"not documented" are still legitimately *about* that aspect.
    hits: list[str] = []
    cues: dict[str, list[str]] = {}
    for cat, terms in compiled.items():
        matched = [t for t, rx in terms
                   if (_clean_hit(rx, text) if suppress else rx.search(text))]
        if matched:
            hits.append(cat)
            cues[cat] = matched
    return sorted(hits), cues


def score_polarity(text: str) -> tuple[float, dict[str, list[str]]]:
    pos = [t for t, rx in C.POSITIVE if _clean_hit(rx, text)]
    neg = [t for t, rx in C.NEGATIVE if _clean_hit(rx, text)]
    n = len(pos) + len(neg)
    polarity = 0.0 if n == 0 else round((len(pos) - len(neg)) / n, 4)
    return polarity, {"positive": pos, "negative": neg}


def infer_expectation(text: str, feelings: list[str], polarity: float,
                      aspects: list[str]) -> str:
    if any(rx.search(text) for _, rx in C.EXCEEDED):
        return "exceeded"
    neg_feel = any(f in feelings for f in C.NEGATIVE_FEELINGS)
    pos_feel = any(f in feelings for f in C.POSITIVE_FEELINGS)
    not_met_cue = any(rx.search(text) for _, rx in C.NOT_MET)
    met_cue = any(rx.search(text) for _, rx in C.MET)

    if not_met_cue or polarity <= -0.2 or (neg_feel and polarity < 0):
        return "not_met"
    if met_cue or (pos_feel and polarity >= 0.2):
        return "met"
    if "onboarding" in aspects and polarity == 0.0 and not neg_feel:
        return "no_baseline"
    return "unclear"


def _doc_relevant(text: str, aspects: list[str]) -> bool:
    if aspects:
        return True
    return any(rx.search(text) for _, rx in C.DOC)


def classify_record(rec: Record) -> dict:
    text = f"{rec.title or ''}\n{rec.text}".lower()
    aspects, aspect_cues = _match_map(C.ASPECTS, text)
    feelings, feeling_cues = _match_map(C.FEELINGS, text, suppress=True)
    polarity, polarity_cues = score_polarity(text)
    expectation = infer_expectation(text, feelings, polarity, aspects)
    return {
        **rec.as_dict(),
        "doc_relevant": _doc_relevant(text, aspects),
        "aspects": aspects,
        "feelings": feelings,
        "expectation": expectation,
        "polarity": polarity,
        "cues": {
            "aspects": aspect_cues,
            "feelings": feeling_cues,
            "polarity": polarity_cues,
        },
        "scheme_version": C.SCHEME_VERSION,
    }
