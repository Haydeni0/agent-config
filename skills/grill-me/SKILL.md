---
name: grill-me
layer: worker
description: Use when stress-testing a plan or design before implementation - challenges assumptions, sharpens terminology, resolves dependencies between decisions one at a time
metadata:
  source: https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/SKILL.md
---

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one.

Do NOT use question tools or interactive modal prompts (such as `ask_question`, `AskUserQuestion`). Always output questions directly as regular markdown text in chat.

Each turn is exactly one Q[N] block, in the format below. Ask it in chat text, then stop and wait for the answer before forming the next question.

## Question format

A Q[N] block has these parts, in order:

**Q[N]:** prefix each question with its sequential number (Q1, Q2, Q3, ...).

1. **The question** - prefer concise; add a sentence of context only when the tradeoff genuinely needs it
2. **Options** - provide options in whatever format makes sense, even for open-ended questions (generate plausible candidates).
3. **Recommend:** - always present, always explicitly labeled. States your recommendation and the one-line reason.

## Responding to answers

- User says **yes / ok / y / sure**: treat your recommendation as accepted. Move to the next question silently - no echo, no confirmation.
- User gives **free text override**: incorporate it and move on. Only echo back if the override is ambiguous.
- User asks a follow-up question or gives a non-answer: answer the question, then **re-ask the same question** (same Q[N], mark as revised if needed). Do NOT move to the next question until the user has explicitly chosen an option or accepted the recommendation.

## Skip sentinel

If the user's answer contains `SKIP_GRILL` (literal, anywhere in the text), switch to auto-walk mode for the rest of the grill:

- Take your recommendation for every remaining question without waiting for further input - work straight through to the end of the decision tree, one Q[N] block after another.
- If the answer also contains a free-text override for the current question (e.g. "use X, SKIP_GRILL"), apply it to the current Q, then skip from the next one onward.
- Decisions made before the skip stay user-made; decisions from the skip onward are your recommendations.
- Skip is one-way. There is no sentinel to resume manual control. If the user wants to weigh in again, they restart the grill.

Why a literal sentinel, not fuzzy detection: the grill is a deliberate-rigor format. Casual "skip" or "idk" stays a non-answer under the rules above and gets re-asked - the sentinel is for an explicit decision to delegate the rest.

## During the session

**Sharpen fuzzy language** - when vague or overloaded terms appear, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User?"

**Discuss concrete scenarios** - stress-test domain relationships with specific edge-case scenarios that force precision about boundaries.

**Cross-reference with code** - when the user states how something works, check whether the code agrees. Surface contradictions: "Your code does X, but you just said Y — which is right?"

If a question can be answered by exploring the codebase, explore it instead of asking.

**Push YAGNI** - when an approach carries a feature nobody asked for, name it and propose cutting it. Ruthless trimming is the grill's job, not a later cleanup.

**Generate alternatives, don't confirm one** - for significant design decisions, propose 2-3 approaches with tradeoffs and your recommendation, rather than asking "does X sound good?". A single candidate hides the options nobody considered.

**Flag decomposition early** - if the request describes multiple independent subsystems, raise it before refining details: what are the pieces, how do they relate, what order? Each piece then gets its own grill → spec → plan cycle.

**Design for isolation** - as boundaries emerge, check each unit: what does it do, how is it used, what does it depend on? If a unit can't be understood without reading its internals, the boundary needs work.

**Offer the spike** - when the real question is feasibility ("can we...?"), propose a cheap probe instead of full design: state the question and probe plan in 2-3 sentences, get a nod, investigate as cheaply as correctness allows, report a recommendation. Anything built stays labeled throwaway.

## Ending the session

When all major branches are resolved, produce a **decision log** - one line per decision:

```
Decision: [what was decided] - [one-line rationale]
```

If `SKIP_GRILL` was used, split the log so the user can tell what they vetted from what they delegated. User-made decisions first, then a header marking where auto-walk began, then the auto-decided lines in the same format:

```
Decision: JWT over sessions - stateless, fits the distributed deployment
Decision: 1h token expiry - short window limits blast radius if token leaked

Auto-decided after SKIP_GRILL at Q4:
Decision: httpOnly cookie for refresh token - XSS-safe, JS cannot read it
Decision: rotate refresh token on use - limits replay window
```

Why split the log: if a skipped decision later surprises the user, they need to see it was auto-decided so they know what to revisit - not silently trust it as something they signed off on.
