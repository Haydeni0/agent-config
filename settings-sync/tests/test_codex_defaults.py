from pathlib import Path
import tomllib

import pytest
from typer.testing import CliRunner

from settings_sync.cli import app


@pytest.fixture
def defaults_source(tmp_path: Path) -> Path:
    source = tmp_path / "claude"
    (source / "codex").mkdir(parents=True)
    (source / "codex" / "config.toml").write_text('model = "example-model"\n[features]\nhooks = true\n')
    (source / "CLAUDE.md").write_text("# Rules\nSee @skills/uv.\n")
    return source


@pytest.mark.parametrize("flags", [[], ["--force"]])
def test_defaults_merge_preserves_local_state(tmp_path: Path, defaults_source: Path, flags: list[str]):
    target = tmp_path / "codex"
    target.mkdir()
    config = target / "config.toml"
    config.write_text(
        '# Local preferences\nmodel = "old-model"\n'
        '[features]\nhooks = false\ncustom_flag = true # keep this\n'
        '[projects."/repo"]\ntrust_level = "trusted"\n'
        '[hooks.state."hook-id"]\ntrusted_hash = "sha256:example"\n'
        '[tui]\nstatus_line = ["model-name", "context-remaining"]\n'
    )

    result = CliRunner().invoke(app, ["--claude-dir", str(defaults_source), "--codex-dir", str(target), "codex", *flags])

    assert result.exit_code == 0, result.output
    assert tomllib.loads(config.read_text()) == {
        "model": "example-model",
        "features": {"hooks": True, "custom_flag": True},
        "projects": {"/repo": {"trust_level": "trusted"}},
        "hooks": {"state": {"hook-id": {"trusted_hash": "sha256:example"}}},
        "tui": {"status_line": ["model-name", "context-remaining"]},
    }
    assert "# Local preferences" in config.read_text()
    assert "# keep this" in config.read_text()
    assert (target / "AGENTS.md").read_text() == "# Rules\nSee the `uv` skill.\n"


@pytest.mark.parametrize("flag", ["--check", "--dry-run"])
def test_defaults_drift_leaves_target_unchanged(tmp_path: Path, defaults_source: Path, flag: str):
    target = tmp_path / "codex"
    target.mkdir()
    config = target / "config.toml"
    original = 'model = "old-model"\n'
    config.write_text(original)

    result = CliRunner().invoke(app, ["--claude-dir", str(defaults_source), "--codex-dir", str(target), "codex", "config", flag])

    assert result.exit_code == 1, result.output
    assert "would_replace" in result.output
    assert config.read_text() == original


@pytest.mark.parametrize("invalid_file", ["source", "target"])
def test_invalid_toml_preserves_target(tmp_path: Path, defaults_source: Path, invalid_file: str):
    target = tmp_path / "codex"
    target.mkdir()
    config = target / "config.toml"
    config.write_text('model = "old-model"\n')
    invalid = defaults_source / "codex" / "config.toml" if invalid_file == "source" else config
    invalid.write_text('model = "unterminated\n')
    original = config.read_bytes()

    result = CliRunner().invoke(app, ["--claude-dir", str(defaults_source), "--codex-dir", str(target), "codex", "config", "--force"])

    assert result.exit_code == 1, result.output
    assert "invalid" in result.output.lower()
    assert config.read_bytes() == original


def test_matching_defaults_preserve_formatting(tmp_path: Path, defaults_source: Path):
    target = tmp_path / "codex"
    target.mkdir()
    config = target / "config.toml"
    original = "# Local preferences\nmodel = 'example-model'\n[features]\nhooks=true\ncustom_flag=true\n"
    config.write_text(original)

    result = CliRunner().invoke(app, ["--claude-dir", str(defaults_source), "--codex-dir", str(target), "codex", "config", "--check"])

    assert result.exit_code == 0, result.output
    assert "unchanged" in result.output
    assert config.read_text() == original


def test_defaults_merge_inline_table(tmp_path: Path, defaults_source: Path):
    target = tmp_path / "codex"
    target.mkdir()
    config = target / "config.toml"
    config.write_text('features = {hooks = false, custom_flag = true}\n')

    result = CliRunner().invoke(app, ["--claude-dir", str(defaults_source), "--codex-dir", str(target), "codex", "config"])

    assert result.exit_code == 0, result.output
    assert tomllib.loads(config.read_text())["features"] == {"hooks": True, "custom_flag": True}


def test_codex_sync_accepts_native_nested_skills(tmp_path: Path, defaults_source: Path):
    skill = defaults_source / "skills" / "synced" / "bucket" / "example"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: example\ndescription: Example workflow\n---\nBody.\n")
    target = tmp_path / "codex"

    result = CliRunner().invoke(app, ["--claude-dir", str(defaults_source), "--codex-dir", str(target), "codex", "agents-md"])

    assert result.exit_code == 0, result.output
    assert (target / "AGENTS.md").is_file()
