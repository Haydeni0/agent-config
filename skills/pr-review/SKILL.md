---
name: pr-review
description: Use when reviewing a GitHub pull request by number - checks out the PR, runs the code-review skill, and writes the review to a local file
deps: [code-review]
disable-model-invocation: true
argument-hint: <PR-number>
allowed-tools:
  - Bash(gh pr checkout *)
  - Bash(gh pr view *)
  - Bash(gh pr checks *)
  - Bash(gh pr diff *)
  - Bash(git diff *)
  - Bash(git fetch *)
  - Bash(git log *)
  - Bash(git merge-base *)
  - Bash(git rev-parse *)
  - Bash(git show *)
  - Bash(git status *)
  - Bash(cat *)
  - Bash(head *)
  - Bash(tail *)
  - Bash(grep *)
  - Bash(rg *)
  - Bash(ls *)
  - Bash(find *)
  - Bash(wc *)
  - Bash(uv sync*)
  - Read(*)
  - Grep(*)
  - Glob(*)
  - Agent(*)
---

Parse `$ARGUMENTS` as `<PR-number>` (required).

Do NOT run tests, build commands, or attempt to fix anything - this is a read-only review. You may run `uv sync` to set up the environment (and view `.venv` for context on installed packages), but do NOT execute project code. Forbidden: `python`, `python3`, `pip`, `npm`, `node`, `make`, `cargo`, `docker run/build`, `pytest`, or any command that runs/compiles project code.

## Steps

1. **Checkout the PR** (user-authorized working-tree mutation - the user invoked `/pr-review` knowing it switches branch)

   ```bash
   gh pr checkout $PR_NUMBER
   ```

2. **Set up environment**

   ```bash
   uv sync
   ```

3. **Gather PR context**

   - `gh pr view $PR_NUMBER --json title,body,author,baseRefName,headRefName,additions,deletions,changedFiles` for metadata.
   - `gh pr checks $PR_NUMBER` for CI status (context only - do not investigate or fix failures). Add a "## CI Status" section after the Summary in the final review with a brief note on passing/failing checks.

4. **Fetch base branch**

   ```bash
   git fetch origin <baseRefName>
   ```

   Use the `baseRefName` from step 3. This ensures `origin/<baseRefName>` is current before diffing.

5. **Dispatch the code-review orchestrator**

   Dispatch one orchestrator subagent. It must be able to spawn its own subagents (the orchestrator procedure runs 4 parallel lens subagents + 1 verifier) - use an unrestricted/general-purpose agent, never a single-shot/fork-style agent (forks are one-shot and forbidden from spawning subagents). If the harness cannot spawn subagents at all, skip dispatch and run the orchestrator procedure inline yourself, then continue at step 6.

   Pass it:
   - The resolved scope: `ref:origin/<baseRefName>` (the orchestrator maps this to `git diff origin/<baseRefName>...HEAD` - three-dot, deterministic, matching GitHub's PR view). No inference or ambiguity-asking - pr-review resolves the scope explicitly.
   - The PR title and description as context (the description informs what's intentional, stopping a reviewer from flagging an intentional refactor).
   - The full orchestrator procedure from the [code-review](../code-review/SKILL.md) skill (stages 1-4: context, 4 parallel lenses, verify, deliver). Paste that procedure into the orchestrator's dispatch prompt.

   The orchestrator runs read-only - no `Write`/`Edit`, no mutating git commands, no project-code execution. (The `gh pr checkout` and `uv sync` above are pr-review's responsibility, already done; the orchestrator inherits the read-only constraint.)

6. **Deliver - override the core's Deliver stage**

   The code-review core's Deliver stage emits the review to chat. pr-review overrides this:

   - The orchestrator returns the review markdown to pr-review (instead of emitting to chat).
   - Write the returned markdown to `pr-<PR_NUMBER>-review.md` in the repo root. This file is the single output - strip any leaked agent working notes so it contains only the review markdown (Summary through Verdict, plus the CI Status section after the Summary).
   - In chat, emit ONLY a one-line pointer: the file path and the Verdict line. Example: `Review written to pr-405-review.md - Verdict: Comment`. Do not paste the review body or wrap it in narration.
   - Do not post a PR comment (`gh pr comment`). The user reads the file and posts manually if they want.
