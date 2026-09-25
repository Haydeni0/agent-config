from conftest import install_hook_sources
import json
import pathlib

from typer.testing import CliRunner

from settings_sync.cli import Paths, app, run_opencode


def _make_claude_home(tmp_path: pathlib.Path) -> pathlib.Path:
    home = tmp_path / "claude"
    home.mkdir(parents=True)
    (home / "rules").mkdir(parents=True, exist_ok=True)
    (home / "rules/global.md").write_text("# Rules\nExtra rules.\nSee @skills/uv.\n")
    (home / "harnesses/opencode").mkdir(parents=True)
    (home / "harnesses/opencode" / "opencode.json").write_text(json.dumps({"model": "test/model"}))
    (home / "harnesses/opencode" / "tui.json").write_text(json.dumps({"theme": "tokyonight"}))
    (home / "agents").mkdir(parents=True)
    (home / "agents" / "reviewer.md").write_text("---\nname: reviewer\ndescription: r\ntools: Read\n---\nBody.\n")
    (home / "commands").mkdir(parents=True)
    (home / "commands" / "foo.md").write_text("---\ndescription: foo\n---\nRun foo.\n")
    (home / "skills").mkdir(parents=True)
    (home / "skills" / "uv").mkdir(parents=True)
    (home / "skills" / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody.\n")
    (home / "harnesses/pi").mkdir(parents=True)
    (home / "harnesses/pi" / "settings.json").write_text(json.dumps({"skills": ["~/.claude/skills"], "prompts": ["~/.claude/commands"]}))
    (home / "harnesses/goose").mkdir(parents=True)
    (home / "harnesses/goose" / "config.yaml").write_text("GOOSE_TELEMETRY_ENABLED: false\n")
    (home / "harnesses/goose" / "custom_providers").mkdir(parents=True)
    (home / "harnesses/goose" / "custom_providers" / "test.json").write_text(json.dumps({"name": "test"}))
    (home / "harnesses/gemini").mkdir(parents=True)
    (home / "harnesses/gemini" / "settings.json").write_text(json.dumps({"model": "gemini-3.7-flash"}))
    (home / "harnesses/codex").mkdir()
    (home / "harnesses/codex" / "config.toml").write_text('model = "test-model"\n')
    (home / "harnesses/no-mistakes").mkdir()
    (home / "harnesses/no-mistakes/config.yaml").write_text("{}")
    (home / "harnesses/claude").mkdir(parents=True)
    (home / "harnesses/claude/settings.json").write_text("{}")
    (home / "harnesses/opencode/plugins").mkdir()
    install_hook_sources(home)
    return home


runner = CliRunner()


def test_all_creates_everything(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    opencode = tmp_path / "config" / "opencode"
    pi_dir = tmp_path / "pi-agent"
    goose_dir = tmp_path / "goose-config"
    agy_dir = tmp_path / "gemini-config"
    agy_cli_dir = tmp_path / "gemini-cli"

    result = runner.invoke(app, ["--claude-dir", str(claude), "--opencode-dir", str(opencode), "--pi-dir", str(pi_dir), "--goose-dir", str(goose_dir), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "--codex-dir", str(tmp_path / "codex")])

    assert result.exit_code == 0
    assert (opencode / "opencode.json").is_file()
    assert (opencode / "tui.json").is_file()
    assert json.loads((opencode / "tui.json").read_text())["theme"] == "tokyonight"
    assert (opencode / "AGENTS.md").is_file()
    assert (opencode / "AGENTS.md").read_text().count("Extra rules.") == 1
    assert (opencode / "agents" / "reviewer.md").is_file()
    assert (opencode / "commands" / "foo.md").is_file()
    assert (opencode / "commands" / "uv.md").is_file()
    assert json.loads((pi_dir / "settings.json").read_text())["skills"] == ["~/.claude/skills"]
    assert "the `uv` skill" in (pi_dir / "CLAUDE.md").read_text()
    assert (goose_dir / ".goosehints").is_file()
    assert (goose_dir / "config.yaml").is_file()
    assert (goose_dir / "custom_providers" / "test.json").is_file()
    assert (agy_dir / "AGENTS.md").is_file()
    assert "the `uv` skill" in (agy_dir / "AGENTS.md").read_text()
    assert (agy_dir / "skills" / "uv").is_symlink()
    assert (agy_cli_dir / "settings.json").is_file()
    assert json.loads((agy_cli_dir / "settings.json").read_text())["model"] == "gemini-3.7-flash"
    assert (tmp_path / "codex" / "config.toml").read_text() == 'model = "test-model"\n'
    assert (tmp_path / "codex" / "AGENTS.md").is_file()


def test_all_exits_nonzero_on_conflict(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    opencode = tmp_path / "config" / "opencode"
    pi_dir = tmp_path / "pi-agent"
    goose_dir = tmp_path / "goose-config"
    agy_dir = tmp_path / "gemini-config"
    agy_cli_dir = tmp_path / "gemini-cli"
    opencode.mkdir(parents=True)
    (opencode / "AGENTS.md").write_text("Hand edited instructions")

    result = runner.invoke(app, ["--claude-dir", str(claude), "--opencode-dir", str(opencode), "--pi-dir", str(pi_dir), "--goose-dir", str(goose_dir), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "--codex-dir", str(tmp_path / "codex")])

    assert result.exit_code == 1


def test_force_resolves_conflicts(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    opencode = tmp_path / "config" / "opencode"
    pi_dir = tmp_path / "pi-agent"
    goose_dir = tmp_path / "goose-config"
    agy_dir = tmp_path / "gemini-config"
    agy_cli_dir = tmp_path / "gemini-cli"
    opencode.mkdir(parents=True)
    (opencode / "opencode.json").write_text(json.dumps({"hand": "edited"}))

    result = runner.invoke(app, ["--force", "--claude-dir", str(claude), "--opencode-dir", str(opencode), "--pi-dir", str(pi_dir), "--goose-dir", str(goose_dir), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "--codex-dir", str(tmp_path / "codex")])

    assert result.exit_code == 0
    assert json.loads((opencode / "opencode.json").read_text())["model"] == "test/model"


def test_check_exits_nonzero_on_drift_without_writing(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    opencode = tmp_path / "config" / "opencode"
    pi_dir = tmp_path / "pi-agent"
    goose_dir = tmp_path / "goose-config"
    agy_dir = tmp_path / "gemini-config"
    agy_cli_dir = tmp_path / "gemini-cli"

    result = runner.invoke(app, ["--check", "--claude-dir", str(claude), "--opencode-dir", str(opencode), "--pi-dir", str(pi_dir), "--goose-dir", str(goose_dir), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "--codex-dir", str(tmp_path / "codex")])

    assert result.exit_code == 1
    assert not (opencode / "opencode.json").exists()


def test_dry_run_creates_nothing(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    opencode = tmp_path / "config" / "opencode"
    pi_dir = tmp_path / "pi-agent"
    goose_dir = tmp_path / "goose-config"
    agy_dir = tmp_path / "gemini-config"
    agy_cli_dir = tmp_path / "gemini-cli"

    result = runner.invoke(app, ["--dry-run", "--claude-dir", str(claude), "--opencode-dir", str(opencode), "--pi-dir", str(pi_dir), "--goose-dir", str(goose_dir), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "--codex-dir", str(tmp_path / "codex")])

    assert result.exit_code == 1
    assert not (opencode / "opencode.json").exists()
    assert not (opencode / "AGENTS.md").exists()
    assert not (pi_dir / "settings.json").exists()
    assert not (goose_dir / ".goosehints").exists()
    assert not (agy_dir / "AGENTS.md").exists()


def test_opencode_agents_only(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    opencode = tmp_path / "config" / "opencode"
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(app, ["--claude-dir", str(claude), "--opencode-dir", str(opencode), "--pi-dir", str(pi_dir), "opencode", "agents"])

    assert result.exit_code == 0
    assert (opencode / "agents" / "reviewer.md").is_file()
    assert not (opencode / "opencode.json").exists()
    assert not (pi_dir / "settings.json").exists()


def test_opencode_config_only(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    opencode = tmp_path / "config" / "opencode"
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(app, ["--claude-dir", str(claude), "--opencode-dir", str(opencode), "--pi-dir", str(pi_dir), "opencode", "config"])

    assert result.exit_code == 0
    assert (opencode / "opencode.json").is_file()
    assert not (opencode / "AGENTS.md").exists()


def test_run_opencode_pure_returns_outcomes(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    opencode = tmp_path / "config" / "opencode"
    paths = Paths(source_dir=claude, opencode_dir=opencode)

    sync_outcomes, skills_outcomes = run_opencode(paths, force=False, dry_run=False)

    statuses = {o.status for o in sync_outcomes}
    from settings_sync.sync import Status

    assert Status.CREATED in statuses


def test_subcommand_flags_after_group(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    opencode = tmp_path / "config" / "opencode"
    pi_dir = tmp_path / "pi-agent"
    goose_dir = tmp_path / "goose-config"
    agy_dir = tmp_path / "gemini-config"
    agy_cli_dir = tmp_path / "gemini-cli"

    # --check on subcommand
    result_check = runner.invoke(app, ["--claude-dir", str(claude), "--opencode-dir", str(opencode), "--pi-dir", str(pi_dir), "--goose-dir", str(goose_dir), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "agy", "--check"])
    assert result_check.exit_code == 1
    assert not (agy_cli_dir / "settings.json").exists()

    # --force on subcommand
    result_force = runner.invoke(app, ["--claude-dir", str(claude), "--opencode-dir", str(opencode), "--pi-dir", str(pi_dir), "--goose-dir", str(goose_dir), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "agy", "--force"])
    assert result_force.exit_code == 0
    assert (agy_cli_dir / "settings.json").is_file()


def test_leaf_command_flags(tmp_path: pathlib.Path):
    claude = _make_claude_home(tmp_path)
    agy_dir = tmp_path / "gemini-config"
    agy_cli_dir = tmp_path / "gemini-cli"

    result = runner.invoke(app, ["--claude-dir", str(claude), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "agy", "settings", "--force"])
    assert result.exit_code == 0
    assert (agy_cli_dir / "settings.json").is_file()
    assert not (agy_dir / "AGENTS.md").exists()
