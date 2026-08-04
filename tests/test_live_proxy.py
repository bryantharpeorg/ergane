"""The one test that talks to a real LiteLLM proxy.

Every other test in this suite runs against `FakeLiteLLM`, which is a statement
about what the proxy *does*, written by the same person who wrote the client that
consumes it. That is enough to pin behaviour and nothing at all to pin reality:
if LiteLLM renames `additional_usage_values`, pages `/spend/logs/v2` differently,
or stops accepting a `/key/generate` body with no `max_budget`, the fake keeps
agreeing with the client and the ledger quietly fills with wrong numbers. This
file is the one place that checks the agreement against the real thing (SC-002).

What it does, once, per quickstart §2: issues a real uncapped key through
`issue_attempt_key`, makes one tiny completion on it, waits for the proxy to
flush its spend logs, tears the attempt down, and then compares the ledger row
against a raw HTTP read of the proxy's own records.

Three deliberate choices:

- **The reconciliation source is raw HTTP, not this component's client.** The
  rows the assertions compare against are read with a plain `httpx` request and
  summed with plain arithmetic in this file. Reconciling `fetch_spend_log_rows`
  against `aggregate_rows` would only prove they agree with each other, which the
  fake already proves.
- **The proxy is hit once.** A live journey costs an operator real time and a
  fraction of a cent, so the module-scoped `attempt` fixture runs it a single time
  and every test below asserts a different facet of the same journey.
- **It skips, it does not fail, when the environment is absent.** No
  `LITELLM_PROXY_URL`/`LITELLM_MASTER_KEY` means the operator did not ask for a
  live run; `uv run pytest -q` stays a pure-unit suite. `-m live_proxy` selects
  this file, and `LITELLM_SMOKE_MODEL` names the model to call — otherwise the
  first model the proxy advertises is used, which one `max_tokens=1` completion
  makes affordable on any backend.

The one thing this file cannot degrade around is spend-log persistence: without
it the proxy has no per-request rows and there is nothing to reconcile with. That
is a documented deployment assumption (spec.md § Assumptions), so its absence
fails loudly here rather than skipping quietly.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities.usage_activities import (
    LEDGER_PATH_ENV,
    IssueKeyInput,
    TeardownInput,
    issue_attempt_key,
    poll_usage,
    teardown_attempt,
)
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from tests.conftest import CACHE_READ_FIELD, CACHE_WRITE_FIELD

#: Selected with `-m live_proxy`, deselected with `-m "not live_proxy"`; skipped
#: outright without proxy credentials (see `live_config`).
pytestmark = pytest.mark.live_proxy

#: Which model the smoke completion calls. Optional: without it the first model
#: the proxy advertises is used.
MODEL_ENV = "LITELLM_SMOKE_MODEL"

NODE = "live-smoke"
ATTEMPT = 1
PERSONA = "researcher"
SPEC_REF = "001-usage-tracking/SC-002"

#: Far below R5's 24h default: this key exists for the length of one completion,
#: and a smoke run that dies before its teardown should not leave a day-long
#: credential on the operator's proxy.
SMOKE_TTL = "10m"

#: LiteLLM writes spend logs from a batching worker, so the row for a completion
#: that has already returned does not exist yet. This is the wait for it, not a
#: request timeout.
SPEND_LOG_TIMEOUT_SECONDS = 90.0
SPEND_LOG_POLL_SECONDS = 2.0

#: Generous enough for a cold local model to load.
COMPLETION_TIMEOUT_SECONDS = 120.0

#: One `max_tokens=1` answer to a one-word prompt — the smallest real call that
#: still produces prompt tokens, completion tokens and a priced row.
SMOKE_PROMPT = "ping"


@dataclass(frozen=True)
class LiveConfig:
    """The operator's proxy, as the environment describes it."""

    base_url: str
    master_key: str
    model: str


