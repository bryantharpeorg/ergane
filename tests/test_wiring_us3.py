"""US3 of epic 059: the merge-queue eligibility rule is written down as a matrix.

The implementation already lives in `factory.mergequeue.wiring`; this story
adds the documentation that makes the rule re-checkable and the tests that make
a drift in the code fail the documented claim.
"""

from __future__ import annotations

import pytest

import factory.mergequeue.wiring as wiring


# T020 [P] [US3] — the module docstring quotes GitHub's availability sentence.


GITHUB_AVAILABILITY_SENTENCE = (
    "Pull request merge queues are available in any public repository owned by "
    "an organization, or in private repositories owned by organizations using "
    "GitHub Enterprise Cloud."
)


def test_module_documentation_quotes_github_availability_sentence() -> None:
    """US3-S2 / FR-009: the module docstring contains GitHub's documented
    availability sentence verbatim, so the claim can be re-checked against the
    vendor rather than this repository's memory of it.
    """
    assert GITHUB_AVAILABILITY_SENTENCE in wiring.__doc__


# T021 [P] [US3] — the eligibility decision is one named predicate, driven across
# all four cells.


@pytest.mark.parametrize(
    ("is_in_organization", "visibility", "expected"),
    [
        (True, "PUBLIC", True),
        (False, "PUBLIC", False),
        (True, "PRIVATE", False),
        (False, "PRIVATE", False),
    ],
    ids=[
        "org-public-eligible",
        "user-public-not-eligible",
        "org-private-not-eligible",
        "user-private-not-eligible",
    ],
)
def test_repository_can_host_merge_queue_predicate(
    is_in_organization: bool,
    visibility: str,
    expected: bool,
) -> None:
    """US3-S1 / FR-009: eligibility is a single named predicate over the two
    properties, and it returns the expected answer for every cell of the matrix.
    """
    assert wiring.repository_can_host_merge_queue(
        is_in_organization=is_in_organization,
        visibility=visibility,
    ) is expected


def test_predicate_inverts_detectably() -> None:
    """SC-004: a predicate that refuses every cell, or accepts every cell, fails
    at least one parametrized assertion above. This explicit assertion locks the
    positive cell so the test cannot pass on a universally-refusing predicate.
    """
    assert wiring.repository_can_host_merge_queue(is_in_organization=True, visibility="PUBLIC") is True
    assert wiring.repository_can_host_merge_queue(is_in_organization=False, visibility="PUBLIC") is False
    assert wiring.repository_can_host_merge_queue(is_in_organization=True, visibility="PRIVATE") is False
    assert wiring.repository_can_host_merge_queue(is_in_organization=False, visibility="PRIVATE") is False
