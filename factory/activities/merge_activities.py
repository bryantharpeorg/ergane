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
  `origin` (FR-001 — `gh` runs against the clone, so the branch has to exist on
  that remote), then opens a ready PR. Never `--draft`, and idempotent: an
  existing open PR for the branch is reused, not duplicated — the queue can hold
  only one PR per head.
- `enqueue_landing` — the factory's *only* merge invocation: `gh pr merge <n>
  --auto --<method>`, the method read from `LandingConfig` (FR-002). A refused
  enqueue (queue disabled mid-flight, the spec edge case) is returned as
  rejection data, never raised — the workflow routes it to escalation.
- `poll_landing` — one `gh pr view` → a `PrSnapshot`, the classifier's input.
- `disable_auto_merge` — the kill-cleanup path: best-effort, so a killed epic's
  landing stops trying to land even when the call fails.

No activity ever removes a branch (FR-008): the branch is the queue's to land,
and this module never issues a branch-removal command — the string the
structural guard greps for must never appear in its command surface.

`_client_factory` is the seam in the same sense as `open_bot` and
`judge_transport`: production builds a `GhClient` that spawns real `gh` against
the target clone, and tests replace the factory with one wired to a `FakeGh`.
The activity itself never touches the runner — it names the repo and the method,
and lets the client own the subprocess.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from temporalio import activity
from temporalio.exceptions import ApplicationError

from factory.mergequeue.gh import (
    GH_AUTH,
    GH_NOT_FOUND,
    GH_REFUSED,
    GH_UNAVAILABLE,
    GhClient,
    GhError,
)
from factory.mergequeue.messages import pr_title, render_pr_body
from factory.mergequeue.models import PrSnapshot, TargetRepoProfile
from factory.mergequeue.onboard import evaluate_repo
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV
from factory.verify.factory_yaml import FactoryConfigError, load_factory_config
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

#: The activity error type for a `gh` outage that should not be re-read as a
#: verdict. The client classifies these; an activity that cannot reach `gh` at
#: all reports the outage rather than guessing.
GH_UNAVAILABLE_ACTIVITY = "GH_UNAVAILABLE"


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
    """The PR the landing will ride: number and URL, for the record and the body."""

    number: int
    url: str


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


#: The seam — a factory `(repo_path: str) -> GhClient`. Production builds a real
#: client against the target clone; tests replace this with one wired to a
#: `FakeGh` (same discipline as `open_bot` / `judge_transport`).
_client_factory: Callable[..., Any] = lambda *, repo_path: GhClient(repo=repo_path)


def _client(*, repo_path: str) -> GhClient:
    return _client_factory(repo_path=repo_path)


def _landing_body_dir() -> Path:
    """Where prepared PR bodies are written, under the worker's state directory.

    The same `FACTORY_ROOT` the worktree ops use, so one override locates all of
    the worker host's state. Body files are scratch — the PR create reads them
    once — so a fixed name is fine and cleanup is not this activity's job.
    """
    return Path(os.environ.get(FACTORY_ROOT_ENV) or worktrees.DEFAULT_FACTORY_ROOT)


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
    """Push the node branch, then open a ready PR for it (FR-001).

    Salvage has already happened; the branch holds the durable work. Pushing to
    the target clone's `origin` is what makes the PR's head exist on the remote
    the queue operates against, so the push comes first. Idempotent: an open PR
    for the branch is reused, so a retry after an unrecorded success does not
    open a second PR for one head.

    Raises `PUSH_FAILED` (retryable) when git refused, and re-raises a `GhError`
    as its own kind when `gh` refused the create.
    """
    try:
        await asyncio.to_thread(
            worktrees.push_branch,
            request.target_repo,
            request.epic_id,
            request.node_id,
            factory_root=Path(os.environ.get(FACTORY_ROOT_ENV) or worktrees.DEFAULT_FACTORY_ROOT),
        )
    except worktrees.WorktreeError as exc:
        raise ApplicationError(str(exc), type=PUSH_FAILED) from exc

    client = _client(repo_path=request.target_repo)

    existing = client.find_existing_pr(request.branch)
    if existing is not None:
        return OpenLandingPrResult(number=existing.number, url=existing.url)

    created = client.create_pr(
        base=request.base,
        head=request.branch,
        title=request.title,
        body_file=request.body_file,
    )
    return OpenLandingPrResult(number=created.number, url=created.url)


@activity.defn
async def enqueue_landing(request: EnqueueLandingInput) -> EnqueueResult:
    """Put the PR into GitHub's merge queue (FR-002).

    The factory's only merge invocation: `gh pr merge <n> --auto --<method>`.
    A refusal — the queue disabled mid-flight, the spec edge case — comes back as
    `EnqueueResult(rejected=True, reason=…)`, never as a raised crash, so the
    workflow can route it to escalation.
    """
    client = _client(repo_path=request.target_repo)
    try:
        client.enqueue_pr(request.pr_number, merge_method=request.merge_method)
    except GhError as exc:
        return EnqueueResult(rejected=True, reason=exc.stderr_tail or str(exc))
    return EnqueueResult(rejected=False, reason="")


@activity.defn
async def poll_landing(request: PollLandingInput) -> PrSnapshot:
    """One `gh pr view` — the classifier's input."""
    client = _client(repo_path=request.target_repo)
    return client.poll_pr(request.pr_number)


@activity.defn
async def disable_auto_merge(request: DisableAutoMergeInput) -> DisableResult:
    """Take the PR out of the queue — best-effort (FR-008).

    Called on the epic/node kill path so a killed epic does not keep landing. A
    failure is reported, never raised: the kill sequence must not be blocked on
    the queue's availability, and a PR that could not be de-queued is a fact the
    workflow surfaces, not a crash it dies on.
    """
    client = _client(repo_path=request.target_repo)
    try:
        client.disable_auto_merge(request.pr_number)
    except GhError as exc:
        return DisableResult(failed=True, reason=exc.stderr_tail or str(exc))
    return DisableResult(failed=False, reason="")


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
            factory_root=Path(
                os.environ.get(FACTORY_ROOT_ENV) or worktrees.DEFAULT_FACTORY_ROOT
            ),
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


def onboard_target_repo(client: GhClient, target_repo: str) -> TargetRepoProfile:
    """US3's preflight: gather a repo's facts through `client` and judge it (FR-010).

    The fact-gathering half of onboarding — `evaluate_repo` (in
    `factory/mergequeue/onboard.py`) is the pure judgment. This reads the world
    at one moment:

    - the repo's identity, visibility and default branch from `gh repo view`;
    - the merge-queue rule's required checks from the rules API, falling back to
      classic branch protection when the rules list carries none (plan.md § US3);
    - the clone's committed `factory.yaml` via the 002 loader.

    Every `gh` failure is returned as a failed validation with a finding — never
    a pass — and a malformed manifest is a failing `factory_yaml` finding
    carrying the loader's error, never a shrug (FR-010, spec US3 AS2). The
    profile's `passed` is the conjunction of its findings; a failing profile
    blocks dispatch before any key is issued or worktree created (SC-005).

    `client` is injected so both the activity (via the `_client_factory` seam)
    and the offline CLI (`factory-epic onboard`) can drive the same logic against
    whichever `GhClient` their caller wired.
    """
    manifest = Path(target_repo) / "factory.yaml"

    try:
        config = load_factory_config(manifest)
        declared_gates = tuple(config.gates.keys())
        manifest_error = None
    except FactoryConfigError as error:
        declared_gates = ()
        manifest_error = str(error)

    try:
        repo_view = client.repo_view()
        owner_repo = str(repo_view.get("nameWithOwner") or "")
        visibility = str(repo_view.get("visibility") or "")
        # `defaultBranchRef` is an object (`{"name": ...}`), not a bare string —
        # stringifying the dict sent the rules query to a branch named
        # "{'name': 'ergane-buildout'}" on the first real onboarding run.
        default_ref = repo_view.get("defaultBranchRef") or {}
        default_branch = (
            str(default_ref.get("name") or "")
            if isinstance(default_ref, Mapping)
            else str(default_ref)
        )
    except GhError as error:
        return _profile_from_gh_failure(
            target_repo, visibility="", default_branch="", owner_repo="",
            manifest_error=manifest_error, declared_gates=declared_gates,
            error=error,
        )

    try:
        rules = client.rules_for_branch(owner_repo, default_branch)
        queue_enabled, required_checks = _queue_from_rules(rules)
        if required_checks is None:
            # The queue is enabled but carries no checks in the rules payload:
            # fall back to classic branch protection for the required checks.
            try:
                protection = client.classic_branch_protection(
                    owner_repo, default_branch
                )
                required_checks = _classic_contexts(protection)
            except GhError as error:
                if error.kind != GH_NOT_FOUND:
                    raise
                # "Branch not protected" is an answer, not a failure (proved
                # live 2026-08-07): the repo simply configures no checks there.
                required_checks = []
    except GhError as error:
        # The rules call failed — a repo the factory cannot read is not dispatchable.
        return _profile_from_gh_failure(
            target_repo, visibility=visibility, default_branch=default_branch,
            owner_repo=owner_repo, manifest_error=manifest_error,
            declared_gates=declared_gates, error=error,
        )

    return evaluate_repo(
        repo=owner_repo or target_repo,
        default_branch=default_branch,
        visibility=visibility,
        queue_enabled=queue_enabled,
        required_checks=required_checks or (),
        declared_gates=declared_gates,
        factory_yaml_error=manifest_error,
    )


def _queue_from_rules(rules: list[dict[str, Any]]) -> tuple[bool, list[str] | None]:
    """The merge-queue rule from a branch-rules list, and its required checks.

    Returns `(queue_enabled, required_checks)`. In the real rulesets payload
    the required checks ride a *sibling* `required_status_checks` rule (proved
    live 2026-08-07); a queue rule may also embed them, and both places are
    read. `required_checks` is `None` when the queue is enabled but no rule
    names a check (so the caller falls back to classic protection); it is `[]`
    when the queue rule is absent.
    """
    queue_enabled = False
    contexts: list[str] = []
    for rule in rules:
        rule_type = str(rule.get("type") or "")
        parameters = rule.get("parameters")
        if rule_type == "merge_queue":
            queue_enabled = True
        elif rule_type != "required_status_checks":
            continue
        if not isinstance(parameters, dict):
            continue
        checks = parameters.get("required_status_checks")
        if isinstance(checks, list):
            contexts += [
                str(c.get("context") or "") for c in checks if isinstance(c, dict)
            ]
    if not queue_enabled:
        return False, []
    # No rule named a check — the repo may configure them via classic
    # protection, so the caller falls back (plan.md § US3).
    return True, [c for c in contexts if c] or None


def _classic_contexts(protection: dict[str, Any]) -> list[str]:
    """The required-check contexts a classic branch-protection payload names."""
    checks = protection.get("required_status_checks")
    if isinstance(checks, dict):
        contexts = checks.get("contexts")
        if isinstance(contexts, list):
            return [str(c) for c in contexts]
    return []


def _profile_from_gh_failure(
    target_repo: str,
    *,
    visibility: str,
    default_branch: str,
    owner_repo: str,
    manifest_error: str | None,
    declared_gates: tuple[str, ...],
    error: GhError,
) -> TargetRepoProfile:
    """A failed validation from a `gh` refusal — never a pass (FR-010).

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

    detail = f"could not read the repo via gh ({error.kind}): {error.stderr_tail or str(error)}"
    findings = [Finding("repo_read", False, detail)]
    if manifest_error is not None:
        findings.append(
            Finding(
                "factory_yaml",
                False,
                f"factory.yaml failed to load: {manifest_error}",
            )
        )
    return TargetRepoProfile(
        repo=owner_repo or target_repo,
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

    The thin wrapper: builds the `GhClient` through the injectable
    `_client_factory` seam and hands it to `onboard_target_repo`, which both this
    activity and the offline CLI share. Tests script the seam to a `FakeGh`; the
    CLI builds a real client against the clone the operator points at.
    """
    return onboard_target_repo(_client(repo_path=request.target_repo), request.target_repo)