@dataclass(frozen=True)
class LiveAttempt:
    """Everything one live journey produced, for the assertions below to read."""

    lease: KeyLease
    issued_info: dict[str, Any]
    completion: dict[str, Any]
    #: The proxy's own per-request records, read raw — the reconciliation source.
    proxy_rows: list[dict[str, Any]]
    #: `/key/info` spend at the moment teardown was about to run.
    proxy_spend_usd: float
    snapshot: UsageSnapshot
    record: UsageRecord
    #: `/key/info` status after teardown; 404 is the key having been revoked.
    key_info_status_after: int
    ledger_path: Path
    master_key: str
    model: str


# --- environment -----------------------------------------------------------


@pytest.fixture(scope="module")
def live_config() -> LiveConfig:
    """The live proxy, or a skip when the operator did not point us at one."""
    base_url = os.environ.get(PROXY_URL_ENV)
    master_key = os.environ.get(MASTER_KEY_ENV)
    if not base_url or not master_key:
        pytest.skip(
            f"live-proxy smoke needs {PROXY_URL_ENV} and {MASTER_KEY_ENV} "
            "in the environment (quickstart §2)"
        )

    base_url = base_url.rstrip("/")
    model = os.environ.get(MODEL_ENV) or asyncio.run(
        _first_advertised_model(base_url, master_key)
    )
    return LiveConfig(base_url=base_url, master_key=master_key, model=model)


@pytest.fixture(scope="module")
def attempt(
    live_config: LiveConfig, tmp_path_factory: pytest.TempPathFactory
) -> LiveAttempt:
    """One real attempt, start to finish, against a scratch ledger.

    Only the ledger path is patched. The proxy credentials stay exactly as the
    operator exported them, because reading them from the process environment is
    the behaviour under test (FR-009, contracts/activities.md).
    """
    ledger_path = tmp_path_factory.mktemp("live-ledger") / ".factory" / "ledger.db"
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(LEDGER_PATH_ENV, str(ledger_path))
        return asyncio.run(_run_attempt(live_config, ledger_path))


# --- the live journey ------------------------------------------------------


async def _run_attempt(config: LiveConfig, ledger_path: Path) -> LiveAttempt:
    """Issue → call → settle → poll → teardown, exactly as the workflow would."""
    env = ActivityEnvironment()
    # Unique per run: LiteLLM rejects a duplicate `key_alias`, and a smoke test
    # an operator runs twice in a row must not be the thing that discovers that.
    epic_id = f"live-smoke-{int(time.time())}"

    lease: KeyLease = await env.run(
        issue_attempt_key,
        IssueKeyInput(
            node_id=NODE,
            epic_id=epic_id,
            attempt=ATTEMPT,
            persona=PERSONA,
            spec_ref=SPEC_REF,
            models=[config.model],
            ttl=SMOKE_TTL,
        ),
    )

    async with httpx.AsyncClient(
        base_url=config.base_url, timeout=COMPLETION_TIMEOUT_SECONDS
    ) as http:
        try:
            issued_info = await _key_info(http, config, lease.key)
            completion = await _tiny_completion(http, config, lease.key)
            proxy_rows, proxy_spend_usd = await _await_settled_usage(
                http, config, lease.key
            )

            snapshot: UsageSnapshot = await env.run(poll_usage, lease)
            record: UsageRecord = await env.run(
                teardown_attempt,
                TeardownInput(
                    lease=lease,
                    termination=Termination.COMPLETED,
                    last_snapshot=snapshot,
                ),
            )

            after = await _admin(http, config, "GET", "/key/info", params={"key": lease.key})
        finally:
            # Teardown revokes on the happy path; this is for every other one, so
            # a failed assertion does not leave a live key behind (R5's TTL is a
            # backstop, not an excuse).
            await _revoke_quietly(http, config, lease.key)

    return LiveAttempt(
        lease=lease,
        issued_info=issued_info,
        completion=completion,
        proxy_rows=proxy_rows,
        proxy_spend_usd=proxy_spend_usd,
        snapshot=snapshot,
        record=record,
        key_info_status_after=after.status_code,
        ledger_path=ledger_path,
        master_key=config.master_key,
        model=config.model,
    )


