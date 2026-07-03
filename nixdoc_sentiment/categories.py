"""Versioned category scheme + lexicons for the deterministic classifier.

Why a transparent lexicon instead of an ML/LLM model?
-----------------------------------------------------
The whole point of this tool is to re-run it in a few months and compare. That
only produces valid trends if the *measurement instrument* is stable. A hosted
LLM drifts (model updates, non-determinism); a lexicon does not. Every label
here is explainable ("these cue words fired") and byte-reproducible.

When you change the scheme, bump ``SCHEME_VERSION`` (semver). It is stamped into
every labeled row and every metrics file, so a reader can tell whether two runs
are comparable or were produced by different instruments.

Three orthogonal axes are coded per record:
  1. aspect      -- which facet of the docs the feedback is about
  2. feeling     -- emotional tone
  3. expectation -- met / not_met / exceeded / no_baseline / unclear
plus a signed polarity score in [-1, 1].
"""

from __future__ import annotations

import re

SCHEME_VERSION = "1.1.0"

# --- Axis 1: documentation aspect ------------------------------------------
# What the sentiment is *about*. A record may match several aspects.
ASPECT_TERMS: dict[str, list[str]] = {
    "discoverability": [
        "can't find", "cant find", "couldn't find", "couldnt find", "hard to find",
        "hard to locate", "where is it documented", "no mention", "buried",
        "not documented anywhere", "impossible to find",
    ],
    "completeness": [
        "incomplete", "missing", "not documented", "undocumented", "lacks documentation",
        "sparse", "gaps", "doesn't cover", "does not cover", "no docs for",
        "no documentation for", "coverage", "half-documented",
    ],
    "accuracy": [
        "outdated", "out of date", "stale", "no longer works", "deprecated",
        "doesn't match", "does not match", "contradict", "wrong", "incorrect",
    ],
    "onboarding": [
        "beginner", "newcomer", "getting started", "learning curve", "steep",
        "onboarding", "new user", "first time", "as a newbie", "newbie",
    ],
    "explanation": [
        "mental model", "conceptual", "explanation", "explain", "how it works",
        "rationale", "makes no sense", "the why", "understand why", "no context",
    ],
    "examples": [
        "example", "examples", "sample", "recipe", "copy paste", "copy-paste",
        "snippet", "real world", "real-world", "practical",
    ],
    "structure": [
        "fragmented", "scattered", "organization", "organisation", "navigation",
        "navigate", "all over the place", "split across", "nix.dev", "wiki",
        "manual", "manuals", "hard to navigate",
    ],
    "search": [
        "search", "searching", "unsearchable", "can't search", "google it",
        "search options", "option search",
    ],
    "unofficial_reliance": [
        "wrote my own", "own notes", "unofficial", "third party", "third-party",
        "someone's blog", "a blog post", "reddit", "discord", "had to ask",
        "community wiki", "external resource",
    ],
    "tooling": [
        "flake", "flakes", "nix command", "man page", "manpage", "home-manager",
        "nix-env", "cli docs", "options.html", "option documentation",
    ],
}

# --- Axis 2: feeling --------------------------------------------------------
FEELING_TERMS: dict[str, list[str]] = {
    "frustration": [
        "frustrat", "annoy", "infuriat", "painful", "a pain", "hate", "awful",
        "terrible", "nightmare", "struggle", "struggling", "fed up", "rage",
    ],
    "confusion": [
        "confus", "unclear", "don't understand", "dont understand", "no idea",
        "lost", "cryptic", "obscure", "makes no sense", "hard to understand",
        "baffl", "bewild",
    ],
    "anxiety": [
        "afraid", "scared", "intimidat", "daunting", "overwhelm", "anxious",
        "nervous", "fear of breaking",
    ],
    "resignation": [
        "gave up", "give up", "wrote my own", "not worth", "abandon",
        "ended up just", "figure it out myself", "figured it out myself",
    ],
    "relief": [
        "finally", "relief", "phew", "at last", "thankfully", "glad",
    ],
    "delight": [
        "love", "amazing", "excellent", "fantastic", "awesome", "wonderful",
        "impressed", "delight", "great docs", "best docs", "best documentation",
        "brilliant",
    ],
    "gratitude": [
        "thank", "thanks", "grateful", "appreciate", "kudos", "shout out",
        "shoutout", "hats off",
    ],
}

