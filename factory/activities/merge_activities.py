"""US1's landing surface: push, open, enqueue, poll, disable — and nothing else.

`factory/mergequeue/` is a library — a data model, a classifier, a client, a PR
renderer. This module turns those into things the workflow can call, which means
it owns the two concerns the library deliberately does not (the same split
`factory/activities/verify_activities.py` draws for verification): reading the
world at a known moment, and turning a library exception into a refusal the
interpreter can route without reading prose.

The activities are one landing's life, in the plan's order:

- `prepare_landing_pr` — renders the PASS node's PR body to a scratch file via
  the pure `render_pr_body`, reading the renderer's secret inputs from the worker
  environment so they never cross a workflow boundary (constitution V).
- `open_landing_pr` — salvage has already happened (the workflow salvages before
  it ever calls this); this *pushes* the node branch to the target clone's
  `origin` (FR-001 — the forge reads that clone, so the branch has to exist on
  that remote), then offers it. Offered ready, and idempotent: an existing
  proposal for the branch is reused — a forge holds one landing per head.
- `enqueue_landing` — asks the forge to land the proposal once its gates pass;
  the factory never merges (D-024, FR-002). A refusal (the target stopped
  accepting landings mid-flight, the spec edge case) is returned as rejection
  data, never raised — the workflow routes it to escalation.
- `poll_landing` — one observation → a `PrSnapshot`, the classifier's input.
- `disable_auto_merge` — the kill-cleanup path: best-effort, so a killed epic's
  landing stops trying to land even when the call fails.

No activity ever removes a branch (FR-008): the branch is the target's to land,
and this module never issues a branch-removal command — the string the
structural guard greps for must never appear in its command surface.

`_client_factory` is the seam in the same sense as `open_bot` and
`judge_transport`: since 049's US1 it resolves the *forge* the target repository
is on — since US5, the one that repository's own manifest declares — and since
US3 every landing activity speaks to that forge and nothing beneath it: none
constructs a forge-native client or names one (FR-009). It
keeps its name deliberately: twenty-one call sites in the landing suite bind it,
and US3-S1 requires that suite to pass with no assertion changed, so a rename
would rewrite the one file whose stillness is the evidence (trap 14).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from temporalio import activity
from temporalio.exceptions import ApplicationError

from factory.mergequeue.forge import Forge, ForgeError, resolve_forge_for_repo
from factory.mergequeue.messages import pr_title, render_pr_body
from factory.mergequeue.models import CheckFailure, PrSnapshot, TargetRepoProfile
from factory.mergequeue.onboard import InitFacts, evaluate_init_facts, evaluate_repo
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV
from factory.verify.factory_yaml import FactoryConfigError, load_factory_config, resolve_manifest_path
from factory.verify.models import VerificationResult
from factory.workgraph import worktree as worktrees
from factory.workgraph.adapter import transcript_dir

#: Where the worker host keeps worktrees — one override, one default, the same
#: resolver agent_activities uses. The merge surface must hand `push_branch` the
#: *same* root the worktree was prepared under: git resolves a relative worktree
#: path against the target clone, while Python resolves it against the worker's
#: cwd, and a relative root silently splits the two (see the absolute-root rule
#: in scripts/ergane-env.sh).
FACTORY_ROOT_ENV = "FACTORY_ROOT"

#: The activity error type for a landing that must not proceed — an enqueue the
#: queue will not accept for a reason that is not an outage. Non-retryable: the
#: rejection is data the workflow routes to escalation, not a transient fault.
#: (The client already classifies; this re-raises as data via `EnqueueResult`.)
LANDING_REFUSED = "LANDING_REFUSED"

#: The activity error type for a git push that failed. Retryable, like the
#: worktree operations: a lock or a slow filesystem is what a second attempt
#: fixes.
PUSH_FAILED = "PUSH_FAILED"


@dataclass(frozen=True)
class PrepareLandingPrInput:
    """The non-secret facts the PR body is rendered from (constitution V).

    `result` is the passing attempt's `VerificationResult` — its per-gate
    results and judge word are what the body quotes. The secrets
    `render_pr_body` also demands (`proxy_url`, `master_key`, `telegram_token`,
    `transcript_path`) are deliberately *absent*: they live only in the worker
    host environment and are read inside this activity, never carried in an
    orchestration payload (architecture §10).
    """

    epic_id: str
    node_id: str
    branch: str
    attempt: int
    feature: str
    requirement_keys: tuple[str, ...]
    result: VerificationResult
    story_title: str


@dataclass(frozen=True)
class PrepareLandingPrResult:
    """The body file and title `open_landing_pr` needs — the workflow's side is pure."""

    body_file: str
    title: str


