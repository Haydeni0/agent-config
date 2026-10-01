# AGENTS.md - agent-config

Agent-config is the source checkout for shared agent rules, skills, commands,
hooks, harness templates, and the settings-sync CLI. Native homes contain
generated artifacts plus local trust, credentials, sessions, and runtime state.
Edit source here, then sync to the native home.

## Commands

```bash
agent-config sync [harness] [step]  # apply source changes to native homes
agent-config check [harness]        # check drift without writing
agent-config doctor                 # inspect hosts, paths, links, and CLIs
uv run --locked --directory settings-sync pytest -q
uv run --locked --directory opencode-resume pytest -q
node --test hooks/tests/*.test.mjs harnesses/opencode/plugins/bash-guard.test.mjs harnesses/opencode/plugins/config-guard.test.mjs
bash scripts/verify.sh              # full local suite
```

Use targeted tests matching the changed area while iterating. Run the full suite before claiming a configuration or guard change is green.

## Working rules

- Never hand-edit generated native targets when their source lives here. Edit the source, then run `agent-config sync` and `agent-config check`.
- Preserve local runtime entries, generated instructions, and explicit permission choices. Do not put credentials, project trust, hook approval hashes, or UI state in shared templates.
- Use `--force`, including selected-step force, only after inspecting the conflicting generated file and its backup path.
- When running inside `local-codex`, `CODEX_HOME` points to a temporary runtime. Pass the real native home explicitly, for example `agent-config --codex-dir "$HOME/.codex" check codex`.
- Launcher changes owned by another source repo stay there. For example, `local-codex` changes belong in the `slurm-llm` checkout, not here.
- Nested `AGENTS.md` files are authoritative for the directories they cover. Keep the root file source-scoped rather than duplicating subproject rules.
- Commit and push only under the active authorization gate. Branches use `hayden/`.

## Documents

| File | Answers |
|---|---|
| `README.md` | Setup, command surface, source layout, and adoption flow |
| `docs/migrate-existing-installation.md` | How to migrate another machine |
| `docs/migration.md` | First machine’s migration record, backup, and rollback |
| `settings-sync/README.md` | Ownership, recovery, adapters, and sync mechanics |
| `hooks/README.md` | Shared hook coverage, tests, and recovery |
| `MEMORY.md` | Verified lessons learned for future sessions |
| `.agents/backlog.md` | Deferred items and open work |

Project plans live in `.agents/plans/`. Read legacy `.claude` documents when canonical files are absent and reconcile both when both exist.

## Autonomy

| Tier | Trigger | Action |
|---|---|---|
| Decide and note | Routine wording, section grouping, or targeted test selection | Do it and record the outcome |
| Queue | A genuine design fork that does not block unrelated work | Add `.agents/backlog.md` and continue |
| Stop | No meaningful work remains, or an action mutates native credentials, trust, approvals, or live runtime state | Halt and ask |

## Maintenance

- Admission test for any new line: “would removing this cause a mistake?” If not, do not add it.
- Add rules when a mistake repeats. Prune rules as readily as they are added.
- Put discovered traps in the innermost applicable `AGENTS.md`; keep this file source-scoped.
- Verified non-obvious learnings belong in `MEMORY.md`. Promote stabilized rules to this file and drop the memory entry.
