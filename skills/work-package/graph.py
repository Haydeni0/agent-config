#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["typer>=0.12"]
# ///
"""Dependency-edge check and frontier for work-package plan/decisions files.

Reads, never writes - `tick`, which flips a task's unchecked boxes to `[x]`
in place, is the one named exception. Fail-closed: malformed input is a
finding, never a silent pass. The grammar and its semantics are owned by the
work-package SKILL.md contract; this module is their mechanical enforcement.

Usage:
  graph.py check <package-dir>     findings, one per line; exit 1 if any
  graph.py frontier <package-dir>  JSON array of open unblocked items
  graph.py tick <package-dir> <task-num>   flip a task's boxes; exit 1, no write, on refusal
  graph.py detect <package-dir>    JSON facts; no routing decision
"""
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import typer

Q_TYPES = ("grill", "research", "prototype", "task")
TASK_HEADING_RE = re.compile(r"^### Task (\d+): (.*)$")
BLOCKED_BY_PLAN_RE = re.compile(r"^\*\*Blocked by:\*\* (.+)$")
CHECKBOX_RE = re.compile(r"^\s*- \[( |x|X)\]")
Q_RE = re.compile(r"^- (~~)?Q(\d+)\b(?:\s*\[(\w+)\])?\s*\.?\s*(.*)$")
Q_BLOCKED_RE = re.compile(r"\bBlocked by:\s*(.+)$")
RESOLVES_RE = re.compile(r"\bResolves Q(\d+)\b")
TASK_REF_RE = re.compile(r"^Task (\d+)$")
Q_REF_RE = re.compile(r"^(?:~~)?Q(\d+)$")
STEP_LABEL_RE = re.compile(r"\*\*Step (\d+)([a-z])?:")
D_LINE_RE = re.compile(r"^- (~~)?D(\d+)")
STATE_RE = re.compile(r"^state: ([a-z0-9-]+)$")
REVIEWED_RE = re.compile(r"^Reviewed: (pass|fail) ([1-9]\d*)$")
IMPLEMENTED_RE = re.compile(r"^Implemented$")


@dataclass
class TaskNode:
    num: int
    title: str
    blocked_by: list[str] = field(default_factory=list)
    has_field: bool = False
    n_fields: int = 0
    n_boxes: int = 0
    n_checked: int = 0
    step_labels: list[tuple[int, str]] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"Task {self.num}"

    @property
    def closed(self) -> bool:
        return self.n_boxes > 0 and self.n_checked == self.n_boxes


@dataclass
class QNode:
    num: int
    title: str
    qtype: str | None = None
    blocked_by: list[str] = field(default_factory=list)
    struck: bool = False

    @property
    def id(self) -> str:
        return f"Q{self.num}"

    @property
    def closed(self) -> bool:
        return self.struck


def _unfenced(text: str) -> list[str]:
    """Non-fenced lines, fence toggles dropped - fenced examples quote the
    grammar as text, not as edges."""
    out = []
    in_fence = False
    for raw in text.splitlines():
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(raw)
    return out


def parse_plan(text: str) -> tuple[list[TaskNode], list[str]]:
    """Tasks in file order plus parse-level findings. Any heading other than a
    Task heading ends the current task, so trailing sections never leak
    checkboxes or edges into it."""
    tasks: list[TaskNode] = []
    findings: list[str] = []
    cur: TaskNode | None = None
    for raw in _unfenced(text):
        m = TASK_HEADING_RE.match(raw)
        if m:
            cur = TaskNode(num=int(m.group(1)), title=m.group(2).strip())
            tasks.append(cur)
            continue
        if raw.startswith("#"):
            cur = None
            continue
        bm = BLOCKED_BY_PLAN_RE.match(raw)
        if bm:
            if cur is None:
                findings.append("plan.md: Blocked by line outside any task heading")
                continue
            cur.n_fields += 1
            if cur.n_fields == 1:
                cur.has_field = True
                val = bm.group(1).strip()
                cur.blocked_by = [] if val == "None" else [t.strip() for t in val.split(",")]
            continue
        if cur is None:
            continue
        cm = CHECKBOX_RE.match(raw)
        if cm:
            cur.n_boxes += 1
            if cm.group(1) != " ":
                cur.n_checked += 1
            sm = STEP_LABEL_RE.search(raw)
            if sm:
                cur.step_labels.append((int(sm.group(1)), sm.group(2) or ""))
    return tasks, findings


