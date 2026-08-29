"""090-US1: the roadmap's refresh takes its branch from the manifest, not HEAD.

`_refresh_to_default` is the one caller of the branch question that still asks
the operator's working copy: it read `_default_branch` — `git symbolic-ref
--short HEAD`, i.e. *whatever branch a human happened to be standing on* — and
then fetched, checked out and hard-reset that branch to its own remote. Every
300 s, on the operator's own clone.

The repository has answered that question correctly since 107:
`resolve_landing_base` reads the manifest's `landing_branch` first, falls back
to the checked-out HEAD only when the manifest is absent or malformed, and says
which arm answered. This story converts the last caller (FR-001) and adds the
field US3 will report from (FR-006).

Trap 6 in the plan is why these tests build real repositories under `tmp_path`
with a local bare `origin` and drive `_refresh_to_default` directly rather than
scripting `_clone_runner`: a scripted `CloneResult` cannot prove reset
semantics, cannot prove a branch was left untouched, and would let an
implementation that never runs git pass a story whose whole point is what git
did. `_clone_runner` stays for the workflow's handling of the result (US2).

The properties these tests defend:

- **S1 / FR-002**: a clone whose manifest declares `landing_branch: dev` while
  HEAD sits on an unrelated branch `spec/x` ends on `dev` reset to
  `origin/dev`, and `spec/x` is neither checked out nor reset. The reflog is
  the load-bearing proof: after a reset, `git status` is clean in a way that is
  indistinguishable from a clean tree nobody touched, so only what HEAD *did*
  — no `reset: moving to origin/spec/x`, and `spec/x` still at its own commit
  — separates the two.
- **S2 / FR-006**: the result names the branch the manifest declared and the
  head the reset landed on, so the workflow's status carries where the epic
  derives from rather than a guess.
- **S3 / FR-001**: a clone with no manifest falls back to the checked-out HEAD
  *exactly as `resolve_landing_base` already does*, and the result says the
  fallback arm answered. Failing open is 107's decision, inherited here, not
  re-litigated (trap 4): the gate run reports the bad manifest as a CONFIG_ERROR
  and a branch reader must not pre-empt that with a less informative refusal.
- **S4 / FR-001, trap 7**: the branch came from `resolve_landing_base` and from
  no second derivation. It is easy to satisfy S1 by calling the resolver and
  still reading `_default_branch` somewhere for the result's own fields, which
  is the silent reinstatement this scenario exists to make impossible — the
  whole argument of `landing_branch`'s docstring is "never a second
  derivation".

Written test-first: against the pre-090 code every S1-S4 assertion fails,
because the branch the refresh reads is the clone's HEAD.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from factory.activities.roadmap_activities import CloneResult, _refresh_to_default
from factory.workgraph import worktree as worktrees

from tests.target_repo import git

#: The branch the manifest declares — deliberately not the clone's HEAD, and
#: deliberately not `main`, so a refresh that read either ambient fact has to
#: fail loudly rather than pass by coincidence.
DECLARED = "dev"

#: An unrelated operator branch. HEAD sits here when the refresh runs, which is
#: the defect's own condition: before 090 the refresh would have reset *this*
#: branch to its remote, discarding whatever was on it.
OPERATOR_BRANCH = "spec/x"

#: A minimal schema-v1 manifest declaring the landing branch. `version`,
#: `runtime` and one known gate are what the schema requires; `landing_branch`
#: is the one key this story is about.
_MANIFEST = """\
version: 1
runtime: bwrap
gates:
  test: "uv run pytest -q"
