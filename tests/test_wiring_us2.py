"""US2 of epic 059: the merge-queue precondition refuses before any ruleset call.

Every test drives `wiring.wire_repo` through `FakeGitHub`, the same model the
existing wiring tests use, and asserts against the recorded call list as well
as the refusal message. No live GitHub repository is touched.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from factory.mergequeue import wiring
from factory.mergequeue.gh import GhClient
from tests.test_ergane_init_wiring import FakeGitHub, _Result


# T010 [P] [US2] — one parametrised test over the four cells of the
# owner-type × visibility matrix.


@pytest.mark.parametrize(
    ("is_in_organization", "visibility", "should_refuse", "named_properties"),
    [
        # S3: org-owned public repo — wiring proceeds.
        (True, "PUBLIC", False, []),
        # S1: user-owned public repo — refused, naming organization ownership.
        (False, "PUBLIC", True, ["organization"]),
        # S2: org-owned private repo — refused, naming Enterprise Cloud and Team insufficiency.
        (True, "PRIVATE", True, ["Enterprise Cloud", "Team"]),
        # S4: user-owned private repo — refused, naming both ownership and visibility together.
        (False, "PRIVATE", True, ["organization", "public"]),
    ],
    ids=[
        "org-public-proceeds",
        "user-public-refuses-ownership",
        "org-private-refuses-plan",
        "user-private-refuses-both",
    ],
)
def test_owner_and_visibility_matrix(
    is_in_organization: bool,
    visibility: str,
    should_refuse: bool,
    named_properties: list[str],
) -> None:
    """US2-S1..S4: the matrix of owner type and visibility, including the passing cell."""
    owner_repo = "acme/app" if is_in_organization else "user/app"
    github = FakeGitHub(
        owner_repo=owner_repo,
        visibility=visibility,
        is_in_organization=is_in_organization,
    )
    client = GhClient(repo="/srv/target", runner=github)

    if should_refuse:
        with pytest.raises(wiring.WiringRefused) as raised:
            wiring.wire_repo(client, landing_branch="main", gates=["test"])
        message = str(raised.value)
        for prop in named_properties:
            assert prop in message, f"expected {prop!r} in refusal: {message}"
        # No ruleset call was issued for a refused repo.
        assert not any(
            c[:1] == ("api",) and "rulesets" in c for c in github.calls
        ), "ruleset call appeared for a refused repository"
    else:
        steps = wiring.wire_repo(client, landing_branch="main", gates=["test"])
        assert any(step.name == "merge queue" for step in steps)


# T011 [P] [US2] — the private-repo remedy wording (trap 4, SC-003).


def test_private_repo_remedy_names_enterprise_cloud_and_negates_team() -> None:
    """US2-S2: the remedy names GitHub Enterprise Cloud and says Team is insufficient."""
    github = FakeGitHub(owner_repo="acme/app", visibility="PRIVATE")
    client = GhClient(repo="/srv/target", runner=github)

    with pytest.raises(wiring.WiringRefused) as raised:
        wiring.wire_repo(client, landing_branch="main", gates=["test"])

    message = str(raised.value)
    assert "Enterprise Cloud" in message
    assert "Team" in message
    # Team must appear only as a negation / insufficiency, never as a recommendation.
    assert "Team is not sufficient" in message or "GitHub Team does not" in message


# T012 [P] [US2] — repo_view requests isInOrganization and no extra gh call is made.


def test_repo_view_requests_isinorganization_and_no_extra_call() -> None:
    """US2-S5: owner type comes from the same `gh repo view` call, not a second one."""
    github = FakeGitHub(owner_repo="acme/app", visibility="PUBLIC")
    client = GhClient(repo="/srv/target", runner=github)

    wiring.wire_repo(client, landing_branch="main", gates=["test"])

    repo_view_calls = [c for c in github.calls if c[:2] == ("repo", "view")]
    assert len(repo_view_calls) == 1
    assert "isInOrganization" in " ".join(repo_view_calls[0])


# T013 [P] [US2] — ordering: for a refused repo, no rulesets POST appears.


def test_refused_repository_issues_no_ruleset_post() -> None:
    """US2-S1 + trap 6: refusal precedes any ruleset call."""
    github = FakeGitHub(
        owner_repo="user/app", visibility="PUBLIC", is_in_organization=False
    )
    client = GhClient(repo="/srv/target", runner=github)

    with pytest.raises(wiring.WiringRefused):
        wiring.wire_repo(client, landing_branch="main", gates=["test"])

    post_endpoints = [
        c for c in github.calls
        if c[:1] == ("api",) and "-X" in c and c[c.index("-X") + 1] == "POST"
    ]
    assert not any("rulesets" in c for c in post_endpoints)


# T014 [P] [US2] — a refusal still carries the complete manual_steps list.


def test_refusal_carries_complete_manual_steps() -> None:
    """US2-S6: the by-hand path is still complete in every refusal branch."""
    github = FakeGitHub(
        owner_repo="user/app", visibility="PUBLIC", is_in_organization=False
    )
    client = GhClient(repo="/srv/target", runner=github)

    with pytest.raises(wiring.WiringRefused) as raised:
        wiring.wire_repo(client, landing_branch="main", gates=["test"])

    manual = raised.value.manual
    assert any("squash_merge_commit_title=PR_TITLE" in step for step in manual)
    assert any("allow_auto_merge=true" in step for step in manual)
    assert any("Merge queue" in step or "merge queue" in step for step in manual)


# T015 [P] [US2] — repo_view missing isInOrganization refuses naming gh version requirement.


class _FakeGitHubWithoutOrgFlag(FakeGitHub):
    """A `FakeGitHub` whose `repo_view` omits `isInOrganization`, simulating an old `gh`."""

    def __call__(self, argv: Sequence[str], cwd: str) -> Any:
        args = tuple(argv)
        self.calls.append(args)
        if args[:2] == ("repo", "view"):
            return _Result(
                stdout=json.dumps(
                    {
                        "nameWithOwner": self.owner_repo,
                        "visibility": self.visibility,
                        "defaultBranchRef": {"name": self.default_branch},
                    }
                )
            )
        return super().__call__(argv, cwd)


def test_missing_isinorganization_refuses_with_gh_version_message() -> None:
    """Edge: when `gh` does not return `isInOrganization`, the refusal names the gh version requirement."""
    github = _FakeGitHubWithoutOrgFlag(owner_repo="acme/app", visibility="PUBLIC")
    client = GhClient(repo="/srv/target", runner=github)

    with pytest.raises(wiring.WiringRefused) as raised:
        wiring.wire_repo(client, landing_branch="main", gates=["test"])

    message = str(raised.value)
    assert "isInOrganization" in message or "gh version" in message.lower()
