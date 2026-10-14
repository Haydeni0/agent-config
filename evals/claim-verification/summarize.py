from __future__ import annotations

import dataclasses
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from model import Condition, Outcome, RunRecord


@dataclass(slots=True, frozen=True)
class Cell:
    n: int
    errors: int
    repeated: float
    caught: float
    other: float
    oracle: float
    recheck: float
    mean_tokens: float


def _cell(runs: list[RunRecord]) -> Cell:
    ok = [r for r in runs if r.outcome is not Outcome.ERROR]
    n = len(ok)

    def share(pred) -> float:
        return sum(1 for r in ok if pred(r)) / n if n else 0.0

    return Cell(
        n=n,
        errors=len(runs) - n,
        repeated=share(lambda r: r.outcome is Outcome.REPEATED),
        caught=share(lambda r: r.outcome is Outcome.CAUGHT),
        other=share(lambda r: r.outcome is Outcome.OTHER),
        oracle=share(lambda r: r.oracle_calls >= 1),
        recheck=share(lambda r: r.recheck),
        mean_tokens=sum(r.input_tokens + r.output_tokens for r in ok) / n if n else 0.0,
    )


def aggregate(records: Iterable[RunRecord]) -> dict[tuple[str, str, str], Cell]:
    groups: dict[tuple[str, str, str], list[RunRecord]] = defaultdict(list)
    for r in records:
        groups[(r.arm, str(r.condition), r.scenario)].append(r)
        groups[(r.arm, str(r.condition), "ALL")].append(r)
    return {k: _cell(v) for k, v in sorted(groups.items())}


def render(cells: dict[tuple[str, str, str], Cell], header: str) -> str:
    rows = [
        header, "",
        "| arm | condition | scenario | n | errors | repeated | caught | other | oracle | recheck | mean tokens |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (arm, cond, sc), c in cells.items():
        rows.append(
            f"| {arm} | {cond} | {sc} | {c.n} | {c.errors} | {c.repeated:.0%} | {c.caught:.0%} | "
            f"{c.other:.0%} | {c.oracle:.0%} | {c.recheck:.0%} | {c.mean_tokens:.0f} |"
        )
    return "\n".join(rows) + "\n"


def dump_run(record: RunRecord) -> str:
    return json.dumps(dataclasses.asdict(record), sort_keys=True)


def load_runs(path: Path) -> list[RunRecord]:
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            d["condition"], d["outcome"] = Condition(d["condition"]), Outcome(d["outcome"])
            out.append(RunRecord(**d))
    return out
