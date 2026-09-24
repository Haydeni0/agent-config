# Agent config

Shared configuration for Claude Code, Codex, Opencode, Pi, Goose, Antigravity, and no-mistakes. Source lives in `~/gitrepos/agent-config`; native homes retain sessions, credentials, caches, and local settings.

## Setup

```bash
git clone --recurse-submodules git@github-haydeni0:Haydeni0/claude-config.git ~/gitrepos/agent-config
cd ~/gitrepos/agent-config
uv tool install --editable ./settings-sync
mkdir -p ~/.config/agent-config
printf 'source = "%s/gitrepos/agent-config"\n' "$HOME" > ~/.config/agent-config/config.toml
agent-config sync
agent-config check
agent-config doctor
```

For an existing installation, follow [Migrate an existing machine](docs/migrate-existing-installation.md). The [first machine's migration record](docs/migration.md) contains its recovery details. `--source /path/to/checkout` works before the local pointer exists. Source selection is explicit flag, `AGENT_CONFIG_REPO`, then `$XDG_CONFIG_HOME/agent-config/config.toml`. Unconfigured source is an error.

## Everyday commands

```bash
agent-config sync                         # local configuration and links
agent-config sync codex                   # one harness
agent-config sync codex agents-md         # one output
agent-config check                       # read-only drift check
agent-config doctor                      # paths, source/link health, host availability
agent-config bootstrap pi                # explicit external installation
agent-config bootstrap --dry-run         # show selected installed hosts
bash scripts/verify.sh                    # same checks as CI
```

`sync [harness] [step]` remains a compatibility command; `sync.sh` invokes bootstrap. Default bootstrap selects installed hosts. no-mistakes installation requires explicit selection because it starts its daemon. Pi/npm/Git and Evo pins are checked against installed versions; web-access uses its lockfile. Dependency changes require refreshing the editable uv tool environment. Lockfile alternative: `uv run --locked --directory settings-sync agent-config`.

## Source layout

| Path | Contents |
|---|---|
| `rules/global.md` | Complete shared instructions |
| `AGENTS.md`, `CLAUDE.md` | Repo editing instructions and Claude loader |
| `harnesses/<harness>/` | Shared native settings and resources |
| `skills/`, `commands/`, `agents/` | Shared agent resources |
| `custom/`, `hooks/` | Hook scripts and pinned plugin submodules |
| `settings-sync/`, `opencode-resume/` | Config CLI and session converter |
| `.agents/plans/` | Design and implementation plans |
| `.agents/backlog.md` | Local deferred topics, ignored |

Shared edits belong here. Runtime skill/command aliases point back here; generated instructions name this checkout. Mixed JSON/YAML/TOML files merge declared template keys and preserve other native keys. Generated outputs update normally after adoption; local edits conflict. Selected-step force backs up before replacement. Unknown entries survive cleanup. Details: [ownership and recovery](settings-sync/README.md#ownership-and-recovery).

Machine-only no-mistakes settings live in `$XDG_CONFIG_HOME/agent-config/overlays/no-mistakes.yaml`. Additional local Claude executable permissions live in `overlays/claude.json` as `permissions.allow`; they append uniquely to shared permissions. Codex trust, hook approvals and UI state remain in its native config. Gemini workspace trust remains native. Secrets stay outside this source checkout.

Shell/editor/OS configuration belongs in the [dotfiles repo](https://github.com/Haydeni0/dotfiles). Shared shell exports belong there; `~/.zshenv` remains machine-local. Add a sync target through one declaration in `settings-sync/settings_sync/registry.py` and its native adapter.

## Updating

Pull this checkout, initialize submodules, then run local sync and check. Update package pins deliberately, then run bootstrap for that harness. Git commit/push follow the user's current authorization gate.

## Typical workflows

> Personal notes. One conversation unless context stale or switching repos.
>
> Single living spec; after Interfaces and Tests grills: `Fold our decisions into the spec. Also, review the spec for consistency after.`

### Feature pipeline

- **Understand** — `Help me plan <feature>. <why> <starter idea> <existing integration surface in repo> /grill-me` — exit: scope, non-goals, key decisions agreed
- **Spec** — `Write a spec from our agreed design. /superpowers:brainstorming` — exit: spec file exists and reviewed
- **Interfaces** — `Help me brainstorm interfaces/classes for this spec. /grill-me` — exit: protocols, classes, module layout agreed — then: spec merge
- **Tests** — `Help me plan tests for this spec before we implement. /grill-me /pytest-guidelines` — exit: public API test strategy agreed — then: spec merge
- **Implement** — `Implement per spec. /tdd` — exit: `tdd_scaffolding/` deleted; behavioral tests pass per `pytest-guidelines`

### Harness config & skill authoring

- **Configure harness / Add skill** - `/agent-config` - single source of truth is the source checkout: edit source in repo -> `agent-config sync <tool>` -> `bash scripts/verify.sh`.
