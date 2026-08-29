"""090-US2: a refresh that would destroy work parks the spec instead.

US1 made the refresh reset the *declared* branch, which made the common case
safe: an operator standing anywhere else is never touched. US2 is the guard for
the case that remains — an operator working **on the landing branch itself**,
where a `reset --hard origin/<branch>` is least expected and most destructive.

The reset the refresh performs is not a safe operation on a dirty clone:

- `reset --hard` discards an uncommitted modification to a tracked file.
- Because the reset target is the *remote* ref, it discards a locally committed
  change just as surely — `origin/dev` does not know about a commit that was
  never pushed. A dirty-tree check alone passes this repository's own worst
  case (trap 2): a grooming write that was committed *to be safe* was destroyed
  anyway.
- `reset --hard` does **not** touch ignored files, so counting them as work at
  risk would park every clone that has ever run a build (trap 3). The check
  asks git, with the target repo's own ignore rules.

The refusal this story adds is a *refused clone*, not a git error (trap 1):
`clone_target`'s contract says a refused clone never raises — the workflow
parks it — while a git error propagates as an activity failure. So the refusal
rides `CloneResult` (T014), and the workflow parks on it explicitly (T015).

Trap 6 is why these tests build real repositories under `tmp_path` with a local
bare `origin` and drive `_refresh_to_default` directly: a scripted
`CloneResult` cannot prove the reset did not happen, and the one thing US2 must
prove is what git did *not* do. The reflog is the load-bearing proof — after a
reset, a clean `git status` is indistinguishable from a clean tree nobody
touched.

Written test-first: against the post-US1 code every assertion below fails,
because the refresh resets unconditionally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.activities.roadmap_activities import CloneResult, _refresh_to_default

from tests.target_repo import git

#: The branch the manifest declares — deliberately not `main`, so a refresh
#: that guessed the trunk rather than read the declaration fails loudly.
DECLARED = "dev"

#: A minimal schema-v1 manifest declaring the landing branch. `version`,
#: `runtime` and one known gate are what the schema requires; `landing_branch`
#: is the key the whole epic turns on.
_MANIFEST = """\
version: 1
runtime: bwrap
gates:
  test: "uv run pytest -q"
