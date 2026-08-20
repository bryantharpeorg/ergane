"""The forge seam: what the factory needs from a forge, and nothing else (049-US1).

D-046 decided that the forge is an adapter and GitHub is the reference
implementation, because GitHub is not a dependency of this factory — it is an
*assumption*, load-bearing at every epic start. This module is that seam: the
reading half (US1), the landing half (US3) and the wiring one (US4), a name →
builder registry, and records written in terms no forge owns.

**Renaming is not seaming.** A protocol whose operations were
`merge_queue_enabled()` and `squash_merge_commit_title()` would have moved
GitHub's vocabulary behind an interface and removed nothing. The test every
operation and record field is held to — structurally, by
`tests/test_forge_seam.py` — is whether a forge that never heard of a merge queue
could answer it: "does this forge refuse to land into this branch until named
checks pass, and which checks" is answerable anywhere, "is the merge queue
enabled" is not.

Nothing on this seam decides: no operation classifies, judges, retries or
settles. Those stay factory-side, the rule `factory/notify/adapter.py` states
for the messenger seam whose shape D-046 §1 tells this one to copy.

The seam lives inside `factory/mergequeue/` on purpose (FR-017): the
merge-surface guards in `tests/test_mergequeue_sweep.py` are scoped to that
directory and were earned by incidents, so a forge here is covered by
construction rather than because somebody widened a list.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Protocol, Sequence, runtime_checkable

from factory.mergequeue.models import CheckFailure, Finding, PrSnapshot

#: The forge every repository is on until its manifest says otherwise. US5
#: taught the manifest the `forge:` key; absent, this is still the answer, and
#: `resolve_forge_for_repo` below is where the two meet.
DEFAULT_FORGE = "github"

#: Forges that ship with the factory, and the module that registers each on
#: import. Imported lazily at resolve time, exactly as the messenger registry
#: does, so this module stays free of any forge's own machinery.
_BUILTIN_FORGE_MODULES = {DEFAULT_FORGE: "factory.mergequeue.github_forge"}


@dataclass(frozen=True)
class RepositoryDescription:
    """Q1's answer: can the factory reach this repository, and by what name.

    `address` is what the forge itself calls the repository, and the handle every
    later call addresses. `visibility` is what it says about who can see the
    repository; `""` means *this forge has no such notion*. Reported, never
    judged: the rule that a repository must be public belongs to GitHub (D-007),
    and 049's US2 moved it into the GitHub implementation, where it arrives as
    one of the `findings` below rather than as a question asked of forges it
    cannot apply to.

    `findings` is how a forge answers about facts only it has, appended by the
    shared judgment without knowing what they mean — which is what lets a
    forge-specific rule fail a repository without the judgment learning that
    forge's vocabulary.
    """

    address: str
    default_branch: str
    visibility: str = ""
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True)
class LandingPolicy:
    """What one branch does to a proposal — Q2, Q3 and Q5 for that branch.

    `gates_on_named_checks` is Q2, and the weight is on **named**: the factory's
    contract is that the gates its manifest declares are the gates the forge
    runs, and that is checkable only if the checks are addressable by name.
    `required_checks` is which ones, so the shared judgment can ask Q4 — parity
    against the declared gates — without knowing where the forge keeps them.

    `lands_without_a_human` is Q3, separate from Q2 because they are separately
    actionable: a forge that gates correctly but waits for a click is one this
    factory cannot land through (D-024), and saying which of the two is missing
    is the difference between a report and a riddle.

    `landing_title_from_proposal` is Q5 — will the commit the forge writes carry
    the proposal's title verbatim. `landing_title_source` is the forge's own
    spelling of the setting behind it: evidence for a remedy, never something to
    decide from; `None` means the forge would not say.

    `landing_title_remedy` (049 US2, FR-007) is how a forge says to fix that —
    one call only it knows. Empty means it offered none.
    """

    branch: str
    gates_on_named_checks: bool = False
    required_checks: tuple[str, ...] = ()
    lands_without_a_human: bool = False
    landing_title_from_proposal: bool = False
    landing_title_source: str | None = None
    #: How this forge says to make a landing take the proposal's title.
    landing_title_remedy: str = ""


#: What one wiring act came to, and the exact words an operator reads (049-US4).
#: They live on the seam rather than in the GitHub implementation because the
#: record crosses it: every forge reports its acts in these three terms.
APPLIED = "applied"
ALREADY_SATISFIED = "already satisfied"
ATTENTION = "attention"


@dataclass(frozen=True)
class WiringStep:
    """One wiring act: what it was, what happened, and what the operator should know."""

    name: str
    status: str
    detail: str


class WiringRefused(Exception):
    """A prerequisite the operator must fix, with its remedies and a manual path.

    Raised at the point of refusal — before the act it would have been — so a
    repository is never left gating on half of what it was asked to gate on, and
    always carrying the by-hand steps (FR-013), because an operator blocked on a
    credential still needs the repository wired today.
    """

    def __init__(
        self,
        headline: str,
        *,
        remedies: Sequence[str],
        manual: Sequence[str],
    ) -> None:
        self.headline = headline
        self.remedies = tuple(remedies)
        self.manual = tuple(manual)
        super().__init__(self.render())

    def render(self) -> str:
        lines = [self.headline, ""]
        for remedy in self.remedies:
            lines.append(f"  {remedy}")
        lines.append("")
        lines.append("or do the manual wiring steps yourself:")
        for step in self.manual:
            lines.append(f"  {step}")
        return "\n".join(lines)


def format_step(step: WiringStep) -> list[str]:
    """A status line, and the detail indented under it."""
    lines = [f"  {step.name}: {step.status}"]
    for line in step.detail.splitlines():
        lines.append(f"    {line}")
    return lines


class ForgeError(RuntimeError):
    """A forge that could not answer — data an activity returns, not a crash.

    `kind` is the implementation's own taxonomy term, carried through so an
    operator sees what their forge said; `detail` is the tail of it. The factory
    never branches on `kind`: a forge that cannot be read is a repository that
    cannot be dispatched against, whichever way it failed.
    """

    def __init__(self, kind: str, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.detail = detail


@runtime_checkable
class Forge(Protocol):
    """The seam: two reading operations, seven landing ones, one wiring one, no eleventh.

    The seventh landing operation is `close_proposal`, added by 069-US3 because
    `ergane build reset` has forge work to do that no existing operation
    expressed — see its docstring for why it is not `withdraw_landing`.
    """

    def describe_repository(self) -> RepositoryDescription:
        """Name this repository and report what only this forge can report.

        Raises `ForgeError` when it cannot be read at all — the failure that
        dominates every other question, since nothing else about a repository
        nobody can see is judgeable.
        """
        ...

    def landing_policy(self, branch: str) -> LandingPolicy:
        """Report what `branch` does to a proposal, in the neutral terms above.

        Reports; it does not decide. Whether a policy is *good enough* is the
        shared judgment's call, so adding a forge cannot change what readiness
        means.
        """
        ...

    # --- the landing half (049-US3, FR-009; 069-US3 added the seventh) --------
    #
    # Seven operations, one per thing a forge's vocabulary differs about when work
    # goes from a branch to the target. None decides: what an observation *means*
    # is `classify`'s call. Each raises `ForgeError` when the forge will not
    # answer — data the caller returns, not a fault.

    def find_proposal(self, head: str) -> "Proposal | None":
        """The open proposal for `head`, or `None`. A forge holds one landing per
        head, so a retried open must find what it has rather than offer a second
        and split the target's attention."""
        ...

    def open_proposal(
        self, *, base: str, head: str, title: str, body_file: str
    ) -> "Proposal":
        """Offer `head` to `base` under `title`, the body read from a file. Ready,
        never held back as unfinished — a forge that treats a proposal as a work
        in progress never runs its gates on it."""
        ...

    def request_landing(self, proposal: int, *, declared_method: str = "") -> None:
        """Ask the forge to land `proposal` itself, once its gates pass — D-024:
        the factory never merges, it asks. `declared_method` is the operator's
        stated intent about how the landing commit is formed, carried so a forge
        that honours it can, defaulted because a branch whose landing policy owns
        its method ignores it."""
        ...

    def observe_proposal(self, proposal: int) -> PrSnapshot:
        """One observation of `proposal`, as the factory's own reader takes it.
        The record's *name* is GitHub-shaped and stays so: it is rebuilt from live
        workflow histories, and renaming it would edit
        `factory/workgraph/workflow.py`, which FR-011 forbids. The field decided
        from is neutral (FR-010) — that is the part that had to move."""
        ...

    def withdraw_landing(self, proposal: int) -> None:
        """Take back the landing request, leaving the proposal open — the kill
        path. A killed epic must stop trying to land, and the proposal is not the
        factory's to close."""
        ...

    def close_proposal(self, proposal: int, *, note: str) -> None:
        """Close `proposal` for good, leaving `note` on it saying what closed it.

        The reset path (069 FR-010), and deliberately not the kill path's
        `withdraw_landing` above: a killed epic keeps its proposal, because an
        operator may still want it. A *reset* is the operator saying that node is
        being rebuilt from scratch, which is the one case where the proposal is
        the factory's to close — its head branch is about to stop existing, so
        what is left behind is a proposal no forge could ever land.

        `note` is not a courtesy. A proposal that simply went away reads as
        somebody having clicked, and whoever debugs the rebuild afterwards needs
        it to say otherwise.

        Closing an already-closed proposal is a success, because the reset it
        belongs to is run twice by operators who are not sure the first one
        finished.
        """
        ...

    def failing_check_evidence(
        self, proposal: int, check_names: tuple[str, ...]
    ) -> tuple[CheckFailure, ...]:
        """What each of `check_names` said when it failed, as far as it can say.
        Evidence, never a conclusion: a forge that cannot produce a log states the
        absence in the record's `note` and returns anyway, one record per
        requested name, so the recovery cycle is not lost to its own evidence."""
        ...

    # --- the wiring half (049-US4, FR-012/FR-013) ----------------------------

    def apply_landing_policy(
        self, branch: str, required_checks: Sequence[str]
    ) -> tuple[WiringStep, ...]:
        """Make `branch` gate on exactly `required_checks`, land with no human in
        the loop, and title a landing from the proposal — the write side of
        `landing_policy`, and the only operation here that changes a repository.

        Those three properties are fixed rather than arguments because the
        factory never wants any of them otherwise: an ungated branch, a landing
        it must click, or a landing commit it cannot read a story out of are all
        repositories it refuses to dispatch against. Only *which* branch and
        *which* checks vary, which is why they are the only parameters.

        Reports one `WiringStep` per act, `ALREADY_SATISFIED` for an act already
        true, so a second run changes nothing. A forge that cannot apply the
        policy raises `WiringRefused` carrying the by-hand steps rather than
        applying part of it (FR-013) — a repository gating on half its checks
        looks wired, which is worse than one gating on none.
        """
        ...


