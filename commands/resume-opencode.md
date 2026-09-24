---
name: resume-opencode
description: Resume an opencode session inside the current Claude Code session. Converts an opencode session transcript from SQLite and ingests it as context. Takes an optional session id or title substring as $ARGUMENTS; with no argument, lists recent sessions to pick from.
---

# resume-opencode

Resume an opencode conversation inside this Claude Code session. Reads the opencode SQLite DB, converts a chosen session into a markdown transcript, and ingests it as context so the conversation can continue here.

The converter is a uv project at `~/gitrepos/agent-config/opencode-resume/`. Stdlib only (sqlite3, json). Run it via `uv run` from its directory.

## On invocation

1. Resolve the session and emit the **full transcript** to capture as your context. Run with the user's `$ARGUMENTS` (may be empty):
   ```
   cd ~/gitrepos/agent-config/opencode-resume && uv run python -m opencode_resume.cli $ARGUMENTS
   ```
   Capture stdout - this is the prior turn history you continue from.
2. Print a **truncated preview** to the user so they can sanity-check the right session was converted:
   ```
   cd ~/gitrepos/agent-config/opencode-resume && uv run python -m opencode_resume.cli $ARGUMENTS --preview
   ```
   The preview shows the header + first/last few turns with a truncation marker.
3. State one line: which session you resumed (title + opencode session id), and that the full transcript is now your context.
4. Await the user's next message. Do not summarise or act unprompted - the transcript ends with a continuation prompt; you respond to what the user says next.

## If $ARGUMENTS is empty

The converter prints a numbered list of recent top-level sessions to stderr and waits on stdin. Run it without arguments; the list lands in the tool output for the user to read. Ask the user which number or title substring they want, then re-run with their choice as the argument.

## Notes

- Only top-level sessions are offered (subagent sessions are excluded).
- Tool outputs are size-thresholded by the converter (<2KB kept verbatim, >=2KB truncated to 500 chars) - you may not have full tool output for every prior call.
- The transcript format is markdown prose (`**User:**` / `**Assistant:**` / tool blockquotes) with a metadata header.
