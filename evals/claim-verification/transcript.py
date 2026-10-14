from __future__ import annotations

import json
from collections.abc import Iterable

from model import ToolUse, Transcript


def parse_stream(lines: Iterable[str]) -> Transcript:
    model: str | None = None
    tools: tuple[str, ...] = ()
    servers: dict[str, str] = {}
    uses: list[ToolUse] = []
    result: dict[str, object] | None = None
    for raw in lines:
        if not raw.strip():
            continue
        event = json.loads(raw)
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            model = event.get("model")
            tools = tuple(event.get("tools", []))
            servers = {s["name"]: s["status"] for s in event.get("mcp_servers", [])}
        elif kind == "assistant":
            for block in event["message"]["content"]:
                if block.get("type") == "tool_use":
                    uses.append(ToolUse(len(uses), block["name"], dict(block.get("input") or {})))
        elif kind == "result":
            result = event
    if result is None:
        raise ValueError(f"stream-json transcript has no result event (tool_uses={len(uses)})")
    usage = result.get("usage") or {}
    return Transcript(
        model=model,
        tools=tools,
        mcp_servers=servers,
        tool_uses=tuple(uses),
        final_text=str(result.get("result") or ""),
        is_error=bool(result.get("is_error")),
        num_turns=int(result.get("num_turns") or 0),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cost_usd=float(result.get("total_cost_usd") or 0.0),
        permission_denials=tuple(
            str(d.get("tool_name", d)) if isinstance(d, dict) else str(d) for d in result.get("permission_denials") or []
        ),
    )
