"""049-US4: wiring a repository is a forge operation.

034/US3 taught the factory to make a repository satisfy `evaluate_repo` — but it
did it by speaking GitHub's client through a seam that only *resolved* a forge
and then reached past it (`factory/cli/init.py`, the `.client` this story
removes). Here the act itself crosses the seam: `apply_landing_policy` is the
write side of `landing_policy`, and the GitHub implementation of it is 034/US3's
`wire_repo` unchanged (FR-012).

Every assertion here is on a **judged repository**, never on a call log. The
distinction is the story: "we called the wiring function" is a claim about this
code, and "the model now passes the gate that guards every epic start" is a
claim about the world — only the second one can fail when the wiring is wrong.

Neither model here is `tests/fake_gh.py`, and that is a requirement rather than
a preference (FR-004, plan trap 3): its match loop consumes nothing, so the
first matching expectation answers a command forever, a second identical command
is unreachable, and **an idempotence claim tested through it cannot fail**
(`ci/the-scripted-gh-fake-never-consumes-an-expectation`). The two models used
instead are `FakeGitHub` (`tests/test_ergane_init_wiring.py`, GitHub as mutable
state behind the real `gh` argv surface) and `RepositoryModel`
(`tests/fake_forge.py`, a repository behind the seam itself).

Every test answers "what edit would make this fail?" in its own docstring;
the transcripts are committed at `specs/049-forge-seam/evidence/us4-mutations.md`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from factory.activities.merge_activities import onboard_target_repo
from factory.mergequeue.wiring import ALREADY_SATISFIED, APPLIED
from factory.mergequeue.gh import GhClient
from factory.mergequeue.github_forge import GithubForge
from tests.fake_forge import FakeForge, RepositoryModel
from tests.target_repo import build_target_repo
from tests.test_ergane_init_wiring import FakeGitHub

#: The gates `tests/fixtures/target_repo/` declares — so gate↔check parity (Q4)
#: is asked of exactly what wiring required.
FIXTURE_GATES = ("lint", "test", "typecheck")


def github_forge_over(model: FakeGitHub, repo: Path) -> GithubForge:
    """The shipped forge, reading and writing one model of a GitHub repository.

    A fresh forge per read: `describe_repository` caches, and a cached answer
    could hide a wiring act that changed nothing.
    """
    return GithubForge(GhClient(repo=str(repo), runner=model))


def failing(profile: Any) -> set[str]:
    return {f.check for f in profile.findings if not f.passed}


# --- US4-S1 / FR-012: the wired model passes the factory's own judgment --------


def test_wiring_through_the_forge_makes_the_factorys_own_gate_pass_the_model(
    tmp_path: Path,
) -> None:
    """US4-S1: one model, wired through the seam, judged by `evaluate_repo` — the
    same judgment `EpicWorkflow._onboard_target` runs before every epic.

    The control is built in: the *same* model is judged before the wiring and
    fails on the three questions wiring exists to answer, so a judgment that
    ignored the repository could not produce both verdicts.

    What edit would make this fail: have `apply_landing_policy` report its acts
    without issuing them, or require checks that are not the declared gates —
    both leave the profile failing while every step still says `applied`.
    """
    repo = build_target_repo(tmp_path / "target")
    model = FakeGitHub(owner_repo="acme/app", default_branch="main")

    unready = onboard_target_repo(github_forge_over(model, repo), str(repo))

    assert unready.passed is False
    assert failing(unready) >= {"gated_landing", "autonomous_landing", "landing_title"}

    steps = github_forge_over(model, repo).apply_landing_policy("main", FIXTURE_GATES)

    ready = onboard_target_repo(github_forge_over(model, repo), str(repo))

    assert ready.passed is True, [f for f in ready.findings if not f.passed]
    assert sorted(ready.required_checks) == sorted(FIXTURE_GATES)

    # The acts are reported too — secondary to the verdict, and asserted as the
    # operator reads them.
    assert [step.status for step in steps] == [APPLIED, APPLIED]


def test_a_forge_that_never_heard_of_github_is_wired_and_judged_the_same_way(
    tmp_path: Path,
) -> None:
    """Wiring is an operation *on the seam*: a forge with no notion of a merge
    queue, a ruleset or a repository's visibility is wired by the same call and
    judged by the same `evaluate_repo`.

    Stated honestly, because a test that overclaims is worse than none: the
    implementation exercised on the wiring side here is the *model's*, so what
    this pins is that the seam's wiring contract and the shared judgment agree
    about what a wired repository is — answer one of Q2, Q3, Q5 and not the
    others and the profile fails. That a non-GitHub forge is reached by
    production code is `ergane init --wire`'s claim, asserted in this file's CLI
    test, and the GitHub implementation's own round trip is the test above.

    What edit would make this fail: drop `lands_without_a_human` from what
    wiring asserts, or have `evaluate_repo` stop asking one of the three.
    """
    repo = build_target_repo(tmp_path / "target")
    model = RepositoryModel(address="acme/app", default_branch="main")

    assert model.visibility == "", "the model must have no notion of visibility"
    assert onboard_target_repo(FakeForge(model), str(repo)).passed is False

    steps = FakeForge(model).apply_landing_policy("main", FIXTURE_GATES)

    profile = onboard_target_repo(FakeForge(model), str(repo))

    assert profile.passed is True, [f for f in profile.findings if not f.passed]
    assert sorted(profile.required_checks) == sorted(FIXTURE_GATES)
    assert [step.status for step in steps] == [APPLIED]
    assert model.mutations == ["landing policy on main"]


# --- US4-S2: a second run reports every act satisfied and mutates nothing ------


def test_a_second_wiring_run_reports_every_act_satisfied_and_changes_nothing(
    tmp_path: Path,
) -> None:
    """US4-S2, asserted against the *repository model's* mutation list.

    It could not be asserted through `tests/fake_gh.py`, and the reason is the
    story: that fake scans its expectations from index 0 on every call and
    consumes none, so the first match answers a command forever, a second
    identical command is unreachable, and an idempotence claim made through it
    is unfalsifiable by construction
    (`ci/the-scripted-gh-fake-never-consumes-an-expectation`). `FakeGitHub` is a
    repository as state, so a second write is reachable — and would show up here
    three ways: a mutating call, a changed snapshot, an `applied` step.

    What edit would make this fail: drop `_ruleset_satisfies`'s comparison, or
    PATCH the squash title without reading it first — either re-writes a setting
    that already said what it was asked to say.
    """
    repo = build_target_repo(tmp_path / "target")
    model = FakeGitHub(owner_repo="acme/app", default_branch="main")

    github_forge_over(model, repo).apply_landing_policy("main", FIXTURE_GATES)
    assert model.mutations(), "the first run must actually have wired something"

    before = model.snapshot()
    model.calls.clear()

    steps = github_forge_over(model, repo).apply_landing_policy("main", FIXTURE_GATES)

    assert [step.status for step in steps] == [ALREADY_SATISFIED, ALREADY_SATISFIED]
    assert model.mutations() == []
    assert model.snapshot() == before

    # And the repository the second run left behind is still one the factory
    # will dispatch against — "changed nothing" must not mean "unwired it".
    assert onboard_target_repo(github_forge_over(model, repo), str(repo)).passed


def test_the_neutral_forges_second_run_records_no_change_either(
    tmp_path: Path,
) -> None:
    """The same claim one layer up, where the mutation list is the model's own
    and not derived from argv: idempotence is a property of the *operation*, so
    a forge whose acts are not `gh` calls answers it the same way.

    What edit would make this fail: have `RepositoryModel.wire` write before it
    compares, and the second run appends a second entry.
    """
    repo = build_target_repo(tmp_path / "target")
    model = RepositoryModel(address="acme/app", default_branch="main")

    FakeForge(model).apply_landing_policy("main", FIXTURE_GATES)
    steps = FakeForge(model).apply_landing_policy("main", FIXTURE_GATES)

    assert [step.status for step in steps] == [ALREADY_SATISFIED]
    assert model.mutations == ["landing policy on main"]
    assert onboard_target_repo(FakeForge(model), str(repo)).passed