class UnknownForgeError(ValueError):
    """A forge name nothing is registered under.

    Raised rather than defaulted: a deployment that asked for one forge and
    silently got another would open proposals, and land them, somewhere nobody
    was looking.
    """


ForgeBuilder = Callable[..., Forge]

_REGISTRY: dict[str, ForgeBuilder] = {}


def register_forge(name: str, build: ForgeBuilder) -> None:
    """Registering under `name` is how a forge becomes selectable."""
    _REGISTRY[name] = build


def registered_forges() -> tuple[str, ...]:
    """Every selectable forge name, built-ins included.

    The conformance suite parametrizes over exactly this, so a forge added later
    is checked by having registered rather than by being remembered (FR-005).
    """
    _load_builtins()
    return tuple(sorted(_REGISTRY))


def resolve_forge(name: str | None = None, **seams: Any) -> Forge:
    """Build the forge named by `name`, or the one every repository has today.

    `seams` are handles the caller's process owns — `repo_path` for the clone a
    forge reads through, and whatever a test injects beneath it. A builder takes
    what it recognises and ignores the rest, because a caller resolving a forge
    by name cannot know which one it got.
    """
    chosen = name or DEFAULT_FORGE
    build = _REGISTRY.get(chosen)
    if build is None:
        _load_builtins()
        build = _REGISTRY.get(chosen)
    if build is None:
        raise UnknownForgeError(
            f"no forge is registered under {chosen!r}; "
            f"registered forges are {', '.join(sorted(_REGISTRY)) or '(none)'}"
        )
    return build(**seams)


