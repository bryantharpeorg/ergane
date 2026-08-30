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

- `_clone_runner` — production refreshes the target clone to its declared
  landing branch (FR-006: "fresh clone at the current default branch"; 090
  US1: the branch is read from the manifest via `resolve_landing_base`, not
  from whatever HEAD has checked out); tests hand back a scripted
  `CloneResult` so the clone never touches a real repo.
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

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from temporalio import activity

from factory.config import Persona, load_personas
from factory.mergequeue.models import TargetRepoProfile
from factory.usage.litellm_client import LiteLLMClient
from factory.workgraph.derive import DerivationError
from factory.workgraph.models import WorkGraph
from factory.workgraph.preflight import (
    PreflightFinding,
    check_aliases,
    landing_readiness_preflight,
    prompt_assembly_preflight,
)
from factory.workgraph.worktree import resolve_factory_root
from factory.workgraph.workflow import JUDGE_PERSONA
from factory.workgraph.worktree import landing_branch
from factory.verify.factory_yaml import load_loop_config
from factory.verify.models import VerificationConfig

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

    `default_source` is the arm that named the branch (090 US1, FR-006):
    `worktree.LANDING_BASE_MANIFEST` when the repo's own manifest declared
    it, `worktree.LANDING_BASE_HEAD` when no readable manifest did and the
    clone's checked-out `HEAD` answered instead. The fallback value is
    shaped exactly like a declared one, so the branch alone cannot tell them
    apart — the arm is what lets an operator see that the refresh guessed.
    US3 populates it from the `LandingBase` the refresh already holds;
    the empty default keeps pre-090 histories replayable.

    `refusal` is the other end of 090 US2 (FR-003, FR-004): the refresh's
    explanation of why it declined to touch the clone, empty when it went
    ahead. It rides on the result rather than being raised because a refused
    clone is not a git error — see `clone_target`'s contract — and the
    workflow parks the spec on it. Empty by default for the same replay
    reason as `default_source`.
    """

    path: str
    default_branch: str
    head_ref: str
    default_source: str = ""
    refusal: str = ""


def _work_at_risk(repo: Path, branch: str) -> str:
    """Why a reset of `branch` to its remote would destroy work, or "" if it would not.

    Two questions, because `git reset --hard origin/<branch>` destroys two
    kinds of work and the obvious check only sees one (FR-003, plan trap 2):

    1. **Uncommitted changes to tracked files.** `git status --porcelain` over
       tracked paths only — `--untracked-files=no`. Untracked files are not at
       risk at all: a hard reset restores tracked paths and leaves everything
       else where it is, so an untracked file survives the refresh whether or
       not the repo ignores it. That is also, exactly, why FR-005 holds without
       a special case — the `.factory/`, `__pycache__/` and `node_modules/`
       every built-in clone carries never reach this list, and git's own ignore
       rules (the *target repo's*, not a list this function carries) are what
       keep them out of the untracked set in the first place. `EXCLUDED_DIR_NAMES`
       is the standing reminder of what a hand-written list costs.
    2. **Commits on the local branch that the remote ref does not have.** The
       reset target is `origin/<branch>`, so work an operator *committed to be
       safe* is discarded just as surely as an uncommitted edit — and is
       invisible to question 1, because committing it left the tree clean. This
       is the case the round-2 report measured.

    The caller fetches first: `origin/<branch>` must be current or a commit that
    is already pushed reads as unpushed and parks a clone that was never at
    risk. A branch that exists only locally has no remote ref to compare
    against; the reset would fail on it anyway, as a git error, which is the
    pre-existing path and not this guard's to pre-empt (trap 1).
    """
    from factory.workgraph.worktree import _git

    def _ref_exists(ref: str) -> bool:
        return bool(_git(repo, "for-each-ref", "--format=%(refname)", ref).strip())

    dirty = [
        line.rstrip()
        for line in _git(
            repo, "status", "--porcelain", "--untracked-files=no"
        ).splitlines()
        if line.strip()
    ]

    remote_ref = f"origin/{branch}"
    unpushed: list[str] = []
    if _ref_exists(f"refs/heads/{branch}") and _ref_exists(f"refs/remotes/{remote_ref}"):
        unpushed = [
            line.strip()
            for line in _git(
                repo,
                "log",
                "--format=%h %s",
                f"{remote_ref}..refs/heads/{branch}",
            ).splitlines()
            if line.strip()
        ]

    if not dirty and not unpushed:
        return ""

    # FR-004: the branch, the work at risk, and the act that clears it. An
    # operator reading a parked spec should not have to open a terminal to
    # learn which of their changes stopped the line.
    lines = [
        f"refusing to refresh {repo}: branch {branch!r} carries work that is not "
        f"on {remote_ref}, and `git reset --hard {remote_ref}` would discard it."
    ]
    if dirty:
        lines.append("  uncommitted changes to tracked files:")
        lines.extend(f"    {entry}" for entry in dirty)
    if unpushed:
        lines.append(f"  commits not on {remote_ref}:")
        lines.extend(f"    {entry}" for entry in unpushed)
    lines.append(
        f"To clear this, push the work to {remote_ref}, move it to a branch of "
        f"your own (`git switch -c <branch>`), or discard it yourself "
        f"(`git restore .` / `git reset --hard {remote_ref}`). The roadmap "
        "refreshes on the next tick once the clone carries nothing of its own."
    )
    return "\n".join(lines)


def _refresh_to_default(target_repo: str) -> CloneResult:
    """Refresh the target clone to its declared branch and report where it stands.

    A fetch + hard reset to `origin/<branch>` so the epic derives from the
    trunk's current head, whatever other landings moved it since the last
    epic. Reuses the workgraph's git helpers (the same `_git` discipline the
    node worktrees already follow) so the clone never sees a factory credential
    (constitution V).

    090 US1: the branch comes from `resolve_landing_base` — the manifest's
    `landing_branch`, falling back to the checked-out HEAD only when the
    manifest is absent or malformed — and never from a second read of HEAD
    (FR-001). Before this, `_default_branch` asked the operator's working copy
    which branch it had checked out and reset *that* to its remote, so a
    clone left on an unpushed branch stalled every tick at clone, and a pushed
    one made the factory derive and land epics against a feature branch as
    though it were the trunk. The fetch / checkout / reset sequence is
    otherwise unchanged (FR-007): a clean clone on the declared branch
    refreshes exactly as it did before.

    090 US2: between the fetch and the checkout the refresh asks whether the
    reset would destroy anything (`_work_at_risk`) and declines if it would
    (FR-003). US1 spared the operator's *other* branches; this spares the case
    US1 cannot reach, an operator working directly on the declared branch,
    which is where the reset is least expected. The refusal travels on the
    result, not as an exception — see `clone_target` — and the fetch is kept
    ahead of it because a stale `origin/<branch>` makes the question
    unanswerable. Fetching destroys nothing, so a refused refresh still leaves
    the clone exactly as it found it.
    """
    from pathlib import Path

    from factory.workgraph.worktree import _git, _head, resolve_landing_base

    repo = Path(target_repo)
    base = resolve_landing_base(repo)
    _git(repo, "fetch", "--quiet", "origin")
    refusal = _work_at_risk(repo, base.branch)
    if refusal:
        return CloneResult(
            path=str(repo),
            default_branch=base.branch,
            head_ref=_head(repo),
            default_source=base.source,
            refusal=refusal,
        )
    _git(repo, "checkout", "--quiet", base.branch)
    _git(repo, "reset", "--quiet", "--hard", f"origin/{base.branch}")
    return CloneResult(
        path=str(repo),
        default_branch=base.branch,
        head_ref=_head(repo),
        default_source=base.source,
    )


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

    090 US2 is the first caller to exercise the first half of that line: a
    refresh that would destroy uncommitted or unpushed work returns a
    `CloneResult` carrying `refusal` and raises nothing, so the refusal reaches
    the workflow as data rather than as a stringified exception in the error
    arm. The two arms stay distinguishable, which is the point: one means the
    operator has work here, the other means git failed.
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
    """Compile one spec into the delta graph the child epic runs (FR-010).

    A thin activity around the pure `derive_delta`: the workflow cannot read
    files or shell git, so derivation — which a spec that does not compile refuses
    — runs as an activity whose `DerivationError` the workflow catches and parks
    verbatim (FR-006). The delta baseline is read from the refreshed target repo
    by `landed_facts` inside the activity; the workflow receives only the result.
    Returns the compiled `WorkGraph` on success.

    A `DerivationError` is a *deterministic* refusal (a spec that does not
    compile the same way every time), so it is re-raised as a non-retryable
    `ApplicationError` — the workflow parks it on the first attempt rather than
    retrying a refusal that cannot change (and the activity's retry policy
    would otherwise burn three attempts before the workflow ever saw it). The
    workflow reads the original message off the `ApplicationError` verbatim.
    """
    runner = _derive_runner
    if runner is not None:
        return runner(request)

    try:
        return await asyncio.to_thread(_derive_from_git, request)
    except DerivationError as exc:
        from temporalio.exceptions import ApplicationError

        raise ApplicationError(str(exc), non_retryable=True, type="DerivationError")


def _derive_from_git(request: DeriveInput) -> WorkGraph:
    """The blocking half of derivation: git reads, fingerprints, compilation.

    Split out of `derive_spec` so it runs on a worker thread rather than the
    event loop. Every call here shells git — `landed_facts` resolves the default
    head through `subprocess.run(..., timeout=GIT_TIMEOUT_S)`, and that timeout
    is 300 seconds. Awaiting it directly on the loop stops every other coroutine
    in the worker, including the heartbeat of an in-flight agent attempt, whose
    timeout is 120 seconds. See `_drift_from_git` for the incident this pair
    exists to prevent.
    """
    from pathlib import Path

    from factory.workgraph.delta import derive_delta
    from factory.workgraph.landed import landed_facts

    facts = landed_facts(
        request.target_repo,
        request.epic_id,
        default_branch=landing_branch(Path(request.target_repo)),
    )
    baseline = {
        story_key: {
            "commit": fact.commit,
            "fingerprint": _fingerprint_for_spec(
                request.target_repo, request.epic_id, fact.commit, story_key
            ),
        }
        for story_key, fact in facts.items()
    }
    delta = derive_delta(
        request.spec_text,
        baseline=baseline,
        epic_id=request.epic_id,
        feature=request.feature,
        specs_root=request.specs_root,
        target_repo=request.target_repo,
        # 069-US2: the task slices, read here rather than carried in the
        # payload. This is the path that dispatches epics *by itself*, so it
        # is where siblings actually race — an inference wired only into the
        # operator's `spec derive` would never reach the fan-out it exists to
        # order. The activity reads them; the workflow cannot.
        tasks_text=_tasks_text(request.specs_root, request.epic_id),
    )
    return delta.graph


def _tasks_text(specs_root: str, spec_dir: str) -> str | None:
    """The spec's `tasks.md` beside its `spec.md`, or None (069-US2).

    None is "there was nothing to read", never "nothing collides". A spec with
    no `tasks.md` cannot dispatch anyway — the prompt-assembly preflight two
    steps down parks it by name — so this stays silent rather than growing a
    second voice for it.
    """
    try:
        return (Path(specs_root) / spec_dir / "tasks.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


#: Test seam for derive_spec: production is `None` so the real delta path runs;
#: scheduler tests set this to a scripted runner so they can drive the graph that
#: reaches the child without a real target clone.
_derive_runner: Callable[[DeriveInput], WorkGraph] | None = None


def _default_branch(repo: Path) -> str:
    """The repo's default branch, or "main" as a safe fallback."""
    from factory.workgraph.worktree import _default_branch as worktree_default_branch

    try:
        return worktree_default_branch(repo)
    except Exception:
        return "main"


