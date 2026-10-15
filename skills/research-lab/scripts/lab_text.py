"""Shared lab-markdown prose parsing for lab_checker, lab_lint and lab_commit
(stdlib only, so the numpy-free lint can import it too).

decisions.md D entries are bullets that wrap across lines, so an entry runs from
its ``- D<n>`` bullet to the next bullet or heading; sentences inside end at
``.!?`` followed by whitespace.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def table_cells(line: str) -> list[str]:
    """Cells of one markdown table row, pipes stripped, each cell trimmed."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


_EID_RE = re.compile(r"\bE\d+\b")
_EID_RANGE_RE = re.compile(r"\bE(\d+)\s*-\s*E(\d+)\b")
_NOT_ACCEPTED_RE = re.compile(r"\b(cut|dropped|rejected|deferred)\b")
_ACCEPTED_WORD_RE = re.compile(r"\baccepted\b", re.IGNORECASE)


def accepted_ids(lab: Path) -> dict[str, tuple[Path, int]]:
    """Experiment ids the lab marks accepted -> (marker file, 1-based marker line).

    One parser for every consumer (lab_lint's accepted-entry rule, lab_commit's
    commit gate), so the two cannot disagree on what "accepted" means:
    - decisions.md: a D-entry sentence containing "accepted"; ids come from
      ``E<n>-E<m>`` ranges and bare ``E<n>`` tokens, minus a token whose next
      two words name an exclusion (cut / dropped / rejected / deferred).
    - status.md: experiment-table rows whose state cell is exactly ``[x]``.
    """
    accepted: dict[str, tuple[Path, int]] = {}
    decisions = lab / "decisions.md"
    if decisions.is_file():
        for _did, entry, first_line in d_entries(decisions.read_text()):
            for sentence, offset in sentences(entry):
                if not _ACCEPTED_WORD_RE.search(sentence):
                    continue
                line = first_line + entry[:offset].count("\n") + 1
                ids: set[str] = set()
                for m in _EID_RANGE_RE.finditer(sentence):
                    ids.update(f"E{n}" for n in range(int(m.group(1)), int(m.group(2)) + 1))
                for m in _EID_RE.finditer(sentence):
                    two_words = " ".join(sentence[m.end() :].split()[:2])
                    if not _NOT_ACCEPTED_RE.search(two_words):
                        ids.add(m.group(0))
                for eid in sorted(ids):
                    accepted.setdefault(eid, (decisions, line))
    status = lab / "status.md"
    if status.is_file():
        for i, line in enumerate(status.read_text().splitlines(), start=1):
            cells = table_cells(line)
            if len(cells) >= 4 and re.fullmatch(r"E\d+", cells[0]) and cells[3] == "[x]":
                accepted.setdefault(cells[0], (status, i))
    return accepted
