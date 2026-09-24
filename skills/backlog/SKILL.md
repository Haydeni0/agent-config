---
name: backlog
description: Use when the user defers a side topic mid-work, suspends the current topic into the backlog, or asks to see or close deferred items. Capture triggers - "one other thing", "one more thing", "before I forget", "side note", "side topic", "save this for later", "park it for later", "note this down", "just noting", "come back to this", "talk about this later", "at some point", "things to pick up on". Suspend triggers - "put this in the backlog", "let's leave this for later". Recall triggers - "backlog", "what's next", "clear out the backlog", "next session". Never trigger on "jot" - the user never uses it.
---

# Backlog

Append deferred side topics to `.agents/backlog.md` at the git root so they survive to a later session. Chat-only acknowledgments rot with scrollback; the file is the record.

## When

- User defers a topic mid-work: "one other thing - we should also X, but finish Y first"
- User notices a problem but wants current work to finish first: "I don't like this design, but let's finish X"
- User suspends the current topic into the backlog: "put this in the backlog", "let's leave this for later"
- User asks for the backlog: "what's next", "check the backlog", "clear out the backlog"
- User closes items: "that's done", "/backlog done 3"

## Capture

1. Resolve target: git root + `.agents/backlog.md`. If cwd is not a git repo, cwd + `.agents/backlog.md`.
2. If only `.claude/backlog.md` exists, read and keep using that legacy file until this project is deliberately migrated. If both files exist, surface both and reconcile before editing. Preserve IDs. Create the canonical file with this template only when neither exists:

   ```markdown
   # Backlog

   Deferred items for this project. Surfaced when starting work here; picked up on request.

   ## Open
   ```

3. Next ID = max existing `#N` in file + 1. IDs are never reused, so deletions don't renumber.
4. Append under `## Open`:

   ```markdown
   - #7 [2026-08-31] <text>
   ```

   Longer thoughts get continuation lines indented under the bullet. Concise by default; no hard cap.
5. Mention in chat in one clause ("noted to backlog as #7").
6. Resume the flow exactly as it stood:
   - Capture scope: only what the user deferred. Never capture conversation or agent state on your own initiative - pending questions, options awaiting a choice, the agent's own analysis, in-flight work. Those live in the conversation, not the backlog.
   - Restore that state unchanged: pending question re-presented with its options, half-done task continues. A deferral is never an answer, decision, or advance signal, so nothing about the pending state changes - it is not dropped, answered, or parked.
   - Exception - user orders the capture: "put this topic in the backlog", "let's leave this for later". The current topic itself goes to the backlog, recorded with its live state ("decision pending, options (a)/(b)/(c)"). This is a suspend, not a deferral: the conversation moves on - a pending question is recorded, not re-presented. Ask what's next (or let the user name it).

## Recall

`/backlog` bare, "what's next" → print open items, ID + one line each. Don't stop at listing: recommend what to pick up next (judge by relevance to current work, age, size) and say why. If an item needs clarification before it's actionable, ask about it - one question at a time.

If the trigger arrives mid-flow (interview, review, task), resume the pending step exactly after capture/recall - a deferral is never an answer, decision, or advance signal. Capture records only user-deferred topics, never conversation state (see Capture step 6).

## Close

- `/backlog done <id>` → move the line to a `## Done` section (create after Open if missing), keeping ID and date.
- `/backlog clear` → delete the `## Done` section contents.
- Closing is user-disposed: when the agent notices an open item was clearly addressed by work just done, it suggests closing ("#3 looks covered - close it?") and moves it only on confirmation. User-initiated close is unconditional.

## Rules

- Everything deferred goes here. No routing to QUESTIONS.md or similar unless the user names that file.
- "jot" is not a trigger word - the user never uses it.
- No git operations on this file. It shows as untracked in git status; that is intended.
- When starting work in a project that has a backlog, surface open items before diving in (see the backlog rule in global CLAUDE.md).
