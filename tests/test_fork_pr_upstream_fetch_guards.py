"""Repo-level guard: fork-PR path filters fetch the base ref from UPSTREAM.

`.github/workflows/{ci,conventions,e2e-smoke}.yml` each detect a PR's changed
files by diffing against the base branch. They must fetch that base ref from
the UPSTREAM repo, not from `origin`: on a fork PR the `origin` remote is the
contributor's fork, so `git fetch origin "$BASE_REF"` pulls the fork's stale
base and the `origin/<base>...HEAD` diff misclassifies the PR -- skipping
required checks or running the wrong lanes (#299).

`$GITHUB_REPOSITORY` always names the base repo for `pull_request` events, so
the fix resolves the upstream URL from it and diffs against `FETCH_HEAD`.
These tests pin that fix so it cannot silently regress. This repo has no local
GitHub Actions runner, so they assert the YAML text like the sibling workflow
guards in `tests/test_conventions_workflow_guards.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# (workflow file, name of the step that builds `changed.txt`). Every entry is a
# fork-PR-reachable `pull_request` path filter -- integration.yml's `git fetch
# origin` is deliberately excluded: it runs only on push-to-main/cron, where
# `origin` already is the upstream repo (#299).
CHANGED_FILE_STEPS = [
    (".github/workflows/ci.yml", "Detect changed files"),
    (".github/workflows/conventions.yml", "Collect changed files"),
    (".github/workflows/e2e-smoke.yml", "Detect changed files"),
]


def _step_commands(workflow: str, step_name: str) -> str:
    """Return the executable commands of the named step's `run: |` block.

    Full-line `#` comments and blank lines are dropped so the guard asserts on
    the shell the runner actually executes, not on explanatory prose (the fix's
    comment necessarily mentions the old `origin/$BASE_REF` pattern it removes).
    The block ends at the first non-blank line indented no deeper than the
    step's `run:` content (10 spaces), i.e. the next step or job key.
    """
    text = (REPO_ROOT / workflow).read_text()
    idx = text.index(f"- name: {step_name}")
    run_idx = text.index("run: |", idx)
    body = text[run_idx + len("run: |") :].lstrip("\n")

    lines: list[str] = []
    for line in body.splitlines():
        if line.strip() and not line.startswith("          "):
            break
        if line.strip() and not line.lstrip().startswith("#"):
            lines.append(line)
    commands = "\n".join(lines)
    assert commands.strip(), f"{workflow}: step {step_name!r} has an empty `run:` block"
    return commands


@pytest.mark.parametrize("workflow, step_name", CHANGED_FILE_STEPS)
def test_changed_files_fetch_base_from_upstream_not_origin(workflow: str, step_name: str) -> None:
    commands = _step_commands(workflow, step_name)

    assert "git fetch origin" not in commands, (
        f"{workflow}: the changed-files step must not `git fetch origin` -- on a "
        "fork PR `origin` is the contributor's fork, not the upstream base repo "
        "(#299)"
    )
    assert "origin/$BASE_REF" not in commands, (
        f"{workflow}: the diff must not reference `origin/$BASE_REF`; compare "
        "against `FETCH_HEAD` fetched from the upstream repo instead (#299)"
    )
    assert "$GITHUB_REPOSITORY" in commands, (
        f"{workflow}: resolve the upstream repo via `$GITHUB_REPOSITORY`, which "
        "names the base repo on `pull_request` events (#299)"
    )
    assert "FETCH_HEAD" in commands, (
        f"{workflow}: diff `HEAD` against the freshly fetched `FETCH_HEAD` (#299)"
    )
