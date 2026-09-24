# Agent Config Reliability Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Complete improvements 1-5 while keeping the current source location usable.

**Architecture:** Retain per-harness adapters; strengthen shared filesystem operations and centralize dispatch. Separate config application, diagnostics, and package installation through the existing Typer application.

**Tech Stack:** Python >=3.11, uv, Typer, pytest, tomlkit, PyYAML, Bash, Node's test runner, GitHub Actions.

**Spec:** [Design](2026-09-24-agent-config-design.md), especially Requirements and Runtime contracts.

## Global Constraints

- Preserve shared instruction content and current model/permission choices.
- Keep the checkout at `~/.claude` throughout this phase.
- Use public-CLI filesystem tests, real temporary files, and mocked external installers only where needed.
- No automatic commit/push. Stage milestone changes only when appropriate; obtain the current Git gate before any requested commit/push.
- Required skills during execution: tdd, pytest-guidelines, uv, verification-before-completion; agent-config for configuration changes.
- Commands below run from the repository root. Complete each task's failing reproduction, implementation, and focused verification before the next task.

Test examples use these imports in their named test modules:

```python
from pathlib import Path
import pytest
from typer.testing import CliRunner
from settings_sync.cli import app
```

## File responsibilities

| File | Responsibility |
|---|---|
| `settings-sync/settings_sync/cli.py` | CLI options, command registration, presentation |
| `settings-sync/settings_sync/paths.py` (new) | Invocation-time source/home resolution and typed Paths |
| `settings-sync/settings_sync/sync.py` | Atomic writes, existing Outcome/Status, local sync primitives |
| `settings-sync/settings_sync/ownership.py` (new) | Minimal generated-file ownership and backup records |
| `settings-sync/settings_sync/registry.py` (new) | Ordered harness/step declarations and execution |
| `settings-sync/settings_sync/diagnostics.py` (new) | Read-only prerequisite and drift reporting |
| Existing harness modules | Native parsing, merging, rendering |
| `scripts/bootstrap.sh` (new) | Explicit external installation commands, moved from sync.sh |
| `scripts/verify.sh` (new) | Run the repository's existing test suites |
| `.github/workflows/verify.yml` (new) | Clean-checkout verification on Linux/macOS |

### A1. Isolate CLI tests and resolve paths at invocation time

**Files:** modify `cli.py`, all affected CLI tests; create `paths.py`, `tests/conftest.py`, `tests/test_paths.py`.

**Interfaces:** move existing `Paths` to `paths.py`, re-export it from `cli.py` during compatibility. Native destination CLI options become `Path | None = None`; the callback resolves missing values using the current environment. Add source override resolution without changing the legacy `--claude-dir` behavior yet.

- [x] Add an autouse temporary-home fixture. Set HOME, XDG_CONFIG_HOME, XDG_STATE_HOME; clear AGENT_CONFIG_REPO, CODEX_HOME, OPENCODE_CONFIG_DIR, and PI_CODING_AGENT_DIR unless a test sets them. Existing test imports must not capture home paths before this fixture runs.

```python
@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    for key in ("AGENT_CONFIG_REPO", "CODEX_HOME", "OPENCODE_CONFIG_DIR", "PI_CODING_AGENT_DIR"):
        monkeypatch.delenv(key, raising=False)
    return home
```

- [x] Reproduce default-home capture in a subprocess with a temporary HOME established before importing the app. Seed source instructions, invoke `sync codex agents-md` without a target override, and assert the output exists only under that home. The in-process equivalent must also pass with `cli` imported during test collection.
- [x] Replace import-time `Path.home()` option defaults with callback-time resolution. An explicitly missing configured source must error; it must not fall through to the legacy source.

```python
codex_dir: Path | None = typer.Option(None, "--codex-dir")
# In path resolution, after parsing arguments:
resolved_codex = codex_dir or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
```

- [x] Add public CLI cases for explicit target precedence, native env overrides, source override precedence, a path with spaces, and an all-tools run without per-harness destination flags. Assert destination contents, not internal resolver calls.
- [x] Run `uv run --directory settings-sync pytest tests/test_paths.py tests/test_cli.py tests/test_goose.py tests/test_nomistakes.py tests/test_codex.py -q`, then the full settings-sync suite. Remove temporary scaffolding tests after keeper coverage exists.

