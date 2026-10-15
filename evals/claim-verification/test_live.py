import shutil
from pathlib import Path

from live import (ALLOWED_BASE, JUDGE_TOOLSET, TOOLSETS, build_command, isolation_evidence,
                  native_snapshot, project_slug, rule_answers)
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


def test_native_snapshot_covers_sync_owned_paths_only(tmp_path: Path) -> None:
    home = tmp_path / ".claude"
    (home / "skills").mkdir(parents=True)
    (home / "skills" / "a").symlink_to(tmp_path)
    (home / "CLAUDE.md").write_text("rules")
    before = native_snapshot(home)
    assert before == native_snapshot(home)
    (home / "CLAUDE.md").write_text("changed")
    assert native_snapshot(home) != before
    assert native_snapshot(home)["hooks"] == "missing"
    assert ".claude.json" not in native_snapshot(home)


def test_project_slug_replaces_every_non_alphanumeric_char_with_dash() -> None:
    assert project_slug("/mnt/home/hayden.dorahy/.cache/x") == "-mnt-home-hayden-dorahy--cache-x"


def _probe_layout(tmp_path: Path) -> tuple[Path, Path, Path, Path, list[Path]]:
    arm = tmp_path / "arm-home"
    native_dir = tmp_path / "native-claude"
    native_json = tmp_path / "native-claude.json"
    scratch = tmp_path / "scratch"
    workspaces = [scratch / "probe-mcp", scratch / "probe-no-mcp"]
    for ws in workspaces:
        (arm / "projects" / project_slug(ws)).mkdir(parents=True)
    native_json.write_text("{}")
    return arm, native_dir, native_json, scratch, workspaces


def test_isolation_evidence_all_true_when_probe_ran_in_the_arm_home(tmp_path: Path) -> None:
    arm, native_dir, native_json, scratch, workspaces = _probe_layout(tmp_path)
    ev = isolation_evidence(arm, native_dir, native_json, scratch, workspaces)
    assert ev == {"arm_projects": True, "native_projects_absent": True, "native_json_clean": True}


def test_isolation_evidence_fails_when_arm_home_lacks_a_project_dir(tmp_path: Path) -> None:
    arm, native_dir, native_json, scratch, workspaces = _probe_layout(tmp_path)
    import shutil
    shutil.rmtree(arm / "projects" / project_slug(workspaces[1]))
    ev = isolation_evidence(arm, native_dir, native_json, scratch, workspaces)
    assert ev["arm_projects"] is False
    assert ev["native_projects_absent"] is True and ev["native_json_clean"] is True


def test_isolation_evidence_fails_when_native_home_gained_a_project_dir(tmp_path: Path) -> None:
    arm, native_dir, native_json, scratch, workspaces = _probe_layout(tmp_path)
    (native_dir / "projects" / project_slug(workspaces[0])).mkdir(parents=True)
    ev = isolation_evidence(arm, native_dir, native_json, scratch, workspaces)
    assert ev["native_projects_absent"] is False
    assert ev["arm_projects"] is True and ev["native_json_clean"] is True


def test_isolation_evidence_fails_when_native_json_mentions_scratch(tmp_path: Path) -> None:
    arm, native_dir, native_json, scratch, workspaces = _probe_layout(tmp_path)
    native_json.write_text('{"lastDir": "' + str(scratch) + '"}')
    ev = isolation_evidence(arm, native_dir, native_json, scratch, workspaces)
    assert ev["native_json_clean"] is False
    assert ev["arm_projects"] is True and ev["native_projects_absent"] is True


def test_rule_answers_strips_markdown_and_matches_case_insensitively() -> None:
    assert rule_answers("**RULE:** NO") == {"NO"}
    assert rule_answers("rule - no") == {"NO"}
    assert rule_answers("`RULE`: **NO**") == {"NO"}


def test_rule_answers_empty_when_line_missing() -> None:
    assert rule_answers("The RULE question was not asked here.") == set()


def test_rule_answers_collects_yes() -> None:
    assert rule_answers("RULE: YES") == {"YES"}


def test_child_env_strips_git_gate_vars(monkeypatch, tmp_path) -> None:
    from live import child_env
    monkeypatch.setenv("COMMIT_AUTHORISED", "1")
    monkeypatch.setenv("PUSH_AUTHORISED", "1")
    env = child_env(tmp_path)
    assert "COMMIT_AUTHORISED" not in env and "PUSH_AUTHORISED" not in env
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path)