@dataclass(frozen=True)
class OpenLandingPrInput:
    """What the workflow knows about a PASS node that must now land.

    `body_file` is a path `prepare_landing_pr` wrote (rendered by
    `factory/mergequeue/messages.py`); the activity passes it to
    `gh pr create --body-file` so the body's quoting needs no shell care.
    """

    epic_id: str
    node_id: str
    target_repo: str
    base: str
    branch: str
    title: str
    body_file: str


@dataclass(frozen=True)
class OpenLandingPrResult:
    """The PR the landing will ride: number, URL, and pushed sha.

    US3: `pushed_sha` records the commit the branch was pushed to origin with,
    so a later recovery can compare the tree the queue rejected against the tree
    it is about to re-enqueue (FR-009). Default `None` keeps pre-spec histories
    replayable.
    """

    number: int
    url: str
    pushed_sha: str | None = None


@dataclass(frozen=True)
class CompareTreesInput:
    """US3: which two refs to compare for tree identity in a node's worktree.

    `rejected_tip` is the recorded `enqueued_tip` — what the queue tested.
    `current_head` is the worktree HEAD after the recovery sync and attempt.
    The activity runs `git rev-parse <ref>^{tree}` for both and reports whether
    the tree ids match.
    """

    epic_id: str
    node_id: str
    target_repo: str
    rejected_tip: str
    current_head: str


@dataclass(frozen=True)
class EnqueueLandingInput:
    """Which PR to enqueue, how the queue should land it, and against which clone.

    `target_repo` is the target clone path — `gh` runs with `cwd` = the clone
    (FR-001), so the queue command is issued against the same repository the
    branch was pushed to.
    """

    pr_number: int
    merge_method: str
    target_repo: str


@dataclass(frozen=True)
class EnqueueResult:
    """The enqueue's outcome — success or a refusal an interpreter can route.

    `None`-shaped on success is deliberately avoided: this dataclass always
    exists, and `rejected=False` is the success case, so the workflow reads
    one type whether the queue accepted the PR or refused it.
    """

    rejected: bool
    reason: str


@dataclass(frozen=True)
class PollLandingInput:
    """The PR to poll, and against which clone."""

    pr_number: int
    target_repo: str


@dataclass(frozen=True)
class DisableAutoMergeInput:
    """The PR to take out of the queue — the kill-cleanup path."""

    pr_number: int
    target_repo: str


@dataclass(frozen=True)
class DisableResult:
    """Best-effort outcome: whether disabling failed, and why, if it did."""

    failed: bool
    reason: str


@dataclass(frozen=True)
class FetchCheckFailureInput:
    """US2: which PR's failing checks to fetch evidence for (FR-005/006/007).

    `check_names` is the set of required checks the classifier named as failing;
    the activity resolves their run links, fetches the per-run failing-step log,
    and returns a frozen record per check. A `gh` failure anywhere in the chain
    returns degraded evidence with the absence stated, never a raise — the cycle
    must not be lost to its own evidence-gathering.
    """

    epic_id: str
    node_id: str
    pr_number: int
    check_names: tuple[str, ...]
    target_repo: str


