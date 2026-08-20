"""US4: a subscription attempt is honest in the ledger and bounded in flight.

The story has two parts.  The first is honesty: a subscription-routed attempt
spends the operator's own subscription quota, not gateway tokens, so the ledger
must record that it carried no gateway spend data.  A row with `spend_usd = 0`
would read as a free call and would be indistinguishable from a genuine zero.
The second part is contention: one subscription credential has no virtual keys to
isolate concurrent nodes, so the scheduler must bound subscription-routed nodes by
a declared limit.  The default must be stated, not accidental.

The concurrency tests run the real `EpicWorkflow` scheduler under Temporal's
time-skipping environment, using the same scripted harness as
`tests/test_interpreter.py`.  A hand-rolled mock scheduler is not sufficient:
the acceptance criteria are about the factory's actual dispatch decisions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment

from factory.activities import usage_activities
from factory.activities.usage_activities import (
    IssueKeyInput,
    TeardownInput,
    issue_attempt_key,
    teardown_attempt,
)
from factory.config import SUBSCRIPTION_AGENT, Persona, WriteScope
from factory.mergequeue.models import LandingConfig
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from factory.workgraph.models import EpicState
from tests.conftest import FakeLiteLLM
from tests.test_interpreter import (
    PERSONAS,
    ScriptedWorld,
    all_passing,
    make_graph,
    make_node,
    run_epic,
)
from tests.test_usage_activities import only_row

EPIC = "070-subscription-accounting"
NODE = "us4"
ATTEMPT = 1
PERSONA = "subscription"
SPEC_REF = "070:US4"
ALIAS = f"{EPIC}:{NODE}:{ATTEMPT}:{PERSONA}"

#: A heartbeat the adapter would have carried back on the normal path.  For a
#: gateway attempt it is a real measured figure; for a subscription attempt it
#: must not be written because there is no proxy measurement to fall back to.
SNAPSHOT = UsageSnapshot(spend_usd=0.0417, captured_at="2026-08-20T10:29:30Z")

#: The subscription persona used by the scheduler tests.  It is added to the
#: interpreter's test registry so both the fake `resolve_graph` activity and the
#: workflow-side `_resolve_persona` see the same entry.
SUBSCRIPTION_PERSONA = Persona(
    name="subscription",
    agent=SUBSCRIPTION_AGENT,
    model="opus",
    fallback=None,
    skills=(),
    write_scope=WriteScope.WORKTREE,
    needs_worktree=True,
    timeout_s=3600,
)
SUBSCRIPTION_REGISTRY: dict[str, Persona] = {**PERSONAS, "subscription": SUBSCRIPTION_PERSONA}


# --- helpers ------------------------------------------------------------------


def _subscription_nodes(count: int) -> list[Any]:
    """Return `count` independent subscription-routed nodes.

    Story keys are reused from the interpreter's fixture set so the fake
    `snapshot_criteria` can build criteria without per-node scripting.
    """
    story_keys = ["US1", "US2", "US3"]
    nodes: list[Any] = []
    for i in range(count):
        story = story_keys[i % len(story_keys)]
        nodes.append(
            make_node(
                f"sub{i + 1}",
                story,
                persona="subscription",
                requirement_keys=[story],
                depends_on=[],
            )
        )
    return nodes


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "ledger.db"


@pytest.fixture
def proxy(
    litellm_env: FakeLiteLLM, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> FakeLiteLLM:
    """A worker host wired to the fake proxy and a scratch ledger."""
    from factory.activities.usage_activities import ERGANE_LEDGER_PATH_ENV, LEDGER_PATH_ENV

    monkeypatch.setenv(ERGANE_LEDGER_PATH_ENV, str(ledger_path))
    monkeypatch.delenv(LEDGER_PATH_ENV, raising=False)
    monkeypatch.setattr(
        usage_activities,
        "open_client",
        lambda: LiteLLMClient.from_env(transport=litellm_env.transport),
    )
    return litellm_env


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
async def workflow_env() -> Any:
    """Temporal with a clock the test owns — an hour of silence costs nothing."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


async def issue(
    env: ActivityEnvironment, *, agent: str = "subscription"
) -> KeyLease:
    return await env.run(
        issue_attempt_key,
        IssueKeyInput(
            node_id=NODE,
            epic_id=EPIC,
            attempt=ATTEMPT,
            persona=PERSONA,
            spec_ref=SPEC_REF,
            models=["opus"],
            agent=agent,
        ),
    )


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


# --- T026 [US4-S1] subscription row carries no gateway spend data --------------