def _load_builtins() -> None:
    """Import the modules that register the shipped forges, once each."""
    for name, module in _BUILTIN_FORGE_MODULES.items():
        if name not in _REGISTRY:
            import_module(module)


# --- the landing half's record (049-US3) --------------------------------------


@dataclass(frozen=True)
class Proposal:
    """A change offered to a branch, as the forge identifies it.

    `number` is the forge's own handle — what every later landing call addresses
    it by, and what the workflow already carries in its histories; `url` is where
    a person reads it. Two fields and no third: a record carrying a *state* would
    invite a caller to decide from it without asking. Appended at the module's
    end because US2 and US5 were building against this file at this commit, and a
    diff confined to the ends cannot shadow theirs (trap 14).
    """

    number: int
    url: str


# --- the door a repository path goes through (049-US5) ------------------------


def resolve_forge_for_repo(*, repo_path: str, **seams: Any) -> Forge:
    """Build the forge the repository at `repo_path` declares (049 FR-014).

    The door every caller holding a repository path goes through, so which forge
    is used is decided by the repository rather than by whichever module got
    there first. A manifest that declares nothing resolves `DEFAULT_FORGE`, which
    is every repository that exists today — that path is unchanged.
    """
    return resolve_forge(_manifest_forge_name(repo_path), repo_path=repo_path, **seams)


def _manifest_forge_name(repo_path: str) -> str:
    """The forge name a repository's manifest declares, or the default.

    One rule, and it is about *whose complaint it is*. Any way a manifest can be
    unreadable other than its `forge` key belongs to the reader that owns it —
    including there being no manifest at all, which is the state
    `ergane init --check` exists to judge, and a `version` that is wrong, which
    an operator should not first meet as a forge lookup exploding underneath
    them. All of those resolve the default.

    A manifest whose `forge` key is itself the defect is the one case re-raised.
    Refusing an unknown forge is the entire point of the key, and swallowing it
    here would reinstate at the door exactly the silent fallback the loader
    refuses — a caller handed a GitHub forge for a manifest that said otherwise
    has already lost, whatever the parser said.

    There is deliberately no `path.is_file()` guard in front of the read: an
    absent file leaves `load_factory_config` as `missing_manifest`, which this
    already handles. The guard was written, and the mutation that should have
    killed the test covering it came back green because removing it changed
    nothing (evidence M9). A second path to the same answer is a branch no test
    can hold.
    """
    from factory.verify.factory_yaml import (
        DEFAULT_FORGE_NAME,
        FactoryConfigError,
        load_factory_config,
        resolve_manifest_path,
    )

    path, _name = resolve_manifest_path(repo_path)
    try:
        return load_factory_config(path).forge
    except FactoryConfigError as error:
        if error.rule == "forge":
            raise
        return DEFAULT_FORGE_NAME