### A2. Fix unsafe writes, migration ordering, and read-only checks

**Files:** modify `sync.py`, `config.py`, `commands.py`, `tests/test_sync.py`, `tests/test_config.py`, `tests/test_commands.py`; add `tests/test_read_only.py`.

**Interfaces:** `write_text_atomic(target: Path, content: str) -> None` is the shared writer used by text/JSON/YAML outputs. Symlink installation remains a separate operation. Existing `sync_*` return types remain unchanged.

- [x] Reproduce migration loss through CLI: valid old `.jsonc` plus differing existing `.json`, run without force, assert both originals remain. Add replacement-failure coverage at the filesystem boundary using pytest-mock to make the final replace raise; assert the old file survives and temporary files are cleaned.
- [x] Reproduce `sync opencode commands --check` creating an empty destination directory. Snapshot relative paths, entry types, symlink targets, bytes, modes, and modification times under the temporary home before/after `--check` and `--dry-run`; compare without including access times.

```python
def test_check_does_not_create_commands(tmp_path: Path):
    source = tmp_path / "source"
    (source / "commands").mkdir(parents=True)
    (source / "commands" / "example.md").write_text("---\ndescription: example\n---\nRun.\n")
    target = tmp_path / "opencode"
    result = CliRunner().invoke(app, ["--claude-dir", str(source), "--opencode-dir", str(target), "opencode", "commands", "--check"])
    assert result.exit_code == 1
    assert not target.exists()
```

- [x] Implement atomic writes using a temporary file in `target.parent`, flush and fsync the temporary file, preserve an existing file's permission bits, and use `Path.replace`. New config files get restrictive permissions. Reject unexpected symlink destinations for regular generated/mixed files rather than following them into source. Return actionable failures through Outcome at the sync boundary.
- [x] Parse legacy JSONC in both preview and apply; remove the legacy file only after a successful installed result. Make preview report the same intended merged config as apply. Preserve both files on conflict/parse/write failure.
- [x] Audit all sync paths for unconditional `mkdir`, `unlink`, state writes, and source migration during check. Guard each mutation with apply mode. A read-only check of an absent destination must leave it absent.
- [x] Run `uv run --directory settings-sync pytest tests/test_sync.py tests/test_config.py tests/test_commands.py tests/test_read_only.py -q`. Acceptance includes unchanged bytes/modes on injected failure, faithful migration preview, and zero writes during check/dry-run.

### A3. Establish ownership and preserve local configuration

**Files:** create `ownership.py`, `tests/test_ownership.py`, `tests/test_config_ownership.py`; modify `sync.py`, `agents_md.py`, `agents.py`, `commands.py`, `pi.py`, `goose.py`, `agy.py`, `codex.py`, `config.py`, relevant tests and `settings-sync/README.md`.

**Interfaces:** `ManagedEntry` is a frozen slotted dataclass containing source identity, destination Path, kind, and last installed digest/link. `OwnershipStore` loads/updates `$XDG_STATE_HOME/agent-config/managed.json`. It uses the atomic writer from A2. Parse a versioned JSON object and fail clearly on invalid or unknown versions; use concrete types. Generated writes and orphan cleanup consume this store; native mixed-config mergers do not need per-key bookkeeping. Destination paths are absolute lexical paths, not dereferenced symlink targets.

Public interfaces for the implementation:

```python
@dataclass(frozen=True, slots=True)
class ManagedEntry:
    source_id: str
    destination: Path
    kind: Literal["file", "symlink"]
    fingerprint: str
```

`OwnershipStore(path: Path)` loads without creating files. Its methods are `get(destination: Path) -> ManagedEntry | None`, `record(entry: ManagedEntry) -> None`, and `forget(destination: Path) -> None`. `sync_generated_text(target: Path, source_id: str, content: str, store: OwnershipStore, force: bool = False, dry_run: bool = False) -> Outcome` implements the generated-file contract; ordinary format writers remain reusable by mixed-config adapters. Add the dataclasses/typing imports in the implementation module.

- [x] Add CLI lifecycle tests: initial creation -> source change -> normal resync updates output; independently edited destination -> conflict preserves it; explicit selected-step force -> backup plus replacement. An identical preexisting output is adoptable; a differing first-run output is not silently adopted.