def _parse_refs(refs: list[str]) -> tuple[list[tuple[str, int]], list[str]]:
    """Split refs into (('task'|'q', n), ...) plus unparseable leftovers."""
    parsed, bad = [], []
    for r in refs:
        m = TASK_REF_RE.match(r)
        if m:
            parsed.append(("task", int(m.group(1))))
            continue
        m = Q_REF_RE.match(r)
        if m:
            parsed.append(("q", int(m.group(1))))
            continue
        bad.append(r)
    return parsed, bad


def _check_plan(tasks: list[TaskNode]) -> list[str]:
    f: list[str] = []
    by_num: dict[int, TaskNode] = {}
    for t in tasks:
        if t.num in by_num:
            f.append(f"plan.md: duplicate task ID {t.id}")
        by_num[t.num] = t
    opted_in = any(t.has_field for t in tasks)
    for t in tasks:
        if opted_in and not t.has_field:
            f.append(f"plan.md: {t.id} lacks a Blocked by line (plan has opted in)")
        if t.n_fields > 1:
            f.append(f"plan.md: {t.id} has more than one Blocked by line")
        if opted_in and t.n_boxes == 0:
            f.append(f"plan.md: {t.id} has no checkboxes, so it can never close")
    closed = {n: t.closed for n, t in by_num.items()}
    for t in tasks:
        parsed, bad = _parse_refs(t.blocked_by)
        for kind, num in parsed:
            if kind == "q":
                f.append(f"plan.md: {t.id} cross-file reference Q{num} - edges stay within one file")
                continue
            if num not in by_num:
                f.append(f"plan.md: {t.id} blocked by unknown Task {num}")
            elif t.closed and not closed[num]:
                f.append(f"plan.md: {t.id} is closed but blocker Task {num} is open")
        for r in bad:
            f.append(f"plan.md: {t.id} unparseable reference {r!r}")
    # cycles over task->task edges
    color: dict[int, int] = {}
    chain: list[int] = []

    def dfs(n: int) -> str | None:
        color[n] = 1
        chain.append(n)
        parsed, _ = _parse_refs(by_num[n].blocked_by)
        for kind, m in parsed:
            if kind != "task" or m not in by_num:
                continue
            if color.get(m, 0) == 1:
                i = chain.index(m)
                return " -> ".join(f"Task {x}" for x in chain[i:] + [m])
            if color.get(m, 0) == 0:
                got = dfs(m)
                if got:
                    return got
        color[n] = 2
        chain.pop()
        return None

    for n in by_num:
        if color.get(n, 0) == 0:
            got = dfs(n)
            if got:
                f.append(f"plan.md: dependency cycle: {got}")
    return f


def _check_step_labels(tasks: list[TaskNode]) -> list[str]:
    """Step labels within a task must start at 1 and run contiguously over
    base numbers; a duplicate is the same (base, letter) pair twice - `2:`
    and `2a:` together are not a duplicate, two bare `2:` labels are."""
    f: list[str] = []
    for t in tasks:
        seen: set[tuple[int, str]] = set()
        for base, letter in t.step_labels:
            if (base, letter) in seen:
                f.append(f"plan.md: {t.id}: duplicate step label Step {base}{letter}")
            seen.add((base, letter))
        bases: list[int] = []
        for base, _letter in t.step_labels:
            if base not in bases:
                bases.append(base)
        if not bases:
            continue
        if bases[0] != 1:
            f.append(f"plan.md: {t.id}: step numbering must start at 1 - first label is Step {bases[0]}")
            continue
        prev = 1
        for b in bases[1:]:
            if b != prev + 1:
                f.append(f"plan.md: {t.id}: step numbering not contiguous - expected Step {prev + 1}, saw Step {b}")
                break
            prev = b
    return f


def _check_d_ids(text: str) -> list[str]:
    """Two live D entries with the same number, or a live plus a struck entry
    with the same number, are findings. No gap check - struck entries keep
    their numbers, so a gap is review-visible."""
    f: list[str] = []
    live: dict[int, int] = {}
    struck: set[int] = set()
    for raw in _unfenced(text):
        m = D_LINE_RE.match(raw)
        if not m:
            continue
        num = int(m.group(2))
        if m.group(1):
            struck.add(num)
        else:
            live[num] = live.get(num, 0) + 1
    for num in sorted(live):
        if live[num] > 1:
            f.append(f"decisions.md: {live[num]} live D{num} entries - duplicate D id")
        if num in struck:
            f.append(f"decisions.md: live D{num} collides with a struck D{num}")
    return f


