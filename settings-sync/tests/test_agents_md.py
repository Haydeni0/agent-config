import pathlib

import pytest

from settings_sync.agents_md import build_agents_md


def test_skills_ref_rewritten_to_plain_text(tmp_path: pathlib.Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("See @skills/uv for rules.\n")
    result = build_agents_md(claude_md)
    assert "the `uv` skill" in result
    assert "@skills/uv" not in result


def test_sync_agents_md_writes_expanded_content(tmp_path: pathlib.Path):
    claude = tmp_path / "claude" / "CLAUDE.md"
    claude.parent.mkdir(parents=True)
    claude.write_text("See @skills/uv.\n")
    target = tmp_path / "config" / "opencode" / "AGENTS.md"

    from settings_sync.agents_md import sync_agents_md
    outcome = sync_agents_md(target, claude)

    from settings_sync.sync import Status
    assert outcome.status == Status.CREATED
    assert "the `uv` skill" in target.read_text()


def test_sync_agents_md_skips_diverging_without_force(tmp_path: pathlib.Path):
    claude = tmp_path / "claude" / "CLAUDE.md"
    claude.parent.mkdir(parents=True)
    claude.write_text("New content\n")
    target = tmp_path / "config" / "opencode" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    target.write_text("hand-edited\n")

    from settings_sync.agents_md import sync_agents_md
    from settings_sync.sync import Status
    outcome = sync_agents_md(target, claude)

    assert outcome.status == Status.SKIPPED
    assert target.read_text() == "hand-edited\n"


def test_codegraph_marker_block_survives_agents_md_build(tmp_path: pathlib.Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# Rules\n"
        "<!-- CODEGRAPH_START -->\n## CodeGraph\nUse codegraph before grep.\n<!-- CODEGRAPH_END -->\n"
    )
    result = build_agents_md(claude_md)
    assert "<!-- CODEGRAPH_START -->" in result
    assert "<!-- CODEGRAPH_END -->" in result
    assert "Use codegraph before grep." in result
