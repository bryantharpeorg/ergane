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
from typing import Any, Callable

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
from factory.mergequeue.models import PrSnapshot
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV
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