def check_pkg(pkg: Path) -> list[str]:
    findings: list[str] = []
    plan = pkg / "plan.md"
    if plan.exists():
        tasks, parse_findings = parse_plan(plan.read_text())
        findings += parse_findings
        findings += _check_plan(tasks)
        findings += _check_step_labels(tasks)
    decisions = pkg / "decisions.md"
    if decisions.exists():
        text = decisions.read_text()
        qs, resolved = parse_decisions(text)
        findings += _check_decisions(qs, resolved)
        findings += _check_d_ids(text)
    return findings


def parse_decisions(text: str) -> tuple[list[QNode], set[int]]:
    """Q entries live only under an `## Open questions` heading, and only
    D-entry lines carry `Resolves Q<n>` closure citations - a Q id or a
    Resolves mention anywhere else (a review finding, a nit) is prose, not
    graph state."""
    qs: list[QNode] = []
    resolved: set[int] = set()
    cur: QNode | None = None
    section = ""
    for raw in _unfenced(text):
        if raw.startswith("## "):
            section = raw[3:].strip().lower()
            cur = None
            continue
        stripped = raw.lstrip()
        if stripped.startswith("- D") or stripped.startswith("- ~~D"):
            rm = RESOLVES_RE.search(raw)
            if rm:
                resolved.add(int(rm.group(1)))
        if section != "open questions":
            continue
        m = Q_RE.match(raw)
        if m:
            struck = m.group(1) is not None
            qtype = m.group(3)
            cur = QNode(num=int(m.group(2)), title=m.group(4).strip(), qtype=qtype, struck=struck)
            qs.append(cur)
            bm = Q_BLOCKED_RE.search(cur.title)
            if bm:
                cur.blocked_by = [t.strip().rstrip("?.!~") for t in bm.group(1).split(",")]
                cur.title = cur.title[: bm.start()].strip().rstrip(",;~-").strip() or cur.title
            continue
        if cur is not None and raw.startswith("  ") and not raw.strip().startswith("- "):
            bm = Q_BLOCKED_RE.search(raw)
            if bm:
                cur.blocked_by = [t.strip().rstrip("?.!~") for t in bm.group(1).split(",")]
    return qs, resolved


def _check_decisions(qs: list[QNode], resolved: set[int]) -> list[str]:
    f: list[str] = []
    seen: set[int] = set()
    for q in qs:
        if q.num in seen:
            f.append(f"decisions.md: duplicate question ID {q.id}")
        seen.add(q.num)
        if q.qtype is not None and q.qtype not in Q_TYPES:
            f.append(f"decisions.md: {q.id} unknown type tag {q.qtype!r} (allowed: {' | '.join(Q_TYPES)})")
    for q in qs:
        for r in q.blocked_by:
            m = TASK_REF_RE.match(r)
            if m:
                f.append(f"decisions.md: {q.id} cross-file reference Task {m.group(1)} - edges stay within one file")
                continue
            m = Q_REF_RE.match(r)
            if m:
                num = int(m.group(1))
                if num not in seen and num not in resolved:
                    f.append(f"decisions.md: {q.id} blocked by unknown Q{num}")
            else:
                f.append(f"decisions.md: {q.id} unparseable reference {r!r}")
    # cycles among open Qs
    open_qs = {q.num: q for q in qs if not q.struck}
    color: dict[int, int] = {}
    chain: list[int] = []

    def dfs(n: int) -> str | None:
        color[n] = 1
        chain.append(n)
        for r in open_qs[n].blocked_by:
            m = Q_REF_RE.match(r)
            if not m or int(m.group(1)) not in open_qs:
                continue
            nxt = int(m.group(1))
            if color.get(nxt, 0) == 1:
                i = chain.index(nxt)
                return " -> ".join(f"Q{x}" for x in chain[i:] + [nxt])
            if color.get(nxt, 0) == 0:
                got = dfs(nxt)
                if got:
                    return got
        color[n] = 2
        chain.pop()
        return None

    for n in open_qs:
        if color.get(n, 0) == 0:
            got = dfs(n)
            if got:
                f.append(f"decisions.md: dependency cycle: {got}")
    return f


