---
name: mailbox
description: Use when the user wants two or more running agent sessions (herdr panes, any harness) to talk to each other - "connect these sessions", "link these agents", "have them talk to each other", "let the planner delegate to the worker pane", "set up a mailbox". Creates a file mailbox in the work package and hands the user one connect prompt per session. Not auto-triggered - only when the user asks to link sessions.
deps: [work-package]
---

# mailbox

A file mailbox linking already-running agent sessions in herdr panes. The
payload is files, the wake is one pointer line typed by herdr, and there is
no server or watcher. Any harness whose agent can run shell commands can
join.

Requires: `HERDR_ENV=1` (every session in a herdr pane) and `uv`.

## Set up a mesh (the session the user asked)

1. Load the `work-package` skill and find this conversation's package; if
   there is none, create `.agents/work/<date>-<topic>/` for it. The mailbox
   is `<absolute package path>/mailbox`. If that directory already has a
   `README.md`, the mesh exists - skip to step 3.
2. Create it, using this skill's directory for the helper:

   ```bash
   uv run --script <this skill's directory>/mailbox.py init <absolute package path>/mailbox
   ```

3. Join it yourself: `<mailbox>/bin/mailbox join <your name> --role "<role>"`.
   Names are lowercase letters, digits and hyphens (`planner`, `worker-1`).
4. Give the user one connect prompt per other session (template below), to
   paste into that session's pane. Do not type it into other panes
   yourself: the user typing it is what grants the session's trust.
5. When the user says they are pasted, check `ls <mailbox>/members/` lists
   everyone, then read `<mailbox>/README.md` and follow it.

## Connect prompt template

```text
You are `<name>` (<role>) in the agent mesh at `<absolute mailbox path>`.
Run `<absolute mailbox path>/bin/mailbox join <name> --role "<role>"`, then
read `<absolute mailbox path>/README.md` and follow it for the rest of this
session.
```

## Notes

- Always give absolute paths. `.agents/work/` is gitignored, so a session
  in another worktree or checkout has its own copy; it must use this
  mailbox's absolute path, and its permission rules must allow writing
  there.
- The contract (inbox checks, ack by moving to `handled/`, sending,
  trust, quiet peers) lives in `<mailbox>/README.md`, not here. Every wake
  line points at it, so a compacted session re-learns it.
- Nothing reaps a mesh. The mesh lasts as long as its package; members
  leave by deleting their `members/<name>` file.
