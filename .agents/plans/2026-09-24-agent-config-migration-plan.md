# Agent Config Source Migration Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make `~/gitrepos/agent-config` the tracked source for every harness while preserving runtime state and routing shared edits into the repo.

**Architecture:** Separate source paths from native runtime homes. Prepare the new layout in an independent checkout; render global routing instructions and install individual shared-source links. Rehearse before changing the live machine.

**Tech Stack:** Phase A Python/Typer sync tool, Git/submodules, native filesystem links, existing Pi/Opencode guards.

**Spec:** [Design](2026-09-24-agent-config-design.md), especially Final source layout, Agent edit routing, and Completion evidence.

## Global Constraints

- Phase A acceptance must pass first. Improvement 7, instruction shortening, remains excluded.
- Keep existing sessions, caches, credentials, trust decisions, hook approvals, and local skills.
- Use an independent checkout for layout changes so moving source files cannot break currently running harnesses.
- Maintain original source/runtime backups and a rollback manifest outside both source and runtime homes.
- No force checkout over `~/.claude`, recursive deletion of unknown content, or remote repository rename.
- No automatic commit/push; previously consumed one-off grants do not authorize this work.
- Before live cutover, inventory active sessions and avoid concurrent config edits. Restart affected harness sessions after installation.
- Adopt `.agents/plans/` and `.agents/backlog.md` for our project conventions during this phase, with the design's legacy-location handling. Retain native harness directories and root `AGENTS.md`.

### B1. Prepare independent source layout and separate source/runtime paths

**Files:** move root `CLAUDE.md` to `rules/global.md`, root `settings.json` and `statusline-command.sh` to `harnesses/claude/`; move `codex/`, `opencode/`, `pi/`, `goose/`, `gemini/`, `no-mistakes/` beneath `harnesses/`; add root `AGENTS.md` and repo-local `CLAUDE.md`; modify `paths.py`, `registry.py`, all adapters' source paths, bootstrap/verify scripts, READMEs and tests.

Create `settings-sync/settings_sync/claude.py` and `settings-sync/tests/test_claude.py` in this task for the new Claude target; B2 extends their routing/link coverage. Python paths without a root prefix in these tasks are relative to `settings-sync/`.

**Interfaces:** rename source `Paths.claude_dir` to `Paths.source_dir`; add separate `Paths.claude_home`. The former points at the checkout, the latter at Claude runtime/cache. Runtime Superpowers cache lookup uses `claude_home / "plugins/cache"`. Use `source_dir / "rules/global.md"` for shared instructions and `source_dir / "harnesses" / name` for native source config.

- [x] Capture a reviewable Phase A checkpoint. Prefer an authorized commit; otherwise preserve `git diff --binary HEAD` and explicitly inventory the new implementation files, then transfer those into the independent clone and verify the resulting diff. Do not pretend uncommitted changes were captured by cloning HEAD. Branch names use `hayden/`.
- [x] Create the independent checkout using `git clone --no-hardlinks` from the current local repository, then set its origin to the original remote URL. It must have independent Git metadata, not a worktree whose common directory lives beneath the runtime home. Preserve submodule revisions. Copy the three plan documents into tracked `.agents/plans/` so the migration retains its own instructions. If Phase A changes were uncommitted, apply the captured binary patch and copy only the inventoried new source files before proceeding.
- [x] Perform the explicit source moves in that checkout only. Keep `custom/plugins/*`, `custom/hooks/*`, `hooks/*`, `skills/*`, `commands/*`, `agents/*`, `settings-sync/*`, and `opencode-resume/*` at their source-relative locations. Update cross-harness test corpus paths after moving Opencode plugin tests.
- [x] Add a temporary-home test with source outside every runtime home. Sync all targets, assert global rules and settings come from the external source, and verify Superpowers resolution still comes from the Claude runtime cache.

```python
def test_external_source_drives_codex(source_repo: Path, isolated_home: Path):
    (source_repo / "rules" / "global.md").write_text("# Rules\nExternal source rule.\n")
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_repo), "sync", "codex"])
    assert result.exit_code == 0
    assert "External source rule." in (isolated_home / ".codex" / "AGENTS.md").read_text()
```

