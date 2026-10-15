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
- ``accepted-entry``: every experiment id marked accepted - a decisions.md
  D-entry sentence naming ids alongside "accepted" (``E<n>-E<m>`` ranges
  expanded; an id followed within two words by cut/dropped/rejected/deferred is
  not), or a status.md experiment-table row decided ``[x]`` - must still head an
  entry in ``experiments.md`` / ``experiments/*.md``. When git history is
  reachable, a heading the last commit still had is named as dropped since it.
- decision-number WARNs: for every ``experiments/<eid>.md`` with its manifest,
  lab_checker's cross-index third direction runs over decisions.md restatements
  of that experiment (numbers matching no manifest claim are flagged for
  review). Non-blocking; printed as ``WARN`` lines.

Usage:
    uv run --script lab_lint.py <lab dir>

Exits 1 on any finding, 0 clean.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from lab_text import d_entries, sentences

import lab_checker as lc  # numpy is imported lazily; the lint stays stdlib-only

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


_EID_RE = re.compile(r"\bE\d+\b")
_EID_RANGE_RE = re.compile(r"\bE(\d+)\s*-\s*E(\d+)\b")
_NOT_ACCEPTED_RE = re.compile(r"\b(cut|dropped|rejected|deferred)\b")
_ENTRY_HEADING_RE = re.compile(r"^#{1,6}\s+(E\d+)\b", re.MULTILINE)
_ACCEPTED_WORD_RE = re.compile(r"\baccepted\b", re.IGNORECASE)


def _accepted_ids(lab: Path) -> dict[str, tuple[Path, int]]:
    """Experiment ids marked accepted -> (marker file, 1-based marker line)."""
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
                    ids.update(
                        f"E{n}" for n in range(int(m.group(1)), int(m.group(2)) + 1)
                    )
                for m in _EID_RE.finditer(sentence):
                    two_words = " ".join(sentence[m.end() :].split()[:2])
                    if not _NOT_ACCEPTED_RE.search(two_words):
                        ids.add(m.group(0))
                for eid in sorted(ids):
                    accepted.setdefault(eid, (decisions, line))
    status = lab / "status.md"
    if status.is_file():
        for i, line in enumerate(status.read_text().splitlines(), start=1):
            cells = _cells(line)
            if len(cells) >= 4 and re.fullmatch(r"E\d+", cells[0]) and cells[3] == "[x]":
                accepted.setdefault(cells[0], (status, i))
    return accepted


def _experiments_files(lab: Path) -> list[Path]:
    files = []
    single = lab / "experiments.md"
    if single.is_file():
        files.append(single)
    exp_dir = lab / "experiments"
    if exp_dir.is_dir():
        files.extend(sorted(exp_dir.glob("*.md")))
    return files


def _head_ids_at_head(lab: Path) -> set[str]:
    """Entry-heading ids the last commit still had in the lab's experiments
    file(s); empty when the lab is not a git repo or nothing is tracked
    (read-only git queries only). Walks HEAD's tree, not the working tree, so a
    deleted file's heading is still seen."""
    try:
        prefix = subprocess.run(
            ["git", "-C", str(lab), "rev-parse", "--show-prefix"],
            capture_output=True, text=True, timeout=10,
        )
        if prefix.returncode != 0:
            return set()
        listing = subprocess.run(
            ["git", "-C", str(lab), "ls-tree", "-r", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if listing.returncode != 0:
            return set()
        ids: set[str] = set()
        pre = prefix.stdout.strip()
        for rel in listing.stdout.splitlines():
            local = rel[len(pre) :] if rel.startswith(pre) else ""
            if local != "experiments.md" and not re.fullmatch(r"experiments/[^/]+\.md", local):
                continue
            blob = subprocess.run(
                ["git", "-C", str(lab), "show", f"HEAD:{rel}"],
                capture_output=True, text=True, timeout=10, errors="replace",
            )
            if blob.returncode == 0:
                ids.update(_ENTRY_HEADING_RE.findall(blob.stdout))
        return ids
    except (OSError, subprocess.SubprocessError):
        return set()


def lint_accepted_entries(lab: Path) -> list[Finding]:
    """Rule ``accepted-entry``: accepted work must still head an entry.

    A regenerated experiments file must not silently drop an accepted entry; the
    pilot's miss was exactly that. The marker (decisions.md sentence or status
    ``[x]`` row) is the finding's location; when git history is reachable the
    detail also names a heading the last commit still had.
    """
    accepted = _accepted_ids(lab)
    if not accepted:
        return []
    files = _experiments_files(lab)
    heading_ids: set[str] = set()
    for p in files:
        heading_ids.update(_ENTRY_HEADING_RE.findall(p.read_text(errors="replace")))
    at_head = _head_ids_at_head(lab)
    findings = []
    for eid in sorted(accepted):
        if eid in heading_ids:
            continue
        src, line = accepted[eid]
        detail = f"{eid} marked accepted but no entry heading remains in experiments.md or experiments/"
        if eid in at_head:
            detail += " (its heading was present in the last commit)"
        findings.append(Finding(src, line, "accepted-entry", detail))
    return findings


def decision_number_warns(lab: Path) -> list[str]:
    """WARN lines from lab_checker's cross-index third direction, run over every
    experiment's manifest each beat - the D entry is written after the worker's
    last checker run, so the heartbeat is where stale restatements surface."""
    if not (lab / "decisions.md").is_file():
        return []
    warns = []
    for exp in sorted((lab / "experiments").glob("*.md")):
        manifest = exp.with_name(f"{exp.stem}_manifest.py")
        if not manifest.is_file():
            continue
        namespace: dict[str, Any] = {"Check": lc.Check, "CHECKS": [], "__file__": str(manifest)}
        try:
            exec(manifest.read_text(), namespace)  # noqa: S102 - trusted lab code
        except Exception:
            continue  # the worker's own checker run surfaces manifest errors
        for f in lc.decision_numbers(namespace["CHECKS"], exp):
            warns.append(f"WARN {f.check_id} [{f.rule}]: {f.detail}")
    return warns


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    lab = Path(sys.argv[1])
    if not lab.is_dir():
        print(f"not a directory: {lab}")
        return 2
    findings = (
        lint_timestamps(lab)
        + lint_status(lab)
        + lint_audit_log(lab, _audit_events())
        + lint_accepted_entries(lab)
    )
    for w in decision_number_warns(lab):
        print(w)
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else str(f.file)
        print(f"FAIL {loc} [{f.rule}]: {f.detail}")
    print(f"lab lint: {'clean' if not findings else f'{len(findings)} finding(s)'}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
