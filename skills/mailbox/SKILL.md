---
name: mailbox
description: Use when the user wants two or more running agent sessions (herdr panes, any harness) to talk to each other - "connect these sessions", "link these agents", "have them talk to each other", "set up a mailbox". Creates a file mailbox in the work package and hands the user one connect prompt per session. Not auto-triggered - only when the user asks to link sessions.
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
5. When the user says they are pasted, check `<mailbox>/bin/mailbox status` lists
   everyone, then read `<mailbox>/README.md` and follow it.

## Connect prompt template

```text
Run <absolute mailbox path>/bin/mailbox join <name> --role "<role>".
```

`join` prints the contract pointer itself, so the prompt is the bare
join command and nothing else.

## Update a stale mesh

Any session with this skill can migrate a mesh whose helper predates
the skill: `uv run --script <this skill's directory>/mailbox.py update
<absolute mesh path>`. It swaps the mesh's `bin/mailbox` and re-renders
its `README.md` from the current template (refusing if the mesh is newer
than this skill), then audits members: seat-less or malformed member
files are listed with a dual re-join-or-delete instruction for the
user to act on. Run it whenever a mesh shows
pre-`take` behavior or its log lacks fields the current helper writes.

## Notes

- Always give absolute paths. `.agents/work/` is gitignored, so a session
  in another worktree or checkout has its own copy; it must use this
  mailbox's absolute path, and its permission rules must allow writing
  there.
- Claude Code mesh members get a turn-end guard Stop hook (agent-config
  `hooks/mailbox-guard.mjs`, REQ-HOOKS-07): it blocks a turn end while
  unread mail waits, one forced follow-up per stop chain. It is a backstop
  behind the contract, not a substitute for taking mail.
- The contract (`take` and `inbox` checks, sending, trust, quiet peers
  via `status` and `poke`) lives in `<mailbox>/README.md`, not here. Every wake
  line points at it, so a compacted session re-learns it.
- Nothing reaps a mesh. The mesh lasts as long as its package; members
  leave by deleting their `members/<name>` file.
