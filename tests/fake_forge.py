"""A fake forge that is a *model of a repository*, never a call recorder (FR-004).

`RepositoryModel` is the repository: its address, its branches, and each
branch's landing policy. `FakeForge` serves every read out of that state, so
changing the model changes what the factory's own `evaluate_repo` says about it
— which is why the tests assert on the *judgment of the model*, never on which
calls were made.

**Why not `tests/fake_gh.py`.** Its match loop consumes nothing, so the first
match answers a command forever and an idempotence claim made through it cannot
fail — the open finding `ci/the-scripted-gh-fake-never-consumes-an-expectation`.
Nothing here is built on it or shaped like it, and it is not repaired here
either: seven unrelated modules ride it, so that is its own work (trap 3). The
bar this copies is `FakeGitHub` in `tests/test_ergane_init_wiring.py`: mutable
state, reads derived from it, the factory's own reader judging the object.

`gate_on` is the repository's own act rather than a test helper: 049's US4 wires
a repository by issuing exactly that change, and must mutate this model rather
than get a scripted answer back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from factory.mergequeue.forge import (
    ForgeError,
    LandingPolicy,
    RepositoryDescription,
)
from factory.mergequeue.models import Finding


@dataclass
class BranchPolicy:
    """What one branch does to a proposal; the default is a branch nobody
    configured — gates on nothing, lands on nothing, says nothing."""

    gates_on_named_checks: bool = False
    required_checks: tuple[str, ...] = ()
    lands_without_a_human: bool = False
    landing_title_from_proposal: bool = False
    landing_title_source: str | None = None


@dataclass
class RepositoryModel:
    """One repository, as mutable state — the thing the fake forge reads.

    `visibility` defaults to `""`: *this forge has no notion of who can see a
    repository*. US2 is where a model in that shape passes readiness; in US1 the
    shared judgment still asks GitHub's questions, so a model must answer them.
    `unreachable` is what the forge says when it cannot read the repository.
    """

    address: str = "acme/app"
    default_branch: str = "main"
    visibility: str = ""
    findings: tuple[Finding, ...] = ()
    unreachable: str = ""
    branches: dict[str, BranchPolicy] = field(default_factory=dict)

    def gate_on(
        self,
        branch: str,
        checks: tuple[str, ...],
        *,
        lands_without_a_human: bool = True,
        title_source: str | None = None,
    ) -> None:
        """Make `branch` refuse a landing until exactly `checks` pass."""
        self.branches[branch] = BranchPolicy(
            gates_on_named_checks=True,
            required_checks=tuple(checks),
            lands_without_a_human=lands_without_a_human,
            landing_title_from_proposal=title_source is not None,
            landing_title_source=title_source,
        )

    def policy_for(self, branch: str) -> BranchPolicy:
        """The branch's policy, or the unconfigured default — never a mutation."""
        return self.branches.get(branch) or BranchPolicy()


class FakeForge:
    """A forge whose answers are derived from `model`, and from nothing else."""

    def __init__(self, model: RepositoryModel) -> None:
        self.model = model

    def describe_repository(self) -> RepositoryDescription:
        if self.model.unreachable:
            raise ForgeError(
                "FORGE_NOT_FOUND", "the fake forge cannot read this repository",
                self.model.unreachable,
            )
        return RepositoryDescription(
            address=self.model.address,
            default_branch=self.model.default_branch,
            visibility=self.model.visibility,
            findings=tuple(self.model.findings),
        )

    def landing_policy(self, branch: str) -> LandingPolicy:
        policy = self.model.policy_for(branch)
        return LandingPolicy(
            branch=branch,
            gates_on_named_checks=policy.gates_on_named_checks,
            required_checks=policy.required_checks,
            lands_without_a_human=policy.lands_without_a_human,
            landing_title_from_proposal=policy.landing_title_from_proposal,
            landing_title_source=policy.landing_title_source,
        )