landing_branch: dev
"""

#: What a refusal must name beyond the paths themselves (FR-004): the operator
#: act that clears it. The refusal is for a human mid-work; a hazard that says
#: what is at risk but not what to do about it parks the line as surely as the
#: silence this spec replaced. Matched case-insensitively, because the refusal
#: is a sentence and the sentence capitalises it.
CLEARING_ACT = "commit or push"


def _names_the_clearing_act(refusal: str) -> bool:
    """Whether the refusal tells the operator how to clear it (FR-004)."""
    return CLEARING_ACT in refusal.lower()


def _reflog(ref: str, repo: Path) -> list[str]:
    """One ref's log entries, newest first, as `subject` lines.

    `git reflog show <ref>` writes newest first, so entries a refresh adds
    appear at the *front*; the tests below diff by length so only the acts the
    refresh performed are examined, never the fixture's own history.
    """
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
    """A clean clone *on the declared landing branch*, ahead of its origin.

    The shape US2 guards: the operator works directly on the landing branch,
    and `origin/dev` exists and is *behind* the clone, so a refresh to the
    remote ref observably moves the branch — and, before this story, would
    have discarded whatever the operator had that the remote did not.

    Nothing is at risk at fixture time: the starting state is the clean clone
    US2-S3 refreshes exactly as before, and each test adds exactly the kind of
    work the scenario names before it calls the refresh.
    """
    origin = tmp_path / "origin.git"
    git(origin.parent, "init", "--bare", "-b", DECLARED, str(origin))

    clone = tmp_path / "clone"
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    (clone / "ergane.yaml").write_text(_MANIFEST, encoding="utf-8")
    (clone / "README.md").write_text("# tracked, so a reset can discard it\n", encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "commit the declared manifest")
    git(clone, "push", "--quiet", "origin", DECLARED)
    git(clone, "fetch", "--quiet", "origin")

    # The local landing branch moves ahead of the remote: one commit, pushed,
    # so the fixture's own state is clean and nothing is at risk yet.
    git(clone, "commit", "--quiet", "-m", "a pushed step on the landing branch", "--allow-empty")
    git(clone, "push", "--quiet", "origin", DECLARED)
    git(clone, "fetch", "--quiet", "origin")

    # A second step, this one *not* pushed — the fixture's own trap-2 shape,
    # armed by each test that needs it and disarmed by the ones that do not.
    # It stays out of the working tree's status: a committed change is exactly
    # the case a dirty-tree check misses.
    git(clone, "commit", "--quiet", "-m", "the unpushed step", "--allow-empty")
    return clone


def _disarm_unpushed_step(clone: Path) -> None:
    """Put the fixture's unpushed commit onto the remote, arming nothing.

    US2-S3 and US2-S4 need a clone whose landing branch is *at* its remote ref,
    so the fixture's unpushed step has to reach the origin before the refresh
    runs. A fresh fetch afterwards keeps `origin/<branch>` current.
    """
    git(clone, "push", "--quiet", "origin", DECLARED)
    git(clone, "fetch", "--quiet", "origin")


# --- US2-S1 / FR-003: an uncommitted modification parks, and survives ---------


def test_an_uncommitted_modification_to_a_tracked_file_parks_and_survives(
    landing_clone: Path,
) -> None:
    """S1 / FR-003: dirty tracked paths refuse the refresh; nothing resets.

    The refusal names the dirty paths (FR-004), and the modification is still
    present afterwards — the two halves of the scenario that make it about
    *saving* the work rather than merely about *noticing* it.
    """
    (landing_clone / "README.md").write_text("work in progress\n", encoding="utf-8")
    head_reflog_before = _reflog("HEAD", landing_clone)
    dev_before = _sha(DECLARED, landing_clone)

    result = _refresh_to_default(str(landing_clone))

    # A refusal, not an exception (trap 1): the activity returns, carrying the
    # refusal, and only a git error would have raised.
    assert result.refused, "a dirty tracked file must refuse the refresh"
    # FR-004: the refusal names the branch, the paths at risk, and the act
    # that clears it.
    assert DECLARED in result.refused, "the refusal must name the branch"
    assert "README.md" in result.refused, (
        "the refusal must name the dirty path, so the operator learns what "
        "the factory was about to discard"
    )
    assert _names_the_clearing_act(result.refused), (
        "the refusal must name the operator act that clears it (FR-004)"
    )
    # No reset: the branch is where it was, and the modification survived.
    assert _sha(DECLARED, landing_clone) == dev_before, (
        "a refused refresh must not move the landing branch"
    )
    assert "work in progress" in (landing_clone / "README.md").read_text(
        encoding="utf-8"
    ), "the uncommitted modification the refusal named must still be on disk"
    assert not any(
        entry.startswith("reset:") for entry in _new_entries(head_reflog_before, _reflog("HEAD", landing_clone))
    ), "the reflog must show no reset: the tick was refused before it could act"


def test_a_staged_but_uncommitted_change_parks_the_spec(
    landing_clone: Path,
) -> None:
    """S1 / FR-003: a staged change is as destructible as an unstaged one.

    `reset --hard` discards the staged copy and the working-tree copy alike,
    so the guard must count it. A check that read only unstaged edits would
    park a spec whose operator had done the responsible-looking thing.
    """
    (landing_clone / "README.md").write_text("staged work\n", encoding="utf-8")
    git(landing_clone, "add", "README.md")

    result = _refresh_to_default(str(landing_clone))

    assert "README.md" in result.refused, (
        "a staged modification must be named in the refusal: `reset --hard` "
        "discards it exactly as it discards an unstaged one"
    )
    assert "staged work" in (landing_clone / "README.md").read_text(encoding="utf-8")


# --- US2-S2 / FR-003: an unpushed commit parks, and survives (trap 2) ----------


def test_an_unpushed_commit_parks_and_survives_the_trap_2_case(
    landing_clone: Path,
) -> None:
    """S2 / FR-003: a clean tree whose branch is ahead of its remote still refuses.

    Trap 2 is this story's own measured case: `git status --porcelain` is empty
    here, because the work was *committed to be safe* — and the reset target is
    `origin/dev`, so the commit is destroyed exactly as surely as an uncommitted
    edit. A dirty-tree check alone passes this scenario and must not.
    """
    dev_before = _sha(DECLARED, landing_clone)
    remote_before = _sha(f"origin/{DECLARED}", landing_clone)
    assert dev_before != remote_before, "fixture must arm the unpushed commit"
    assert git(landing_clone, "status", "--porcelain").strip() == "", (
        "the fixture's own point: the tree is clean while the work is at risk"
    )
    head_reflog_before = _reflog("HEAD", landing_clone)

    result = _refresh_to_default(str(landing_clone))

    assert result.refused, (
        "an unpushed commit must refuse the refresh even though the working "
        "tree is clean — the reset target is the remote ref (trap 2)"
    )
    assert "the unpushed step" in result.refused, (
        "the refusal must name the unpushed commit by its subject, so an "
        "operator learns which of their commits is at risk (FR-004)"
    )
    assert _names_the_clearing_act(result.refused), (
        "the refusal must name the operator act that clears it (FR-004)"
    )
    assert _sha(DECLARED, landing_clone) == dev_before, (
        "a refused refresh must not move the landing branch: the unpushed "
        "commit is work the factory has no right to discard"
    )
    assert not any(
        entry.startswith("reset:") for entry in _new_entries(head_reflog_before, _reflog("HEAD", landing_clone))
    ), "the reflog must show no reset"


def test_a_clean_tree_on_a_pushed_branch_is_not_a_refusal(
    landing_clone: Path,
) -> None:
    """S2's own boundary: ahead-of-remote is what parks, not merely clean.

    The trap-2 check must not become a refusal of every refresh: a clone whose
    landing branch is *at* its remote ref has nothing at risk, committed or
    otherwise, and must refresh. This is the discriminating case between "asks
    git about the remote ref" and "parks whenever git says anything".
    """
    _disarm_unpushed_step(landing_clone)

    result = _refresh_to_default(str(landing_clone))

    assert not result.refused, (
        "a clean clone whose branch matches its remote must not be refused"
    )
    assert result.default_branch == DECLARED


# --- US2-S3 / FR-007: the control — a clean clone refreshes exactly as before --


def test_a_clean_clone_on_the_declared_branch_refreshes_exactly_as_before(
    landing_clone: Path,
) -> None:
    """S3 / FR-007: the always-safe path is untouched — fetch, then reset.

    The control, and the scenario that stops a guard from becoming a behaviour
    change: a clean clone at its remote ref must come back reset to
    `origin/dev` with the same reflog acts US1 established — `reset: moving to
    origin/dev` and nothing else. A refusal that fires here parks the line
    permanently, which is the failure mode this story must not introduce.
    """
    _disarm_unpushed_step(landing_clone)
    head_reflog_before = _reflog("HEAD", landing_clone)

    result = _refresh_to_default(str(landing_clone))

    assert not result.refused, "a clean clone must not be refused (FR-007)"
    assert _sha("HEAD", landing_clone) == _sha(f"origin/{DECLARED}", landing_clone), (
        "the clean clone must still be reset to its remote ref (FR-007)"
    )
    # Exactly the acts US1 established for a clean refresh, newest first: the
    # reset to the remote ref, preceded by the checkout — which git logs even
    # when the branch it names is the one already checked out, so the pair is
    # today's behaviour, not a new one. A refusal here would have been the
    # behaviour change S3 exists to forbid.
    assert _new_entries(head_reflog_before, _reflog("HEAD", landing_clone)) == [
        f"reset: moving to origin/{DECLARED}",
        f"checkout: moving from {DECLARED} to {DECLARED}",
    ], (
        "the refresh's acts on a clean clone must be exactly today's: the "
        "checkout and the reset to the remote ref, nothing else"
    )
    assert result.default_branch == DECLARED
    assert result.head_ref == _sha(f"origin/{DECLARED}", landing_clone)


def test_a_remote_moved_while_the_clone_was_clean_is_followed_not_parked(
    tmp_path: Path,
) -> None:
    """S3 / FR-007: a *behind* clean clone is the refresh's whole job.

    The case the reset exists for — another landing moved the remote, and the
    clone must follow it — must not be confused with work at risk. The clone
    is behind and clean, so the reset moves it *forward* and discards nothing.
    """
    origin = tmp_path / "origin.git"
    git(origin.parent, "init", "--bare", "-b", DECLARED, str(origin))
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    (clone / "ergane.yaml").write_text(_MANIFEST, encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "commit the declared manifest")
    git(clone, "push", "--quiet", "origin", DECLARED)

    # Another landing advances the remote behind the clone's back.
    scratch = tmp_path / "scratch"
    git(tmp_path, "clone", "--quiet", str(origin), str(scratch))
    git(scratch, "commit", "--quiet", "-m", "another landing moves the remote", "--allow-empty")
    git(scratch, "push", "--quiet", "origin", DECLARED)

    result = _refresh_to_default(str(clone))

    assert not result.refused, (
        "a clean clone behind its remote is the refresh's normal case, not a "
        "refusal — the reset moves it forward and discards nothing"
    )
    assert result.head_ref == _sha(f"origin/{DECLARED}", clone)


# --- US2-S4 / FR-005: files the target repo ignores park nothing (trap 3) ------


def test_files_the_target_repo_ignores_do_not_park_anything(
    landing_clone: Path,
) -> None:
    """S4 / FR-005: ignored files are not work at risk, because git says so.

    `reset --hard` does not touch ignored files, so counting them would park
    every clone that has ever run a build — `.factory/`, `node_modules/`,
    `__pycache__`. The check asks git with the target repo's *own* ignore
    rules (trap 3); a hand-rolled list written against one repo is the mistake
    this repository has already paid for once.
    """
    _disarm_unpushed_step(landing_clone)
    (landing_clone / ".gitignore").write_text(
        ".factory/\n__pycache__/\n", encoding="utf-8"
    )
    git(landing_clone, "add", ".gitignore")
    git(landing_clone, "commit", "--quiet", "-m", "commit the repo's own ignore rules")
    git(landing_clone, "push", "--quiet", "origin", DECLARED)
    git(landing_clone, "fetch", "--quiet", "origin")
    # Ignored artefacts, exactly the kind a build leaves behind.
    (landing_clone / ".factory" / "worktrees").mkdir(parents=True, exist_ok=True)
    (landing_clone / ".factory" / "worktrees" / "scratch.txt").write_text(
        "a build artefact\n", encoding="utf-8"
    )
    (landing_clone / "__pycache__").mkdir(exist_ok=True)
    (landing_clone / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"\x00\x01")

    result = _refresh_to_default(str(landing_clone))

    assert not result.refused, (
        "ignored files must not park the spec: `reset --hard` does not touch "
        "them, so treating them as work at risk would park every clone that "
        "has ever run a build (FR-005)"
    )
    assert _sha("HEAD", landing_clone) == _sha(f"origin/{DECLARED}", landing_clone), (
        "the refresh must still reset a clean clone to its remote ref"
    )


def test_an_untracked_file_git_does_not_ignore_still_does_not_park(
    landing_clone: Path,
) -> None:
    """S4's boundary: the *ignore rules* decide, not whether a file is tracked.

    A reset to the same ref the branch already sits at cannot discard an
    untracked file either way — but the discriminating case is what keeps the
    guard honest about *whose* rules answered. An untracked file the repo does
    not ignore is left alone by the reset and must not park; the scenario above
    proves the ignored ones do not either, so together they pin the check to
    git's own answer rather than to any list of names.
    """
    _disarm_unpushed_step(landing_clone)
    (landing_clone / "operator-scratch.txt").write_text(
        "not tracked, not ignored\n", encoding="utf-8"
    )

    result = _refresh_to_default(str(landing_clone))

    assert not result.refused, (
        "an untracked file on a clone whose branch matches its remote must "
        "not park: the reset neither needs nor would perform a checkout "
        "through it"
    )


# --- the contract: a refusal rides the result, never an exception (trap 1) ----


def test_the_refusal_is_carried_on_the_result_not_raised(
    landing_clone: Path,
) -> None:
    """T014 / trap 1: a refused clone returns; only a git error raises.

    `clone_target`'s contract draws the line US2 must keep: raising from the
    activity would land the refusal in the workflow's `FailureError` arm and
    park it with a stringified exception — which works by accident and
    contradicts the contract. The refusal is data on `CloneResult`, and the
    workflow parks on it explicitly (T012 proves that half against the seam).
    """
    from factory.activities.roadmap_activities import clone_target

    (landing_clone / "README.md").write_text("work in progress\n", encoding="utf-8")

    result = _refresh_to_default(str(landing_clone))

    assert isinstance(result, CloneResult)
    assert result.refused
    # A refused result still names the branch it was asked to refresh, so the
    # park reason can say which branch the operator's work is sitting on.
    assert result.default_branch == DECLARED
    # And the refusal is readable without knowing the dataclass: any caller
    # that stringifies the result sees the hazard, not a bare repr.
    assert result.refused in repr(result)


async def test_the_activity_returns_a_refused_result_rather_than_raising(
    landing_clone: Path,
) -> None:
    """T014, at the activity boundary: the wrapper adds no exception of its own.

    `clone_target` is a thin pass-through to the seam, so the refusal must
    survive the activity boundary as data. Driven through `activity.sh`-free
    direct call — the wrapper's only job is to hand the seam's answer back.
    """
    from factory.activities.roadmap_activities import CloneInput, clone_target

    (landing_clone / "README.md").write_text("work in progress\n", encoding="utf-8")

    result = await clone_target(
        CloneInput(target_repo=str(landing_clone), spec_dir="001-alpha")
    )

    assert isinstance(result, CloneResult)
    assert result.refused, "the activity must return the refusal, not raise it"


def test_the_refusal_names_the_branch_and_both_kinds_of_risk(
    landing_clone: Path,
) -> None:
    """T016 / FR-004: one refusal naming both the dirty path and the commit.

    The refusal is for an operator who has to decide what to do with their
    half-finished work. Branch, paths, commits and the act that clears it —
    all on the one line that parks, because that line is the only place the
    operator will look.
    """
    (landing_clone / "README.md").write_text("work in progress\n", encoding="utf-8")

    result = _refresh_to_default(str(landing_clone))

    assert DECLARED in result.refused
    assert "README.md" in result.refused
    assert "the unpushed step" in result.refused, (
        "the refusal must name the unpushed commit alongside the dirty path: "
        "FR-003 requires both checks, and the operator needs both names"
    )
    assert _names_the_clearing_act(result.refused)