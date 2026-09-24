"""Build AGENTS.md from CLAUDE.md (rewriting @skills/<n> refs)."""

import re
from pathlib import Path

from settings_sync.ownership import sync_generated_file

from settings_sync.sync import Outcome, Status

SKILLS_REF = re.compile(r"@skills/([a-zA-Z0-9_-]+)")


def _rewrite_skills_refs(markdown: str) -> str:
    return SKILLS_REF.sub(r"the `\1` skill", markdown)


def build_agents_md(claude_md: Path, rules_path: Path | None = None, *, source_root: Path | None = None, harness: str = "") -> str:
    markdown = claude_md.read_text()
    if harness != "claude":
        markdown = _rewrite_skills_refs(markdown)
    if rules_path is not None and rules_path.is_file():
        markdown = markdown.rstrip() + "\n\n" + rules_path.read_text()
    if source_root is not None:
        preamble = (
            f"# Shared agent configuration\n\nSource checkout: `{source_root.resolve()}`.\n"
            "Edit shared rules in `rules/global.md`, skills in `skills/`, commands in `commands/`, "
            f"and harness settings in `harnesses/{'gemini' if harness == 'agy' else harness}/`.\n"
            f"Apply shared edits with `agent-config sync {harness}`. Runtime instructions and managed config values are generated.\n"
            "Keep machine-only settings in native local state or the documented agent-config overlays.\n\n"
        )
        markdown = preamble + markdown
    return markdown


def sync_agents_md(
    target: Path,
    claude_md: Path,
    force: bool = False,
    dry_run: bool = False,
    rules_path: Path | None = None,
    *, source_root: Path | None = None, harness: str = "opencode",
) -> Outcome:
    if not claude_md.is_file():
        return Outcome(target, Status.NO_SOURCE, f"CLAUDE.md not found: {claude_md}")
    content = build_agents_md(claude_md, rules_path=rules_path, source_root=source_root, harness=harness)
    return sync_generated_file(target, content, force=force, dry_run=dry_run)