@dataclass(frozen=True)
class SyncLandingBranchInput:
    """Which node's branch to sync onto the target head (US2 recovery, FR-005).

    A `CHECKS_FAILED` rejection means the target branch moved under the node; the
    recovery cycle's first move is to sync the node branch onto the new target
    head inside its worktree. `target_repo` is the clone whose `origin` is the
    remote the queue operates against — the branch is pushed there, so the sync
    fetches and merges from it.
    """

    epic_id: str
    node_id: str
    target_repo: str


@dataclass(frozen=True)
class SyncLandingBranchResult:
    """The sync's outcome, as data the workflow can route (FR-005).

    `clean` mirrors `worktree.SyncResult`: True when the target head merged in
    without a conflict, with `base_ref` the merged-in target head (the new branch
    point re-verification's diff is measured from, D-027 extended). `refused`
    covers a recovery that could not run — a missing worktree or a wedged git —
    surfaced as data with the reason, never a silent pass that would read as a
    successful sync and re-enqueue work that was not actually synced.
    """

    clean: bool
    base_ref: str | None
    conflicted_files: tuple[str, ...]
    refused: bool
    reason: str


@dataclass(frozen=True)
class ValidateTargetRepoInput:
    """Which target clone to validate — US3's preflight (FR-010).

    `validate_target_repo` runs against the clone itself: `gh` resolves the
    owner/repo from `origin`, and the repo's committed `factory.yaml` is read from
    the same clone. There is nothing else to say — the repo path is the whole
    input, which is what makes onboarding a property of a repo, not of a payload.
    """

    target_repo: str


#: The seam — a factory `(repo_path: str) -> Forge`. Production resolves the
#: forge the repository's own manifest declares (049-US5); tests replace this
#: with one over a scripted `gh` or a modelled repository. One factory for this
#: boundary, and no second.
_client_factory: Callable[..., Forge] = lambda *, repo_path: resolve_forge_for_repo(
    repo_path=repo_path
)


def _forge(*, repo_path: str) -> Forge:
    return _client_factory(repo_path=repo_path)


def _landing_body_dir() -> Path:
    """Where prepared PR bodies are written, under the worker's state directory.

    The same `FACTORY_ROOT` the worktree ops use, so one override locates all of
    the worker host's state. Body files are scratch — the PR create reads them
    once — so a fixed name is fine and cleanup is not this activity's job.
    """
    root, _choice, _source = worktrees.resolve_factory_root(FACTORY_ROOT_ENV)
    return root


# --- the activities -----------------------------------------------------------


@activity.defn
async def prepare_landing_pr(request: PrepareLandingPrInput) -> PrepareLandingPrResult:
    """Render a PASS node's PR body to a file — the one landing side effect that is a write.

    The body is rendered by the pure `render_pr_body` (deterministic, secret-free)
    and written to a scratch file for `gh pr create --body-file`. The renderer's
    secret inputs — proxy URL, master key, telegram token, transcript path — are
    read from the worker host environment *here*, inside the activity, so they
    never cross a workflow boundary (constitution V, architecture §10).
    """
    factory_root = _landing_body_dir()
    transcript = str(
        transcript_dir(factory_root, request.epic_id, request.node_id, request.attempt)
    )
    body = render_pr_body(
        epic_id=request.epic_id,
        node_id=request.node_id,
        branch=request.branch,
        attempt=request.attempt,
        feature=request.feature,
        requirement_keys=request.requirement_keys,
        result=request.result,
        proxy_url=os.environ.get(PROXY_URL_ENV, ""),
        master_key=os.environ.get(MASTER_KEY_ENV, ""),
        telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        transcript_path=transcript,
    )
    title = pr_title(
        epic_id=request.epic_id,
        node_id=request.node_id,
        story_title=request.story_title,
    )
    body_dir = factory_root / "landing" / request.epic_id / request.node_id
    body_dir.mkdir(parents=True, exist_ok=True)
    body_file = body_dir / f"attempt-{request.attempt}.md"
    body_file.write_text(body, encoding="utf-8")
    return PrepareLandingPrResult(body_file=str(body_file), title=title)