`source_repo` is the existing source fixture migrated to the final layout; `agent_config_app` is the new Typer root from A5, exported under that exact name. Tests import `Path`, `CliRunner`, and `agent_config_app` explicitly.

- [x] Add Claude as an explicit sync target. Install its generated global instructions and merge shared settings into the runtime settings file. Keep `settings.local.json` and auth/session/plugin-cache files local. Settings hooks must resolve source scripts through intentional links or generated source paths, not a mistaken runtime-as-source assumption.
- [x] Replace the source repo's ignore-all policy with specific ignores for secrets, machine overrides, build/cache files, node_modules, virtualenvs, and temporary work. Before staging, inspect every newly visible untracked path; retain legitimate shared source and keep runtime material out.
- [x] Update package/source path tests and run `bash scripts/verify.sh` from the independent checkout. Verify submodule status and every tracked source symlink. Phase A commands must work against the final layout before live cutover.

### B2. Route agents and deploy shared links without losing local files

**Files:** modify `settings_sync/agents_md.py`, `settings_sync/claude.py`, `settings_sync/registry.py`, `tests/test_claude.py`, root `skills/agent-config/SKILL.md`, and `rules/global.md` only for necessary routing/path references; modify `harnesses/opencode/rules.md`, `harnesses/opencode/plugins/config-guard.js`, its test, `harnesses/pi/extensions/config-guard.ts`; add `tests/test_routing.py` and `harnesses/pi/extensions/config-guard.test.ts`.

**Interfaces:** `build_agents_md` gains explicit source-root/harness context for its routing preamble; it preserves the complete common instruction body and existing harness-specific rules. Claude output retains native skill references; other outputs retain the current rewriting. All generated global instruction outputs use the same routing renderer.

- [x] Test the rendered global instructions for Claude, Codex, Opencode, Pi, Goose, and AGY. Each includes the actual source path and correct source-relative edit location. no-mistakes uses the selected agent's instructions; document its separate local overlay route without inserting unsupported config fields.
- [x] Keep root repo instructions brief and specific to editing this source tree; shared global rules remain complete in `rules/global.md`. Repo-local `CLAUDE.md` loads repo-local `AGENTS.md`. Update the agent-config skill's routing table to final paths and normal sync commands, preserving unrelated skill content.
- [x] Install per-entry links for tracked skill directories, command files, and Claude agent files. Preserve real runtime parent directories and untracked local entries. Test a preexisting `skills/synced/` tree and an unknown local skill surviving migration and repeated sync.
- [x] Update Pi/Opencode guard messages to identify the configured source repo and the actual runnable `agent-config` command. Test allowed source edits, blocked direct managed-target edits, read-only commands, and allowed normal sync. Add Pi coverage for these touched behaviors using its actual extension callback interface; do not rewrite shell parsing as part of routing.
- [x] Wire the new Pi guard test into `scripts/verify.sh` and CI using the installed Pi extension loader or its declared TypeScript test runtime. Pin any required dev dependency; run the actual extension module with a controlled host API and exercise its registered callback, rather than testing a rewritten copy of its guard logic.
- [x] Keep runtime dependencies separated: caveman active-state files remain in Claude runtime; its SKILL source points into the repo; cached Superpowers plugin lookup stays runtime. Existing hook/settings paths into `~/.claude/custom` may use intentionally installed compatibility links. Document each retained link rather than globally replacing every `.claude` string.
- [x] Update active source-location guidance in first-party skills, commands, agents, setup docs, and launcher-facing docs. Search using `git grep -n -E '\.claude|/home/hayden|/mnt/home/hayden'`; classify source references versus legitimate runtime paths before editing. Preserve upstream submodule contents.
- [x] Update first-party backlog, planning, handoff, and repo-setup instructions/templates to `.agents/plans/` and `.agents/backlog.md`, including the explicit legacy-location rules in the design. Audit every match by purpose; native Claude paths stay unchanged. Preserve instruction content apart from these routing changes.
- [x] Run `uv run --directory settings-sync pytest tests/test_routing.py tests/test_claude.py -q` and both native guard test suites, then `bash scripts/verify.sh`. Acceptance: editing a shared skill through its runtime link changes the tracked source, and every instruction renderer directs shared edits there.

