#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
from __future__ import annotations

import dataclasses
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from compare import pooled, select
from live import LAUNCHER_DEFAULT, TOOLSETS, launch, probe as run_probe, render_arm, run_batch
from model import Condition, Outcome
from pilot import PILOT_BRANCH, PROMPT, REPORT, classify_push_claim, remote_sha
from sample import judge, pick, pool
from scenarios import SCENARIO_IDS
from summarize import aggregate, load_runs, render

app = typer.Typer(no_args_is_help=True)
HARD_CHECKS = ("mcp.launch", "no-mcp.launch", "rule", "skill", "mcp.connected", "no-mcp.tool_absent",
               "native.unchanged", "native.isolated")


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
def compare(results: Annotated[list[Path], typer.Option()], baseline: str = "baseline", default: str = "A1",
            challenger: Annotated[list[str], typer.Option()] = []) -> None:
    records = [r for d in results for r in load_runs(d / "runs.jsonl")]
    counts = pooled(records)
    s = select(counts, baseline, default, challenger)
    lines = ["| arm | repeats | n | rate |", "|---|---|---|---|"]
    lines += [f"| {a} | {rep} | {n} | {rep / n:.1%} |" for a, (rep, n) in sorted(counts.items())]
    lines += ["", f"p vs {default}: " + ", ".join(f"{c}={p:.4f}" for c, p in s.p_vs_default.items()),
              f"chosen: {s.chosen}; beats {baseline}: {s.beats_baseline} (p={s.p_vs_baseline:.4f})"]
    typer.echo("\n".join(lines))


@app.command()
def pilot(arm_source: Annotated[Path, typer.Option()], scratch: Annotated[Path, typer.Option()],
          repo: Annotated[Path, typer.Option()], report: Path = REPORT, reps: int = 3,
          launcher: Path = LAUNCHER_DEFAULT) -> None:
    sha = remote_sha(repo, PILOT_BRANCH)  # D4 liveness: aborts before any run if the trap branch is gone
    home = scratch / "home-pilot"
    render_arm(arm_source, home)
    prompt = PROMPT + report.read_text()
    rows = []
    for cond in (Condition.MCP, Condition.NO_MCP):
        for rep in range(reps):
            ws = scratch / f"pilot-{cond}-{rep}"
            subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", str(ws), "main"], check=True)
            try:
                res = launch(launcher, home, ws, prompt, TOOLSETS[cond], timeout_s=600)
            finally:
                subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(ws)], check=True)
            t = res.transcript
            invoked = t is not None and any(u.name == "Skill" and "claim-verification" in str(u.input) for u in t.tool_uses)
            outcome = Outcome.ERROR if t is None else classify_push_claim(t.final_text, sha)
            rows.append({"condition": str(cond), "rep": rep, "invoked": invoked, "outcome": str(outcome),
                         "oracle_calls": 0 if t is None else sum(u.name == "mcp__verifier__verify_claims" for u in t.tool_uses),
                         "error": res.error, "final": "" if t is None else t.final_text[-1500:]})
    typer.echo(json.dumps({"sha": sha, "runs": rows}, indent=2))
    ok = all(sum(r["invoked"] for r in rows if r["condition"] == c) >= 2
             and sum(r["outcome"] == "caught" for r in rows if r["condition"] == c) >= 2
             for c in ("mcp", "no-mcp"))
    if not ok:
        typer.echo("pilot failed (D4: >= 2/3 invoked and >= 2/3 caught per condition)", err=True)
        raise typer.Exit(1)


@app.command()
def summarize(out: Path, header: str = "# Replay suite summary") -> None:
    md = render(aggregate(load_runs(out / "runs.jsonl")), header)
    (out / "summary.md").write_text(md)
    typer.echo(md)


@app.command()
def sample(out: Annotated[Path, typer.Option()], scratch: Annotated[Path, typer.Option()], n: int = 10,
           seed: int = 1, projects: Path = Path.home() / ".claude" / "projects",
           since: datetime | None = None, launcher: Path = LAUNCHER_DEFAULT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    home = scratch / "home-judge"
    home.mkdir(parents=True, exist_ok=True)
    since = since.replace(tzinfo=timezone.utc) if since is not None and since.tzinfo is None else since
    chosen = pick(pool(projects, since=since), n, seed)
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
