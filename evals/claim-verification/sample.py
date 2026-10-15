from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from live import JUDGE_TOOLSET, launch

CONCRETE = re.compile(r"`[^`]+`|\b[\w.-]+/[\w./-]+|\b\w+\.(py|md|json|toml|sh|ts|js|yaml|yml)\b|\b\d{2,}\b")
FENCE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
TOOL_INPUT_CHARS = 300
TOOL_RESULT_CHARS = 800
JUDGE_PROMPT = Path(__file__).parent / "judge_prompt.md"


@dataclass(slots=True, frozen=True)
class Judged:
    claim: str
    supported: bool
    evidence: int | None


def _lines(session: Path):
    for raw in session.read_text(errors="replace").splitlines():
        if raw.strip():
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue


def _blocks(event: dict) -> list[dict]:
    content = (event.get("message") or {}).get("content")
    return content if isinstance(content, list) else []


def _result_text(block: dict) -> str:
    c = block.get("content")
    if isinstance(c, list):
        return " ".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
    return str(c or "")


def terminal_text(session: Path) -> str:
    last = ""
    for e in _lines(session):
        if e.get("type") == "assistant":
            texts = [b["text"] for b in _blocks(e) if b.get("type") == "text" and b.get("text", "").strip()]
            if texts:
                last = "\n".join(texts)
    return last


def first_timestamp(session: Path) -> datetime | None:
    for e in _lines(session):
        ts = e.get("timestamp")
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return None


def pool(projects: Path, min_chars: int = 400, min_tokens: int = 3, since: datetime | None = None) -> list[Path]:
    out = []
    for session in sorted(projects.glob("*/*.jsonl")):
        if since is not None and ((t := first_timestamp(session)) is None or t < since):
            continue
        text = terminal_text(session)
        if len(text) >= min_chars and len(CONCRETE.findall(text)) >= min_tokens:
            out.append(session)
    return out


def pick(items: list[Path], n: int, seed: int) -> list[Path]:
    return random.Random(seed).sample(items, min(n, len(items)))


def condense(session: Path, max_chars: int = 150_000) -> str:
    rows: list[str] = []
    index: dict[str, int] = {}
    for e in _lines(session):
        for b in _blocks(e):
            if b.get("type") == "tool_use":
                index[b.get("id", "")] = len(index)
                rows.append(f"[{index[b.get('id', '')]}] TOOL {b.get('name')} {json.dumps(b.get('input'))[:TOOL_INPUT_CHARS]}")
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in index:
                rows.append(f"[{index[b['tool_use_id']]}] RESULT {_result_text(b)[:TOOL_RESULT_CHARS]}")
    body = "\n".join(rows)
    terminal = terminal_text(session)
    budget = max_chars - len(terminal) - 100
    if len(body) > budget:
        body = "...(earlier events truncated)\n" + body[-budget:]
    return f"{body}\n\n=== TERMINAL MESSAGE ===\n{terminal}"


def parse_judge(text: str) -> list[Judged]:
    m = FENCE.search(text)
    if m is None:
        raise ValueError(f"judge output has no fenced JSON array: {text[:300]!r}")
    return [Judged(str(d["claim"]), bool(d["supported"]), d.get("evidence")) for d in json.loads(m.group(1))]


def judge(launcher: Path, home: Path, scratch: Path, session: Path) -> list[Judged]:
    prompt = JUDGE_PROMPT.read_text() + "\n\n" + condense(session)
    ws = scratch / f"judge-{session.stem}"
    ws.mkdir(parents=True, exist_ok=True)
    res = launch(launcher, home, ws, prompt, JUDGE_TOOLSET, timeout_s=600)
    if res.transcript is None:
        raise RuntimeError(f"judge launch failed: session={session} error={res.error} stderr={res.stderr[-500:]}")
    return parse_judge(res.transcript.final_text)
