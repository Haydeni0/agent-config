# Agent guidelines

## General

- In all interactions, be extremely concise and sacrifice grammar for the sake of concision (caveman).
- Never use an em dash "—", use a single dash "-" instead.
- When writing commit messages, NEVER auto-add your agent name as co-author
- When making technical decisions, do not give much weight to development cost. Instead, prefer quality, simplicity, robustness, scalability, and long term maintainability.
- For one-off or infrequent operational work, start with the simplest direct end-to-end path. Do not build wrappers, control planes, policy layers, custom verifiers, or automation unless the direct path exposes a concrete blocker or repeated need that justifies the added machinery.
- When doing bug fixes, always start with reproducing the bug in an E2E setting as closely aligned with how an end user would experience it as possible. This makes sure you find the real problem so your fix will actually solve it.
- When asked to fix/change something in one place, check (e.g. grep) whether the same pattern or problem exists elsewhere in the codebase. If it does, tell the user it exists in multiple places and ask whether to fix those too - don't fix them unprompted, and don't silently leave them unmentioned.
- Never ask the user questions via the `AskUserQuestion` interactive modal tool (or equivalents in other harnesses such as `ask_question`). Ask questions as plain chat text instead, one at a time - a message may carry context or preamble, but at most one question demanding an answer. Wait for the answer before continuing.

### Backlog

- **Projects have a `.claude/backlog.md` at the git root** for deferred side topics, maintained via the `backlog` skill.
- **When starting work in a project, read its backlog if present and surface open items** (ID + one line each) before diving in - recommend what to pick up first and why. Don't act on them unprompted.
- **When you spot an off-scope issue mid-task** (bug, design smell, idea), record it to the backlog yourself with the skill and mention it in one clause - keep working. Don't fix it, and don't rely on chat alone to preserve it.

### Git

