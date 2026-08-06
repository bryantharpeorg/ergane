"""The three activities the orchestrator calls: mint the attempt's key, watch
what it is spending, and record what it spent.

Everything else in this component is a library; this module is where the
promises become the factory's behaviour, so the ordering and the failure
handling here are the design rather than an implementation detail:

- **A poll is a read with no consequence.** `poll_usage` is the only activity
  here that runs while an attempt is alive, which makes it the only place a
  budget could accidentally be enforced. It does one `/key/info` read per beat
  (R9) and returns the number; nothing branches on the number, at any
  magnitude, because enforcement is deferred (D-021) and SC-005 asks for its
  absence to be observable rather than asserted. A failed poll raises the
  client's own error rather than a typed one, since the caller's only correct
  response is to skip the beat (contracts/activities.md).
- **Teardown's deliverable is the ledger row, not the proxy call.** The order is
  fixed (R3): read `/key/info`, page the spend logs, write the row, delete the
  key LAST. Deleting last removes any dependence on how the proxy's spend-log
  filters behave once the key is gone, and it means a ledger that refuses the
  row has not yet destroyed the only thing that could still produce it.
- **A partial reading is not a reading.** If either read fails, the whole
  confirmed path is abandoned for the flagged fallback — the last heartbeat's
  dollar figure, `NULL` tokens, `final_usage_confirmed = 0`. Mixing a confirmed
  spend with absent token detail would publish a row that looks measured and is
  not (FR-005).
- **An anonymous row is worse than no row.** The one thing teardown will not
  degrade to is a row it cannot attribute. Every rollup groups by epic, node,
  persona or spec_ref (FR-006), so a row missing one of them does not merely
  lack detail — it lands in no group and makes the totals an operator reads
  quietly too small. `ATTRIBUTION_INCOMPLETE` raises before the write, and
  therefore before the revocation, so the attempt's usage survives on a live key
  until the dispatch that dropped the dimension is fixed (SC-003).
- **Only the ledger's own failure is fatal.** An unreadable proxy costs the
  detail; a failed revocation costs nothing the 24h TTL does not already cover
  (R5). Both still write the row. A failed *write* propagates unwrapped, because
  Temporal retrying the activity is the only thing that can still make "exactly
  one row per attempt" (SC-001) true.
- **Issuance failure is not an attempt.** A proxy that will not mint a key
  raises `KEY_ISSUANCE_FAILED` (R4) and writes nothing: no key, no usage, and no
  row invented out of an outage. The activity never loops — the retry budget
  belongs to the workflow's policy (contracts/activities.md) — but it does
  distinguish a transient proxy from a misconfigured worker host, which no
  amount of retrying will fix.
- **The master key never leaves the worker host.** It reaches the proxy through
  `LiteLLMClient.from_env` and appears in no input, no lease, no record and no
  error (FR-009).

`open_client` exists as a module-level seam so tests can supply a transport
without supplying a credential: `from_env` still resolves the master key from
the environment, so a worker without one still fails.
"""

from __future__ import annotations

import os
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from temporalio import activity
from temporalio.exceptions import ApplicationError

from factory.usage import ledger
from factory.usage.aggregate import aggregate_rows
from factory.usage.litellm_client import DEFAULT_KEY_TTL, LiteLLMClient, LiteLLMError
from factory.usage.models import (
    AggregatedUsage,
    KeyLease,
    Termination,
    UsageRecord,
    UsageSnapshot,
)

#: The activity error type that tells the interpreter "no agent ever started"
#: (R4). Distinct from agent failure so infrastructure blips stay out of
#: agent-quality statistics.
KEY_ISSUANCE_FAILED = "KEY_ISSUANCE_FAILED"

#: The activity error type for a teardown whose lease cannot say whose usage it
#: is (SC-003). Non-retryable by construction: the dimensions arrive with the
#: dispatch, so a rerun rebuilds exactly the same unattributable row.
ATTRIBUTION_INCOMPLETE = "ATTRIBUTION_INCOMPLETE"

#: The dimensions every rollup groups by (FR-006) — the ones whose absence a
#: reader of the ledger cannot detect, because the row simply is not in the
#: answer. The remaining columns may legitimately be unknown; these may not.
_ATTRIBUTION_FIELDS = ("epic_id", "node_id", "persona", "spec_ref")

#: Where the ledger lives when the worker does not say otherwise; the CLI
#: resolves the same default, or an operator's `factory-usage` reads an empty
#: database (contracts/cli.md).
DEFAULT_LEDGER_PATH = ".factory/ledger.db"

LEDGER_PATH_ENV = "FACTORY_LEDGER_PATH"

#: A credential the proxy rejected is a worker-host misconfiguration; retrying
#: it for ten minutes only delays the diagnosis.
_CREDENTIAL_REJECTED = frozenset({401, 403})


@dataclass(frozen=True)
class IssueKeyInput:
    """A dispatch: which attempt is starting, and what it may call.

    `models` is the persona's allowed list (R8) — the key is model-constrained,
    never capped (D-021). `ttl` is the backstop against teardown never running
    (R5), overridable per dispatch.
    """

    node_id: str
    epic_id: str
    attempt: int
    persona: str
    spec_ref: str
    models: list[str] = field(default_factory=list)
    ttl: str = DEFAULT_KEY_TTL