landing_branch: dev
"""


def _reflog(branch: str, repo: Path) -> list[str]:
    """One ref's log entries, newest first, as `subject` lines.

    `git reflog show <ref>` writes newest first, so entries a refresh adds
    appear at the *front*; the tests below diff by length so only the acts the
    refresh performed are examined, never the fixture's own history.
    """
    out = git(repo, "reflog", "show", branch, "--format=%gs")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _new_entries(before: list[str], after: list[str]) -> list[str]:
    """The entries added since `before`, given the newest-first ordering."""
    return after[: len(after) - len(before)]


def _sha(ref: str, repo: Path) -> str:
    """The SHA a ref points at right now."""
    return git(repo, "rev-parse", ref).strip()


@pytest.fixture
def declared_clone(tmp_path: Path) -> Path:
    """A target clone whose manifest declares `dev`, with HEAD on `spec/x`.

    The shape of the incident this spec fixes: `origin` holds a `dev` branch
    that is *ahead* of where the clone's `dev` sits, so a refresh to
    `origin/dev` observably moves the branch, and an operator branch `spec/x`
    carries a commit that exists nowhere on the remote — work a wrong refresh
    would destroy and the right one must never touch.
    """
    origin = tmp_path / "origin.git"
    git(origin.parent, "init", "--bare", "-b", DECLARED, str(origin))
    git(origin, "branch", "-M", DECLARED)

    clone = tmp_path / "clone"
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    (clone / "ergane.yaml").write_text(_MANIFEST, encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "commit the declared manifest")

    # Push the manifest-bearing commit so `origin/dev` exists and holds work
    # the clone's own `dev` does not: two commits on the remote, one local.
    git(clone, "push", "--quiet", "origin", f"{DECLARED}")
    git(clone, "commit", "--quiet", "-m", "advance the remote", "--allow-empty")
    git(clone, "push", "--quiet", "origin", DECLARED)
    git(clone, "fetch", "--quiet", "origin")

    # The operator's own branch, off the remote's dev, with work on it.
    git(clone, "checkout", "--quiet", "-b", OPERATOR_BRANCH)
    (clone / "operator-notes.md").write_text("work in progress\n", encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "operator's unpushed work")
    return clone


def test_refresh_leaves_the_clone_on_the_declared_branch_and_spares_the_operator_branch(
    declared_clone: Path,
) -> None:
    """S1 / FR-002: HEAD ends on `dev` at `origin/dev`; `spec/x` is untouched."""
    spec_x_before = _sha(OPERATOR_BRANCH, declared_clone)
    spec_x_reflog_before = _reflog(OPERATOR_BRANCH, declared_clone)
    dev_reflog_before = _reflog(DECLARED, declared_clone)
    dev_on_origin = _sha(f"origin/{DECLARED}", declared_clone)
    assert spec_x_before != dev_on_origin, "fixture must give the two branches distinct tips"

    _refresh_to_default(str(declared_clone))

    assert (
        git(declared_clone, "symbolic-ref", "--short", "HEAD").strip() == DECLARED
    ), "the clone must end checked out on the declared landing branch"
    assert _sha("HEAD", declared_clone) == dev_on_origin, (
        "the declared branch must be reset to its own remote ref, not left at "
        "whatever the clone last saw"
    )
    assert (
        git(declared_clone, "status", "--porcelain").strip() == ""
    ), "a clean clone must stay clean through the refresh"

    # The branch the operator was standing on: same commit, and nothing the
    # refresh did to it. This is the half of S1 a `git status` on `dev` cannot
    # prove — a reset of `spec/x` leaves `dev`'s status just as clean, which
    # is exactly how the defect shipped.
    assert _sha(OPERATOR_BRANCH, declared_clone) == spec_x_before, (
        f"{OPERATOR_BRANCH} must not be reset: its commit is work the factory "
        "has no right to discard"
    )
    spec_x_acts = _new_entries(spec_x_reflog_before, _reflog(OPERATOR_BRANCH, declared_clone))
    assert not spec_x_acts, (
        f"the refresh acted on {OPERATOR_BRANCH} ({spec_x_acts}); an operator "
        "branch must be neither checked out nor reset. An unpushed branch that "
        "is never reset cannot stall the line, and a pushed one can never "
        "become the tree an epic derives from"
    )
    # And positively: the refresh's own acts all belong to the declared branch.
    dev_acts = _new_entries(dev_reflog_before, _reflog(DECLARED, declared_clone))
    assert any("reset: moving to origin/dev" in entry for entry in dev_acts), (
        "the declared branch must be the one that was reset"
    )


def test_refresh_reports_the_declared_branch_and_the_remote_head(
    declared_clone: Path,
) -> None:
    """S2 / FR-006: the result names `dev` and `origin/dev`'s SHA."""
    expected_head = _sha(f"origin/{DECLARED}", declared_clone)

    result = _refresh_to_default(str(declared_clone))

    assert isinstance(result, CloneResult)
    assert result.default_branch == DECLARED, (
        "the result's branch field must carry the branch the manifest declared, "
        "not the branch HEAD happened to be on"
    )
    assert result.head_ref == expected_head, (
        "the result's head field must carry the commit the reset landed on — "
        "the branch point the epic's nodes pin against (FR-006)"
    )
    assert result.path == str(declared_clone)


