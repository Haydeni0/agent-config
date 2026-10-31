#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["typer>=0.12"]
# ///
"""Dependency-edge check and frontier for work-package plan/decisions files.

Reads, never writes. Fail-closed: malformed input is a finding, never a
silent pass. The grammar and its semantics are owned by the work-package
SKILL.md contract; this module is their mechanical enforcement.

Usage:
  graph.py check <package-dir>     findings, one per line; exit 1 if any
  graph.py frontier <package-dir>  JSON array of open unblocked items
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

Q_TYPES = ("grill", "research", "prototype", "task")
TASK_HEADING_RE = re.compile(r"^### Task (\d+): (.*)$")
BLOCKED_BY_PLAN_RE = re.compile(r"^\*\*Blocked by:\*\* (.+)$")
CHECKBOX_RE = re.compile(r"^\s*- \[( |x|X)\]")
Q_RE = re.compile(r"^- (~~)?Q(\d+)\b(?:\s*\[(\w+)\])?\s*\.?\s*(.*)$")
Q_BLOCKED_RE = re.compile(r"\bBlocked by:\s*(.+)$")
RESOLVES_RE = re.compile(r"\bResolves Q(\d+)\b")
TASK_REF_RE = re.compile(r"^Task (\d+)$")
Q_REF_RE = re.compile(r"^(?:~~)?Q(\d+)$")


@dataclass
class TaskNode:
    num: int
    title: str
    blocked_by: list[str] = field(default_factory=list)
    has_field: bool = False
    n_boxes: int = 0
    n_checked: int = 0

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


def parse_plan(text: str) -> list[TaskNode]:
    tasks: list[TaskNode] = []
    cur: TaskNode | None = None
    for raw in _unfenced(text):
        m = TASK_HEADING_RE.match(raw)
        if m:
            cur = TaskNode(num=int(m.group(1)), title=m.group(2).strip())
            tasks.append(cur)
            continue
        if cur is None:
            continue
        bm = BLOCKED_BY_PLAN_RE.match(raw)
        if bm:
            cur.has_field = True
            val = bm.group(1).strip()
            cur.blocked_by = [] if val == "None" else [t.strip() for t in val.split(",")]
            continue
        cm = CHECKBOX_RE.match(raw)
        if cm:
            cur.n_boxes += 1
            if cm.group(1) != " ":
                cur.n_checked += 1
    return tasks


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


def check_pkg(pkg: Path) -> list[str]:
    findings: list[str] = []
    plan = pkg / "plan.md"
    if plan.exists():
        findings += _check_plan(parse_plan(plan.read_text()))
    return findings
