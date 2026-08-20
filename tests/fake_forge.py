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
from typing import Sequence

from factory.mergequeue.forge import (
    ALREADY_SATISFIED,
    APPLIED,
    ForgeError,
    LandingPolicy,
    Proposal,
    RepositoryDescription,
    WiringRefused,
    WiringStep,
)
from factory.mergequeue.models import CheckFailure, Finding, PrSnapshot

#: What this forge calls "the landing takes the proposal's title" — its own
#: spelling, deliberately not GitHub's, so a judgment deciding from the spelling
#: rather than from the answer fails here.
WIRED_TITLE_SOURCE = "proposal-title"


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
    #: US4: why this forge's credentials cannot change this repository. Non-empty
    #: is a forge that refuses every write, before making any of them.
    refuse_writes: str = ""
    #: US4: every change actually made to this repository, in order — the list an
    #: idempotence claim is asserted against. "The wiring ran twice" is a fact
    #: about the caller; "the repository changed twice" is a fact about the
    #: world, and only the second one can fail.
    mutations: list[str] = field(default_factory=list)
    branches: dict[str, BranchPolicy] = field(default_factory=dict)
    #: US3: the proposals offered to this repository. The factory is deferred
    #: through a lambda so `LandingModel` can live at the module's end, where a
    #: diff cannot shadow the two siblings building against it (trap 14).
    landings: "LandingModel" = field(default_factory=lambda: LandingModel())

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

    def wire(self, branch: str, checks: tuple[str, ...]) -> tuple[WiringStep, ...]:
        """US4: the repository's own wiring act — read the state, then write.

        Nothing is written when nothing would change, which is what makes an
        idempotence claim falsifiable here: a caller that wrote unconditionally
        would leave a second entry in `mutations` even though the repository
        already said what it was asked to say.
        """
        desired = BranchPolicy(
            gates_on_named_checks=True,
            required_checks=tuple(checks),
            lands_without_a_human=True,
            landing_title_from_proposal=True,
            landing_title_source=WIRED_TITLE_SOURCE,
        )
        named = ", ".join(checks) or "(nothing declared)"
        if self.branches.get(branch) == desired:
            return (WiringStep(
                "landing policy", ALREADY_SATISFIED,
                f"'{branch}' already gates on exactly: {named}",
            ),)
        self.branches[branch] = desired
        self.mutations.append(f"landing policy on {branch}")
        return (WiringStep(
            "landing policy", APPLIED,
            f"'{branch}' now gates on exactly: {named}, lands with no human, and "
            "titles a landing from the proposal",
        ),)


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

    # --- the wiring half (049-US4) ------------------------------------------

    def apply_landing_policy(
        self, branch: str, required_checks: Sequence[str]
    ) -> tuple[WiringStep, ...]:
        """Make `branch` gate on exactly `required_checks` — or refuse, whole.

        A forge that cannot write refuses before its first act and carries the
        by-hand steps (FR-013), so this repository is never left gating on half
        of what it was asked to gate on.
        """
        if self.model.refuse_writes:
            raise WiringRefused(
                f"this forge cannot change {self.model.address}: "
                f"{self.model.refuse_writes}",
                remedies=(
                    "use an account this forge lets change repository settings",
                ),
                manual=(
                    f"1. make '{branch}' refuse a landing until these pass: "
                    f"{', '.join(required_checks)}",
                    f"2. make '{branch}' complete the landing itself once they do",
                    "3. make a landing commit take the proposal's title",
                ),
            )
        return self.model.wire(branch, tuple(required_checks))

    # --- the landing half (049-US3) -----------------------------------------
    #
    # Same rule: answers derived from `model.landings`, writes changing it, and
    # no call log to assert against — a test that passes because a method was
    # called would pass if the method did nothing.

    def find_proposal(self, head: str) -> Proposal | None:
        found = self.model.landings.by_head(head)
        return None if found is None else Proposal(found.number, found.url)

    def open_proposal(
        self, *, base: str, head: str, title: str, body_file: str
    ) -> Proposal:
        opened = self.model.landings.open(head, self.model.address)
        return Proposal(opened.number, opened.url)

    def request_landing(self, proposal: int, *, declared_method: str = "") -> None:
        state = self.model.landings.require(proposal)
        if self.model.landings.refuse_landing:
            raise ForgeError(
                "FORGE_REFUSED", "this repository will not take a landing request",
                self.model.landings.refuse_landing,
            )
        state.landing_requested = True

    def observe_proposal(self, proposal: int) -> PrSnapshot:
        state = self.model.landings.require(proposal)
        return PrSnapshot(
            state=state.state,
            is_draft=False,
            auto_merge_requested=state.landing_requested,
            # Empty on purpose: this forge never heard of GitHub's status
            # vocabulary, which makes the conflict case a control.
            merge_state_status="",
            merged_at=state.merged_at,
            closed_at=None,
            failing_required_checks=state.failing_checks,
            observed_at=self.model.landings.observed_at,
            in_conflict=state.in_conflict,
        )

    def withdraw_landing(self, proposal: int) -> None:
        self.model.landings.require(proposal).landing_requested = False

    def close_proposal(self, proposal: int, *, note: str) -> None:
        self.model.landings.close(proposal, note=note)

    def failing_check_evidence(
        self, proposal: int, check_names: tuple[str, ...]
    ) -> tuple[CheckFailure, ...]:
        state = self.model.landings.require(proposal)
        base = f"https://forge.invalid/{self.model.address}/proposals/{proposal}"
        return tuple(
            CheckFailure(
                name,
                f"{base}/checks/{name}" if name in state.failing_checks else "",
                state.logs.get(name, ""),
                "" if state.logs.get(name)
                else "log unavailable: the forge kept none for this check",
            )
            for name in check_names
        )