def test_refresh_without_a_manifest_falls_back_to_the_checked_out_head(
    tmp_path: Path,
) -> None:
    """S3 / FR-001: no manifest means today's behaviour, labelled as such.

    Failing open is 107's decision (trap 4): the manifest's absence is reported
    as a CONFIG_ERROR by the gate run, and a branch reader that refused instead
    would pre-empt that with a less informative exception — and park every spec
    on a repo that today refreshes fine.
    """
    origin = tmp_path / "origin.git"
    git(origin.parent, "init", "--bare", "-b", "main", str(origin))
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    (clone / "README.md").write_text("# no manifest here\n", encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "a repo with no manifest")
    git(clone, "push", "--quiet", "origin", "main")
    git(clone, "fetch", "--quiet", "origin")
    assert not (clone / "ergane.yaml").exists()

    result = _refresh_to_default(str(clone))

    assert result.default_branch == "main", (
        "an absent manifest must keep today's behaviour: the checked-out HEAD"
    )
    assert result.head_ref == _sha("origin/main", clone)
    # The label is the whole point of `LandingBase.source`: the fallback value
    # is indistinguishable from a declared one, so only the arm tells them
    # apart. S3 says the result *records* that the fallback answered.
    assert result.default_source == worktrees.LANDING_BASE_HEAD


def test_refresh_takes_its_branch_from_the_resolver_and_never_a_second_derivation(
    declared_clone: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S4 / trap 7: `resolve_landing_base` answered; `_default_branch` was never asked.

    The branch is patched at the seam the refresh must read — the workgraph
    module's own binding, since the refresh imports it deferred inside the
    function body (trap 5). `_default_branch` is patched to fail the test
    rather than return, because a call it survives is a call this scenario
    exists to catch: an implementation could take the branch from the resolver
    and still read HEAD again for the result's own fields.
    """
    seen: dict[str, Any] = {}

    def fake_resolve(repo: Any) -> Any:
        seen["repo"] = str(repo)
        return worktrees.LandingBase(
            branch=DECLARED,
            source=worktrees.LANDING_BASE_MANIFEST,
            detail="declared in ergane.yaml",
        )

    def no_second_derivation(repo: Any) -> str:
        pytest.fail(
            "_refresh_to_default read the branch a second time: "
            "`_default_branch` was called directly. FR-001 makes "
            "`resolve_landing_base` the one derivation."
        )

    monkeypatch.setattr(worktrees, "resolve_landing_base", fake_resolve)
    monkeypatch.setattr(worktrees, "_default_branch", no_second_derivation)

    result = _refresh_to_default(str(declared_clone))

    assert seen.get("repo") == str(declared_clone), (
        "the refresh must ask the resolver about the clone it was handed"
    )
    assert result.default_branch == DECLARED, (
        "the branch the refresh used must be the resolver's answer"
    )


def test_the_seam_still_points_at_the_real_refresh() -> None:
    """The production seam must keep naming the real refresh.

    `_clone_runner` is the seam the workflow's tests script; production points
    it at `_refresh_to_default`. A test that scripted the seam to hide the
    real path would let the S1-S4 properties pass while nothing changed.
    """
    from factory.activities.roadmap_activities import _clone_runner

    assert _clone_runner is _refresh_to_default