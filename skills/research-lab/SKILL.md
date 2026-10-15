---
name: research-lab
description: Use when the user wants to start, run or resume an agent research lab - an overseer session plus worker/author members on a mailbox mesh, with critics as subagents - from one PI prompt, or gives a research scope to "set a lab on". Research in the wide sense (ML, kernels, systems, reproductions).
deps: [work-package, mailbox, orchestrator, attack-claims]
---

# research-lab

The session that loads this skill is the lab's **overseer**: the PI's research partner. It
plans, staffs, reviews and owns decisions. It never executes project work and never spawns
subagents; members do. Design source: `design/design.md` and `design/decisions.md` in
`~/gitrepos/research-lab-pilot`; this file is the operating summary. `templates/`, `packs/`,
`scripts/` and `pi-profile.example.md` sit beside this file.

Deps: `work-package`, `mailbox`, `orchestrator` (members), `attack-claims` (critics).

## 1. Start (one PI prompt)

The PI gives a scope in prose, maybe a deadline and a lab location in words. Ask nothing that
a file or a probe answers. The code repo is the current directory unless the PI names one. Then, in order:

1. **Profile.** Read `~/.config/research-lab/pi-profile.md` (including its Resources
   section: known data paths and environment facts - use them before searching) (template: `pi-profile.example.md`
   here). Missing: copy the example, then send the PI one message listing only the lines you
   could not fill. Its `LAUNCHER:` line is the only way members are launched.
2. **Probe.** `date`, `nvidia-smi` (free GPUs), `df -h` on the work dirs, `printenv
   COMMIT_AUTHORISED PUSH_AUTHORISED`, the code repo and branch. A code repo needs a
   worktree: `wt switch -c hayden/lab-<slug> --no-cd`.
3. **Lab dir.** The location the PI names is the lab dir itself (no extra level); default
   `<code repo>/.agents/work/<date>-lab-<slug>/`.
   Lab id = `<slug>` (short, kebab). Create:
   - `policy.md` from `templates/policy.md`: profile rules + probe results + this lab's
     deltas (deadline, GPU set, caps). Deadline absent = none.
   - `status.md`: line 1 = one-line state for the PI. Then the milestone table (D32):
     `| by | milestone | state |`, back-planned from the deadline, and the experiment table
     `| id | question | tier | state | budget | eta |` with state one of `[ ]` briefed,
     `[-]` running, `[?]` in audit, `[R]` revising, `[x]` decided, `[S]` cut.
   - `questions.md` from `templates/questions.md`: turn the scope into questions (why it
     matters, cost, status).
   - `false-findings.md`: table of failure patterns (pattern, how detected, domain),
     seeded from the domain pack checklist; members append every new pattern they hit.
   - `decisions.md` (D entries; agent-picked marked), `audit/log.md` from
     `templates/audit-log.md`, `experiments/`, `friction.md` when the PI asked for one.
   - Domain pack: if `packs/<domain>/` exists here, point briefs at it; else write
     `<lab>/packs/<domain>/checklist.md` (failure checklist for this domain).
4. **Mesh.** `mailbox` skill: init `<lab>/mailbox`, join as `<id>-overseer`. All member names
   are prefixed `<id>-` (herdr agent names are global across labs).
