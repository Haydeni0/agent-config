"""CLI entrypoint: sync ~/.claude config into opencode, pi, goose, agy, codex, and no-mistakes.

~/.claude is the single source of truth. `sync opencode` derives config
into ~/.config/opencode; `sync pi` writes pointers + inlined context
into ~/.pi/agent; `sync goose` writes hints + config + providers into
~/.config/goose; `sync agy` writes rules + skills into ~/.gemini/config;
`sync codex` merges shared config.toml defaults + writes AGENTS.md into ~/.codex;
`sync no-mistakes` merges the config template + machine overlay into
~/.no-mistakes/config.yaml. Bare `sync` (or `sync all`) runs all six.
"""

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from settings_sync.agents import sync_agents_dir
from settings_sync.agents_md import sync_agents_md
from settings_sync.agy import sync_agy_agents_md, sync_agy_settings, sync_agy_skills
from settings_sync.commands import sync_commands
from settings_sync.codex import sync_codex_agents_md, sync_codex_config
from settings_sync.config import sync_config, sync_tui
from settings_sync.goose import sync_goose_config, sync_goose_hints, sync_goose_providers
from settings_sync.nomistakes import sync_nomistakes_config
from settings_sync.pi import sync_pi_config, sync_pi_context, sync_pi_keybindings
from settings_sync.plugins import sync_superpowers
from settings_sync.skills import validate_skills
from settings_sync.sync import Outcome, Status

app = typer.Typer(add_completion=False, no_args_is_help=False)
opencode_app = typer.Typer(add_completion=False, no_args_is_help=False, help="Sync opencode config.")
pi_app = typer.Typer(add_completion=False, no_args_is_help=False, help="Sync pi config.")
goose_app = typer.Typer(add_completion=False, no_args_is_help=False, help="Sync goose config.")
agy_app = typer.Typer(add_completion=False, no_args_is_help=False, help="Sync agy config.")
nomistakes_app = typer.Typer(add_completion=False, no_args_is_help=False, help="Sync no-mistakes config.")
codex_app = typer.Typer(add_completion=False, no_args_is_help=False, help="Sync codex config.")

OPENCODE_STEPS = ("config", "tui", "agents-md", "agents", "commands", "plugins")
PI_STEPS = ("config", "context", "keybindings")
GOOSE_STEPS = ("hints", "config", "providers")
AGY_STEPS = ("settings", "agents-md", "skills")
NOMISTAKES_STEPS = ("config",)
CODEX_STEPS = ("config", "agents-md")


@dataclass(slots=True, frozen=True)
class Paths:
    claude_dir: Path
    opencode_dir: Path
    pi_dir: Path | None = None
    goose_dir: Path | None = None
    agy_dir: Path | None = None
    agy_cli_dir: Path | None = None
    nomistakes_dir: Path | None = None
    codex_dir: Path | None = None


def run_opencode_step(name: str, paths: Paths, force: bool, dry_run: bool) -> list[Outcome]:
    if name == "config":
        return [sync_config(paths.opencode_dir / "opencode.json", paths.claude_dir / "opencode" / "opencode.json", force, dry_run)]
    if name == "tui":
        return [sync_tui(paths.opencode_dir / "tui.json", paths.claude_dir / "opencode" / "tui.json", force, dry_run)]
    if name == "agents-md":
        return [sync_agents_md(paths.opencode_dir / "AGENTS.md", paths.claude_dir / "CLAUDE.md", force, dry_run, rules_path=paths.claude_dir / "opencode" / "rules.md")]
    if name == "agents":
        return sync_agents_dir(paths.opencode_dir / "agents", paths.claude_dir / "agents", force, dry_run)
    if name == "commands":
        return sync_commands(
            paths.opencode_dir / "commands",
            paths.claude_dir / "commands",
            paths.claude_dir / "skills",
            force,
            dry_run,
        )
    if name == "plugins":
        cache = paths.claude_dir / "plugins" / "cache"
        return [sync_superpowers(paths.opencode_dir / "plugins" / "superpowers.js", cache, force, dry_run)]
    raise ValueError(f"unknown opencode step: {name}")


def run_pi_step(name: str, paths: Paths, force: bool, dry_run: bool) -> list[Outcome]:
    if paths.pi_dir is None:
        raise ValueError("pi_dir is required for pi steps")
    if name == "config":
        return [sync_pi_config(paths.pi_dir / "settings.json", paths.claude_dir / "pi" / "settings.json", dry_run)]
    if name == "context":
        return [sync_pi_context(paths.pi_dir / "CLAUDE.md", paths.claude_dir / "CLAUDE.md", force, dry_run)]
    if name == "keybindings":
        return [sync_pi_keybindings(paths.pi_dir / "keybindings.json", paths.claude_dir / "pi" / "keybindings.json", dry_run)]
    raise ValueError(f"unknown pi step: {name}")