def _fingerprint_for_spec(repo: str | Path, spec_dir: str, rev: str, story_key: str):
    """Pinned fingerprint of one story at a landing commit."""
    from factory.workgraph.landed import fingerprint

    return fingerprint(repo, rev, spec_dir, story_key)


# --- drift: read-only fingerprint comparison for render -----------------------


@dataclass(frozen=True)
class DriftInput:
    """Inputs for drift detection: which spec and which repo to compare against."""

    target_repo: str
    spec_dir: str
    spec_text: str


#: The drift seam — production computes from git; tests script a boolean so the
#: scheduler tests do not need a real target clone at `TARGET_REPO`.
_drift_runner: Callable[[DriftInput], bool] | None = None


@activity.defn
async def drift_for_spec(request: DriftInput) -> bool:
    """Return True when the spec's fingerprints differ from their landed baseline.

    Read-only and repo-authoritative: computes per-story landed facts from the
    refreshed target repo, pins each fact's fingerprint at its landing commit,
    and compares it to the current spec text. A spec whose frontmatter is not
    `landed` is never drifted. The workflow uses this via `compute_readiness`
    so the render can show `amended` without dispatching (FR-009).
    """
    runner = _drift_runner
    if runner is not None:
        return runner(request)

    return await asyncio.to_thread(_drift_from_git, request)