### B3. Rehearse adoption, local-state preservation, and rollback

**Files:** add `docs/migration.md`, `tests/test_migration.py`; update doctor diagnostics and local-overlay path handling. Implement the migration as a documented sequence of standard filesystem/Git operations, not a permanent migration service.

**Interfaces:** local `$XDG_CONFIG_HOME/agent-config/config.toml` stores the final source pointer. Move no-mistakes machine overlay to `$XDG_CONFIG_HOME/agent-config/overlays/no-mistakes.yaml`; preserve its values. Leave Gemini trustedWorkspaces in installed native config while removing it from shared source. Move the exact existing local-codex executable permission into `$XDG_CONFIG_HOME/agent-config/overlays/claude.json`; render shared `permissions.allow` followed by unique local additions, as specified in the design. Other Claude array keys keep declared-array replacement semantics. Test that both a later shared allow entry and the existing local executable entry survive sync.

- [x] Create a fixture representing an existing installation: tracked shared skills, local nested skill cache, a foreign skill, a plugin cache, native sessions/auth placeholders, mixed configs with local state, a local overlay, and existing generated instruction files. All sensitive fixture values are synthetic.
- [x] Inventory destination entries and classify by ownership before replacement. Preserve files not represented by Git, including ignored local skill content inside an otherwise tracked directory. If ownership is ambiguous, stop that entry and report the path; do not move it into tracked source or discard it automatically.
- [x] Write a rollback manifest containing each changed path, prior entry type, backup location, and previous symlink target. Preserve modes. Back up only affected source/deployment entries plus Git metadata; runtime sessions/caches remain in place. Backups live outside both trees and are not committed.
- [x] Rehearse: stage external source -> back up affected entries -> install links/config -> set source pointer -> two syncs -> check/doctor -> edit source and resync -> rollback. Compare the entire fixture runtime before and after rollback. Assert session/auth/local-skill bytes never change throughout forward migration.
- [x] Exercise a mid-install failure and a foreign link collision. Resume only entries safe under ownership rules; provide exact rollback commands for the affected paths. Test paths with spaces and symlinked source checkout paths.
- [x] Rehearse project-document migration with legacy-only, canonical-only, and both-present fixtures. Preserve all backlog IDs, plan progress, and relative document links; both-present differences must be reconciled without overwriting either original. Verify `.agents/plans/` files are trackable and `.agents/backlog.md` stays ignored. Check first-party skill instructions by a scoped behavior review rather than a source-string-only unit test.
- [x] Ensure `git -C <new-source> status` detects a runtime-alias skill edit. Verify all originally tracked source files are mapped into the new tree, including submodules, hooks, statusline, and auxiliary tools.
- [x] Run `uv run --directory settings-sync pytest tests/test_migration.py tests/test_routing.py -q` and `bash scripts/verify.sh`. The live cutover runbook must contain the actual target and backup paths selected for this machine before execution.

### B4. Cut over the machine last and verify actual harness loading

**Files/state:** final checkout `~/gitrepos/agent-config`; local source pointer; generated outputs and managed links in native homes; preserved backup directory; `docs/migration.md` acceptance record.

**Interfaces:** all live commands now resolve the source through the installed pointer. Remove Phase A's implicit `~/.claude` source fallback; an unset pointer provides a setup error with the command to configure it. Keep explicit `--source` usable for recovery.

- [x] Confirm the destination is still available, the prepared source checkpoint includes all Phase A/B code, and the current runtime inventory matches the rehearsal assumptions. Resolve unexpected local changes before touching them. Coordinate affected active sessions to avoid concurrent edits.
- [x] Preserve the original `.claude` Git metadata and affected tracked entries in the backup location. Leave `.claude` itself, sessions, auth, plugin caches, and local skills in place. Transfer ignored planning/backlog documents deliberately; the three agreed plans belong in the new repo's tracked `.agents/plans/`. Copy the project backlog to the new checkout's ignored `.agents/backlog.md`, preserve its IDs, and retain the original in the backup. Inventory other existing project plans and transfer them without losing progress; review which are durable source documents before tracking. Restore Git metadata and its original submodule paths together during rollback; do not attempt Git operations in a partially relocated backup.
- [x] Install the source checkout at the selected path, initialize exact submodule revisions, and set the local source pointer. Install the tool editably:

