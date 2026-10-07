---
name: linear-agent-update
description: Use when writing or updating any Linear comment or diff comment via the Linear MCP tools (save_comment, save_diff_comment, or editing an existing comment). Use whenever about to post to a Linear issue, project, initiative, document, milestone, or PR review.
deps: [living-doc]
---

# linear-agent-update

## Overview

Agents post verbose, partly-unverified output to Linear. Humans don't want to wade through it. This skill wraps every agent comment so the verified conclusion is visible by default and the reasoning, exploration, and speculation is hidden behind a collapsed toggle the reader can expand.

Core principle: **position is two signals at once.** The title (or short-form line) carries the verified conclusion - the bottom line a reader scans. The toggle body hides the rest: verbose reasoning and supporting detail (even when verified) AND unverified speculation (tagged `[unverified]`). A human scanning Linear sees only the verified conclusion; the volume and the uncertainty are one click away.

## When to use

Use when calling any of:
- `mcp__linear__save_comment` (new comment on an issue, project, initiative, document, milestone, or status update)
- `mcp__linear__save_diff_comment` (PR review comment anchored to a code hunk)
- Editing an existing comment (`save_comment` with `id`, or `save_diff_comment` with `commentId`)

**Not for** (do not apply this skill to):
- Status updates (`save_status_update`) - agents should not write these
- Issue descriptions / the `description` field of `save_issue` - that is the issue's body, not discussion; collapsing it hides the issue itself
- Linear documents (`save_document`)
- Issue titles, labels, status, or other structured fields

## The two forms

Every agent comment is exactly one of two forms. Pick by sentence count of the content you intend to post (count terminal punctuation: `.`, `!`, `?`).

### Short form - 2 sentences or fewer

Visible, no toggle. Bold the prefix so it stands out in a thread of human comments.

```
**AGENT:** <the content>
```

Example:
```
**AGENT:** Deploy isn't blocked on the auth refactor - they're separate modules and can ship independently.
```

### Long form - more than 2 sentences

A single Linear collapsible toggle. The title carries the verified conclusion; the body carries everything else. Default state is collapsed, so a human sees only the title until they expand.

```
+++ AGENT: <verified conclusion - one line>

<body: reasoning, exploration, steps, supporting detail - trim per below; tag any unverified claim [unverified]>

+++
```

The `+++` syntax is Linear's native collapsible section marker. The exact shape matters - blank line after the title, blank line before the closing `+++`, no text outside the toggle.

Example:
```
+++ AGENT: Fixed flaky test_token_refresh - parameterized the timeout, all 87 tests pass

Root cause: hardcoded 30s timeout raced a 45s refresh window.
Fix: timeout now derives from the refresh window.

[unverified] the same race pattern likely exists in two other test files - not yet checked.

+++
```

## What goes where - two signals, one position

The split between visible (title) and hidden (body) serves two purposes at once: it hides verbosity AND it sorts by trust.

**Title (visible) = the verified conclusion.** One line - what the agent did or observed this session, or a sound judgment it can stand behind. "Fixed the bug, tests pass" (ran them). "Recommend switching to JWT" (a judgment the agent owns). Try to verify claims before asserting them in the title. The title is the surface a reader scans and trusts; keep it to the bottom line.

**Body (hidden) = everything else.** Two kinds of content land here:
1. **Verbose verified detail** - reasoning, the exploration path, alternative approaches considered, supporting detail. All verified, but too long for a scan. The body hides the volume so it doesn't flood the reader.
2. **Unverified speculation** - any claim not yet confirmed. Tag these `[unverified]` (see below).

The rule has two halves:
- **Verbosity:** if it's not the one-line bottom line, it goes in the body - even when fully verified. The title is for scanning; the body is for the reader who wants depth.
- **Trust:** if you can't verify something, it does not go in the title. Demote it to the body and tag it `[unverified]`. Unverified content never sits in the visible layer.

So an all-verified-but-verbose update still uses the long form: the verified conclusion in the title, the verified supporting detail in the body (untagged - it's confirmed). The toggle hides verbosity regardless of trust level.

### The toggle is a floor on visibility, not a license to write more

Hiding output behind a toggle does not make verbose output fine - it just moves the cost. A reader who expands still wades through it, and you spent the effort producing it. The toggle is a safety net for content that genuinely needs depth (reasoning a reviewer may want, steps to reproduce, exploration that led to the conclusion). It is not a bin for everything you thought along the way.

Write the body as if it might be read: trim reasoning that doesn't help a reader understand or reproduce the conclusion, cut exploration that dead-ended (unless it's a gotcha worth recording), drop restated context. If the body is long, that's a signal to tighten the thinking, not a sign the toggle is doing its job. A tight body respects the reader who clicks expand; a wall of text wastes their click.

