"""lab-worktree.sh: the lab's code worktree created/reused, setup run, all recorded.

The worktree comes from the wt shim (`switch` records to $SHIM_LOG and creates a
marker dir under $WT_SWITCH_DIR): branch = <BRANCH_PREFIX>lab-<slug> from the PI
profile, existing branches reused. Setup order: repo wt project hooks (wt switch
already ran them), --setup, the profile's `Setup <repo-name>` Resources line. The
Code repo / Branch lines land in policy.md in lab_heartbeat.py's parse format.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from lab_heartbeat import _BRANCH_RE, _REPO_RE

SCRIPT = Path(__file__).with_name("lab-worktree.sh")


def write_profile(tmp_path: Path, *, prefix: str = "hayden/", resources: str = "") -> Path:
    """A PI profile with a branch prefix and a Resources section (template shape)."""
    p = tmp_path / "profile.md"
    p.write_text(
        "# PI profile\n\n"
        f"TRUSTED_ROOTS: {tmp_path}\n"
        f"BRANCH_PREFIX: {prefix}\n"
        "\n## Resources (cross-lab facts)\n\n"
        f"{resources}\n"
    )
    return p


@pytest.fixture()
def f(tmp_path: Path, shims) -> SimpleNamespace:
    """A repo (no hooks, no docs), a profile with a branch prefix, an empty lab dir."""
    repo = tmp_path / "repo"
    repo.mkdir()
    profile = write_profile(tmp_path)
    lab = tmp_path / "lab"
    lab.mkdir()
    return SimpleNamespace(
        repo=repo, profile=profile, lab=lab,
        env={"RESEARCH_LAB_PROFILE": str(profile)},
    )


def worktree_of(shims, branch: str) -> Path:
    return shims.wt_switch / branch.replace("/", "-")


def run(f, shims, *extra: str):
    return shims.run(SCRIPT, [str(f.lab), str(f.repo), "kern"] + list(extra),
                     **f.env)


def test_new_worktree_with_setup_arg(f, shims):
    result = run(f, shims, "--setup", "echo ran > setup-ran.txt")

    assert result.returncode == 0, result.stderr
    wt = worktree_of(shims, "hayden/lab-kern")
    # stdout is exactly the worktree path; everything else went to stderr
    assert result.stdout == f"{wt}\n"
    assert wt.is_dir()
    assert (wt / "setup-ran.txt").read_text() == "ran\n", "setup ran in the worktree"
    assert f"wt -C {f.repo} switch -c hayden/lab-kern --no-cd --format json" in shims.log.read_text()
    # recorded in policy.md, in lab_heartbeat.py's parse format
    policy = (f.lab / "policy.md").read_text()
    assert f"Code repo: {f.repo}" in policy
    assert "Branch: hayden/lab-kern" in policy
    assert f"Worktree: {wt}" in policy
    assert "Setup: echo ran > setup-ran.txt" in policy
    assert _REPO_RE.search(policy).group(1) == str(f.repo)
    assert _BRANCH_RE.search(policy).group(1) == "hayden/lab-kern"


def test_existing_branch_reused(f, shims):
    first = run(f, shims, "--setup", "true")
    assert first.returncode == 0, first.stderr

    second = run(f, shims, "--setup", "true")

    assert second.returncode == 0, second.stderr
    assert second.stdout == first.stdout
    assert "already has a worktree; reusing" in second.stderr
    log = shims.log.read_text()
    # the second call switched to the existing branch without -c
    assert f"wt -C {f.repo} switch hayden/lab-kern --no-cd --format json" in log


def test_repo_hooks_beat_setup_arg(f, shims):
    (f.repo / ".config").mkdir()
    (f.repo / ".config" / "wt.toml").write_text(
        '[post-start]\ninstall = "npm ci"\n')

    result = run(f, shims, "--setup", "echo should-not-run > nope.txt")

    assert result.returncode == 0, result.stderr
    assert (f.lab / "policy.md").read_text().count("Setup: repo wt hooks") == 1
    assert not (worktree_of(shims, "hayden/lab-kern") / "nope.txt").exists(), \
        "repo hooks already ran the setup; the script must not run it again"


def test_hooks_table_and_pipeline_forms_count(f, shims):
    for toml in ('pre-start = "npm install"\n',
                 '[[post-start]]\ninstall = "npm ci"\n'):
        (f.repo / ".config").mkdir(exist_ok=True)
        (f.repo / ".config" / "wt.toml").write_text(toml)
        result = run(f, shims)
        assert result.returncode == 0, result.stderr
        assert "Setup: repo wt hooks" in (f.lab / "policy.md").read_text()


def test_missing_setup_source_names_all_three(f, shims):
    result = run(f, shims)

    assert result.returncode == 1
    err = result.stderr
    assert "no setup source" in err
    for source in ("worktrunk project hooks", "--setup", "- Setup repo:"):
        assert source in err, f"error must name the source: {source}"
    assert not (f.lab / "policy.md").exists(), "nothing recorded when setup is unresolved"


def test_failing_setup_fails_loud(f, shims):
    result = run(f, shims, "--setup", "echo boom; exit 3")

    assert result.returncode == 1
    assert "setup command failed (exit 3)" in result.stderr
    assert "boom" in result.stderr, "the tail of the setup output is reported"
    assert not (f.lab / "policy.md").exists(), "a failed setup records nothing"


def test_policy_lines_replaced_in_place(f, shims):
    (f.lab / "policy.md").write_text(
        "# Lab policy\n\n"
        "## Permissions\n\n"
        "- Code repo: /old/repo\n"
        "- Branch: old-lab\n"
        "- Worktree: /old/wt\n"
        "- Setup: old-cmd\n"
        "\n## People\n")
    wt = worktree_of(shims, "hayden/lab-kern")

    result = run(f, shims, "--setup", "true")

    assert result.returncode == 0, result.stderr
    policy = (f.lab / "policy.md").read_text()
    assert policy == (
        "# Lab policy\n\n"
        "## Permissions\n\n"
        f"Code repo: {f.repo}\n"
        "Branch: hayden/lab-kern\n"
        f"Worktree: {wt}\n"
        "Setup: true\n"
        "\n## People\n")


def test_profile_resources_append(f, shims):
    result = run(f, shims, "--setup", "echo ok")

    assert result.returncode == 0, result.stderr
    today = datetime.date.today().isoformat()
    text = f.profile.read_text()
    line = f"- Setup repo: echo ok (verified: lab kern, {today})"
    assert line in text
    assert text.index("## Resources") < text.index(line), "appended under Resources"


def test_profile_setup_line_used_and_not_duplicated(f, shims):
    f.profile.write_text(f.profile.read_text().replace(
        "## Resources (cross-lab facts)\n",
        "## Resources (cross-lab facts)\n\n"
        "- Setup repo: touch built.txt (verified: lab other, 2026-01-01)\n"))

    result = run(f, shims)

    assert result.returncode == 0, result.stderr
    wt = worktree_of(shims, "hayden/lab-kern")
    assert (wt / "built.txt").exists(), "the profile setup command ran in the worktree"
    assert "Setup: touch built.txt" in (f.lab / "policy.md").read_text(), \
        "the (verified: ...) suffix is stripped before the command is recorded"
    text = f.profile.read_text()
    assert text.count("- Setup repo:") == 1, "an existing profile entry is not re-appended"


def test_missing_branch_prefix_fails(f, shims):
    (f.profile).write_text("# PI profile\n\n## Resources (cross-lab facts)\n")

    result = run(f, shims, "--setup", "true")

    assert result.returncode == 1
    assert "BRANCH_PREFIX" in result.stderr
    assert not shims.log.exists() or "wt switch" not in shims.log.read_text(), \
        "no worktree without a prefix"


def test_branch_prefix_slash_normalised(tmp_path, shims):
    repo = tmp_path / "repo"
    repo.mkdir()
    profile = write_profile(tmp_path, prefix="someone/")
    lab = tmp_path / "lab"
    lab.mkdir()

    result = shims.run(SCRIPT, [str(lab), str(repo), "kern", "--setup", "true"],
                       RESEARCH_LAB_PROFILE=str(profile))

    assert result.returncode == 0, result.stderr
    assert "Branch: someone/lab-kern" in (lab / "policy.md").read_text()
