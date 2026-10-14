from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from model import VERIFIER_TOOL, Condition, Outcome, RunRecord, Transcript
from scenarios import generate
from score import score_run
from summarize import dump_run
from transcript import parse_stream

log = logging.getLogger(__name__)

LAUNCHER_DEFAULT = Path("/mnt/data/slurm_llm/bin/local-claude")
ALLOWED_BASE = ("Read", "Grep", "Glob", "Edit", "Write", "Bash", "Agent", "Task", "Skill")
SYNC_OWNED = (
    "CLAUDE.md", "settings.json", "skills", "commands", "agents", "custom", "hooks", "statusline-command.sh",
    "pi", "opencode", "settings-sync", "opencode-resume", "codex", "goose", "gemini", "no-mistakes",
    "README.md", "sync.sh", "scripts",
)
NATIVE_RETRY_S = 30  # a concurrent `agent-config sync` from another session can legitimately rewrite these


@dataclass(slots=True, frozen=True)
class Toolset:
    allowed: tuple[str, ...]
    disallowed: tuple[str, ...]
    builtins: tuple[str, ...] | None = None


TOOLSETS = {
    Condition.MCP: Toolset((*ALLOWED_BASE, VERIFIER_TOOL), ()),
    Condition.NO_MCP: Toolset(ALLOWED_BASE, (VERIFIER_TOOL,)),
}
# design-D7 + spec "transcripts never leave the machine": the judge gets no repo reads and no web tools
JUDGE_TOOLSET = Toolset((), (VERIFIER_TOOL,), builtins=())


def build_command(launcher: Path, toolset: Toolset) -> list[str]:
    cmd = [str(launcher), "--", "-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence"]
    if toolset.builtins is not None:
        cmd.append("--tools=" + ",".join(toolset.builtins))
    if toolset.allowed:
        cmd.append("--allowedTools=" + ",".join(toolset.allowed))
    if toolset.disallowed:
        cmd.append("--disallowedTools=" + ",".join(toolset.disallowed))
    return cmd


def render_arm(source: Path, home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["agent-config", "--source", str(source), "--claude-home", str(home), "sync", "claude"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"arm render failed: source={source} home={home} rc={proc.returncode} stderr={proc.stderr[-2000:]}")


def _entry(path: Path) -> str:
    if path.is_symlink():
        return f"link:{os.readlink(path)}"
    if path.is_file():
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if path.is_dir():
        return "dir:" + ";".join(f"{c.name}={_entry(c) if not c.is_dir() or c.is_symlink() else 'dir'}"
                                 for c in sorted(path.iterdir()))
    return "missing"


def native_snapshot(claude_dir: Path, claude_json: Path) -> dict[str, str]:
    snap = {name: _entry(claude_dir / name) for name in SYNC_OWNED}
    snap[".claude.json"] = _entry(claude_json)
    return snap


@dataclass(slots=True, frozen=True)
class Launch:
    transcript: Transcript | None
    raw: str
    stderr: str
    returncode: int | None
    wall_s: float
    error: str | None


def launch(launcher: Path, home: Path, workspace: Path, prompt: str, toolset: Toolset, timeout_s: float) -> Launch:
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(home)}
    start = time.monotonic()
    try:
        proc = subprocess.run(build_command(launcher, toolset), input=prompt, cwd=workspace, env=env,
                              capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return Launch(None, raw, "", None, time.monotonic() - start, "timeout")
    wall = time.monotonic() - start
    if proc.returncode != 0:
        return Launch(None, proc.stdout, proc.stderr, proc.returncode, wall, "launch")
    try:
        return Launch(parse_stream(proc.stdout.splitlines()), proc.stdout, proc.stderr, 0, wall, None)
    except (ValueError, KeyError) as exc:
        return Launch(None, proc.stdout, proc.stderr, 0, wall, f"malformed: {exc}")


@dataclass(slots=True, frozen=True)
class ProbeResult:
    checks: dict[str, bool]
    details: dict[str, str]


PROBE_PROMPT = (
    "Answer three items, one line each, prefixed exactly as shown.\n"
    "RULE: According to your instructions, may you add Co-Authored-By trailers to git commits? Answer YES or NO.\n"
    "SKILL: Invoke the work-package skill with the Skill tool and quote its first markdown heading.\n"
    "SUBAGENT: Spawn one subagent and ask it the RULE question; report its YES/NO answer.\n"
)


def probe(launcher: Path, home: Path, scratch: Path) -> ProbeResult:
    claude_dir, claude_json = Path.home() / ".claude", Path.home() / ".claude.json"
    before = native_snapshot(claude_dir, claude_json)
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}
    for cond in (Condition.MCP, Condition.NO_MCP):
        ws = scratch / f"probe-{cond}"
        ws.mkdir(parents=True, exist_ok=True)
        res = launch(launcher, home, ws, PROBE_PROMPT, TOOLSETS[cond], timeout_s=600)
        details[f"{cond}.error"] = str(res.error)
        details[f"{cond}.stderr"] = res.stderr[-1000:]
        t = res.transcript
        if t is None:
            checks[f"{cond}.launch"] = False
            continue
        checks[f"{cond}.launch"] = True
        text = t.final_text
        details[f"{cond}.final"] = text[-2000:]
        if cond is Condition.MCP:
            checks["rule"] = "RULE: NO" in text.upper().replace("**", "")
            checks["skill"] = any(u.name == "Skill" and "work-package" in str(u.input) for u in t.tool_uses) \
                and "# work-package" in text
            checks["subagent"] = any(u.name in ("Agent", "Task") for u in t.tool_uses) \
                and "SUBAGENT: NO" in text.upper().replace("**", "")
            checks["mcp.connected"] = t.mcp_servers.get("verifier") == "connected"
        else:
            checks["no-mcp.tool_absent"] = VERIFIER_TOOL not in t.tools
    after = native_snapshot(claude_dir, claude_json)
    if after != before:
        time.sleep(NATIVE_RETRY_S)
        after = native_snapshot(claude_dir, claude_json)
    changed = sorted(k for k in before if before[k] != after.get(k))
    details["native.changed"] = ",".join(changed)
    checks["native.unchanged"] = not changed
    return ProbeResult(checks, details)