```python
def test_source_updates_apply_without_force(source_home: Path, isolated_home: Path):
    args = ["--claude-dir", str(source_home), "codex", "agents-md"]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 0
    (source_home / "CLAUDE.md").write_text("# Rules\nUpdated source.\n")
    assert runner.invoke(app, args).exit_code == 0
    assert "Updated source." in (isolated_home / ".codex" / "AGENTS.md").read_text()
```

`source_home` is a conftest fixture containing the minimal valid source tree shared by CLI integration tests; move the existing `_make_claude_home` setup into that fixture and seed the required no-mistakes template as well. Its absence must not make the all-target fixture depend on optional-source behavior.

- [x] Implement last-installed digest/link recording and selected-output backups. A matching destination can repair a missing ownership record after interrupted installation. Serialize mutating sync runs with a standard-library advisory lock on the state directory; checks neither create nor modify lock/state files.
- [x] Change orphan handling to consider only recorded entries. Test unknown files surviving force, modified managed orphans being preserved as conflicts, unchanged managed orphans removed, broken owned links handled without following them, and corrupt ownership state preserving every destination.
- [x] Use declared-key merges for Opencode JSON, Pi JSON, AGY JSON, and Goose YAML, preserving native unknown keys. Keep Codex TOML preservation and no-mistakes overlay precedence. Parameterize tests for nested local keys, declared arrays replacing, template-key removal retaining installed values, and malformed source/target preserving originals. Validate top-level mappings before merging. Before replacement, detect a destination changed since reading and return a conflict; cover this with a deterministic filesystem-boundary test. Do not claim advisory locking prevents native applications from writing their own settings.
- [x] Document adoption, normal updates, local-edit conflicts, local config ownership, and recoverable replacement. Do not describe entire runtime directories as source-owned.
- [x] Run `uv run --directory settings-sync pytest -q`. Acceptance: routine shared instruction edits require no force; foreign files and local state survive; interrupted installation can be rerun; no state changes during check.

### A4. Centralize dispatch and scope skill validation

**Files:** create `registry.py`, `tests/test_registry.py`; modify `cli.py`, `skills.py`, `tests/test_skills.py`, `tests/test_cli.py`, harness runner tests, README target-addition instructions.

**Interfaces:** use typed frozen slotted `Harness` and `Step` declarations. Each Step carries its public name, callable, and required source paths. Each Harness carries its ordered steps, availability predicate, and optional native skill validator. Move orchestration out of `cli.py`; retain native behavior in existing adapters. Both single-harness and all-target execution use these declarations.

- [x] Reproduce all-target versus individual behavior with the same source and temporary destinations. Include a `Paths` with an omitted optional Pi destination; it must skip Pi consistently. Seed a nested `skills/synced/` container and ensure unrelated Pi/Goose/AGY/no-mistakes config sync succeeds.
- [x] Implement a single ordered declaration and register commands from it. Keep a small concrete callable table, not a discovery/plugin system. Distinguish AGY's actual `skills` installation step from explicit skill diagnostics.

```python
@dataclass(frozen=True, slots=True)
class Step:
    name: str
    run: Callable[[Paths, bool, bool], list[Outcome]]
    required_sources: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class Harness:
    name: str
    steps: tuple[Step, ...]
    available: Callable[[Paths], bool]
    validate_skills: Callable[[Path], list[Outcome]] | None = None
```

- [x] Require source files for requested steps; optional keybindings and absent external Superpowers cache remain documented optional inputs. Record target errors and continue independent targets. Run validation against the harness that consumes those skills, with discovery excluding container directories rather than treating every directory as a skill.
- [x] Remove duplicate harness enumeration strings in CLI status messages. Keep explicit human documentation of native differences.
- [x] Run `uv run --directory settings-sync pytest tests/test_registry.py tests/test_skills.py tests/test_cli.py tests/test_codex_defaults.py -q`, then the full suite. Acceptance: all and individual commands use the same step behavior and source checks; no unrelated skill warning aborts config sync.

### A5. Add short commands, diagnostics, and the shared skill link

**Files:** modify `pyproject.toml`, `cli.py`, `paths.py`, `README.md`, `settings-sync/README.md`, `skills/agent-config/SKILL.md`; create `diagnostics.py`, `tests/test_diagnostics.py`.

