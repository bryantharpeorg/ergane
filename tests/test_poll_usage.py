"""The heartbeat read: a number, and nothing else.

`poll_usage` is the only activity in this component that runs while an attempt is
alive, which makes it the only place a budget could accidentally be enforced. So
the tests here are mostly about what does *not* happen:

- **A poll is a read.** One `GET /key/info` per beat (R9). No spend-log paging —
  token detail is aggregated once, at teardown (R2) — and no write of any kind,
  so the request log after a poll is exactly one entry long and the ledger file
  does not exist.
- **No usage level means anything.** The snapshot for $0.00 and the snapshot for
  $1,000,000,000 are the same kind of object, produced by the same code path,
  with the same absence of consequence: no warning, no throttle, no kill, no
  revocation (SC-005, US3 scenario 2). The assertion that carries this is the
  request log — an enforcement branch would have to *call* something to have any
  effect, so a log containing only the read is proof there is no such branch on
  the value.
- **A missed poll is not an incident.** A failed read raises the client's own
  `LiteLLMError` rather than a typed application error, because nothing branches
  on it: the caller's contract (contracts/activities.md) is to skip the beat, and
  the attempt keeps running with the previous snapshot as its latest-known state.
  Failing an attempt over an unreadable observability endpoint would be the
  enforcement side effect SC-005 forbids, arriving by the back door.
- **The snapshot is teardown's fallback, not just a display value.** US3 scenario
  1 asks for the latest-known state to be retained; the last test here proves the
  value a poll returns is the one a teardown that cannot reach the proxy records.

Written before `poll_usage` exists (T023 precedes T024): until the activity
lands, every test in this file fails at import.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.testing import ActivityEnvironment

from factory.activities import usage_activities
from factory.activities.usage_activities import (
    LEDGER_PATH_ENV,
    IssueKeyInput,
    TeardownInput,
    issue_attempt_key,
    poll_usage,
    teardown_attempt,
)
from factory.usage.litellm_client import LiteLLMClient, LiteLLMError
from factory.usage.models import KeyLease, Termination, UsageSnapshot
from tests.conftest import FakeLiteLLM

EPIC = "epic-7"
NODE = "node-3"
ATTEMPT = 1
PERSONA = "implementer"
SPEC_REF = "add-usage-tracking/live-visibility"
MODELS = ["anthropic/CHANGEME"]


# --- fixtures & helpers ----------------------------------------------------


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "ledger.db"


@pytest.fixture
def proxy(
    litellm_env: FakeLiteLLM, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> FakeLiteLLM:
    """A worker host wired to the fake proxy and a scratch ledger.

    The ledger path points somewhere nothing has created, so "polling wrote
    nothing" is checkable as the file's absence rather than as a row count.
    """
    monkeypatch.setenv(LEDGER_PATH_ENV, str(ledger_path))
    monkeypatch.setattr(
        usage_activities,
        "open_client",
        lambda: LiteLLMClient.from_env(transport=litellm_env.transport),
    )
    return litellm_env


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


async def issue(env: ActivityEnvironment, **overrides: Any) -> KeyLease:
    """Dispatch the standard attempt; the lease is what a poll takes as input."""
    fields: dict[str, Any] = {
        "node_id": NODE,
        "epic_id": EPIC,
        "attempt": ATTEMPT,
        "persona": PERSONA,
        "spec_ref": SPEC_REF,
        "models": MODELS,
    }
    fields.update(overrides)
    return await env.run(issue_attempt_key, IssueKeyInput(**fields))


async def poll(env: ActivityEnvironment, lease: KeyLease) -> UsageSnapshot:
    return await env.run(poll_usage, lease)


def routes_since(proxy: FakeLiteLLM, marker: int) -> list[str]:
    """Everything the fake was asked for after call number `marker`."""
    return proxy.routes[marker:]


def assert_iso_utc(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"{value!r} is not timezone-aware"
    assert parsed.utcoffset() == timedelta(0), f"{value!r} is not UTC"


def assert_credential_free(error: BaseException, *secrets: str) -> None:
    """No secret may appear anywhere in the raised chain (FR-009, SC-004)."""
    seen: BaseException | None = error
    depth = 0
    while seen is not None and depth < 10:
        for rendering in (str(seen), repr(seen), str(seen.args)):
            for secret in secrets:
                assert secret not in rendering, (
                    f"{secret!r} leaked into {type(seen).__name__}"
                )
        seen = seen.__cause__ or seen.__context__
        depth += 1


def spend_a_little(proxy: FakeLiteLLM, key: str, *, spend: float) -> None:
    """One request on the attempt's key, as the running agent would make it."""
    proxy.add_spend_row(
        key, prompt_tokens=100, completion_tokens=10, spend=spend, cache_read_tokens=32
    )


