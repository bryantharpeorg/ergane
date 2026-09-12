"""The three activities the orchestrator calls: mint the attempt's key, watch
what it is spending, and record what it spent.

Everything else in this component is a library; this module is where the
promises become the factory's behaviour, so the ordering and the failure
handling here are the design rather than an implementation detail:

- **A poll is a read with no consequence.** `poll_usage` does one `/key/info`
  read and returns the number; nothing branches on the number, at any magnitude,
  because enforcement is deferred (D-021) and SC-005 asks for its absence to be
  observable rather than asserted. It is no longer called per interval — the
  live figure rides the attempt's own heartbeat to teardown (plan US1, FR-001)
  — and the workflow's one remaining call, on a kill, reads the bracket it is
  about to close (FR-003). A failed poll raises the client's own error rather
  than a typed one, since the caller's only correct response is to skip the
  read (contracts/activities.md).
- **Teardown's deliverable is the ledger row, not the proxy call.** The order is
  fixed (R3): read `/key/info`, page the spend logs, write the row, delete the
  key LAST. Deleting last removes any dependence on how the proxy's spend-log
  filters behave once the key is gone, and it means a ledger that refuses the
  row has not yet destroyed the only thing that could still produce it.
- **Completeness is separate from measurement.** Independently measured cost
  and partial token detail survive a failed read. Only stable, consistent usage
  is confirmed; unknown detail stays NULL and partial detail is labelled.
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

import asyncio
import math
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from temporalio import activity
from temporalio.exceptions import ApplicationError

from factory.usage import ledger
from factory.usage.aggregate import aggregate_rows
from factory.env import (
    ERGANE_LEDGER_PATH_ENV,
    FACTORY_LEDGER_PATH_ENV,
    resolve_env_path,
)
from factory.attestation import (
    LaunchRecord,
    RungSelection,
    link_usage,
    record_launch,
    set_launch_outcome,
)
from factory.usage.litellm_client import DEFAULT_KEY_TTL, LiteLLMClient, LiteLLMError
from factory.usage.codex_evidence import read_codex_usage_evidence
from factory.usage.models import (
    AggregatedUsage,
    CodexUsageEvidence,
    CodexUsageRecord,
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

# Three bounded snapshots allow the proxy's asynchronous log writer to catch up.
FINAL_READ_DELAYS = (1.0, 2.0)

#: The dimensions every rollup groups by (FR-006) — the ones whose absence a
#: reader of the ledger cannot detect, because the row simply is not in the
#: answer. The remaining columns may legitimately be unknown; these may not.
_ATTRIBUTION_FIELDS = ("epic_id", "node_id", "persona", "spec_ref")

#: Where the ledger lives when the worker does not say otherwise; the CLI
#: resolves the same default, or an operator's `ergane usage` reads an empty
#: database (contracts/cli.md).
DEFAULT_LEDGER_PATH = ".factory/ledger.db"
DEFAULT_ATTESTATION_PATH = ".factory/attestation.db"

LEDGER_PATH_ENV = "FACTORY_LEDGER_PATH"  # legacy re-export
ERGANE_LEDGER_PATH_ENV = ERGANE_LEDGER_PATH_ENV  # re-export

ATTESTATION_PATH_ENV = "FACTORY_ATTESTATION_DB"  # legacy re-export
ERGANE_ATTESTATION_PATH_ENV = "ERGANE_ATTESTATION_DB"  # re-export

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
    #: US2: the persona's `agent` field decides whether the attempt routes
    #: through the gateway (and needs a virtual key) or through the operator's
    #: subscription. Empty means "look it up from the registry" for backward
    #: compatibility with payloads that predate this field.
    agent: str = ""
    #: 154-US1: the persona's credential route, resolved at dispatch. Read for
    #: the subscription decision (FR-006); empty means a payload that predates
    #: the field, answered from the `agent` sentinel, then the registry.
    route: str = ""
    #: 167-US1: identity supplied in deterministic workflow state. Empty fields
    #: are old payloads and retain the pre-journal behavior.
    target: str = ""
    spec_revision: str = ""
    spec_fingerprint: str = ""
    epic_workflow_id: str = ""
    epic_run_id: str = ""
    invocation_id: str = ""
    launch_ordinal: int = 0
    ladder_ordinal: int = 0
    ladder: tuple[RungSelection, ...] = ()
    transition_reason: str = ""


@dataclass(frozen=True)
class TeardownInput:
    """A terminated attempt: its key, how it ended, and the last thing measured.

    `last_snapshot` is the newest measurement the attempt's own heartbeat read
    (plan US1) and exists solely so a teardown that cannot reach the proxy still
    has a dollar figure to record. It is carried to the row by the workflow on
    the normal and timeout paths and read once more by the workflow on a kill —
    never polled per interval (FR-001). `None` means the proxy was never read —
    the row then carries `NULL` spend rather than a fabricated zero (FR-003,
    FR-005).
    """

    lease: KeyLease
    termination: Termination
    last_snapshot: UsageSnapshot | None = None
    #: 167-US1: the lifecycle outcome supplied by the workflow. None leaves a
    #: launch pending; it never invents an ending.
    launch_outcome: str | None = None
    launch_reason: str | None = None


@dataclass(frozen=True)
class _ConfirmedUsage:
    """Independent cost and token measurements, with explicit completeness."""

    spend_usd: float | None
    aggregate: AggregatedUsage
    status: str = "complete"
    source: str = "gateway"
    cost_basis: str = "proxy_estimate"


def open_client() -> LiteLLMClient:
    """The activities' one route to the proxy, credentials from the environment.

    A seam, not a factory: tests replace it to inject a transport, which is why
    every proxy call below goes through it rather than constructing a client.
    """
    return LiteLLMClient.from_env()


def _is_subscription_persona(request: IssueKeyInput) -> bool:
    """Whether the persona runs against the operator's subscription rather than
    the gateway (US2 FR-005).

    The dispatch now carries the resolved `agent` value, so key issuance does not
    need to reload the persona registry. 154-US1 (FR-006): the route axis
    decides — `effective_route` reads the dispatch's `route` field when it has
    one and answers a pre-field payload from the legacy `agent` sentinel. When
    neither is present (legacy payloads), fall back to the file registry for
    backward compatibility.
    """
    from factory.config import ROUTE_SUBSCRIPTION, load_personas

    if request.route or request.agent:
        from factory.config import effective_route

        return effective_route(request.route, request.agent) == ROUTE_SUBSCRIPTION

    try:
        registry = load_personas()
    except Exception:
        return False
    entry = registry.get(request.persona)
    if entry is None:
        return False
    return entry.route == ROUTE_SUBSCRIPTION


def _is_direct_mode() -> bool:
    """Whether the control plane is configured for direct provider access."""
    from factory.controlplane.config import load_controlplane_config
    from factory.controlplane.resolve import resolve_config_path

    try:
        cfg = load_controlplane_config(resolve_config_path())
    except Exception:
        return False
    return cfg.llm.mode == "direct"


def _direct_credential() -> str:
    """The static credential declared for direct mode, read from the environment.

    Raises `LiteLLMError` when the variable is missing, using the same vocabulary
    `from_env` uses so callers treat a misconfigured direct host the same way.
    """
    from factory.controlplane.config import load_controlplane_config
    from factory.controlplane.resolve import resolve_config_path

    cfg = load_controlplane_config(resolve_config_path())
    assert cfg.llm.direct is not None
    env_name = cfg.llm.direct.api_key_env
    value = os.environ.get(env_name)
    if not value:
        raise LiteLLMError(
            f"{env_name} is not set; it is the credential variable declared for "
            "direct mode in the control-plane config"
        )
    return value


def key_alias_for(
    epic_id: str,
    node_id: str,
    attempt: int,
    persona: str,
    *,
    invocation_id: str = "",
) -> str:
    """The key's identity as the proxy and the ledger both spell it (R1).

    All four dimensions, persona included: the judge scores an attempt while
    the implementer's key is still live (005 closes the agent's bracket only
    after verification), so two personas' keys coexist on one attempt. The
    proxy rejects a duplicate alias outright and the ledger upserts on it —
    an alias without the persona is a failed mint on every scored node, or
    one persona's row silently overwriting the other's.
    """
    alias = f"{epic_id}:{node_id}:{attempt}:{persona}"
    return f"{alias}:{invocation_id}" if invocation_id else alias


@activity.defn
async def issue_attempt_key(request: IssueKeyInput) -> KeyLease:
    """Open the attempt's bracket and return its credential (FR-001, US3 FR-007).

    In `gateway` mode this mints a LiteLLM virtual key. In `direct` mode it
    returns the static provider credential declared in the config. Both paths
    still write the attempt's ledger row, because the row is the record that the
    attempt happened (US2 FR-007).

    A killed epic leaves a deterministic alias orphaned in the proxy. When the
    alias belongs to this epic, the activity recovers by deleting the orphan and
    reissuing — the same retry budget that would have waited out a proxy restart
    instead does the cleanup, with no operator call to the admin API. An alias
    whose `epic_id` is not this epic's is never touched: disturbing a live epic's
    key mid-attempt is the wrong recovery.

    Raises `KEY_ISSUANCE_FAILED` on any failure. The error is marked
    non-retryable only when retrying cannot help — a missing or rejected
    credential, or a live-epic alias collision — so a restarting proxy still
    gets the workflow's ten-minute retry budget (R4).
    """
    alias = key_alias_for(
        request.epic_id,
        request.node_id,
        request.attempt,
        request.persona,
        invocation_id=request.invocation_id,
    )

    actual = RungSelection(
        persona=request.persona,
        runner=request.agent or "<unresolved>",
        route=request.route or "<unknown>",
        model_aliases=tuple(request.models),
        reason=request.transition_reason,
    )
    if request.invocation_id:
        record_launch(
            _journal_path(),
            LaunchRecord(
                target=request.target,
                spec_revision=request.spec_revision,
                spec_fingerprint=request.spec_fingerprint,
                epic_id=request.epic_id,
                epic_workflow_id=request.epic_workflow_id,
                epic_run_id=request.epic_run_id,
                node_id=request.node_id,
                invocation_id=request.invocation_id,
                ladder_ordinal=request.ladder_ordinal or request.attempt,
                launch_ordinal=request.launch_ordinal,
                phase="builder" if request.persona != "judge" else "judge",
                form="launch",
                scoring_job_id=None,
                scoring_call_ordinal=None,
                delivery_id=request.invocation_id,
                key_alias=alias,
                usage_id=None,
                actual_rung=actual,
                ladder=tuple(request.ladder),
                transition_reason=request.transition_reason,
            ),
        )

    # US2 FR-006: subscription-routed personas authenticate through the operator's
    # own credential, not a gateway virtual key. A minted-and-unused key would be
    # a live credential with no purpose and an attribution row that reads zero.
    if _is_subscription_persona(request):
        return KeyLease(
            key="",
            key_alias=alias,
            node_id=request.node_id,
            epic_id=request.epic_id,
            attempt=request.attempt,
            persona=request.persona,
            spec_ref=request.spec_ref,
            issued_at=_now_iso(),
            invocation_id=request.invocation_id,
        )

    if _is_direct_mode():
        try:
            key = _direct_credential()
        except LiteLLMError as exc:
            raise _issuance_failed(exc, permanent=True) from exc
        return KeyLease(
            key=key,
            key_alias=alias,
            node_id=request.node_id,
            epic_id=request.epic_id,
            attempt=request.attempt,
            persona=request.persona,
            spec_ref=request.spec_ref,
            issued_at=_now_iso(),
            invocation_id=request.invocation_id,
        )

    try:
        client = open_client()
    except LiteLLMError as exc:
        # The worker host itself is misconfigured: no amount of waiting fixes it.
        raise _issuance_failed(exc, permanent=True) from exc

    try:
        existing = await _find_key_for_alias(client, alias)
        if existing is not None:
            await _maybe_recover_alias(client, request, existing, alias)
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
        invocation_id=request.invocation_id,
    )


async def _find_key_for_alias(
    client: LiteLLMClient, alias: str
) -> tuple[str, str] | None:
    """The live key currently holding `alias`, if any.

    Returns `(token, hashed_token)` so recovery can read metadata and delete
    without ever needing the raw credential that only the proxy's internal store
    can map back to a token. The alias is the key's identity (R1); `/key/list`
    pages through full objects to resolve alias -> token.
    """
    try:
        aliases = await client.list_key_aliases()
    except LiteLLMError:
        return None
    if alias not in aliases:
        return None

    page = 1
    while True:
        body = await client._call(
            "GET",
            "/key/list",
            params={"return_full_object": "true", "size": 100, "page": page},
        )
        keys = body.get("keys")
        if not isinstance(keys, list):
            return None
        for entry in keys:
            if (
                isinstance(entry, dict)
                and isinstance(entry.get("token"), str)
                and isinstance(entry.get("key_alias"), str)
                and entry["key_alias"] == alias
            ):
                return (entry["token"], entry["token"])
        total_pages = body.get("total_pages")
        if not isinstance(total_pages, int) or page >= total_pages:
            return None
        page += 1


async def _maybe_recover_alias(
    client: LiteLLMClient,
    request: IssueKeyInput,
    existing: tuple[str, str],
    alias: str,
) -> None:
    """Delete an orphaned alias so reissue can succeed, or raise if unsafe.

    The alias is always built from this request's `epic_id` inside
    `issue_attempt_key`, so a collision is either:

    - a closed earlier run of this same workflow id (same epic_id), or
    - this run retrying this activity after the first try already minted a key.

    Both are reclaimable; the second is why recovery must be idempotent. The
    only unsafe case is an alias whose `epic_id` differs from the request's,
    which this call path cannot produce today but is still guarded because a
    future change could.
    """
    token, _hashed = existing
    existing_epic_id = await _key_epic_id(client, token)
    if existing_epic_id != request.epic_id:
        raise _issuance_failed(
            LiteLLMError(
                f"alias {alias!r} is held by a live key for epic {existing_epic_id!r} "
                f"and will not be disturbed",
                status=409,
            ),
            permanent=True,
        )

    # Reclaim: the dead run's ledger row is already immutable, so its spend
    # stays attributable (FR-011). Delete only the live key, not the spend rows.
    # The token from /key/list is the sha256 hash; the proxy accepts it on
    # `/key/delete` and `/key/info` exactly as it does the raw key.
    await _revoke_quietly(client, token)


async def _key_epic_id(client: LiteLLMClient, token: str) -> str | None:
    """The `epic_id` the proxy stored as metadata for the hashed `token`, if readable."""
    try:
        body = await client.get_key_info(token)
    except LiteLLMError:
        return None
    info = body.get("info")
    if not isinstance(info, dict):
        return None
    metadata = info.get("metadata")
    if not isinstance(metadata, dict):
        return None
    epic_id = metadata.get("epic_id")
    return epic_id if isinstance(epic_id, str) else None


@activity.defn
async def poll_usage(lease: KeyLease) -> UsageSnapshot:
    """Read what the attempt has spent so far (FR-007, R9).

    Called by the workflow on a kill, once, to close the bracket with a real
    reading where the SDK surfaces no heartbeat details on a cancellation the
    workflow itself requested (plan US1, FR-003). The attempt's own heartbeat —
    not a per-interval workflow poll — is what carries the live figure to
    teardown on the normal and timeout paths (FR-001). It stays this small: one
    `/key/info`, no spend-log paging, no write. Token detail is aggregated once,
    at teardown (R2).

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
    from factory.activities.agent_activities import factory_root

    codex_usage = read_codex_usage_evidence(factory_root(), request.lease)
    if _is_subscription_lease(request.lease):
        from factory.usage.runner import read_attempt_usage

        if codex_usage is not None:
            reading = _codex_reading(codex_usage)
        else:
            measured = read_attempt_usage(factory_root(), request.lease)
            reading = None if measured is None else _ConfirmedUsage(
                spend_usd=None, aggregate=measured.aggregate, status=measured.status,
                source=measured.source, cost_basis="unknown",
            )
        record = _record_for(request, reading)
        _require_attribution(record)
        with closing(ledger.connect(_ledger_path())) as conn:
            record = ledger.upsert_record(conn, record)
            _store_codex_corroboration(conn, codex_usage, record)
            _record_launch_usage(request.lease, record.id)
            _complete_launch(request)
            return record

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
            _store_codex_corroboration(conn, codex_usage, stored)
            _record_launch_usage(request.lease, stored.id)
            _complete_launch(request)

        if client is not None:
            await _revoke_quietly(client, request.lease.key)
    finally:
        if client is not None:
            await client.aclose()

    return stored