def run_goose_step(name: str, paths: Paths, force: bool, dry_run: bool) -> list[Outcome]:
    if paths.goose_dir is None:
        raise ValueError("goose_dir is required for goose steps")
    if name == "hints":
        return [sync_goose_hints(paths.goose_dir / ".goosehints", paths.claude_dir / "CLAUDE.md", force, dry_run)]
    if name == "config":
        return [sync_goose_config(paths.goose_dir / "config.yaml", paths.claude_dir / "goose" / "config.yaml", force, dry_run)]
    if name == "providers":
        return sync_goose_providers(paths.goose_dir / "custom_providers", paths.claude_dir / "goose" / "custom_providers", force, dry_run)
    raise ValueError(f"unknown goose step: {name}")


def run_nomistakes_step(name: str, paths: Paths, force: bool, dry_run: bool) -> list[Outcome]:
    if paths.nomistakes_dir is None:
        raise ValueError("nomistakes_dir is required for no-mistakes steps")
    if name == "config":
        return [sync_nomistakes_config(paths.nomistakes_dir / "config.yaml", paths.claude_dir / "no-mistakes" / "config.yaml", paths.claude_dir / "no-mistakes" / "config.local.yaml", dry_run)]
    raise ValueError(f"unknown no-mistakes step: {name}")


def run_nomistakes(paths: Paths, force: bool, dry_run: bool, steps: tuple[str, ...] = NOMISTAKES_STEPS) -> tuple[list[Outcome], list[Outcome]]:
    sync_outcomes: list[Outcome] = []
    for step in steps:
        sync_outcomes.extend(run_nomistakes_step(step, paths, force, dry_run))
    skills_outcomes = validate_skills(paths.claude_dir / "skills")
    return sync_outcomes, skills_outcomes


def run_agy_step(name: str, paths: Paths, force: bool, dry_run: bool) -> list[Outcome]:
    if paths.agy_dir is None:
        raise ValueError("agy_dir is required for agy steps")
    if name == "settings":
        target = (paths.agy_cli_dir / "settings.json") if paths.agy_cli_dir else (paths.agy_dir / "settings.json")
        return [sync_agy_settings(target, paths.claude_dir / "gemini" / "settings.json", force, dry_run)]
    if name == "agents-md":
        return [sync_agy_agents_md(paths.agy_dir / "AGENTS.md", paths.claude_dir / "CLAUDE.md", force, dry_run)]
    if name == "skills":
        return sync_agy_skills(paths.agy_dir / "skills", paths.claude_dir / "skills", force, dry_run)
    raise ValueError(f"unknown agy step: {name}")


def run_codex_step(name: str, paths: Paths, force: bool, dry_run: bool) -> list[Outcome]:
    if paths.codex_dir is None:
        raise ValueError("codex_dir is required for codex steps")
    if name == "config":
        return [sync_codex_config(paths.codex_dir / "config.toml", paths.claude_dir / "codex" / "config.toml", dry_run=dry_run)]
    if name == "agents-md":
        return [sync_codex_agents_md(paths.codex_dir / "AGENTS.md", paths.claude_dir / "CLAUDE.md", force, dry_run)]
    raise ValueError(f"unknown codex step: {name}")


def run_opencode(paths: Paths, force: bool, dry_run: bool, steps: tuple[str, ...] = OPENCODE_STEPS) -> tuple[list[Outcome], list[Outcome]]:
    sync_outcomes: list[Outcome] = []
    for step in steps:
        sync_outcomes.extend(run_opencode_step(step, paths, force, dry_run))
    skills_outcomes = validate_skills(paths.claude_dir / "skills")
    return sync_outcomes, skills_outcomes


def run_pi(paths: Paths, force: bool, dry_run: bool, steps: tuple[str, ...] = PI_STEPS) -> tuple[list[Outcome], list[Outcome]]:
    sync_outcomes: list[Outcome] = []
    for step in steps:
        sync_outcomes.extend(run_pi_step(step, paths, force, dry_run))
    skills_outcomes = validate_skills(paths.claude_dir / "skills")
    return sync_outcomes, skills_outcomes


def run_goose(paths: Paths, force: bool, dry_run: bool, steps: tuple[str, ...] = GOOSE_STEPS) -> tuple[list[Outcome], list[Outcome]]:
    sync_outcomes: list[Outcome] = []
    for step in steps:
        sync_outcomes.extend(run_goose_step(step, paths, force, dry_run))
    skills_outcomes = validate_skills(paths.claude_dir / "skills")
    return sync_outcomes, skills_outcomes