# --- registration ----------------------------------------------------------


def test_poll_usage_is_registered_under_its_contract_name() -> None:
    # The heartbeat calls it by the name in contracts/activities.md; a worker can
    # only register a decorated callable.
    definition = activity._Definition.from_callable(poll_usage)
    assert definition is not None, "poll_usage must carry @activity.defn"
    assert definition.name == "poll_usage"


# --- the reading -----------------------------------------------------------


async def test_poll_returns_the_keys_current_spend(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)
    spend_a_little(proxy, lease.key, spend=0.02)
    spend_a_little(proxy, lease.key, spend=0.03)

    snapshot = await poll(env, lease)

    assert isinstance(snapshot, UsageSnapshot)
    # The proxy computes the dollar figure; this component only reports it (R9).
    assert snapshot.spend_usd == pytest.approx(0.05)


async def test_the_snapshot_says_when_it_was_taken(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)

    before = datetime.now(timezone.utc)
    snapshot = await poll(env, lease)
    after = datetime.now(timezone.utc)

    # Staleness is the whole risk of a fallback value (R9): a snapshot teardown
    # may record hours later has to carry the moment it was true.
    assert_iso_utc(snapshot.captured_at)
    captured = datetime.fromisoformat(snapshot.captured_at)
    assert before - timedelta(seconds=1) <= captured <= after + timedelta(seconds=1)


async def test_successive_polls_track_the_attempt_as_it_spends(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)
    spend_a_little(proxy, lease.key, spend=0.01)
    first = await poll(env, lease)

    spend_a_little(proxy, lease.key, spend=0.04)
    second = await poll(env, lease)

    # Each beat re-reads the proxy rather than returning cached state; the
    # newest snapshot is the one teardown falls back to.
    assert first.spend_usd == pytest.approx(0.01)
    assert second.spend_usd == pytest.approx(0.05)
    assert second.captured_at >= first.captured_at


async def test_a_poll_is_one_key_info_read_and_nothing_more(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)
    spend_a_little(proxy, lease.key, spend=0.01)
    marker = len(proxy.calls)

    await poll(env, lease)

    # R9: `/key/info` is one cheap indexed read, cheap enough to run every 30s
    # for every live attempt. Token detail is deliberately not polled — paging
    # the spend logs on every beat would cost far more than it tells anyone,
    # and teardown reads them once (R2).
    assert routes_since(proxy, marker) == ["GET /key/info"]
    (call,) = proxy.calls_to("/key/info")
    assert call.params["key"] == lease.key


# --- enforcement-free by construction (SC-005) ------------------------------


@pytest.mark.parametrize(
    "spend", [0.0, 0.000001, 42.5, 10_000.0, 1_000_000_000.0, 9.9e15]
)
async def test_any_usage_level_produces_a_snapshot_and_nothing_else(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path, spend: float
) -> None:
    lease = await issue(env)
    proxy.set_spend(lease.key, spend)
    marker = len(proxy.calls)

    snapshot = await poll(env, lease)

    # US3 scenario 2 / SC-005: a billion dollars is a number, not an event. No
    # warning, no throttle, no kill, no revocation — and the request log is what
    # proves it, because any enforcement action would have to call the proxy to
    # have an effect. A raise would be enforcement too: it would fail the
    # heartbeat, and with it the attempt.
    assert snapshot.spend_usd == pytest.approx(spend)
    assert routes_since(proxy, marker) == ["GET /key/info"]
    assert lease.key in proxy.keys
    assert not ledger_path.exists()