@activity.defn
async def open_landing_pr(request: OpenLandingPrInput) -> OpenLandingPrResult:
    """Push the node branch, then offer it to the target (FR-001, FR-009).

    Salvage has already happened; the branch holds the durable work. Pushing to
    the target clone's `origin` is what makes the PR's head exist on the remote
    the forge operates against, so the push comes first. Idempotent: an open PR
    for the branch is reused, so a retry after an unrecorded success does not
    open a second PR for one head.

    Raises `PUSH_FAILED` (retryable) when git refused, and lets the forge's own
    `ForgeError` through when it refused the offer.
    """
    try:
        pushed_sha = await asyncio.to_thread(
            worktrees.push_branch,
            request.target_repo,
            request.epic_id,
            request.node_id,
            factory_root=worktrees.resolve_factory_root(FACTORY_ROOT_ENV)[0],
        )
    except worktrees.WorktreeError as exc:
        raise ApplicationError(str(exc), type=PUSH_FAILED) from exc

    forge = _forge(repo_path=request.target_repo)

    existing = forge.find_proposal(request.branch)
    if existing is not None:
        return OpenLandingPrResult(
            number=existing.number, url=existing.url, pushed_sha=pushed_sha
        )

    created = forge.open_proposal(
        base=request.base,
        head=request.branch,
        title=request.title,
        body_file=request.body_file,
    )
    return OpenLandingPrResult(
        number=created.number, url=created.url, pushed_sha=pushed_sha
    )


@activity.defn
async def enqueue_landing(request: EnqueueLandingInput) -> EnqueueResult:
    """Ask the forge to land the proposal once its gates pass (FR-002, FR-009).

    The factory never merges: it asks (D-024). The operator's declared method
    travels as stated intent; a branch whose landing policy owns the method
    ignores it. A refusal — the target stopped accepting landings mid-flight,
    the spec edge case — comes back as `EnqueueResult(rejected=True, reason=…)`,
    never as a raised crash, so the workflow routes it to escalation.
    """
    forge = _forge(repo_path=request.target_repo)
    try:
        forge.request_landing(
            request.pr_number, declared_method=request.merge_method
        )
    except ForgeError as exc:
        return EnqueueResult(rejected=True, reason=exc.detail or str(exc))
    return EnqueueResult(rejected=False, reason="")


@activity.defn
async def poll_landing(request: PollLandingInput) -> PrSnapshot:
    """One observation of the proposal — the classifier's input (FR-009)."""
    return _forge(repo_path=request.target_repo).observe_proposal(request.pr_number)


@activity.defn
async def disable_auto_merge(request: DisableAutoMergeInput) -> DisableResult:
    """Withdraw the landing request — best-effort (FR-008, FR-009).

    Called on the epic/node kill path so a killed epic does not keep landing. A
    failure is reported, never raised: the kill sequence must not be blocked on
    the forge's availability, and a landing that could not be withdrawn is a fact
    the workflow surfaces, not a crash it dies on.
    """
    forge = _forge(repo_path=request.target_repo)
    try:
        forge.withdraw_landing(request.pr_number)
    except ForgeError as exc:
        return DisableResult(failed=True, reason=exc.detail or str(exc))
    return DisableResult(failed=False, reason="")


@activity.defn
async def compare_trees(request: CompareTreesInput) -> bool:
    """Compare the rejected tip's tree with the current worktree HEAD (US3).

    Runs on a thread via `asyncio.to_thread` so the git subprocess never blocks the
    worker's event loop (trap 4). Returns True when the two refs resolve to the
    same tree id, False otherwise. A missing worktree or an unresolvable ref is
    a `WorktreeError` surfaced as `ApplicationError(type=PUSH_FAILED)` so the
    workflow escalates rather than guessing.
    """

    def _compare() -> bool:
        return worktrees.trees_identical(
            request.target_repo, request.rejected_tip, request.current_head
        )

    try:
        return await asyncio.to_thread(_compare)
    except worktrees.WorktreeError as exc:
        raise ApplicationError(str(exc), type=PUSH_FAILED) from exc


