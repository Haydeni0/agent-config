"""Deploy shared sources into native harness homes; inspect drift and bootstrap dependencies."""

import difflib
from pathlib import Path
from typing import Any

import typer

from settings_sync.paths import Paths, resolve_paths
from settings_sync.registry import HARNESSES, Harness, run_all_tools, run_harness, run_opencode, select_harnesses
from settings_sync.skills import validate_skills
from settings_sync.sync import Outcome, Status

app = typer.Typer(add_completion=False, no_args_is_help=False)


_FAILURE_STATES = {Status.SKIPPED, Status.FAILED, Status.WARNED, Status.WOULD_CREATE, Status.WOULD_REPLACE, Status.WOULD_SKIP}


def exit_code(sync_outcomes: list[Outcome]) -> int:
    return 1 if any(o.status in _FAILURE_STATES for o in sync_outcomes) else 0


def _run_skills(ctx: typer.Context) -> int:
    """Run validate_skills and report. One exit-code policy for all skills invocations."""
    paths = _ctx_paths(ctx)
    _, _, _, verbose = _ctx_flags(ctx)
    outcomes = validate_skills(paths.source_dir / "skills")
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
    sync_outcomes = run_harness(select_harnesses(tool)[0], paths, force, effective_dry, steps)
    skills_outcomes: list[Outcome] = []
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
    claude_dir: Path | None = typer.Option(None, "--source", "--claude-dir", help="Shared configuration source directory."),
    opencode_dir: Path | None = typer.Option(None, "--opencode-dir", help="Target opencode directory."),
    pi_dir: Path | None = typer.Option(None, "--pi-dir", help="Target ~/.pi/agent directory."),
    goose_dir: Path | None = typer.Option(None, "--goose-dir", help="Target goose directory."),
    agy_dir: Path | None = typer.Option(None, "--agy-dir", help="Target ~/.gemini/config directory."),
    agy_cli_dir: Path | None = typer.Option(None, "--agy-cli-dir", help="Target ~/.gemini/antigravity-cli directory."),
    nomistakes_dir: Path | None = typer.Option(None, "--nomistakes-dir", help="Target ~/.no-mistakes directory."),
    codex_dir: Path | None = typer.Option(None, "--codex-dir", help="Target CODEX_HOME directory."),
    claude_home: Path | None = typer.Option(None, "--claude-home", help="Claude runtime destination."),
) -> None:
    """Deploy shared configuration from the selected source checkout into native harness homes."""
    try:
        paths = resolve_paths(claude_dir, opencode_dir, pi_dir, goose_dir, agy_dir, agy_cli_dir, nomistakes_dir, codex_dir, claude_home)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    ctx.obj = {"paths": paths, "force": force, "dry_run": dry_run, "check": check, "verbose": verbose}
    if ctx.invoked_subcommand is None:
        typer.echo("Syncing: " + ", ".join(h.name for h in HARNESSES))
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
    typer.echo("Syncing: " + ", ".join(h.name for h in HARNESSES))
    raise typer.Exit(_run_all(ctx))


def _make_group_callback(harness: Harness):
    def group(
        ctx: typer.Context,
        force: bool = typer.Option(False, "--force"),
        dry_run: bool = typer.Option(False, "--dry-run"),
        check: bool = typer.Option(False, "--check"),
        verbose: bool = typer.Option(False, "--verbose", "-v"),
    ) -> None:
        _update_ctx_flags(ctx, force, dry_run, check, verbose)
        if ctx.invoked_subcommand is None:
            raise typer.Exit(_run_steps(ctx, harness.name, tuple(step.name for step in harness.steps)))
    return group


for harness in HARNESSES:
    group = typer.Typer(add_completion=False, no_args_is_help=False, help=f"Sync {harness.name} configuration.")
    group.callback(invoke_without_command=True)(_make_group_callback(harness))
    for step in harness.steps:
        group.command(step.name)(_make_step_cmd(harness.name, (step.name,)))
    if harness.validate_skills is not None:
        group.command("skills")(_make_skills_cmd())
    app.add_typer(group, name=harness.name)



agent_config_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Manage shared agent configuration.")
agent_config_app.callback()(callback)


def _selection(name: str | None) -> tuple[Harness, ...]:
    try:
        return select_harnesses(name)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@agent_config_app.command("sync")
def sync_command(
    ctx: typer.Context,
    harness: str | None = typer.Argument(None),
    step: str | None = typer.Argument(None),
    force: bool = typer.Option(False, "--force"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    _update_ctx_flags(ctx, force=force, dry_run=dry_run, verbose=verbose)
    paths = _ctx_paths(ctx)
    selected_force, selected_dry, check, selected_verbose = _ctx_flags(ctx)
    try:
        outcomes = [outcome for selected in _selection(harness)
                    for outcome in run_harness(selected, paths, selected_force, selected_dry or check, (step,) if step else None)]
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    report(outcomes, [], selected_verbose)
    raise typer.Exit(exit_code(outcomes))


@agent_config_app.command("check")
def check_command(ctx: typer.Context, harness: str | None = typer.Argument(None), step: str | None = typer.Argument(None)) -> None:
    _update_ctx_flags(ctx, check=True)
    sync_command(ctx, harness, step, False, False, False)


@agent_config_app.command("doctor")
def doctor_command(ctx: typer.Context, harness: str | None = typer.Argument(None)) -> None:
    from settings_sync.diagnostics import doctor
    outcomes = doctor(_ctx_paths(ctx), _selection(harness))
    report(outcomes, [], verbose=False)
    # Show effective paths even when all outputs are current.
    paths = _ctx_paths(ctx)
    typer.echo(f"Source: {paths.source_dir}")
    for selected in _selection(harness):
        typer.echo(f"{selected.name}: {selected.destination(paths)}; instructions: {paths.source_dir / 'rules/global.md'}")
    raise typer.Exit(exit_code(outcomes))



@agent_config_app.command("bootstrap")
def bootstrap_command(ctx: typer.Context, harness: str | None = typer.Argument(None), dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    import os
    import shutil
    import subprocess
    paths = _ctx_paths(ctx)
    force, global_dry, check, verbose = _ctx_flags(ctx)
    selected = _selection(harness)
    if harness is None:
        selected = tuple(item for item in selected if item.name != "no-mistakes" and shutil.which(item.host))
    failures = 0
    for item in selected:
        typer.echo(f"Bootstrap {item.name}: {paths.source_dir / 'scripts/bootstrap.sh'}")
        if dry_run or global_dry or check:
            continue
        outcomes = run_harness(item, paths, force, False)
        report(outcomes, [], False)
        failures |= exit_code(outcomes)
        result = subprocess.run(["bash", str(paths.source_dir / "scripts/bootstrap.sh"), str(paths.source_dir), item.name],
                                env={**os.environ, "OPENCODE_CONFIG_DIR": str(paths.opencode_dir), "AGENT_CONFIG_PI_HOME": str(paths.target("pi")), "AGENT_CONFIG_NOMISTAKES_HOME": str(paths.target("nomistakes"))}, check=False)
        failures |= int(result.returncode != 0)
    raise typer.Exit(failures)

def agent_config_main() -> None:
    agent_config_app()

def main() -> None:
    app()


if __name__ == "__main__":
    main()
