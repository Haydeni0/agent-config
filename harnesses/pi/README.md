# pi config (shared, portable)

This directory keeps the agent-config checkout as the **single source of truth** for [pi](https://pi.dev)
resources too. Your skills and commands are already shared with Claude Code; pi reads
them through native pointers. Sync installs individual shared entries into the Claude runtime resource directories.

Sync is handled by [`settings-sync`](../../settings-sync/README.md) (one tool syncs both opencode
and pi): `sync pi` writes the pointer template into `~/.pi/agent/settings.json`
and an inlined `CLAUDE.md` into `~/.pi/agent/CLAUDE.md`.

## Architecture

```
~/gitrepos/agent-config/           <-- source checkout.
├── skills/            <name>/SKILL.md      shared: Claude Code + pi (recursive)
├── commands/          <name>.md            shared: Claude Code commands = pi prompt templates
├── rules/global.md               global context (inlined into pi's CLAUDE.md by settings-sync)
├── harnesses/pi/                           pi-only resources (Claude ignores these)
│   ├── extensions/    *.ts                 pi extensions
│   ├── themes/        *.json               pi themes
│   ├── settings.json                       pointer template + pinned packages[] (SOT)
│   └── README.md                          this file
└── settings-sync/                  the sync tool (opencode + pi)

~/.pi/agent/                       <-- machine-local (NOT in the repo)
├── settings.json                   declared defaults merged from harnesses/pi/settings.json
├── keybindings.json                generated copy of optional harnesses/pi/keybindings.json
├── CLAUDE.md                       generated: inlined rules/global.md (@imports expanded)
├── auth.json                       credentials (per machine)
├── sessions/                       session history (per machine)
└── bin/rg                          bundled binary (per machine)
```

The pointer template (`harnesses/pi/settings.json`) is the single source of truth for which dirs pi
reads:
```json
{
  "skills":     ["~/.claude/skills"],
  "prompts":    ["~/.claude/commands"],
  "extensions": ["~/gitrepos/agent-config/harnesses/pi/extensions"],
  "themes":     ["~/gitrepos/agent-config/harnesses/pi/themes"]
}
```
The source template uses `${AGENT_CONFIG_REPO}` for extension/theme paths; sync renders the selected checkout. Native resource pointers select the assembled runtime resources. `agent-config sync pi config` merges declared keys into `~/.pi/agent/settings.json`, preserving Pi state and other local keys. Shared arrays replace the corresponding installed arrays.

`packages[]` declares exact npm versions and a Git commit. `agent-config bootstrap pi` compares installed versions/revisions and installs mismatches; the vendored web-access extension uses its npm lockfile. Update a package by editing its pin and running bootstrap.

`sync pi context` inlines `rules/global.md` into `~/.pi/agent/CLAUDE.md`: it adds source routing and rewrites `@skills/<n>` to ``the `<n>` skill`` (pi can't
expand `@` imports itself). This runs by default with `agent-config sync pi`; select `config` or `context` to update one output.

## Set up a new machine

```bash
# 1. install pi (no npm/node needed)
curl -fsSL https://pi.dev/install.sh | sh
# fallback if you prefer npm:
#   npm install -g --ignore-scripts @earendil-works/pi-coding-agent

# 2. get your config repo at ~/gitrepos/agent-config (clone once, or refresh)
git clone git@github-haydeni0:Haydeni0/agent-config.git ~/gitrepos/agent-config   # first time
git -C ~/gitrepos/agent-config pull                                               # existing machine

# 3. install and select source (needs uv: https://docs.astral.sh/uv/)
uv tool install --editable ~/gitrepos/agent-config/settings-sync
agent-config --source ~/gitrepos/agent-config sync pi   # writes pointers + inlined CLAUDE.md into ~/.pi/agent

# 4. authenticate, then use
pi            # then /login  (or: export ANTHROPIC_API_KEY=... etc.)
```

## Day-to-day: edit in ONE place

| Action | Where (in the repo) | Sync to pi |
|--------|---------------------|------------|
| Add a skill | `skills/<name>/SKILL.md` | `agent-config sync pi` → `/reload` |
| Rename a skill | edit that one `SKILL.md` (or rename the dir) | `agent-config sync pi` → `/reload` |
| Add a command / prompt template | `commands/<name>.md` | `agent-config sync pi` → `/reload` |
| Add an extension | `~/gitrepos/agent-config/harnesses/pi/extensions/<name>.ts` | `agent-config sync pi` → `/reload` |
| Add a theme | `~/gitrepos/agent-config/harnesses/pi/themes/<name>.json` | `agent-config sync pi` → `/reload` |
| **Change pointers** | `~/gitrepos/agent-config/harnesses/pi/settings.json` | commit → `git pull` → `sync pi config` → `/reload` |
| **Change keybindings** | `~/gitrepos/agent-config/harnesses/pi/keybindings.json` | commit → `git pull` → `sync pi keybindings` → `/reload` |
| **Change global context** | `rules/global.md` or its `@` imports | commit → `git pull` → `sync pi context` (or `sync pi`) |

Skill discovery is **recursive** over directories containing `SKILL.md`. Existing linked skill/command edits need `/reload`; adding or renaming entries needs `agent-config sync pi` first to update links.

Notes on the `commands/` → pi prompt-template mapping:
- pi uses the **filename** as the command name (`resume-opencode.md` → `/resume-opencode`); the
  Claude `name:` frontmatter is ignored by pi.
- pi prompt discovery is **non-recursive** (top-level `.md` only), so keep commands as
  top-level files.
- Both use `$ARGUMENTS`, `$1`, `$@` for arguments — compatible.

## What stays machine-local (NOT synced)

- `~/.pi/agent/auth.json` — credentials
- `~/.pi/agent/sessions/` — session history
- `~/.pi/agent/bin/` — bundled `rg` binary
- `~/.pi/agent/models.json` — custom providers (per harness; e.g. a hosted model gateway)

Shared keys in `~/.pi/agent/settings.json` come from `harnesses/pi/settings.json`. Edit those in the template; Pi-owned state and other undeclared keys remain local.

## Re-running the sync

`agent-config sync pi` is idempotent. Re-run after changing `harnesses/pi/settings.json` or `rules/global.md`. It merges declared settings and renders context; identical files report `unchanged`.

To target a different pi agent dir (e.g. a throwaway harness), use `--pi-dir`:
```bash
sync --pi-dir /tmp/glm-pi pi
```

Common flags (apply to `sync` and any subcommand, before the group name):
- `--check` — exit nonzero if drift detected, write nothing
- `--dry-run` — show what would change, write nothing
- `--force` — overwrite diverging derived files (context); declared Pi config keys always merge
- `--verbose` / `-v` — show diffs for changed text artifacts

## Troubleshooting

- **New skill not showing?** Run `/reload` in pi (or restart). Confirm it has `SKILL.md`
  with `name` + `description` frontmatter. Dirs without `SKILL.md` are ignored silently.
- **Pointers lost / `/settings` clobbered them?** Re-run `sync pi config`.
- **Context stale after editing rules/global.md?** Re-run `sync pi context` (or `sync pi`).
- **Command name mismatch?** pi uses the filename, not the `name:` frontmatter.
- **Excluding a Claude-only skill** from pi: edit `harnesses/pi/settings.json`, e.g.
  `"skills": ["~/.claude/skills", "!~/.claude/skills/caveman*"]` (arrays support globs + `!`).

## Files in this directory

- `settings.json` — pointer template (source of truth for resource locations)
- `keybindings.json` — pi keybindings (source of truth; wholesale-copied to ~/.pi/agent)
- `extensions/`   — pi extensions (TypeScript)
- `themes/`       — pi themes (JSON)
- `README.md`     — this file

See also [`settings-sync/README.md`](../../settings-sync/README.md) and pi's own docs:
`pi /reload`, `/settings`, `--no-skills`, `--skill <path>`.