def _record_launch_usage(lease: KeyLease, usage_id: int | None) -> None:
    """Link durable usage to a launch when it carries a supplied identity."""
    if not lease.invocation_id:
        return
    link_usage(_journal_path(), lease.invocation_id, usage_id)


def _complete_launch(request: TeardownInput) -> None:
    lease = request.lease
    if not lease.invocation_id or request.launch_outcome is None:
        return
    set_launch_outcome(
        _journal_path(),
        lease.invocation_id,
        request.launch_outcome,
        request.launch_reason,
    )


async def _read_final_usage(
    client: LiteLLMClient | None, lease: KeyLease
) -> _ConfirmedUsage | None:
    """Read cost independently; bound retries and require stable usable detail.

    A successful HTTP response is not evidence of a complete request log. The
    proxy writes asynchronously and historically discarded duplicate provider IDs.
    """
    if client is None:
        return None
    spend: float | None = None
    best = aggregate_rows([])
    previous: AggregatedUsage | None = None
    for delay in (0.0, *FINAL_READ_DELAYS):
        if delay:
            await asyncio.sleep(delay)
        try:
            spend = await client.get_spend(lease.key)
        except LiteLLMError as error:
            if error.status in (401, 403, 404):
                break
        try:
            rows = await client.fetch_spend_log_rows(lease.key, issued_at=lease.issued_at)
        except LiteLLMError:
            previous = None
            continue
        current = aggregate_rows(rows)
        best = max(best, current, key=_measurement_quality)
        usable = bool(rows) and all(
            isinstance(row.get(field), int) and not isinstance(row.get(field), bool) and row[field] >= 0
            for row in rows for field in ("prompt_tokens", "completion_tokens")
        )
        consistent = spend is not None and math.isclose(current.spend_usd, spend, rel_tol=1e-6, abs_tol=1e-8)
        if usable and consistent and current == previous:
            return _ConfirmedUsage(spend, current)
        previous = current
    if spend is None and best.request_count is None:
        return None
    status = "partial" if best.prompt_tokens is not None or best.completion_tokens is not None else "unknown"
    return _ConfirmedUsage(spend, best, status=status)