@activity.defn
async def sync_landing_branch(request: SyncLandingBranchInput) -> SyncLandingBranchResult:
    """Sync a rejected node's branch onto the target head (US2 recovery, FR-005).

    The recovery cycle's first move after a `CHECKS_FAILED` rejection: the
    `worktree.sync_with_target` helper fetches origin and merges the target head
    into the node branch inside its worktree (merge, never rebase — the branch is
    pushed, history stays fast-forward). The activity turns the helper's two
    outcomes into the data the workflow routes:

    - a clean merge → `clean=True` with the merged-in target head as `base_ref`;
    - a conflict → `clean=False` with the conflicted file list, the markers left
      in the tree for the debugger persona (FR-006);
    - a helper failure (missing worktree, wedged git) → `refused=True` with the
      reason, so the workflow escalates rather than re-enqueueing work that was
      not synced. Never a silent pass.
    """
    try:
        result = await asyncio.to_thread(
            worktrees.sync_with_target,
            request.target_repo,
            request.epic_id,
            request.node_id,
            factory_root=worktrees.resolve_factory_root(FACTORY_ROOT_ENV)[0],
        )
    except worktrees.WorktreeError as exc:
        return SyncLandingBranchResult(
            clean=False,
            base_ref=None,
            conflicted_files=(),
            refused=True,
            reason=str(exc),
        )
    return SyncLandingBranchResult(
        clean=result.clean,
        base_ref=result.base_ref,
        conflicted_files=result.conflicted_files,
        refused=False,
        reason="",
    )


@activity.defn
async def fetch_check_failure(request: FetchCheckFailureInput) -> tuple[CheckFailure, ...]:
    """Fetch each named failing check's evidence (US2, FR-005/006/007, FR-009).

    Runs on a thread via `asyncio.to_thread` so the forge's I/O never blocks the
    worker's event loop (trap 4). How the evidence is gathered was GitHub detail
    living in an activity and is the forge's since US3; what survives here is the
    promise the workflow depends on — one record per requested name, degraded
    with the absence stated rather than raised.
    """

    def _fetch() -> tuple[CheckFailure, ...]:
        forge = _forge(repo_path=request.target_repo)
        return forge.failing_check_evidence(request.pr_number, request.check_names)

    return await asyncio.to_thread(_fetch)