5. **Staff** (D3, D13). Long-lived members on the mesh, each in its own herdr tab:
   write the connect prompt to a file, then
   `scripts/spawn-member.sh <id>-worker <cwd> <prompt-file>` (prints the pane id).
   Connect prompt: the mailbox template + `Load the orchestrator skill: you own all
   execution.` + `Read <lab>/policy.md; launch nothing except the LAUNCHER in
   ~/.config/research-lab/pi-profile.md. Before the first expensive run, stub-verify timing
   and counting code on a cheap input where the counters provably move.` Default staff: one worker per independent
   question stream; one author when there is a page to write. Critics and literature spikes
   are fresh subagents launched by the owner from templates (D17), not members.
   One-off sessions (a fix, a spike outside the mesh) get a brief that ends with a
   ring-back: `herdr agent prompt <your pane> "done: <report path>"`.
   **Teardown as soon as a member's work is accepted**, not only at lab end: `herdr tab
   close <tab>`, and `wt remove --foreground <branch>` for its merged worktree.
6. **Heartbeat** (D9, D32). Session cron, period at most a sixth of the time box (5 min
   floor, 30 min cap) while active: mail, member states, GPUs,
   ledgers, clock vs milestones and ETAs; each beat runs `scripts/lab_lint.py <lab dir>`
   (projected timestamps, status.md shape, audit event vocabulary). Ends itself at the
   lab's end condition.
7. Tell the PI one line: lab dir, members, deadline, first briefs. Then work.

## 1b. Resume (new overseer session, existing lab)

The PI says "resume the lab in <place>". Files are the memory (D11): read `status.md`,
`decisions.md`, `questions.md`, `audit/log.md`, the experiment files and the mailbox
`members/` and `log.jsonl`. Then: re-join the mesh under the overseer's existing member name
(the old seat is stale, join takes it over); `mailbox take`; for each member check its pane
is alive (`herdr agent get <pane>`) and ring it with what you expect next, re-spawn the dead
ones from their connect-prompt files; recreate the heartbeat and list the session's cron jobs to confirm it is live; print `date` and replan
against the milestones. Tell the PI one line: what state you found and what is next.

## 2. Run

Lifecycle per experiment (D5): question -> brief (pre-registered, `templates/experiment.md`:
hypothesis, falsifier, headline/supporting tier, wall-clock budget, cut rule) -> design review
for expensive runs (`templates/critic-design-review.md`) -> run -> entry + manifest
(`templates/manifest.md`, worker-written) -> deterministic checks -> result audit
(`templates/critic-result-audit.md`) -> decision (D entry) -> provenance commit -> publish to
the page. One file per experiment: `experiments/<eid>.md`.

- Briefs are one coherent instruction with paths, constraints, budget, cut rule and what to
  report. Member replies are data: check them against files.
- Every gate, catch, critic error, cut and closed budget gets one `audit/log.md` line with
  a fixed event name and the failure text (template). The worker runs
  `scripts/lab_checker.py` on every entry write, before reporting; the critic never sees an
  entry that fails it.
- Revision cap: two owner-critic rounds per finding; then the overseer rules against the
  data and logs a `RULING`.
- Clock (D32): every timestamp in a lab file comes from `date` at the moment of writing,
  never estimated or projected; ETAs are labelled `eta`. A heartbeat starts by printing
  `date`. Heartbeat period at most one sixth of the time box (5 min floor), not a fixed 30.
- Blockers ring: a member that is blocked sends with a ring, never `--no-ring`; FYI is for
  non-blocking notes only.
- Time (D32): at 1.5x a brief's budget or a slipped milestone, cut scope and record a D.
  Only moving the deadline goes to the PI. Cut order: unstarted non-headline experiments,
  then optional arms/sweeps, then headline depth; never controls, pre-registration or
  audits - shrink the claim instead.
- Parallel across questions, serial refinement within one (D26).
- Critic concurrency: at most two critic subagents at once per lab when the profile's
  Resources say the model backend is a single shared replica; queue the rest.
- Ideas cite their trigger; novelty claims need a literature spike (D27).

## 3. PI interface (D16, D33)

The PI talks to you in this pane, in prose; the PI is never a mesh member. Never ask the
PI for paths or commands: derive them. Interrupts and the final report are messages in this
pane (and `herdr notification` if the PI may not be watching).

Message the PI only for: scope changes, reversing a PI decision, irreversible or outward
actions, spend above policy, dead ends, and the final report. Everything else: decide, record
an agent-picked D, continue. The PI never writes lab files; questions they give in prose,
you file. Keep `status.md` line 1 current.

The interrupt list limits what *you* start, not how you talk when the PI does. When the PI
chats, think with them as a colleague (D6): which questions are worth answering is worked
out together and keeps changing as results come in. `questions.md` is that shared agenda;
reshape it as the conversation goes. Disagree when the evidence says the PI is wrong. Land
what the conversation settles in files the same turn (D, question row, brief).

## 4. Finish

After the report, one reflective pass (D35): read `audit/log.md` (CATCH, CRITIC_ERR, RULING
lines) and `friction.md`, and propose edits to the templates and pack checklists as a short
file `<lab>/template-proposals.md` for the PI's design owner. Do not edit shared templates
from inside a lab.

End condition = deadline, or every headline question answered/dropped. Then (rewrite
`status.md` line 1 last, so it states the final state): page audited
with `templates/critic-page-audit.md`, all lab files and code committed (gated), member tabs
closed and their worktrees removed, heartbeat deleted, one report to the PI: page path, findings by claim state,
open questions, measures (PI messages received, interrupts, wall clock, budget vs actual).

Append to the PI profile's Resources section every environment fact the lab verified (data
paths, recipes, quirks), with how it was verified. Claims about the environment ("X is not
available") are claims: they list what was searched.
