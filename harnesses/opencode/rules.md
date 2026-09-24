## opencode safety rules

These rules apply to all opencode sessions. They are opencode-specific additions to the CLAUDE.md guidelines.

### System safety

- Never use `sudo` or escalate privileges. Ask the user if a task requires root.
- Never edit system files (`/etc/`, `/usr/`, `/var/`, `/boot/`). These are outside the workspace.
- Never install system packages (`apt`, `apt-get`, `yum`, `dnf`, `brew install`). Ask the user.
- Never run destructive commands (`rm -rf /`, `dd`, `mkfs`, `shred`, `chmod -R 777 /`).
- Never modify files outside the current workspace without explicit user permission.
- Never disable security tools or weaken permissions (`chmod 777`, editing SELinux, disabling firewall).

### Network

- Never pipe remote content directly into shell (`curl ... | sh`, `wget ... | bash`).
- Never open reverse shells or background network listeners (`nc -l`, `socat`).
- Never exfiltrate data to external endpoints.

### Git

- Never `git push --force` or `git push -f` to `main` or `master`.
- Never `git push --force` to any branch without explicit user permission.

### Process

- Never background daemons or services without asking.
- Never start interactive shell sessions that bypass approval.
- When in doubt about whether an action is safe, stop and ask.

### Config management

The source checkout named in the shared routing preamble is the source of truth. `~/.config/opencode/` is derived by settings-sync. Never edit the derived target.

| Do | Don't |
|---|---|
| Edit `harnesses/opencode/opencode.json` | Edit `~/.config/opencode/opencode.json` |
| Edit `harnesses/opencode/tui.json` | Edit `~/.config/opencode/tui.json` |
| Edit `rules/global.md` | Edit `~/.config/opencode/AGENTS.md` |
| Run `agent-config sync opencode <step>` after changes | Assume changes propagate without sync |

**Red flags - stop:**
- About to write/edit a file under `~/.config/opencode/` - STOP. Edit the source checkout, then sync.
- `~/.config/opencode/` file doesn't match the source checkout - run `agent-config check opencode` to find drift.
