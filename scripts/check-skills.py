"""Static checker for the skills/ suite - the REQ-SKILLS verification.

Enforces the skill-suite contract without hardcoded skill lists: the layering
rules read each skill's self-declared `layer:` frontmatter field, and a skill
without the field is unconstrained. New skills maintain themselves by declaring
their layer where the knowledge lives - their own frontmatter.

Checks (all map to a REQ-SKILLS row in docs/requirements.md):
- frontmatter: parses as YAML, `name` equals the directory name, matches
  ``^[a-z0-9]+(-[a-z0-9]+)*$``, and carries a non-empty `description`
- flat namespace: every SKILL.md sits at ``skills/<name>/SKILL.md``; anything
  deeper is reported as nested (traversal does not follow symlinks, so upstream
  submodule content is out of scope)
- one-way layering: no `layer: worker` skill names a `layer: orchestrator` skill
- peer rule: design-log and dev-cycle never name each other
- deps validation: every `deps:` entry names an existing skill, never self,
  and a `layer: worker` skill never declares a `layer: orchestrator` skill
- workers never reference the design-package contract except through the
  plan-package skill: the bare word "package" (not hyphen-joined, so
  "plan-package" passes; file names like package.json excluded) is banned in
  worker bodies except in plan-package itself
- every top-level symlink under skills/ resolves (vendored skills link into
  submodules; a dangling link means the submodule is missing or moved)
- cross-skill path references (``../``-prefixed or ``<skill-name>/``-prefixed,
  with a code/doc extension) resolve, relative to the skill or the repo root

A skill that fails to parse is reported once and skipped by the later checks;
every other violation is printed. Exits nonzero if any violation was found.
"""

import re
import sys
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PACKAGE_RE = re.compile(r"(?<!-)\bpackage\b(?!\.[A-Za-z])")
ORCHESTRATOR_PEERS = ("design-log", "dev-cycle")
CONTRACT_OWNER = "plan-package"
# Skill names that are also generic English words: a bare word-boundary match
# would fire on prose ("orchestrator mode"), so these need a skill-like
# reference (backticked, slash-command form, or "<name> skill").
GENERIC_WORD_NAMES = {"orchestrator"}
PATH_TOKEN_RE = re.compile(r"`([A-Za-z0-9_./-]+/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`")
EXT_RE = re.compile(r"\.(md|py|js|mjs|ts|json|sh|toml|yaml|yml)$")


def parse_skill(skill_md: Path) -> tuple[dict, str]:
    text = skill_md.read_text()
    if not text.startswith("---"):
        raise ValueError("missing frontmatter")
    end = text.index("\n---", 3)
    frontmatter = yaml.safe_load(text[4:end])
    if not isinstance(frontmatter, dict):
        raise ValueError("frontmatter is not a mapping")
    return frontmatter, text[end + 4 :]


def orchestrator_reference(orch: str, body: str) -> bool:
    if orch in GENERIC_WORD_NAMES:
        return bool(re.search(rf"`{re.escape(orch)}`|/{re.escape(orch)}\b|{re.escape(orch)} skill", body))
    return bool(re.search(rf"\b{re.escape(orch)}\b", body))


def check(skills_dir: Path, repo_root: Path) -> tuple[list[str], int]:
    failures = []
    root = set(skills_dir.glob("*/SKILL.md"))
    for nested in sorted(set(skills_dir.glob("*/**/SKILL.md")) - root):
        failures.append(f"nested SKILL.md at {nested.relative_to(repo_root)}")

    parsed: dict[str, tuple[dict, str]] = {}
    for skill_md in sorted(root):
        name = skill_md.parent.name
        try:
            frontmatter, body = parse_skill(skill_md)
        except (ValueError, yaml.YAMLError) as exc:
            failures.append(f"{name}: unparseable SKILL.md: {exc}")
            continue
        parsed[name] = (frontmatter, body)
        if frontmatter.get("name") != name:
            failures.append(f"{name}: frontmatter name {frontmatter.get('name')!r} != dir name")
        if not NAME_RE.match(str(frontmatter.get("name", ""))):
            failures.append(f"{name}: name does not match {NAME_RE.pattern}")
        if not str(frontmatter.get("description", "")).strip():
            failures.append(f"{name}: empty or missing description")

    orchestrators = {
        name for name, (frontmatter, _) in parsed.items() if frontmatter.get("layer") == "orchestrator"
    }
    for name, (frontmatter, body) in parsed.items():
        if frontmatter.get("layer") != "worker":
            continue
        for orch in sorted(orchestrators):
            if orchestrator_reference(orch, body):
                failures.append(f"{name}: worker names orchestrator skill {orch}")
        if name != CONTRACT_OWNER and PACKAGE_RE.search(body):
            failures.append(f"{name}: worker references the design-package contract")

    for name, (frontmatter, _) in parsed.items():
        deps = frontmatter.get("deps") or []
        if not isinstance(deps, list):
            failures.append(f"{name}: deps is not a list")
            deps = []
        for dep in deps:
            if not isinstance(dep, str):
                # unhashable entries (nested list/mapping) would crash the
                # membership tests below - report them instead
                failures.append(f"{name}: deps entry {dep!r} is not a skill name")
            elif dep == name:
                failures.append(f"{name}: deps self-reference {dep!r}")
            elif dep not in parsed:
                failures.append(f"{name}: deps entry {dep!r} names no skill")
            elif frontmatter.get("layer") == "worker" and parsed[dep][0].get("layer") == "orchestrator":
                failures.append(f"{name}: worker declares orchestrator-layer dep {dep!r}")

    for peer in ORCHESTRATOR_PEERS:
        if peer not in parsed:
            continue
        for other in ORCHESTRATOR_PEERS:
            if other != peer and orchestrator_reference(other, parsed[peer][1]):
                failures.append(f"{peer}: names peer orchestrator {other}")

    for link in sorted(skills_dir.glob("*")):
        if link.is_symlink() and not link.exists():
            failures.append(f"{link.name}: dangling symlink ({link.readlink()})")

    for name, (_, body) in parsed.items():
        for token in PATH_TOKEN_RE.findall(body):
            cross_skill = token.startswith("../") or token.split("/")[0] in parsed
            if not cross_skill or not EXT_RE.search(token):
                continue
            candidates = [skills_dir / name / token, skills_dir / token, repo_root / token]
            if not any(c.exists() for c in candidates):
                failures.append(f"{name}: referenced path does not resolve: {token}")

    return failures, len(root)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    skills_dir = repo_root / "skills"
    failures, count = check(skills_dir, repo_root)
    for failure in failures:
        print(f"check-skills: {failure}")
    print(f"check-skills: {count} skills checked, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