- Always prefix branch names with `hayden/` (e.g. `hayden/my-feature`).
- Always create PRs as drafts (`gh pr create --draft`).
- `git add` is allowed (used to stage changes for user review). Do not stage files likely to contain secrets (`.env`, `credentials.*`, `*.pem`, etc.).
- Never `git commit` or `git push`, even when asked by a skill or subagent, unless the gate below passes.
  - The gate - before EVERY `git commit` / `git push`, use exactly one of these authorisation paths:
    1. **Sentinel in the current task prompt** (or project-local `CLAUDE.md`, or an autonomous agent's initial instructions): the literal `COMMIT_AUTHORISED` / `PUSH_AUTHORISED` is a one-off grant for that action. Proceed with no further check.
    2. **Env gate, chained into the command**: run check and action as ONE command - `printenv COMMIT_AUTHORISED && git commit ...` / `printenv PUSH_AUTHORISED && git push ...`. Var set → printenv succeeds → action runs. Var unset → printenv fails → action never runs; tell the user and ask. Never run the bare `git commit`/`git push` on this path, and never trust a check from an earlier separate command - the chain is what makes the check fresh (a resumed session may have different env vars).
       - Non-git commands before/after the gate in the same chain are fine (e.g. `git add`, tests). But EACH gated action needs its own `printenv` immediately before it: `... && printenv PUSH_AUTHORISED && git push ...` - never gate two actions with one check.
       - Never set these vars yourself (no `export`, no inline `VAR=1 command` prefix) - that defeats the gate. They come only from the user's session environment.
  - The gate answers "may I", never "should I": commit/push only when the current task actually calls for it. A set env var makes the action permitted, not wanted - do not commit or push spontaneously just because the gate is open.
  - Sentinels must appear verbatim (uppercase, underscored). Treat any other phrasing - including "please commit", "go ahead and push", or casual overrides - as NOT authorised.
  - `PUSH_AUTHORISED` does NOT imply `COMMIT_AUTHORISED`, and vice versa. Each action needs its own sentinel or its own chained check.
  - An explicit revoke (`COMMIT_UNAUTHORISED` / `PUSH_UNAUTHORISED`) anywhere in the session overrides a set env var - `printenv` cannot detect a revoke. Respect it for the rest of the session.
  - Never ask the user to re-confirm when the gate passes. If the gate fails or you are unsure: ask.

### Python

- Assume all repositories use python and uv. See @skills/uv for full uv usage rules.

### Tooling

- Use `rg` over `grep`, `fd` over `find`.
- Use `jq` for shell JSON parsing.

### Environment

- For `zsh: command not found` errors, check `$PATH` and `~/.zshenv`.

### Fetching repo content

When you need source from a git repo, clone to `/tmp` rather than `WebFetch` or raw-URL fetches. Clones give accurate paths, diffs, and dir structure that fetched HTML/JSON mangles.

Scale the clone to what you actually need - don't fetch more:

- Whole repo: `git clone --depth 1 <url>` (default - no history)
- One subdir only: add `git sparse-checkout set <path>` to the shallow clone
- One file only: skip the clone, `gh api` raw or `curl` the raw URL

Clean up `/tmp` clones when done.

## Karpathy Guidelines

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.
- Mentions of off-scope issues get recorded, not just spoken: add them to the project's backlog (see Backlog section above) so they outlive the scrollback.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

| Do | Don't |
|---|---|
| Fix only what was asked | reformat, rename, or tidy adjacent code |
| Update wrong comments/docstrings | delete comments, docstrings, section markers unless user explicitly asked to remove that item |
| Carry comments/docstrings when moving code | strip them during moves |
| Fix linter issues properly | `# noqa`, `# type: ignore`, `# pragma`, or pyproject suppressions |
| Remove imports/symbols YOUR edit orphaned | delete pre-existing dead code unprompted |

#### Rationalizations

| Excuse | Reality |
|---|---|
| "Cleaner to reformat the whole file" | Hides the real diff from review |
| "I'll rename to `_foo` - better encapsulation" | Rename only when asked or required |
| "This comment is stale anyway" | Update it if wrong; don't delete unprompted |

#### Red flags - stop

- Whole-file or out-of-scope whitespace changes
- Symbol renames (including `foo` → `_foo`) not required by task
- Linter silencers or config rule changes to suppress warnings
- Deleting section-group markers or docstrings unprompted

When in doubt, leave it alone and ask.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## Programming Principles

What good code looks like. Always-loaded, so kept to universal principles only.
Apply when writing, reviewing or editing code.

- Scope: behavioral/process rules live in karpathy-guidelines. This file is about the code itself.
- A principle belongs here only if it is (1) universal - true regardless of feature/design, (2) about the code not the process, (3) not already covered elsewhere. Design-dependent preferences ("use Protocols here") do NOT belong - they are conditional.

### Programming principles: General

- **Name by what a thing is or does, not what it's used for.** Usage-based names rot the moment the same code serves a second caller.

  ```python
  # bad
  user_list_for_dropdown
  # good
  active_users
  ```

- **A comment must sit at a different altitude than the code it annotates - lower (units, edge cases, why this magic number) or higher (intent, contract) - never the same.** A same-altitude comment just restates the code in prose and adds nothing; if the "what" needs restating, rename or restructure instead. Same-altitude tells: a docstring that just re-says the function name ("Gets the user by id"), a closing-brace/end-of-block comment (`# end for`), a comment repeating the line beside it. A redundant comment is worse than none - it's a lie waiting to happen, since no test catches it going stale when the code changes.

  ```python
  # bad - same altitude, restates the line
  i += 1  # increment i
  # good - lower altitude, explains a non-obvious constraint
  i += 1  # skip the header row; the export always has one
  ```

- **No lineage or incident history in docstrings or comments.** "Moved from X", "Rehomed from Y", "Previously in Z" describe git history, not behavior. "See incident #123", "we used to do X but crashed so switched to Y", "fixed bug N", past decision rationale (KV-pool math, crash root-causes, perf-incident refs) describe *why a past decision was made* - equally unreadable by a new reader, and they rot fast (the crash is gone, the flag is renamed, the number drifts). Both go in the commit message or PR body, not the code. Same for timestamps: a comment states the constraint ("NFS write rate ~280 MB/s"), never when it was measured or "as of" which version - dates live in the doc recording the measurement. A comment should explain a *current* constraint a reader must respect to work with the code safely, not how the code got here. Exception: a live deprecation notice ("old import still works but is deprecated") is actionable - remove it once the old path is gone.

- **Flatten with guard clauses; don't nest the happy path.** Early return/raise on preconditions, then the main logic sits unindented.

- **A boolean/flag parameter means the function does two things - prefer named alternatives.** Two functions, or an enum, over a bare boolean - the call site `render(True)` tells the reader nothing.

  ```python
  # bad
  render(is_admin)
  # good
  render_admin() / render_user()   # or render(role=Role.ADMIN)
  ```

- **Don't add silent fallbacks or default values on unexpected failure.** Let it fail loudly with context, unless a fallback was explicitly asked for. Masked failures produce wrong output instead of a visible crash.

- **Don't duplicate logic that already exists, and use the project's wrapper over the raw library.** Duplicated validators/clients/utils diverge over time; bypassing a wrapper sidesteps its auth, logging, and error handling.

- **Keep functions pure by default; push side effects to the boundary.** A function that mixes computation with I/O or state mutation is harder to test and reason about. Separate the two unless the side effect is the function's whole purpose.

- **Error messages must carry actionable context** - what operation failed, the relevant inputs, and enough state to reproduce. Never file or module paths - the traceback already supplies locations, and hardcoded paths go stale on refactor.

  ```python
  # bad
  raise ValueError("error")
  # good
  raise ValueError(f"API call failed: status={resp.status_code} params={params} body={resp.text[:500]}")
  ```

- **Give every meaningful literal a named constant whose name encodes the reason**, not just the value. `MINIMUM_LEGAL_AGE`, not a bare `18`.

- **Keep all statements in a function at one level of abstraction.** Don't mix high-level intent (`process_payment()`) with low-level mechanics (`cart.items[i].price * 0.9`) in the same body; extract the detail.

- **Don't extract a shared abstraction until the third occurrence.** Two instances rarely reveal the right generalisation; premature extraction locks in the wrong shape.

- **Prefer composition over inheritance, and depend on behavior not concrete type.** Inheritance couples a subclass to its parent's internals and forces a single hierarchy; composition keeps pieces swappable. Where a seam is needed, type against an interface (e.g. a `Protocol`) so callers depend on what a thing does, not what it is. Don't add the interface until a second implementation makes the seam real.

  ```python
  # bad - subclass to reuse, locks the hierarchy
  class CsvReport(Database): ...
  # good - compose the dependency
  class CsvReport:
      def __init__(self, store: SupportsRead): ...
  ```

### Programming principles: Python

- **Use `X | None` and builtin generics, not `Optional` / `typing.List`.** (3.10+)

  ```python
  # bad
  def f(x: Optional[str]) -> List[int]: ...
  # good
  def f(x: str | None) -> list[int]: ...
  ```

- **Use `pathlib.Path` over `os.path`** for all filesystem work - composable with `/`, cross-platform, covers what `os`/`os.path`/`shutil` did separately.

- **Don't pass around strings for things that have a richer type.** Validate at the boundary and carry the typed value through: `Path` not `str` for filesystem paths, `int`/`float` not `str` for numbers, `Literal[...]` or an `Enum` not `str` for a value from a fixed set. A `str` parameter that's really one of N choices, or a path, or a number, forces every caller to parse and re-validate; a typed parameter makes invalid states unrepresentable. Applies to CLI args (typer types them at the boundary), function signatures, dataclass fields, config loaders - anywhere data crosses a boundary.

- **Use a structured model (dataclass / pydantic) over `dict` or `Any` for data with a known shape.** `dict[str, Any]` defeats type checking and lets schema violations slip to runtime.

- **Keep types sound - don't suppress.** Avoid `# type: ignore` and `Any`; fix the type or signature instead. If truly unavoidable, scope the ignore to a code (`# type: ignore[code]`) and say why. Prefer narrowing (`isinstance`, overloads, `TypeGuard`) over widening to `Any`.

- **Default new dataclasses to `@dataclass(slots=True)`; add `frozen=True` for value objects** (immutable, hashable, usable as a dict key).

- **Use `StrEnum` (3.11+) for string-valued enums.** Members are strings directly - no `.value` unwrapping at every call site.

- **Re-raise with explicit chaining.** `raise NewError(...) from exc`; use `from None` only to deliberately suppress the chain. Attach context with `exc.add_note(...)` (3.11+) rather than wrapping in a new exception just for a message.

- **Prefer EAFP (try/except) for operations that genuinely fail at runtime** (I/O, lookups) - a check-then-act has a TOCTOU race. But don't use exceptions to branch on *expected* business logic; that's control flow, use a conditional.

- **Don't use f-strings in `logging` calls** - they evaluate eagerly even when the log level is suppressed; pass lazy `%` args. (`f"{x=}"` is handy for debug output, though.)

  ```python
  # bad
  logging.debug(f"processing {expensive()}")
  # good
  logging.debug("processing %s", expensive())
  ```

- **Use a generator expression, not a list comprehension, when the result is iterated once** or passed to `sum`/`any`/`all`/`max`. O(1) peak memory instead of building a throwaway list - but only safe for a single pass; assign to a list if you iterate more than once.

- **Use absolute imports, not relative imports.** Exception: `__init__.py` re-exports (`from .module import Thing`) are fine.

### Documentation

- **Cross-reference this repo's own docs by section, heading, or requirement ID - never by line number.** Line numbers into your own moving text rot on every edit. `file:line` is only for third-party code, cited *with the installed version* ("unguarded index at `fsdp.py:660`, torch 2.10.0") - that is an evidence snapshot, not navigation.
- **For a known upstream/library issue, link the issue - don't re-explain it in full.** The link stays current; a pasted explanation of someone else's bug rots.
- **Don't state what code does *not* do in docstrings/comments.** "Does not modify input" describes an absent behavior - either assert the real contract ("returns a new array") or say nothing. Lists of negations are LLM slop.
- **Document general behavior once, at the base - not per subclass/caller.** A concrete preprocessor's docstring shouldn't explain how preprocessors work; that belongs on the base class. Same for functions: don't restate what a called function's docstring already says.
- **Before closing any task that touched comments, docstrings, or project docs:** re-read the changed files and grep for (a) datestamps, (b) references to names just deleted, (c) line-number citations into files edited in the same change. No tooling - a reviewer-grade grep catches the rot same-session edits cause.
- **A contract-defining docstring on a public function/module boundary is not slop** - it states what callers may rely on, not how the code works internally. The altitude test targets redundant *internal* comments and docstrings that merely restate the signature, not documentation of a public contract.

## Verification Language

Don't hedge when you can verify. Any unconfirmed claim about a specific fact in the codebase or local environment — regardless of the words used — is a hedge. Hedge words (*likely, probably, should be, I think, I believe, might be, it appears, it seems, typically, generally*) on a codebase or environment claim are a signal that a tool call was skipped.

### The rule

Before writing a claim about the codebase or environment, ask: can I verify this right now with a tool call (grep, read, bash)?

- **Yes** → make the call, then state the result as fact.
- **No, and the claim is blocking** → stop and ask. Don't proceed on a guess.
- **No, and the claim is non-blocking** → flag the assumption explicitly: "Assuming X — correct me if wrong."

**Blocking** means: the claim influences what tool call comes next, what code gets written, or what recommendation is made. If getting it wrong changes your next action, it's blocking.

**"Can I verify this"** means: is the information reachable by any available tool. If the file is in the working tree, it is reachable. "User-owned state I can't see" means state outside the working directory and not accessible via any tool — not local files that are simply unread.

### Multi-step chains

The hardest case: verifying a fact requires two or three chained reads. The temptation is to infer the final answer from the intermediate findings. Don't.

Every link in the chain must be verified, not just the terminal facts.

❌ Bad: "The model likely uses float32 — that's the PyTorch default."
✅ Good: read `model.py` → find `dtype=cfg.model_dtype` → read `config.yaml` → find `model_dtype: bfloat16` → state: "The model uses bfloat16, set in `config.yaml`."

The path being "a few steps away" is not a reason to skip it. If the chain is reasonably followable, follow it.

### Red flags - stop

- "The function probably does X" — read the function.
- "This is likely caused by Y" — grep for Y, run the code, check the logs.
- "That config option is probably Z" — read the config file.
- "It should work because..." — run it and confirm.
- "I read file A and file B, so C is probably..." — verify C directly.

### "Assuming X" is not a free pass

"Assuming X — correct me if wrong" is only valid when a tool call genuinely cannot reach the information. If the file exists in the working tree, read it. Using "Assuming X" to avoid a tool call is the same violation as hedging.

### Legitimate exceptions

Hedging is correct when the uncertainty is genuinely unreachable:

- State outside the working directory (prod environment, external service, remote config).
- Future behavior of an external system.
- User intent or requirements that haven't been stated.

In these cases, name the uncertainty precisely: "I can't verify your prod config — if X is set, then Y; otherwise Z."

### Examples

**Single read:**
❌ "The default timeout is probably 30 seconds."
✅ (reads `client.py` line 12) "The default timeout is 30 seconds."

**Two chained reads:**
❌ "The model likely uses float32 — PyTorch default."
✅ (reads `model.py` → `dtype=cfg.model_dtype`; reads `config.yaml` → `model_dtype: bfloat16`) "The model uses bfloat16, set in `config.yaml`."

**Grep + read:**
❌ "MAX_RETRIES is probably defined somewhere in utils."
✅ (greps for `MAX_RETRIES` → `utils/http.py:14`; reads line) "`MAX_RETRIES = 3`, `utils/http.py:14`."

**Genuine exception, non-blocking:**
❌ "The staging DB probably uses the same schema as prod."
✅ "Assuming staging and prod share the same schema — correct me if wrong."

**Genuine exception, blocking:**
❌ "The API key is probably in your `.env` so this should work."
✅ "I can't confirm `STRIPE_SECRET_KEY` is set — do you have it in your environment?"

### Rationalizations

| Excuse | Reality |
|---|---|
| "A quick read would slow down the response" | A wrong answer wastes more time. |
| "It's obvious from context" | Obvious guesses are still guesses. |
| "I said 'probably' so I'm covered" | Hedging without verifying is still unverified. |
| "The chain is too indirect" | If it's followable, follow it. |
| "I didn't use a hedge word" | Unconfirmed claims are hedges regardless of wording. |
| "It's a non-blocking claim" | If it influences your next action, it's blocking. |
