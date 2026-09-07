"""090-US2: a refresh that would destroy work refuses, and the workflow parks.

US1 stopped the refresh reading the operator's HEAD, which makes the *common*
case safe: an operator standing on `spec/x` is now never checked out or reset.
It leaves one case open, and it is the one where the reset is least expected —
an operator working directly on the branch the manifest declares. There the
refresh still does exactly what it always did:

    git fetch origin
    git checkout dev
    git reset --hard origin/dev

and both halves of that last line destroy work. The obvious half is the working
tree: an uncommitted edit to a tracked file is gone. The half that is easy to
miss — and the one this repository actually paid for — is that the reset target
is a *remote* ref, so a change the operator committed **to be safe** is
discarded just as surely, because a local commit is not on `origin/dev` either
(plan trap 2).

So the guard is two questions, not one, and a `git status --porcelain` check
alone passes this repository's own worst case. The properties defended here:

- **S1 / FR-003**: an uncommitted modification to a tracked file refuses, no
  reset is performed, and the modification is still on disk afterwards.
- **S2 / FR-003, trap 2**: a commit that is not on `origin/<branch>` refuses,
  with a clean working tree — the case a dirty-tree check cannot see.
- **S3 / FR-007**: the control. A clean clone on the declared branch fetches
  and resets exactly as it did before this story. This story adds a refusal,
  not a behaviour change on the path that was always safe.
- **S4 / FR-005, trap 3**: files the target repo's own ignore rules cover do
  not refuse. `reset --hard` does not discard them, so counting them as work at
  risk would park every clone that has ever run a build (`.factory/`,
  `__pycache__/`, `node_modules/`). The rules are git's, read from the target
  repo — never a hand-written list of directory names, which is the mistake the
  boundary detector's `EXCLUDED_DIR_NAMES` made once against a Python-shaped
  repo, removed again by epic 130 US3 (FR-006).

Real repositories under `tmp_path` with a local bare `origin`, driving
`_refresh_to_default` directly, for the reason plan trap 6 gives: a scripted
`CloneResult` cannot prove that no reset was performed. The reflog is the
load-bearing evidence throughout — after a reset, `git status` is clean in a way
that is indistinguishable from a tree nobody touched, so only the *absence* of a
`reset: moving to origin/dev` entry separates "spared" from "destroyed and
restored by coincidence". The workflow's half of FR-003 — parking on the
refusal the result carries — is scripted through `_clone_runner` in
`tests/test_roadmap_scheduler.py` (T012), where the seam belongs.

Written test-first: against the pre-US2 code S1, S2 and their message
assertions fail, because `CloneResult` has no refusal to carry and the refresh
resets unconditionally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.activities.roadmap_activities import _refresh_to_default

from tests.target_repo import git

#: The branch the manifest declares, and — unlike US1's fixture — the branch the
#: clone is standing on. That is US2's whole condition: the operator is working
#: directly on the landing branch, where US1's protection does not reach.
DECLARED = "dev"

_MANIFEST = """\
version: 1
runtime: bwrap
gates:
  test: "uv run pytest -q"
landing_branch: dev
"""

#: The target repo's own ignore rules. S4 turns on these being *the repo's*:
#: a guard that hand-rolled its own exclusions would have to know that this
#: repository ignores `.factory/` and `*.log`, and could not know it for the
#: next target repo.
_GITIGNORE = """\
.factory/
*.log
"""


def _reflog(ref: str, repo: Path) -> list[str]:
    """One ref's log entries, newest first, as `subject` lines."""
    out = git(repo, "reflog", "show", ref, "--format=%gs")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _new_entries(before: list[str], after: list[str]) -> list[str]:
    """The entries added since `before`, given the newest-first ordering."""
    return after[: len(after) - len(before)]


def _sha(ref: str, repo: Path) -> str:
    """The SHA a ref points at right now."""
    return git(repo, "rev-parse", ref).strip()


