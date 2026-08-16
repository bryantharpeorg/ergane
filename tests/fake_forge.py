"""A fake forge that is a *model of a repository*, never a call recorder (FR-004).

`RepositoryModel` is the repository: its address, its branches, and what each
branch's landing policy is. `FakeForge` serves every read out of that state, so
changing the model changes what the factory's own `evaluate_repo` says about it.
That is the whole point — a test asserts on the *judgment of the model*, not on
which calls were made.

**Why not `tests/fake_gh.py`.** That fake is the open finding
`ci/the-scripted-gh-fake-never-consumes-an-expectation`: its `__call__` scans
its expectation list from index 0 on every invocation and consumes nothing, so
the first match answers a command forever, a second expectation for the same
command is unreachable, and — the sharp consequence — an idempotence claim made
through it cannot fail. Nothing here is built on it or shaped like it (plan
trap 3). It is also not repaired here: seven unrelated test modules ride it, and
that is its own piece of work.

The bar this copies instead is `FakeGitHub` in `tests/test_ergane_init_wiring.py`
— mutable state, reads derived from it, and the factory's own reader judging the
same object.

`gate_on` is the repository's own act rather than a test helper: 049's US4 wires
a repository by issuing exactly that change, and when it does it must mutate
this model rather than get a scripted answer.
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
    """What one branch of the modelled repository does to a proposal.

    The default is the honest default for a repository nobody has configured:
    it gates on nothing, it will not land on its own, and it says nothing about
    where a landing commit's subject comes from.
    """

    gates_on_named_checks: bool = False
    required_checks: tuple[str, ...] = ()
    lands_without_a_human: bool = False
    landing_title_from_proposal: bool = False
    landing_title_source: str | None = None


@dataclass
class RepositoryModel:
    """One repository, as mutable state — the thing the fake forge reads.

    `visibility` defaults to `""`, meaning *this forge has no notion of who can
    see a repository*. That is a real forge shape, and 049's US2 is where a
    model in that shape passes readiness; in US1 the shared judgment still asks
    GitHub's questions, so a model has to answer them to pass.

    `unreachable`, when set, is what the forge says when it cannot read the
    repository at all — Q1's failing answer.
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
