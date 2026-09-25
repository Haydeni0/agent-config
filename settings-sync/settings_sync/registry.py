"""Harness declarations shared by sync, diagnostics, and CLI registration."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from settings_sync.agents import sync_agents_dir
from settings_sync.agents_md import sync_agents_md
from settings_sync.agy import sync_agy_agents_md, sync_agy_settings, sync_agy_skills
from settings_sync.claude import claude_home, sync_claude_config, sync_claude_links, sync_shared_skills, sync_claude_entries
from settings_sync.commands import sync_commands
from settings_sync.codex import sync_codex_agents_md, sync_codex_config, sync_codex_sqlite_home
from settings_sync.config import sync_config, sync_tui
from settings_sync.goose import sync_goose_config, sync_goose_hints, sync_goose_providers
from settings_sync.hooks import sync_command_hooks
from settings_sync.nomistakes import sync_nomistakes_config
from settings_sync.ownership import sync_generated_symlink
from settings_sync.paths import Paths, config_home
from settings_sync.pi import sync_pi_config, sync_pi_context, sync_pi_keybindings
from settings_sync.plugins import sync_plugins
from settings_sync.skills import validate_skills
from settings_sync.sync import Outcome, Status


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    run: Callable[[Paths, bool, bool], list[Outcome]]
    required_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Harness:
    name: str
    steps: tuple[Step, ...]
    destination: Callable[[Paths], Path | None]
    host: str
    validate_skills: Callable[[Path], list[Outcome]] | None = None

    def available(self, paths: Paths) -> bool:
        return self.destination(paths) is not None


HARNESSES = (
    Harness("claude", (
        Step("config", lambda p, f, d: [sync_claude_config(p, d)], ("harnesses/claude/settings.json",)),
        Step("context", lambda p, f, d: [sync_agents_md(claude_home(p) / "CLAUDE.md", p.source_dir / "rules/global.md", f, d, source_root=p.source_dir, harness="claude")], ("rules/global.md",)),
        Step("links", lambda p, f, d: sync_claude_links(p, f, d), ("skills", "commands", "agents")),
    ), claude_home, "claude"),
    Harness("opencode", (
        Step("resources", lambda p, f, d: sync_claude_entries(p, ("skills",), f, d), ("skills",)),
        Step("config", lambda p, f, d: [sync_config(p.opencode_dir / "opencode.json", p.source_dir / "harnesses/opencode/opencode.json", f, d)], ("harnesses/opencode/opencode.json",)),
        Step("tui", lambda p, f, d: [sync_tui(p.opencode_dir / "tui.json", p.source_dir / "harnesses/opencode/tui.json", f, d)], ("harnesses/opencode/tui.json",)),
        Step("agents-md", lambda p, f, d: [sync_agents_md(p.opencode_dir / "AGENTS.md", p.source_dir / "rules/global.md", f, d, rules_path=p.source_dir / "harnesses/opencode/rules.md", source_root=p.source_dir, harness="opencode")], ("rules/global.md",)),
        Step("agents", lambda p, f, d: sync_agents_dir(p.opencode_dir / "agents", p.source_dir / "agents", f, d), ("agents",)),
        Step("commands", lambda p, f, d: sync_commands(p.opencode_dir / "commands", p.source_dir / "commands", p.source_dir / "skills", f, d), ("commands",)),
        Step("plugins", lambda p, f, d: sync_plugins(p.opencode_dir / "plugins", p.source_dir / "harnesses/opencode/plugins", (p.claude_home or Path.home() / ".claude") / "plugins/cache", f, d), ("harnesses/opencode/plugins",)),
    ), lambda p: p.opencode_dir, "opencode", validate_skills),
    Harness("pi", (
        Step("resources", lambda p, f, d: sync_claude_entries(p, ("skills", "commands"), f, d), ("skills", "commands")),
        Step("config", lambda p, f, d: [sync_pi_config(p.target("pi") / "settings.json", p.source_dir / "harnesses/pi/settings.json", d, source_root=p.source_dir, runtime_home=claude_home(p))], ("harnesses/pi/settings.json",)),
        Step("context", lambda p, f, d: [sync_pi_context(p.target("pi") / "CLAUDE.md", p.source_dir / "rules/global.md", f, d, source_root=p.source_dir)], ("rules/global.md",)),
        Step("keybindings", lambda p, f, d: [sync_pi_keybindings(p.target("pi") / "keybindings.json", p.source_dir / "harnesses/pi/keybindings.json", d, force=f)]),
    ), lambda p: p.pi_dir, "pi"),
    Harness("goose", (
        Step("hooks", lambda p, f, d: sync_command_hooks(p, "goose", d), ("harnesses/goose/hooks.json", "hooks/command.mjs")),
        Step("resources", lambda p, f, d: sync_claude_entries(p, ("skills", "agents"), f, d), ("skills", "agents")),
        Step("hints", lambda p, f, d: [sync_goose_hints(p.target("goose") / ".goosehints", p.source_dir / "rules/global.md", f, d, source_root=p.source_dir)], ("rules/global.md",)),
        Step("config", lambda p, f, d: [sync_goose_config(p.target("goose") / "config.yaml", p.source_dir / "harnesses/goose/config.yaml", f, d)], ("harnesses/goose/config.yaml",)),
        Step("providers", lambda p, f, d: sync_goose_providers(p.target("goose") / "custom_providers", p.source_dir / "harnesses/goose/custom_providers", f, d), ("harnesses/goose/custom_providers",)),
    ), lambda p: p.goose_dir, "goose"),
    Harness("agy", (
        Step("hooks", lambda p, f, d: sync_command_hooks(p, "agy", d), ("harnesses/gemini/hooks.json", "hooks/command.mjs")),
        Step("settings", lambda p, f, d: [sync_agy_settings((p.agy_cli_dir or p.target("agy")) / "settings.json", p.source_dir / "harnesses/gemini/settings.json", f, d)], ("harnesses/gemini/settings.json",)),
        Step("agents-md", lambda p, f, d: [sync_agy_agents_md(p.target("agy") / "AGENTS.md", p.source_dir / "rules/global.md", f, d, source_root=p.source_dir)], ("rules/global.md",)),
        Step("skills", lambda p, f, d: sync_agy_skills(p.target("agy") / "skills", p.source_dir / "skills", f, d), ("skills",)),
    ), lambda p: p.agy_dir, "agy"),
    Harness("no-mistakes", (
        Step("config", lambda p, f, d: [sync_nomistakes_config(p.target("nomistakes") / "config.yaml", p.source_dir / "harnesses/no-mistakes/config.yaml", config_home() / "agent-config/overlays/no-mistakes.yaml", d)], ("harnesses/no-mistakes/config.yaml",)),
    ), lambda p: p.nomistakes_dir, "no-mistakes"),
    Harness("codex", (
        Step("hooks", lambda p, f, d: sync_command_hooks(p, "codex", d), ("harnesses/codex/hooks.json", "hooks/command.mjs")),
        Step("skills", lambda p, f, d: sync_shared_skills(p, d), ("skills",)),
        Step("config", lambda p, f, d: [
            sync_codex_sqlite_home(p.source_dir / "harnesses/codex/config.toml", dry_run=d),
            sync_codex_config(p.target("codex") / "config.toml", p.source_dir / "harnesses/codex/config.toml", dry_run=d),
        ], ("harnesses/codex/config.toml",)),
        Step("agents-md", lambda p, f, d: [sync_codex_agents_md(p.target("codex") / "AGENTS.md", p.source_dir / "rules/global.md", f, d, source_root=p.source_dir)], ("rules/global.md",)),
    ), lambda p: p.codex_dir, "codex"),
)


def select_harnesses(name: str | None) -> tuple[Harness, ...]:
    if name is None or name == "all":
        return HARNESSES
    for harness in HARNESSES:
        if harness.name == name:
            return (harness,)
    raise ValueError(f"unknown harness {name!r}; choose {', '.join(h.name for h in HARNESSES)}")


def run_harness(harness: Harness, paths: Paths, force: bool, dry_run: bool, steps: tuple[str, ...] | None = None) -> list[Outcome]:
    if not harness.available(paths):
        return []
    selected = harness.steps if steps is None else tuple(step for step in harness.steps if step.name in steps)
    if steps is not None and set(steps) - {step.name for step in selected}:
        raise ValueError(f"unknown step for {harness.name}: {steps}")
    outcomes: list[Outcome] = []
    for step in selected:
        missing = [paths.source_dir / name for name in step.required_sources if not (paths.source_dir / name).exists()]
        if missing:
            outcomes.extend(Outcome(path, Status.FAILED, f"required source missing for {harness.name} {step.name}; restore it in the source checkout") for path in missing)
            continue
        try:
            outcomes.extend(step.run(paths, force, dry_run))
        except (OSError, ValueError) as exc:
            outcomes.append(Outcome(paths.source_dir, Status.FAILED, f"{harness.name} {step.name}: {exc}"))
    return outcomes


def run_all_tools(paths: Paths, force: bool, dry_run: bool) -> tuple[list[Outcome], list[Outcome]]:
    return [outcome for harness in HARNESSES for outcome in run_harness(harness, paths, force, dry_run)], []


def run_opencode(paths: Paths, force: bool, dry_run: bool, steps: tuple[str, ...] | None = None) -> tuple[list[Outcome], list[Outcome]]:
    return run_harness(select_harnesses("opencode")[0], paths, force, dry_run, steps), []