def onboard_target_repo(
    forge: Forge,
    target_repo: str,
    *,
    init_facts: "InitFacts | None" = None,
) -> TargetRepoProfile:
    """US3's preflight: gather a repo's facts through `forge` and judge it (FR-010).

    The fact-gathering half of onboarding — `evaluate_repo` (in
    `factory/mergequeue/onboard.py`) is the pure judgment. This reads the world
    at one moment, and since 049's US1 it reads it through a forge rather than
    by naming `gh`:

    - the repository's address, default branch and forge-authored findings;
    - the landing branch's policy — does it gate on named checks, which checks;
    - the clone's committed `factory.yaml` via the 002 loader.

    Every forge failure is returned as a failed validation with a finding — never
    a pass — and a malformed manifest is a failing `factory_yaml` finding
    carrying the loader's error, never a shrug (FR-010, spec US3 AS2). The
    profile's `passed` is the conjunction of its findings; a failing profile
    blocks dispatch before any key is issued or worktree created (SC-005).

    `forge` is injected so both the activity (via the `_client_factory` seam) and
    the offline CLI (`ergane repo onboard`) can drive the same logic against
    whichever forge their caller resolved.

    `init_facts` is 034 US4's second door: `ergane init --check` gathers what init
    created (runtime root, registry entry, landing branch, control plane) and
    passes it straight through to `evaluate_repo`, so terminal and dispatch
    render the *same* parity findings rather than two implementations that agree
    today. It travels the read-failure path too: a repo with no remote at all is
    precisely the repo whose local findings must still render.
    """
    manifest_path, _ = resolve_manifest_path(target_repo)

    try:
        config = load_factory_config(manifest_path)
        declared_gates = tuple(config.gates.keys())
        manifest_error = None
    except FactoryConfigError as error:
        declared_gates = ()
        manifest_error = str(error)

    try:
        repository = forge.describe_repository()
    except ForgeError as error:
        return _profile_from_forge_failure(
            target_repo, visibility="", default_branch="", address="",
            manifest_error=manifest_error, declared_gates=declared_gates,
            error=error, init_facts=init_facts,
        )

    try:
        policy = forge.landing_policy(repository.default_branch)
    except ForgeError as error:
        # A repo the factory cannot read is not dispatchable.
        return _profile_from_forge_failure(
            target_repo, visibility=repository.visibility,
            default_branch=repository.default_branch,
            address=repository.address, manifest_error=manifest_error,
            declared_gates=declared_gates, error=error, init_facts=init_facts,
        )

    return evaluate_repo(
        repo=repository.address or target_repo,
        reading=repository,
        policy=policy,
        declared_gates=declared_gates,
        factory_yaml_error=manifest_error,
        init_facts=init_facts,
    )


def _profile_from_forge_failure(
    target_repo: str,
    *,
    visibility: str,
    default_branch: str,
    address: str,
    manifest_error: str | None,
    declared_gates: tuple[str, ...],
    error: ForgeError,
    init_facts: "InitFacts | None" = None,
) -> TargetRepoProfile:
    """A failed validation from a forge refusal — never a pass (FR-010).

    A repo the factory cannot read is a repo the factory must not dispatch
    against. The findings carry the refusal and name the remedy; `queue_enabled`
    is False and the required checks are unknown, so `evaluate_repo` would report
    them as failing — but the primary finding is the read failure itself.
    """
    # The read failure dominates: visibility, queue and checks are all unknown,
    # so every check a known-value check would need is not judgeable. We return a
    # profile whose single dominant finding is the refusal, plus the manifest's
    # own finding if the manifest also failed.
    from factory.mergequeue.models import Finding

    # US3 left this naming `gh` and called it US2's; US2 left it too, and no
    # per-module check either story wrote was pointed here. US6's package-wide
    # sweep is what found it. `error.kind` already carries the forge's own
    # taxonomy term, so the operator loses nothing.
    detail = (
        f"could not read the repo via its forge ({error.kind}): "
        f"{error.detail or str(error)}"
    )
    findings = [Finding("repo_read", False, detail)]
    if manifest_error is not None:
        findings.append(
            Finding(
                "factory_yaml",
                False,
                f"manifest failed to load: {manifest_error}",
            )
        )
    # A forge refusal is not a reason to stop judging the repo's own tree: init's
    # findings come from the same function `evaluate_repo` calls, so the
    # gitignore and registry checks survive a repo with no remote at all.
    findings.extend(evaluate_init_facts(init_facts))
    return TargetRepoProfile(
        repo=address or target_repo,
        default_branch=default_branch,
        visibility=visibility,
        queue_enabled=False,
        required_checks=(),
        declared_gates=declared_gates,
        findings=tuple(findings),
        passed=False,
    )


@activity.defn
async def validate_target_repo(request: ValidateTargetRepoInput) -> TargetRepoProfile:
    """US3's preflight activity: gather facts through the seam and judge (FR-010).

    The thin wrapper: resolves the forge through the injectable `_client_factory`
    seam and hands it to `onboard_target_repo`, which both this activity and the
    offline CLI share. Tests replace the seam with one over a `FakeGh`; the CLI
    resolves a forge against the clone the operator points at.
    """
    return onboard_target_repo(_forge(repo_path=request.target_repo), request.target_repo)
