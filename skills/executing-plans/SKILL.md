---
name: executing-plans
description: >
  Use when the user asks to execute or implement a written implementation plan (checkbox-tracked plan file), in this or a fresh session. Not auto-triggered: never invoke unless a written plan document exists and the user asks to carry it out.
forked-from: superpowers@claude-plugins-official v6.3.0 (executing-plans)
forked-date: 2026-09-01
forked-note: description rewritten to require explicit user request; see Provenance line in body
---

# executing-plans

Forked from executing-plans (plugin claude-plugins-official, v6.3.0) on 2026-09-01; description rewritten to require explicit user request.

# Executing Plans

## Overview

Load plan, review critically, execute all tasks, report when complete.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."



## The Process

### Step 1: Load and Review Plan
1. Ensure an isolated workspace: create a git worktree manually (or verify the existing one) if isolation is wanted
2. Read plan file
3. Review critically - identify any questions or concerns about the plan
4. If concerns: Raise them with your human partner before starting
5. If no concerns: Create todos for the plan items and proceed

### Step 2: Execute Tasks

For each task:
1. Mark as in_progress
2. Before writing any implementation code, invoke the `tdd` skill.
3. Follow each step exactly (plan has bite-sized steps)
4. Run verifications as specified
5. Mark as completed

### Step 3: Complete Development

After all tasks complete and verified:
- Verify tests pass, then summarize the work and ask the user how to finish (merge, PR, keep branch) - per your normal git workflow

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Remember
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Stop when blocked, don't guess
- Never start implementation on main/master branch without explicit user consent

## Existing project documents

Use the global legacy-document rule before creating or resuming plans/backlogs: canonical `.agents` when present, legacy `.claude` when it is the only copy, reconcile both before resuming, editing, or migrating. Preserve IDs and checkbox progress.
