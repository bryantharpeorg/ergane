"""The forge seam: what the factory needs from a forge, and nothing else (049-US1).

D-046 decided that the forge is an adapter and GitHub is the reference
implementation, because GitHub is not a dependency of this factory — it is an
*assumption*, load-bearing at every epic start. This module is the **reading**
half of that seam: two operations, a name → builder registry, and records
written in terms no forge owns. US3 adds the landing half, US4 the wiring one.

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
from typing import Any, Callable, Protocol, runtime_checkable

from factory.mergequeue.models import CheckFailure, Finding, PrSnapshot

#: The forge every repository is on until one says otherwise. 049's US5 teaches
#: the manifest to name it; until then this is the only answer.
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

    `landing_title_remedy` (049 US2, FR-007) is how a forge answers *how to fix
    that* — a title source is one call only the forge knows. Empty means it
    offered none, and the judgment says what it can without one.
    """

    branch: str
    gates_on_named_checks: bool = False
    required_checks: tuple[str, ...] = ()
    lands_without_a_human: bool = False
    landing_title_from_proposal: bool = False
    landing_title_source: str | None = None
    #: How this forge says to make a landing take the proposal's title.
    landing_title_remedy: str = ""


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
    """The seam: two reading operations, six landing ones, and no ninth."""

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

    # --- the landing half (049-US3, FR-009) ----------------------------------
    #
    # Six operations, one per thing a forge's vocabulary differs about when work
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

    def failing_check_evidence(
        self, proposal: int, check_names: tuple[str, ...]
    ) -> tuple[CheckFailure, ...]:
        """What each of `check_names` said when it failed, as far as it can say.
        Evidence, never a conclusion: a forge that cannot produce a log states the
        absence in the record's `note` and returns anyway, one record per
        requested name, so the recovery cycle is not lost to its own evidence."""
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