def _measurement_quality(value: AggregatedUsage) -> tuple[int, int, int]:
    return (
        int(value.prompt_tokens is not None) + int(value.completion_tokens is not None),
        value.request_count or 0,
        int(value.cache_read_tokens is not None) + int(value.cache_write_tokens is not None),
    )


def _codex_reading(usage: CodexUsageEvidence) -> _ConfirmedUsage:
    """Map CLI counts to the accounting model without inventing a request."""

    aggregate = AggregatedUsage(
        prompt_tokens=usage.input_tokens,
        completion_tokens=usage.output_tokens,
        cache_read_tokens=usage.cached_input_tokens,
        cache_write_tokens=None,
        request_count=None,
        spend_usd=0.0,
    )
    if usage.complete:
        status = "complete"
    elif usage.input_tokens is not None or usage.output_tokens is not None:
        status = "partial"
    else:
        status = "unknown"
    return _ConfirmedUsage(
        spend_usd=None,
        aggregate=aggregate,
        status=status,
        source="codex_cli",
        cost_basis="unknown",
    )


def _store_codex_corroboration(
    conn: sqlite3.Connection,
    usage: CodexUsageEvidence | None,
    record: UsageRecord,
) -> None:
    """Store CLI counts beside, never inside, the authoritative row."""

    if usage is None:
        return
    ledger.upsert_codex_usage(
        conn,
        CodexUsageRecord(
            key_alias=record.key_alias,
            input_tokens=usage.input_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            output_tokens=usage.output_tokens,
            reasoning_output_tokens=usage.reasoning_output_tokens,
            source=usage.source,
            complete=usage.complete,
            reason=usage.reason,
        ),
    )


