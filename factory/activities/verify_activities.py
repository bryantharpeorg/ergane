"""The activity surface of verification.

`factory/verify/` is a library of pure functions and one-purpose runners; this
module is where they become things the orchestrator can call, which means it
owns exactly two concerns the library deliberately does not: reading the world
at a known moment, and turning a library exception into an error a workflow can
branch on without reading prose.

`snapshot_criteria` is the first of those calls and the only one that runs
*before* an agent does any work. What it returns is the node's goalposts for the
rest of its life (FR-010) — every later attempt is judged against this value,
not against whatever the spec file says by then — so it stamps the moment it
read and hashes the bytes it read, and the difference between that hash and a
later one is the whole of drift detection (R8).

Its two failure modes are why the parser raises two different exception classes.
A spec the grammar refuses and a spec file that is not there both mean "this
node cannot be verified", but they send an operator to different places: one
goes and edits a requirement, the other fixes a wrong `specs_root` or a
misspelled feature. They come back as `CRITERIA_PARSE_FAILED` and
`CRITERIA_FILE_MISSING` so the workflow can tell them apart. Both are
non-retryable — neither a malformed spec nor an absent file becomes well-formed
by being read again a second later, and the ladder's retry budget exists for
proxies and worktrees, not for typos.

The parse error carries the parser's message verbatim. That message names the
one offending requirement and no sibling, and it is the operator's entire
diagnosis; an error that only said "spec did not parse" would make this activity
strictly less useful than the library call it wraps.

The four activities that follow verify an attempt once the agent has stopped, and
between them they draw the same line twice, in opposite directions:

- **A gate that fails is data.** `run_gates` returns one `GateResult` per declared
  gate whatever they did, and one `CONFIG_ERROR` result for a manifest it cannot
  use, because an exception here would cost the attempt the very output the retry
  prompt quotes (FR-006) and an empty gate list is what a naive verdict reads as
  "nothing failed" (SC-002).
- **A worktree that vanished is not.** `check_output` raises `WORKTREE_MISSING`
  rather than reporting the clean worktree an absent directory resembles:
  charging an infrastructure failure to the agent's attempt budget is the same
  mistake as passing on an empty diff, pointed the other way. `run_judge` draws
  the line in the same place — `JUDGE_UNAVAILABLE` is an outage, and whether it
  becomes a gates-only PASS is `compose_result`'s decision, not this module's.

`record_verification` is the one write. It refuses a row it cannot attribute
before writing anything (the discipline component 1's teardown follows: every
rollup and every escalation summary reads this store by epic and node, so a row
missing one is not thin, it is absent from the query that would have shown the
gap), and it re-hashes the spec file to set `criteria_drift` when the caller has
not already found it — which is what makes drift a fact about the file rather
than a race.

Credentials are conspicuously absent from all of it. The judge authenticates with
the per-attempt virtual key component 1 minted, which arrives in the dispatch;
`LITELLM_MASTER_KEY` sits in the same worker environment and has no path into
these calls (FR-009).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

from factory.verify import diffcheck, gates, judge, store
from factory.verify.criteria import CriteriaParseError, load_criteria
from factory.verify.judge import DEFAULT_MAX_JUDGE_RETRIES
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    JudgeVerdict,
    OutputCheck,
    VerificationResult,
)
from factory.verify.question import (
    QUESTION_HEADING,  # noqa: F401  -- re-exported for the prompt contract (T008)
    QuestionMarker,
    TranscriptReadError,
    detect_operator_question,
)

#: The activity error type for a spec the grammar refuses (spec US1). The
#: message is the parser's, naming the one requirement at fault.
CRITERIA_PARSE_FAILED = "CRITERIA_PARSE_FAILED"

#: The activity error type for a spec file that is not where the dispatch said
#: it would be — a wiring mistake, not a spec to go fix.
CRITERIA_FILE_MISSING = "CRITERIA_FILE_MISSING"

#: The activity error type for a worktree that is not there, or that git refuses
#: to read — infrastructure, not a verdict (contracts/activities.md).
WORKTREE_MISSING = "WORKTREE_MISSING"

#: The activity error type for a proxy that stayed down through the judge's own
#: HTTP retries. Retryable, unlike every other error here: a backend that is down
#: now may be up in a minute.
JUDGE_UNAVAILABLE = "JUDGE_UNAVAILABLE"

#: The activity error type for a verification result no rollup could account for.
ATTRIBUTION_INCOMPLETE = "ATTRIBUTION_INCOMPLETE"

#: The activity error type for a transcript the marker detector could not read
#: (008-US1). Infrastructure, not a verdict: a vanished or unreadable archive must
#: never be read as a clean attempt that happened to ask nothing, so it raises the
#: way `WORKTREE_MISSING` does rather than returning "no question" (FR-010).
DETECT_FAILED = "DETECT_FAILED"

#: The system of record's filename under `<specs_root>/<feature>/` (D-023).
SPEC_FILENAME = "spec.md"

#: Where the evidence store lives when the worker does not say otherwise —
#: beside component 1's ledger under the same `.factory/` (quickstart §5).
DEFAULT_VERIFICATION_DB_PATH = ".factory/verification.db"

VERIFICATION_DB_PATH_ENV = "FACTORY_VERIFICATION_DB_PATH"

#: Pause between the judge's HTTP attempts, at module scope so a test can zero it
#: without waiting out a backoff to prove an outage is an outage.
JUDGE_RETRY_BACKOFF_S = judge.DEFAULT_RETRY_BACKOFF_S

#: The dimensions the evidence store is queried by (FR-002, SC-005) — the ones
#: whose absence a reader cannot detect, because the row is simply not in the
#: answer they got.
_ATTRIBUTION_FIELDS = ("epic_id", "node_id", "spec_ref")


def judge_transport() -> httpx.AsyncBaseTransport | None:
    """The transport the judge's chat completion goes out over (None = the network).

    A seam, not a factory: tests replace it to point the one HTTP call at a fake
    proxy without supplying a credential, so the per-attempt virtual key still has
    to arrive from the dispatch and a wrong one is still refused.
    """
    return None


@dataclass(frozen=True)
class SnapshotCriteriaInput:
    """A node's dispatch, in the terms the criteria parser needs.

    `requirement_keys` is what this node owes — empty means the whole feature,
    which is a legitimate dispatch and must not quietly become "no criteria"
    (a node verified against nothing passes on an empty diff, the very failure
    FR-004 exists to prevent). `spec_ref` is component 1's work-attribution key
    and is carried through untouched: the activity has no business inventing one.
    """

    specs_root: str
    feature: str
    spec_ref: str
    requirement_keys: list[str] = field(default_factory=list)


@activity.defn
async def snapshot_criteria(request: SnapshotCriteriaInput) -> CriteriaSet:
    """Take the node's acceptance criteria from the spec, once (FR-010).

    A pure read and parse, safe for Temporal to retry: two runs against
    unchanged bytes agree on everything but the timestamp.

    Raises `CRITERIA_FILE_MISSING` when there is no `spec.md` at the dispatched
    path, `CRITERIA_PARSE_FAILED` when there is one and the grammar refuses it.
    Both are non-retryable.
    """
    path = spec_path(request.specs_root, request.feature)
    try:
        return load_criteria(
            path,
            feature=request.feature,
            spec_ref=request.spec_ref,
            requirement_keys=request.requirement_keys,
        )
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError) as exc:
        # Every one of these means the same thing to the operator: nothing
        # readable at that path. The path is in the message because the root,
        # the feature name and the filename are all suspects.
        raise ApplicationError(
            f"no feature spec at {path}",
            type=CRITERIA_FILE_MISSING,
            non_retryable=True,
        ) from exc
    except CriteriaParseError as exc:
        # Verbatim: the parser already named the offending requirement and said
        # what is wrong with it, and that is the whole diagnosis.
        raise ApplicationError(
            str(exc),
            type=CRITERIA_PARSE_FAILED,
            non_retryable=True,
        ) from exc


def spec_path(specs_root: str, feature: str) -> Path:
    """The file D-023 designates as the system of record for one feature."""
    return Path(specs_root) / feature / SPEC_FILENAME


# --- gates ------------------------------------------------------------------


@dataclass(frozen=True)
class RunGatesInput:
    """Which worktree to check, and which manifest says how.

    `factory_yaml_path` defaults to the worktree's own committed manifest, which
    is the only shape the factory dispatches; it is settable because conflating
    the two would make an operator's manifest unreadable from anywhere else.
    `timeout_overrides` is the verification config an operator is holding right
    now, and it wins over what the repo declared.
    """

    worktree_path: str
    factory_yaml_path: str | None = None
    timeout_overrides: dict[str, int] = field(default_factory=dict)


class _HeartbeatingExecutor:
    """A gate executor that tells Temporal which gate is starting, then delegates.

    A repo's test suite may legitimately run for the full 600s per-gate deadline,
    so an activity silent until the last gate finished would be killed by its own
    heartbeat timeout long before it had an answer. Reporting sits in the
    `GateExecutor` seam (R3) rather than inside the runner because progress is a
    property of running the gates as an activity, not of running them at all.
    """

    def __init__(
        self, inner: gates.GateExecutor, loop: asyncio.AbstractEventLoop
    ) -> None:
        self._inner = inner
        self._loop = loop

    def run(self, invocation: gates.GateInvocation) -> gates.ExecutionOutcome:
        # This runs inside `asyncio.to_thread`'s worker thread. The activity
        # context rides in on the copied contextvars, but an async activity's
        # heartbeat must be delivered from the event-loop thread — called here
        # it dies in `asyncio.create_task` with no running loop (found live
        # 2026-08-05; the test environment's synchronous heartbeat cannot see
        # the difference). `call_soon_threadsafe` re-enters the loop carrying
        # this thread's context, activity context included — and delivers the
        # beat while the gate below still owns this thread, which is the whole
        # point of beating per gate.
        self._loop.call_soon_threadsafe(activity.heartbeat, invocation.name)
        return self._inner.run(invocation)


@activity.defn
async def run_gates(request: RunGatesInput) -> list[GateResult]:
    """Run the target repo's declared gates and report every one of them (FR-002).

    Never raises for a gate: a non-zero exit, a deadline and an unusable
    `factory.yaml` all come back as `GateResult`s, because failures are the
    evidence the retry prompt quotes and the verdict truth table reads. A missing
    or malformed manifest is one `CONFIG_ERROR` result, never zero results.

    Runs in a worker thread: gates are subprocesses that own the wall clock for as
    long as their deadline allows, and blocking the event loop for ten minutes
    would stall every other activity this worker is running.
    """
    return await asyncio.to_thread(
        gates.run_gates,
        request.worktree_path,
        manifest_path=request.factory_yaml_path,
        executor=_HeartbeatingExecutor(
            gates.SubprocessGateExecutor(), asyncio.get_running_loop()
        ),
        timeout_overrides=request.timeout_overrides,
    )


# --- output check -----------------------------------------------------------


@dataclass(frozen=True)
class CheckOutputInput:
    """The anti-rubber-stamp question, in the terms the persona registry sets.

    `write_scope` crosses this boundary as a plain string (component 1's
    `WriteScope` value) and decides which half of the evidence is the criterion:
    the diff, or the declared artifacts (R7).

    `base_ref` is the node's branch point (D-027): "did the attempt do work" is
    answered against where the node began, because an agent following the inner
    ralph contract commits as it goes — against HEAD, a fully committed attempt
    reads as no work at all, and committed out-of-scope changes read as none.
    The default is R7's original semantics, correct only for a caller that
    knows nothing committed mid-attempt; the epic workflow always passes the
    prepared worktree's real base, and the interpreter suite asserts it does.
    """

    worktree_path: str
    write_scope: str
    base_ref: str = "HEAD"
    expected_artifacts: list[str] = field(default_factory=list)


@activity.defn
async def check_output(request: CheckOutputInput) -> OutputCheck:
    """Decide whether the node proved it did any work at all (FR-004).

    Read-only, and safe to retry. Raises `WORKTREE_MISSING` when the worktree is
    gone or git cannot read it: an absent directory resembles a clean worktree
    exactly, and reporting one would charge an infrastructure failure to the
    agent's attempt budget. It stays retryable for the same reason — a worktree
    the worker could not reach this second is the workflow's retry budget to
    spend, not the ladder's.
    """
    try:
        return await asyncio.to_thread(
            diffcheck.check_output,
            request.worktree_path,
            request.write_scope,
            request.expected_artifacts,
            request.base_ref,
        )
    except diffcheck.WorktreeMissingError as exc:
        # The path travels with the error: by the time an operator reads this
        # they are holding a node id, not a directory.
        raise ApplicationError(str(exc), type=WORKTREE_MISSING) from exc


# --- operator-question detection (008-US1) ----------------------------------


@dataclass(frozen=True)
class DetectQuestionInput:
    """The archived transcript the marker detector reads (D-018's evidence).

    The detector reads ``stdout.log`` from the attempt's transcript directory —
    the same ``AdapterResult.transcript_path`` the adapter points at the archive
    on every termination path. The workflow owns the attribution (epic/node/
    attempt) and the detector owns nothing but the read, so the only input it
    needs is the path. No verdict travels in or out: the marker's only possible
    effect is to park the node, never to grade it (FR-010).
    """

    transcript_path: str


@activity.defn
async def detect_operator_question_activity(
    request: DetectQuestionInput,
) -> QuestionMarker:
    """Scan the archived transcript for the OPERATOR QUESTION marker (008-US1).

    Read-only, and safe to retry. Raises ``DETECT_FAILED`` when the transcript is
    missing or unreadable — the same line ``check_output`` draws for a vanished
    worktree: an absent archive resembles a marker-free attempt exactly, and
    reporting one would let an infrastructure failure masquerade as a clean
    attempt that happened to ask nothing. ``None`` (no marker, or a marker with
    an empty body) is the common case the workflow grades as today; an
    unreadable archive is the one outcome that is neither QUESTION nor the common
    case, and it stays retryable so the workflow's retry budget — not the
    ladder's — spends it.
    """
    try:
        marker = await asyncio.to_thread(
            detect_operator_question, Path(request.transcript_path)
        )
    except TranscriptReadError as exc:
        raise ApplicationError(str(exc), type=DETECT_FAILED) from exc
    return marker if marker is not None else QuestionMarker(is_question=False)


# --- judge ------------------------------------------------------------------


@dataclass(frozen=True)
class RunJudgeInput:
    """One bounded judge invocation (R4).

    `virtual_key` is the per-attempt key component 1 minted for persona `judge`
    and `model_alias` is that persona's registry alias — both arrive in the
    dispatch, because this module reads no credential from the environment and
    code never names a model (constitution V, VII). `judge_attempt` is the
    caller's count: it is what turns an unreadable response into a retry now and
    a FAIL once the cap is reached (SC-003).
    """

    criteria: CriteriaSet
    diff_text: str
    virtual_key: str
    proxy_url: str
    model_alias: str
    judge_attempt: int = 1
    prior_feedback: str | None = None
    max_judge_retries: int = DEFAULT_MAX_JUDGE_RETRIES


@activity.defn
async def run_judge(request: RunJudgeInput) -> JudgeVerdict:
    """Score the node's diff against its dispatched scenarios (FR-003).

    Called only when `judge_required` says a verdict is still open — a node whose
    lint gate failed in two seconds must not cost a completion to find that out.

    A response the strict parser refuses is not an error: it consumes one judge
    attempt and comes back as RETRY, or as FAIL once `judge_attempt` has reached
    the cap, carrying the parse failure as the next prompt's feedback. Only an
    unreachable proxy raises, as `JUDGE_UNAVAILABLE`, and it is retryable —
    falling back to a gates-only verdict is `compose_result`'s decision to make
    after the workflow's retry budget is spent, not this activity's.
    """
    try:
        return await judge.run_judge(
            request.criteria,
            request.diff_text,
            proxy_url=request.proxy_url,
            virtual_key=request.virtual_key,
            model_alias=request.model_alias,
            prior_feedback=request.prior_feedback,
            judge_attempt=request.judge_attempt,
            max_judge_retries=request.max_judge_retries,
            transport=judge_transport(),
            retry_backoff_s=JUDGE_RETRY_BACKOFF_S,
        )
    except judge.JudgeUnavailableError as exc:
        # The library already scrubbed its own message; nothing is added here
        # that was not already safe to write down (FR-009).
        raise ApplicationError(str(exc), type=JUDGE_UNAVAILABLE) from exc


# --- recording --------------------------------------------------------------


@dataclass(frozen=True)
class RecordVerificationInput:
    """One attempt's composed evidence, plus the spec file to re-hash.

    `criteria_source_path` is optional because an interpreter may not be holding
    the path; without it the caller's `criteria_drift` stands, which is the only
    honest answer available when there is nothing left to compare against.
    """

    result: VerificationResult
    criteria_source_path: str | None = None


@dataclass(frozen=True)
class RecordedVerification:
    """What the store did: the row's stable id, and the drift it ended up with.

    `criteria_drift` comes back because the activity may have recomputed it, and
    the caller's next step — the escalation summary, the retry prompt — should
    read the same value the row does.
    """

    row_id: int
    criteria_drift: bool


@activity.defn
async def record_verification(
    request: RecordVerificationInput,
) -> RecordedVerification:
    """Write one attempt's evidence to `.factory/verification.db` (invariant 3).

    Upserts on `(epic_id, node_id, attempt, form)`, so a Temporal re-run lands on
    the first run's row and the returned id is stable.

    Raises `ATTRIBUTION_INCOMPLETE`, before writing anything, for a result that no
    rollup could account for. Non-retryable: the dispatch is wrong, not the
    moment, and a rerun rebuilds exactly the same unaccountable row.
    """
    _require_attribution(request.result)
    result = _with_drift(request.result, request.criteria_source_path)

    with closing(store.connect(_store_path())) as conn:
        row_id = store.upsert_result(conn, result)

    return RecordedVerification(row_id=row_id, criteria_drift=result.criteria_drift)


def _require_attribution(result: VerificationResult) -> None:
    """Refuse a verification row that could never be found again (SC-005).

    Blank counts as absent: the store's `NOT NULL` would accept `""` and every
    per-node query would then report a nameless group. `attempt` is checked the
    same way for the same reason — the DDL's `CHECK (attempt >= 1)` would refuse
    a zero anyway, but as an opaque `IntegrityError` rather than as the name of
    the dimension the dispatch dropped.
    """
    missing = [name for name in _ATTRIBUTION_FIELDS if _is_blank(getattr(result, name))]
    if not isinstance(result.attempt, int) or result.attempt < 1:
        missing.append("attempt")
    if not missing:
        return

    raise ApplicationError(
        f"unattributable verification result for epic {result.epic_id!r} "
        f"node {result.node_id!r}: missing {', '.join(sorted(missing))}",
        type=ATTRIBUTION_INCOMPLETE,
        non_retryable=True,
    )


def _is_blank(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


def _with_drift(
    result: VerificationResult, criteria_source_path: str | None
) -> VerificationResult:
    """Set `criteria_drift` from the spec file's current bytes, if it is still open.

    Drift the caller already found is never cleared: a verifier that watched the
    spec change mid-attempt must not have its finding overwritten by a file that
    has since been restored. The row keeps the *snapshot's* hash either way — the
    node was judged against those bytes (FR-010), and recording the new ones would
    make the evidence agree with a spec this attempt never saw.
    """
    if result.criteria_drift or criteria_source_path is None:
        return result
    return replace(
        result,
        criteria_drift=_has_drifted(Path(criteria_source_path), result.criteria_sha256),
    )


def _has_drifted(source: Path, snapshot_sha256: str) -> bool:
    """Whether the spec file's bytes still hash to the dispatch snapshot's (R8).

    A file that cannot be read is drift, not "no drift detected": a deleted spec
    is the loudest possible form of the system of record moving under a node.
    """
    try:
        current = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError:
        return True
    return current != snapshot_sha256


def _store_path() -> Path:
    return Path(
        os.environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH
    )