def _drift_from_git(request: DriftInput) -> bool:
    """The blocking half of drift detection: git reads and pinned fingerprints.

    Split out of `drift_for_spec` so it runs on a worker thread rather than the
    event loop.

    This is not a hypothetical. On 2026-08-26 this body ran directly on the
    worker's loop: `landed_facts` resolves the default head through
    `subprocess.run(..., timeout=GIT_TIMEOUT_S)` — 300 seconds — and one slow
    fetch held the loop for 5m12s. The heartbeat of an in-flight agent attempt
    times out at 120s, so Temporal killed a node that was working correctly and
    had 138 insertions on disk. The roadmap schedule ticks every 300s, which
    made the exposure recur every five minutes until the schedule was paused.

    The rule this encodes: an `async` activity may not shell git on the loop.
    """
    from factory.workgraph.delta import fingerprint_for
    from factory.workgraph.landed import landed_facts

    repo_path = Path(request.target_repo)
    default = landing_branch(repo_path)
    facts = landed_facts(request.target_repo, request.spec_dir, default_branch=default)
    if not facts:
        return False

    current_by_key = {
        story_key: fingerprint_for(request.spec_text, story_key)
        for story_key in facts
    }
    for story_key, fact in facts.items():
        pinned = _fingerprint_for_spec(
            request.target_repo, request.spec_dir, fact.commit, story_key
        )
        # Missing baselines are skipped, not errors (US1 FR-001/FR-002).
        if pinned.digest is None:
            continue
        current = current_by_key.get(story_key)
        if current is None or pinned.digest != current.digest:
            return True
    return False