async def _tiny_completion(
    http: httpx.AsyncClient, config: LiveConfig, key: str
) -> dict[str, Any]:
    """The agent's whole run, compressed to one call on the attempt's key."""
    response = await http.post(
        "/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": config.model,
            "messages": [{"role": "user", "content": SMOKE_PROMPT}],
            "max_tokens": 1,
        },
    )
    if response.status_code != 200:
        pytest.fail(
            f"the attempt key could not call {config.model!r} "
            f"({response.status_code}: {response.text[:300]}). "
            f"Set {MODEL_ENV} to a model this proxy can route."
        )
    return response.json()


async def _await_settled_usage(
    http: httpx.AsyncClient, config: LiveConfig, key: str
) -> tuple[list[dict[str, Any]], float]:
    """Wait for the proxy to finish writing what the completion cost.

    Two independent batched writers have to land before a reconciliation means
    anything: the per-request spend rows and the key's own spend counter. Reading
    either one early would compare the ledger against a proxy that has not
    finished counting, and fail a test whose subject was never wrong.

    A timeout with rows still absent is fatal — the deployment lacks spend-log
    persistence and this component cannot work without it. A timeout with rows
    present returns what was read, so the mismatch is reported as numbers by the
    assertion that cares rather than as a wait that gave up.
    """
    deadline = time.monotonic() + SPEND_LOG_TIMEOUT_SECONDS
    rows: list[dict[str, Any]] = []
    spend_usd = 0.0

    while True:
        rows = await _spend_log_rows(http, config, key)
        spend_usd = await _key_spend(http, config, key)
        if rows and _agrees(spend_usd, sum_spend(rows)):
            return rows, spend_usd
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(SPEND_LOG_POLL_SECONDS)

    if not rows:
        pytest.fail(
            f"no spend-log row appeared for the attempt key within "
            f"{SPEND_LOG_TIMEOUT_SECONDS:.0f}s — this component needs the proxy "
            "running with its database and spend-log persistence enabled "
            "(spec.md § Assumptions)"
        )
    return rows, spend_usd


# --- raw proxy reads (the reconciliation source) ----------------------------


