---
name: test-plan
layer: worker
description: Use when planning what tests a feature needs before or during implementation - enumerate scenarios, apply test-design heuristics, and stress-test the test plan against gaps and over-testing. Trigger when the user says "what tests does this need", "plan tests for X", "which scenarios should I cover", or when designing a feature and test coverage is undecided. Use even if the user doesn't say "test plan" - whenever the question is "what should I test" rather than "review existing tests" (that's test-add/test-trim territory). Use whenever you are about to start implementing a feature and have not yet decided what tests it needs, even if the user hasn't asked about tests explicitly.
---

# test-plan

Plan what tests a feature needs. This skill drafts a candidate test plan, then hands the draft to `grill-me` to interrogate and sharpen. It does not write test code - it produces the *plan* (what to test and why), which later TDD/implementation work consumes.

Timing-agnostic. Invoke during design, after a design is done, or mid-implementation when catching up on tests. If a diff already exists and the question is "what's missing in these tests", that's `test-add`, not this skill. This skill answers "what tests *should* exist".

## The loop

1. **Preamble** - load the canon and heuristics (below). Defer mechanics to existing skills.
2. **Draft** - enumerate candidate tests using the heuristics. Run the two gates. Label each test.
3. **Hand off to grill-me** - invoke `grill-me` with the draft as the plan to stress-test. `grill-me` sharpens fuzzy scenarios, resolves overlaps, finds gaps, ends in a decision log.
4. **Output** - inline by default. Offer to write the final plan to a file (`docs/tests/<feature>.md` or alongside the design doc) if the user wants it persisted.

## Preamble

### Pillar A - what makes a good test

Two gate checks govern every planned test. They come from `tdd-core/writing-good-tests.md` - load that skill if you need the full canon (mutation check, warning signs, the gate functions verbatim).

**Gate 1: name the break.** Before planning a test, answer: what production change makes this test fail, and is that change a bug or a decision? A test earns its place by catching a wrong branch, missing side effect, wrong argument, boundary case, or broken contract. Drop tests that can only fail through an intentional decision (change-detectors), that assert expected values computed by the code under test (mirror assertions), or that exist for coverage with no side effect or outcome.

**Gate 2: exercise the real thing.** The mock earns no assertions - a mock assertion passes when the mock is present and fails when absent, saying nothing about the component. For each dependency a planned test touches, state: real or mocked, why, and which level. If you cannot articulate why a mock is needed, the test should use the real thing. Mock at the slow/external level; keep what the test depends on real.

Plus: test the public surface, not internals (no tests of `_private` methods in keeper tests - exercise them through the public API that calls them). One logical assertion per test - if a test can fail for three different reasons, split it. Behavior, not text - run scripts/configs against controlled inputs and assert outputs/side effects; don't grep source.

### Pillar B - why this matters for AI-generated tests

LLM-generated tests hit roughly 45% statement / 30% branch coverage on real-world functions (versus near-100% on toy benchmarks), and over 99% of LLM-generated tests that *should* fail under semantic-altering changes actually pass on the original - models hallucinate requirements from training data, ignoring the explicit functional logic of the instance in front of them. The concrete failure modes:

- vacuous assertions (`assert result is not None`)
- implementation-coupled tests (asserting internal calls rather than outputs - break on refactor)
- redundant tests exercising the same path N ways
- reinventing setup in each test instead of using fixtures
- mocking so much that only mocks execute - the test proves nothing

The two gates and the anti-pattern checklist exist to defend against these documented failure modes, not to enforce taste. When you catch yourself planning a test that "fills coverage" or "verifies the object exists", stop - that is the failure mode, not the fix.

### Pillar C - test design heuristics

The planning toolkit. Apply these to enumerate candidate tests, then `grill-me` interrogates the result.

**Given/When/Then as the scenario template.** Force every candidate test into Given (preconditions) / When (action) / Then (expected outcome). This is the structural contribution of BDD; drop the Gherkin syntax and Cucumber tooling, keep the structure. Example Mapping's insight: concrete examples ARE the test list - once you can write a specific example, you have a test. Split conjunction steps ("Given X and Y" - if the "and" matters, it's two preconditions; split). A scenario you cannot phrase as Given/When/Then is too fuzzy to test - sharpen it or drop it.

**Equivalence partitioning + boundary value analysis (EP+BVA) - for numeric or range inputs.** Partition the input domain into classes where behavior should be identical (valid range, below valid, above valid). Pick one representative per class. Then test both sides of each boundary: the boundary value itself, plus one neighbor on each side (just-inside-valid and just-outside-invalid). Skipping the just-inside neighbor misses one direction of the off-by-one - a boundary test on its own cannot tell you whether `>` was used instead of `>=`. Example: quantity 1-10 valid. EP tests 0, 5, 15. BVA tests 0 (below), 1 (min), 2 (min+1), 9 (max-1), 10 (max), 11 (above). Algorithmic - apply mechanically to any function with numeric or range inputs.