class GraphFindings(Exception):
    def __init__(self, findings: list[str]):
        super().__init__("; ".join(findings))
        self.findings = findings


def _first_sentence(title: str) -> str:
    ends = [title.find(e) for e in (".", "?", "!")]
    hits = [i for i in ends if i != -1]
    return title[: min(hits) + 1].strip() if hits else title.strip()


def frontier_pkg(pkg: Path) -> list[dict]:
    """Open items whose blockers are all closed, in file order: plan tasks in
    plan order, then Q entries in decisions order. Raises GraphFindings when
    check_pkg reports anything - never a partial frontier. Task titles are
    the full heading title; Q titles are the entry's first sentence."""
    findings = check_pkg(pkg)
    if findings:
        raise GraphFindings(findings)
    items: list[dict] = []
    plan = pkg / "plan.md"
    if plan.exists():
        tasks, _ = parse_plan(plan.read_text())
        by_num = {t.num: t for t in tasks}
        for t in tasks:
            if t.closed or not t.has_field:
                continue
            parsed, _ = _parse_refs(t.blocked_by)
            if all(kind == "task" and by_num[num].closed for kind, num in parsed):
                items.append({"id": t.id, "kind": "task", "type": None,
                              "title": t.title, "blocked_by": t.blocked_by})
    decisions = pkg / "decisions.md"
    if decisions.exists():
        qs, resolved = parse_decisions(decisions.read_text())
        for q in qs:
            if q.num in resolved or q.struck:
                continue
            blocked_open = False
            for r in q.blocked_by:
                m = Q_REF_RE.match(r)
                if not m:
                    continue
                num = int(m.group(1))
                if num not in resolved and not any(o.num == num and o.struck for o in qs):
                    blocked_open = True
            if not blocked_open:
                items.append({"id": q.id, "kind": "q", "type": q.qtype or "grill",
                              "title": _first_sentence(q.title), "blocked_by": q.blocked_by})
    return items


def tick_pkg(pkg: Path, task_num: int) -> None:
    """Flip every unchecked box of one task to [x]. Raises GraphFindings
    (no write) on unknown/ambiguous/already-complete tasks."""
    plan = pkg / "plan.md"
    if not plan.exists():
        raise GraphFindings([f"plan.md: no plan.md in {pkg}"])
    raw = plan.read_text()
    tasks, _ = parse_plan(raw)
    counts: dict[int, int] = {}
    for t in tasks:
        counts[t.num] = counts.get(t.num, 0) + 1
    dupes = sorted(n for n, c in counts.items() if c > 1)
    if dupes:
        raise GraphFindings([
            f"plan.md: duplicate task ID Task {n} - tick refuses ambiguous plans" for n in dupes
        ])
    task = next((t for t in tasks if t.num == task_num), None)
    if task is None:
        raise GraphFindings([f"plan.md: unknown task Task {task_num}"])
    if task.n_boxes == 0:
        raise GraphFindings([f"plan.md: {task.id} has no checkboxes"])
    if task.n_checked == task.n_boxes:
        raise GraphFindings([f"plan.md: {task.id} is already fully checked"])
    lines = raw.split("\n")
    # locate the task's heading range in the raw line list, fence-aware:
    # its `### Task N:` heading to the next `### Task` or `#` heading
    start = end = None
    in_fence = False
    for i, l in enumerate(lines):
        if l.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = TASK_HEADING_RE.match(l)
        if m:
            if start is None:
                if int(m.group(1)) == task_num:
                    start = i
            else:
                end = i
                break
        elif start is not None and l.startswith("#"):
            end = i
            break
    if start is None:
        raise GraphFindings([f"plan.md: unknown task Task {task_num}"])
    if end is None:
        end = len(lines)
    flips = 0
    in_fence = False
    for i, l in enumerate(lines):
        if l.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not (start < i < end):
            continue
        cm = CHECKBOX_RE.match(l)
        if cm and cm.group(1) == " ":
            lines[i] = l.replace("- [ ]", "- [x]", 1)
            flips += 1
    if flips == 0:
        raise GraphFindings([f"plan.md: {task.id} has no unchecked boxes to flip"])
    plan.write_text("\n".join(lines))
    # re-read after write: the flip count must match a fresh parse
    tasks2, _ = parse_plan(plan.read_text())
    task2 = next((t for t in tasks2 if t.num == task_num), None)
    if task2 is None or task2.n_checked - task.n_checked != flips:
        moved = None if task2 is None else task2.n_checked - task.n_checked
        raise GraphFindings([
            f"plan.md: tick verification failed - flipped {flips} boxes but the fresh parse moved {moved}"
        ])


