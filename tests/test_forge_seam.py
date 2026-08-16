"""049-US1: onboarding reads a repository through a forge, not through `gh`.

Every test answers "what edit would make this fail?" in its own docstring,
because the defect that has cost this repository most is a test that cannot
fail. The mutation transcripts proving each answer are committed at
`specs/049-forge-seam/evidence/us1-mutations.md`.

Scope fence: this moves *where the facts come from*, and does not re-ask the
readiness questions — `evaluate_repo`'s findings stay byte-identical, which is
what makes the move checkable. Byte identity for a GitHub target is carried by
the nine `test_validate_target_repo_*` tests in `tests/test_merge_activities.py`,
which pass with no assertion changed; added here is the one thing they assert
only by substring — the remedies, word for word.
"""

from __future__ import annotations

import dataclasses
import inspect
import tomllib
from pathlib import Path

import pytest

from factory.activities.merge_activities import onboard_target_repo
from factory.mergequeue.forge import (
    DEFAULT_FORGE,
    Forge,
    LandingPolicy,
    RepositoryDescription,
    UnknownForgeError,
    register_forge,
    registered_forges,
    resolve_forge,
)
from factory.mergequeue.gh import GhClient
from factory.mergequeue.github_forge import GithubForge
from factory.mergequeue.models import Finding
from tests.fake_forge import FakeForge, RepositoryModel
from tests.fake_gh import FakeGh
from tests.target_repo import build_target_repo

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The reading half of the seam, and nothing else. US3 adds the landing half and
#: US4 the wiring one; both extend this set rather than replacing it.
READING_OPERATIONS = {"describe_repository", "landing_policy"}

#: Verbs that would mean a forge had started deciding. Classifying, settling and
#: judging stay factory-side (FR-001) — the rule `factory/notify/adapter.py`
#: states for the messenger seam.
DECIDING_VERBS = ("classify", "verdict", "settle", "escalat", "judge", "retry")

#: Words that belong to one forge. No operation and no record field may be named
#: with any of them — that is the difference between a seam and a rename
#: (D-046 §3). Matched as whole `snake_case` words, so `proposal` is not `pr`.
#: `visibility` is deliberately absent: many forges report who can see a
#: repository, and what belongs to GitHub is the *rule* that it must be public
#: (D-007), which US2 moves into the GitHub implementation.
FORGE_NATIVE_WORDS = {
    "queue", "mergequeue", "squash", "gh", "github", "pr", "pull",
    "automerge", "ruleset", "rulesets", "mergestatestatus", "draft",
}

#: A second registration, made at *import* time so the conformance
#: parametrization below is a list of two rather than 041's hardcoded list of one
#: (`ci/the-adapter-conformance-suite-is-a-hardcoded-list-of-one`). It is enrolled
#: by having registered — the property FR-005 asks for — and nobody edited the
#: parametrization to admit it.
CONFORMANCE_PROBE = "conformance-probe"
register_forge(CONFORMANCE_PROBE, lambda **seams: FakeForge(RepositoryModel()))

FORGE_NAMES = registered_forges()


def public_methods(cls: type) -> set[str]:
    """Every public operation a class declares in its own body."""
    return {
        name
        for name, value in vars(cls).items()
        if not name.startswith("_") and callable(value)
    }


def declared_names() -> list[str]:
    """Every name the seam declares: its operations and its records' fields."""
    names = sorted(public_methods(Forge))
    for record in (RepositoryDescription, LandingPolicy):
        names.extend(f.name for f in dataclasses.fields(record))
    return names


# --- US1-S1 / FR-001: the interface declares the reading half, and no verdict --


def test_the_forge_protocol_declares_exactly_the_reading_operations() -> None:
    """A third operation, a renamed one, or one returning a forge's own payload
    fails here: an operation answering with raw JSON would have moved the
    coupling one call deeper instead of removing it."""
    assert public_methods(Forge) == READING_OPERATIONS

    returns = [
        inspect.get_annotations(op, eval_str=True)["return"]
        for op in (Forge.describe_repository, Forge.landing_policy)
    ]
    assert returns == [RepositoryDescription, LandingPolicy]


