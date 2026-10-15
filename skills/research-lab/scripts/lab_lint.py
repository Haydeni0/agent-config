# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Lab-wide lint for a research-lab directory. The heartbeat runs it each beat
(SKILL.md, Start step 6); stdlib only.

Rules (each answers a pilot incident):

- ``future-stamp`` (T3): a timestamp in a lab markdown/JSONL line later than the
  file's mtime + 2 min was projected, not read from ``date``. Checked stamps:
  ISO datetimes (``YYYY-MM-DD HH:MM[:SS]`` or with ``T``) always; bare
  ``HH:MM[:SS]`` only when the file carries today's ISO date (the date context);
  date-only strings are skipped - the milestone ``by`` column and labelled ETAs
  are planned dates, not event stamps. A stamp is exempt when its clause marks
  it as planned: ``deadline|due|by|until|eta|cap|target|window|gate|before|next``
  or ``at the latest`` within the previous ~4 words, or it sits in a table
  column headed ``by``/``eta``. ``by`` must be adjacent (last 2 words) - it is
  agentive in "launched by author-2 at 16:39", which would otherwise exempt a
  real projection.
- ``status`` (SKILL.md, Start step 3): ``status.md`` line 1 is a one-line state (not a
  heading, not a table row), and the milestone table ``| by | milestone |
  state |`` and experiment table ``| id | question | tier | state | budget |
  eta |`` are present.
- ``audit-event`` (templates/audit-log.md): every audit/log.md table-row Event
  is inside the template's fixed vocabulary, so D28 measures and D32
  budget-vs-actual stay grep-able. The vocabulary is parsed from the template
  at run time; a missing template fails the run.

Usage:
    uv run --script lab_lint.py <lab dir>

Exits 1 on any finding, 0 clean.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

# a stamp at most this far past the file's mtime is fine: edits lag stamps and
# mtimes are second-granular
STAMP_TOLERANCE_S = 120

_ISO_DT_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?")
_HHMM_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b")
# clause markers that make a following time planned, not an event stamp
_PLANNED_RE = re.compile(
    r"\b(deadline|due|until|eta|cap|target|windows?|gate|before|next)\b|at the latest",
    re.IGNORECASE,
)
_BY_RE = re.compile(r"\bby\b", re.IGNORECASE)

MILESTONE_COLS = ["by", "milestone", "state"]
EXPERIMENT_COLS = ["id", "question", "tier", "state", "budget", "eta"]

_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "audit-log.md"


@dataclass
class Finding:
    file: Path
    line: int  # 1-based; 0 = file-level
    rule: str
    detail: str


def _audit_events() -> set[str]:
    """Fixed Event vocabulary, parsed from the template so it cannot drift."""
    try:
        text = _TEMPLATE.read_text()
    except OSError as e:
        raise SystemExit(f"cannot read audit-log template {_TEMPLATE}: {e}")
    m = re.search(r"^Events: (.*?)(?:\n\n|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        raise SystemExit(f"no 'Events:' line in {_TEMPLATE}")
    return set(re.findall(r"`([A-Z_]+)`", m.group(1)))


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _planned(line: str, start: int) -> bool:
    """True when the clause before a stamp marks it as planned, not an event."""
    words = line[:start].lower().split()
    if _PLANNED_RE.search(" ".join(words[-4:])):
        return True
    # "by" must be adjacent: it is agentive in "launched by author-2 at 16:39"
    return bool(_BY_RE.search(" ".join(words[-2:])))


def _in_planned_column(line: str, start: int, header: list[str] | None) -> bool:
    if not header or not line.lstrip().startswith("|"):
        return False
    idx = line[:start].count("|") - 1
    return 0 <= idx < len(header) and header[idx].lower() in {"by", "eta"}


def lint_timestamps(lab: Path) -> list[Finding]:
    today = date.today()
    findings = []
    files = sorted(p for p in lab.rglob("*") if p.suffix in {".md", ".jsonl"} and p.is_file())
    for f in files:
        limit = f.stat().st_mtime + STAMP_TOLERANCE_S
        text = f.read_text(errors="replace")
        # bare HH:MM is only a timestamp when the file says which day
        has_today = today.isoformat() in text
        header: list[str] | None = None
        prev_table = False
        for i, line in enumerate(text.splitlines(), start=1):
            is_table = line.lstrip().startswith("|")
            if is_table and not prev_table:
                header = _cells(line)  # first row of a table block is its header
            elif not is_table:
                header = None
            prev_table = is_table
            iso = [
                (
                    m.start(),
                    m.end(),
                    datetime(
                        int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)), int(m.group(6) or 0),
                    ),
                )
                for m in _ISO_DT_RE.finditer(line)
            ]
            iso_spans = [(s, e) for s, e, _ in iso]
            for s, _, dt in iso:
                if dt.timestamp() > limit and not (
                    _planned(line, s) or _in_planned_column(line, s, header)
                ):
                    findings.append(Finding(f, i, "future-stamp", dt.strftime("%Y-%m-%d %H:%M:%S")))
            for m in _HHMM_RE.finditer(line):
                if any(s <= m.start() < e for s, e in iso_spans):
                    continue
                h, mi = int(m.group(1)), int(m.group(2))
                if not has_today or not (0 <= h <= 23 and 0 <= mi <= 59):
                    continue
                dt = datetime.combine(today, time(h, mi, int(m.group(3) or 0)))
                if dt.timestamp() > limit and not (
                    _planned(line, m.start()) or _in_planned_column(line, m.start(), header)
                ):
                    findings.append(Finding(f, i, "future-stamp", m.group(0)))
    return findings


def lint_status(lab: Path) -> list[Finding]:
    status = lab / "status.md"
    if not status.is_file():
        return [Finding(status, 0, "status", "status.md missing")]
    findings = []
    lines = status.read_text().splitlines()
    if not lines or not lines[0].strip() or lines[0].lstrip().startswith(("#", "|")):
        first = lines[0] if lines else ""
        findings.append(
            Finding(status, 1, "status", f"line 1 is not a one-line state: {first.strip()[:80]!r}")
        )
    for cols, table in ((MILESTONE_COLS, "milestone"), (EXPERIMENT_COLS, "experiment")):
        if not any(_cells(l) == cols for l in lines if l.lstrip().startswith("|")):
            findings.append(
                Finding(status, 0, "status", f"{table} table missing (header | {' | '.join(cols)} |)")
            )
    return findings


def lint_audit_log(lab: Path, events: set[str]) -> list[Finding]:
    log = lab / "audit" / "log.md"
    if not log.is_file():
        return [Finding(log, 0, "audit-event", "audit/log.md missing")]
    findings = []
    for i, line in enumerate(log.read_text().splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 3 or cells[0].lower() == "time" or set(cells[0]) <= {"-", " ", ":"}:
            continue  # header, separator, or malformed row - not an event row
        if cells[1] not in events:
            findings.append(Finding(log, i, "audit-event", f"event {cells[1]!r} outside the vocabulary"))
    return findings


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    lab = Path(sys.argv[1])
    if not lab.is_dir():
        print(f"not a directory: {lab}")
        return 2
    findings = lint_timestamps(lab) + lint_status(lab) + lint_audit_log(lab, _audit_events())
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else str(f.file)
        print(f"FAIL {loc} [{f.rule}]: {f.detail}")
    print(f"lab lint: {'clean' if not findings else f'{len(findings)} finding(s)'}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
