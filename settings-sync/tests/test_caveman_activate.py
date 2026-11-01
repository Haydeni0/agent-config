"""Seam B: the caveman SessionStart script against a controlled checkout copy."""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = "harnesses/claude/hooks/caveman-activate.sh"


def checkout_with_skill(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    (root / "harnesses/claude/hooks").mkdir(parents=True)
    shutil.copyfile(REPO / SCRIPT, root / SCRIPT)
    skill = root / "vendor/plugins/caveman/skills/caveman/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: caveman\ndescription: terse output\n---\n# Rules\n\nBe terse.\n")
    return root


def run_script(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(root / SCRIPT)], capture_output=True, text=True)


def test_emits_ruleset_stripping_frontmatter(tmp_path: Path, isolated_home: Path):
    """S11: repo-relative resolution lands on the vendored skill and strips its frontmatter."""
    result = run_script(checkout_with_skill(tmp_path))
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "# Rules\n\nBe terse.\n"


def test_writes_no_flag_file(tmp_path: Path, isolated_home: Path):
    """S12: the retired .caveman-active flag stays unwritten, under HOME and the checkout."""
    root = checkout_with_skill(tmp_path)
    run_script(root)
    run_script(root)
    assert not list(isolated_home.rglob(".caveman-active"))
    assert not list(root.rglob(".caveman-active"))


def test_missing_skill_messages_on_stderr_and_exits_zero(tmp_path: Path, isolated_home: Path):
    """S13: a missing submodule emits the fix on stderr and never blocks session start."""
    root = tmp_path / "checkout"
    (root / "harnesses/claude/hooks").mkdir(parents=True)
    shutil.copyfile(REPO / SCRIPT, root / SCRIPT)
    result = run_script(root)
    assert (result.returncode, result.stdout) == (0, "")
    assert "vendor/plugins/caveman/skills/caveman/SKILL.md" in result.stderr
    assert "git submodule update --init --recursive" in result.stderr
