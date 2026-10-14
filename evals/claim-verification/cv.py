#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from live import LAUNCHER_DEFAULT, probe as run_probe, render_arm, run_batch
from model import Condition
from sample import judge, pick, pool
from scenarios import SCENARIO_IDS
from summarize import aggregate, load_runs, render

app = typer.Typer(no_args_is_help=True)
HARD_CHECKS = ("mcp.launch", "no-mcp.launch", "rule", "skill", "mcp.connected", "no-mcp.tool_absent", "native.unchanged")


@app.command()
def probe(arm_source: Annotated[Path, typer.Option()], scratch: Annotated[Path, typer.Option()],
          launcher: Path = LAUNCHER_DEFAULT) -> None:
    home = scratch / "home-probe"
    render_arm(arm_source, home)
    res = run_probe(launcher, home, scratch)
    typer.echo(json.dumps(dataclasses.asdict(res), indent=2))
    failed = [c for c in HARD_CHECKS if not res.checks.get(c)]
    if failed:
        typer.echo(f"fidelity probe failed: {failed}", err=True)
        raise typer.Exit(1)


@app.command()
def run(arm: Annotated[list[str], typer.Option()], out: Annotated[Path, typer.Option()],
        scratch: Annotated[Path, typer.Option()],
        scenario: Annotated[list[str], typer.Option()] = list(SCENARIO_IDS),
        condition: Annotated[list[Condition], typer.Option()] = [Condition.MCP, Condition.NO_MCP],
        reps: int = 5, jobs: int = 4, timeout: float = 600, launcher: Path = LAUNCHER_DEFAULT) -> None:
    arms: dict[str, Path] = {}
    for a in arm:
        name, sep, src = a.partition("=")
        if not sep or not name or not src:
            raise typer.BadParameter(f"--arm must be name=dir, got {a!r}")
        arms[name] = Path(src)
    run_batch(arms, scenario, condition, reps, jobs, launcher, out, scratch, timeout)
    typer.echo(f"wrote {out / 'runs.jsonl'}")


@app.command()
def summarize(out: Path, header: str = "# Replay suite summary") -> None:
    md = render(aggregate(load_runs(out / "runs.jsonl")), header)
    (out / "summary.md").write_text(md)
    typer.echo(md)


@app.command()
def sample(out: Annotated[Path, typer.Option()], scratch: Annotated[Path, typer.Option()], n: int = 10,
           seed: int = 1, projects: Path = Path.home() / ".claude" / "projects",
           launcher: Path = LAUNCHER_DEFAULT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    home = scratch / "home-judge"
    home.mkdir(parents=True, exist_ok=True)
    chosen = pick(pool(projects), n, seed)
    rows, lines = [], ["# Retrospective sample", "", "| session | claims | unsupported |", "|---|---|---|"]
    total = unsupported = 0
    for s in chosen:
        j = judge(launcher, home, scratch, s)
        bad = sum(1 for c in j if not c.supported)
        total, unsupported = total + len(j), unsupported + bad
        rows.append(json.dumps({"session": str(s), "claims": [dataclasses.asdict(c) for c in j]}))
        lines.append(f"| {s.parent.name}/{s.name} | {len(j)} | {bad} |")
    lines += ["", f"Pooled unsupported-claim fraction: {unsupported}/{total} = {unsupported / total:.0%}" if total
              else "Pooled: no claims judged"]
    (out / "sample.jsonl").write_text("\n".join(rows) + "\n")
    (out / "sample.md").write_text("\n".join(lines) + "\n")
    typer.echo("\n".join(lines))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    app()