# --- preflight: the shared alias checks behind the proxy seam -----------------


@dataclass(frozen=True)
class PreflightInput:
    """The graph to preflight and the proxy url its key is honored at (FR-006).

    `proxy_url` is a url, never a credential — the master key is read from the
    environment inside the preflight client seam (FR-009). `spec_dir` names
    which spec this preflight is for, so a parked finding can say so.

    044 US2 adds `specs_root`, and it is deliberately a *root* rather than the
    three documents' text: `specs_root/spec_dir` is where the dispatch path's
    own read (`load_prompt_sources`) will look, so the activity opens the same
    files at the last moment before dispatch (044 FR-007). Carrying the texts
    instead would mean checking bytes the workflow read on some earlier pass,
    which is the hole this check exists to close. It carries a default only so
    an activity task scheduled by a pre-044 worker deserializes into this shape
    instead of failing the converter; every live caller passes it, and a task
    that somehow arrives without one reads its trio relative to the worker's
    working directory and parks naming the path it could not open — legible, and
    never a silent pass.
    """

    graph: WorkGraph
    proxy_url: str
    spec_dir: str
    specs_root: str = ""


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

    return LiteLLMClient(base_url=proxy_url, master_key=_master_key_from_env())


def _master_key_from_env() -> str:
    """The proxy master key, read from the worker environment (FR-009).

    Lives only in this process's environment; never enters an activity input,
    a finding, or a status payload. Read here — inside the seam — so the
    workflow never sees it.

    *Which* variable holds it is the control plane's answer, not this module's
    (048 FR-006): `LITELLM_MASTER_KEY` when the host exports it, otherwise the
    variable the operator declared at install. Routed through the one resolver
    so the roadmap and a hand-started epic cannot disagree about which host
    they are on. Only the credential is resolved here — the seam above is
    handed its `proxy_url` as an argument.
    """
    from factory.controlplane.resolve import resolve_master_key_env

    return resolve_master_key_env().read()