**Interfaces:** add `agent-config = "settings_sync.cli:agent_config_main"`; keep `sync = "settings_sync.cli:main"` for compatibility. Export the new Typer root as `agent_config_app`; `agent_config_main() -> None` invokes it. The new root exposes sync/check/doctor/bootstrap. Check reuses the sync planning path. Doctor returns structured Outcomes and the existing report formatter. Add the shared skills link as a local operation independent of external installers.

- [x] Add CLI tests for `agent-config check codex`, missing required config, an absent optional plugin cache, broken submodule-backed skill links, foreign `~/.agents/skills`, and a configured source path containing spaces. Check/doctor must leave the whole temporary home unchanged.
- [x] Implement entry points with ordinary Typer composition. Keep existing per-harness and per-step selection. Successful check exits 0; drift/conflicts exit 1; malformed CLI arguments use Typer's normal exit behavior. Required missing source is a failure; optional unavailable integrations are explicitly reported.

```toml
[project.scripts]
sync = "settings_sync.cli:main"
agent-config = "settings_sync.cli:agent_config_main"
```

- [x] Doctor prints the effective source repo, harness destination, instruction source/output, link health, missing prerequisites, and the exact corrective command. Report metadata without dumping config values. Reuse registry requirements instead of writing a second source inventory.
- [x] Separate configuration health from host availability in doctor output. Missing native CLIs are informational for config-only checks, while explicitly requested bootstrap reports them as prerequisite errors. A clean CI checkout can verify config generation without installing every agent CLI.
- [x] Preserve foreign skill directories/links. Install or repair only the shared link sync owns. Document resolution/adoption instead of silently accepting missing shared skill discovery as complete.
- [x] Offer the verified editable install command `uv tool install --editable ./settings-sync`. Explain that Python dependency changes require refreshing the tool environment; the lockfile-based invocation remains available as `uv run --directory settings-sync agent-config`.
- [x] Run `uv run --directory settings-sync pytest tests/test_diagnostics.py tests/test_paths.py tests/test_cli.py -q`. Verify `uv run --directory settings-sync agent-config --help` and legacy `sync --help`.

### A6. Separate bootstrap and make declared installs reproducible

**Files:** create `scripts/bootstrap.sh`, `tests/test_bootstrap.py`; modify `.gitignore`, `sync.sh`, `cli.py`, `pi/settings.json`, `pi/extensions/web-access/.gitignore`; add `pi/extensions/web-access/package-lock.json`; update setup docs.

**Interfaces:** `agent-config bootstrap [harness]` invokes the repository bootstrap script using an argument list, passes the resolved source path explicitly, and propagates failures. The shell script handles external commands only. The old `sync.sh` becomes a documented compatibility entry that invokes bootstrap; routine sync stays local.

- [x] Add subprocess tests with tiny fake external executables on a temporary PATH. Capture their requested operations to files. Exercise selected-host installation, missing prerequisites, failed install, already matching versions, and changed pin. Keep all source rendering/sync/filesystem work real.
- [x] Whitelist `scripts/` in the current ignore-all policy so the new bootstrap script is visible to Git immediately.
- [x] Move installation sections out of `sync.sh`. Install only the selected harness integrations. The default set is the registered harnesses with their host CLI on PATH; an explicitly selected missing host reports a prerequisite error. Install no-mistakes only when explicitly selected, because its installer starts a daemon. Config/link sync still runs independently of unrelated optional installer failures, and the aggregate exit is nonzero on failures.
- [x] Pin currently installed Pi package versions, verified during planning: `npm:@evo-hq/pi-evo@0.7.0`, `npm:pi-subagents@0.34.0`, `npm:pi-schedule-prompt@0.4.1`. Installed pi-monitor commit: `475aafb60124176015f7d185a37f173735cb9ceb`. Verify the installed Pi package manager's git-revision syntax from its local source/help before encoding that commit; require installation to land on that exact revision.
- [x] Record immutable external bootstrap versions/revisions as named constants in `scripts/bootstrap.sh`. Resolve the installed evo version with `uv tool list`, the installed no-mistakes version with its local version command, and an official installer revision with `git ls-remote https://github.com/kunchenguid/no-mistakes.git HEAD`; persist actual values before installation. Verify the installer supports selecting the recorded binary version. If it does not, use the matching official release artifact and documented installation steps. An immutable script that still downloads latest is insufficient. Preserve no-mistakes's native updater for later user-requested upgrades.
- [x] Generate and track the web-access npm lockfile, remove its ignore entry, and use `npm ci` during explicit bootstrap. Compare Pi installed package version/commit with declared pins; directory existence alone is insufficient. An intentional update edits pins and re-runs bootstrap.
- [x] Replace Evo's unconditional `rm -rf` of skill names with an isolated external installation staging directory where supported. If the installer requires real host state, snapshot the exact affected entries and remove only demonstrably newly installed artifacts, preserving preexisting skills. Cover a preexisting same-named skill in the bootstrap test.
- [x] Run `bash -n scripts/bootstrap.sh sync.sh` and `uv run --directory settings-sync pytest tests/test_bootstrap.py -q`. Perform one explicit real bootstrap for the selected installed harnesses after reviewing the dry diagnostic output; confirm exact installed versions and source-tree cleanliness.

