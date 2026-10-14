from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Outcome(StrEnum):
    CAUGHT = "caught"
    REPEATED = "repeated"
    OTHER = "other"
    ERROR = "error"


class Condition(StrEnum):
    MCP = "mcp"
    NO_MCP = "no-mcp"


VERIFIER_TOOL = "mcp__verifier__verify_claims"


@dataclass(slots=True, frozen=True)
class ToolUse:
    index: int  # position among all tool_use events in the run, 0-based
    name: str
    input: dict[str, object]


@dataclass(slots=True, frozen=True)
class Transcript:
    model: str | None
    tools: tuple[str, ...]
    mcp_servers: dict[str, str]  # server name -> status
    tool_uses: tuple[ToolUse, ...]
    final_text: str
    is_error: bool
    num_turns: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    permission_denials: tuple[str, ...] = ()  # tool names denied by the allow-list; diagnoses allow-list misses


@dataclass(slots=True, frozen=True)
class RunScore:
    outcome: Outcome
    oracle_calls: int
    recheck: bool


@dataclass(slots=True, frozen=True)
class RunRecord:
    arm: str
    condition: Condition
    scenario: str
    rep: int
    seed: int
    truth: dict[str, object]
    outcome: Outcome
    oracle_calls: int
    recheck: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float
    num_turns: int
    wall_s: float
    model: str | None
    error: str | None = None
    transcript_path: str | None = None
    extra: dict[str, object] = field(default_factory=dict)
