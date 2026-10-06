# reflect - DRAFT

Companion to `SKILL.md` in this directory. Tracks the skill's status,
its fixed intent, open questions, and field notes from real sessions.
Edit the source copy at `skills/reflect/` in the agent-config source
checkout, never a synced copy.

## Status

Draft. Not baseline-tested - the writing-skills Iron Law is
deliberately deferred: real sessions are the test corpus. Promote to
stable when the field notes cover at least three sessions across more
than one repo or kind of work, and every open question below is
answered or consciously dropped. On promotion, remove the DRAFT marker
from `SKILL.md` (heading note and description) and from this file's
title, and fold settled answers into the skill.

## Intent

Change these only deliberately; field notes refine the procedure, not
the intent.

- General: any learning that improves the next session, not only
  repo-agent-setup files.
- Smallest change at the narrowest correct layer - often none.
- Diagnose before routing: missing, ignored, and stale rules need
  different fixes.
- The user decides every change.

## Open questions

1. **Trigger** - user-only `/reflect`, or should agents suggest it
   (session end, after a user correction)? Currently user-only.
2. **Repetition evidence** - the agent cannot see past sessions. Ask
   the user, search transcripts, or keep a "seen once" log somewhere?
3. **Cross-repo edits** - reflect running in repo X edits the
   agent-config source checkout directly. Acceptable, or queue to the
   agent-config backlog instead?
4. **Harness-native memory** (e.g. Claude auto-memory) - a destination,
   or ignored in favour of portable files?
5. **Boundaries** - reflect is session-driven and incremental;
   repo-agent-setup audit mode and doc-sweep are whole-file hygiene. Is
   that split right in practice?
6. **Granularity** - one question per candidate may drag for many small
   items. Batch approval?

## Iterating on this skill

For an agent the user pointed here from another task, because something
in that session should shape `/reflect`:

1. Restate the case in 2-3 lines - what happened, what reflect did or
   would have done, what the user wanted instead. Confirm with the user.
2. Append a field note below.
3. Generalise: name the gap in the skill, not the instance. Test: would
   the change help a different repo or task? If not, the learning
   belongs in that repo, not here.
4. Propose the exact edit, one question at a time. Prefer editing or
   deleting over adding. Mark any open question it answers.
5. Apply in the source checkout, run `scripts/check-skills.py`, then
   `agent-config sync` and `agent-config check`.

## Field notes

Newest at top. Template:

```markdown
### YYYY-MM-DD - <repo or task> - <one line>

- Invoked: how and when reflect ran, or the moment it should have
- Happened: candidates found, routes chosen
- Worked:
- Felt off:
- Skill change: none | <summary>
```

None yet.