@dataclass(frozen=True)
class TeardownInput:
    """A terminated attempt: its key, how it ended, and the last thing measured.

    `last_snapshot` is the newest heartbeat read (R9) and exists solely so a
    teardown that cannot reach the proxy still has a dollar figure to record.
    `None` means no poll ever succeeded — the row then carries `NULL` spend
    rather than a fabricated zero (FR-005).
    """

    lease: KeyLease
    termination: Termination
    last_snapshot: UsageSnapshot | None = None


@dataclass(frozen=True)
class _ConfirmedUsage:
    """Both halves of a successful final reading (R3 steps 1–2).

    They answer different questions and the row needs both: the key's own
    counter is the attempt's authoritative dollar total, and the per-request
    rows are the only place token and cache detail exists (R2).
    """

    spend_usd: float
    aggregate: AggregatedUsage


def open_client() -> LiteLLMClient:
    """The activities' one route to the proxy, credentials from the environment.

    A seam, not a factory: tests replace it to inject a transport, which is why
    every proxy call below goes through it rather than constructing a client.
    """
    return LiteLLMClient.from_env()


def key_alias_for(epic_id: str, node_id: str, attempt: int, persona: str) -> str:
    """The key's identity as the proxy and the ledger both spell it (R1).

    All four dimensions, persona included: the judge scores an attempt while
    the implementer's key is still live (005 closes the agent's bracket only
    after verification), so two personas' keys coexist on one attempt. The
    proxy rejects a duplicate alias outright and the ledger upserts on it —
    an alias without the persona is a failed mint on every scored node, or
    one persona's row silently overwriting the other's.
    """
    return f"{epic_id}:{node_id}:{attempt}:{persona}"


@activity.defn
async def issue_attempt_key(request: IssueKeyInput) -> KeyLease:
    """Mint the attempt's virtual key (FR-001).

    Raises `KEY_ISSUANCE_FAILED` on any failure. The error is marked
    non-retryable only when retrying cannot help — a missing or rejected
    credential — so a restarting proxy still gets the workflow's ten-minute
    retry budget (R4).
    """
    try:
        client = open_client()
    except LiteLLMError as exc:
        # The worker host itself is misconfigured: no amount of waiting fixes it.
        raise _issuance_failed(exc, permanent=True) from exc

    alias = key_alias_for(
        request.epic_id, request.node_id, request.attempt, request.persona
    )
    try:
        key = await client.issue_key(
            key_alias=alias,
            models=request.models,
            metadata={
                "node_id": request.node_id,
                "epic_id": request.epic_id,
                "attempt": request.attempt,
                "persona": request.persona,
                "spec_ref": request.spec_ref,
            },
            ttl=request.ttl,
        )
    except LiteLLMError as exc:
        raise _issuance_failed(
            exc, permanent=exc.status in _CREDENTIAL_REJECTED
        ) from exc
    finally:
        await client.aclose()

    return KeyLease(
        key=key,
        key_alias=alias,
        node_id=request.node_id,
        epic_id=request.epic_id,
        attempt=request.attempt,
        persona=request.persona,
        spec_ref=request.spec_ref,
        issued_at=_now_iso(),
    )


@activity.defn
async def poll_usage(lease: KeyLease) -> UsageSnapshot:
    """Read what the attempt has spent so far (FR-007, R9).

    Called on the agent activity's heartbeat, roughly every 30s per live
    attempt, which makes it the most-executed proxy call in the component and
    the reason it stays this small: one `/key/info`, no spend-log paging, no
    write. Token detail is aggregated once, at teardown (R2).

    The returned snapshot is the attempt's latest-known state and teardown's
    fallback, so it carries the moment it was true — a value the ledger may
    record hours later is only honest if its staleness is visible.

    Raises `LiteLLMError` on any failure, deliberately untyped and unwrapped: a
    missed beat is the caller's to skip, and failing an attempt over an
    unreadable observability endpoint would be exactly the enforcement side
    effect SC-005 forbids. Nothing here inspects `spend_usd`.
    """
    client = open_client()
    try:
        spend_usd = await client.get_spend(lease.key)
    finally:
        await client.aclose()

    return UsageSnapshot(spend_usd=spend_usd, captured_at=_now_iso())


@activity.defn
async def teardown_attempt(request: TeardownInput) -> UsageRecord:
    """Record the attempt's usage and revoke its key (FR-002/003/005, R3).

    Returns the row as persisted, `id` included. Idempotent: the ledger upserts
    on `key_alias`, so a teardown Temporal ran twice lands on the first run's
    row, and revoking an already-absent key is a normal outcome.
    """
    client: LiteLLMClient | None
    try:
        client = open_client()
    except LiteLLMError:
        # Unreachable proxy, same as an unreadable one: the row is still owed.
        client = None

    try:
        confirmed = await _read_final_usage(client, request.lease)
        record = _record_for(request, confirmed)
        _require_attribution(record)

        # Before the key dies, so a ledger that refuses the row leaves the
        # attempt's usage still readable from the proxy (R3).
        with closing(ledger.connect(_ledger_path())) as conn:
            stored = ledger.upsert_record(conn, record)

        if client is not None:
            await _revoke_quietly(client, request.lease.key)
    finally:
        if client is not None:
            await client.aclose()

    return stored


