"""The types every other module in this component speaks.

One dataclass per entity in data-model.md, frozen so a value that crossed an
activity boundary can never be edited in place, and plain enough that Temporal's
default JSON converter round-trips them without help.

Two invariants show up here as types rather than as checks:

- `None` means *unknown*, and only ever that. Token and spend fields are
  optional precisely where the data may not exist — the proxy never reported the
  metric, or teardown never got a confirmed read — and code that fills them with
  0 has fabricated usage (FR-005, principle V). Zero is a real measurement.
- Enforcement is not modelled. `Termination` has no `BUDGET_BREACH` member and
  `KeyLease` carries no cap, because caps are deferred to spec 004 (D-021).

Validation lives where the decision is made, not here: teardown rejects a record
with missing attribution (SC-003), the ledger's CHECK constraints backstop the
persisted shape, and these stay dumb carriers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Termination(StrEnum):
    """How an attempt ended (FR-008); persisted as the lowercase value.

    A `str` subclass so a member serializes as its value in Temporal payloads and
    binds directly as a SQLite TEXT parameter. `StrEnum` specifically, not the
    older `class X(str, Enum)` spelling: both satisfy those two, but only
    `StrEnum` is recognised by the payload converter's *deserializer*, which
    rebuilds a field annotated with any other str-subclass enum as a list of
    one-character strings — a `TIMEOUT` that arrives as `['t', 'i', ...]` and
    compares equal to nothing. The distinction is invisible until a value crosses
    a real activity boundary in both directions, which is what the interpreter
    does with every attempt: the adapter classifies a termination, hands it back
    to the workflow, and the workflow hands it on to teardown and to the salvage
    commit's subject.
    """

    COMPLETED = "completed"
    AGENT_ERROR = "agent_error"
    TIMEOUT = "timeout"
    KILLED = "killed"
    #: The one termination the workflow derives rather than the adapter: an
    #: attempt whose final message carried the `## OPERATOR QUESTION` marker
    #: (008-US1, the narrowest hole in D-018/FR-012). The adapter still classifies
    #: the process's own fate (completed/agent_error/timeout/killed); the workflow
    #: reads the marker from the archived transcript and reclassifies the attempt
    #: QUESTION. Its ladder routing is park — never a verdict — so it is the one
    #: termination that does not run the gates (FR-010).
    QUESTION = "question"


@dataclass(frozen=True)
class KeyLease:
    """One virtual key bound to one node attempt (R1) — a Temporal payload.

    `key` is a capped-scope credential and is allowed to travel in payloads; the
    proxy master key is not, and never appears on this type (FR-009).

    `(epic_id, node_id, attempt, persona)` is the key's identity everywhere in
    this component, and `key_alias` is its
    `"{epic_id}:{node_id}:{attempt}:{persona}"` rendering — the ledger's
    uniqueness key, so re-teardown upserts instead of duplicating. Persona is
    part of the identity because two personas' keys coexist on one attempt:
    the judge scores while the implementer's key is still live (D-026).
    """

    key: str
    key_alias: str
    node_id: str
    epic_id: str
    attempt: int
    persona: str
    spec_ref: str
    issued_at: str


@dataclass(frozen=True)
class UsageSnapshot:
    """A point-in-time `/key/info` read (R9) — heartbeat state, and the value
    teardown falls back to when the final read fails.

    Observability only: nothing in this component may branch on `spend_usd`
    (SC-005). `spend_usd` is proxy-computed and is legitimately 0.0 for models
    the proxy has no price for — which is why "no snapshot at all" is `None`
    rather than a zeroed snapshot.
    """

    spend_usd: float
    captured_at: str


@dataclass(frozen=True)
class AggregatedUsage:
    """Spend-log rows for one key, summed (R2) — internal, never persisted raw.

    The cache fields are `None` when the metric was absent from *every* row, and
    a sum when it was present on any: an attempt that genuinely read no cache
    reports 0, an attempt whose backend does not report cache reports nothing
    (FR-004).
    """

    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    request_count: int
    spend_usd: float


@dataclass(frozen=True)
class UsageRecord:
    """The ledger row: exactly one per attempt teardown (FR-003).

    Mirrors `usage_records` in contracts/ledger-schema.sql column for column.
    Two type mappings are worth naming: `final_usage_confirmed` is a bool here
    and the DDL's 0/1 INTEGER there, and `termination` is the enum here and its
    lowercase value there.

    On the confirmed path every field is populated from proxy data. On the
    fallback path `final_usage_confirmed` is False, `spend_usd` comes from the
    last snapshot (or is `None` if there never was one), and the token fields
    stay `None` — the row exists, flagged, rather than being invented (FR-005).

    `id` is assigned by SQLite, so it is `None` until the row has been written.
    """

    epic_id: str
    node_id: str
    attempt: int
    persona: str
    spec_ref: str
    key_alias: str
    prompt_tokens: int | None
    completion_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    request_count: int | None
    spend_usd: float | None
    final_usage_confirmed: bool
    termination: Termination
    issued_at: str
    torn_down_at: str
    id: int | None = None
