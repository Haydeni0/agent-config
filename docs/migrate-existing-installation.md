# Migrate an existing machine

For an agent moving this repo from a machine's live `~/.claude` directory into a separate source checkout. Use that machine's files, paths and settings throughout. The [first machine's migration record](migration.md) is an example, with backups specific to that machine.

**Result:** shared configuration lives in `~/gitrepos/agent-config`; native harness homes retain runtime state. Agents edit the source checkout and run `agent-config sync`. Full shared instructions remain intact.

## 1. Inspect before changing anything

- Read the machine's existing agent instructions and project backlog. Identify active sessions and coordinate a pause in configuration edits during cutover.
- Check whether migration already happened: inspect the local agent-config pointer, environment overrides, source checkout and runtime links. If they already agree, run check/doctor and address only remaining drift.
- Inspect Git status, local commits, submodule revisions and ignored/untracked files in the legacy repo. Preserve local work before fetching or changing files.
- Identify actual native destinations. `CODEX_HOME`, `OPENCODE_CONFIG_DIR` and XDG paths can differ between machines. Explicit destination flags go before the subcommand. Use `--claude-home` for a custom Claude home and the other destination flags shown by `agent-config --help`; repeat them consistently. The source pointer stores only the source path.
- Inspect symlinked native homes and their targets, including broken links. Resolve their ownership before writing through or replacing them.

Commands below assume default native homes and Bash. Adjust variables to the inspected machine:

```bash
legacy_repo="$HOME/.claude"
source_repo="$HOME/gitrepos/agent-config"
control_dir="${XDG_CONFIG_HOME:-$HOME/.config}/agent-config"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/agent-config"

git -C "$legacy_repo" status --short --untracked-files=all
git -C "$legacy_repo" submodule status --recursive
git -C "$legacy_repo" ls-files --others --ignored --exclude-standard
```

Keep credentials, tokens and private config contents out of chat and tracked documents. Record the inventory privately on the machine.

## 2. Obtain the migration version in an independent checkout

The migration implementation and this guide are on `main` in [Haydeni0/agent-config](https://github.com/Haydeni0/agent-config). Use the new repository name even if the legacy checkout still points at `claude-config`.

Use a destination outside every runtime home. If it already exists, inspect it and preserve its work instead of cloning over it. For a new destination:

```bash
repo_url="https://github.com/Haydeni0/agent-config.git"
git clone --branch main "$repo_url" "$source_repo"
git -C "$source_repo" submodule update --init --recursive
git -C "$source_repo" rev-parse HEAD
```

The HTTPS URL works for reading this public repo. To use SSH, replace `repo_url` before cloning with this machine's configured SSH host or alias and the repository path `Haydeni0/agent-config.git`. Preserve the machine's authentication method when updating an existing checkout's origin.

Record the printed revision in the machine's migration notes. If a specific reviewed revision is required, check it out before initializing submodules. Keep the normal checkout on `main` tracking `origin/main`; create a `hayden/` branch if reconciling local source edits requires changes. The checkout must have independent Git metadata. For a local clone, use `git clone --no-hardlinks`; a linked worktree depending on the old runtime repo is unsuitable.

**Keep the old live repo at its existing revision until cutover.** Pulling the restructuring into `~/.claude` can remove files that running harnesses still use.

Confirm the new checkout contains `rules/global.md`, `harnesses/claude/settings.json`, `settings-sync/`, `scripts/verify.sh` and this guide. Reconcile local commits and uncommitted source edits into the new layout using this mapping:

| Legacy source | New source |
|---|---|
| Root `CLAUDE.md` | `rules/global.md` |
| Root `settings.json`, `statusline-command.sh` | `harnesses/claude/` |
| `codex/`, `opencode/`, `pi/`, `goose/`, `gemini/`, `no-mistakes/` | Same directories under `harnesses/` |
| `skills/`, `commands/`, `agents/`, `hooks/`, `custom/` | Same relative locations |
| `settings-sync/`, `opencode-resume/` | Same relative locations |

Root `CLAUDE.md` in the new repo loads its repo-specific `AGENTS.md`. Preserve the complete global rule body in `rules/global.md`. Review patches before applying them: old source paths and machine settings need reconciliation. Inventory submodule-local edits too; use the new checkout's pinned revisions, preserving any local work separately before reconciling it.

## 3. Prepare backups and machine-local settings

Create a private backup outside both source and runtime trees:

```bash
umask 077
mkdir -p "${XDG_STATE_HOME:-$HOME/.local/state}"
migration_backup=$(mktemp -d "${XDG_STATE_HOME:-$HOME/.local/state}/agent-config-migration.XXXXXX")
git -C "$legacy_repo" diff --binary HEAD > "$migration_backup/source.patch"
git -C "$legacy_repo" ls-files -z > "$migration_backup/tracked-files.nul"
git -C "$legacy_repo" submodule status --recursive > "$migration_backup/submodules.txt"
```

Save staged/unstaged status, local commit refs, and copies of relevant untracked source files as well. A patch omits untracked files and submodule working-tree changes.

Before any live replacement, create a private rollback manifest. For every affected entry record its absolute destination, previous type (including absent), mode, symlink target, backup location, and intended action. Include:

- Original repo Git metadata and source entries, preserving their relative layout, especially `.git/modules` and `custom/plugins`.
- Native settings, generated instruction files, command/agent/provider/plugin outputs and resource links that sync can change.
- Existing local pointer, overlays, ownership ledger/backups, and CLI installation/entrypoints. Record how to restore any prior editable tool installation.
- Project plans/backlog. For preserved sessions, credentials and local skills, record private digests and file identity; leave those trees in place.

Copy only affected native outputs; move inventoried source entries at cutover. Back up the actual targets of any symlinked outputs that will be modified. Preserve permissions and symlinks. Review ignored content inside source directories before moving them: local skill caches, active-state files and runtime data belong in their native homes.

Prepare these local settings before the first sync:

| Setting | Destination / treatment |
|---|---|
| Legacy `no-mistakes/config.local.yaml` | `$control_dir/overlays/no-mistakes.yaml`; preserve values and reconcile an existing overlay |
| Machine-specific Claude executable allow entries | `$control_dir/overlays/claude.json`, under `permissions.allow` |
| Codex trust, hook approvals, UI state | Retain native config; inspect shared-key differences before merging |
| Gemini workspace trust | Retain native settings; keep machine workspace lists out of shared templates |
| Credentials, sessions, plugin caches, local skills | Retain native files |

The Claude overlay accepts only `permissions.allow`, a list of strings. It appends unique local additions to shared allow entries. Select actual permissions from this machine; copy no executable paths or permission grants from the example machine.

Shared templates replace declared scalar/array values and merge mapping keys recursively. Undeclared native keys survive. Compare each machine's settings with the templates before syncing; reconcile intentional differences in model, provider, packages and permissions explicitly. A clean dry-run is not a guarantee that the chosen shared defaults match local intent.

## 4. Preview and rehearse

Use Git, uv, Bash, Node/npm and jq available on this machine. Run from the new source:

```bash
cd "$source_repo"
bash scripts/verify.sh
uv run --locked --directory "$source_repo/settings-sync" agent-config --source "$source_repo" sync --dry-run
uv run --locked --directory "$source_repo/settings-sync" agent-config --source "$source_repo" doctor
```

Drift/conflict exit codes are expected before adoption. Inspect every conflict. Preview selected harnesses instead of all when that is the intended deployment; bare sync targets all declared harnesses, including those whose executables are absent.

Check that every legacy tracked source has a new equivalent and that source symlinks resolve. Rehearse the intended backup/restore operations in a temporary fixture, including Git/submodule metadata and a simulated interrupted cutover. Check file contents, permissions and symlink targets after restoration. The test suite covers sync behavior; the agent must also verify its machine-specific move list and rollback procedure.

## 5. Cut over shared entries

Recheck the original inventory for concurrent edits. Save the completed manifest and backups before changing each entry.

1. Move inventoried old source entries into their recorded backup locations. Keep `~/.claude` and its `skills`, `commands`, `agents` parent directories real. Move shared entries individually; retain unknown/local entries, including nested skill caches.
2. Free the inventoried compatibility-link locations. The current list is in `sync_claude_links` in `settings-sync/settings_sync/claude.py` and the [compatibility table](migration.md#compatibility-links). Preserve any runtime content discovered there before installing links. Generated `settings.json` and `CLAUDE.md` stay native files with backups.
3. Preserve original Git metadata and submodule source directories together in the backup. Avoid Git operations against a partially relocated repo.
4. Copy this repo's legacy project documents into `.agents`: preserve IDs, checkbox progress and relative links. Reconcile both-present copies before replacing either. Durable plans go in `.agents/plans/`; local historical material can use ignored `.agents/plans/local/`; backlog goes in ignored `.agents/backlog.md`. Keep originals in the backup. Other projects migrate separately when requested.
5. Install/reconcile the prepared overlays. Create `$control_dir/config.toml` with `source` set to the new checkout's actual absolute path. Preserve existing local control settings. Example content:

```toml
source = "/absolute/path/to/agent-config"
```

`--source` overrides `AGENT_CONFIG_REPO`, which overrides this pointer. Check for stale environment overrides. Keep the pointer and overlays machine-local.

6. Install the CLI and sync using the inspected destination flags and selected harnesses:

```bash
uv tool install --editable "$source_repo/settings-sync"
agent-config sync
```

Inspect the installed CLI location if the shell cannot find it. Use the explicit `uv run --locked --directory "$source_repo/settings-sync" agent-config --source "$source_repo" ...` invocation for recovery.

Identical generated files are adopted. Known old generated instructions can conflict because their routing preamble changed. Compare with the original source, preserve any local edits in the appropriate source, then force only the reviewed step, for example:

```bash
agent-config sync codex agents-md --force
```

Real directories and foreign shared-skill roots require deliberate inventory/reconciliation. Force is not a directory migration mechanism. Leave ambiguous entries intact and report their paths. After an interruption, inspect current entries against the manifest and resume completed-safe steps or roll back; retain the original backups.

Codex's `~/.agents/skills` links directly to the source checkout's `skills/`. Shared machine-local skills, such as `headless-chromium-rootless-libs`, can live there gitignored and still sync to agent directories. Copy those skills separately when migrating machines. Keep Claude's generated `~/.claude/skills/synced/` collection local to Claude; sync preserves that directory when switching discovery. Reconcile each remaining visible legacy skill with its source counterpart. Compare existing local copies with source files, preserve differences, and move reconciled runtime copies into the private backup. Run `agent-config sync claude links` to install compatibility links, then `agent-config sync codex`. Sync refuses the switch while other legacy entries would lose discovery.

If external dependencies are needed, inspect `agent-config bootstrap --dry-run`, then bootstrap the intended harness explicitly. This can install packages. no-mistakes installation requires explicit selection and starts its daemon. `sync.sh` invokes bootstrap; use `agent-config sync` for routine local rendering.

## 6. Verify this machine

- Run sync again, then check and doctor for the same deployment scope. Require zero drift; investigate failures rather than applying blanket force.
- Compare private runtime digests and local settings with the inventory. Account separately for concurrent session appends and credential refreshes; investigate unexplained changes.
- Verify runtime resource links resolve into the new checkout and local resources remain accessible. Temporarily edit a shared skill through its alias, confirm Git sees the source edit, then restore the exact original bytes. Preserve any existing source diff.
- Run check from an unrelated directory, using the same environment/destination flags.
- Inspect fresh native sessions. Codex versions exposing `debug prompt-input` can show routing without a model call. For other versions/harnesses, inspect local help for diagnostics or use a read-only prompt with tools disabled where supported. Confirm the actual source path, intended permissions and skill discovery. Record missing CLIs/provider failures as unverified checks.
- Inspect local launchers and shell aliases. Existing paths covered by compatibility links can continue working; propose separate changes to other repos only when needed.
- Restart affected sessions to load the new routing. Future configuration work starts in the source checkout.

Record this machine's source path, migration revision, backup path, checks, exceptions and recovery instructions privately. Report those to the user. Retain backups until the user disposes of them. Follow the user's Git authorization rules for any commit/push.

## Rollback on this machine

Use this machine's manifest and backups. The example machine's private `rollback.py` is outside the repo and is not a portable installer or recovery dependency.

1. Pause config editing and harness startup.
2. Preserve current changed outputs in a separate forward-state backup, including any edits made after migration.
3. Restore each inventoried entry to its exact original path, type, mode and link target. For previously absent entries, move newly created outputs into the forward-state backup. Preserve unrelated new runtime files.
4. Restore original `.git` and submodule directories together before running Git in the legacy checkout.
5. Restore the previous pointer, overlays, ownership state and CLI installation. Reinstate the old editable tool source when one existed.
6. Verify original Git status/submodule revisions and preserved runtime data, then restart sessions. Keep the new source checkout and both backups for inspection.

For partial cutovers, restore only entries actually changed; a missing backup must never trigger removal of an untouched original.