async def _read_final_usage(
    client: LiteLLMClient | None, lease: KeyLease
) -> _ConfirmedUsage | None:
    """The confirmed reading, or `None` if any part of it failed (R3 steps 1–2).

    The spend logs are read only once `/key/info` has answered: a key the proxy
    no longer knows is a key whose spend-log filters can no longer be trusted to
    resolve, so a dead key short-circuits to the fallback rather than to an
    empty row set that would look like an attempt which never called anything.
    """
    if client is None:
        return None
    try:
        spend_usd = await client.get_spend(lease.key)
        rows = await client.fetch_spend_log_rows(lease.key, issued_at=lease.issued_at)
    except LiteLLMError:
        return None
    return _ConfirmedUsage(spend_usd=spend_usd, aggregate=aggregate_rows(rows))


def _record_for(
    request: TeardownInput, confirmed: _ConfirmedUsage | None
) -> UsageRecord:
    """Build the ledger row from whatever the proxy was willing to tell us.

    The dimensions come from the lease — the proxy does not carry persona or
    spec_ref back (R1), so attribution is factory-side by construction.
    """
    lease = request.lease
    snapshot = request.last_snapshot

    if confirmed is None:
        # Flagged, not fabricated: the tokens are unknown and say so, and the
        # dollar figure is the last one actually measured (FR-005).
        usage: dict[str, int | float | None] = {
            "prompt_tokens": None,
            "completion_tokens": None,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
            "request_count": None,
            "spend_usd": snapshot.spend_usd if snapshot is not None else None,
        }
    else:
        aggregate = confirmed.aggregate
        usage = {
            "prompt_tokens": aggregate.prompt_tokens,
            "completion_tokens": aggregate.completion_tokens,
            "cache_read_tokens": aggregate.cache_read_tokens,
            "cache_write_tokens": aggregate.cache_write_tokens,
            "request_count": aggregate.request_count,
            # The key's own counter, not the row sum: `/key/info` is the
            # contract's final spend, and the rows are the token detail (R2).
            "spend_usd": confirmed.spend_usd,
        }

    return UsageRecord(
        epic_id=lease.epic_id,
        node_id=lease.node_id,
        attempt=lease.attempt,
        persona=lease.persona,
        spec_ref=lease.spec_ref,
        key_alias=lease.key_alias,
        final_usage_confirmed=confirmed is not None,
        termination=request.termination,
        issued_at=lease.issued_at,
        torn_down_at=_now_iso(),
        **usage,
    )


def _require_attribution(record: UsageRecord) -> None:
    """Refuse a row that no rollup could ever account for (SC-003).

    This is the one failure teardown does not absorb into a flagged row. A
    fallback row is a real measurement with unknown detail, and an operator can
    see it is unconfirmed; a row with no persona is invisible in exactly the
    query that would have revealed the gap. Raising leaves the caller — the only
    party that knows the attempt's dimensions — to fix the dispatch, and because
    nothing has been written or deleted yet, the usage is still there to record
    when they do.

    Blank counts as absent: the ledger's `NOT NULL` constraints would accept
    `""` and every rollup would then report a nameless group.
    """
    missing = [name for name in _ATTRIBUTION_FIELDS if _is_blank(getattr(record, name))]
    if not missing:
        return

    raise ApplicationError(
        f"unattributable usage record for key alias {record.key_alias!r}: "
        f"missing {', '.join(missing)}",
        type=ATTRIBUTION_INCOMPLETE,
        # The dispatch is wrong, not the moment: retrying reproduces it exactly.
        non_retryable=True,
    )


def _is_blank(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


async def _revoke_quietly(client: LiteLLMClient, key: str) -> None:
    """Delete the attempt's key, tolerating every way that can fail.

    Revocation is last because it is the only step whose failure something else
    already covers: the key's TTL expires it within a day either way (R5).
    Raising here would fail an activity whose row is already durable, and
    Temporal would then re-run a teardown that has nothing left to do.
    """
    try:
        await client.revoke_key(key)
    except LiteLLMError:
        pass


def _issuance_failed(exc: LiteLLMError, *, permanent: bool) -> ApplicationError:
    """The R4 error, carrying the proxy's (already credential-free) explanation."""
    return ApplicationError(
        f"key issuance failed: {exc}",
        type=KEY_ISSUANCE_FAILED,
        non_retryable=permanent,
    )


def _ledger_path() -> Path:
    return Path(os.environ.get(LEDGER_PATH_ENV) or DEFAULT_LEDGER_PATH)


def _now_iso() -> str:
    """ISO 8601 UTC, to the second — the ledger's timestamp format (FR-012)."""
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
