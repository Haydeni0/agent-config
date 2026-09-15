---
name: explain-diff
description: Use when the user asks for a rich explanation of a code change, diff, branch, or PR. Produces HTML output (or a Notion page when the user asks for Notion).
---

# Explain Diff

Please make me a rich, interactive explanation of the specified code change.

It should have these sections:

- Background: Explain the existing system relevant to this change. (You should broadly explore surrounding code for this.) We don't know how much the reader already knows, so include a deep background for beginners (note that it can be skipped if the reader is already familiar), and then a more narrow background directly relevant to the change.
- Intuition: Explain the core intuition for the code change. The focus here is to explain the essence, not the full details. Use concrete examples with toy data. Use figures and diagrams liberally.
- Code: Do a high-level walkthrough of the changes to the code. Group/order the changes in an understandable way.
- Quiz: Come up with five questions that test the reader's knowledge of this PR. This should be medium difficulty, difficult enough that you actually need to understand the substance of the PR to answer them, but not gotchas. The goal is to help the reader make sure they've actually understood. These should be presented as interactive multiple-choice questions, and when the user clicks, it tells them whether they were correct and gives feedback.

## Output format

Default is HTML. If the user asks for a Notion page instead, follow the Notion variant below.

### HTML

- **Use `~/.claude/skills/explain-diff/render.py` instead of hand-writing HTML.**
  Repeated invocations of this command tend to regenerate near-identical CSS/JS boilerplate
  every time, which wastes tokens and drifts in quality — factor that out once. Write a small
  JSON content spec (title, subtitle, slug, sections with raw HTML bodies, quiz questions with
  correct/incorrect options) and run:
  ```
  python3 ~/.claude/skills/explain-diff/render.py <spec.json>
  ```
  This handles all CSS, JavaScript, page scaffolding, table of contents, quiz-option
  randomization, and the date-prefixed global filename automatically — only write the
  content spec, not the full HTML page. Run `python3 ~/.claude/skills/explain-diff/render.py --help` for the exact JSON
  schema if you haven't used it recently.
- Section `html` fields in the spec are raw HTML you write directly — use `<pre>` for
  code blocks (already `white-space: pre-wrap` styled by the renderer), `.diagram`/
  `.flow`/`.box`/`.box.fail` divs for flow diagrams, `.callout` for key definitions/
  edge cases, and plain `<table>` for comparison tables. See the renderer's docstring
  for the exact class names available.

### Notion

- Use the Notion MCP tools to create a new page and return the URL of the new page.
- The quiz is built from toggle blocks, each option revealing an explanation of why it
  was correct or incorrect. For example:
  ```markdown
  1. Question
     ▶ Option 1
      ❌ Explanation for why it was incorrect
     ▶ Option 2
      ✅ Explanation for why it was correct
     ▶ Option 3
      ❌ Explanation for why it was incorrect
  2. Question
     ...
  ```
- Use callouts for key concepts or definitions, important edge cases, etc.

## Writing style

- Please write with the clarity and flow of Martin Kleppmann, making it engaging and
  written in classic style. Transitions between sections should be smooth.
- Some tips on diagrams. Ideally, pick a small number of diagram families that can be
  reused throughout the explanation to explain various cases. Make sure to include
  example data! Some useful kinds:
  - A very simplified version of the UI the user sees in the app, to explain UI changes.
  - A system diagram showing data flow or communication between components, with
    example data included.
- Don't use ASCII diagrams — in HTML use the renderer's diagram classes; in Notion use
  embedded content blocks.