def test_nothing_the_seam_declares_is_spelled_in_one_forges_vocabulary() -> None:
    """Trap 1, made structural: renaming is not seaming.

    `merge_queue_enabled` and `squash_merge_commit_title` would move GitHub's
    vocabulary behind an interface and remove nothing. Rename any field back to
    one of those and this fails — which is the mutation that proves it.
    """
    spelled = sorted(
        name
        for name in declared_names()
        if set(name.lower().split("_")) & FORGE_NATIVE_WORDS
    )

    assert spelled == [], (
        f"the seam spells {spelled} — a forge-native name behind a neutral "
        "interface has moved the coupling, not removed it (D-046 §3)"
    )
    assert declared_names(), "the seam declared nothing to check"


# --- US1-S1 / FR-005: the conformance suite enrols every registered forge ------


def test_the_conformance_parametrization_is_not_empty_and_names_two_forges() -> None:
    """The anti-vacuity guard (trap 4), and the reason FR-005 exists: a suite
    parametrized over a registry nothing populated passes with zero cases and
    asserts nothing, and 041's is the literal `["telegram"]`. This asserts the
    parametrization really enrolled two forges, the second by registering."""
    assert DEFAULT_FORGE in FORGE_NAMES
    assert CONFORMANCE_PROBE in FORGE_NAMES
    assert len(FORGE_NAMES) >= 2, FORGE_NAMES


@pytest.mark.parametrize("name", FORGE_NAMES)
def test_every_registered_forge_exposes_exactly_the_reading_operations(
    name: str,
) -> None:
    """Registration is enrolment: a forge added later is checked without an edit."""
    forge = resolve_forge(name, repo_path="/srv/target")

    assert isinstance(forge, Forge)
    assert public_methods(type(forge)) == READING_OPERATIONS


@pytest.mark.parametrize("name", FORGE_NAMES)
def test_no_registered_forge_decides_anything(name: str) -> None:
    """FR-001, read off each forge class's own source — the class's and not its
    module's, since a module may hold factory-side helpers precisely because
    they are not the forge."""
    source = inspect.getsource(type(resolve_forge(name, repo_path="/srv/target")))

    found = [verb for verb in DECIDING_VERBS if verb in source]
    assert not found, (
        f"the {name} forge names {found}; classifying, settling and judging stay "
        "factory-side whatever forge answered (FR-001)"
    )


# --- US1-S4 / FR-002: an unregistered name raises rather than defaulting -------


def test_an_unregistered_forge_name_raises_rather_than_defaulting() -> None:
    """A deployment that asked for one forge and silently got another would land
    somewhere nobody looked. Mutation: make `resolve_forge` fall back to
    `DEFAULT_FORGE` and this fails on the missing raise."""
    with pytest.raises(UnknownForgeError) as excinfo:
        resolve_forge("bitbucket", repo_path="/srv/target")

    message = str(excinfo.value)
    assert "bitbucket" in message
    assert DEFAULT_FORGE in message


# --- US1-S3 / FR-004: the shared judgment judges a model of a repository ------


def test_the_shared_judgment_judges_a_forge_that_never_spawns_gh(
    tmp_path: Path,
) -> None:
    """The seam's whole claim: `evaluate_repo` judged a repository no `gh` was
    ever spawned against, and the verdict followed the *model*.

    The assertion is the profile, never a call log; the control is built in —
    one judgment sees one forge three times and says three things, so a judgment
    ignoring the forge could not produce them.
    """
    repo = build_target_repo(tmp_path / "target")
    model = RepositoryModel(address="acme/app", default_branch="main")
    forge = FakeForge(model)

    unready = onboard_target_repo(forge, str(repo))

    assert unready.passed is False
    assert {f.check for f in unready.findings if not f.passed} >= {
        "visibility", "merge_queue", "squash_title",
    }

    # The repository changes; nothing about the judgment does.
    model.visibility = "PUBLIC"
    model.gate_on("main", ("lint", "test", "typecheck"), title_source="PR_TITLE")

    ready = onboard_target_repo(forge, str(repo))

    assert ready.passed is True, [f for f in ready.findings if not f.passed]
    assert ready.repo == "acme/app"
    assert sorted(ready.required_checks) == ["lint", "test", "typecheck"]

    # Q1's failing answer travels as data through the seam, not as a `GhError`.
    model.unreachable = "no such repository"
    unreadable = onboard_target_repo(forge, str(repo))
    assert unreadable.passed is False
    read = next(f for f in unreadable.findings if f.check == "repo_read")
    assert "no such repository" in read.detail