async def test_polling_leaves_the_running_attempt_untouched(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    lease = await issue(env)
    spend_a_little(proxy, lease.key, spend=0.01)

    for _ in range(5):
        await poll(env, lease)

    # Observability only (FR-007): the key stays live and unmodified, its
    # spend-log rows are untouched, and nothing is written anywhere. The ledger
    # is teardown's business — a row per attempt, not per beat (FR-003).
    assert lease.key in proxy.keys
    assert proxy.keys[lease.key]["max_budget"] is None
    assert len(proxy.rows_for(lease.key)) == 1
    assert not ledger_path.exists()
    assert proxy.calls_to("/key/delete") == []


# --- failure is the caller's to skip ----------------------------------------


async def test_a_failed_poll_raises_for_the_caller_to_skip(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    """A missed beat raises the client's own error, untyped and unwrapped.

    Issuance gets `KEY_ISSUANCE_FAILED` because the workflow branches on it (R4).
    A poll gets nothing of the sort, because no caller may branch on a poll at
    all: contracts/activities.md makes failure skippable, so the error only has
    to be loggable and credential-free.
    """
    lease = await issue(env)
    proxy.fail_next("/key/info", status=503)

    with pytest.raises(LiteLLMError) as excinfo:
        await poll(env, lease)

    assert excinfo.value.status == 503
    assert_credential_free(excinfo.value, proxy.master_key)


async def test_a_missed_poll_costs_only_that_beat(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    lease = await issue(env)
    spend_a_little(proxy, lease.key, spend=0.02)
    proxy.fail_next("/key/info", status=500)

    with pytest.raises(LiteLLMError):
        await poll(env, lease)
    recovered = await poll(env, lease)

    # SC-005 again, from the other side: the attempt survives an unreadable
    # observability endpoint. Nothing was revoked, nothing was written, and the
    # next beat reads the current state as if the gap had not happened.
    assert recovered.spend_usd == pytest.approx(0.02)
    assert lease.key in proxy.keys
    assert not ledger_path.exists()


async def test_polling_a_key_that_is_already_gone_raises(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)
    del proxy.keys[lease.key]  # TTL expiry (R5), or teardown already ran

    with pytest.raises(LiteLLMError) as excinfo:
        await poll(env, lease)

    # A poll of a dead key reports absence rather than inventing $0.00 for it:
    # the last good snapshot stays the latest-known state (FR-005).
    assert excinfo.value.status == 404


async def test_missing_worker_credentials_fail_the_poll_before_any_call(
    env: ActivityEnvironment, proxy: FakeLiteLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    lease = await issue(env)
    monkeypatch.delenv("LITELLM_MASTER_KEY")
    marker = len(proxy.calls)

    with pytest.raises(LiteLLMError) as excinfo:
        await poll(env, lease)

    # The credential comes from the worker host's environment, never from the
    # lease (FR-009) — so a host without one cannot poll at all, and the
    # variable's name is diagnostic while its value never is.
    assert "LITELLM_MASTER_KEY" in str(excinfo.value)
    assert routes_since(proxy, marker) == []


async def test_a_rejected_credential_never_appears_in_the_failure(
    env: ActivityEnvironment, proxy: FakeLiteLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    lease = await issue(env)
    wrong = "sk-wrong-master-key"
    monkeypatch.setenv("LITELLM_MASTER_KEY", wrong)

    with pytest.raises(LiteLLMError) as excinfo:
        await poll(env, lease)

    # Every 30s for every live attempt is the most-executed proxy call in the
    # component, which makes it the likeliest place for a credential to reach a
    # log (SC-004).
    assert_credential_free(excinfo.value, wrong, proxy.master_key)


async def test_the_snapshot_never_carries_the_master_key(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)
    spend_a_little(proxy, lease.key, spend=0.01)

    snapshot = await poll(env, lease)

    # The snapshot is a Temporal payload: it is persisted in workflow history
    # and survives the attempt it describes (FR-009).
    assert proxy.master_key not in repr(snapshot)
    assert lease.key not in repr(snapshot)


# --- the value teardown falls back to ---------------------------------------


async def test_the_polled_snapshot_is_what_teardown_records_when_the_proxy_is_lost(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)
    spend_a_little(proxy, lease.key, spend=0.07)
    snapshot = await poll(env, lease)
    del proxy.keys[lease.key]  # the attempt outlived its key

    record = await env.run(
        teardown_attempt,
        TeardownInput(
            lease=lease, termination=Termination.KILLED, last_snapshot=snapshot
        ),
    )

    # US3 scenario 1: the heartbeat's value is retained as latest-known state,
    # and this is what retaining it buys — a killed attempt whose key is already
    # gone still records the dollars it was last seen spending, flagged as
    # unconfirmed rather than fabricated (FR-005).
    assert record.final_usage_confirmed is False
    assert record.spend_usd == pytest.approx(snapshot.spend_usd)
    assert record.prompt_tokens is None
