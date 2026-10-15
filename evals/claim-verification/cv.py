#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
from __future__ import annotations

import dataclasses
import json
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from compare import oracle_counts, pooled, select
from live import LAUNCHER_DEFAULT, TOOLSETS, launch, probe as run_probe, render_arm, run_batch
from model import Condition, Outcome
from pilot import PILOT_BRANCH, PROMPT, REPORT, classify_push_claim, remote_sha
from revise import brief, extract_revision, failing_runs
from sample import judge, pick, pool
from scenarios import SCENARIO_IDS, generate
from score import classify
from summarize import aggregate, dump_run, load_runs, render
from transcript import parse_stream

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
            challenger: Annotated[list[str], typer.Option()] = [],
            scenario: Annotated[list[str], typer.Option()] = ["S1", "S2", "S3", "S4"],
            holdout: str = "S5") -> None:
    records = [r for d in results for r in load_runs(d / "runs.jsonl")]
    core = frozenset(scenario)
    counts = pooled(records, core)
    s = select(counts, baseline, default, challenger, oracle_counts(records, core))
    lines = ["| arm | repeats | n | rate |", "|---|---|---|---|"]
    lines += [f"| {a} | {rep} | {n} | {rep / n:.1%} |" for a, (rep, n) in sorted(counts.items())]
    lines += ["", f"p vs {default}: " + ", ".join(f"{c}={p:.4f}" for c, p in s.p_vs_default.items()),
              f"chosen: {s.chosen}; beats {baseline}: {s.beats_baseline} (p={s.p_vs_baseline:.4f})"]
    if s.p_oracle:
        lines.append(f"p oracle use vs {default}: " + ", ".join(f"{c}={p:.4f}" for c, p in s.p_oracle.items()))
    h = pooled(records, frozenset({holdout}))
    gate = s.chosen in h and baseline in h and h[s.chosen][0] <= h[baseline][0]
    lines += ["", f"holdout {holdout}: " + ", ".join(f"{a}={rep}/{n}" for a, (rep, n) in sorted(h.items())),
              f"holdout {holdout}: chosen {h.get(s.chosen)} vs {baseline} {h.get(baseline)}; gate ok: {gate}"]
    typer.echo("\n".join(lines))


@app.command("revise-brief")
def revise_brief(results: Annotated[list[Path], typer.Option()], arm: Annotated[str, typer.Option()],
                 skill: Annotated[Path, typer.Option()], out: Annotated[Path, typer.Option()]) -> None:
    records = [r for d in results for r in load_runs(d / "runs.jsonl")]
    out.write_text(brief(records, arm, skill.read_text()))
    typer.echo(f"wrote {out} ({len(failing_runs(records, arm))} failing runs)")


@app.command("apply-revision")
def apply_revision(revision: Path, skill: Annotated[Path, typer.Option()]) -> None:
    skill.write_text(extract_revision(revision.read_text(), skill.read_text()))
    typer.echo(f"revised {skill}")


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
def rescore(out: Path) -> None:
    """Reclassify saved runs with the current scorer (D15). No new runs; error runs and oracle/recheck pass through."""
    runs, orig = out / "runs.jsonl", out / "runs.orig.jsonl"
    if not orig.exists():
        shutil.copy(runs, orig)
    records = load_runs(orig)
    tdir = out / "transcripts"
    lines: list[str] = []
    flips: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        for r in records:
            tag = f"{r.arm}-{r.condition}-{r.scenario}-{r.rep}"
            sc = generate(r.scenario, r.seed, Path(td) / tag)
            truth = {k: v for k, v in sc.truth.items() if not k.startswith("_")}
            if truth != r.truth:
                raise ValueError(f"rescore: {tag} regenerated truth {truth} != recorded {r.truth}")
            if r.outcome is Outcome.ERROR:
                lines.append(dump_run(r))
                continue
            if sc.artifact is None:
                jpath = Path(r.transcript_path) if r.transcript_path else tdir / f"{tag}.jsonl"
                if not jpath.is_file():
                    raise ValueError(f"rescore: {tag} transcript missing at {jpath}")
                text = parse_stream(jpath.read_text().splitlines()).final_text
            else:
                apath = tdir / f"{tag}.artifact"
                text = apath.read_text() if apath.is_file() else None
            original = sc.truth.get("_original_artifact")
            outcome = classify(sc, text, str(original) if original is not None else None)
            if outcome is not r.outcome:
                flips.append(f"{tag}: {r.outcome} -> {outcome}")
            lines.append(dump_run(dataclasses.replace(r, outcome=outcome)))
    runs.write_text("".join(line + "\n" for line in lines))
    typer.echo(f"rescored {len(records)} runs from {orig.name}; {len(flips)} flipped")
    typer.echo("\n".join(flips))


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
