"""Normalized data contract shared across every pipeline stage.

A ``Record`` is the unit of analysis: one piece of human-written feedback
(a forum post, comment, or issue) reduced to source-independent fields.
Collectors produce ``Record``s; the classifier consumes them and emits labeled
rows (plain dicts) that carry every ``Record`` field plus the label axes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class Record:
    id: str            # globally unique: "<source>:<native_id>"
    source: str        # hackernews | discourse | github | reddit
    native_id: str     # id within the source
    url: str           # permalink to the item
    created_utc: str   # ISO-8601 timestamp, e.g. 2025-12-01T02:23:12Z
    author: str | None
    title: str | None  # thread/story/issue title providing context
    text: str          # cleaned plain-text body
    query: str         # which query surfaced it (collection provenance)

    def as_dict(self) -> dict:
        return asdict(self)


_RECORD_FIELDS = tuple(f.name for f in fields(Record))


def record_from_dict(d: dict) -> Record:
    return Record(**{k: d[k] for k in _RECORD_FIELDS})
