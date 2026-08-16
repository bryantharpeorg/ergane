"""049-US2: the readiness questions are forge-neutral, and D-007 is GitHub's.

US1 moved *where* the facts come from. This is where the questions themselves
stop being one forge's. `evaluate_repo` asks Q1–Q5 — can the factory reach this
repository, does the branch refuse a landing until named checks pass, which
checks, will it land without a human, will the landing commit take the
proposal's title — and every answer arrives on `RepositoryDescription` or
`LandingPolicy`. GitHub's rule that a repository must be public (D-007) is now
GitHub's own answer, contributed as a finding the shared judgment appends
without knowing what it means.

Every test answers "what edit would make this fail?" in its own docstring,
because the defect that has cost this repository most is a test that cannot
fail. The mutation transcripts proving each answer are committed at
`specs/049-forge-seam/evidence/us2-mutations.md`.

Two fakes appear here and neither is a call recorder (FR-004, trap 3).
`RepositoryModel` (`tests/fake_forge.py`) is a repository on a forge that never
heard of GitHub; `GithubRepositoryModel` below is GitHub's own state, and the
client over it serves reads from that state so a changed field changes what
`GithubForge` answers. No assertion here is about which calls were made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factory.activities.merge_activities import onboard_target_repo
from factory.mergequeue.forge import LandingPolicy, RepositoryDescription
from factory.mergequeue.github_forge import GithubForge
from factory.mergequeue.models import Finding
from factory.mergequeue.onboard import InitFacts, evaluate_repo
from tests.fake_forge import FakeForge, RepositoryModel
from tests.target_repo import build_target_repo

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The judgment under test, and the implementation D-007 moved into.
JUDGMENT = REPO_ROOT / "factory" / "mergequeue" / "onboard.py"
GITHUB_IMPLEMENTATION = REPO_ROOT / "factory" / "mergequeue" / "github_forge.py"

#: The fixture repository declares exactly these gates.
FIXTURE_GATES = ("lint", "test", "typecheck")

#: A title source spelled the way a forge that is not GitHub would spell it. It
#: is evidence in a remedy and never something the judgment decides from — the
#: decision is the boolean beside it.
NEUTRAL_TITLE_SOURCE = "proposal-title"

#: The remedy an operator reads today when their repository is private, verbatim
#: from `onboard.py` before this story moved it. Asserted as a literal because
#: "the same remedy" is the acceptance criterion, not "a similar one".
D007_REMEDY = (
    "repo is 'PRIVATE'; the merge queue is available on any plan only for "
    "public repos — make the repo public, or dispatch against a public target "
    "(D-007)"
)


def _finding(profile: Any, check: str) -> Finding:
    for finding in profile.findings:
        if finding.check == check:
            return finding
    raise AssertionError(
        f"no finding for {check!r}; got {[f.check for f in profile.findings]}"
    )


def _failing(profile: Any) -> set[str]:
    return {f.check for f in profile.findings if not f.passed}


def _ready_model() -> RepositoryModel:
    """A repository that answers every neutral question well — and says nothing
    at all about who can see it, because its forge has no such notion."""
    model = RepositoryModel(address="acme/app", default_branch="main")
    model.gate_on("main", FIXTURE_GATES, title_source=NEUTRAL_TITLE_SOURCE)
    return model


# --- US2-S1 / SC-002: a forge with no notion of visibility passes -------------


def test_a_forge_that_reports_no_visibility_at_all_passes_readiness(
    tmp_path: Path,
) -> None:
    """The story's whole claim. A repository that gates on named checks, lands
    with no human, requires exactly the declared gates and titles the landing
    from the proposal is ready — and it never said whether anyone can see it.

    What edit would make this fail: put the visibility check back into the
    shared judgment. A model whose `visibility` is `''` then fails a check it
    cannot answer, which is what a target on another forge faces today.
    """
    repo = build_target_repo(tmp_path / "target")
    model = _ready_model()

    assert model.visibility == "", "the model must have no notion of visibility"

    profile = onboard_target_repo(FakeForge(model), str(repo))

    assert profile.passed is True, [f for f in profile.findings if not f.passed]
    assert {f.check for f in profile.findings} == {
        "gated_landing",
        "autonomous_landing",
        "factory_yaml",
        "landing_title",
        "gate_check:lint",
        "gate_check:test",
        "gate_check:typecheck",
    }
    assert sorted(profile.required_checks) == list(FIXTURE_GATES)


# --- US2-S1 / SC-003: the control, so the question is shown to decide ---------


def test_the_same_model_with_its_gating_removed_fails_readiness(
    tmp_path: Path,
) -> None:
    """SC-003's control, and trap 4's answer for the test above: one model, one
    difference, two verdicts. Without it, "the neutral repository passes" is
    consistent with a judgment that passes everything.

    What edit would make this fail: have `evaluate_repo` read Q2 from anything
    but the forge's landing policy — a hardcoded `True`, or GitHub's queue flag
    — and the ungated model passes exactly as the gated one does.
    """
    repo = build_target_repo(tmp_path / "target")
    model = _ready_model()

    assert onboard_target_repo(FakeForge(model), str(repo)).passed is True

    model.branches.clear()  # the repository stops gating; nothing else changes.

    ungated = onboard_target_repo(FakeForge(model), str(repo))

    assert ungated.passed is False
    assert "gated_landing" in _failing(ungated)
    gating = _finding(ungated, "gated_landing")
    assert "main" in gating.detail
    assert gating.detail.strip() and gating.detail != gating.check


# --- US2-S4: Q2 and Q3 are separately answerable and separately actionable ----


def test_a_forge_that_gates_but_waits_for_a_human_fails_a_distinct_finding(
    tmp_path: Path,
) -> None:
    """A branch that runs the gates and then waits for a click is not a branch
    this factory can land through (D-024) — and telling an operator "gating is
    wrong" when gating is right is a riddle, not a report.

    What edit would make this fail: fold Q3 back into Q2 (one finding for both,
    as GitHub's merge queue happens to answer them), and the distinct
    `autonomous_landing` finding disappears while `gated_landing` starts lying.
    """
    repo = build_target_repo(tmp_path / "target")
    model = RepositoryModel(address="acme/app", default_branch="main")
    model.gate_on(
        "main",
        FIXTURE_GATES,
        lands_without_a_human=False,
        title_source=NEUTRAL_TITLE_SOURCE,
    )

    profile = onboard_target_repo(FakeForge(model), str(repo))

    assert profile.passed is False
    assert _failing(profile) == {"autonomous_landing"}

    gating = _finding(profile, "gated_landing")
    human = _finding(profile, "autonomous_landing")
    assert gating.passed is True
    assert human.passed is False
    assert human.detail != gating.detail
    assert "human" in human.detail


# --- US2-S2 / FR-007: D-007 is authored by the GitHub implementation ----------


@dataclass
class GithubRepositoryModel:
    """GitHub's own state for one repository — the thing the client below reads.

    A model rather than a script of expected calls: change `visibility` and the
    reads change, which is what makes the assertions below about the repository
    instead of about the traffic (`tests/fake_gh.py` cannot support that claim —
    `ci/the-scripted-gh-fake-never-consumes-an-expectation`).
    """

    name_with_owner: str = "acme/app"
    visibility: str = "PUBLIC"
    default_branch: str = "main"
    squash_merge_commit_title: str | None = "PR_TITLE"
    queue_enabled: bool = True
    required_checks: tuple[str, ...] = FIXTURE_GATES


@dataclass
class GithubClientOverModel:
    """The `GhClient` surface `GithubForge` uses, served from the model."""

    model: GithubRepositoryModel = field(default_factory=GithubRepositoryModel)

    def repo_view(self) -> dict[str, Any]:
        return {
            "nameWithOwner": self.model.name_with_owner,
            "visibility": self.model.visibility,
            "defaultBranchRef": {"name": self.model.default_branch},
        }

    def merge_settings(self, owner_repo: str) -> dict[str, Any]:
        return {"squash_merge_commit_title": self.model.squash_merge_commit_title}

    def rules_for_branch(self, owner_repo: str, branch: str) -> list[dict[str, Any]]:
        if not self.model.queue_enabled:
            return []
        return [
            {"type": "merge_queue", "parameters": {}},
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [
                        {"context": check} for check in self.model.required_checks
                    ]
                },
            },
        ]

    def classic_branch_protection(self, owner_repo: str, branch: str) -> dict[str, Any]:
        return {}


def test_the_github_forge_authors_the_d007_finding_for_a_private_repository(
    tmp_path: Path,
) -> None:
    """FR-007: the rule that a repository must be public did not soften and did
    not move to advice — it moved to the implementation where it is true, with
    the remedy an operator reads today, character for character.

    What edit would make this fail: stop contributing the finding from
    `describe_repository`, or reword the remedy. The public case beside it is
    the control: one implementation, one field changed, two verdicts.
    """
    repo = build_target_repo(tmp_path / "target")
    private = GithubRepositoryModel(visibility="PRIVATE")
    forge = GithubForge(GithubClientOverModel(private))

    assert forge.describe_repository().findings == (
        Finding("visibility", False, D007_REMEDY),
    )

    profile = onboard_target_repo(forge, str(repo))

    assert profile.passed is False
    assert profile.findings[0] == Finding("visibility", False, D007_REMEDY)
    assert _failing(profile) == {"visibility"}

    # The control: the same implementation, one field changed.
    public = GithubForge(GithubClientOverModel(GithubRepositoryModel()))
    passing = onboard_target_repo(public, str(repo))

    assert passing.passed is True, [f for f in passing.findings if not f.passed]
    assert passing.findings[0] == Finding("visibility", True, "repo is public")


# --- US2-S3 / FR-006: the judgment names no forge's own configuration ---------

#: Words that belong to GitHub's configuration rather than to readiness. Matched
#: against lowercased source, so `PR_TITLE` is `pr_title`.
FORGE_OWNED_VOCABULARY = (
    "merge queue",
    "merge_queue",
    "pr_title",
    "squash",
    "visibility",
)

#: Tokens that prove the scan read the judgment and not an empty string. Trap 4:
#: `tests/test_final_sweep.py:644` is here because a sweep over nothing passes
#: forever.
JUDGMENT_LANDMARKS = ("def evaluate_repo(", "gate_check:", "unknown_check:")


def _forge_owned_words_in(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8").lower()
    assert source.strip(), f"{path} read as empty — the scan proves nothing"
    return sorted({word for word in FORGE_OWNED_VOCABULARY if word in source})


def test_the_shared_judgment_names_no_forges_own_configuration() -> None:
    """US2-S3, read off the module's source so a later edit cannot quietly put
    one back. A finding slug is a string, and a string reintroduced in six
    months would pass every behavioural test in this file.

    Its own anti-vacuity control is the second assertion: the *same* scanner
    over `github_forge.py` must find every word. A scan that read nothing, a
    ban list that emptied, or a matcher that stopped matching fails there before
    it can pass here.

    What edit would make this fail: name a finding `merge_queue` again, or
    quote `squash_merge_commit_title` in a remedy the shared judgment writes.
    """
    assert FORGE_OWNED_VOCABULARY, "an empty ban list forbids nothing"

    judgment = JUDGMENT.read_text(encoding="utf-8")
    for landmark in JUDGMENT_LANDMARKS:
        assert landmark in judgment, f"{JUDGMENT} is not the module this expects"

    assert _forge_owned_words_in(JUDGMENT) == []
    assert _forge_owned_words_in(GITHUB_IMPLEMENTATION) == sorted(
        FORGE_OWNED_VOCABULARY
    )

    # And D-007 is decided on exactly one side of the seam. Its *text* is
    # asserted where text belongs — off the finding, in the test above; a source
    # scan only has to say which module authors it, since the string is built
    # from an f-string no `in` check can match verbatim.
    assert "(D-007)" in GITHUB_IMPLEMENTATION.read_text(encoding="utf-8")
    assert "D-007" not in judgment


# --- US2-S5 / FR-008: tree and host checks stay in the shared judgment --------


def test_the_checks_a_tree_or_a_host_owns_stay_in_the_shared_judgment() -> None:
    """FR-008 stated as output: a forge with no GitHub vocabulary at all still
    gets manifest validity, gate↔check parity and 034's local facts, because
    none of them is a forge question. `tests/test_ergane_init_check.py:441`
    holds the authorship half — that no module but `onboard.py` builds them —
    and this holds the production half.

    What edit would make this fail: move any of these behind the seam, and they
    vanish for a forge that does not contribute them.
    """
    profile = evaluate_repo(
        repo="acme/app",
        reading=RepositoryDescription(address="acme/app", default_branch="main"),
        policy=LandingPolicy(
            branch="main",
            gates_on_named_checks=True,
            required_checks=("test", "judge"),
            lands_without_a_human=True,
            landing_title_from_proposal=True,
            landing_title_source=NEUTRAL_TITLE_SOURCE,
        ),
        declared_gates=("test",),
        init_facts=InitFacts(
            repo_root="/repos/app",
            gitignore="/repos/app/.gitignore",
            registry_path="/state/ergane/repos.json",
            registry_slug="app",
            landing_branch="main",
            landing_branch_exists=True,
            control_plane=(Finding("temporal", True, "namespace exists"),),
            schedule_id="ergane-roadmap-app",
            schedule_present=True,
        ),
    )

    checks = [f.check for f in profile.findings]
    assert "factory_yaml" in checks
    assert "gate_check:test" in checks
    assert "unknown_check:judge" in checks
    for slug in (
        "runtime_root_ignored",
        "registry_entry",
        "landing_branch",
        "control_plane",
        "roadmap_schedule",
    ):
        assert slug in checks, slug
    assert _failing(profile) == {"unknown_check:judge"}
