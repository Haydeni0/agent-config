"""Harness declarations: one entry drives CLI, doctor, hooks, links, and bootstrap."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from settings_sync.actions import Action, Report, Status, Symlink
from settings_sync.agents import plan_agents_dir
from settings_sync.agents_md import plan_agents_md
from settings_sync.agy import plan_agy_settings, plan_agy_skills
from settings_sync.claude import plan_claude_config, plan_claude_entries, plan_shared_skills
from settings_sync.codegraph import plan_agy_mcp, plan_claude_mcp, plan_codegraph_binary, plan_codegraph_telemetry, plan_pi_mcp
from settings_sync.commands import plan_commands
from settings_sync.codex import plan_codex_config
from settings_sync.config import plan_opencode_config, plan_opencode_tui
from settings_sync.goose import plan_goose_config, plan_goose_providers
from settings_sync.hooks import HookSpec, plan_command_hooks
from settings_sync.nomistakes import plan_nomistakes_config
from settings_sync.paths import Paths
from settings_sync.pi import plan_pi_config, plan_pi_keybindings
from settings_sync.plugins import plan_plugins
from settings_sync.skills import validate_skills


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    plan: Callable[[Paths], list[Action]]
    required_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Destination:
    attr: str  # Paths field name, e.g. "goose_dir"
    option: str  # CLI flag, e.g. "--goose-dir"
    env: str | None  # resolution env var, e.g. "CODEX_HOME"
    default: Callable[[Path, Path], Path]  # (home, xdg_config) -> default dir


@dataclass(frozen=True, slots=True)
class BootstrapSpec:
    mode: Literal["installer", "host-check", "explicit"]  # no-mistakes = explicit
    env: tuple[tuple[str, str], ...] = ()  # (env var, Paths attr) pairs


@dataclass(frozen=True, slots=True)
class Harness:
    name: str
    destinations: tuple[Destination, ...]  # first is the harness home (doctor, availability)
    host: str
    steps: tuple[Step, ...]
    hooks: HookSpec | None
    node_required: bool
    bootstrap: BootstrapSpec
    alias: str | None  # ~/.claude/<alias> link; None = no link

    def destination(self, paths: Paths) -> Path | None:
        return getattr(paths, self.destinations[0].attr)


_GOOSE_HOOKS = HookSpec("goose", "hooks", plugin=True)
_AGY_HOOKS = HookSpec("gemini", "agent-config", plugin=False)
_CODEX_HOOKS = HookSpec("codex", "hooks", plugin=False)

HARNESSES = (
    Harness(
        name="codegraph",
        destinations=(Destination("codegraph_dir", "--codegraph-dir", None, lambda home, config: home / ".codegraph"),),
        host="codegraph",
        steps=(
            Step("binary", plan=plan_codegraph_binary),
            Step("claude-mcp", plan=plan_claude_mcp),
            Step("telemetry", plan=plan_codegraph_telemetry),
        ),
        hooks=None,
        node_required=False,
        bootstrap=BootstrapSpec(mode="host-check"),
        alias=None,
    ),
    Harness(
        name="claude",
        destinations=(Destination("claude_home", "--claude-home", "CLAUDE_CONFIG_DIR", lambda home, config: home / ".claude"),),
        host="claude",
        steps=(
            Step("config", plan=plan_claude_config, required_sources=("harnesses/claude/settings.json",)),
            Step("context", plan=lambda p: plan_agents_md(p.claude_home / "CLAUDE.md", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="claude"), required_sources=("rules/global.md",)),
            Step("links", plan=lambda p: plan_claude_links(p, HARNESSES), required_sources=("skills", "commands", "agents")),
        ),
        hooks=None,
        node_required=True,
        bootstrap=BootstrapSpec(mode="installer"),
        alias=None,
    ),
    Harness(
        name="opencode",
        destinations=(Destination("opencode_dir", "--opencode-dir", "OPENCODE_CONFIG_DIR", lambda home, config: config / "opencode"),),
        host="opencode",
        steps=(
            Step("resources", plan=lambda p: plan_claude_entries(p, ("skills",)), required_sources=("skills",)),
            Step("config", plan=plan_opencode_config, required_sources=("harnesses/opencode/opencode.json",)),
            Step("tui", plan=plan_opencode_tui, required_sources=("harnesses/opencode/tui.json",)),
            Step("agents-md", plan=lambda p: plan_agents_md(p.opencode_dir / "AGENTS.md", p.source_dir / "rules/global.md", rules_path=p.source_dir / "harnesses/opencode/rules.md", source_root=p.source_dir, harness="opencode"), required_sources=("rules/global.md",)),
            Step("agents", plan=lambda p: plan_agents_dir(p.opencode_dir / "agents", p.source_dir / "agents"), required_sources=("agents",)),
            Step("commands", plan=lambda p: plan_commands(p.opencode_dir / "commands", p.source_dir / "commands", p.source_dir / "skills"), required_sources=("commands",)),
            Step("plugins", plan=lambda p: plan_plugins(p.opencode_dir / "plugins", p.source_dir / "harnesses/opencode/plugins", p.claude_home / "plugins/cache"), required_sources=("harnesses/opencode/plugins",)),
            Step("skills", plan=lambda p: [Report(o.path, o.status, o.detail) for o in validate_skills(p.source_dir / "skills")]),
        ),
        hooks=None,
        node_required=False,
        bootstrap=BootstrapSpec(mode="installer", env=(("OPENCODE_CONFIG_DIR", "opencode_dir"),)),
        alias="opencode",
    ),
    Harness(
        name="pi",
        destinations=(Destination("pi_dir", "--pi-dir", "PI_CODING_AGENT_DIR", lambda home, config: home / ".pi" / "agent"),),
        host="pi",
        steps=(
            Step("resources", plan=lambda p: plan_claude_entries(p, ("skills", "commands")), required_sources=("skills", "commands")),
            Step("config", plan=plan_pi_config, required_sources=("harnesses/pi/settings.json",)),
            Step("mcp", plan=plan_pi_mcp, required_sources=("harnesses/pi/mcp.json",)),
            Step("context", plan=lambda p: plan_agents_md(p.target("pi") / "CLAUDE.md", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="pi"), required_sources=("rules/global.md",)),
            Step("keybindings", plan=plan_pi_keybindings),
        ),
        hooks=None,
        node_required=False,
        bootstrap=BootstrapSpec(mode="installer", env=(("AGENT_CONFIG_PI_HOME", "pi_dir"),)),
        alias="pi",
    ),
    Harness(
        name="goose",
        destinations=(Destination("goose_dir", "--goose-dir", None, lambda home, config: config / "goose"),),
        host="goose",
        steps=(
            Step("hooks", plan=lambda p: plan_command_hooks(p, "goose", _GOOSE_HOOKS), required_sources=("harnesses/goose/hooks.json", "hooks/command.mjs")),
            Step("resources", plan=lambda p: plan_claude_entries(p, ("skills", "agents")), required_sources=("skills", "agents")),
            Step("hints", plan=lambda p: plan_agents_md(p.target("goose") / ".goosehints", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="goose"), required_sources=("rules/global.md",)),
            Step("config", plan=plan_goose_config, required_sources=("harnesses/goose/config.yaml",)),
            Step("providers", plan=plan_goose_providers, required_sources=("harnesses/goose/custom_providers",)),
        ),
        hooks=_GOOSE_HOOKS,
        node_required=True,
        bootstrap=BootstrapSpec(mode="host-check"),
        alias="goose",
    ),
    Harness(
        name="agy",
        destinations=(
            Destination("agy_dir", "--agy-dir", None, lambda home, config: home / ".gemini" / "config"),
            Destination("agy_cli_dir", "--agy-cli-dir", None, lambda home, config: home / ".gemini" / "antigravity-cli"),
        ),
        host="agy",
        steps=(
            Step("hooks", plan=lambda p: plan_command_hooks(p, "agy", _AGY_HOOKS), required_sources=("harnesses/gemini/hooks.json", "hooks/command.mjs")),
            Step("settings", plan=plan_agy_settings, required_sources=("harnesses/gemini/settings.json",)),
            Step("mcp", plan=plan_agy_mcp),
            Step("agents-md", plan=lambda p: plan_agents_md(p.target("agy") / "AGENTS.md", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="agy"), required_sources=("rules/global.md",)),
            Step("skills", plan=plan_agy_skills, required_sources=("skills",)),
        ),
        hooks=_AGY_HOOKS,
        node_required=True,
        bootstrap=BootstrapSpec(mode="host-check"),
        alias="gemini",
    ),
    Harness(
        name="no-mistakes",
        destinations=(Destination("nomistakes_dir", "--nomistakes-dir", None, lambda home, config: home / ".no-mistakes"),),
        host="no-mistakes",
        steps=(
            Step("config", plan=plan_nomistakes_config, required_sources=("harnesses/no-mistakes/config.yaml",)),
        ),
        hooks=None,
        node_required=False,
        bootstrap=BootstrapSpec(mode="explicit", env=(("AGENT_CONFIG_NOMISTAKES_HOME", "nomistakes_dir"),)),
        alias="no-mistakes",
    ),
    Harness(
        name="codex",
        destinations=(Destination("codex_dir", "--codex-dir", "CODEX_HOME", lambda home, config: home / ".codex"),),
        host="codex",
        steps=(
            Step("hooks", plan=lambda p: plan_command_hooks(p, "codex", _CODEX_HOOKS), required_sources=("harnesses/codex/hooks.json", "hooks/command.mjs")),
            Step("skills", plan=plan_shared_skills, required_sources=("skills",)),
            Step("config", plan=plan_codex_config, required_sources=("harnesses/codex/config.toml",)),
            Step("agents-md", plan=lambda p: plan_agents_md(p.target("codex") / "AGENTS.md", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="codex"), required_sources=("rules/global.md",)),
        ),
        hooks=_CODEX_HOOKS,
        node_required=True,
        bootstrap=BootstrapSpec(mode="host-check"),
        alias="codex",
    ),
)

_REPO_ALIASES = (
    ("custom", "custom"), ("hooks", "hooks"),
    ("statusline-command.sh", "harnesses/claude/statusline-command.sh"),
    ("settings-sync", "settings-sync"), ("opencode-resume", "opencode-resume"),
    ("README.md", "README.md"), ("sync.sh", "sync.sh"), ("scripts", "scripts"),
)


def plan_claude_links(paths: Paths, harnesses: tuple[Harness, ...]) -> list[Action]:
    """Claude's linked entries plus per-harness aliases derived from the declarations."""
    actions = plan_claude_entries(paths, ("skills", "commands", "agents"))
    actions.extend(
        Symlink(paths.claude_home / alias, paths.source_dir / source)
        for alias, source in _REPO_ALIASES
        if (paths.source_dir / source).exists()
    )
    for harness in harnesses:
        if harness.alias is None or harness.name == "claude":
            continue
        source_dir = harness.hooks.source_dir if harness.hooks else harness.name
        entry = paths.source_dir / "harnesses" / source_dir
        if entry.exists():
            actions.append(Symlink(paths.claude_home / harness.alias, entry))
    return actions


def select_harnesses(name: str | None, harnesses: tuple[Harness, ...] | None = None) -> tuple[Harness, ...]:
    declarations = HARNESSES if harnesses is None else harnesses
    if name is None or name == "all":
        return declarations
    for harness in declarations:
        if harness.name == name:
            return (harness,)
    raise ValueError(f"unknown harness {name!r}; choose {', '.join(h.name for h in declarations)}")
