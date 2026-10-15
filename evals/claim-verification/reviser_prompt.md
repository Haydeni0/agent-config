# Revise the claim-verification skill

You are revising one skill file, `SKILL.md` for `claim-verification`. An agent loads this skill before it sends any message that asserts facts about code, environment or work state, and it should check each claim against fresh evidence before sending.

Below the current file are transcripts of runs where an agent with this skill available still sent a false claim, or produced no usable answer. Read each transcript and work out why the skill did not stop it:
- it never invoked the skill;
- it invoked the skill but skipped a step;
- or it followed the skill and the skill did not cover the case.

Revise the skill to fix the general failure, not the specific example. These runs are a small sample from an open-ended stream of future tasks. A rule that only matches these files, values, names or phrasings is worthless, and so is any mention of them.

- Prefer explaining why a step matters over adding MUST or NEVER. The agent reading the skill is capable, and understanding beats rote rules.
- Keep it lean: remove text that is not pulling its weight. The revised file may be at most 25% longer than the current one.
- Do not change the frontmatter `name`, `layer` or `deps`. Keep the sentence beginning "Never shell out to" verbatim.
- Match the current file's prose style: full sentences, no em dashes.

Output: one short paragraph explaining the change and why it generalises, then the complete revised file inside a ````markdown fence. Output nothing else.
