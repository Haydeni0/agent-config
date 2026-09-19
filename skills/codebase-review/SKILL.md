---
name: codebase-review
description: Use when reviewing a module, directory, or file for structural issues - complexity, duplication, dead code, coupling, cohesion, module boundaries - without a diff or PR
---

# codebase-review

## Overview

Multi-lens structural review of a file or directory. The main session resolves the target (asking the user if ambiguous), then dispatches one orchestrator subagent that runs per-file review subagents, a cross-file subagent, and a verify pass, returning a category-grouped review. The skill is read-only: it never writes, edits, or mutates the repository, and never runs commands that compile or execute project code.

## Hierarchy

```
main session (/codebase-review or model-invoked)
  |- pre-step: resolve target (infer path from CWD/context; if ambiguous, ask user)
  +- orchestrator subagent (dispatched with resolved target + procedure below)
       |- stage 1: context (enumerate files, build import graph)
       |- stage 2: per-file subagents (N parallel, one per file, 3 lenses each)
       |- stage 3: cross-file subagent (1, sees graph + per-file summaries)
       |- stage 4: verify subagent (score 0-100, drop <80, dedup)
       +- stage 5: deliver (return review markdown to main session)
  +- main session emits returned markdown to chat
```

The main session does NOT spawn the per-file or cross-file subagents. It resolves the target (including user interaction, which subagents cannot do), dispatches one orchestrator subagent, and emits the orchestrator's returned review. The body of this skill IS the orchestrator's procedure - paste it into the orchestrator's dispatch prompt.

## Pre-step (main session, before dispatching the orchestrator)

Resolve the target. The user may give an explicit path ("review src/auth", "review this file: lib/http.py") or be vague ("review this module", "review the auth code").

If the user gives an explicit path, use it.

If the user is vague, infer from CWD and context:
- If CWD is inside an obvious module/package (e.g. `src/auth/`, a single Python package dir), review that.
- If CWD is the repo root with multiple top-level dirs, or the target is ambiguous, ask the user one clarifying question ("which directory?").

Do not default to reviewing the whole repo when CWD is repo root - that floods output and wastes subagent calls. Ask.

Pass the resolved target path to the orchestrator. Then dispatch the orchestrator subagent with that path and the procedure below, and emit its returned review markdown to chat.

## Orchestrator procedure (paste into the orchestrator's dispatch prompt)

You are a structural code review orchestrator. You receive a resolved target path (a file or directory) and run five stages. You are read-only: do not write, edit, or mutate any repository file, and do not run commands that compile or execute project code (no `python`, `npm`, `make`, `pytest`, `cargo`, `docker run`, etc.). Return the final review markdown as your response.

### Stage 1: Context

