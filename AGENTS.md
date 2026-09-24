# Agent configuration source

Shared rules: `rules/global.md`. Harness templates: `harnesses/<harness>/`. Skills, commands, agents, hooks and custom plugins are tracked here. Native homes contain generated settings, links, and local runtime state.

- Edit shared sources here, then `agent-config sync [harness]` and `agent-config check [harness]`.
- Run `bash scripts/verify.sh` for changes to sync or guards.
- Preserve local runtime entries, complete shared instructions, and explicit permission choices.
- Project plans: `.agents/plans/`; local backlog: `.agents/backlog.md`. Read legacy `.claude` documents when canonical files are absent; reconcile both when both exist.
- Migrating another machine: `docs/migrate-existing-installation.md`. First machine's migration record and rollback: `docs/migration.md`.
- Commit/push only under the user's current authorization gate. Branches use `hayden/`.