**Decision tables - for multi-condition logic.** When output depends on N conditions (pricing rules, eligibility, discounts, permission checks), draw a table: rows = conditions, columns = every combination, cells = actions. Each column is one test case. The "don't care" (-) symbol reveals when a condition is irrelevant to a path. Forces exhaustive enumeration of condition combinations - the one place "exhaustive" is tractable. Blows up past 4-5 conditions; at that point use pairwise testing (test all *pairs* of parameter values - catches most bugs because a single input or pair causes most defects).

**State-transition testing - for stateful features.** When the same input produces different outputs depending on prior events (auth flows, carts, wizards, order status machines, draft/published/archived), model states + transitions + events + actions. Draw the diagram for valid paths, then build the state table to surface *invalid* transitions (e.g. "can't log in from a locked account"). Each invalid transition is a test case. Trigger this heuristic whenever the feature involves state; skip for stateless CRUD. The table is the valuable artifact - it forces enumerating invalid paths that happy-path thinking misses.

**Testing Trophy - as the level tiebreaker.** "Write tests. Not too many. Mostly integration." (Guillermo Rauch, 2016; the Testing Trophy is Kent C. Dodds). The more your tests resemble the way your software is used, the more confidence they give. Default new tests to integration level unless there's a reason:
- pure logic with no I/O -> unit test
- cross-system contract -> contract test
- critical user journey -> end-to-end test
- otherwise -> integration

Don't chase 100% coverage - diminishing returns past ~70%. If a higher-level test spots an error and no lower-level test is failing, write the lower-level test. Don't test trivial code (getters/setters, no-branch logic). Test your boundary contract, not the framework's documented mechanics.

**Anti-pattern guardrails - run the candidate list against this checklist before handing to grill-me:**
1. Don't test private methods or internal state - test through the public API.
2. Don't assert on mock call counts or sequences unless the call itself is the contract.
3. Don't test trivial code with no branching.
4. Don't test third-party code; test your integration with it.
5. One logical assertion per test - if a test can fail for three different reasons, split it.
6. Don't write tests that couple to implementation you intend to refactor.

## Phase 2 - draft

Apply the heuristics to the feature. Produce a candidate test list. One entry per test:

| Field | What it captures |
|---|---|
| Name | the scenario, named by what it asserts |
| Given/When/Then | the scenario, in that structure |
| Asserts | what it checks (the observable outcome/side effect) |
| Break it catches | the production change that makes it fail, and that the change is a bug not a decision (Gate 1) |
| Mocks | per dependency: real or mocked, why, which level (Gate 2) |
| Level | unit / integration / contract / e2e (Trophy) |
| Kind | scaffolding (drives TDD implementation, deleted after) or keeper (documents public behavior) |

Then run the two gates as filters over the draft:
- Drop tests that cannot name a bug-making break.
- Drop or fix tests with unjustified mocks.

If a feature area produces no tests that survive the gates, that area may not need tests (trivial code earns none) - say so rather than padding.

## Phase 3 - hand off to grill-me

Invoke `grill-me` with the draft as the plan to stress-test. Frame the hand-off: "Here is a draft test plan for [feature]. Stress-test it - sharpen fuzzy scenarios, resolve overlaps, find gaps, resolve dependencies one decision at a time."

`grill-me` does what it is built for: one question at a time, sharpening fuzzy language into precise canonical terms, discussing concrete edge-case scenarios, cross-referencing the code. It ends in a decision log:

```
Decision: [what was decided] - [one-line rationale]
```

The decision log becomes the test plan's rationale. If `grill-me` is not available, fall back to interrogating the draft yourself using `grill-me`'s question format (Q[N] prefix, options, recommend) - but prefer invoking the skill so the loop runs as designed.

## Phase 4 - output

Present the final test plan inline. Offer to write it to a file if the user wants to reference it during implementation - suggest `docs/tests/<feature>.md` or alongside the design doc. One-line offer, no opinion baked in; the default is inline, matching `grill-me`.

## Defer, don't duplicate

- **`pytest-guidelines`** - HOW to write pytest (uv run, mocker not unittest.mock, patch-where-used, parametrize, typed fixtures, keeper vs scaffolding). This skill references it for mechanics; it handles WHAT to test.
- **`tdd-core/writing-good-tests.md`** - the full good-test canon (gate functions, mutation check, warning signs). This skill references it for the gates; it adds the planning heuristics those gates filter.
- **`grill-me`** - the interrogative loop. This skill drafts a plan for `grill-me` to sharpen; it does not reimplement the Q&A loop.
- **`tdd` / `tdd-core`** - the red-green-refactor loop that consumes this plan. This skill produces the plan; TDD executes it.

Keeping each skill focused avoids divergence when one is updated.
