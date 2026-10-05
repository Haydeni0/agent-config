---
name: write-spec
layer: worker
description: >
  Use when the user asks to write a spec or design document - typically after a grill-me session has settled the design. Turns the agreed decisions into a spec saved next to the design record and walks it through self-review and user approval. Not auto-triggered: never invoke unless the user asks for a spec/design doc or the grill ended with intent to write one.
forked-from: superpowers@claude-plugins-official v6.3.0 (brainstorming)
forked-date: 2026-09-01
forked-note: 2026-09-01 trimmed to pure spec-writer; all brainstorming dialogue moved to grill-me
---

# write-spec

Forked from superpowers:brainstorming (claude-plugins-official, v6.3.0) on 2026-09-01. 2026-09-01: trimmed to a pure spec-writer - the collaborative design dialogue lives in `grill-me`; this skill turns settled decisions into a document.

Assumes the design is already decided (usually via grill-me). Your job: capture it faithfully in a spec, review it, get approval.

## Writing the spec

**Destination:** save where the invoking instructions direct. Otherwise, next to the design you are capturing - if the design record (decisions, requirements) lives in a directory, save as that directory's `spec.md`. Starting from no recorded design, default to `.agents/plans/YYYY-MM-DD-<topic>-spec.md`.

Compose sections to fit the task - this is loose guidance, not a mandated skeleton:

- **Problem** - what and why; the friction being removed
- **Goals / Non-goals** - explicit non-goals prevent scope creep; carry YAGNI cuts from the grill here
- **Design** - approach, components, boundaries; each unit answerable: what does it do, how is it used, what does it depend on
- **Data flow** - where information moves, if it moves
- **Error handling** - failure modes that matter
- **Testing** - what gets verified and how
- **Open questions** - anything unresolved; empty is fine, "TBD" is not

Follow the repo's existing spec style if one exists. If the design covers multiple independent subsystems that weren't split during the grill, flag it and suggest separate specs - one per subsystem, each independently implementable.

## Spec self-review

After writing, look at it with fresh eyes and fix inline:

1. **Placeholder scan** - any "TBD", "TODO", incomplete sections, vague requirements? Fix them.
2. **Internal consistency** - do sections contradict? Does the design match the goals?
3. **Scope check** - focused enough for one implementation plan, or needs decomposition?
4. **Ambiguity check** - could any requirement be read two ways? Pick one, make it explicit.

Fix and move on - no re-review loop.

## User review gate

> "Spec written to `<path>`. Review it and tell me if you want changes before we write the implementation plan."

Wait for the response. If changes are requested, make them and re-run the self-review. Proceed only once approved.

## After approval

Suggest the `writing-plans` skill to turn the spec into a checkbox-tracked implementation plan (same directory as the spec - its `plan.md`, or `.agents/plans/YYYY-MM-DD-<topic>-plan.md` for a flat spec). Not mandatory - some specs get implemented directly; the user decides.

## Existing project documents

Use the global legacy-document rule before creating or resuming plans/backlogs: canonical `.agents` when present, legacy `.claude` when it is the only copy, reconcile both before resuming, editing, or migrating. Preserve IDs and checkbox progress.