def run_agy(paths: Paths, force: bool, dry_run: bool, steps: tuple[str, ...] = AGY_STEPS) -> tuple[list[Outcome], list[Outcome]]:
    sync_outcomes: list[Outcome] = []
    for step in steps:
        sync_outcomes.extend(run_agy_step(step, paths, force, dry_run))
    skills_outcomes = validate_skills(paths.claude_dir / "skills")
    return sync_outcomes, skills_outcomes


def run_codex(paths: Paths, force: bool, dry_run: bool, steps: tuple[str, ...] = CODEX_STEPS) -> tuple[list[Outcome], list[Outcome]]:
    sync_outcomes: list[Outcome] = []
    for step in steps:
        sync_outcomes.extend(run_codex_step(step, paths, force, dry_run))
    return sync_outcomes, []


def run_all_tools(paths: Paths, force: bool, dry_run: bool) -> tuple[list[Outcome], list[Outcome]]:
    sync_outcomes: list[Outcome] = []
    for step in OPENCODE_STEPS:
        sync_outcomes.extend(run_opencode_step(step, paths, force, dry_run))
    for step in PI_STEPS:
        sync_outcomes.extend(run_pi_step(step, paths, force, dry_run))
    if paths.goose_dir is not None:
        for step in GOOSE_STEPS:
            sync_outcomes.extend(run_goose_step(step, paths, force, dry_run))
    if paths.agy_dir is not None:
        for step in AGY_STEPS:
            sync_outcomes.extend(run_agy_step(step, paths, force, dry_run))
    if paths.nomistakes_dir is not None:
        for step in NOMISTAKES_STEPS:
            sync_outcomes.extend(run_nomistakes_step(step, paths, force, dry_run))
    if paths.codex_dir is not None:
        for step in CODEX_STEPS:
            sync_outcomes.extend(run_codex_step(step, paths, force, dry_run))
    skills_outcomes = validate_skills(paths.claude_dir / "skills")
    return sync_outcomes, skills_outcomes


_FAILURE_STATES = {Status.SKIPPED, Status.FAILED, Status.WARNED, Status.WOULD_CREATE, Status.WOULD_REPLACE, Status.WOULD_SKIP}


def exit_code(sync_outcomes: list[Outcome]) -> int:
    return 1 if any(o.status in _FAILURE_STATES for o in sync_outcomes) else 0


def _run_skills(ctx: typer.Context) -> int:
    """Run validate_skills and report. One exit-code policy for all skills invocations."""
    paths = _ctx_paths(ctx)
    _, _, _, verbose = _ctx_flags(ctx)
    outcomes = validate_skills(paths.claude_dir / "skills")
    report([], outcomes, verbose=True)
    return 1 if any(o.status == Status.WARNED for o in outcomes) else 0


def _format_diff(outcome: Outcome) -> str:
    if outcome.old_content is None or outcome.new_content is None:
        return ""
    diff = difflib.unified_diff(
        outcome.old_content.splitlines(keepends=True),
        outcome.new_content.splitlines(keepends=True),
        fromfile=str(outcome.path) + " (current)",
        tofile=str(outcome.path) + " (generated)",
    )
    return "".join(diff)


def report(sync_outcomes: list[Outcome], skills_outcomes: list[Outcome], verbose: bool) -> None:
    unchanged_count = 0
    for o in sync_outcomes:
        if not verbose and o.status == Status.UNCHANGED:
            unchanged_count += 1
            continue
        typer.echo(f"  {o.status.value:14s} {o.path}")
        if o.detail:
            typer.echo(f"                 {o.detail}")
        if verbose and o.status in (Status.SKIPPED, Status.REPLACED, Status.WOULD_REPLACE):
            diff = _format_diff(o)
            if diff:
                typer.echo(diff)
    if not verbose and unchanged_count > 0:
        typer.echo(f"  {Status.UNCHANGED.value:14s} {unchanged_count} entries up to date")
    for o in skills_outcomes:
        typer.echo(f"  {o.status.value:14s} {o.detail}")


def _ctx_paths(ctx: typer.Context) -> Paths:
    obj: Any = ctx.obj
    return obj["paths"]


def _ctx_flags(ctx: typer.Context) -> tuple[bool, bool, bool, bool]:
    obj: Any = ctx.obj
    return obj["force"], obj["dry_run"], obj["check"], obj["verbose"]


