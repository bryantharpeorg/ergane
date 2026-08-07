"""The roadmap's pre-dispatch surface: clone, derive, preflight, onboarding, capacity.

US2's `RoadmapWorkflow` runs four checks before starting each dispatchable
spec's child `EpicWorkflow`, and one read to know how many epics are already
in flight. Each is an activity because workflow code touches nothing
(constitution IV): the clone is a git operation, derivation reads a file, the
preflight dials the proxy, onboarding reads the target repo, and the capacity
read lists open workflows through the Temporal client. None of it belongs in
workflow code, and none of it carries a credential across the boundary.

The shape mirrors `factory/activities/merge_activities.py`: a pure library
function does the work, a thin `@activity.defn` wrapper builds the side-effect
through an injectable seam, and tests script the seam. The seams are:

- `_clone_runner` — production refreshes the target clone to its default
  branch (FR-006: "fresh clone at the current default branch"); tests hand
  back a scripted `CloneResult` so the clone never touches a real repo.
- `_registry` — production reads `personas.yaml`; tests hand a fixed
  registry so the preflight checks deterministic personas (the same split the
  CLI's preflight draws, one host reading its own file).
- `_preflight_client` — production dials the proxy from the environment; the
  activity passes it to `check_aliases`, the shared core.
- `_open_epics_provider` — production lists open `epic-*` workflows through
  `activity.client()`; tests hand a scripted set, because the time-skipping
  test server does not answer the list filter the production query uses and
  the capacity read is a single per-pass call (not an interval poll) either
  way (FR-004).

Onboarding reuses 003's `validate_target_repo` activity as it stands — the
roadmap inherits N onboarding checks for N epics and does not optimize (plan
§ US2). A failing onboarding check parks the spec with its finding verbatim
(FR-006); the child epic re-runs onboarding at its own start, the same
belt-and-suspenders the epic already had.

FR-009 (the closed credential discipline 001 established, extended one level
up): the master key lives only in this process's environment and is read
inside the preflight client seam. No key value reaches any activity *input*
— `PreflightInput` carries the graph and a proxy *url* (not a credential),
`CloneInput` carries a path, `CountOpenInput` is empty. The sweep (T012)
asserts each surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from temporalio import activity

from factory.config import Persona, load_personas
from factory.mergequeue.models import TargetRepoProfile
from factory.usage.litellm_client import LiteLLMClient
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.models import WorkGraph
from factory.workgraph.preflight import PreflightFinding, check_aliases
from factory.workgraph.workflow import JUDGE_PERSONA

from factory.activities.merge_activities import (
    ValidateTargetRepoInput,
    validate_target_repo,
)


# --- clone: refresh the target clone to its current default branch ------------


@dataclass(frozen=True)
class CloneInput:
    """Where to refresh, and which spec the clone is for (FR-006).

    `target_repo` is the worker-host path to the target clone; `spec_dir` is
    the spec the clone is being prepared for, carried only so a finding can
    name which spec's pre-dispatch failed. No credential crosses here.
    """

    target_repo: str
    spec_dir: str


@dataclass(frozen=True)
class CloneResult:
    """The clone's identity at refresh time: path, default branch, head ref.

    `head_ref` is the commit the clone stood at after the refresh — the
    branch point the epic's nodes will pin against (FR-006: derive from the
    current default branch, not a stale one).
    """

    path: str
    default_branch: str
    head_ref: str


def _refresh_to_default(target_repo: str) -> CloneResult:
    """Refresh the target clone to its default branch and report where it stands.

    A fetch + hard reset to `origin/<default>` so the epic derives from the
    trunk's current head, whatever other landings moved it since the last
    epic. Reuses the workgraph's git helpers (the same `_git` discipline the
    node worktrees already follow) so the clone never sees a factory credential
    (constitution V).
    """
    from factory.workgraph.worktree import _default_branch, _git, _head
    from pathlib import Path

    repo = Path(target_repo)
    default = _default_branch(repo)
    _git(repo, "fetch", "--quiet", "origin")
    _git(repo, "checkout", "--quiet", default)
    _git(repo, "reset", "--quiet", "--hard", f"origin/{default}")
    return CloneResult(path=str(repo), default_branch=default, head_ref=_head(repo))


#: The clone seam — production refreshes a real clone; tests hand back a
#: scripted result so the activity never spawns git.
_clone_runner: Callable[[str], CloneResult] = _refresh_to_default


@activity.defn
async def clone_target(request: CloneInput) -> CloneResult:
    """Refresh the target clone to its default branch before dispatch (FR-006).

    The thin wrapper: the clone runs through `_clone_runner`, which production
    implements with git and tests replace with a scripted result. Never raises
    on a refused clone — that is a pre-dispatch refusal the workflow parks —
    but a git error propagates as an activity failure the workflow catches and
    parks verbatim (FR-006).
    """
    return _clone_runner(request.target_repo)


# --- derive: the pure deriver behind a thin activity --------------------------


@dataclass(frozen=True)
class DeriveInput:
    """One spec's text and the identity fields the deriver cannot infer.

    The deriver is pure and is handed text (FR-011), so the epic id, feature,
    specs root and target repo — the four identity fields — are the caller's.
    No credential; the spec text is read by the workflow's `read_roadmap`
    surface, not carried here.
    """

    spec_text: str
    epic_id: str
    feature: str
    specs_root: str
    target_repo: str


@activity.defn
async def derive_spec(request: DeriveInput) -> WorkGraph:
    """Compile one spec into the graph the child epic runs (FR-006).

    A thin activity around the pure `derive_workgraph`: the workflow cannot
    read files, so derivation — which a spec that does not compile refuses —
    runs as an activity whose `DerivationError` the workflow catches and parks
    verbatim (FR-006). Returns the compiled `WorkGraph` on success.

    A `DerivationError` is a *deterministic* refusal (a spec that does not
    compile the same way every time), so it is re-raised as a non-retryable
    `ApplicationError` — the workflow parks it on the first attempt rather than
    retrying a refusal that cannot change (and the activity's retry policy
    would otherwise burn three attempts before the workflow ever saw it). The
    workflow reads the original message off the `ApplicationError` verbatim.
    """
    try:
        return derive_workgraph(
            request.spec_text,
            epic_id=request.epic_id,
            feature=request.feature,
            specs_root=request.specs_root,
            target_repo=request.target_repo,
        )
    except DerivationError as exc:
        from temporalio.exceptions import ApplicationError

        raise ApplicationError(str(exc), non_retryable=True, type="DerivationError")


# --- preflight: the shared alias checks behind the proxy seam -----------------


@dataclass(frozen=True)
class PreflightInput:
    """The graph to preflight and the proxy url its key is honored at (FR-006).

    `proxy_url` is a url, never a credential — the master key is read from the
    environment inside the preflight client seam (FR-009). `spec_dir` names
    which spec this preflight is for, so a parked finding can say so.
    """

    graph: WorkGraph
    proxy_url: str
    spec_dir: str


def _preflight_registry() -> dict[str, Persona]:
    """The worker host's view of the registry, read from its `personas.yaml`.

    The same split the CLI's preflight draws: the worker reads its own file,
    so the preflight states what *this* registry resolves — never claims the
    CLI's resolution was validated (US2 Edge Cases).
    """
    return load_personas()


def _preflight_client(proxy_url: str) -> LiteLLMClient:
    """The activity's one route to the proxy, credentials from the environment.

    A seam, not a factory: production builds a `LiteLLMClient` against the
    worker host's environment (the master key lives there and nowhere else);
    tests replace it to inject a fake transport, the same way the usage
    activities' `open_client` is replaced.
    """
    from factory.usage.litellm_client import LiteLLMClient

    return LiteLLMClient(base_url=proxy_url, api_key=_master_key_from_env())


def _master_key_from_env() -> str:
    """The proxy master key, read from the worker environment (FR-009).

    Lives only in this process's environment; never enters an activity input,
    a finding, or a status payload. Read here — inside the seam — so the
    workflow never sees it.
    """
    import os

    return os.environ["LITELLM_MASTER_KEY"]


@activity.defn
async def preflight_spec(request: PreflightInput) -> list[PreflightFinding]:
    """Run the shared preflight against a live proxy before dispatch (FR-006).

    The pure checks live in `factory/workgraph/preflight.py` and are shared
    with the CLI's `factory-epic start`, so the two surfaces cannot drift. The
    activity owns the client (master key from the environment) and the
    registry (the worker host's `personas.yaml`); the preflight module owns
    the alias math and the wording. Returns `[]` when every check passes.
    """
    return await check_aliases(
        request.graph, _preflight_registry(), _preflight_client(request.proxy_url)
    )


# --- onboarding: reuse 003's activity as it stands ----------------------------


@dataclass(frozen=True)
class OnboardInput:
    """The target repo to validate before dispatch (FR-006, reusing 003).

    `spec_dir` names which spec this onboarding is for, so a parked finding
    can say so; the onboarding check itself is the repo's, not the spec's.
    """

    target_repo: str
    spec_dir: str


async def _onboard_profile(target_repo: str) -> TargetRepoProfile:
    """Production onboarding: 003's `validate_target_repo` activity as it stands.

    The child epic re-runs onboarding at its own start, so this is the roadmap's
    pre-dispatch refusal gate — a repo that fails onboarding parks every spec
    that would dispatch against it, with the finding verbatim, instead of
    starting an epic that immediately fails (FR-006). Onboarding re-validates
    per epic by design, uncached — inherit, do not optimize (plan § US2).
    """
    return await validate_target_repo(
        ValidateTargetRepoInput(target_repo=target_repo)
    )


#: The onboarding seam — production reuses 003's activity; tests replace it with
#: a scripted `TargetRepoProfile` so the scheduler tests are not also onboarding
#: tests (003 owns onboarding's own coverage).
_onboard: Callable[[str], "Awaitable[TargetRepoProfile]"] = _onboard_profile


@activity.defn
async def onboard_target(request: OnboardInput) -> TargetRepoProfile:
    """Re-validate the target repo before each dispatch (FR-006, reusing 003).

    Thin wrapper over the `_onboard` seam: production calls 003's
    `validate_target_repo`; tests script a profile. `spec_dir` names which
    spec this onboarding is for, so a parked finding can say so; the check
    itself is the repo's, not the spec's.
    """
    return await _onboard(request.target_repo)


# --- capacity: count the open epics the roadmap dispatches around -------------


@dataclass(frozen=True)
class CountOpenInput:
    """No arguments — the capacity read is against the worker's own client.

    Empty on purpose: the open-epic count is a property of the Temporal
    namespace the worker polls, not of any roadmap input. Carrying nothing
    is what keeps a credential out of it (FR-009).
    """


@dataclass(frozen=True)
class CountOpenResult:
    """The open `epic-*` workflow ids at pass start.

    Includes epics the roadmap started *and* operator-started epics mid-flight
    when the roadmap booted — the roadmap dispatches around both, so the bound
    is honest about everything consuming a slot (plan § US2, the double-
    dispatch-after-restart guard).
    """

    open_ids: tuple[str, ...]


async def _list_open_epics() -> set[str]:
    """Production capacity read: open `epic-*` workflows through the client.

    A single read at the start of a scheduling pass, never an interval poll
    (FR-004): the workflow wakes on child completion events and calls this once
    per pass to know how many slots are free. `RUNNING` is the open state;
    `CONTINUED_AS_NEW` is a closed run (the new run carries a fresh id), so it
    does not count.
    """
    from temporalio.client import WorkflowExecutionStatus

    client = activity.client()
    open_ids: set[str] = set()
    # The list filter is the production query shape; the time-skipping test
    # server does not answer it, which is exactly why the seam below lets a
    # test script the count instead.
    async for execution in client.list_workflows(
        'ExecutionStatus = "RUNNING"'
    ):
        if execution.id.startswith("epic-"):
            open_ids.add(execution.id)
    return open_ids


#: The capacity seam — production lists open workflows through the client;
#: tests hand a scripted set so the count is deterministic without a real
#: Temporal list round trip.
_open_epics_provider: Callable[[], Awaitable[set[str]]] = _list_open_epics


@activity.defn
async def count_open_epics(request: CountOpenInput) -> CountOpenResult:
    """How many `epic-*` workflows are open right now (FR-005 capacity accounting).

    The roadmap's own in-flight children are open `epic-*` workflows, so this
    count is the total slots in use — roadmap's plus operator-started — and the
    roadmap dispatches around it (FR-005). Called once per scheduling pass, not
    on an interval (FR-004).
    """
    open_ids = await _open_epics_provider()
    return CountOpenResult(open_ids=tuple(sorted(open_ids)))