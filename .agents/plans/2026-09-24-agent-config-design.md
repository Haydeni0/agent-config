# Agent Config Reliability and Migration Design

## Scope and order

Implement the agreed improvements in two separately verifiable phases:

1. [Reliability and usability plan](2026-09-24-agent-config-reliability-plan.md): safe sync, ownership, test isolation and CI, clearer commands/bootstrap, shared harness dispatch. Keep the current checkout location and source layout.
2. [Source migration plan](2026-09-24-agent-config-migration-plan.md): prepare an independent checkout, then move canonical source to `~/gitrepos/agent-config` and install into runtime homes. Start only after Phase A acceptance passes.

The user excluded improvement 7: shortening always-loaded instructions. Preserve the complete shared instruction body. Routing additions and corrections to moved paths are in scope.

Backlog item 7 is a different item: Opencode-only skill validation affects other harnesses. Include that fix in Phase A. Backlog items 4 and 6 otherwise remain deferred; routing work includes tests for the existing guards it changes, without closing backlog items automatically.

These documents are the proposed design and executable plan, based on the conversation. Planning does not authorize live migration or additional commits/pushes. Earlier one-off commit/push grants were consumed.

## Requirements

| ID | Requirement | Delivery |
|---|---|---|
| R1 | Read-only checks create no files/directories, including bookkeeping. Failed writes and migrations preserve usable originals. | A2 |
| R2 | Source updates to adopted generated files apply without routine `--force`. Local state and unrelated files survive sync. | A3 |
| R3 | CLI tests use temporary homes by construction. CI exercises sync, guard tests, and clean-checkout behavior. | A1, A7 |
| R4 | Short commands distinguish sync, check, diagnostics, and installation. Missing required sources fail clearly. | A5, A6 |
| R5 | Individual and all-harness execution share declarations and target-specific validation. | A4 |
| R6 | Shared source remains tracked in an independent repo; caches, sessions, credentials, and local overrides stay local. | B1-B4 |
| R7 | Every supported harness receives explicit edit routing to the actual source checkout. | B2-B4 |
| R8 | Migration happens last, after a rehearsal, with preserved originals and a documented rollback. | B3-B4 |
| R9 | Keep the existing shared instruction content and current model/permission choices. | All |
| R10 | Use `.agents/plans/` and `.agents/backlog.md` for our project conventions, with explicit handling of legacy `.claude` locations. Retain native harness paths. | B1-B4 |

## Runtime contracts

### File ownership

Use three explicit categories, rather than one global meaning of `--force`:

1. **Generated files:** shared instructions, generated agent/command markdown, and provider files. Record the last installed file digest or symlink target in one local ownership file. A normal sync updates an unchanged managed file. A local edit produces a conflict; explicit replacement first backs up the existing file.
2. **Mixed configuration:** merge declared source keys recursively into installed config. Keep other keys. Declared arrays/scalars replace their corresponding values. Retain Codex's TOML formatting behavior. Removing a declared key releases management and leaves its installed value in place, matching current Codex behavior.
3. **Unmanaged entries:** preserve them. Orphan cleanup removes only entries recorded as managed whose content/link still matches the record. A broad `--force` must not turn unknown directory contents into deletion candidates.

On first adoption: missing destination -> create; identical destination -> record ownership; differing destination -> report conflict. Existing runtime files are never silently claimed by directory membership. `--force` remains for an explicitly selected conflicting output, with a recoverable backup. Whole nonempty directories require migration inventory, not recursive replacement.

The ownership file is narrowly justified by two existing problems: distinguishing source changes from local edits, and distinguishing obsolete generated entries from user-owned entries. Store only destination, source identity, kind, and last installed digest/link. Source identity is the stable harness/step/output identity, independent of the checkout's absolute path. No content, credentials, operation queue, or background service. Missing/corrupt ownership metadata cannot authorize deletion. Apply destinations atomically and record each successful result; a retry can adopt an already matching destination after interruption. If a destination changes after it was read, report a conflict rather than applying a stale merge; advisory locking coordinates sync processes, not native harness writers.

For no-mistakes, retain its existing explicit template-plus-local-overlay contract. Move the overlay to the local control directory during migration. Preserve native schemas and YAML value types.

For the existing machine-specific Claude executable permission, use a local `overlays/claude.json` containing only additional `permissions.allow` entries. Append those entries uniquely after rendering shared Claude permissions. This one native list needs additive treatment so preserving a machine path does not shadow future shared permission updates. Other shared arrays retain replacement semantics. Keep Gemini trustedWorkspaces solely in installed native config after removing the machine paths from shared source.

### Paths and commands

Expose the existing Python application under a distinct `agent-config` entry point. Keep the existing `sync` entry point temporarily for compatibility.

```text
agent-config sync [harness] [step]
agent-config check [harness]
agent-config doctor [harness]
agent-config bootstrap [harness]
```

`sync` performs local config/link work. `check` reports drift and conflicts without writes. `doctor` reads prerequisites, source files, submodules, links, and resolved paths. `bootstrap` explicitly installs dependencies and then performs local sync; ordinary sync never installs packages or contacts package registries.

