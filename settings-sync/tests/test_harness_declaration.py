"""One Harness declaration drives every surface (REQ-HARNESS-04, REQ-SYNC-08). S41-S47."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.actions import File
from settings_sync.cli import build_app
from settings_sync.hooks import HookSpec
from settings_sync.paths import resolve_paths
from settings_sync.registry import BootstrapSpec, Destination, Harness, Step


def fake_registry(node_required: bool = False, alias: str | None = "fake") -> tuple[Harness, ...]:
    fake = Harness(
        name="fake",
        destinations=(Destination("fake_dir", "--fake-dir", "FAKE_DIR", lambda home, config: home / "fake"),),
        host="fake",
        steps=(Step("greet", plan=lambda p: [File(p.fake_dir / "hello.txt", "hello\n")]),),
        hooks=HookSpec("fake", "hooks", plugin=False) if node_required else None,
        node_required=node_required,
        bootstrap=BootstrapSpec(mode="installer"),
        alias=alias,
    )
    return (fake,)


def test_every_surface_picks_up_a_new_declaration(source_home: Path, isolated_home: Path) -> None:
    """S41: --fake-dir sync, all-sync, check drift, doctor all expose the fake harness."""
    app = build_app(fake_registry())
    runner = CliRunner()
    result = runner.invoke(app, ["--source", str(source_home), "--fake-dir", str(isolated_home / "x"), "sync", "fake"])
    assert result.exit_code == 0, result.output
    assert (isolated_home / "x" / "hello.txt").read_text() == "hello\n"
    result = runner.invoke(app, ["--source", str(source_home), "sync"])
    assert result.exit_code == 0, result.output
    (isolated_home / "fake" / "hello.txt").unlink()
    result = runner.invoke(app, ["--source", str(source_home), "check", "fake"])
    assert result.exit_code == 1, result.output
    result = runner.invoke(app, ["--source", str(source_home), "sync", "fake"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["--source", str(source_home), "check", "fake"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["--source", str(source_home), "doctor", "fake"])
    assert "fake" in result.output


def test_destination_precedence_flag_env_default(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S42: flag > env > default per declaration."""
    source = isolated_home / "source"
    source.mkdir()
    (fake,) = fake_registry()
    monkeypatch.delenv("FAKE_DIR", raising=False)
    paths = resolve_paths((fake,), claude_dir=source)
    assert paths.fake_dir == isolated_home / "fake"
    monkeypatch.setenv("FAKE_DIR", str(isolated_home / "from-env"))
    paths = resolve_paths((fake,), claude_dir=source)
    assert paths.fake_dir == isolated_home / "from-env"
    paths = resolve_paths((fake,), claude_dir=source, fake_dir=isolated_home / "from-flag")
    assert paths.fake_dir == isolated_home / "from-flag"


def test_doctor_node_line_follows_the_declaration(source_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S43: a declaration with a hook adapter requires Node; without one, no Node line."""
    monkeypatch.setenv("PATH", "/nonexistent")
    runner = CliRunner()
    result = runner.invoke(build_app(fake_registry(node_required=True)), ["--source", str(source_home), "doctor", "fake"])
    assert "Node.js" in result.output
    result = runner.invoke(build_app(fake_registry(node_required=False)), ["--source", str(source_home), "doctor", "fake"])
    assert "Node.js" not in result.output


def test_claude_links_gains_registry_aliases(source_home: Path, isolated_home: Path) -> None:
    """S44: every non-Claude harness with a source directory gets its ~/.claude/<alias> link."""
    from settings_sync.actions import Mode
    from settings_sync.executor import execute
    from settings_sync.ownership import OwnershipStore
    from settings_sync.registry import HARNESSES, plan_claude_links

    (source_home / "harnesses/fake").mkdir(parents=True)
    harnesses = tuple(h for h in HARNESSES if h.name != "codegraph") + fake_registry()
    paths = resolve_paths(harnesses, claude_dir=source_home, claude_home=isolated_home / ".claude")
    store = OwnershipStore()
    store.load(Mode.APPLY)
    execute(plan_claude_links(paths, harnesses), Mode.APPLY, store)
    assert (isolated_home / ".claude/fake").is_symlink()
    assert (isolated_home / ".claude/gemini").is_symlink()
    assert (isolated_home / ".claude/codex").is_symlink()
