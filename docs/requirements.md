# Requirements

Binding contract for agent-config. Cite entries as ID plus one-line meaning, verbatim
where interpretation matters. Update this file with or before any behavior change. Never
mark work complete without running the entry's verification. Verification legend:
`(CI)` = run by `scripts/verify.sh` / `.github/workflows/verify.yml`; `manual (...)` =
honor-system with the exact procedure; `planned` = accepted, not yet built. IDs are
stable and never reused; new areas get a new section. Backlog references (#N) point
into the machine-local, gitignored `.agents/backlog.md`.

## Sync - source of truth and safety

| ID | Requirement | Verification |
|---|---|---|
| REQ-SYNC-01 | Native homes are generated from this checkout; hand edits are never adopted: the no-mistakes target is regenerated unconditionally, every other managed target conflict-gates (REQ-SYNC-02). | `test_config_ownership.py`, `test_nomistakes.py` (CI) |
| REQ-SYNC-02 | Sync never silently overwrites a locally-edited managed output: the conflict skips the file and the whole run exits 1; `--force` replaces only after a restorable backup. | `test_cli.py::test_all_exits_nonzero_on_conflict`, `test_ownership.py::test_local_edit_requires_backup_before_force` (CI) |
| REQ-SYNC-03 | `--check` and `--dry-run` are strictly read-only (no file, link, ownership-record, or mtime changes); `--check` exits nonzero when drift exists. | `test_read_only.py`, `test_cli.py::test_check_exits_nonzero_on_drift_without_writing` (CI) |
| REQ-SYNC-04 | Config merges preserve native local state: declared keys merge recursively, local keys (trust, approvals, UI state) create no drift, declared arrays and scalars replace, released template keys stay installed, and invalid source or target fails before any write (Codex retains TOML formatting). | `test_config_ownership.py`, `test_codex_defaults.py`, `test_claude.py`, `test_pi.py` (CI) |
| REQ-SYNC-05 | Orphan cleanup deletes only unchanged outputs recorded in managed.json; foreign files and locally-edited managed orphans are preserved (warned) even under force. | `test_ownership.py::test_orphan_cleanup_preserves_foreign_files`, `test_commands.py`, `test_agents_dir.py` (CI) |
| REQ-SYNC-06 | Generated outputs are tracked in managed.json; an identical existing file is adopted, and a corrupt managed.json blocks all generated-output writes with a restore-from-backup error. | `test_ownership.py::test_source_update_needs_no_force`, `test_corrupt_ownership_prevents_changes`, `test_migration.py` (CI) |
| REQ-SYNC-07 | Hook reconciliation touches only groups this checkout adopted: foreign registrations keep their position, a locally-edited adopted group is a hard error (`--force` does not bypass), and removal leaves foreign groups intact. | `test_hooks.py` (CI) |
| REQ-SYNC-08 | Source and destination resolution precedence is CLI flags > environment variables > config file, resolved fresh per invocation; an unconfigured or missing source is a hard error. | `test_paths.py` (CI) |
| REQ-SYNC-09 | `doctor` is read-only: it reports effective source, per-harness destinations, missing required source files, broken symlinks, and missing hook runtimes, and never writes. | `test_diagnostics.py`, `test_read_only.py` (CI) |
| REQ-SYNC-10 | Bare `agent-config bootstrap` (no harness argument) installs only harnesses whose host CLI is on PATH and never auto-selects no-mistakes. | planned - test for the `cli.py` default-selection filter |
| REQ-SYNC-11 | Syncs are safe under concurrency and failure: writes are atomic under a lock, concurrent syncs are idempotent, and a corrupt ownership snapshot or invalid native config leaves the target untouched. | `test_hooks.py::test_concurrent_hook_sync_is_idempotent`, `test_write_safety.py`, `test_config_ownership.py` (CI) |

## Harness - agnostic sharing

| ID | Requirement | Verification |
|---|---|---|
| REQ-HARNESS-01 | The full `rules/global.md` body reaches every harness's global-instructions file, with `@skills/<n>` refs rewritten to plain skill references outside Claude and a source-routing preamble naming the harness's sync command. | `test_routing.py::test_routing_preserves_complete_rule_body` (CI) |
| REQ-HARNESS-02 | Every deny/allow decision for shell commands comes from the one shared policy core; each harness integration is a thin payload adapter, and the shared corpus yields identical decisions through every adapter. A passing decision grants no permission - the native permission engine stays in control. | `command.test.mjs` corpus + `custom/hooks/test_bash_guard.py` (CI); pi consumes the shared core directly (corpus-through-pi is inference, its tests are hand-rolled); native-enforcement limits manual (`hooks/tests/native-smoke.mjs`) |
| REQ-HARNESS-03 | Adapter and bootstrap failures fail closed (exit 2, empty stdout), never crash open. | `command.test.mjs` malformed-payload tests, `harnesses/pi/tests/command-guard.test.mjs` (CI) |
| REQ-HARNESS-04 | Adding a harness takes an adapter module plus one `Harness` declaration in `registry.py`; CLI subcommands, `all` runs, `check`, and `doctor` then pick it up with no further registration. | `test_registry.py` (CI); auto-exposure claim manual (new-harness walkthrough) |
| REQ-HARNESS-05 | Harness-specific divergence lives only in `harnesses/<harness>/` and machine-local overlays; `rules/`, `skills/`, `commands/`, `agents/` carry no per-harness forks. | manual (review a diff touching those dirs for per-harness branches) |
| REQ-HARNESS-06 | Every shared command is invokable in every harness with a user-command surface; harnesses without one are excluded deliberately (today: goose, codex - documented in their `harnesses/<harness>/README.md`). | manual (per-harness README + spot-check) |
| REQ-HARNESS-07 | Agent definitions convert mechanically Claude -> opencode (documented tool/permission table, deny-by-default mapping, unknown tools warned and skipped); tool restrictions are harness-enforced properties, not shared ones. | `test_agents.py`, `test_agents_dir.py` (CI) |
| REQ-HARNESS-08 | Skill-format lint applies only to the harness whose native format demands it (opencode); a validation failure never fails another harness's sync. Exception: pi/goose/agy runners currently leak opencode-only lint - backlog #7. | `test_registry.py::test_config_independent_of_skill_lint` (CI); #7 fix planned |
| REQ-HARNESS-09 | Synced skills and commands are discoverable through each harness's own CLI. Exception: native prompt checks blocked on provider setup - backlog #8. | manual (per-harness CLI spot-check); blocked portion tracked in #8 |

## Skills - layering and authoring

| ID | Requirement | Verification |
|---|---|---|
| REQ-SKILLS-01 | Frontmatter contract: every `skills/<name>/SKILL.md` parses as YAML, `name` equals the directory name and matches `^[a-z0-9]+(-[a-z0-9]+)*$`, and carries a non-empty `description`. | `scripts/check-skills.py` (CI) |
| REQ-SKILLS-02 | Flat namespace: every skill is a top-level `skills/<name>/` directory with its SKILL.md at the root; no nested skills. | `scripts/check-skills.py` (CI) |
| REQ-SKILLS-03 | One-way layering: a skill declaring `layer: worker` never names a skill declaring `layer: orchestrator`; undeclared skills are unconstrained, and new skills self-declare their layer in their own frontmatter. | `scripts/check-skills.py` (CI) |
| REQ-SKILLS-04 | `design-log` and `dev-cycle` stay peers - neither names the other. | `scripts/check-skills.py` (CI) |
| REQ-SKILLS-05 | Worker skills never reference the design-package contract (the word "package"); their destination rule is invoker directive, then document-adjacent, then the flat default. | package-word clause: `scripts/check-skills.py` (CI); destination ordering manual (review worker skill text) |
| REQ-SKILLS-06 | Vendored skills are symlinks into `custom/plugins/*` submodules and are never edited in place; every top-level symlink under `skills/` resolves. | symlink resolution: `scripts/check-skills.py` (CI); edit-in-place manual (review diffs touching a symlinked skill) |
| REQ-SKILLS-07 | Cross-skill references are name-only or resolve to the referenced skill's files (`../`-prefixed or `<skill-name>/`-prefixed paths must exist). | `scripts/check-skills.py` (CI) |
| REQ-SKILLS-08 | A skill writing cycle-state artifacts uses the `.agents/plans/<slug>/` package layout. Exception: the `orchestrator` skill still teaches the flat layout - backlog #17. | manual (grep `decisions.md\|## Outcome` in `skills/`); #17 fix planned |
| REQ-SKILLS-09 | Skills that persist artifacts or must not fire unprompted declare it in their description ("Not auto-triggered" / "Invoke only via ..."). | manual (grep `Not auto-triggered` and review new skills' descriptions) |

## Hooks - guards and safety

| ID | Requirement | Verification |
|---|---|---|
| REQ-HOOKS-01 | The shared policy denies the destructive-command set (S3 deletes, protected-path deletes, privilege escalation, disk writes, force pushes, API writes, cluster mutations) with class-named reasons; everything else passes. | `hooks/tests/fixtures/command-cases.json` corpus via `command.test.mjs` (CI) |
| REQ-HOOKS-02 | Each harness adapter speaks its native payload and deny protocol and ignores unrelated tools/events. | `command.test.mjs` per-host protocol tests (CI) |
| REQ-HOOKS-03 | A synced hook registration's installed command actually denies end-to-end in its harness, while local state (foreign registrations, unrelated keys, local flags) survives the sync. | `test_hooks.py::test_native_hook_sync_preserves_local_state_and_runs` (CI) |
| REQ-HOOKS-04 | Config guards block model writes to the derived config dirs (opencode, pi) while reads and adjacent directories pass. | `harnesses/opencode/plugins/config-guard.test.mjs`, `harnesses/pi/tests/config-guard.test.mjs`, `config.test.mjs` (CI) |
| REQ-HOOKS-05 | Policy changes are fixture-first: a behavior change to a guard adds its case to the shared corpus in the same change. | manual (review guard diffs for a matching `command-cases.json` hunk) |
| REQ-HOOKS-06 | Claude Code worktree lifecycle events route through wt: the synced `WorktreeCreate` hook makes worktree creation (`EnterWorktree({name})`, the `--worktree` flag, Agent isolation, background sessions) produce ordinary wt worktrees. Cleanup does NOT route through wt: Claude Code never fires `WorktreeRemove` for hook-created git worktrees (anthropics/claude-code#74708), so agents must remove finished agent worktrees themselves (`wt remove --foreground <branch>`, rule in `rules/global.md`). | manual (sync claude twice, `check` clean; scratch repo: `claude -w verify-hook -p "create note.txt containing ok; report cwd and branch"` yields a wt worktree visible in `wt list`, not `.claude/worktrees/`; an Agent `isolation: "worktree"` sub-agent likewise creates via wt; verify its worktree remains in `wt list` after it finishes, and is removed by `wt remove --foreground <branch>`) |

## Process

| ID | Requirement | Verification |
|---|---|---|
| REQ-PROCESS-01 | `scripts/verify.sh` is both the full local suite and the CI suite; the full suite is green before any configuration or guard change is claimed done. | CI runs `verify.sh` on push and PR (`.github/workflows/verify.yml`); local run honor-system |
| REQ-PROCESS-02 | Shell entry points pass `bash -n`, and `*.sh` files are LF-normalized via `.gitattributes`. | `verify.sh` step (CI) |
| REQ-PROCESS-03 | After a source change, native homes are left drift-free: `agent-config sync` then `agent-config check`. | manual (run `agent-config check`); wiring into a gate = backlog #18 |
| REQ-PROCESS-04 | Commits and pushes happen only under the authorization gate (sentinel or chained env check); branches use the `hayden/` prefix. | manual (`rules/global.md` gate spec) |
| REQ-PROCESS-05 | No secrets in shared templates: credentials, trust, hook approval hashes, and UI state stay out of the checkout (`.gitignore` blocks `.env*`, `credentials.*`, `*.pem`). | manual (review diffs adding config files) |