def detect_pkg(pkg: Path) -> dict:
    """JSON facts about a package; makes no routing decision. Raises
    GraphFindings on an absent decisions.md or a malformed state line."""
    decisions = pkg / "decisions.md"
    if not decisions.exists():
        raise GraphFindings([f"decisions.md: absent in {pkg} - detect serves existing packages"])
    text = decisions.read_text()
    lines = text.splitlines()
    first = lines[0].rstrip() if lines else ""
    m = STATE_RE.match(first)
    if m:
        state, has_state = m.group(1), True
    elif first.strip().lower().startswith("state:"):
        raise GraphFindings([
            f"decisions.md: malformed state line: {first[:40]!r} (expected 'state: <value>')"
        ])
    else:
        state, has_state = None, False
    unfenced = _unfenced(text)
    qs, _resolved = parse_decisions(text)
    return {
        "state": state,
        "has_state_line": has_state,
        "outcome": any(re.match(r"^## Outcome\s*$", l) for l in unfenced),
        "d_entries": sum(1 for l in unfenced if re.match(r"^- D\d+", l)),
        "open_qs": sum(1 for q in qs if not q.struck),
        "review_findings": any(re.match(r"^## Review findings\s*$", l) for l in unfenced),
        "spec": _artifact_facts(pkg / "spec.md", with_markers=True),
        "plan": _artifact_facts(pkg / "plan.md", with_markers=True, is_plan=True),
        "scenarios": _artifact_facts(pkg / "scenarios.md", with_markers=False),
    }


def _artifact_facts(path: Path, with_markers: bool, is_plan: bool = False) -> dict:
    if not path.exists():
        facts = {"exists": False, "nonempty": False}
        if with_markers:
            facts["markers"] = []
        if is_plan:
            facts.update(implemented=False, boxes=0, unchecked=0, fully_checked=False)
        return facts
    text = path.read_text()
    lines = _unfenced(text)
    facts: dict = {"exists": True, "nonempty": bool(text.strip())}
    if with_markers:
        facts["markers"] = [
            f"{m.group(1)} {m.group(2)}" for l in lines if (m := REVIEWED_RE.match(l.strip()))
        ]
    if is_plan:
        boxes = sum(1 for l in lines if CHECKBOX_RE.match(l))
        unchecked = sum(1 for l in lines if (cm := CHECKBOX_RE.match(l)) and cm.group(1) == " ")
        facts.update(
            implemented=any(IMPLEMENTED_RE.match(l.strip()) for l in lines),
            boxes=boxes,
            unchecked=unchecked,
            fully_checked=boxes > 0 and unchecked == 0,
        )
    return facts


app = typer.Typer()


@app.command()
def check(
    package_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False,
                                                help="Package directory to lint")],
) -> None:
    """Dependency-edge findings, one per line. Exit 1 on findings."""
    findings = check_pkg(package_dir)
    for f_ in findings:
        print(f_)
    raise typer.Exit(1 if findings else 0)


@app.command()
def frontier(
    package_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False,
                                                help="Package directory to read")],
) -> None:
    """Open unblocked items as a JSON array. Exit 1, no array, on findings."""
    findings = check_pkg(package_dir)
    if findings:
        for f_ in findings:
            print(f_, file=sys.stderr)
        raise typer.Exit(1)
    print(json.dumps(frontier_pkg(package_dir), indent=2))


@app.command()
def tick(
    package_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False,
                                                help="Package directory whose plan.md to tick")],
    task_num: Annotated[int, typer.Argument(help="Task number to complete")],
) -> None:
    """Flip a task's unchecked boxes to [x]. Exit 1, no write, on refusal."""
    try:
        tick_pkg(package_dir, task_num)
    except GraphFindings as exc:
        for f_ in exc.findings:
            print(f_)
        raise typer.Exit(1) from None


@app.command()
def detect(
    package_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False,
                                                help="Package directory to read")],
) -> None:
    """JSON facts about a package; no routing decision. Exit 1 on an absent
    decisions.md or a malformed state line."""
    try:
        print(json.dumps(detect_pkg(package_dir), indent=2))
    except GraphFindings as exc:
        for f_ in exc.findings:
            print(f_)
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
