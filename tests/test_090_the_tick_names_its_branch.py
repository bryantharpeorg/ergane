"""090-US3: the tick's own record says which branch it used and who named it.

US1 made the refresh read `resolve_landing_base`, so the branch is now the
declaration's rather than the operator's HEAD. That resolver deliberately
*fails open* (107, trap 4): a clone with no readable manifest still gets a
branch, taken from whatever HEAD has checked out. Which means the branch name
alone answers nothing an operator needs — `dev` looks exactly the same whether
the manifest declared it or the refresh guessed it off a checkout, and on the
wrong clone the guess *is* the defect this spec exists to prevent.

So the record has to carry the arm, and when the arm is the fallback it has to
carry the reason. `LandingBase` already holds both — `.source` as the
machine-readable arm, `.detail` as the loader's own complaint — and the refresh
already holds a `LandingBase`. This story stops throwing them away.

The properties defended here:

- **S1 / FR-006**: a clone whose manifest declares the branch produces a result
  whose arm is `LANDING_BASE_MANIFEST` — a distinguishable value, not merely the
  branch name — and whose detail names the manifest that declared it.
- **S2 / FR-006**: a clone with no manifest records `LANDING_BASE_HEAD` *and*
  the loader's own complaint, verbatim, so an operator reading the record learns
  why the guess was made rather than only that a branch came back. The complaint
  is compared against `resolve_landing_base`'s own, because a phrase the
  activity invented for itself would drift from the one arm that knows what went
  wrong.
- The log line T021 asks for: the base, the repository it was read from and the
  arm, the shape `_log_landing_base` (`factory/activities/merge_activities.py`)
  uses one activity over. A field on a dataclass that no operator ever sees is
  half the story; the 6h34m outage this spec exists to prevent was extended by
  the absence of exactly this line in the worker log.

S3 — that the park reason US2's refusal produces names the branch, the paths at
risk and the clearing act — lives in `tests/test_roadmap_scheduler.py`, where the
workflow harness is. The division US2 drew holds: reset semantics need real git,
what the workflow does with a result needs none.

Real repositories under `tmp_path` with a local bare `origin` (trap 6), driving
`_refresh_to_default` directly.

Written test-first: against the pre-US3 code every assertion touching
`default_detail` fails, because the refresh reads `LandingBase.detail` and drops
it, and no log line is emitted at all.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from factory.activities.roadmap_activities import _refresh_to_default
from factory.verify.factory_yaml import MANIFEST_NAME
from factory.workgraph import worktree as worktrees

from tests.target_repo import git

#: The branch the manifest declares. Not `main`, so a result that carried a
#: default rather than the declaration fails loudly rather than by coincidence.
DECLARED = "dev"

_MANIFEST = """\
version: 1
runtime: bwrap
gates:
  test: "uv run pytest -q"
landing_branch: dev
"""


def _seed(clone: Path, origin: Path, branch: str) -> None:
    """Commit whatever is in `clone` and push it, so `origin/<branch>` exists."""
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "the repository as the roadmap finds it")
    git(clone, "push", "--quiet", "origin", branch)
    git(clone, "fetch", "--quiet", "origin")


@pytest.fixture
def declared_clone(tmp_path: Path) -> Path:
    """A clean clone on `dev`, whose manifest declares `dev` (S1).

    Clean and already on the declared branch, because S1 is about what the
    *successful* refresh records: the refusal path is US2's and has its own
    file.
    """
    origin = tmp_path / "origin.git"
    git(origin.parent, "init", "--bare", "-b", DECLARED, str(origin))
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    (clone / MANIFEST_NAME).write_text(_MANIFEST, encoding="utf-8")
    _seed(clone, origin, DECLARED)
    return clone


@pytest.fixture
def undeclared_clone(tmp_path: Path) -> Path:
    """A clone with no manifest at all, standing on `main` (S2).

    The fallback's own condition: nothing declares a landing branch, so
    `resolve_landing_base` answers from the checked-out HEAD and complains about
    the manifest it could not read.
    """
    origin = tmp_path / "origin.git"
    git(origin.parent, "init", "--bare", "-b", "main", str(origin))
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    (clone / "README.md").write_text("# a repo with no manifest\n", encoding="utf-8")
    _seed(clone, origin, "main")
    assert not (clone / MANIFEST_NAME).exists()
    return clone


def test_a_declared_branch_records_the_arm_that_declared_it(
    declared_clone: Path,
) -> None:
    """S1 / FR-006: the manifest arm, as a value, not just the branch name."""
    result = _refresh_to_default(str(declared_clone))

    assert result.default_branch == DECLARED
    assert result.default_source == worktrees.LANDING_BASE_MANIFEST, (
        "the result must name the arm that answered; the branch alone cannot "
        "distinguish a declaration from a guess, because the resolver fails open "
        "and the fallback value is shaped exactly like a declared one"
    )
    assert result.default_source != worktrees.LANDING_BASE_HEAD
    assert MANIFEST_NAME in result.default_detail, (
        "the record must say where the declaration was read from; it said "
        f"{result.default_detail!r}"
    )


def test_a_fallback_records_the_loaders_own_complaint(
    undeclared_clone: Path,
) -> None:
    """S2 / FR-006: the fallback arm, and *why* the guess was made.

    Failing open is 107's decision and is inherited, not re-litigated (trap 4):
    a clone with no manifest still refreshes. What US3 adds is that it says so.
    The complaint is the resolver's own — asserted by equality against
    `resolve_landing_base`, because an activity that phrased the reason itself
    would be a second account of a failure only the loader witnessed, and the
    two would drift the first time the loader's wording changed.
    """
    expected = worktrees.resolve_landing_base(undeclared_clone)
    assert expected.source == worktrees.LANDING_BASE_HEAD, (
        "the fixture must actually reach the fallback arm"
    )

    result = _refresh_to_default(str(undeclared_clone))

    assert result.default_branch == "main"
    assert result.default_source == worktrees.LANDING_BASE_HEAD
    assert result.default_detail == expected.detail, (
        "the fallback's reason must be the loader's own complaint, carried "
        f"through: it recorded {result.default_detail!r} against the resolver's "
        f"{expected.detail!r}"
    )
    assert result.default_detail, (
        "a fallback with an empty reason tells an operator nothing they could "
        "not already see from the branch name"
    )


def test_the_refresh_logs_the_base_the_repository_and_the_arm(
    declared_clone: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T021 / FR-006: the line an operator reads in the worker log.

    The shape `_log_landing_base` uses for the landing path, one activity over:
    the branch, the arm that named it, and the repository it was read from — plus
    the head the refresh landed on, which is the third thing US3's story says the
    tick should be able to answer. A record that exists only as a dataclass field
    reaches nobody: the outage this spec exists to prevent was extended by the
    absence of this line, not by the absence of a field.
    """
    expected_head = git(declared_clone, "rev-parse", f"origin/{DECLARED}").strip()

    with caplog.at_level(logging.INFO, logger="factory.activities.roadmap_activities"):
        _refresh_to_default(str(declared_clone))

    lines = [record.getMessage() for record in caplog.records]
    assert lines, "the refresh must say what it did"
    stated = [line for line in lines if DECLARED in line]
    assert stated, f"no logged line named the branch the refresh used: {lines}"
    line = stated[0]
    assert worktrees.LANDING_BASE_MANIFEST in line, (
        f"the arm must be on the line even when the manifest answered: {line!r}"
    )
    assert str(declared_clone) in line, (
        f"the line must name the repository the branch was read from: {line!r}"
    )
    assert expected_head in line, (
        f"the line must name the head the refresh landed on: {line!r}"
    )