async def _admin(
    http: httpx.AsyncClient,
    config: LiveConfig,
    method: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    """One admin request, master-key authenticated, no interpretation."""
    return await http.request(
        method,
        path,
        headers={"Authorization": f"Bearer {config.master_key}"},
        **kwargs,
    )


async def _key_info(
    http: httpx.AsyncClient, config: LiveConfig, key: str
) -> dict[str, Any]:
    response = await _admin(http, config, "GET", "/key/info", params={"key": key})
    response.raise_for_status()
    body = response.json()
    info = body.get("info")
    return info if isinstance(info, dict) else body


async def _key_spend(http: httpx.AsyncClient, config: LiveConfig, key: str) -> float:
    return float((await _key_info(http, config, key)).get("spend") or 0.0)


async def _spend_log_rows(
    http: httpx.AsyncClient, config: LiveConfig, key: str
) -> list[dict[str, Any]]:
    """The proxy's per-request records for `key`, verbatim and unpaged.

    One completion is one row, so a single generous page is the whole log —
    pagination is the client's problem and the fake's contract, not this file's.
    """
    response = await _admin(
        http,
        config,
        "GET",
        "/spend/logs/v2",
        params={"api_key": key, "page": 1, "page_size": 1000},
    )
    response.raise_for_status()
    data = response.json().get("data")
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


async def _first_advertised_model(base_url: str, master_key: str) -> str:
    """Whatever the proxy will route, when the operator did not choose."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as http:
        response = await http.get(
            "/v1/models", headers={"Authorization": f"Bearer {master_key}"}
        )
        response.raise_for_status()
        data = response.json().get("data") or []

    for entry in data:
        model = entry.get("id") if isinstance(entry, dict) else None
        if isinstance(model, str) and model:
            return model

    pytest.skip(f"the proxy advertises no models; set {MODEL_ENV} to name one")


async def _revoke_quietly(
    http: httpx.AsyncClient, config: LiveConfig, key: str
) -> None:
    """Best-effort cleanup: the key is normally already gone by teardown."""
    try:
        await _admin(http, config, "POST", "/key/delete", json={"keys": [key]})
    except httpx.HTTPError:
        pass


# --- helpers ----------------------------------------------------------------


def sum_tokens(rows: list[dict[str, Any]], column: str) -> int:
    return sum(int(row.get(column) or 0) for row in rows)


def sum_spend(rows: list[dict[str, Any]]) -> float:
    return sum(float(row.get("spend") or 0.0) for row in rows)


def cache_values(rows: list[dict[str, Any]], field: str) -> list[int]:
    """Every value the backend actually reported for one cache metric (R2).

    An empty list is the metric being absent from the whole attempt — which the
    ledger must record as NULL, not as 0 (FR-004).
    """
    values: list[int] = []
    for row in rows:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            continue
        additional = metadata.get("additional_usage_values")
        if not isinstance(additional, dict):
            continue
        value = additional.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(int(value))
    return values


def ledger_rows(path: Path) -> list[dict[str, Any]]:
    """The ledger as an operator would read it — plain `sqlite3` (FR-012)."""
    conn = sqlite3.connect(path)
    try:
        cursor = conn.execute("SELECT * FROM usage_records ORDER BY id")
        return [
            {column[0]: value for column, value in zip(cursor.description, row)}
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def _agrees(left: float, right: float) -> bool:
    return abs(left - right) <= max(1e-9, 1e-6 * max(abs(left), abs(right)))


# --- the key the proxy actually minted --------------------------------------


def test_the_proxy_mints_an_uncapped_key_for_the_attempt(attempt: LiveAttempt) -> None:
    """A real `/key/generate` accepts a body with no cap — and adds none.

    The fake rejects `max_budget` outright, which proves this component never
    sends one; it cannot prove the proxy does not apply a default of its own. A
    key that came back capped would enforce a budget nobody in this component
    decided on (D-021, FR-004).
    """
    info = attempt.issued_info

    assert info.get("max_budget") is None
    assert info.get("key_alias") == attempt.lease.key_alias
    assert attempt.lease.key != attempt.master_key


def test_the_key_carries_the_attempts_dimensions(attempt: LiveAttempt) -> None:
    metadata = attempt.issued_info.get("metadata") or {}

    # A best-effort mirror (R1): the proxy does not copy this into spend rows, so
    # attribution is factory-side. It is still what an operator reads in the
    # LiteLLM UI when they ask whose key this is.
    assert metadata.get("node_id") == NODE
    assert metadata.get("persona") == PERSONA
    assert metadata.get("spec_ref") == SPEC_REF


def test_the_completion_really_ran_on_the_attempts_key(attempt: LiveAttempt) -> None:
    # Without a call that actually executed, everything below would reconcile two
    # empty sets and pass.
    assert attempt.completion.get("choices"), attempt.completion
    assert attempt.proxy_rows, "the proxy recorded no request for the attempt key"


# --- SC-002: the ledger row against the proxy's own records ------------------


def test_the_ledger_tokens_reconcile_with_the_proxys_spend_logs(
    attempt: LiveAttempt,
) -> None:
    """SC-002, against the real thing: exact match when the final read succeeded.

    Every number on the right comes from a raw HTTP read of the proxy summed with
    plain arithmetic in this file, so this is the component's aggregation checked
    against LiteLLM's records rather than against the fake that imitates them.
    """
    record = attempt.record
    rows = attempt.proxy_rows

    assert record.final_usage_confirmed is True
    assert record.request_count == len(rows)
    assert record.prompt_tokens == sum_tokens(rows, "prompt_tokens")
    assert record.completion_tokens == sum_tokens(rows, "completion_tokens")
    # A real completion spends real tokens; zeros here would mean the row columns
    # this component reads are not the ones LiteLLM populates any more.
    assert record.prompt_tokens > 0


def test_the_recorded_spend_is_the_keys_own_total(attempt: LiveAttempt) -> None:
    """`/key/info` is the contract's final spend (R3 step 1); rows are the detail.

    Both are asserted because the interesting failure is them disagreeing: the
    ledger records the counter, so a counter that has drifted from the rows it
    summarises would make the dollar column and the token columns describe
    different attempts. A locally-hosted model the proxy has no price for
    reconciles at $0.00 — a measurement, not a gap.
    """
    assert attempt.record.spend_usd == pytest.approx(attempt.proxy_spend_usd)
    assert attempt.record.spend_usd == pytest.approx(sum_spend(attempt.proxy_rows))


def test_cache_metrics_follow_the_backend_that_reported_them(
    attempt: LiveAttempt,
) -> None:
    """FR-004 on a live backend: absent stays absent, present sums.

    Which branch runs depends on the model the operator pointed us at — Anthropic
    reports cache counters, most local backends do not — so both are asserted
    against what the rows actually contained. The failure this catches is a
    backend that reports the metric under a name this component stopped
    recognising, which would look exactly like an attempt that used no cache.
    """
    for field, recorded in (
        (CACHE_READ_FIELD, attempt.record.cache_read_tokens),
        (CACHE_WRITE_FIELD, attempt.record.cache_write_tokens),
    ):
        reported = cache_values(attempt.proxy_rows, field)
        if reported:
            assert recorded == sum(reported), field
        else:
            assert recorded is None, f"{field} was never reported; NULL, not 0"


def test_the_attempt_lands_as_exactly_one_attributed_row(attempt: LiveAttempt) -> None:
    rows = ledger_rows(attempt.ledger_path)
    assert len(rows) == 1, f"expected exactly one ledger row, found {len(rows)}"
    stored = rows[0]

    # SC-001 and SC-003 on the live path: one row, and every dimension a rollup
    # groups by is on it (FR-006).
    assert stored["key_alias"] == attempt.lease.key_alias
    assert stored["epic_id"] == attempt.lease.epic_id
    assert stored["node_id"] == NODE
    assert stored["persona"] == PERSONA
    assert stored["spec_ref"] == SPEC_REF
    assert stored["attempt"] == ATTEMPT
    assert stored["termination"] == Termination.COMPLETED.value
    assert stored["final_usage_confirmed"] == 1
    assert stored["prompt_tokens"] == attempt.record.prompt_tokens
    assert stored["request_count"] == attempt.record.request_count


def test_the_heartbeat_saw_the_same_attempt(attempt: LiveAttempt) -> None:
    # The poll is the fallback's only source (R9), so a live run is the place to
    # confirm it reads the same counter teardown does — and that observing an
    # attempt costs it nothing (SC-005): the completion above already returned.
    assert attempt.snapshot.spend_usd == pytest.approx(attempt.proxy_spend_usd)


# --- cleanup & credentials --------------------------------------------------


def test_teardown_revoked_the_attempts_key(attempt: LiveAttempt) -> None:
    # Last step of R3, and the reason the smoke test is safe to run repeatedly:
    # the credential it minted does not outlive it.
    assert attempt.key_info_status_after == 404


def test_the_master_key_reaches_no_stored_byte(attempt: LiveAttempt) -> None:
    # SC-004 where it matters most: against a real proxy whose responses this
    # component parsed, stored, and could have echoed.
    secret = attempt.master_key.encode()
    for artifact in sorted(attempt.ledger_path.parent.iterdir()):
        assert secret not in artifact.read_bytes(), (
            f"master key found in {artifact.name}"
        )
