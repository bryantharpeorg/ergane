"""The activity surface: a key per attempt, and a ledger row on every path.

These are the only functions the orchestrator calls, so this module is where the
component's promises stop being module-local and become the factory's behaviour:

- **Teardown's job is the row, not the proxy.** The ordering is fixed — read
  `/key/info`, page the spend logs, write the ledger, delete the key LAST (R3) —
  and every proxy failure along the way degrades to the flagged fallback rather
  than to a lost attempt (FR-002, FR-005). A read that failed writes `NULL`s and
  `final_usage_confirmed = 0`; it never writes a zero it did not measure.
  The one failure teardown does *not* absorb is the ledger's own: if the row
  cannot be written the error propagates, because Temporal retrying is the only
  thing that can still make SC-001 true.
- **Delete-last is observable.** Ordering is asserted from the fake's request log,
  and — the part a call log cannot show — by breaking the ledger write and
  proving the key is still alive afterwards. A teardown that deleted first would
  have destroyed the key and the attempt's usage together.
- **Idempotency is exercised, not assumed.** Temporal runs teardown at least
  once; the second run finds the key gone, takes the fallback, and upserts onto
  the first run's row (SC-001).
- **An unattributable row is refused, not written.** Every other failure here
  degrades to a flagged row, but a row missing epic, node, persona or spec_ref
  belongs to no rollup group and quietly shrinks the totals it should have been
  part of. Teardown raises instead — before the write, so the usage is still
  sitting on a live key when the dispatch bug is fixed (SC-003).
- **The master key stays on the worker host.** It reaches the activities through
  the process environment only, and appears in no lease, no record, no error and
  no byte of the ledger file (FR-009, SC-004).
- **Issuance failure is not an attempt.** A proxy that will not mint a key raises
  `KEY_ISSUANCE_FAILED` (R4) and leaves no ledger row behind: no key, no usage.

`open_client` is the seam the tests inject the fake proxy through — in
production it is `LiteLLMClient.from_env()`, so the credential still has to come
from the environment for any of this to authenticate, and deleting the variable
still fails issuance.

Written before `factory/activities/usage_activities.py` exists (T015 precedes
T017): until the module lands, every test here fails at import.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from factory.activities import usage_activities
from factory.activities.usage_activities import (
    ATTRIBUTION_INCOMPLETE,
    DEFAULT_LEDGER_PATH,
    KEY_ISSUANCE_FAILED,
    LEDGER_PATH_ENV,
    IssueKeyInput,
    TeardownInput,
    issue_attempt_key,
    teardown_attempt,
)
from factory.usage.litellm_client import DEFAULT_KEY_TTL, LiteLLMClient
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from tests.conftest import FakeLiteLLM

EPIC = "epic-7"
NODE = "node-3"
ATTEMPT = 2
PERSONA = "implementer"
SPEC_REF = "add-usage-tracking/ledger-row"
ALIAS = f"{EPIC}:{NODE}:{ATTEMPT}"
MODELS = ["anthropic/CHANGEME", "local/CHANGEME"]

#: The last heartbeat before the attempt ended (R9) — teardown's fallback input.
SNAPSHOT = UsageSnapshot(spend_usd=0.0417, captured_at="2026-07-24T10:29:30Z")


# --- fixtures & helpers ----------------------------------------------------


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "ledger.db"


@pytest.fixture
def proxy(
    litellm_env: FakeLiteLLM, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> FakeLiteLLM:
    """A worker host wired to the fake proxy and a scratch ledger.

    `litellm_env` puts the credentials in the process environment, where the
    activities must read them from (FR-009); the seam below only supplies the
    transport, so `from_env` still resolves the master key and the fake still
    401s if the wrong one arrives.
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


def issue_input(**overrides: Any) -> IssueKeyInput:
    """A dispatch of the standard attempt; override only what a test is about."""
    fields: dict[str, Any] = {
        "node_id": NODE,
        "epic_id": EPIC,
        "attempt": ATTEMPT,
        "persona": PERSONA,
        "spec_ref": SPEC_REF,
        "models": MODELS,
    }
    fields.update(overrides)
    return IssueKeyInput(**fields)


async def issue(env: ActivityEnvironment, **overrides: Any) -> KeyLease:
    return await env.run(issue_attempt_key, issue_input(**overrides))


async def tear_down(
    env: ActivityEnvironment,
    lease: KeyLease,
    *,
    termination: Termination = Termination.COMPLETED,
    snapshot: UsageSnapshot | None = SNAPSHOT,
) -> UsageRecord:
    return await env.run(
        teardown_attempt,
        TeardownInput(lease=lease, termination=termination, last_snapshot=snapshot),
    )


