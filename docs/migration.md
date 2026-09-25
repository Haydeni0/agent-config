# Source migration and recovery

This is the first machine's migration record. For another machine, follow [Migrate an existing machine](migrate-existing-installation.md); use that machine's own paths, inventory and backups.

## Machine paths

- Source checkout: `/mnt/home/hayden.dorahy/gitrepos/agent-config`
- Claude runtime: `/mnt/home/hayden.dorahy/.claude`
- Private original-state backup: `/mnt/home/hayden.dorahy/.local/state/agent-config-migration-o6v3q56v`
- Local pointer: `~/.config/agent-config/config.toml`
- Machine overlays: `~/.config/agent-config/overlays/{claude.json,no-mistakes.yaml}`

The source checkout has independent Git metadata and exact plugin submodule revisions. The original Phase A patch and inventoried new files are saved in the backup. Runtime sessions, credentials, plugin caches and local skills remain in their native homes.

## Cutover sequence

1. Verify all originally tracked files exist in the new layout. Compare the live source diff against the Phase A checkpoint; inventory ignored content before moving a source directory. Inspect active sessions and avoid concurrent source edits.
2. Run `bash scripts/verify.sh`. Rehearse selective rollback with Git metadata and all four submodules. Save a private manifest with each affected path, prior type, mode, symlink target, backup path and copy/move action.
3. Copy affected native outputs to the backup. Move inventoried shared source entries and original Git metadata into the backup, preserving their relative paths. Keep native resource parent directories and local skill containers in place. Preserve project documents separately; copy agreed plans into `.agents/plans/`, historical plans into ignored `.agents/plans/local/legacy/`, and backlog into ignored `.agents/backlog.md`.
4. Install the local source pointer and overlays. Preserve the existing local-codex permission as an additive Claude allow entry. Preserve no-mistakes overlay values and native Gemini workspace trust.
5. Install and deploy:

```bash
uv tool install --editable "$HOME/gitrepos/agent-config/settings-sync"
agent-config sync
```

Initial generated-instruction conflicts require selected-step `--force` only after comparing them with original source and backing them up. This machine's older Pi/Goose/AGY instructions lack the newer Tooling section; its agent-config command stub also has an older description. Those known generated outputs are regenerated from complete current sources. Unknown local differences require inspection.

6. Run a second `agent-config sync`, then `agent-config check` and `agent-config doctor`. Compare private runtime digests; distinguish concurrent session appends from migration changes. Verify a temporary alias edit appears in source Git status, restore it, and run check from `/tmp`.
7. Inspect native instruction/config loaders for each installed harness. Restart interactive sessions to load new instructions. Record unavailable diagnostics explicitly.

## Rollback

Stop configuration editing and harness startup while restoring. Existing sessions may retain loaded instructions; restart them afterward. The new source checkout is retained for review.

The private backup contains `rollback-manifest.json` and `rollback.py`. The script restores exactly the inventoried entries, preserving modes, symlink targets, and the relative Git/submodule layout. It moves current forward-state entries into `forward-state/` before restoration. Session/cache/local-skill trees excluded from the manifest stay in place. The original backup stays intact.

```bash
uv run --directory /mnt/home/hayden.dorahy/gitrepos/agent-config/settings-sync python \
  /mnt/home/hayden.dorahy/.local/state/agent-config-migration-o6v3q56v/rollback.py
git -C /mnt/home/hayden.dorahy/.claude status --short
git -C /mnt/home/hayden.dorahy/.claude submodule status
```

Run rollback once. A second invocation refuses paths whose forward state is already saved. If cutover stops during backup, entries without a saved original are left untouched. Inspect the manifest and saved entries before manual recovery. Restore original `.git` and `custom/plugins` together before running Git in the old location. The manifest includes the newly installed CLI binaries/tool environment and local pointer; restoring absent entries removes those installations into the forward-state backup.

## Compatibility links

Native `~/.claude/skills`, `commands`, and `agents` remain real directories. Each shared entry points into the source checkout, including `skills/synced` and `skills/headless-chromium-rootless-libs`. `~/.agents/skills` points directly to the source checkout's `skills/` directory.