@pytest.fixture
def landing_clone(tmp_path: Path) -> Path:
    """A clone standing on the declared landing branch, with origin ahead of it.

    `origin/dev` carries a commit the clone has never seen, pushed through a
    second working copy, so a refresh that fetches and resets *observably*
    moves the branch — S3 can then assert the reset happened rather than
    assert the absence of evidence. The clone's own remote-tracking ref is
    deliberately stale at fixture exit: the refresh's fetch is what makes it
    current, and the unpushed-commit question is only answerable after it.
    """
    origin = tmp_path / "origin.git"
    git(origin.parent, "init", "--bare", "-b", DECLARED, str(origin))
    git(origin, "branch", "-M", DECLARED)

    clone = tmp_path / "clone"
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    (clone / "ergane.yaml").write_text(_MANIFEST, encoding="utf-8")
    (clone / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
    (clone / "README.md").write_text("# the target repo\n", encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "the manifest, the ignore rules, a readme")
    git(clone, "push", "--quiet", "origin", DECLARED)

    # Advance `origin/dev` from somewhere other than the clone, so the clone is
    # behind the remote without any local rewind muddying its reflog.
    publisher = tmp_path / "publisher"
    git(tmp_path, "clone", "--quiet", str(origin), str(publisher))
    (publisher / "LANDED.md").write_text("a story landed on the trunk\n", encoding="utf-8")
    git(publisher, "add", "-A")
    git(publisher, "commit", "--quiet", "-m", "advance origin/dev")
    git(publisher, "push", "--quiet", "origin", DECLARED)

    assert git(clone, "symbolic-ref", "--short", "HEAD").strip() == DECLARED
    return clone


def _origin_head(clone: Path) -> str:
    """What `origin/dev` really points at — read from the bare repo, not the stale ref."""
    origin = clone.parent / "origin.git"
    return git(origin, "rev-parse", DECLARED).strip()


def test_an_uncommitted_change_to_a_tracked_file_refuses_and_survives(
    landing_clone: Path,
) -> None:
    """S1 / FR-003, FR-004: the refusal names the branch and the path, and no reset runs."""
    (landing_clone / "README.md").write_text(
        "# the target repo\n\noperator's uncommitted note\n", encoding="utf-8"
    )
    head_before = _sha("HEAD", landing_clone)
    head_reflog_before = _reflog("HEAD", landing_clone)

    result = _refresh_to_default(str(landing_clone))

    assert result.refusal, (
        "a clone whose tracked file is modified must be refused: the checkout "
        "and reset that follow would discard the modification"
    )
    assert DECLARED in result.refusal, "FR-004: the refusal must name the branch"
    assert "README.md" in result.refusal, (
        "FR-004: the refusal must name the paths at risk — a bare 'the clone is "
        "dirty' leaves the operator to find the work themselves"
    )

    # No reset, and no checkout: the refusal happens before either.
    acts = _new_entries(head_reflog_before, _reflog("HEAD", landing_clone))
    assert not acts, (
        f"the refresh acted on the clone ({acts}); a refusal must perform no "
        "reset. Fetching is not a reset and is what makes the question "
        "answerable, but nothing may move HEAD"
    )
    assert _sha("HEAD", landing_clone) == head_before

    # And the work itself: still on disk, still uncommitted, unchanged.
    assert (
        "operator's uncommitted note" in (landing_clone / "README.md").read_text(encoding="utf-8")
    ), "the modification the refusal was about must still be present afterwards"
    assert "README.md" in git(landing_clone, "status", "--porcelain")


def test_a_local_commit_absent_from_the_remote_refuses_and_survives(
    landing_clone: Path,
) -> None:
    """S2 / FR-003, trap 2: a *committed* change is destroyed too, so it refuses too.

    The working tree here is clean. That is the entire point: an operator who
    commits their work to keep it safe from the reset has made it invisible to
    `git status --porcelain` and no safer at all, because the reset target is
    `origin/dev` and their commit is not on it. A guard that asked only the
    working tree would pass this test's clone straight through to the reset
    that destroys it.
    """
    (landing_clone / "GROOMED.md").write_text("a grooming write, committed\n", encoding="utf-8")
    git(landing_clone, "add", "-A")
    git(landing_clone, "commit", "--quiet", "-m", "operator's unpushed grooming write")
    local_commit = _sha("HEAD", landing_clone)
    short_sha = git(landing_clone, "rev-parse", "--short", "HEAD").strip()
    head_reflog_before = _reflog("HEAD", landing_clone)
    assert git(landing_clone, "status", "--porcelain").strip() == "", (
        "the fixture must leave a clean working tree: a dirty one would let a "
        "tracked-paths-only guard pass this scenario for the wrong reason"
    )
    assert local_commit != _origin_head(landing_clone)

    result = _refresh_to_default(str(landing_clone))

    assert result.refusal, (
        "a commit that is not on the remote ref must be refused: `reset --hard "
        "origin/dev` discards it as surely as an uncommitted edit"
    )
    assert DECLARED in result.refusal, "FR-004: the refusal must name the branch"
    assert short_sha in result.refusal or local_commit in result.refusal, (
        "FR-004: the refusal must name the commit at risk, so the operator can "
        f"find it; it said instead: {result.refusal!r}"
    )

    acts = _new_entries(head_reflog_before, _reflog("HEAD", landing_clone))
    assert not acts, f"the refresh acted on the clone ({acts}); a refusal performs no reset"
    assert _sha(DECLARED, landing_clone) == local_commit, (
        "the unpushed commit must still be the tip of the declared branch"
    )
    assert (landing_clone / "GROOMED.md").exists()


def test_a_clean_clone_on_the_declared_branch_refreshes_exactly_as_before(
    landing_clone: Path,
) -> None:
    """S3 / FR-007: the control. Nothing at risk means fetch and reset, unchanged."""
    remote_head = _origin_head(landing_clone)
    head_reflog_before = _reflog("HEAD", landing_clone)
    assert _sha("HEAD", landing_clone) != remote_head, (
        "the fixture must leave the clone behind its remote, so a reset that "
        "happens is visible as movement rather than as a no-op"
    )

    result = _refresh_to_default(str(landing_clone))

    assert not result.refusal, (
        "a clean clone on the declared branch carries nothing at risk and must "
        f"refresh: it refused with {result.refusal!r}"
    )
    assert result.default_branch == DECLARED
    assert result.head_ref == remote_head, (
        "the fetch must have run and the reset must have landed the clone on "
        "the remote's current head — this is what makes an epic derive from "
        "the trunk rather than from whatever the clone last saw"
    )
    acts = _new_entries(head_reflog_before, _reflog("HEAD", landing_clone))
    assert acts == [
        f"reset: moving to origin/{DECLARED}",
        f"checkout: moving from {DECLARED} to {DECLARED}",
    ], (
        "the refresh must fetch, check out and reset exactly as it did before "
        f"this story; it performed: {acts}"
    )


def test_files_the_target_repo_ignores_do_not_refuse(landing_clone: Path) -> None:
    """S4 / FR-005, trap 3: ignored files are not work at risk.

    `.factory/` and `*.log` are ignored by *this* repo's `.gitignore`, and the
    guard learns that from git rather than from a list it carries. A guard that
    counted them would park every clone the factory has ever built in — which
    is every clone the roadmap runs against.
    """
    (landing_clone / ".factory").mkdir()
    (landing_clone / ".factory" / "state.json").write_text("{}\n", encoding="utf-8")
    (landing_clone / "build.log").write_text("gate output\n", encoding="utf-8")
    ignored = git(landing_clone, "status", "--porcelain", "--ignored")
    assert ".factory/" in ignored and "build.log" in ignored, (
        "the fixture must give git something it considers ignored, or this "
        "scenario proves nothing"
    )
    assert git(landing_clone, "status", "--porcelain").strip() == "", (
        "and git must not report them as ordinary untracked files"
    )
    remote_head = _origin_head(landing_clone)

    result = _refresh_to_default(str(landing_clone))

    assert not result.refusal, (
        "ignored files are not work at risk — `reset --hard` does not touch "
        f"them — and must not park a spec; it refused with {result.refusal!r}"
    )
    assert result.head_ref == remote_head, "the refresh must have proceeded"
    # And they are still there, because the reset never had anything to do with
    # them: the reason the refusal would have been wrong, demonstrated.
    assert (landing_clone / ".factory" / "state.json").exists()
    assert (landing_clone / "build.log").exists()