### A7. Add clean-checkout verification and close Phase A

**Files:** create `scripts/verify.sh`, `.github/workflows/verify.yml`; update `.gitignore`, `README.md`; adjust any newly required test dependencies via uv.

**Interfaces:** one local verification script runs the existing settings-sync suite, opencode-resume suite, Claude Bash guard suite, and Opencode Node guard suites. CI invokes the same script with checkout/submodules and declared runtimes.

- [x] Add explicit whitelist entries for `.github/` and `scripts/` while the ignore-all layout still exists. Confirm intended new files appear in `git status`; local state and credentials remain ignored.
- [x] Implement the direct verification commands:

```bash
uv run --locked --directory settings-sync pytest -q
uv run --locked --directory opencode-resume pytest -q
uv run --locked --directory settings-sync pytest ../custom/hooks/test_bash_guard.py -q
node --test opencode/plugins/bash-guard.test.mjs opencode/plugins/config-guard.test.mjs
bash -n sync.sh scripts/bootstrap.sh
```

- [x] Configure Linux/macOS CI with Python 3.11 and Node 22, install uv and jq, initialize submodules, and run verification. Pin third-party action revisions to verified upstream commits when writing the workflow. CI must not install agent plugins, call models, read personal accounts, or sync to real developer homes.
- [x] Add a subprocess clean-checkout smoke test: temporary HOME, real source checkout, local sync, repeated sync, check, and doctor. Resolve optional external plugins explicitly. Assert unknown sentinel runtime files survive and the second sync is stable.
- [x] Run `bash scripts/verify.sh`, `git diff --check`, and a temporary-home all-target check. Re-read changed docs and grep for stale moved names, date annotations, and line-number citations. Confirm instructions were not shortened.
- [x] Present Phase A evidence and retain the phase checkpoint. Commit/push only if separately requested and authorized. Begin the linked migration plan only after all Phase A acceptance criteria pass.

## Phase A acceptance

- [x] R1-R5 pass with evidence from the public CLI and filesystem effects.
- [x] The legacy invocation remains usable, and the new command is documented.
- [x] Default CLI tests cannot write to the developer home.
- [x] Generated source edits update without routine force; local changes remain recoverable.
- [x] Runtime homes remain where they are; source layout migration has not occurred.

## Phase A verification record

- Settings sync: 243 tests; opencode-resume: 20; Claude guard: 275; Node guards: 304. Local `scripts/verify.sh` passed; hosted CI will run after publication.
- Temporary-home real-checkout sync, repeated sync, check and doctor pass. Missing empty agent source was represented by tracked `agents/.gitkeep`.
- Real Pi bootstrap verified all four pins and ran locked web-access install. Claude Evo cache matches 0.8.0; Opencode bundle matches the pinned uv wheel.
- No local no-mistakes executable was present. Initial bootstrap pins upstream release v1.79.0; it remains explicit and was not installed during verification.
- Implementation adjustment: copy the Opencode bundle from the pinned Evo wheel directly. Upstream installer unconditionally installs global skills; direct bundle installation preserves existing skills without temporary global-state swapping.
- Independent review findings fixed with regressions: empty XDG defaults, nonregular legacy JSONC, destination normalization, declared null, CRLF adoption, missing command source, global bootstrap preview and effective bootstrap destinations. Evo checks the uv environment providing its bundle.
- Changes remain uncommitted. Phase B captures the binary diff and an explicit new-file inventory.
