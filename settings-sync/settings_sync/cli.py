"""Deploy shared sources into native harness homes; inspect drift and bootstrap dependencies."""

import difflib
import inspect
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import typer

from settings_sync.paths import Paths, resolve_paths
from settings_sync.actions import Mode
from settings_sync.executor import run as run_engine
from settings_sync.registry import HARNESSES, Harness, select_harnesses
from settings_sync.actions import Outcome, Status

_FAILURE_STATES = {Status.SKIPPED, Status.FAILED, Status.WARNED, Status.WOULD_CREATE, Status.WOULD_REPLACE, Status.WOULD_MERGE}


def exit_code(sync_outcomes: list[Outcome]) -> int:
    return 1 if any(o.status in _FAILURE_STATES for o in sync_outcomes) else 0


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
        if verbose and o.status in (Status.SKIPPED, Status.REPLACED, Status.WOULD_REPLACE, Status.WOULD_MERGE):
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


def build_app(harnesses: tuple[Harness, ...]) -> typer.Typer:
    """Build the agent-config CLI from the harness declarations."""
    app = typer.Typer(add_completion=False, no_args_is_help=True, help="Manage shared agent configuration.")

    def selection(name: str | None) -> tuple[Harness, ...]:
        try:
            return select_harnesses(name, harnesses)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    def callback(
        ctx: typer.Context,
        force: bool = typer.Option(False, "--force", help="Clobber conflicting managed paths."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing."),
        check: bool = typer.Option(False, "--check", help="Exit nonzero if drift detected (writes nothing)."),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diffs for changed text artifacts."),
        claude_dir: Path | None = typer.Option(None, "--source", "--claude-dir", help="Shared configuration source directory."),
        **destinations: Path | None,
    ) -> None:
        """Deploy shared configuration from the selected source checkout into native harness homes."""
        try:
            paths = resolve_paths(harnesses, claude_dir, **{key: value for key, value in destinations.items() if value is not None})
        except (OSError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        ctx.obj = {"paths": paths, "force": force, "dry_run": dry_run, "check": check, "verbose": verbose}

    base = inspect.signature(callback)
    parameters = [p for p in base.parameters.values() if p.kind is not inspect.Parameter.VAR_KEYWORD]
    seen = {"ctx", "force", "dry_run", "check", "verbose", "claude_dir"}
    for harness in harnesses:
        for dest in harness.destinations:
            if dest.attr in seen:
                continue
            seen.add(dest.attr)
            parameters.append(inspect.Parameter(
                dest.attr, inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=typer.Option(None, dest.option, help=f"Target {harness.name} directory."),
            ))
    callback.__signature__ = base.replace(parameters=parameters)
    app.callback()(callback)

    @app.command("sync")
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
            mode = Mode.DRY_RUN if (selected_dry or check) else (Mode.FORCE if selected_force else Mode.APPLY)
            outcomes = run_engine(selection(harness), paths, mode, (step,) if step else None)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        report(outcomes, [], selected_verbose)
        raise typer.Exit(exit_code(outcomes))

    @app.command("check")
    def check_command(ctx: typer.Context, harness: str | None = typer.Argument(None), step: str | None = typer.Argument(None)) -> None:
        _update_ctx_flags(ctx, check=True)
        sync_command(ctx, harness, step, False, False, False)

    @app.command("doctor")
    def doctor_command(ctx: typer.Context, harness: str | None = typer.Argument(None)) -> None:
        from settings_sync.diagnostics import doctor
        outcomes = doctor(_ctx_paths(ctx), selection(harness))
        report(outcomes, [], verbose=False)
        # Show effective paths even when all outputs are current.
        paths = _ctx_paths(ctx)
        typer.echo(f"Source: {paths.source_dir}")
        for selected in selection(harness):
            typer.echo(f"{selected.name}: {selected.destination(paths)}; instructions: {paths.source_dir / 'rules/global.md'}")
        raise typer.Exit(exit_code(outcomes))

    @app.command("bootstrap")
    def bootstrap_command(ctx: typer.Context, harness: str | None = typer.Argument(None), dry_run: bool = typer.Option(False, "--dry-run")) -> None:
        paths = _ctx_paths(ctx)
        force, global_dry, check, verbose = _ctx_flags(ctx)
        selected = selection(harness)
        if harness is None:
            # Bare bootstrap installs only PATH-present installer and host-check
            # harnesses; explicit harnesses (no-mistakes) are never auto-selected.
            selected = tuple(item for item in selected
                             if item.bootstrap.mode in ("installer", "host-check") and shutil.which(item.host))
        env_pairs = {env: str(getattr(paths, attr)) for h in harnesses for env, attr in h.bootstrap.env}
        failures = 0
        for item in selected:
            if item.bootstrap.mode == "host-check" and not shutil.which(item.host):
                typer.echo(f"Bootstrap {item.name}: host CLI {item.host!r} not found on PATH")
                failures |= 1
                continue
            typer.echo(f"Bootstrap {item.name}: {paths.source_dir / 'scripts/bootstrap.sh'}")
            if dry_run or global_dry or check:
                continue
            outcomes = run_engine((item,), paths, Mode.FORCE if force else Mode.APPLY)
            report(outcomes, [], False)
            failures |= exit_code(outcomes)
            if item.bootstrap.mode == "host-check":
                continue
            result = subprocess.run(["bash", str(paths.source_dir / "scripts/bootstrap.sh"), str(paths.source_dir), item.name],
                                    env={**os.environ, **env_pairs}, check=False)
            failures |= int(result.returncode != 0)
        raise typer.Exit(failures)

    return app


agent_config_app = build_app(HARNESSES)


def agent_config_main() -> None:
    agent_config_app()