# --- Polarity lexicon -------------------------------------------------------
POSITIVE_TERMS: list[str] = [
    "clear", "helpful", "useful", "improved", "better", "solid", "polished",
    "comprehensive", "thorough", "well documented", "well-documented",
    "well written", "well-written", "easy to follow", "great", "good",
    "excellent", "love", "readable", "intuitive",
]
NEGATIVE_TERMS: list[str] = [
    "poor", "bad", "lacking", "worst", "difficult", "hard", "harder", "hardest",
    "impossible", "broken", "useless", "a mess", "horrible", "disappointing",
    "confusing", "frustrating", "outdated", "incomplete", "missing", "sparse",
    "cryptic", "unclear", "terrible", "awful", "painful",
]

# --- Axis 3: expectation cues ----------------------------------------------
EXCEEDED_CUES: list[str] = [
    "better than expected", "pleasantly surprised", "exceeded", "surprisingly good",
    "blown away",
]
MET_CUES: list[str] = [
    "as expected", "did the trick", "documentation helped", "docs helped",
    "found what i needed", "answered my question", "well documented",
    "well-documented",
]
NOT_MET_CUES: list[str] = [
    "expected", "should be documented", "should have", "wish there was",
    "wish it was", "let down", "disappoint", "but there's no", "but there is no",
    "no docs", "not documented", "left me", "had to guess",
]

# --- Documentation-relevance gate ------------------------------------------
# Used to drop off-topic records (e.g. HN comments in a release thread that
# never touch the docs). Aspect matches also imply relevance.
DOC_TERMS: list[str] = [
    "document", "docs", "manual", "manuals", "wiki", "tutorial", "guide",
    "nix.dev", "readme", "man page", "manpage", "learning", "how-to", "howto",
    "reference", "options search", "handbook",
]

# --- Negation / conditional suppressors ------------------------------------
# A cue is ignored when one of these appears just before it in the same clause,
# so "not helpful" is not counted as positive and "would love" (a wish) is not
# counted as delight. Applied to feeling and polarity matching. This is a small
# window heuristic, not full parsing: it fixes the common cases, not all of them.
SUPPRESSOR_TERMS: list[str] = [
    "not", "no", "never", "without", "hardly", "cannot", "lacks", "lack of",
    "would", "wish", "hope", "should", "rather than", "instead of",
]


# Ambiguous common tokens matched whole-word (both boundaries) instead of as a
# prefix, so "manual" does not catch "manually" and "hard" does not catch
# "hardware"/"hardly". Unambiguous stems (manuals, harder, hardest) are listed
# explicitly to preserve recall.
EXACT_WORD = frozenset({"manual", "hard"})


def _compile(term: str) -> re.Pattern[str]:
    # Bare alnum tokens default to left-boundary prefix match. This acts as a
    # cheap stemmer -- "document" matches documentation/documented/documents --
    # while still requiring a word start, so "docs" does not match "docker".
    # Terms in EXACT_WORD require both boundaries; phrases match as substrings.
    if re.fullmatch(r"[a-z0-9]+", term):
        boundary = r"\b" if term in EXACT_WORD else ""
        return re.compile(r"\b" + re.escape(term) + boundary)
    return re.compile(re.escape(term))


def _compile_map(m: dict[str, list[str]]) -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    return {cat: [(t, _compile(t)) for t in terms] for cat, terms in m.items()}


def _compile_list(terms: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    return [(t, _compile(t)) for t in terms]


ASPECTS = _compile_map(ASPECT_TERMS)
FEELINGS = _compile_map(FEELING_TERMS)
POSITIVE = _compile_list(POSITIVE_TERMS)
NEGATIVE = _compile_list(NEGATIVE_TERMS)
EXCEEDED = _compile_list(EXCEEDED_CUES)
MET = _compile_list(MET_CUES)
NOT_MET = _compile_list(NOT_MET_CUES)
DOC = _compile_list(DOC_TERMS)
SUPPRESSORS = _compile_list(SUPPRESSOR_TERMS)
# Contraction negators (isn't, wouldn't, don't, ...): match the "n't" tail.
CONTRACTION_NEG = re.compile(r"n't\b")

NEGATIVE_FEELINGS = ("frustration", "confusion", "anxiety", "resignation")
POSITIVE_FEELINGS = ("relief", "delight", "gratitude")
