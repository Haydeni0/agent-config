---
name: code-review
description: Use when reviewing uncommitted changes, a branch diff, or any git diff for bugs, security issues, CLAUDE.md compliance, and quality problems - works on local work with no PR required
---

# Code review

## Overview

Multi-lens code review of a git diff. The main session resolves the scope (asking the user if ambiguous), then dispatches one orchestrator subagent (unrestricted, able to spawn its own subagents) that runs 4 parallel review lenses and a verify pass, returning a severity-grouped review. Harnesses without subagent spawning run the whole procedure inline. The core is read-only: it never writes, edits, or mutates the repository, and never runs commands that compile or execute project code.

## Hierarchy

```
main session (/code-review or model-invoked)
  ├─ pre-step: resolve scope (parse phrase; if ambiguous, ask user)
  └─ orchestrator subagent (unrestricted, spawns its own subagents; dispatched with resolved scope + the procedure below)
       ├─ stage 1: context (git diff, gather CLAUDE.md)
       ├─ stage 2: 4 lens subagents (parallel; inline sequential if no subagent spawning)
       ├─ stage 3: verify subagent (score + dedup; inline if no subagent spawning)
       └─ stage 4: deliver (return review markdown to main session)
  └─ main session emits returned markdown to chat
```

The main session does NOT spawn the lenses or collate their output. It resolves scope (including user interaction, which subagents cannot do), dispatches one orchestrator subagent (unrestricted/general-purpose - not a single-shot/fork-style agent, which cannot spawn the lenses), and emits the orchestrator's returned review. If the harness has no subagent spawning at all, the main session runs the orchestrator procedure inline. The body of this skill IS the orchestrator's procedure - paste it into the orchestrator's dispatch prompt.

## Pre-step (main session, before dispatching the orchestrator)

Resolve the scope.

Parse the user's scope phrase. Run `git status --short` and `git diff --stat` to assess ambiguity. Common interpretations:

| User means | Resolved scope (passed to orchestrator) |
|---|---|
| "uncommitted" / "my changes" / nothing said but uncommitted changes exist | `uncommitted` |
| "staged" / "cached" | `staged` |
| "this branch" / "the branch" / nothing said AND no uncommitted changes | `branch` |
| A ref (`origin/main`, a SHA, a tag) | `ref:<ref>` |
| A file or path ("just src/auth", "this file") | append `path:<path>` to whichever scope above |

If the scope is ambiguous between plausible interpretations (e.g. both uncommitted changes AND a branch ahead of upstream, with no phrase disambiguating), ask the user one clarifying question. Do not pick a default silently. If unambiguous, proceed.

Pass the resolved scope token (e.g. `uncommitted`, `branch`, `ref:origin/main`, `branch path:src/auth`) to the orchestrator. Dispatch it as an unrestricted/general-purpose agent that can spawn its own subagents - never a single-shot/fork-style agent, which is one-shot by definition and cannot run the parallel lens stage. If the harness cannot spawn subagents at all, skip dispatch and run the orchestrator procedure below inline (all four stages, sequentially). Then emit the review markdown to chat.

## Orchestrator procedure (paste into the orchestrator's dispatch prompt)

You are a code review orchestrator. You receive a resolved scope and run four stages. If your harness cannot spawn subagents, run all four stages inline yourself, sequentially, with the lens subagent prompts executed as inline analysis passes instead of separate agents. You are read-only: do not write, edit, or mutate any repository file, and do not run commands that compile or execute project code (no `python`, `npm`, `make`, `pytest`, `cargo`, `docker run`, etc.). Return the final review markdown as your response.

### Stage 1: Context

Map the resolved scope to git commands:

| Scope | Commands |
|---|---|
| `uncommitted` | `git diff` + `git diff --cached` |
| `staged` | `git diff --cached` |
| `branch` | `git diff @{u}...HEAD` (three-dot from upstream tracking branch; fallback `origin/main`, then `origin/master` if no upstream) |
| `ref:<ref>` | `git diff <ref>...HEAD` (three-dot) |
| `... path:<path>` | append `-- <path>` to the diff command above |

Three-dot (`...`) is mandatory for branch/ref scopes - it diffs from the merge-base, showing only this branch's changes (GitHub's PR view). Never two-dot (`..`) for review - it diffs tips and pulls in the base branch's drift as if you removed it.

Run the diff. Also run `git log --oneline <base>..HEAD` for commit narrative (where a base ref exists).

