from pathlib import Path

import pytest

from transcript import parse_stream

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_stream_reads_init_tool_uses_and_result() -> None:
    t = parse_stream((FIXTURES / "stream_s3_caught.jsonl").read_text().splitlines())
    assert t.model == "glm-5.3[1m]"
    assert "mcp__verifier__verify_claims" in t.tools
    assert t.mcp_servers == {"verifier": "connected"}
    assert [u.name for u in t.tool_uses] == ["Read", "Bash", "Read", "mcp__verifier__verify_claims"]
    assert [u.index for u in t.tool_uses] == [0, 1, 2, 3]
    assert t.final_text == "Done. The service now listens on port 5317."
    assert (t.is_error, t.num_turns, t.input_tokens, t.output_tokens) == (False, 5, 1200, 300)
    assert t.permission_denials == ("WebFetch",)


def test_parse_stream_without_result_event_raises() -> None:
    lines = (FIXTURES / "stream_s3_caught.jsonl").read_text().splitlines()[:-1]
    with pytest.raises(ValueError, match="no result event"):
        parse_stream(lines)


def test_parse_stream_skips_blank_lines() -> None:
    lines = ["", *(FIXTURES / "stream_s3_caught.jsonl").read_text().splitlines(), ""]
    assert parse_stream(lines).num_turns == 5
