"""Shared lab-markdown prose parsing for lab_checker and lab_lint (stdlib only,
so the numpy-free lint can import it too).

decisions.md D entries are bullets that wrap across lines, so an entry runs from
its ``- D<n>`` bullet to the next bullet or heading; sentences inside end at
``.!?`` followed by whitespace.
"""

from __future__ import annotations

import re

_D_BULLET_RE = re.compile(r"^- D\d+\b", re.MULTILINE)
_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def d_entries(text: str) -> list[tuple[str, str, int]]:
    """(D id, entry text, 0-based line of the bullet) per decisions.md D entry."""
    entries = []
    bullets = list(_D_BULLET_RE.finditer(text))
    for k, m in enumerate(bullets):
        end = bullets[k + 1].start() if k + 1 < len(bullets) else len(text)
        heading = _HEADING_RE.search(text, m.start() + 1, end)
        if heading:
            end = heading.start()
        entries.append((m.group(0)[2:], text[m.start() : end], text[: m.start()].count("\n")))
    return entries


def sentences(text: str) -> list[tuple[str, int]]:
    """(sentence, 0-based offset), split at sentence enders followed by whitespace."""
    out = []
    pos = 0
    for m in _SENT_SPLIT_RE.finditer(text):
        out.append((text[pos : m.start()], pos))
        pos = m.end()
    out.append((text[pos:], pos))
    return out
