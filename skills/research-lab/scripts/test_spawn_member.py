import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("spawn-member.sh")

PROFILE = """# PI profile

## Staffing

| role | launcher | model | effort |
|---|---|---|---|
| default | ~/bin/agent | small | medium |
| author | claude | opus | |
| worker | | | high |

## Resources
| default | wrong | wrong | wrong |
"""


def resolve(profile: Path, role: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), "--resolve", role],
        env={**os.environ, "RESEARCH_LAB_PROFILE": str(profile)},
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("role", "command"),
    [
        ("author", "claude --model opus --effort medium"),
        ("worker", "~/bin/agent --model small --effort high"),
        ("critic", "~/bin/agent --model small --effort medium"),
    ],
)
def test_resolve(tmp_path, role, command):
    profile = tmp_path / "profile.md"
    profile.write_text(PROFILE)

    assert resolve(profile, role).stdout.strip() == command


def test_resolve_rejects_placeholder(tmp_path):
    profile = tmp_path / "profile.md"
    profile.write_text("## Staffing\n\n| role | launcher | model | effort |\n|---|---|---|---|\n"
                       "| default | <command> | | |\n")

    result = resolve(profile, "worker")

    assert result.returncode == 1
    assert "no launcher" in result.stderr
