from pathlib import Path

from live import ALLOWED_BASE, JUDGE_TOOLSET, TOOLSETS, build_command, native_snapshot
from model import VERIFIER_TOOL, Condition


def test_build_command_mcp_passes_one_comma_joined_allow_list() -> None:
    cmd = build_command(Path("/bin/lc"), TOOLSETS[Condition.MCP])
    assert cmd[:3] == ["/bin/lc", "--", "-p"]
    allow = [a for a in cmd if a.startswith("--allowedTools=")]
    assert allow == ["--allowedTools=" + ",".join((*ALLOWED_BASE, VERIFIER_TOOL))]
    assert not any(a.startswith("--disallowedTools") for a in cmd)
    assert "--no-session-persistence" in cmd and "--verbose" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "bypassPermissions" not in " ".join(cmd)


def test_build_command_no_mcp_disallows_verifier() -> None:
    cmd = build_command(Path("/bin/lc"), TOOLSETS[Condition.NO_MCP])
    assert f"--disallowedTools={VERIFIER_TOOL}" in cmd
    assert VERIFIER_TOOL not in next(a for a in cmd if a.startswith("--allowedTools="))


def test_judge_command_removes_every_builtin_and_the_verifier() -> None:
    # `--tools=` (empty) leaves no built-in tool - probe: init event `tools: []`; MCP tools need the explicit deny
    cmd = build_command(Path("/bin/lc"), JUDGE_TOOLSET)
    assert "--tools=" in cmd
    assert not any(a.startswith("--allowedTools") for a in cmd)
    assert f"--disallowedTools={VERIFIER_TOOL}" in cmd


def test_condition_commands_keep_default_builtins() -> None:
    assert not any(a.startswith("--tools") for a in build_command(Path("/bin/lc"), TOOLSETS[Condition.MCP]))


def test_native_snapshot_detects_link_file_and_dir_changes(tmp_path: Path) -> None:
    home = tmp_path / ".claude"
    (home / "skills").mkdir(parents=True)
    (home / "skills" / "a").symlink_to(tmp_path)
    (home / "CLAUDE.md").write_text("rules")
    cj = tmp_path / ".claude.json"
    cj.write_text("{}")
    before = native_snapshot(home, cj)
    assert before == native_snapshot(home, cj)
    (home / "CLAUDE.md").write_text("changed")
    assert native_snapshot(home, cj) != before
    assert native_snapshot(home, cj)["hooks"] == "missing"