The shared-skill move has a separate private backup at `/mnt/home/hayden.dorahy/.local/state/agent-config/direct-skills-ob74rf13`. Its `manifest.json` maps the original skill directories, shared discovery link, Codex config and ownership ledger to their backups. The imported skill files match those originals byte-for-byte. To reverse this move, preserve current edits, restore those manifest entries, and restore the prior sync implementation before running sync again. The original migration rollback above covers the earlier source-checkout cutover.

| Alias under `~/.claude` | Source target | Reason |
|---|---|---|
| `custom`, `hooks` | same-named source directories | Existing hook commands and plugin imports |
| `statusline-command.sh` | `harnesses/claude/statusline-command.sh` | Native statusline command |
| `pi`, `opencode`, `codex`, `goose`, `gemini`, `no-mistakes` | corresponding `harnesses/` directories | Existing launchers and source references |
| `settings-sync`, `opencode-resume` | same-named source directories | Existing tool invocations |
| `sync.sh`, `scripts`, `README.md` | same-named source entries | Setup entry and existing navigation |

Runtime `settings.json` and `CLAUDE.md` are generated files. Edit templates in `harnesses/` and shared rules in `rules/global.md`, then sync. The no-mistakes local overlay is under the local control directory, outside these links. Caveman runtime activation files and cached Superpowers plugin discovery stay native.

## Verification record

Prepared source: 260 settings-sync tests, 20 session-converter tests, 275 Claude Bash guard cases, 305 Opencode guard tests and 5 Pi callback tests pass. Selective rollback rehearsal restored byte/mode/mtime snapshots, Git status and all four submodule revisions. Full shared instruction body differs only in project-document routing.

Live cutover complete. Two consecutive syncs and check report 464 unchanged entries; doctor exits successfully. Of 3,672 inventoried files, 3,667 match their original bytes and five active session files have matching original prefixes and unchanged inodes with appended data. Live mixed-config checks preserve native local keys, Codex trust/approval state, original Claude permission entries and the no-mistakes overlay. A temporary skill edit through its runtime alias appeared in the new source Git diff and was restored. Check also succeeds from `/tmp`.

Native loading evidence:

- Codex 0.156.1 `debug prompt-input`: new source routing plus `danger-full-access` and `never` approvals present.
- Claude 2.1.281 fresh print session with tools disabled: returned the configured source path from its loaded global instructions.
- Pi installed native `loadProjectContextFiles`: loaded the generated global context and source routing.
- Opencode `debug config` and `debug skill`: resolved settings and 78 skills. Fresh model prompt blocked by an existing Bedrock HTTP 403 invalid security token.
- Goose fresh prompt blocked by existing missing provider configuration. Generated hints and configuration pass sync checks.
- AGY and no-mistakes executables unavailable; generated configuration verified only.

The preexisting `~/.no-mistakes` link pointed to missing `/tmp/nm-data`. Its original link is backed up in the manifest; cutover created a real native directory. The older Superpowers plugin link was backed up and updated to the highest cached plugin version.

Installed shell aliases and the local-codex launcher contain no references requiring separate dotfiles edits; `glm-pi` is unavailable on this machine. Intentional native aliases are listed above. Project document transfer preserves backlog IDs and checkbox progress; legacy-only and canonical-only cases retain their originals, and both-present agreed plans were compared before keeping the canonical copies. Historical document bodies remain unchanged in the local archive.

The migration implementation is published on `main` in [Haydeni0/agent-config](https://github.com/Haydeni0/agent-config). Other machines should follow [Migrate an existing machine](migrate-existing-installation.md) from that branch. Local verification runs the same script as hosted CI; [verification of revision `689ffe9`](https://github.com/Haydeni0/agent-config/actions/runs/36046142982) passed on Linux and macOS, including the Bash 3.2 guard fix. Check the [Verify workflow](https://github.com/Haydeni0/agent-config/actions/workflows/verify.yml) for subsequent runs.
