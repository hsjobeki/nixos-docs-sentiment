"""Versioned source + query configuration.

Kept in one place so that what we sample is explicit, reviewable, and stable
across runs. Changing these queries changes what the trend measures, so treat
edits here like a scheme change and note them in commit history.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ALL_SOURCES = ("hackernews", "discourse", "github", "reddit")

# Per-source query lists. HN is global, so queries are NixOS-scoped; Discourse
# (discourse.nixos.org) and Reddit (r/NixOS) are already NixOS-scoped.
QUERIES: dict[str, list[str]] = {
    "hackernews": [
        "nixos documentation", "nix documentation", "nixos docs",
        "nixos manual", "nixos wiki", "nixos learning curve",
    ],
    "discourse": [
        "documentation", "docs", "manual", "learning curve", "beginner guide",
    ],
    "reddit": [
        "documentation", "docs", "manual", "wiki", "learning curve",
    ],
    "github": [
        "documentation", "docs", "confusing", "unclear", "missing docs",
    ],
}

# nix.dev is the dedicated documentation repo -> highest signal-to-noise.
GITHUB_REPOS: list[str] = ["NixOS/nix.dev"]


@dataclass
class CollectConfig:
    sources: tuple[str, ...] = ALL_SOURCES
    max_pages: int = 2          # pages per query (100 items/page where supported)
    max_topics: int = 40        # Discourse full-topic fetches per run (bounded)
    github_repos: list[str] = field(default_factory=lambda: list(GITHUB_REPOS))
    request_delay: float = 1.0  # seconds between HTTP calls (be polite)
    user_agent: str = "nixdoc-sentiment/0.1 (research; +https://nixos.org)"

    def queries_for(self, source: str) -> list[str]:
        return QUERIES.get(source, [])
