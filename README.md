# claude-config

Backup of `~/.claude` config - the single source of truth for [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [opencode](https://opencode.ai), [pi](https://pi.dev), [goose](https://goose.dev), [agy (Antigravity)](https://antigravity.google), and [Codex](codex/README.md).

## What's tracked

- `CLAUDE.md` — global memory/instructions
- `settings.json` — permissions and plugin config
- `skills/` — custom skills (includes `agent-config` cross-harness guide; some symlink into `custom/plugins/caveman`)
- `commands/` — custom slash commands
- `custom/` — hooks and plugins (includes [caveman](https://github.com/JuliusBrussee/caveman) submodule)
- `statusline-command.sh` — CLI statusline
- `opencode/` — base opencode config (`opencode.json`, `tui.json`), synced by settings-sync
- `settings-sync/` - syncs this config into [opencode](https://opencode.ai), [pi](https://pi.dev), [goose](https://goose.dev), [agy](https://antigravity.google), [Codex](codex/README.md), and [no-mistakes](https://github.com/kunchenguid/no-mistakes); see [settings-sync/README.md](settings-sync/README.md)
- `pi/` — base pi config (pointer template + pinned `packages[]`), wired by `sync`; see [pi/README.md](pi/README.md)
- `goose/` — base goose config (`config.yaml`, `custom_providers/`), synced by settings-sync; see [goose/README.md](goose/README.md)
- `gemini/` — base gemini/agy config (`settings.json`), synced by settings-sync
- `codex/` - shared defaults merged into `~/.codex/config.toml`; launch with plain `codex`. Local state is preserved. See [codex/README.md](codex/README.md).
- `no-mistakes/` — no-mistakes gate config template (`config.yaml`) + machine/local overlay (`config.local.yaml`, untracked), merged by settings-sync into `~/.no-mistakes/config.yaml`; see [no-mistakes/README.md](no-mistakes/README.md)
- `sync.sh` — one-command machine setup: runs settings-sync + installs the machine-local tools the repo declares ([evo](https://github.com/evo-hq/evo) for claude-code/opencode, pi packages incl. [pi-web-access](https://github.com/nicobailon/pi-web-access)), symlinks `~/.agents/skills`, and installs the no-mistakes binary if missing

## Ownership and routing

This repo is the SOT for agent-harness config (claude code, opencode, pi, goose, agy, codex, no-mistakes): skills, commands, rules files, and the config templates that settings-sync derives per-target. Everything else (shells, editors, OS) lives in the [dotfiles repo](https://github.com/Haydeni0/dotfiles) - `~/.claude` and `~/.dotfiles` together cover the machine.

Routing rules for the cases that look like they belong here but don't:

- **Env vars exported to all shells** (e.g. `NO_MISTAKES_TELEMETRY=0`) → dotfiles `configs/zprofile`, not this repo and not `~/.zshenv`. Login shells see it - including the no-mistakes daemon's login-shell env probe at startup.
- **Machine/local keys** (agent selection, absolute paths, per-host ports, credentials) → untracked `<tool>/config.local.yaml` overlay (settings-sync deep-merges it over the template), or stay out of the repo entirely. Never in the tracked template, never hand-edited into the derived target - it regenerates every sync. Day-to-day choices like no-mistakes's `agent:` are local, not shared - the template is committed, so a flip there would mean a commit.
- **`~/.zshenv`** is intentionally machine-local (different env vars per machine), not managed by dotfiles.
- **Codex** keeps project trust, hook approvals, and UI state in its local `~/.codex/config.toml`. Shared model and permission preferences belong in `codex/config.toml` here; sync merges the declared keys into the local config.

`.gitignore` policy: ignore-all by default, whitelist per tracked dir (`!dir/` + `!dir/**`), then re-ignore machine-local files after the whitelist (last match wins). New tracked dir = add whitelist lines.

### Adding a new settings-sync target

1. **Pick the contract**: fully-derived file (no legitimate machine state) → pi-style always-overwrite (`force=True` at the call site, no force gate); target that legitimately holds machine state → goose-style refuse-to-clobber without `--force`.
2. **Wire it**: `Paths` field defaulting `None`, gate the `run_all_tools` loop on `is not None` (goose pattern, not pi - direct `Paths()` construction in tests must not crash).
3. **Test isolation**: every CliRunner test that seeds a source for the target MUST pass the new `--<tool>-dir` to tmp - the callback defaults point at the real home, and a seeded source without the flag writes to the developer's real config.
4. **Docs**: settings-sync README table row + conflicts-and-safety note (what the target owns vs leaves alone).
5. **Enumeration strings**: grep the old tool list - the module docstring, the "Syncing all tools (...)" echoes, `run_all_tools`, `_run_steps` runner dict, sync.sh's error string, and README comments all enumerate targets and go stale one by one.

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

- **Configure harness / Add skill** - `/agent-config` - single source of truth is `~/.claude/`: edit source in repo -> `uv run --directory ~/.claude/settings-sync sync <tool> --force` -> `uv run --directory ~/.claude/settings-sync pytest`.

## Install (new machine)

`~/.claude` is the single source of truth — Claude Code, opencode, pi, and goose all read from it.
Get the repo, then wire up whichever tools you use.

### 1. Get the repo

```bash
# If ~/.claude doesn't exist yet
git clone --recurse-submodules git@github-haydeni0:Haydeni0/claude-config.git ~/.claude

# If ~/.claude already exists (Claude Code was already run)
cd ~/.claude
git init
git remote add origin git@github-haydeni0:Haydeni0/claude-config.git
git fetch origin
git checkout -f main
git submodule update --init --recursive
```

### 2. Wire up your tools

**Claude Code** reads `~/.claude` directly — nothing to run.

**opencode**, **pi**, **goose**, **agy**, and **Codex** are synced by `settings-sync`, and the machine-local tools the repo declares (evo, pi packages) are installed by `sync.sh`. All need [uv](https://docs.astral.sh/uv/).

```bash
# install opencode: https://opencode.ai  •  install pi: https://pi.dev  •  install goose: https://goose.dev
bash ~/.claude/sync.sh                                    # one command: settings-sync + install evo + pi packages
uv run --directory ~/.claude/settings-sync sync opencode # granular: opencode config only (no installs)
uv run --directory ~/.claude/settings-sync sync pi       # granular: pi config only (no installs)
uv run --directory ~/.claude/settings-sync sync goose    # granular: goose config only (no installs)
uv run --directory ~/.claude/settings-sync sync agy      # granular: agy config only (no installs)
uv run --directory ~/.claude/settings-sync sync codex    # granular: Codex defaults + instructions
codex                                                  # loads shared defaults
uv run --directory ~/.claude/settings-sync sync --check  # drift check (read-only)
# tip: alias ssync='uv run --directory ~/.claude/settings-sync sync' for brevity
```

- **sync.sh** — runs settings-sync, then materializes machine-local installs: `pi install` for each entry in `pi/settings.json#packages[]` (evo + pi-subagents + pi-web-access), and `evo install` for claude-code/opencode (skipped if that host isn't on PATH). Idempotent; re-run after `git pull` or any `~/.claude` edit.
- **opencode** — derives config into `~/.config/opencode`; re-run `sync.sh` (or `sync`) after every `~/.claude` edit.
- **pi** — writes pointers + inlined context + `packages[]` into `~/.pi/agent`; skills/commands are read directly (just `/reload` in pi after edits), only the context file is derived.
- **goose** — derives config into `~/.config/goose`; skills/agents are read directly from `~/.claude` (native compat), only `.goosehints`/`config.yaml`/`custom_providers/` are derived. Re-run `sync.sh` (or `sync`) after every `~/.claude` edit.
- **agy** — derives config into `~/.gemini/config`; rules are written to `AGENTS.md` and skills are symlinked into `skills/`. Re-run `sync.sh` (or `sync`) after every `~/.claude` edit.

See [settings-sync/README.md](settings-sync/README.md), [pi/README.md](pi/README.md), and [goose/README.md](goose/README.md).

## Update

```bash
cd ~/.claude
git add -A
git commit -m "update"
git push
```

To pull in a newer caveman release:

```bash
cd ~/.claude/custom/plugins/caveman && git pull
cd ~/.claude && git add custom/plugins/caveman && git commit -m "bump caveman" && git push
```