@pytest.mark.asyncio
async def test_subscription_attempt_records_no_gateway_spend_data(
    env: ActivityEnvironment,
    proxy: FakeLiteLLM,
    ledger_path: Path,
) -> None:
    """A subscription-routed attempt is recorded as carrying no gateway spend
    data: every token field is NULL, spend_usd is NULL, and final_usage_confirmed
    is False.  This is distinguishable from a zero."""
    lease = await issue(env)

    assert lease.key == ""

    record = await tear_down(env, lease)

    assert record.prompt_tokens is None
    assert record.completion_tokens is None
    assert record.cache_read_tokens is None
    assert record.cache_write_tokens is None
    assert record.request_count is None
    assert record.spend_usd is None
    assert record.final_usage_confirmed is False
    assert record.termination == Termination.COMPLETED

    stored = only_row(ledger_path)
    assert stored["prompt_tokens"] is None
    assert stored["completion_tokens"] is None
    assert stored["cache_read_tokens"] is None
    assert stored["cache_write_tokens"] is None
    assert stored["request_count"] is None
    assert stored["spend_usd"] is None
    assert stored["final_usage_confirmed"] == 0
    assert stored["key_alias"] == ALIAS


# --- T027 [US4-S2] gateway control still records exactly as today --------------


@pytest.mark.asyncio
async def test_gateway_attempt_records_exactly_as_today(
    env: ActivityEnvironment,
    proxy: FakeLiteLLM,
    ledger_path: Path,
) -> None:
    """The control: a gateway attempt still mints a key, reads the proxy, and
    writes a confirmed row with real numbers.  US4 must not change this path."""
    from tests.test_usage_activities import spend_rows_for

    lease = await issue(env, agent="claude-code")

    assert lease.key != ""
    spend_rows_for(proxy, lease.key)

    record = await tear_down(env, lease)

    assert record.final_usage_confirmed is True
    assert record.prompt_tokens == 600
    assert record.request_count == 3
    assert record.spend_usd == pytest.approx(0.06)

    stored = only_row(ledger_path)
    assert stored["final_usage_confirmed"] == 1
    assert stored["prompt_tokens"] == 600
    assert stored["request_count"] == 3
    assert stored["spend_usd"] == pytest.approx(0.06)


# --- T028 [US4-S3] concurrent subscription-routed nodes are bounded ------------


@pytest.mark.asyncio
async def test_subscription_concurrency_is_bounded_by_declared_limit(
    workflow_env: WorkflowEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US4-S3: with more subscription-routed nodes than the declared limit, the
    real scheduler keeps at most that many in flight at once."""
    monkeypatch.setattr(
        "factory.config.load_personas", lambda path=None: SUBSCRIPTION_REGISTRY
    )
    monkeypatch.setattr("tests.test_interpreter.PERSONAS", SUBSCRIPTION_REGISTRY)

    script = ScriptedWorld(all_passing(), client=workflow_env.client, agent_sleep_s=0.5)
    graph = make_graph(_subscription_nodes(4))

    status = await run_epic(
        workflow_env,
        script,
        graph=graph,
        max_concurrent_nodes=4,
        max_concurrent_subscription_nodes=2,
        landing_config=LandingConfig(poll_interval_s=0),
    )

    assert status.epic_state == EpicState.COMPLETED
    assert set(script.dispatched) == {"sub1", "sub2", "sub3", "sub4"}
    assert all(len(running) <= 2 for running in script.running_sets), (
        f"more than 2 subscription-routed nodes in flight at once: "
        f"{script.running_sets}"
    )


# --- T029 [US4-S4] default limit is stated and observed ------------------------


@pytest.mark.asyncio
async def test_subscription_default_has_no_additional_cap(
    workflow_env: WorkflowEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US4-S4: when no subscription-specific limit is declared, subscription
    nodes are constrained only by the general `max_concurrent_nodes` cap."""
    monkeypatch.setattr(
        "factory.config.load_personas", lambda path=None: SUBSCRIPTION_REGISTRY
    )
    monkeypatch.setattr("tests.test_interpreter.PERSONAS", SUBSCRIPTION_REGISTRY)

    script = ScriptedWorld(all_passing(), client=workflow_env.client, agent_sleep_s=0.5)
    graph = make_graph(_subscription_nodes(3))

    status = await run_epic(
        workflow_env,
        script,
        graph=graph,
        max_concurrent_nodes=3,
        landing_config=LandingConfig(poll_interval_s=0),
    )

    assert status.epic_state == EpicState.COMPLETED
    assert set(script.dispatched) == {"sub1", "sub2", "sub3"}
    assert any(len(running) == 3 for running in script.running_sets), (
        f"expected all 3 subscription nodes in flight at once at some point, "
        f"got running_sets={script.running_sets}"
    )
