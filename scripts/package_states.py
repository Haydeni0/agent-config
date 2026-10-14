"""Single source for package state enums and contract filenames.

Consumed by scripts/check-packages.py (lint) and scripts/check-skills.py
(exits: validation); settings-sync tests assert the work-package SKILL.md
enum line equals ALL_STATES."""

DEV_CYCLE_STATES = {
    "grill", "test-plan", "spec", "plan", "implement",
    "code-review", "verify-fix", "complete",
}
DEBUG_STATES = {
    "root-cause", "pattern-analysis", "hypothesis", "implementation", "resolved",
}
ALL_STATES = DEV_CYCLE_STATES | DEBUG_STATES
CONTRACT_FILES = (
    "context.md", "scenarios.md", "requirements.md", "decisions.md", "spec.md", "plan.md",
)
