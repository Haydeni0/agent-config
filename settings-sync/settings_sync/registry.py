"""Harness declarations shared by sync, diagnostics, and CLI registration."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from settings_sync.agents import plan_agents_dir
from settings_sync.agents_md import plan_agents_md
from settings_sync.agy import plan_agy_settings, plan_agy_skills
from settings_sync.claude import plan_claude_config, plan_claude_entries, plan_claude_links, plan_shared_skills
from settings_sync.codegraph import plan_agy_mcp, plan_claude_mcp, plan_codegraph_binary, plan_codegraph_telemetry, plan_pi_mcp
from settings_sync.commands import plan_commands
from settings_sync.codex import plan_codex_config
from settings_sync.config import plan_opencode_config, plan_opencode_tui
from settings_sync.goose import plan_goose_config, plan_goose_providers
from settings_sync.hooks import plan_command_hooks
from settings_sync.nomistakes import plan_nomistakes_config
from settings_sync.skills import validate_skills
from settings_sync.paths import Paths
from settings_sync.pi import plan_pi_config, plan_pi_keybindings
from settings_sync.plugins import plan_plugins
from settings_sync.actions import Action, Outcome, Report, Status


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    plan: Callable[[Paths], list[Action]]
    required_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Harness:
    name: str
    steps: tuple[Step, ...]
    destination: Callable[[Paths], Path | None]
    host: str

    def available(self, paths: Paths) -> bool:
        return self.destination(paths) is not None


HARNESSES = (
    Harness("codegraph", (
        Step("binary", plan=plan_codegraph_binary),
        Step("claude-mcp", plan=plan_claude_mcp),
        Step("telemetry", plan=plan_codegraph_telemetry),
    ), lambda p: p.codegraph_dir, "codegraph"),
    Harness("claude", (
        Step("config", plan=plan_claude_config, required_sources=("harnesses/claude/settings.json",)),
        Step("context", plan=lambda p: plan_agents_md(p.claude_home / "CLAUDE.md", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="claude"), required_sources=("rules/global.md",)),
        Step("links", plan=plan_claude_links, required_sources=("skills", "commands", "agents")),
    ), lambda p: p.claude_home, "claude"),
    Harness("opencode", (
        Step("resources", plan=lambda p: plan_claude_entries(p, ("skills",)), required_sources=("skills",)),
        Step("config", plan=plan_opencode_config, required_sources=("harnesses/opencode/opencode.json",)),
        Step("tui", plan=plan_opencode_tui, required_sources=("harnesses/opencode/tui.json",)),
        Step("agents-md", plan=lambda p: plan_agents_md(p.opencode_dir / "AGENTS.md", p.source_dir / "rules/global.md", rules_path=p.source_dir / "harnesses/opencode/rules.md", source_root=p.source_dir, harness="opencode"), required_sources=("rules/global.md",)),
        Step("agents", plan=lambda p: plan_agents_dir(p.opencode_dir / "agents", p.source_dir / "agents"), required_sources=("agents",)),
        Step("commands", plan=lambda p: plan_commands(p.opencode_dir / "commands", p.source_dir / "commands", p.source_dir / "skills"), required_sources=("commands",)),
        Step("plugins", plan=lambda p: plan_plugins(p.opencode_dir / "plugins", p.source_dir / "harnesses/opencode/plugins", p.claude_home / "plugins/cache"), required_sources=("harnesses/opencode/plugins",)),
        Step("skills", plan=lambda p: [Report(o.path, o.status, o.detail) for o in validate_skills(p.source_dir / "skills")]),
    ), lambda p: p.opencode_dir, "opencode"),
    Harness("pi", (
        Step("resources", plan=lambda p: plan_claude_entries(p, ("skills", "commands")), required_sources=("skills", "commands")),
        Step("config", plan=plan_pi_config, required_sources=("harnesses/pi/settings.json",)),
        Step("mcp", plan=plan_pi_mcp, required_sources=("harnesses/pi/mcp.json",)),
        Step("context", plan=lambda p: plan_agents_md(p.target("pi") / "CLAUDE.md", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="pi"), required_sources=("rules/global.md",)),
        Step("keybindings", plan=plan_pi_keybindings),
    ), lambda p: p.pi_dir, "pi"),
    Harness("goose", (
        Step("hooks", plan=lambda p: plan_command_hooks(p, "goose"), required_sources=("harnesses/goose/hooks.json", "hooks/command.mjs")),
        Step("resources", plan=lambda p: plan_claude_entries(p, ("skills", "agents")), required_sources=("skills", "agents")),
        Step("hints", plan=lambda p: plan_agents_md(p.target("goose") / ".goosehints", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="goose"), required_sources=("rules/global.md",)),
        Step("config", plan=plan_goose_config, required_sources=("harnesses/goose/config.yaml",)),
        Step("providers", plan=plan_goose_providers, required_sources=("harnesses/goose/custom_providers",)),
    ), lambda p: p.goose_dir, "goose"),
    Harness("agy", (
        Step("hooks", plan=lambda p: plan_command_hooks(p, "agy"), required_sources=("harnesses/gemini/hooks.json", "hooks/command.mjs")),
        Step("settings", plan=plan_agy_settings, required_sources=("harnesses/gemini/settings.json",)),
        Step("mcp", plan=plan_agy_mcp),
        Step("agents-md", plan=lambda p: plan_agents_md(p.target("agy") / "AGENTS.md", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="agy"), required_sources=("rules/global.md",)),
        Step("skills", plan=plan_agy_skills, required_sources=("skills",)),
    ), lambda p: p.agy_dir, "agy"),
    Harness("no-mistakes", (
        Step("config", plan=plan_nomistakes_config, required_sources=("harnesses/no-mistakes/config.yaml",)),
    ), lambda p: p.nomistakes_dir, "no-mistakes"),
    Harness("codex", (
        Step("hooks", plan=lambda p: plan_command_hooks(p, "codex"), required_sources=("harnesses/codex/hooks.json", "hooks/command.mjs")),
        Step("skills", plan=plan_shared_skills, required_sources=("skills",)),
        Step("config", plan=plan_codex_config, required_sources=("harnesses/codex/config.toml",)),
        Step("agents-md", plan=lambda p: plan_agents_md(p.target("codex") / "AGENTS.md", p.source_dir / "rules/global.md", source_root=p.source_dir, harness="codex"), required_sources=("rules/global.md",)),
    ), lambda p: p.codex_dir, "codex"),
)


def select_harnesses(name: str | None) -> tuple[Harness, ...]:
    if name is None or name == "all":
        return HARNESSES
    for harness in HARNESSES:
        if harness.name == name:
            return (harness,)
    raise ValueError(f"unknown harness {name!r}; choose {', '.join(h.name for h in HARNESSES)}")