def _run_steps(ctx: typer.Context, tool: str, steps: tuple[str, ...]) -> int:
    paths = _ctx_paths(ctx)
    force, dry_run, check, verbose = _ctx_flags(ctx)
    effective_dry = dry_run or check
    runner = {"opencode": run_opencode, "pi": run_pi, "goose": run_goose, "agy": run_agy, "nomistakes": run_nomistakes, "codex": run_codex}[tool]
    sync_outcomes, skills_outcomes = runner(paths, force, effective_dry, steps)
    report(sync_outcomes, skills_outcomes, verbose)
    return exit_code(sync_outcomes) or (1 if any(o.status == Status.WARNED for o in skills_outcomes) else 0)


def _run_all(ctx: typer.Context) -> int:
    paths = _ctx_paths(ctx)
    force, dry_run, check, verbose = _ctx_flags(ctx)
    effective_dry = dry_run or check
    sync_outcomes, skills_outcomes = run_all_tools(paths, force, effective_dry)
    report(sync_outcomes, skills_outcomes, verbose)
    return exit_code(sync_outcomes) or (1 if any(o.status == Status.WARNED for o in skills_outcomes) else 0)


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
    check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
    claude_dir: Path = typer.Option(Path.home() / ".claude", "--claude-dir", help="Source ~/.claude directory."),
    opencode_dir: Path = typer.Option(Path.home() / ".config" / "opencode", "--opencode-dir", help="Target ~/.config/opencode directory."),
    pi_dir: Path = typer.Option(Path.home() / ".pi" / "agent", "--pi-dir", help="Target ~/.pi/agent directory."),
    goose_dir: Path = typer.Option(Path.home() / ".config" / "goose", "--goose-dir", help="Target ~/.config/goose directory."),
    agy_dir: Path = typer.Option(Path.home() / ".gemini" / "config", "--agy-dir", help="Target ~/.gemini/config directory."),
    agy_cli_dir: Path = typer.Option(Path.home() / ".gemini" / "antigravity-cli", "--agy-cli-dir", help="Target ~/.gemini/antigravity-cli directory."),
    nomistakes_dir: Path = typer.Option(Path.home() / ".no-mistakes", "--nomistakes-dir", help="Target ~/.no-mistakes directory."),
    codex_dir: Path = typer.Option(Path.home() / ".codex", "--codex-dir", help="Target ~/.codex directory."),
) -> None:
    """Sync ~/.claude config into opencode, pi, goose, agy, codex, and no-mistakes. ~/.claude is the source of truth."""
    ctx.obj = {"paths": Paths(claude_dir=claude_dir, opencode_dir=opencode_dir, pi_dir=pi_dir, goose_dir=goose_dir, agy_dir=agy_dir, agy_cli_dir=agy_cli_dir, nomistakes_dir=nomistakes_dir, codex_dir=codex_dir), "force": force, "dry_run": dry_run, "check": check, "verbose": verbose}
    if ctx.invoked_subcommand is None:
        typer.echo("Syncing all tools (opencode + pi + goose + agy + codex + no-mistakes)...")
        raise typer.Exit(_run_all(ctx))


def _update_ctx_flags(
    ctx: typer.Context,
    force: bool = False,
    dry_run: bool = False,
    check: bool = False,
    verbose: bool = False,
) -> None:
    if ctx.obj is None:
        return
    if force:
        ctx.obj["force"] = True
    if dry_run:
        ctx.obj["dry_run"] = True
    if check:
        ctx.obj["check"] = True
    if verbose:
        ctx.obj["verbose"] = True


def _make_step_cmd(tool: str, steps: tuple[str, ...]):
    def cmd(
        ctx: typer.Context,
        force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
        check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
    ) -> None:
        _update_ctx_flags(ctx, force=force, dry_run=dry_run, check=check, verbose=verbose)
        raise typer.Exit(_run_steps(ctx, tool, steps))

    return cmd


def _make_skills_cmd():
    def cmd(
        ctx: typer.Context,
        force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
        check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
    ) -> None:
        _update_ctx_flags(ctx, force=force, dry_run=dry_run, check=check, verbose=verbose)
        raise typer.Exit(_run_skills(ctx))

    return cmd


@app.command()
def all(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
    check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
) -> None:
    """Sync opencode, pi, goose, agy, codex, and no-mistakes."""
    _update_ctx_flags(ctx, force=force, dry_run=dry_run, check=check, verbose=verbose)
    typer.echo("Syncing all tools (opencode + pi + goose + agy + codex + no-mistakes)...")
    raise typer.Exit(_run_all(ctx))


# ---- opencode group ----

