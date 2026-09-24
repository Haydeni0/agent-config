# no-mistakes config (shared template + local overlay)

This directory is the tracked half of the config for
[no-mistakes](https://github.com/kunchenguid/no-mistakes) - the local git gate
pipeline that validates a branch (review, test, docs, lint, push, PR, CI)
before it reaches your real remote.

Sync is handled by [`settings-sync`](../../settings-sync/README.md):
`sync no-mistakes` merges the template below with the machine overlay and
writes `~/.no-mistakes/config.yaml`.

## The three files

```
~/gitrepos/agent-config/harnesses/no-mistakes/
├── config.yaml           tracked: shared keys only (committed - every machine gets these)
└── README.md             this file

~/.config/agent-config/overlays/no-mistakes.yaml   local: agent choice and machine paths
~/.no-mistakes/config.yaml   derived: shared defaults plus local overlay
```

Sync merges declared shared and overlay keys while retaining other native keys. Which key goes where:

| Key class | Lives in | Examples |
|---|---|---|
| Shared (same on every machine) | `config.yaml` (committed) | timeouts, auto-fix limits, review agents |
| Machine/local (per machine or per day) | `$XDG_CONFIG_HOME/agent-config/overlays/no-mistakes.yaml` | `agent`, `agent_path_override`, `worktree_roots`, `forge_profiles` |

The `agent` choice is deliberately local: flipping the gate agent is a
day-to-day decision, and the template is committed - a flip there would mean
a commit. Untracked overlay = one `sed`, one `sync`, done.

## Day-to-day: switch the gate agent

```sh
sed -i '' 's/^agent: claude$/agent: opencode/' ${XDG_CONFIG_HOME:-$HOME/.config}/agent-config/overlays/no-mistakes.yaml
agent-config sync no-mistakes
no-mistakes doctor   # "gate validation: <agent> is runnable" confirms
```

Config applies to the next pipeline run with no daemon restart (no-mistakes
re-reads global config per run).

## Using the gate

Setup is per repo, one command from inside it (needs an `origin` remote):

```sh
cd ~/your-repo && no-mistakes init
```

That creates the local bare gate repo, adds a `no-mistakes` git remote,
installs hooks, and writes the `/no-mistakes` skill into `~/.claude/skills/`
(shared skill edits go through this repo). From then on:

| You want | Run |
|---|---|
| Gate a branch (manual) | `git push no-mistakes <branch>` - pipeline runs in a disposable worktree, branch reaches `origin` only if every step passes |
| Gate + drive from an agent session | `/no-mistakes` - the skill does the task, then gates it, and escalates findings that need you |
| Check a run | `no-mistakes axi status` |
| Read pipeline logs | `no-mistakes axi logs` |
| Answer a parked finding | `no-mistakes axi respond approve\|fix\|skip` (`ask-user` findings park the run; `auto-fix` findings fix themselves) |
| Abandon a run | `no-mistakes axi abort` |
| Pull remote changes into your branch safely | `no-mistakes axi sync` |
| Drop the gate from a repo | `no-mistakes eject` (from that repo) |

The pipeline order is fixed: intent → rebase → review → test → document →
lint → push → PR → CI. Your working checkout is never touched - everything
runs in the worktree. The gate agent is whatever `agent` + `agent_path_override`
resolve to on this machine (see the flip recipe above), so on the Mac that
means the cluster models via `local-claude`, not API tokens.

## Rules for the template

- Keys must exist in no-mistakes's own config schema - it decodes strictly
  (`KnownFields`) and fails daemon startup on unknown keys. Keep this file
  minimal; never paste its ~240-line commented default.
- Bare `yes/no/on/off` scalars must be quoted (`"no"`) - pyyaml is YAML 1.1,
  no-mistakes parses YAML 1.2.
- No duplicate keys (pyyaml silently keeps the last; Go rejects the file).
- Comments survive in the template but not in the derived file.

## Updates (when no-mistakes ships a new version)

`no-mistakes update` owns the binary + daemon and never touches config:

```sh
no-mistakes update                 # binary + daemon restart
cd ~/any-gated-repo && no-mistakes init   # re-renders the /no-mistakes skill (idempotent)
cd ~/gitrepos/agent-config && git diff skills/no-mistakes  # usually empty; commit if it changed
```

`agent-config bootstrap no-mistakes` installs the pinned initial release only when absent. Routine sync updates configuration. Binary upgrades remain explicit.

## Removal

Everything here is additive. Drop this dir, the settings-sync target, and the
`~/.no-mistakes/` state; per-repo `no-mistakes eject` + the documented
uninstall (`daemon stop`, `rm -rf ~/.no-mistakes`, delete the launchd plist)
cleans the tool itself.