Gather instruction files, following `@import` lines inside each: the user-level `~/.claude/CLAUDE.md`, the repo root `AGENTS.md` and `CLAUDE.md`, plus any `AGENTS.md` or `CLAUDE.md` in directories touching modified files. Cap the total at 500 lines (truncate with a `...(truncated)...` marker) so a giant instruction file doesn't blow the reviewers' context. Deduplicate: a `CLAUDE.md` that only `@imports` `AGENTS.md` contributes its imported content once.

### Stage 2: Review (4 parallel subagents)

Dispatch 4 subagents in parallel as foreground agents (multiple Agent tool calls in a single message, not `run_in_background`). Foreground returns all results inline when complete so Stage 3 can proceed immediately; background dispatch forces a wait loop and blocks the orchestrator. If the harness has no subagent spawning, run the 4 lenses inline sequentially - same prompts, same calibration rules, one after another. A lens that returns an empty findings list has completed successfully - do not re-dispatch a lens that has returned. Only re-dispatch on a confirmed agent error, never on absence of a completion notification. Each returns findings as a structured list, never prose:

```
- file: <path>
  header: <one-or-two-word title>
  content: <what's wrong, why it matters, the realistic trigger scenario - no line numbers in this field>
  start_line: <int>
  end_line: <int>
  severity: <Critical|Major|Minor>
  lens: <which lens found it>
```

The four lenses:

**Lens 1 - CLAUDE.md / instruction-files compliance.** Audit the diff against the gathered instruction files. For each finding, the lens must cite which instruction file and which line calls out the issue. Not all instructions in CLAUDE.md are applicable during review (some are guidance for writing code, not review criteria) - flag only violations of instructions that are enforceable on the diff.

When checking docstring/comment slop specifically, look for: comments at the same altitude as the code (restating a line in prose), docstrings that just restate the function name/signature, closing-brace/end-of-block comments (`# end for`), negation statements ("does not X"), lineage/incident history ("moved from X", "see incident #123"), line-number cross-refs into the same repo, and per-subclass restatement of base-class behavior. Do not flag a contract-defining docstring on a public function/module boundary - that's documentation, not slop.

**Lens 2 - Bugs in diff.** Shallow scan of the diff only. Focus on large bugs. Ignore small issues and nitpicks. Do not read extra context beyond the changes themselves. Ignore likely false positives.

**Lens 3 - Full-file + caller-trace depth.** Read the full file (working tree) for each changed file, not just the diff. Trace how the changes interact with callers, dependencies, and downstream consumers. Check whether the changes break any implicit contracts or assumptions in adjacent code. This lens catches issues the shallow scan misses.

**Lens 4 - Git history / blame.** Read `git blame` and `git log -p` for the modified regions. Flag changes that revert or contradict prior intent (e.g. "this removes the null check added in commit X to fix issue Y").

Each lens prompt MUST include these calibration rules (give them to the lens subagent verbatim):

- For clear bugs and security issues, be thorough. Do not skip a genuine problem just because the trigger scenario is narrow.
- For lower-severity concerns, be certain before flagging. If you cannot confidently explain why something is a problem with a concrete scenario, do not flag it.
- Each issue must be discrete and actionable, not a vague concern about the codebase in general.
- Do not speculate that a change might break other code unless you can identify the specific affected code path from the diff context.
- When confidence is limited but potential impact is high (e.g. data loss, security), report it with an explicit note on what remains uncertain. Otherwise, prefer not reporting over guessing.

False-positive examples to ignore (give to each lens verbatim):

- Pre-existing issues unrelated to the current changes.
- Something that looks like a bug but is not actually a bug.
- Pedantic nitpicks a senior engineer wouldn't call out.
- Issues a linter, typechecker, or compiler would catch (missing imports, type errors, formatting, pedantic style). Assume CI runs these.
- General code quality issues (test coverage, documentation) unless explicitly required in an instruction file.
- Issues called out in an instruction file but explicitly silenced in the code (e.g. a lint-ignore comment).
- Changes in functionality that are likely intentional or directly related to the broader change.
- Real issues on lines the diff did not modify.

### Stage 3: Verify (single subagent)

Dispatch one verifier subagent as a foreground agent (not `run_in_background`); if the harness cannot spawn subagents, run the verification inline. It receives all structured findings from all 4 lenses and:

