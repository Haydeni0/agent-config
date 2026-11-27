---
name: tui
layer: worker
deps: [prototype, tdd-core, writing-plans, work-package]
description: Use when building, extending, or restyling a terminal UI - a full-screen interactive TUI or dashboard, a "tui" subcommand in the style of "cw slurm tui", a Textual/curses app, or a lazygit-style keyboard-driven terminal interface. Also triggers on "make it look like the cw tui", "add a view/panel to the tui", "tui theme", or restyling an existing terminal UI. Not for plain one-shot CLI output.
---

# tui

Build TUIs the way this user's accepted TUIs were built: one fixed look ported from the settled palette, digit-switched lazygit-style views, a throwaway prototype the user reacts to in their own terminal, pure-render views under golden tests, real-terminal (pty) verification layered above simulated-input tests, and performance budgets pinned as tests.

**Default stack: Python + Textual + rich**, matching all accepted builds. Deviate only when the host project's language forces it - then port the principles, not the library calls.

**The user's taste is the point.** Never invent a look, a layout, or a keymap. Start from `references/theme.md`, and where it flags an open question, ask the user - one question at a time, each with a recommendation.

## Non-negotiables

1. **Prototype first.** A throwaway single-file app against live data, before any spec. Nothing graduates from the prototype - only recorded taste verdicts do. Use prototype.
2. **Pin the visual contract explicitly.** The spec must carry the palette hexes, box borders, meters, and selection treatment verbatim, or the planner never carries them over (the rebuild that lost the look: methodology.md, The iterate loop).
3. **Views are pure functions.** Typed models + view state + width -> rich Text (or the framework's equivalent). The app shell owns layout, keys, and the refresh loop; it owns no data logic. Most of the TUI is then testable without the framework running.
4. **Never render fake data.** Uncapped has no fraction, so no bar. Unknowns get an explicit quiet marker (dim "…", the raw number, "(unattributed)"), never a blank, a zero, or an invented value.
5. **Every key visibly does something.** A no-op key reads as broken; the esc grammar lives in theme.md (Interaction model).
6. **Self-review visually, from the user's seat.** Screenshot every view at fixed sizes after each wave, review the shots, and keep a live preview the user can run. Code review waits until the visual passes settle.
7. **Simulated-input green proves nothing.** Pilot/synthetic key tests pass while the real terminal is broken; at least one real-pty test layer is mandatory for keys and mouse.
8. **Performance is a gate, not a hope.** Budgets are pytest tests; measure before optimizing - the profile-first overturns are recorded in methodology.md (Performance).
9. **Theme fidelity over framework defaults.** One theme module owns every colour; no literal colour string survives outside it.
10. **Keyboard-first.** Every action is reachable by keys. Mouse is strictly optional enhancement and no feature may depend on it: its bytes cross terminal and multiplexer layers the app does not control (methodology.md, Mouse and terminal input).

## The iterate loop

`references/methodology.md` owns the full loop (The iterate loop): investigate -> prototype -> code-facts inventory -> decisions as law -> plan reviewed by running it -> prefactors -> red-first implementation waves -> taste checkpoints -> live-behavior verification -> measure-first perf -> bounded bug hunts -> release pty smoke.

Scale the machinery to the build: the full loop is the ceiling for a multi-week TUI; a single-view TUI keeps the non-negotiables (prototype-first taste, red-first TDD, goldens, one real-pty layer, perf budgets, measure-before-optimizing) and drops the rest.

## Reference routing

Read only what the current phase needs:

| Need | Read |
|---|---|
| Colors, palette hexes, meters, charts, logs, layout, keybindings, the user's taste rules | `references/theme.md` |
| Loop detail, the five testing layers, pty/screenshot harnesses, perf budgets and measurement rules, pitfalls and framework traps | `references/methodology.md` |

## Red flags - stop and check

- Designing a look before the user has reacted to a running prototype.
- A colour literal outside the theme module, or a second palette for one view.
- A theme switcher, passthrough CLI args, or an auto-scaling y-axis - all explicitly rejected by the user.
- All tests green, but no test has ever fed real terminal bytes or run in a real pty.
- A mouse fix chosen before a trace of the user's real mouse in the user's real terminal showed which stage the click is lost in.
- Claiming "fast" with no measured number, or optimizing before a profile named the dominant phase.