@activity.defn
async def preflight_spec(request: PreflightInput) -> list[PreflightFinding]:
    """Run the shared preflight before dispatch: prompts, then the proxy (FR-006).

    The pure checks live in `factory/workgraph/preflight.py` and are shared
    with the CLI's `ergane build start`, so the two surfaces cannot drift. The
    activity owns the client (master key from the environment) and the
    registry (the worker host's `personas.yaml`); the preflight module owns
    the alias math and the wording. Returns `[]` when every check passes.

    Prompt assembly runs **here, in the activity** (044 US2, FR-003). It is a
    read of three files, and workflow code cannot read files — putting it in
    `RoadmapWorkflow._dispatch` would make the roadmap non-deterministic, which
    is the defect class that killed the schedule on 2026-08-13. The workflow
    hands over the root it already holds; the activity opens the trio.

    Assembly goes first, and every check runs. First because it is the cheaper
    and more certain fact — no service is consulted, so it cannot be wrong about
    a proxy that is merely slow — and the workflow parks on the first finding,
    which makes it the one the operator is shown. All of them, rather than
    returning early, because an author fixing one refusal per run is the failure
    mode the collected-findings discipline exists to avoid: a spec with a broken
    `tasks.md` *and* an unserved alias needs one edit pass, not two roadmap
    passes.

    107 US4 adds the two landing preconditions between the two, through the same
    shared module (FR-011): a node worktree registered to another clone, and a
    landing branch that would be inferred from the target clone's checked-out
    HEAD rather than declared. The activity owns the *root* — `PreflightInput`
    gains no field, because the runtime root is a worker-host fact the workflow
    cannot read and must not carry — and the module owns the check and the
    wording, exactly as it does for the registry and the client.
    """
    findings = prompt_assembly_preflight(
        request.graph, Path(request.specs_root) / request.spec_dir
    )
    findings += landing_readiness_preflight(request.graph, _preflight_factory_root())
    findings += await check_aliases(
        request.graph, _preflight_registry(), _preflight_client(request.proxy_url)
    )
    return findings


def _preflight_factory_root() -> Path:
    """The worker host's runtime root, resolved as the dispatch path resolves it.

    The same read `agent_activities.factory_root()` makes before it prepares a
    worktree, so the directories this checks are the directories `ensure()` will
    be handed one dispatch later.
    """
    root, _choice, _source = resolve_factory_root()
    return root


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
    client = activity.client()
    open_ids: set[str] = set()
    # The list filter is the production query shape; the time-skipping test
    # server does not answer it, which is exactly why the seam below lets a
    # test script the count instead. The SDK's WorkflowExecutionStatus enum
    # does not round-trip to the grammar's expected spelling by any of .name,
    # .value, or str(), and .name.title() silently breaks on multi-word
    # members, so the literal is pinned here and guarded by tests/test_live_capacity.py.
    async for execution in client.list_workflows(
        f'ExecutionStatus = "{_OPEN_EPIC_STATUS}"'
    ):
        if execution.id.startswith("epic-"):
            open_ids.add(execution.id)
    return open_ids


#: The visibility status the production capacity read treats as "open".
#: Temporal's visibility grammar wants the title-case enum name, not the
#: uppercase .name of the SDK enum; see the comment in _list_open_epics.
_OPEN_EPIC_STATUS = "Running"


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


# --- loop config: dispatch-time ladder + order read ---------------------------


@dataclass(frozen=True)
class ReadLoopConfigInput:
    """The operator clone whose manifest decides this spec's loop (023 FR-002).

    The target repo is a worker-host path; the workflow never touches the
    filesystem, so this read runs as an activity and is pinned before the
    child starts. A manifest that does not parse is a non-retryable refusal:
    it will not become valid by being read again a moment later.
    """

    target_repo: str


@dataclass(frozen=True)
class ReadLoopConfigResult:
    """The two loop facts that ride `EpicInput` into the child epic."""

    config: VerificationConfig
    verify_order: tuple[str, ...]


#: Test seam for `read_loop_config`: production reads the clone's manifest;
#: scheduler tests script a fixed result so the manifest file is not the subject.
_read_loop_config_runner: Callable[[str], ReadLoopConfigResult] | None = None


@activity.defn
async def read_loop_config(request: ReadLoopConfigInput) -> ReadLoopConfigResult:
    """Read the committed loop config from the operator clone (023 US2).

    The read is pinned at dispatch time so the child epic's ladder and step
    order are properties of the commit the roadmap saw, not of any worktree
    the child may later write (trap 2, FR-002). `FactoryConfigError` is raised
    as a non-retryable `ApplicationError` so the workflow parks the spec with
    the rule named.
    """
    runner = _read_loop_config_runner
    if runner is not None:
        return runner(request.target_repo)

    from factory.verify.factory_yaml import FactoryConfigError

    try:
        config, verify_order = load_loop_config(request.target_repo)
    except FactoryConfigError as exc:
        from temporalio.exceptions import ApplicationError

        raise ApplicationError(str(exc), non_retryable=True, type="FactoryConfigError") from None
    return ReadLoopConfigResult(config=config, verify_order=verify_order)