Enumerate files in the target:
- If the target is a file, the file list is just that file.
- If the target is a directory, enumerate recursively. Use `find <target> -type f \( -name "*.py" -o -name "*.ts" -o -name "*.js" -o -name "*.go" -o -name "*.java" -o -name "*.rb" -o -name "*.rs" -o -name "*.c" -o -name "*.cpp" \)` (extend the extensions for the repo's languages). Exclude tests, vendored code, build artifacts, and `.git`.

Cap at 50 files. If the target exceeds this, review the largest/most-imported files first and note the truncation in the review's Summary ("Reviewed N of M files; truncated."). Do not silently review a subset without noting what was dropped.

Build the import graph:
- Detect the primary language from file extensions.
- Primary method (language-agnostic, portable): `rg '^(import |from \S+ import |#include |using |require\()' <target>`. This produces raw import lines with file paths - the format the cross-file lens reads directly. For an N-file module this is ~N*10 lines, smaller and more directly useful than a full graph JSON.
- Supplement for cycle detection (optional, when `uvx` is available, Python only): `uvx --from pydeps pydeps --no-output --show-cycles <target>`. The `--no-output` flag skips SVG rendering (which requires graphviz `dot`); cycle detection works without it. Use `--show-cycles` only (not `--show-deps` - the full dep JSON bloats context with fields the lens doesn't need).
- Supplement for JS/TS (optional, when `npx` is available): `npx madge --circular <target>` for explicit cycle detection.
- The graph from grep is approximate. The cross-file lens reads actual code for semantic judgment on top of it.

Gather instruction files, following `@import` lines inside each: the user-level `~/.claude/CLAUDE.md`, the repo root `AGENTS.md` and `CLAUDE.md`, plus any `AGENTS.md` or `CLAUDE.md` in the target directory. Cap at 500 lines total (truncate with a `...(truncated)...` marker) so a giant instruction file doesn't blow the reviewers' context. Deduplicate: a `CLAUDE.md` that only `@imports` `AGENTS.md` contributes its imported content once.

### Stage 2: Per-file review (N parallel subagents)

Dispatch one subagent per file in parallel. Each reads its file once and applies 3 lens checklists. Returns findings as a structured list:

```
- file: <path>
  header: <one-or-two-word title>
  content: <what's wrong, why it matters, the realistic impact on maintainability - no line numbers in this field>
  start_line: <int>
  end_line: <int>
  impact: <severe|moderate|minor>  (rough; verifier re-derives from score)
  lens: <Complexity|DeadCode|SOLID>
```

The three per-file lenses (each subagent applies all three; structure the prompt with explicit lens sections):

**Lens 1 - Complexity & Bloat:**
- Cyclomatic/cognitive complexity (functions with many branches, deep nesting).
- Long methods (functions too long to hold in head - rough threshold 50+ lines for business logic).
- Large classes/files (god classes; files 500+ lines).
- Primitive obsession (overuse of primitives where a value object fits).
- Long parameter lists (5+ params where a parameter object fits).
- Data clumps (the same group of fields passed together across many call sites).

**Lens 2 - Dead Code & Dispensables:**
- Unused/unreachable code (defined-but-never-called functions, unreachable code after return/raise).
- Lazy classes (classes doing almost nothing, could be a function or inlined).
- Speculative generality (abstraction/extension points with one or zero implementations; "flexibility" nobody uses).
- Dead flexibility (config flags nobody sets, hooks with one subscriber).

**Lens 3 - SOLID & OO Abuse:**
- SRP / god class (one class/file with multiple unrelated responsibilities).
- OCP / switch-on-type (switch or if-chain over type codes, modified for each new variant).
- LSP / contract break (subtype silently violates parent invariant).
- ISP / fat interface (clients forced to implement unused methods).
- DIP / concrete dependency (high-level module imports concrete low-level, not an abstraction).
- Feature envy (method more interested in another class's data than its own).
- Inappropriate intimacy (two classes reaching into each other's internals).
- Middle man (class that just delegates, adds no behavior).
- Refused bequest (subclass that doesn't honor the parent's contract).
- Temporary field (field set only in some code paths, null otherwise).

Each lens prompt includes calibration rules:
- For clear structural issues (god class, dead code, circular dep), be thorough.
- For judgment-call smells (feature envy, primitive obsession), be certain before flagging - if you cannot concretely explain the maintainability cost, do not flag it.
- Each issue must be discrete and actionable, not a vague concern about the codebase in general.
- Do not flag intentional design choices unless they introduce a clear maintainability cost.
- When confidence is limited but the smell is severe (e.g. a 2000-line god class), report it with an explicit note on what remains uncertain. Otherwise, prefer not reporting over guessing.

False-positive examples to ignore:
- Stylistic preferences without a maintainability cost.
- Issues a linter/formatter would catch (assume CI runs these).
- Intentional patterns the codebase consistently uses (don't flag a project's chosen convention).
- Test files unless the structural issue is in the test code itself.
- Generated code.

### Stage 3: Cross-file review (1 subagent)

Dispatch one cross-file subagent. It receives the import graph (from stage 1) + per-file finding summaries (from stage 2). It checks:

- **Duplication:** repeated logic across files (copy-paste, near-duplicate functions). Identify the files and the duplicated region.
- **Coupling & cohesion:** afferent/efferent coupling, instability (Ce/(Ce+Ca)). Flag modules that are both highly depended-on and highly instable, or packages with low internal cohesion. Use the graph for numbers; read code for whether the coupling is justified (DI factories, shared schemas are not necessarily bad).
- **Circular dependencies:** cycles in the import graph. List the cycle.
- **Module boundaries:** leaks across module/context boundaries (one module reaching into another's internals). Flag the boundary violation.
- **Dependency direction:** arrows that point outward where they should point inward (domain importing frameworks; low-level importing high-level). Flag the direction.
- **Shotgun surgery:** a change concept that requires edits across many files (inferred from scattered related code).

Returns structured findings (same schema, with `lens: CrossFile`; `file` may be `path1, path2` for cross-file findings; line ranges optional).

The cross-file lens does NOT re-flag per-file issues. Its domain is relationships between files.

### Stage 4: Verify (1 subagent)

Dispatch one verifier subagent. It receives all findings (per-file + cross-file) and:

1. **Dedups.** Same file + overlapping line range + same issue -> merge. For cross-file findings, dedup against per-file if the per-file lens already flagged the same root cause.

2. **Scores each finding 0-100** using this rubric (give to the verifier verbatim):
   - 0: Not a real smell. Subjective preference, not a structural issue.
   - 25: Might be a smell, unverified. Could be intentional or context-dependent.
   - 50: Real smell but minor. Low impact on maintainability.
   - 75: Verified smell, materially hurts maintainability, worth addressing. Future work is harder because of this.
   - 100: Severe, clearly harmful, high effort multiplier on future work.

3. **For CLAUDE.md-flagged findings**, double-check the cited instruction actually calls out the issue.

4. **Drops findings with score < 80.** Survivors are scored 80-100; the verifier maps the score to an impact label for the output: 80-89 = `moderate`, 90-100 = `severe`. (`minor` findings, score <80, are dropped.) The per-file subagent's rough `impact` field is discarded - the verifier's score-derived label is the one shown.

### Stage 5: Deliver

Assemble surviving findings into the output format below. Return this markdown as your response.

```
## Summary
One-line description of the target's structural state.

## Findings

### Complexity & Bloat
- [file:line] <finding> [impact: severe|moderate]

### Dead Code & Dispensables
- [file:line] <finding> [impact: ...]

### SOLID & OO Abuse
- [file:line] <finding> [impact: ...]

### Cross-file Structure
- [file:line or file:file] <finding> [impact: ...]

## Questions
Things that need author clarification.

## Verdict
Assessment of the target's structural health + top 1-2 priorities.
```

Omit empty categories. Always include Summary and Verdict.

Comment-construction rules:
- Be direct about the structural issue and the maintainability cost it imposes.
- State the impact accurately. Do not overstate. If the cost only manifests under specific conditions, say so.
- Keep each finding concise.
- Matter-of-fact tone. No accusatory language, no excessive praise, no filler.

## Review criteria

Structural quality is judged on:
- **Complexity:** cyclomatic/cognitive load, function/class/file size, nesting depth, parameter lists.
- **Cohesion:** whether a module's parts belong together (SRP, LCOM).
- **Coupling:** afferent/efferent coupling, instability, dependency direction, circular deps.
- **Duplication:** repeated logic across files.
- **Dead code & flexibility:** unused code, speculative generality, dead config.
- **SOLID adherence:** the 5 principles, concretely detected.
- **Boundaries:** module/context leaks, shotgun surgery.

Not judged (out of scope - use other skills):
- Correctness bugs (use `code-review`).
- Security (use `code-review` or `security-review`).
- Performance (unless the structural choice causes a clear perf cost).
- Style/formatting (assume CI handles).
- System architecture across multiple services (out of scope).

## Read-only rule (mandatory)

The skill is read-only. It must not write, edit, or mutate repository files, and must not run commands that compile or execute project code. It reports findings; it never applies fixes.

| Excuse | Reality |
|--------|---------|
| "I found a god class, I'll just split it" | No. Refactoring mutates the repo and breaks review isolation. Report it as a finding. |
| "The user would want me to fix this" | If they wanted fixes, they'd invoke `simplify`. This skill diagnoses. |
| "It's a one-line dead-code deletion" | Still a write. Report it, don't apply it. |
| "Running the tests confirms the refactor is safe" | No. Running tests executes project code and may mutate state. |
| "I'll just stage the change to verify" | Staging mutates the index. No. |

**Red flags - STOP:**
- About to run `Write` or `Edit`.
- About to run `python`, `npm`, `make`, `pytest`, `cargo`, `docker run`, or any build/test command.
- About to run `git add`, `git checkout`, `git reset`, `git stash`, or any mutating git command.
- "I'll just quickly refactor this."

All of these mean: stop. Report the finding in the review instead.