def ledger_rows(path: Path) -> list[dict[str, Any]]:
    """Every row in the ledger, read back with plain `sqlite3` (FR-012)."""
    conn = sqlite3.connect(path)
    try:
        cursor = conn.execute("SELECT * FROM usage_records ORDER BY id")
        return [
            {column[0]: value for column, value in zip(cursor.description, row)}
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def only_row(path: Path) -> dict[str, Any]:
    rows = ledger_rows(path)
    assert len(rows) == 1, f"expected exactly one ledger row, found {len(rows)}"
    return rows[0]


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


def spend_rows_for(proxy: FakeLiteLLM, key: str) -> None:
    """Three requests on the attempt's key: 600/60 tokens, $0.06, mixed cache."""
    proxy.add_spend_row(
        key, prompt_tokens=100, completion_tokens=10, spend=0.01, cache_read_tokens=128
    )
    proxy.add_spend_row(key, prompt_tokens=200, completion_tokens=20, spend=0.02)
    proxy.add_spend_row(
        key, prompt_tokens=300, completion_tokens=30, spend=0.03, cache_write_tokens=16
    )


# --- registration ----------------------------------------------------------


def test_the_activities_are_registered_under_their_contract_names() -> None:
    # A worker can only register decorated callables; the names are what
    # contracts/activities.md tells the workflow side to call.
    for fn, name in (
        (issue_attempt_key, "issue_attempt_key"),
        (teardown_attempt, "teardown_attempt"),
    ):
        definition = activity._Definition.from_callable(fn)
        assert definition is not None, f"{name} must carry @activity.defn"
        assert definition.name == name


# --- issuance --------------------------------------------------------------


async def test_issue_attempt_key_mints_a_key_bound_to_the_attempt(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)

    assert isinstance(lease, KeyLease)
    # The alias is the attempt's identity everywhere downstream: the ledger's
    # uniqueness key and the thing that makes a re-teardown an upsert (R1).
    assert lease.key_alias == ALIAS
    assert lease.key in proxy.keys
    assert proxy.key_for_alias(ALIAS) == lease.key
    assert (lease.epic_id, lease.node_id, lease.attempt) == (EPIC, NODE, ATTEMPT)
    assert lease.persona == PERSONA
    assert lease.spec_ref == SPEC_REF
    assert_iso_utc(lease.issued_at)


async def test_issue_attempt_key_sends_the_dimensions_and_never_a_cap(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    await issue(env)

    (call,) = proxy.calls_to("/key/generate")
    assert call.body is not None
    assert call.body["key_alias"] == ALIAS
    assert call.body["models"] == MODELS
    assert call.body["metadata"] == {
        "node_id": NODE,
        "epic_id": EPIC,
        "attempt": ATTEMPT,
        "persona": PERSONA,
        "spec_ref": SPEC_REF,
    }
    # Budget enforcement is deferred (D-021, FR-004): nothing this component
    # sends can stop an agent mid-run.
    assert "max_budget" not in call.body
    assert "soft_budget" not in call.body


async def test_issue_attempt_key_applies_the_backstop_ttl(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    await issue(env)
    (default_call,) = proxy.calls_to("/key/generate")
    assert default_call.body is not None
    # R5: the TTL exists so a key whose teardown never ran still dies.
    assert default_call.body["duration"] == DEFAULT_KEY_TTL == "24h"

    await issue(env, attempt=3, ttl="1h")
    override_call = proxy.calls_to("/key/generate")[1]
    assert override_call.body is not None
    assert override_call.body["duration"] == "1h"


async def test_a_persistent_proxy_failure_raises_key_issuance_failed(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    proxy.fail_next("/key/generate", status=500)

    with pytest.raises(ApplicationError) as excinfo:
        await issue(env)

    # R4: the distinct type is what keeps infrastructure failures out of
    # agent-quality statistics.
    assert KEY_ISSUANCE_FAILED == "KEY_ISSUANCE_FAILED"
    assert excinfo.value.type == KEY_ISSUANCE_FAILED
    # A proxy restart is transient, so the workflow's retry policy gets to run;
    # the activity itself does not loop.
    assert excinfo.value.non_retryable is False
    assert len(proxy.calls_to("/key/generate")) == 1


async def test_a_rejected_credential_fails_issuance_permanently(
    env: ActivityEnvironment, proxy: FakeLiteLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = "sk-wrong-master-key"
    monkeypatch.setenv("LITELLM_MASTER_KEY", wrong)

    with pytest.raises(ApplicationError) as excinfo:
        await issue(env)

    assert excinfo.value.type == KEY_ISSUANCE_FAILED
    # Retrying a misconfigured host for ten minutes only delays the diagnosis.
    assert excinfo.value.non_retryable is True
    assert_credential_free(excinfo.value, wrong, proxy.master_key)


async def test_missing_worker_credentials_fail_issuance_before_any_call(
    env: ActivityEnvironment, proxy: FakeLiteLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LITELLM_MASTER_KEY")

    with pytest.raises(ApplicationError) as excinfo:
        await issue(env)

    assert excinfo.value.type == KEY_ISSUANCE_FAILED
    assert excinfo.value.non_retryable is True
    # The variable's name is diagnostic; its value never is (FR-009).
    assert "LITELLM_MASTER_KEY" in str(excinfo.value)
    assert proxy.calls == []


async def test_a_failed_issuance_leaves_no_ledger_row(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    proxy.fail_next("/key/generate", status=500)

    with pytest.raises(ApplicationError):
        await issue(env)

    # No key, no usage: the attempt never ran (data-model.md § state
    # transitions). A row here would invent an attempt out of an outage.
    assert not ledger_path.exists()


# --- teardown, confirmed path ----------------------------------------------


async def test_teardown_reads_then_writes_then_deletes_last(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)

    await tear_down(env, lease)

    # R3, in order: the spend-log filters resolve through the live key, so the
    # key cannot die until everything has been read from it.
    assert proxy.routes == [
        "POST /key/generate",
        "GET /key/info",
        "GET /spend/logs/v2",
        "POST /key/delete",
    ]
    assert lease.key not in proxy.keys


async def test_teardown_records_the_attempts_usage_from_proxy_data(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)

    record = await tear_down(env, lease, termination=Termination.COMPLETED)

    assert isinstance(record, UsageRecord)
    assert record.id is not None
    assert record.final_usage_confirmed is True
    assert record.prompt_tokens == 600
    assert record.completion_tokens == 60
    assert record.cache_read_tokens == 128
    # Independent metrics: one cache counter reported and one absent is a
    # number and a NULL, not two NULLs (FR-004).
    assert record.cache_write_tokens == 16
    assert record.request_count == 3
    assert record.spend_usd == pytest.approx(0.06)

    stored = only_row(ledger_path)
    assert stored["id"] == record.id
    assert stored["epic_id"] == EPIC
    assert stored["node_id"] == NODE
    assert stored["attempt"] == ATTEMPT
    assert stored["persona"] == PERSONA
    assert stored["spec_ref"] == SPEC_REF
    assert stored["key_alias"] == ALIAS
    assert stored["prompt_tokens"] == 600
    assert stored["completion_tokens"] == 60
    assert stored["cache_read_tokens"] == 128
    assert stored["cache_write_tokens"] == 16
    assert stored["request_count"] == 3
    assert stored["spend_usd"] == pytest.approx(0.06)
    assert stored["final_usage_confirmed"] == 1
    assert stored["termination"] == "completed"
    assert stored["issued_at"] == lease.issued_at
    assert_iso_utc(stored["torn_down_at"])


async def test_the_confirmed_spend_is_the_keys_own_total(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    """`/key/info` is the contract's "final spend" (R3 step 1); rows are tokens.

    Teardown reads both because they answer different questions: the key's
    counter is the attempt's authoritative dollar total, and the per-request
    rows are the only place token and cache detail exists (R2). Where they
    disagree the row records the counter — otherwise step 1 would be ceremony
    on the path that matters most.
    """
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)
    proxy.set_spend(lease.key, 0.0725)

    record = await tear_down(env, lease)

    assert record.spend_usd == pytest.approx(0.0725)
    assert record.prompt_tokens == 600
    assert record.request_count == 3


async def test_an_attempt_that_never_called_the_proxy_records_real_zeros(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    """The proxy answered "no rows" — that is a measurement, so zeros are right.

    Cache stays NULL: no row reported the metric, vacuously (FR-004/FR-005).
    """
    lease = await issue(env)

    record = await tear_down(env, lease, termination=Termination.AGENT_ERROR)

    assert record.final_usage_confirmed is True
    assert record.prompt_tokens == 0
    assert record.completion_tokens == 0
    assert record.request_count == 0
    assert record.spend_usd == 0.0
    assert record.cache_read_tokens is None
    assert record.cache_write_tokens is None


@pytest.mark.parametrize("termination", list(Termination))
async def test_every_terminal_path_produces_a_row(
    env: ActivityEnvironment,
    proxy: FakeLiteLLM,
    ledger_path: Path,
    termination: Termination,
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)

    record = await tear_down(env, lease, termination=termination)

    # SC-001: kill and timeout are terminal paths like any other.
    assert record.termination is termination
    assert only_row(ledger_path)["termination"] == termination.value


# --- teardown, fallback path -----------------------------------------------


async def test_a_key_already_gone_falls_back_to_the_last_snapshot(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)
    del proxy.keys[lease.key]  # TTL expiry, or a teardown that already ran

    record = await tear_down(env, lease)

    # The spend logs are not consulted for a dead key: their filters resolve
    # through the live token table, so the answer would be untrustworthy (R3).
    assert proxy.routes == ["POST /key/generate", "GET /key/info", "POST /key/delete"]

    assert record.final_usage_confirmed is False
    assert record.spend_usd == pytest.approx(SNAPSHOT.spend_usd)
    assert record.prompt_tokens is None
    assert record.completion_tokens is None
    assert record.cache_read_tokens is None
    assert record.cache_write_tokens is None
    assert record.request_count is None

    stored = only_row(ledger_path)
    assert stored["final_usage_confirmed"] == 0
    assert stored["prompt_tokens"] is None
    assert stored["request_count"] is None
    assert stored["spend_usd"] == pytest.approx(SNAPSHOT.spend_usd)


async def test_a_failed_spend_log_read_falls_back_too(
    env: ActivityEnvironment, proxy: FakeLiteLLM
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)
    proxy.fail_next("/spend/logs/v2", status=500)

    record = await tear_down(env, lease, termination=Termination.TIMEOUT)

    # Half a reading is not a reading: without token detail the row is an
    # estimate and says so, rather than mixing a confirmed dollar figure with
    # invented tokens (FR-005).
    assert record.final_usage_confirmed is False
    assert record.spend_usd == pytest.approx(SNAPSHOT.spend_usd)
    assert record.prompt_tokens is None
    assert record.request_count is None
    assert lease.key not in proxy.keys


async def test_a_rejected_credential_still_produces_a_flagged_row(
    env: ActivityEnvironment,
    proxy: FakeLiteLLM,
    ledger_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-wrong-master-key")

    record = await tear_down(env, lease)

    # Teardown's deliverable is the row (FR-002). A proxy that cannot be read —
    # unreachable, restarting, misconfigured — costs the detail, not the attempt.
    assert record.final_usage_confirmed is False
    assert record.prompt_tokens is None
    assert only_row(ledger_path)["final_usage_confirmed"] == 0


async def test_a_failed_read_with_no_snapshot_records_nulls_never_zeros(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)
    proxy.fail_next("/key/info", status=503)

    record = await tear_down(env, lease, termination=Termination.KILLED, snapshot=None)

    # An attempt killed before its first heartbeat: nothing was ever measured,
    # and $0.00 would be a lie about a run that may have cost real money.
    assert record.final_usage_confirmed is False
    assert record.spend_usd is None
    assert record.prompt_tokens is None

    stored = only_row(ledger_path)
    assert stored["spend_usd"] is None
    assert stored["prompt_tokens"] is None
    assert stored["completion_tokens"] is None
    assert stored["request_count"] is None
    assert stored["final_usage_confirmed"] == 0
    assert stored["termination"] == "killed"


# --- idempotency & ordering -------------------------------------------------


async def test_running_teardown_twice_leaves_exactly_one_row(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)

    first = await tear_down(env, lease)
    second = await tear_down(env, lease)

    # Temporal runs teardown at least once; the rerun finds the key gone, takes
    # the fallback, and lands on the same row (FR-002, SC-001).
    assert second.id == first.id
    assert len(ledger_rows(ledger_path)) == 1

    stored = only_row(ledger_path)
    assert stored["final_usage_confirmed"] == 0
    assert stored["prompt_tokens"] is None
    assert stored["spend_usd"] == pytest.approx(SNAPSHOT.spend_usd)


async def test_a_failed_revocation_still_records_the_attempt(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)
    proxy.fail_next("/key/delete", status=500)

    record = await tear_down(env, lease)

    # Revocation is the last step for a reason: it is the only one whose
    # failure the TTL already covers (R5). The row is complete regardless.
    assert record.final_usage_confirmed is True
    assert record.prompt_tokens == 600
    assert only_row(ledger_path)["prompt_tokens"] == 600
    assert lease.key in proxy.keys


async def test_a_failed_ledger_write_leaves_the_key_alive(
    env: ActivityEnvironment,
    proxy: FakeLiteLLM,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lease = await issue(env)
    spend_rows_for(proxy, lease.key)
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    monkeypatch.setenv(LEDGER_PATH_ENV, str(blocked / "ledger.db"))

    with pytest.raises(OSError):
        await tear_down(env, lease)

    # Proof of ordering that a call log cannot give: the write comes first, so a
    # ledger that refuses the row has not yet lost the key it describes. The
    # error propagates unwrapped — Temporal retrying is what still makes SC-001
    # true, and swallowing it would drop the attempt silently.
    assert "POST /key/delete" not in proxy.routes
    assert lease.key in proxy.keys
    assert proxy.rows_for(lease.key) != []


async def test_the_ledger_path_defaults_to_the_documented_location(
    env: ActivityEnvironment,
    proxy: FakeLiteLLM,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LEDGER_PATH_ENV)
    monkeypatch.chdir(tmp_path)

    lease = await issue(env)
    spend_rows_for(proxy, lease.key)
    await tear_down(env, lease)

    # The writer and the CLI must agree on where the ledger is, or an operator's
    # `factory-usage` reads an empty database (contracts/cli.md).
    assert DEFAULT_LEDGER_PATH == ".factory/ledger.db"
    assert only_row(tmp_path / DEFAULT_LEDGER_PATH)["key_alias"] == ALIAS


# --- attribution ------------------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("dimension", ["epic_id", "node_id", "persona", "spec_ref"])
async def test_an_unattributable_row_is_refused_rather_than_written(
    env: ActivityEnvironment,
    proxy: FakeLiteLLM,
    ledger_path: Path,
    dimension: str,
    blank: str,
) -> None:
    lease = replace(await issue(env), **{dimension: blank})
    spend_rows_for(proxy, lease.key)

    with pytest.raises(ApplicationError) as excinfo:
        await tear_down(env, lease)

    # SC-003: these four are what every rollup groups by (FR-006). A row missing
    # one is not a weaker measurement — it falls out of the group it belonged to
    # and makes the operator's totals quietly too small. A whitespace persona is
    # as absent as an empty one.
    assert excinfo.value.type == ATTRIBUTION_INCOMPLETE
    # The dimensions come from the dispatch, so a rerun rebuilds the same
    # unattributable row; only the caller can fix this.
    assert excinfo.value.non_retryable is True
    # The message names the field, because the operator's next move is to find
    # where the dispatch dropped it.
    assert dimension in str(excinfo.value)
    assert_credential_free(excinfo.value, proxy.master_key)


@pytest.mark.parametrize("dimension", ["epic_id", "node_id", "persona", "spec_ref"])
async def test_a_refused_row_leaves_the_usage_recoverable(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path, dimension: str
) -> None:
    lease = replace(await issue(env), **{dimension: ""})
    spend_rows_for(proxy, lease.key)

    with pytest.raises(ApplicationError):
        await tear_down(env, lease)

    # Refused before the write, and the write is before the revocation (R3): the
    # attempt's usage is still readable from a live key, so a corrected
    # re-dispatch can still record it. No half-row, no partial ledger file.
    assert not ledger_path.exists()
    assert "POST /key/delete" not in proxy.routes
    assert lease.key in proxy.keys
    assert proxy.rows_for(lease.key) != []


async def test_a_fully_attributed_row_is_written_on_the_fallback_path_too(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    lease = await issue(env)
    proxy.fail_next("/key/info", status=503)

    record = await tear_down(env, lease)

    # The guard is about attribution, not about the reading: a flagged row is
    # still a row, and it still carries all four dimensions (FR-005, SC-003).
    assert record.final_usage_confirmed is False
    stored = only_row(ledger_path)
    for dimension, expected in (
        ("epic_id", EPIC),
        ("node_id", NODE),
        ("persona", PERSONA),
        ("spec_ref", SPEC_REF),
    ):
        assert stored[dimension] == expected


# --- credentials ------------------------------------------------------------


async def test_the_master_key_reaches_no_payload_error_or_stored_byte(
    env: ActivityEnvironment, proxy: FakeLiteLLM, ledger_path: Path
) -> None:
    secret = proxy.master_key

    lease = await issue(env)
    spend_rows_for(proxy, lease.key)
    record = await tear_down(env, lease)

    # The virtual key may travel — model-constrained, TTL'd, now revoked. The
    # master key may not, in any direction (FR-009, SC-004).
    assert secret not in repr(lease)
    assert secret not in repr(record)
    assert lease.key != secret

    for artifact in sorted(ledger_path.parent.iterdir()):
        assert secret.encode() not in artifact.read_bytes(), (
            f"master key found in {artifact.name}"
        )