1. **Dedup across lenses.** Same file + overlapping line range + same issue → merge into one finding. Keep the higher-severity label. Combine the content fields.

2. **Score each finding 0-100** using this rubric (give the rubric to the verifier verbatim):
   - 0: Not confident. False positive that doesn't stand up to light scrutiny, or a pre-existing issue.
   - 25: Somewhat confident. Might be real, might be false positive. Not verified. If stylistic, not explicitly called out in an instruction file.
   - 50: Moderately confident. Verified real, but might be a nitpick or rare in practice. Not very important relative to the rest of the diff.
   - 75: Highly confident. Double-checked, very likely real, will be hit in practice. The existing approach is insufficient. Important - directly impacts functionality, or directly mentioned in an instruction file.
   - 100: Absolutely certain. Double-checked, definitely real, happens frequently. Evidence directly confirms.

3. **For CLAUDE.md-flagged findings**, double-check that the cited instruction file actually calls out the issue specifically.

4. **Drop findings with score < 80.**

### Stage 4: Deliver

Assemble surviving findings into the output format below. Return this markdown as your response (the main session emits it to chat).

```
## Summary
One-line description of what this change does.

## Findings

### Critical
- [file:line] Description

### Major
- [file:line] Description

### Minor / Nits
- [file:line] Description

## Questions
Things that are unclear or need author clarification.

## Verdict
Approve / Request Changes / Comment - with brief justification.
```

If a section has no findings, omit it (e.g. no Critical findings → drop the Critical heading). Always include Summary and Verdict.

Comment-construction rules:

- Be direct about why something is a problem and the realistic scenario where it manifests.
- Communicate severity accurately. Do not overstate impact. If an issue only arises under specific inputs, say so upfront.
- Keep each issue description concise.
- Matter-of-fact tone. Avoid accusatory language, excessive praise, or filler like "Great job", "Thanks for".

For each finding, include a full-SHA blob link to the cited lines with at least 1 line of context before and after:

```
https://github.com/<owner>/<repo>/blob/<full-sha>/<path>#L<start>-L<end>
```

Use the full SHA (run `git rev-parse HEAD`), never `$(git rev-parse HEAD)` embedded in the URL - the comment renders Markdown directly. Repo name must match the repo being reviewed. Line range format is `#L[start]-L[end]`. If commenting about lines 5-6, link to `#L4-L7`.

## Review criteria

Evaluate against these (skip any that don't apply):

- **Correctness:** bugs, edge cases, off-by-one, race conditions.
- **Security:** injection, auth gaps, secrets, input validation.
- **Performance:** unnecessary allocations, O(n²) where O(n) is possible, missing indexes, I/O in hot paths, missing caching (non-negligible cases).
- **Readability:** naming, structure, unnecessary complexity, deep nesting, unclear control flow, functions too long to hold in head.
- **Maintainability:** separation of concerns, tight coupling, duplicated logic, unclear module boundaries, hardcoded assumptions, over/under-abstraction.
- **Breaking changes:** API surface, backward compatibility, config changes.
- **Dependencies:** new dependencies justified and secure.
- **Missing coverage:** untested paths that should have tests (note them, don't write them).

Guidelines:

- Keep findings concise and actionable. Reference specific lines.
- Do not suggest stylistic changes unless they hurt readability.
- Do not flag pre-existing issues unrelated to the current changes.

## Read-only rule (mandatory)

The core is read-only. It must not write, edit, or mutate repository files, and must not run commands that compile or execute project code. The core emits its review to chat - it writes no files.

| Excuse | Reality |
|--------|---------|
| "I found a bug, I'll just fix it" | No. The core reviews, it never fixes. Fixing mutates the repo and breaks review isolation. |
| "The user would want me to fix this" | If they wanted fixes, they'd ask. Review output only. |
| "It's a one-line obvious fix" | Still a write. Report it as a finding, don't apply it. |
| "Running the tests will confirm my finding" | No. Running tests executes project code and may mutate state. Report what you see in the diff. |
| "I'll just stage the change to verify" | Staging mutates the index. No. |

**Red flags - STOP:**
- About to run `Write` or `Edit`
- About to run `python`, `npm`, `make`, `pytest`, `cargo`, `docker run`, or any build/test command
- About to run `git add`, `git checkout`, `git reset`, `git stash`, or any mutating git command
- "I'll just quickly fix this"

All of these mean: stop. Report the finding in the review instead.