Resolve source from `--source`, then `AGENT_CONFIG_REPO`, then `source` in `$XDG_CONFIG_HOME/agent-config/config.toml` (default `~/.config/agent-config/config.toml`). Phase A retains `~/.claude` as the final compatibility default. Phase B removes that fallback after writing the local source pointer. A missing configured source is an error, never a reason to use another checkout silently.

Resolve destination defaults at invocation time. Respect supported native home overrides explicitly; test `CODEX_HOME` and `OPENCODE_CONFIG_DIR`. Preserve the intentional distinction between Pi's live `PI_CODING_AGENT_DIR` and its default persistent installation home. Explicit target flags win over environment defaults. `--claude-dir` remains a deprecated source alias through Phase A; Phase B introduces an unambiguous Claude runtime destination flag.

Store local ownership and backups beneath `$XDG_STATE_HOME/agent-config` (default `~/.local/state/agent-config`). Tests override home, XDG roots, source env, and native harness overrides, so inherited developer state cannot affect destinations.

### Shared dispatch

One small ordered Python declaration associates a harness with its steps, availability, required sources, and skill validator. Existing harness functions remain responsible for native formats. CLI registration and all-target execution consume the same declaration. Run applicable skill lint explicitly in diagnostics, instead of making config-only steps fail due to unrelated skill containers.

Report independent harness failures together and return nonzero; a failed target does not prevent independent targets from being attempted. Exceptions are prerequisite failures within a target, which stop dependent writes for that target.

### Final source layout

```text
agent-config/
  AGENTS.md                       # repo-specific editing and verification instructions
  CLAUDE.md                       # repo-local loader for AGENTS.md
  rules/global.md                 # complete current shared instruction body
  skills/
  commands/
  agents/
  harnesses/
    claude/settings.json
    claude/statusline-command.sh
    codex/
    opencode/
    pi/
    goose/
    gemini/
    no-mistakes/
  custom/                         # existing hooks, shared guard cases, submodules
  hooks/                          # existing shared hook scripts
  settings-sync/
  opencode-resume/
  scripts/
  .agents/plans/                  # tracked design and implementation plans
  .agents/backlog.md              # local deferred topics, ignored
  docs/
```

Keep submodules at `custom/plugins/*` so existing source-relative skill links keep working. Preserve the Git remote and repository history; renaming the remote repository is unnecessary.

Runtime homes remain real directories. Install individual tracked skills/commands/agents as links to source. Preserve local skill containers such as `~/.claude/skills/synced/`. Keep `~/.agents/skills` pointing at the assembled runtime skill directory when it is already our link. Inventory a foreign link/directory and report it instead of replacing it. Native settings with local state remain ordinary files merged by sync.

### Project convention migration

New project plans use `.agents/plans/`; deferred topics use `.agents/backlog.md`. Keep `AGENTS.md` at the project root. Update our first-party rules, skills, and templates together in Phase B. This convention change does not rename Claude's native `.claude/settings.json`, other harness runtime paths, or upstream submodule files.

For existing projects, use the canonical `.agents` location when present. If only the legacy `.claude` location exists, read it and identify it as legacy; preserve continuity until that project's files are deliberately migrated. If both locations exist, surface both and reconcile their contents before moving or deleting anything. Preserve backlog IDs and plan checkbox state. Migrate this repo during B4; do not bulk-move files in unrelated repositories.

### Agent edit routing

Generate a short routing preamble for every global instruction output, including Claude:

```text
Shared agent configuration source: /absolute/path/to/agent-config
Edit shared rules in rules/global.md, skills in skills/, and harness settings
in harnesses/<harness>/. Apply changes with agent-config sync <harness>.
Runtime instruction files and managed config values are generated outputs.
Machine-only settings belong in the documented local overlay or native state.
```

Render the actual resolved path, never a machine path committed into a shared template. Update the agent-config skill and existing Pi/Opencode guard messages to use this routing. Preserve guard coverage and keep normal sync commands usable. Symlinks ensure an edit through a supported skill/command alias still changes the tracked file. Test generated routing for all instruction targets, then inspect actual prompt loading in installed harnesses.

Instructions and existing guards guide agent behavior; full-access agents are not subject to a universal filesystem security boundary. Do not claim absolute enforcement in every harness. Do not add a new cross-harness permission framework as part of this migration.

## Constraints

- Python >=3.11, uv, Typer; preserve existing native JSON/YAML/TOML adapters.
- Linux and macOS filesystem semantics; preserve file modes, Unicode, and paths containing spaces.
- Reproduce bugs through the public CLI before fixes; keep tests focused on observable filesystem results.
- No skill/body shortening, model changes, permission-policy changes, blanket directory deletion, or automatic remote rename.
- No automatic commit/push. Follow the current authorization gate for each requested Git action.
- Implement Phase A and Phase B as independent milestones. Keep Phase A usable without migration.
- Do not alter credential values or print runtime config contents while inventorying local state.

## Completion evidence

Phase A: required test suites pass from a clean checkout; checks leave the temporary home unchanged; sync handles local state and source edits as designed; doctor reports precise actionable failures.

Phase B: a temporary-home rehearsal passes, then the real machine uses the external checkout; all tracked sources are accounted for; native session/credential files match their pre-migration bytes; two consecutive syncs leave no drift; source edits propagate; every installed harness sees the actual source path. Keep backups until the user disposes of them.
