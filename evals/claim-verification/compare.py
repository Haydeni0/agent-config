from __future__ import annotations

from dataclasses import dataclass, field
from math import comb

from model import Condition, Outcome, RunRecord

ALPHA = 0.05  # D3: one-sided Fisher exact


def fisher_one_sided(a_rep: int, a_n: int, b_rep: int, b_n: int) -> float:
    k, n = a_rep + b_rep, a_n + b_n
    total = comb(n, k)
    return sum(comb(b_n, i) * comb(a_n, k - i) for i in range(b_rep + 1) if 0 <= k - i <= a_n) / total


def pooled(records: list[RunRecord], scenarios: frozenset[str] | None = None) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for r in records:
        if r.outcome is Outcome.ERROR or (scenarios and r.scenario not in scenarios):
            continue
        rep, n = out.get(r.arm, (0, 0))
        out[r.arm] = (rep + (r.outcome is Outcome.REPEATED), n + 1)
    return out


@dataclass(slots=True, frozen=True)
class Selection:
    chosen: str
    beats_baseline: bool
    p_vs_baseline: float
    p_vs_default: dict[str, float]
    p_oracle: dict[str, float] = field(default_factory=dict)


def oracle_counts(records: list[RunRecord], scenarios: frozenset[str] | None = None) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for r in records:
        if r.outcome is Outcome.ERROR or r.condition is not Condition.MCP or (scenarios and r.scenario not in scenarios):
            continue
        without, n = out.get(r.arm, (0, 0))
        out[r.arm] = (without + (r.oracle_calls == 0), n + 1)
    return out


def select(counts: dict[str, tuple[int, int]], baseline: str, default: str, challengers: list[str],
           oracle: dict[str, tuple[int, int]] | None = None) -> Selection:
    d_rep, d_n = counts[default]
    p_vs_default = {c: fisher_one_sided(d_rep, d_n, *counts[c]) for c in challengers}
    winners = sorted((p, counts[c][0], c) for c, p in p_vs_default.items() if p < ALPHA)
    # D13: fewer runs without an oracle call = more oracle use; only among challengers no worse on repeats
    p_oracle = {c: fisher_one_sided(*oracle[default], *oracle[c]) for c in challengers} if oracle else {}
    if not winners:
        winners = sorted((p, counts[c][0], c) for c, p in p_oracle.items() if p < ALPHA and counts[c][0] <= d_rep)
    chosen = winners[0][2] if winners else default
    p_base = fisher_one_sided(*counts[baseline], *counts[chosen])
    return Selection(chosen, p_base < ALPHA, p_base, p_vs_default, p_oracle)
