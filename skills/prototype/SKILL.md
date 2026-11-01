---
name: prototype
layer: worker
deps: [work-package, grill-me]
description: Use when a feature's main uncertainty is human judgement - how it looks or feels - and the design should be settled by building a throwaway artifact the human reacts to, before any spec or clean build. Covers terminal rendering, dashboards, API/class shape ("does this feel right to call"), and any visual or experiential design, including demos a non-developer judges. Starts light and promotes its record to a work-package on first suspend or handoff, filing user-facing requirements as R entries, taste verdicts as D entries, unsettled mechanism as Q entries. Trigger phrases include "could we prototype this first?", "I want to see what it looks like", "let's try a few designs". Skip for logic-only features with settled design.
---

# prototype

Before committing to a design a human must judge, build a throwaway artifact from real material, let the human react to it, iterate until it survives the ugly cases, then record what the artifact taught you - user-facing requirements, taste verdicts, open questions - for the design grill that follows, and discard the artifact once the real build no longer needs it.

**The one invariant: the human reacts to something concrete, in their real environment - never to a description.** Every guideline below serves that.

## When (and when not)

Prototype when the main uncertainty is human judgement, not mechanism - output is visual, or a system whose *shape* must feel right. When design is settled and only implementation is uncertain, skip straight to spec/plan: prototyping there is pure overhead.

The artifact's form follows its purpose: rendered output for visuals, worked usage examples for API/class design, a script driving the real system end-to-end for system design.

## Guidelines

**State the question first.** Before writing code, write the design question in one paragraph, in a block labelled `Design question:` at the top of the artifact, in user-observable terms - the taste or shape uncertainty this artifact exists to settle; on promotion it anchors the work-package record. A prototype that answers the wrong question is pure waste.

**Know who is judging.** When the judge is a non-developer (a PM, a domain expert), the artifact must speak their language: labels read like the business, not the code; it opens by double-click with nothing to install; and it carries 2-3 guided walkthroughs of the awkward cases as named tabs - the ugly corpus made drivable by a non-expert. When the judge is the developer, form stays free.

**Ugly-but-real, scoped by what is being judged.** The smallest thing that puts the real experience in front of the human. Hardcode whatever isn't the point; skip layering, plumbing, tests. The only quality bar is "the human can judge the experience from it." When the question is about content, density, layout, or volume, real material is mandatory - live data, real volumes, real hostile names - because synthetic fixtures hide exactly the edge cases you are prototyping to find. When the question is transition semantics or shape (a state model, an API's feel), in-memory synthetic state is the designed form. No persistence, ever: the prototype checks behavior, it never depends on plumbing.

**Rounds count only in the human's environment.** The medium the agent previews in is not the medium the human works in - display, scaling, fonts, and interaction all differ between them - so no round counts until the human has seen the real artifact where they work. Between rounds, self-serve mechanics freely: try variants internally, measure sizes, check edge cases. Where the human reacts in chat, present one concrete thing at a time - a menu of descriptions shifts design from taste to pick-listing. But flipping between concrete, in-environment variants is reacting, not pick-listing: a variant switcher on the real surface is allowed - 3-5 variants, structurally different (layout, information hierarchy, primary affordance; colour or copy tweaks are wallpaper), free to throw out the layout while sharing fine details. "The header from B with the sidebar from C" is a design outcome, not indecision.

**Surface the state.** After every action or variant switch, render the full relevant state as a labelled, readable panel - not a raw dump. The moments that matter ("wait, that shouldn't be possible") only fire when the change is visible.

**The exit gate is two-part: "looks good" AND "survived the ugly corpus."** Before sign-off, exercise empty results, single item, hostile inputs (names that break markup/escaping), extreme volumes, the worst-case row count. Happy-path rounds catch taste problems; the corpus catches correctness ones.

**Wipe the slate, record the exception.** The prototype never graduates into product code - it is structurally compromised (no layering, no tests, hardcoded shortcuts) and glancing at it for an implementation trick during the clean build is fine; *copying* is the failure mode the rule guards against. One exception: when the artifact's core is a pure module and that module IS the validated decision, it may lift into the real build - only when a decision entry records the lift, never silently; engineer the core liftable (pure, page-independent) or it cannot lift at all. Discard fires at effort end, once the downstream design has taken the record over and the real build no longer needs to glance at the artifact - never at a spec, never at promotion; a mid-iteration suspend leaves the artifact alive. A module named by the recorded lift stays exempt until the real build claims it or the effort ends.

**The record outlives the round.** Start light: the design question at the top of the artifact is all that persists. Promote to a work-package (the work-package skill owns the layout) at first suspend or handoff, whichever comes first. The handoff record: user-facing requirements as R entries - what the user observes, never how (no module shape, no code, no tech choice); taste verdicts and rejected alternatives as D entries, rejections named so taste is never relitigated; unsettled mechanism as Q entries.

**Then settle what pixels cannot.** Once taste is settled, interrogate the rest - flags, defaults, semantics, naming, edge-case behaviour - and file what the human ruled on into the record's R and D entries. The next step is a design grill (grill-me) that consumes the entries; a spec comes only after the grill has settled design, because a spec is for settled design and would drag implementation decisions in too early.

## Anti-patterns

- **Write code first, add tests later** - no: the prototype is discarded; product code is TDD-built fresh from the design that follows.
- **Proof-of-feasibility spike only** - no: feasibility is a bonus; the point is design judgement by a human on real material.
- **Synthetic-data demo where material is the point** - no: when the question is content, density, layout, or volume, real volumes and hostile names surface what fixtures hide - synthetic fixtures judged for material qualities are this anti-pattern. In-memory synthetic state for transition-semantics and shape questions is the designed form (see Ugly-but-real), not this anti-pattern.
- **Human reviews a description/proposal** - no: they react to the artifact, in their environment, every round.
- **Implementation detail in the handoff record** - no: R entries state what the user observes; module shape, code, and tech choice belong to the downstream design.
- **Silently lifted prototype code** - no: a lift-out is a recorded decision or it did not happen.
- **Wallpaper variants** - no: variants that differ only in colour or copy are tweaks, not prototypes.
- **Wiring persistence into a prototype** - no: state lives in memory; a prototype checks behavior, it never depends on plumbing.