def _one(arm: str, home: Path, sid: str, cond: Condition, rep: int, launcher: Path, out: Path,
         scratch: Path, timeout_s: float) -> RunRecord:
    seed = int(hashlib.sha256(f"{arm}|{sid}|{cond}|{rep}".encode()).hexdigest()[:8], 16)
    tag = f"{arm}-{cond}-{sid}-{rep}"
    ws, run_home = scratch / tag, scratch / f"home-{tag}"
    for d in (ws, run_home):
        if d.exists():
            shutil.rmtree(d)
    # one config home per run: concurrent sessions sharing a CLAUDE_CONFIG_DIR race on its .claude.json
    shutil.copytree(home, run_home, symlinks=True)
    sc = generate(sid, seed, ws)
    res = launch(launcher, run_home, ws, sc.prompt, TOOLSETS[cond], timeout_s)
    tdir = out / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    tpath = tdir / f"{arm}-{cond}-{sid}-{rep}.jsonl"
    tpath.write_text(res.raw)
    if sc.artifact and (ws / sc.artifact).is_file():
        shutil.copy(ws / sc.artifact, tdir / f"{arm}-{cond}-{sid}-{rep}.artifact")
    truth = {k: v for k, v in sc.truth.items() if not k.startswith("_")}
    if res.transcript is None:
        rec = RunRecord(arm, cond, sid, rep, seed, truth, Outcome.ERROR, 0, False, 0, 0, 0.0, 0, res.wall_s,
                        None, res.error, str(tpath), {"stderr": res.stderr[-1000:]})
    else:
        s = score_run(sc, res.transcript, ws)
        t = res.transcript
        rec = RunRecord(arm, cond, sid, rep, seed, truth, s.outcome, s.oracle_calls, s.recheck, t.input_tokens,
                        t.output_tokens, t.cost_usd, t.num_turns, res.wall_s, t.model, None, str(tpath),
                        {"permission_denials": list(t.permission_denials)})
    shutil.rmtree(ws)
    shutil.rmtree(run_home)
    return rec


def run_batch(arms: dict[str, Path], scenario_ids: list[str], conditions: list[Condition], reps: int, jobs: int,
              launcher: Path, out: Path, scratch: Path, timeout_s: float) -> list[RunRecord]:
    out.mkdir(parents=True, exist_ok=True)
    homes = {}
    for name, source in arms.items():
        homes[name] = scratch / f"home-{name}"
        render_arm(source, homes[name])
    work = [(a, s, c, r) for a in arms for s in scenario_ids for c in conditions for r in range(reps)]
    records: list[RunRecord] = []
    with ThreadPoolExecutor(max_workers=jobs) as pool, (out / "runs.jsonl").open("a") as sink:
        futures = [pool.submit(_one, a, homes[a], s, c, r, launcher, out, scratch, timeout_s) for a, s, c, r in work]
        for f in futures:
            rec = f.result()
            sink.write(dump_run(rec) + "\n")
            sink.flush()
            log.info("run %s %s %s %d -> %s", rec.arm, rec.condition, rec.scenario, rec.rep, rec.outcome)
            records.append(rec)
    return records
