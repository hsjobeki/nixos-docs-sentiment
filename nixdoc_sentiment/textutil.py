"""Deterministic text cleaning: HTML/entity stripping + whitespace collapse."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_WS = re.compile(r"\s+")


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def clean_text(raw: str | None) -> str:
    """Return plain text: strip HTML tags, unescape entities, collapse spaces.

    Non-HTML input (e.g. Markdown issue bodies) passes through tag-free; we only
    invoke the parser when angle brackets are present so plain text is untouched.
    """
    if not raw:
        return ""
    s = raw
    if "<" in s and ">" in s:
        p = _Stripper()
        try:
            p.feed(s)
            p.close()
            s = p.text()
        except Exception:
            # Malformed HTML: fall back to the raw string rather than losing data.
            pass
    s = html.unescape(s)
    return _WS.sub(" ", s).strip()