@opencode_app.callback(invoke_without_command=True)
def opencode_callback(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
    check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
) -> None:
    """Sync opencode config (all steps)."""
    _update_ctx_flags(ctx, force=force, dry_run=dry_run, check=check, verbose=verbose)
    if ctx.invoked_subcommand is None:
        typer.echo("Syncing opencode...")
        raise typer.Exit(_run_steps(ctx, "opencode", OPENCODE_STEPS))


opencode_app.command("config")(_make_step_cmd("opencode", ("config",)))
opencode_app.command("tui")(_make_step_cmd("opencode", ("tui",)))
opencode_app.command("agents-md")(_make_step_cmd("opencode", ("agents-md",)))
opencode_app.command("agents")(_make_step_cmd("opencode", ("agents",)))
opencode_app.command("commands")(_make_step_cmd("opencode", ("commands",)))
opencode_app.command("plugins")(_make_step_cmd("opencode", ("plugins",)))
opencode_app.command("skills")(_make_skills_cmd())


# ---- pi group ----

@pi_app.callback(invoke_without_command=True)
def pi_callback(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
    check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
) -> None:
    """Sync pi config (pointers + inlined context)."""
    _update_ctx_flags(ctx, force=force, dry_run=dry_run, check=check, verbose=verbose)
    if ctx.invoked_subcommand is None:
        typer.echo("Syncing pi...")
        raise typer.Exit(_run_steps(ctx, "pi", PI_STEPS))


pi_app.command("config")(_make_step_cmd("pi", ("config",)))
pi_app.command("context")(_make_step_cmd("pi", ("context",)))
pi_app.command("keybindings")(_make_step_cmd("pi", ("keybindings",)))
pi_app.command("skills")(_make_skills_cmd())


# ---- goose group ----

@goose_app.callback(invoke_without_command=True)
def goose_callback(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
    check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
) -> None:
    """Sync goose config (all steps)."""
    _update_ctx_flags(ctx, force=force, dry_run=dry_run, check=check, verbose=verbose)
    if ctx.invoked_subcommand is None:
        typer.echo("Syncing goose...")
        raise typer.Exit(_run_steps(ctx, "goose", GOOSE_STEPS))


goose_app.command("hints")(_make_step_cmd("goose", ("hints",)))
goose_app.command("config")(_make_step_cmd("goose", ("config",)))
goose_app.command("providers")(_make_step_cmd("goose", ("providers",)))
goose_app.command("skills")(_make_skills_cmd())


# ---- agy group ----

@agy_app.callback(invoke_without_command=True)
def agy_callback(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
    check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
) -> None:
    """Sync agy config (all steps)."""
    _update_ctx_flags(ctx, force=force, dry_run=dry_run, check=check, verbose=verbose)
    if ctx.invoked_subcommand is None:
        typer.echo("Syncing agy...")
        raise typer.Exit(_run_steps(ctx, "agy", AGY_STEPS))


agy_app.command("settings")(_make_step_cmd("agy", ("settings",)))
agy_app.command("agents-md")(_make_step_cmd("agy", ("agents-md",)))
agy_app.command("skills")(_make_step_cmd("agy", ("skills",)))


# ---- no-mistakes group ----

@nomistakes_app.callback(invoke_without_command=True)
def nomistakes_callback(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
    check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
) -> None:
    """Sync no-mistakes config (all steps)."""
    _update_ctx_flags(ctx, force=force, dry_run=dry_run, check=check, verbose=verbose)
    if ctx.invoked_subcommand is None:
        typer.echo("Syncing no-mistakes...")
        raise typer.Exit(_run_steps(ctx, "nomistakes", NOMISTAKES_STEPS))


nomistakes_app.command("config")(_make_step_cmd("nomistakes", ("config",)))
nomistakes_app.command("skills")(_make_skills_cmd())


# ---- codex group ----

@codex_app.callback(invoke_without_command=True)
def codex_callback(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
    check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
) -> None:
    """Sync codex config (all steps)."""
    _update_ctx_flags(ctx, force=force, dry_run=dry_run, check=check, verbose=verbose)
    if ctx.invoked_subcommand is None:
        typer.echo("Syncing codex...")
        raise typer.Exit(_run_steps(ctx, "codex", CODEX_STEPS))


codex_app.command("config")(_make_step_cmd("codex", ("config",)))
codex_app.command("agents-md")(_make_step_cmd("codex", ("agents-md",)))


app.add_typer(opencode_app, name="opencode")
app.add_typer(pi_app, name="pi")
app.add_typer(goose_app, name="goose")
app.add_typer(agy_app, name="agy")
app.add_typer(nomistakes_app, name="no-mistakes")
app.add_typer(codex_app, name="codex")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