The short form exists for the same reason - if the whole update is one or two sentences, there's nothing to hide and nothing to trim. Don't pad a short update into a toggle to "use the skill properly"; the skill's goal is less noise, not more structure.

### Conversational replies (answering a direct human question)

The demotion rule above targets *unsolicited* output - the agent volunteering claims a reader will take as fact. When a human asks you a direct question in a thread and you reply, the reply is solicited: hiding the answer behind a collapsed toggle gives the human zero signal for the click they prompted. So a conversational reply stays in the short form even when based on recall rather than a fresh tool run - but it carries an inline hedge stating the verification status, instead of being demoted to a toggle.

```
**AGENT:** <answer>. <brief hedge if based on recall, not a fresh check>
```

Example (recalled, not re-verified):
```
**AGENT:** Deploy isn't blocked - separate modules, can ship independently. Recalled from an earlier code read, not re-checked this session.
```

The hedge does the honesty work the `[unverified]` tag does in the long-form body - but inline, so the answer stays visible. Do not tag conversational replies with `[unverified]`; that tag lives in the toggle body. Do not collapse a direct answer into a toggle whose title is meta-commentary ("Answer from prior reading") - that defeats the point of the reply.

This latitude is for solicited replies only. Unsolicited volunteered claims still follow the full demotion rule: unverified → toggle body, tagged.

### `[unverified]` tag

Inside the toggle body, prefix any plausible-but-unconfirmed claim with `[unverified]`. This borrows the tag from the living-doc skill - same vocabulary, same meaning: a genuine partial finding the agent intends to confirm, not a dump for unfounded guesses.

- `[unverified] the same race pattern likely exists in two other test files`
- `[unverified] bare `except:` may be intentional legacy code - author didn't respond`

The tag lives **only inside the toggle body**, never in the short form. If a claim is unverified, it cannot be in the short form - use the long form so the claim can sit in the body, tagged. The short form is reserved for verified statements and direct conversational replies.

Pure speculation the agent won't test doesn't go in at all. `[unverified]` tags a finding worth confirming, not a guess worth ignoring.

## Before you send - format check

Since there's no hook enforcing structure, this check is the only structural guarantee. Before passing `body` to the tool, verify:

1. **Right form chosen** - count sentences. ≤2 = short form. >2 = long form.
2. **Long form matches the template exactly** - starts with `+++ AGENT: `, has a blank line after the title, body content, blank line, closing `+++` as the last line. No text outside the toggle.
3. **Short form matches** - starts with `**AGENT:** `, no `+++`, no toggle.
4. **Title is verified** - nothing in the title (or short-form line) is unverified. Unverified claims demoted to body and tagged.
5. **No stray text** - the entire `body` is either the toggle or the prefixed line. No leading/trailing commentary.

If any check fails, restructure before sending.

## Edits follow the same rule

Updating an existing comment (`save_comment` with `id`, `save_diff_comment` with `commentId`) is not a bypass. The edited output must still match the correct form. In practice this means preserve the existing toggle structure and add new content in the right place: new verified content to the title or short-form line, new speculation to the tagged body.

## The one bypass

If a human explicitly tells you to post text verbatim ("post this exactly", "post this as-is", quotes something for you to relay) - transcribe it raw. Do not wrap, prefix, or tag. The skill governs agent-generated content; transcribed human content is not agent-generated.

## Common mistakes

| Mistake | Fix |
|---|---|
| Long-form comment posted with no toggle - all reasoning visible | Wrap in `+++ AGENT: <conclusion>\n\n<body>\n\n+++` |
| Unverified claim in the title stated as fact | Demote to toggle body, prefix `[unverified]` |
| Unverified claim in a short-form line | Use long form so it can sit in the body, tagged |
| Missing closing `+++` or blank lines - toggle breaks | Match the template exactly |
| `AGENT:` prefix not bolded in short form - blends into thread | Use `**AGENT:**` |
| Text outside the toggle (e.g. a stray "AGENT UPDATE" header) | Remove it - the toggle is the whole comment |
| Wrapping a human's verbatim text | Transcribe raw when told to post exactly |
| Applying the toggle to an issue description or document | Only comments and diff comments - see non-goals |
| Wall-of-text body - the toggle hides verbosity, not a license to write it | Trim: cut dead-end exploration, restated context, reasoning that doesn't help understand or reproduce the conclusion |