```bash
uv tool install --editable "$HOME/gitrepos/agent-config/settings-sync"
agent-config sync
agent-config check
agent-config doctor
```

- [x] Run sync a second time and verify no drift. Compare preserved runtime file digests privately; print only pass/fail counts, never credentials or file contents. Confirm the complete shared instruction body remains present.
- [x] Verify actual instruction loading from a fresh session of each installed/configured harness. For Codex, use its already verified `debug prompt-input` facility and inspect source routing plus permissions. For other CLIs, inspect their local help/source for supported prompt/context diagnostics; use those or a narrowly scoped read-only prompt. Record unavailable/unverified harnesses explicitly instead of claiming they passed.
- [x] Make one temporary edit to a tracked shared skill in the source repo, sync where needed, verify its runtime alias sees the edit, and restore it. Verify `agent-config check` from a working directory unrelated to either checkout.
- [x] Audit dotfiles launchers that still refer to old source paths, especially local-codex/glm-pi paths. Keep explicit compatibility links where sufficient; prepare separately reviewed dotfiles edits only where needed. Do not silently edit another repository.
- [x] Remove stale edit-routing references in maintained docs, retain rollback instructions and backups, and report the final source path, verification results, and any unavailable harness checks. Commit/push only under a fresh applicable authorization gate.

## Phase B acceptance

- [x] Shared configs, skills, commands, agents, hooks, and complete global rules are represented in the new tracked source tree.
- [ ] Each installed harness receives source routing and reads the intended configuration. Native prompt confirmation remains unavailable for Goose/Opencode due to provider configuration, and AGY/no-mistakes CLIs are absent; see evidence below.
- [x] Local runtime data remains intact; native home directories remain usable real directories.
- [x] Shared-source edits propagate; foreign entries survive; second sync and check show no drift.
- [x] The user can run `agent-config` from any working directory and recover via the documented rollback.
- [x] Project plans/backlog use `.agents` conventions; legacy documents remain discoverable during transition; native harness paths retain their required names.

## Execution evidence

Source installed at `/mnt/home/hayden.dorahy/gitrepos/agent-config`; original metadata/source/output backups at `/mnt/home/hayden.dorahy/.local/state/agent-config-migration-o6v3q56v`. The backup includes the Phase A binary patch, 19 inventoried new files, private runtime hashes, rollback manifest/script, and original project documents. All 221 originally tracked source paths accounted for; exact four submodule revisions retained.

Full verification: 260 settings-sync, 20 opencode-resume, 275 Claude guard, 305 Opencode guard, 5 Pi callback tests. The Pi callback test lives under `harnesses/pi/tests/` so the native extension loader does not auto-load a test module. Standalone Pi/Goose/Opencode sync installs required native resource aliases; Pi custom Claude-home pointers are rendered explicitly.

Rehearsal covered synthetic runtime preservation, interruption, foreign collision, source paths with spaces/symlinks, source edits and rollback. A separate selective rollback rehearsal restored per-entry byte/mode/mtime snapshots, Git status and all four submodules using the live rollback script. Project document transfer compared duplicate agreed plans before keeping canonical copies, preserved checkbox state and backlog IDs, and retained historical originals and links. Skill behavior review checked canonical-only, legacy-only and both-present routing instructions.

Live sync/check: 464 unchanged entries; doctor succeeds. Runtime comparison: 3,667 unchanged files, five append-only active session files. Mixed config checks preserve native keys, permissions and overlay values. Runtime skill alias edit was detected in source Git diff, restored, and check passed from `/tmp`. No commit or push during cutover.

Native checks: Codex prompt-input includes actual source and full-access/no-approval settings; Claude tools-disabled print returned actual source; Pi native context loader read new routing; Opencode resolved config and 78 skills. Opencode model prompt hit preexisting Bedrock 403; Goose prompt hit missing provider. AGY/no-mistakes CLI absent. Those limitations are recorded, not claimed as passing. Full runbook and recovery: `docs/migration.md`.