def test_a_forge_contributes_its_own_findings_ahead_of_the_shared_ones(
    tmp_path: Path,
) -> None:
    """FR-007's carriage, built in US1 and spent in US2.

    A forge answers about facts only it has; the shared judgment appends them
    without knowing what they mean. They read first so the report an operator
    already knows how to read keeps its shape when US2 moves D-007's visibility
    finding across the seam.

    Mutation: stop passing `RepositoryDescription.findings` into `evaluate_repo`
    and this fails — the finding disappears from the profile.
    """
    repo = build_target_repo(tmp_path / "target")
    model = RepositoryModel(findings=(Finding("forge_note", False, "only I know"),))

    profile = onboard_target_repo(FakeForge(model), str(repo))

    assert profile.findings[0] == Finding("forge_note", False, "only I know")
    assert profile.passed is False


# --- US1-S2 / FR-003: the GitHub target's judgment is unchanged ---------------


def test_the_github_forge_carries_todays_remedies_word_for_word(
    tmp_path: Path,
) -> None:
    """SC-001, where the existing suite only checks by substring: a failing
    GitHub target reads exactly as it did before the seam, remedy included.
    Details rather than slugs — a migration that kept the check names and
    reworded what an operator must do would still have changed the judgment."""
    repo = build_target_repo(tmp_path / "target")
    fake = FakeGh()
    fake.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={"nameWithOwner": "OWNER/REPO", "visibility": "PRIVATE",
                 "defaultBranchRef": {"name": "main"}},
    )
    fake.expect_json("api", "repos/OWNER/REPO",
                     payload={"squash_merge_commit_title": "COMMIT_OR_PR_TITLE"})
    fake.expect_json(
        "api", "repos/OWNER/REPO/rules/branches/main",
        payload=[{"type": "merge_queue", "parameters": {
            "required_status_checks": [{"context": "lint"}, {"context": "test"},
                                       {"context": "typecheck"}]}}],
    )

    # Built from its registered name, not constructed here (FR-002).
    forge = resolve_forge(repo_path=str(repo))
    assert isinstance(forge, GithubForge)
    forge = GithubForge(GhClient(repo=str(repo), runner=fake))

    profile = onboard_target_repo(forge, str(repo))

    assert profile.passed is False
    details = {f.check: f.detail for f in profile.findings}
    assert details["visibility"] == (
        "repo is 'PRIVATE'; the merge queue is available on any plan only for "
        "public repos — make the repo public, or dispatch against a public "
        "target (D-007)"
    )
    assert details["squash_title"] == (
        "squash_merge_commit_title is 'COMMIT_OR_PR_TITLE'; observed value was "
        "'COMMIT_OR_PR_TITLE' — run `gh api -X PATCH repos/OWNER/REPO -f "
        "squash_merge_commit_title=PR_TITLE`"
    )


# --- T011 / trap 14: three doors moved, and the proof each old one is gone ----


def test_only_the_github_forge_constructs_the_forge_native_client() -> None:
    """The three construction seams — `merge_activities.py`, `workgraph/cli.py`
    and `cli/init.py` — each built a `GhClient` of its own, and a migration that
    moved two would leave a door with no seam and no test noticing.

    Equality against a non-empty literal rather than `assert not offenders`, so a
    glob that stopped matching fails instead of going quiet. Mutation: put
    `GhClient(repo=repo_path)` back into any one of the three and this fails."""
    builders = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "factory").rglob("*.py")
        if "GhClient(" in path.read_text(encoding="utf-8")
    }

    assert builders == {"factory/mergequeue/github_forge.py"}


# --- US1-S5 / FR-018: no new dependency --------------------------------------


def test_the_forge_seam_declares_no_new_dependency() -> None:
    """Constitution III. Pinned as a literal so an addition faces this test."""
    manifest = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert manifest["project"]["dependencies"] == [
        "temporalio", "httpx", "pyyaml", "python-telegram-bot",
    ]