def _is_subscription_lease(lease: KeyLease) -> bool:
    """Whether the lease belongs to a subscription-routed attempt.

    The key is empty for subscription personas (US2 FR-006).  That is the only
    signal: the persona name is operator-configured, while an empty key is the
    contract this component wrote.
    """
    return lease.key == ""


def _record_for(
    request: TeardownInput, confirmed: _ConfirmedUsage | None
) -> UsageRecord:
    """Build the ledger row from whatever the proxy was willing to tell us.

    The dimensions come from the lease — the proxy does not carry persona or
    spec_ref back (R1), so attribution is factory-side by construction.

    Subscription readings come from archived runner telemetry and never carry
    a per-attempt monetary charge. Gateway cost and token detail are preserved
    independently; completeness belongs to the reading's status.
    """
    lease = request.lease
    snapshot = request.last_snapshot

    if confirmed is None:
        usage = {
            "prompt_tokens": None, "completion_tokens": None,
            "cache_read_tokens": None, "cache_write_tokens": None, "request_count": None,
            "spend_usd": snapshot.spend_usd if snapshot is not None and lease.key else None,
        }
        status = "unknown"
        source = "gateway" if lease.key else "unknown"
        cost_basis = "proxy_estimate" if usage["spend_usd"] is not None else "unknown"
    else:
        aggregate = confirmed.aggregate
        usage = {
            "prompt_tokens": aggregate.prompt_tokens,
            "completion_tokens": aggregate.completion_tokens,
            "cache_read_tokens": aggregate.cache_read_tokens,
            "cache_write_tokens": aggregate.cache_write_tokens,
            "request_count": aggregate.request_count,
            "spend_usd": confirmed.spend_usd if confirmed.spend_usd is not None else (
                snapshot.spend_usd if snapshot is not None and lease.key else None
            ),
        }
        status, source, cost_basis = confirmed.status, confirmed.source, confirmed.cost_basis

    return UsageRecord(
        epic_id=lease.epic_id,
        node_id=lease.node_id,
        attempt=lease.attempt,
        persona=lease.persona,
        spec_ref=lease.spec_ref,
        key_alias=lease.key_alias,
        final_usage_confirmed=status == "complete",
        usage_status=status,
        usage_source=source,
        cost_basis=cost_basis,
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

    `key` may be the raw credential or the hashed token returned by
    `/key/list`; the proxy accepts both on `/key/delete` (US3 FR-007).

    Revocation is last because it is the only step whose failure something else
    already covers: the key's TTL expires it within a day either way (R5).
    Raising here would fail an activity whose row is already durable, and
    Temporal would then re-run a teardown that has nothing left to do.
    """
    try:
        await client.revoke_key_by_tokens([key])
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
    return resolve_env_path(
        ERGANE_LEDGER_PATH_ENV,
        FACTORY_LEDGER_PATH_ENV,
        DEFAULT_LEDGER_PATH,
    )


def _journal_path() -> Path:
    return resolve_env_path(
        ERGANE_ATTESTATION_PATH_ENV,
        ATTESTATION_PATH_ENV,
        DEFAULT_ATTESTATION_PATH,
    )


def _now_iso() -> str:
    """ISO 8601 UTC, to the second — the ledger's timestamp format (FR-012)."""
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