# --- the landing half's model (049-US3) ---------------------------------------


@dataclass
class ProposalState:
    """One proposal offered to this repository, and what became of it."""
    number: int
    url: str
    head: str
    state: str = "OPEN"
    landing_requested: bool = False
    merged_at: str | None = None
    in_conflict: bool = False
    failing_checks: tuple[str, ...] = ()
    logs: dict[str, str] = field(default_factory=dict)
    #: What the last close said. Modelled rather than call-logged (069-US3): a
    #: test asserting `close_proposal` was *called* would pass against a forge
    #: that did nothing, and the note is the half an operator actually reads.
    closing_note: str = ""


@dataclass
class LandingModel:
    """The proposals a repository holds — mutable state, not a script.

    Its methods are *acts*: things a forge or a person does, after which the test
    asks the factory what it makes of the result. `refuse_landing`, when
    non-empty, is a repository that will not take a landing request at all.
    """

    proposals: dict[int, ProposalState] = field(default_factory=dict)
    next_number: int = 1
    refuse_landing: str = ""
    observed_at: str = "2026-08-16T10:05:00Z"

    def open(self, head: str, address: str = "acme/app") -> ProposalState:
        """Offer `head`, reusing the open proposal for it — one landing per head."""
        existing = self.by_head(head)
        if existing is not None:
            return existing
        number = self.next_number
        self.next_number += 1
        self.proposals[number] = ProposalState(
            number, f"https://forge.invalid/{address}/proposals/{number}", head
        )
        return self.proposals[number]

    def by_head(self, head: str) -> ProposalState | None:
        """The *open* proposal for `head`, if this repository holds one."""
        for proposal in self.proposals.values():
            if proposal.head == head and proposal.state == "OPEN":
                return proposal
        return None

    def require(self, number: int) -> ProposalState:
        """The proposal, or a forge refusal — an unknown handle is not silence."""
        found = self.proposals.get(number)
        if found is None:
            raise ForgeError("FORGE_NOT_FOUND", f"no proposal {number} here", "")
        return found

    def close(self, number: int, *, note: str = "") -> None:
        """Somebody closed it, unlanded, and this is what they said (069-US3).

        Idempotent by construction: closing what is already closed re-states the
        note and stays closed, which is what a forge does and what a reset run
        twice depends on.
        """
        proposal = self.require(number)
        proposal.state, proposal.closing_note = "CLOSED", note

    def land(self, number: int, *, at: str = "2026-08-16T10:04:00Z") -> None:
        """The forge landed it."""
        proposal = self.require(number)
        proposal.state, proposal.merged_at = "MERGED", at

    def fail_checks(self, number: int, checks: tuple[str, ...], *, log: str = "") -> None:
        """The named gates failed, and this is what they left behind."""
        proposal = self.require(number)
        proposal.failing_checks = checks
        proposal.logs = {name: log for name in checks} if log else {}

    def target_moved(self, number: int) -> None:
        """The target moved under it: the change no longer applies."""
        self.require(number).in_conflict = True
