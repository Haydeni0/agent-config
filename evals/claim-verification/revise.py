from __future__ import annotations

import re
from pathlib import Path

from model import Outcome, RunRecord
from sample import condense

REVISER_PROMPT = Path(__file__).parent / "reviser_prompt.md"
HOLDOUT = frozenset({"S5"})  # D11: never shown to the reviser
MAX_FAILURES = 6
RUN_CHARS = 12_000  # per condensed transcript; bounds the Haiku input (D14)
MAX_GROWTH = 1.25
FENCE = re.compile(r"````markdown\n(.*?)\n?````", re.DOTALL)
PINNED = ("name: claim-verification", "layer: worker")


def failing_runs(records: list[RunRecord], arm: str) -> list[RunRecord]:
    fails = [r for r in records if r.arm == arm and r.scenario not in HOLDOUT and r.transcript_path
             and r.outcome in (Outcome.REPEATED, Outcome.OTHER)]
    fails.sort(key=lambda r: (r.outcome is not Outcome.REPEATED, r.scenario, str(r.condition), r.rep))
    return fails[:MAX_FAILURES]


def brief(records: list[RunRecord], arm: str, skill_md: str) -> str:
    parts = [REVISER_PROMPT.read_text(), "## Current SKILL.md", f"````markdown\n{skill_md}````",
             "## Runs where the skill did not stop a false claim"]
    for r in failing_runs(records, arm):
        parts.append(f"### {r.scenario} / {r.condition} / rep {r.rep}: {r.outcome}\n\n"
                     + condense(Path(str(r.transcript_path)), RUN_CHARS))
    return "\n\n".join(parts) + "\n"


def extract_revision(text: str, current: str) -> str:
    m = FENCE.search(text)
    if m is None:
        raise ValueError(f"reviser output has no ````markdown fence: {text[:300]!r}")
    new = m.group(1).rstrip("\n") + "\n"
    missing = [p for p in PINNED if p not in new]
    if missing:
        raise ValueError(f"revision drops pinned frontmatter {missing}")
    if len(new) > MAX_GROWTH * len(current):
        raise ValueError(f"revision grows {len(new)}/{len(current)} chars, over {MAX_GROWTH}x")
    return new
