"""The one test that asks a real model to be the judge.

`test_judge.py` proves the judge module against `httpx.MockTransport`: a fake
that returns whatever verdict the test author wrote. That pins the parser, the
truncation arithmetic and the stricter-reading cross-check, and it pins nothing
at all about whether a model an operator would actually route to persona `judge`
can produce a response the strict parser accepts. A judge whose every reply is
refused as malformed spends three completions per cycle and never passes
anything — and against the fake it looks perfect.

This file closes that gap once, per quickstart §3: it resolves the judge
persona from `personas.yaml` (never a model name in code, constitution VII),
mints a real per-attempt virtual key through component 1, scores one tiny
fixture diff against one acceptance scenario over the deployed proxy, tears the
attempt down, and then asserts the two things the smoke exists for — a
structured verdict came back, and the tokens it cost landed in the usage ledger
attributed to persona `judge` (constitution V).

Four deliberate choices:

- **The model comes from the registry, not from an env var.** `test_live_proxy`
  lets `LITELLM_SMOKE_MODEL` name any model because its subject is the ledger and
  the model is incidental. Here the alias *is* the subject: FR-003 is scored by
  whatever the operator routed `judge` to, so this test calls that alias or it
  does not run. `LIVE_JUDGE_PERSONAS_PATH` points at a registry whose judge model
  the proxy serves — the shipped `personas.yaml` carries `CHANGEME` placeholders,
  so out of the box this skips with that instruction rather than failing.
- **The verdict is asserted structurally, not by outcome.** Every dispatched
  scenario must come back scored exactly once, with reasoning — the contract
  `parse_verdict` enforces. Which way a live model votes on a fixture diff is the
  model's judgment and asserting it would make an honest disagreement look like a
  regression. What must not happen is a reply the parser refuses, and the
  refusal's own text is what the failure prints.
- **The proxy is hit once.** Two completions would buy a second sample of the
  same fact at twice an operator's wait; the module-scoped `attempt` fixture runs
  the journey a single time and each test below reads a different facet of it.
- **It skips, it does not fail, without credentials.** No
  `LITELLM_PROXY_URL`/`LITELLM_MASTER_KEY` means nobody asked for a live run;
  `uv run pytest -q` stays a pure-unit suite and `-m live_proxy` selects this.

Spend-log persistence is the one thing this file cannot degrade around: without
per-request rows the ledger has no tokens to attribute and constitution V's
assertion has nothing to stand on. Its absence is a documented deployment
assumption (spec.md § Assumptions), so it fails loudly here rather than skipping.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
    teardown_attempt,
)
from factory.activities.verify_activities import RunJudgeInput, run_judge
from factory.config import ConfigError, load_personas
from factory.usage.litellm_client import (
    MASTER_KEY_ENV,
    PROXY_URL_ENV,
    hashed_token,
)
from factory.usage.models import KeyLease, Termination, UsageRecord
from factory.verify.judge import dispatched_scenario_ids
from factory.verify.models import (
    CriteriaSet,
    JudgeOutcome,
    JudgeVerdict,
    Requirement,
    RequirementKind,
    Scenario,
)

#: Selected with `-m live_proxy`, deselected with `-m "not live_proxy"`; skipped
#: outright without proxy credentials (see `live_config`).
pytestmark = pytest.mark.live_proxy

#: An operator's own persona registry, whose `judge` model their proxy routes.
#: Read only by this test — production loads the shipped registry.
REGISTRY_ENV = "LIVE_JUDGE_PERSONAS_PATH"

#: The persona whose registry entry decides which model judges. A persona name,
#: not a model name: constitution VII is about the latter.
JUDGE_PERSONA = "judge"

NODE = "live-judge-smoke"
ATTEMPT = 1
FEATURE = "live-judge-smoke"
SPEC_REF = "002-verification-gating/SC-002"

#: Far below R5's 24h default: this key exists for one completion, and a smoke
#: run that dies before its teardown should not leave a day-long credential on
#: the operator's proxy.
SMOKE_TTL = "10m"

#: LiteLLM writes spend logs from a batching worker, so the row for a completion
#: that has already returned does not exist yet. This is the wait for it, not a
#: request timeout.
SPEND_LOG_TIMEOUT_SECONDS = 90.0
SPEND_LOG_POLL_SECONDS = 2.0

#: Generous enough for a cold local judge model to load and write a verdict.
PROXY_READ_TIMEOUT_SECONDS = 120.0

#: The fixture the judge scores: one scenario, and a diff that plainly satisfies
#: it. Small on purpose — the truncation path has its own unit tests, and a
#: large diff here would only buy a slower, pricier smoke.
SCENARIO_TEXT = (
    "1. **Given** a caller supplies a name, **When** `greet` is called with it, "
    "**Then** the returned string contains that name"
)

FIXTURE_DIFF = """diff --git a/greeting.py b/greeting.py
index 1c7c9f1..b2d4e08 100644
--- a/greeting.py
+++ b/greeting.py
@@ -1,2 +1,2 @@
 def greet(name: str) -> str:
-    return "Hello!"
+    return f"Hello, {name}!"
"""


@dataclass(frozen=True)
class LiveConfig:
    """The operator's proxy and their judge persona, as configuration has them."""

    base_url: str
    master_key: str
    #: The persona registry's alias for `judge` — the only model name in play.
    model_alias: str


@dataclass(frozen=True)
class LiveJudgement:
    """Everything one live judge attempt produced, for the assertions to read."""

    lease: KeyLease
    criteria: CriteriaSet
    verdict: JudgeVerdict
    #: The proxy's own per-request records for the attempt's key, read raw.
    proxy_rows: list[dict[str, Any]]
    record: UsageRecord
    ledger_path: Path
    master_key: str
    model_alias: str


# --- environment -----------------------------------------------------------


@pytest.fixture(scope="module")
def live_config() -> LiveConfig:
    """The live proxy and a judge alias it will route, or a skip."""
    base_url = os.environ.get(PROXY_URL_ENV)
    master_key = os.environ.get(MASTER_KEY_ENV)
    if not base_url or not master_key:
        pytest.skip(
            f"live-judge smoke needs {PROXY_URL_ENV} and {MASTER_KEY_ENV} "
            "in the environment (quickstart §3)"
        )

    base_url = base_url.rstrip("/")
    alias = _judge_alias()
    advertised = asyncio.run(_advertised_models(base_url, master_key))
    if alias not in advertised:
        pytest.skip(
            f"the proxy does not advertise {alias!r}, the model persona "
            f"'{JUDGE_PERSONA}' resolves to. Point {REGISTRY_ENV} at a persona "
            "registry whose judge model this proxy serves; it advertises "
            f"{', '.join(sorted(advertised)) or 'nothing'}"
        )

    return LiveConfig(base_url=base_url, master_key=master_key, model_alias=alias)


def _judge_alias() -> str:
    """Persona `judge`'s model, from the registry and from nowhere else."""
    try:
        personas = load_personas(os.environ.get(REGISTRY_ENV) or None)
    except ConfigError as exc:
        pytest.fail(f"the persona registry does not load: {exc}")

    persona = personas.get(JUDGE_PERSONA)
    if persona is None or persona.model is None:
        pytest.skip(
            f"the persona registry declares no model for '{JUDGE_PERSONA}'; set "
            f"{REGISTRY_ENV} to one that does"
        )
    return persona.model


@pytest.fixture(scope="module")
def judgement(
    live_config: LiveConfig, tmp_path_factory: pytest.TempPathFactory
) -> LiveJudgement:
    """One real judge attempt, start to finish, against a scratch ledger.

    Only the ledger path is patched. The proxy credentials stay exactly as the
    operator exported them, because reading them from the process environment is
    the behaviour under test (FR-009, contracts/activities.md).
    """
    ledger_path = tmp_path_factory.mktemp("live-judge-ledger") / ".factory" / "ledger.db"
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(LEDGER_PATH_ENV, str(ledger_path))
        return asyncio.run(_run_judgement(live_config, ledger_path))


# --- the live journey ------------------------------------------------------


async def _run_judgement(config: LiveConfig, ledger_path: Path) -> LiveJudgement:
    """Issue → judge → settle → teardown, exactly as a verifier node would."""
    env = ActivityEnvironment()
    # Unique per run: LiteLLM rejects a duplicate `key_alias`, and a smoke test
    # an operator runs twice in a row must not be the thing that discovers that.
    epic_id = f"live-judge-{int(time.time())}"
    criteria = _fixture_criteria()

    lease: KeyLease = await env.run(
        issue_attempt_key,
        IssueKeyInput(
            node_id=NODE,
            epic_id=epic_id,
            attempt=ATTEMPT,
            persona=JUDGE_PERSONA,
            spec_ref=SPEC_REF,
            # The key may call the judge's alias and nothing else (R8): a judge
            # that can reach the implementer's model is an unattributed budget.
            models=[config.model_alias],
            ttl=SMOKE_TTL,
        ),
    )

    async with httpx.AsyncClient(
        base_url=config.base_url, timeout=PROXY_READ_TIMEOUT_SECONDS
    ) as http:
        try:
            verdict: JudgeVerdict = await env.run(
                run_judge,
                RunJudgeInput(
                    criteria=criteria,
                    diff_text=FIXTURE_DIFF,
                    virtual_key=lease.key,
                    proxy_url=config.base_url,
                    model_alias=config.model_alias,
                ),
            )
            proxy_rows = await _await_spend_rows(http, config, lease.key)

            record: UsageRecord = await env.run(
                teardown_attempt,
                TeardownInput(lease=lease, termination=Termination.COMPLETED),
            )
        finally:
            # Teardown revokes on the happy path; this is for every other one, so
            # a failed assertion does not leave a live key behind (R5's TTL is a
            # backstop, not an excuse).
            await _revoke_quietly(http, config, lease.key)

    return LiveJudgement(
        lease=lease,
        criteria=criteria,
        verdict=verdict,
        proxy_rows=proxy_rows,
        record=record,
        ledger_path=ledger_path,
        master_key=config.master_key,
        model_alias=config.model_alias,
    )


def _fixture_criteria() -> CriteriaSet:
    """One story, one scenario — the smallest thing a judge can be strict about.

    Hand-built rather than parsed: US1's parser has its own corpus, and coupling
    this smoke to a spec file would mean an edit there could only ever break it.
    """
    body = f"**Acceptance Scenarios**:\n\n{SCENARIO_TEXT}\n"
    source = f"### User Story 1 - Greeting names the caller (Priority: P1)\n\n{body}"

    return CriteriaSet(
        feature=FEATURE,
        spec_ref=SPEC_REF,
        requirements=[
            Requirement(
                key="US1",
                kind=RequirementKind.STORY,
                title="Greeting names the caller",
                priority="P1",
                body=body,
                scenarios=[
                    Scenario(
                        scenario_id="US1-S1",
                        steps=[
                            "Given a caller supplies a name",
                            "When `greet` is called with it",
                            "Then the returned string contains that name",
                        ],
                        raw_text=SCENARIO_TEXT,
                    )
                ],
            )
        ],
        source_path="<live-judge-fixture>",
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        snapshotted_at=datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    )


async def _await_spend_rows(
    http: httpx.AsyncClient, config: LiveConfig, key: str
) -> list[dict[str, Any]]:
    """Wait for the proxy to write down what the judge's completion cost.

    Reading before the batching writer lands would attribute the judge's tokens
    to nothing and fail an assertion whose subject was never wrong. A timeout
    with rows still absent is fatal, not a skip: without spend-log persistence
    there is no per-node attribution for any persona, judge included.
    """
    deadline = time.monotonic() + SPEND_LOG_TIMEOUT_SECONDS
    while True:
        rows = await _spend_log_rows(http, config, key)
        if rows:
            return rows
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(SPEND_LOG_POLL_SECONDS)

    pytest.fail(
        f"no spend-log row appeared for the judge's key within "
        f"{SPEND_LOG_TIMEOUT_SECONDS:.0f}s — this component needs the proxy "
        "running with its database and spend-log persistence enabled "
        "(spec.md § Assumptions)"
    )


# --- raw proxy reads --------------------------------------------------------


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


async def _spend_log_rows(
    http: httpx.AsyncClient, config: LiveConfig, key: str
) -> list[dict[str, Any]]:
    """The proxy's per-request records for `key`, verbatim and unpaged.

    One judge invocation is one row, so a single generous page is the whole log.
    """
    response = await _admin(
        http,
        config,
        "GET",
        "/spend/logs/v2",
        params={
            # The store keys rows by the token's sha256; a raw key matches nothing.
            "api_key": hashed_token(key),
            # The proxy requires the window; +/- a day is the same
            # generous partition hint the real client sends.
            "start_date": (date.today() - timedelta(days=1)).isoformat(),
            "end_date": (date.today() + timedelta(days=1)).isoformat(),
            "page": 1,
            # 100 is the proxy's hard cap (422 above it) and plenty for a smoke.
            "page_size": 100,
        },
    )
    response.raise_for_status()
    data = response.json().get("data")
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


async def _advertised_models(base_url: str, master_key: str) -> set[str]:
    """Every alias the proxy says it can route."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as http:
        response = await http.get(
            "/v1/models", headers={"Authorization": f"Bearer {master_key}"}
        )
        response.raise_for_status()
        data = response.json().get("data") or []

    return {
        entry["id"]
        for entry in data
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }


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


# --- (a) a structured verdict came back --------------------------------------


def test_the_judge_answered_in_the_schema_the_parser_demands(
    judgement: LiveJudgement,
) -> None:
    """The thing the fake cannot prove: a real model can satisfy `parse_verdict`.

    `run_judge` never raises on an unreadable response — it converts the parse
    failure into a RETRY verdict with no findings and the reason as feedback — so
    an empty `findings` list *is* the malformed case, and printing the feedback is
    printing exactly what the strict parser objected to.
    """
    verdict = judgement.verdict

    assert verdict.findings, (
        "the judge's response could not be parsed as a verdict: "
        f"{verdict.feedback}"
    )
    assert verdict.outcome in set(JudgeOutcome)


def test_every_dispatched_scenario_was_scored_individually(
    judgement: LiveJudgement,
) -> None:
    """FR-003 against a real model: per-scenario, ids echoed, reasons given.

    The outcome itself is not asserted. Whether this diff satisfies this scenario
    is the judge's judgment, and a smoke test that demanded one answer would
    report an honest disagreement as a broken component.
    """
    expected = dispatched_scenario_ids(judgement.criteria)
    findings = judgement.verdict.findings

    assert [finding.scenario for finding in findings] == expected
    assert all(finding.reasoning.strip() for finding in findings)
    assert isinstance(judgement.verdict.feedback, str)


def test_the_verdict_names_the_personas_alias_and_a_whole_diff(
    judgement: LiveJudgement,
) -> None:
    # The alias is the registry's, not a literal in any module (constitution
    # VII), and a fixture this small must never be reported as abridged — a
    # `truncated_input` here would mean the cap arithmetic is cutting diffs that
    # fit (R6).
    assert judgement.verdict.model_alias == judgement.model_alias
    assert judgement.verdict.truncated_input is False
    assert judgement.verdict.judge_attempt == 1


# --- (b) the judge's spend is attributed (constitution V) ---------------------


def test_the_completion_ran_on_the_attempts_own_key(judgement: LiveJudgement) -> None:
    # Rows filtered by the virtual key: their existence is the proof that the
    # judge's tokens were charged to this attempt and not to the master key or to
    # some shared credential. Without it, everything below reconciles zeros.
    assert judgement.proxy_rows, "the proxy recorded no request for the judge's key"
    assert judgement.lease.key != judgement.master_key


def test_the_judges_spend_lands_in_the_ledger_attributed_to_the_persona(
    judgement: LiveJudgement,
) -> None:
    """Constitution V on the judge path: no LLM call in this component is anonymous.

    The judge is the component's only model call, so this row is the whole of its
    spend attribution — and `persona` is the column that makes a "what did
    verification cost?" rollup include it.
    """
    rows = ledger_rows(judgement.ledger_path)
    assert len(rows) == 1, f"expected exactly one ledger row, found {len(rows)}"
    stored = rows[0]

    assert stored["persona"] == JUDGE_PERSONA
    assert stored["epic_id"] == judgement.lease.epic_id
    assert stored["node_id"] == NODE
    assert stored["attempt"] == ATTEMPT
    assert stored["spec_ref"] == SPEC_REF
    assert stored["key_alias"] == judgement.lease.key_alias
    assert stored["termination"] == Termination.COMPLETED.value


def test_the_recorded_tokens_are_the_judges_own(judgement: LiveJudgement) -> None:
    """The ledger row against the proxy's records for the same key.

    Both numbers are read here — one from the row component 1 wrote, one summed
    from a raw HTTP read — so this checks attribution end to end rather than the
    ledger against itself. A judge invocation always spends prompt tokens; a zero
    would mean the row was written from an empty reading and the attribution is
    decorative.
    """
    record = judgement.record
    rows = judgement.proxy_rows

    assert record.final_usage_confirmed is True
    assert record.persona == JUDGE_PERSONA
    assert record.request_count == len(rows)
    assert record.prompt_tokens == sum_tokens(rows, "prompt_tokens")
    assert record.completion_tokens == sum_tokens(rows, "completion_tokens")
    assert record.prompt_tokens > 0


def test_no_credential_reaches_a_stored_byte(judgement: LiveJudgement) -> None:
    # FR-009 where it matters most: against a real proxy whose responses this
    # component parsed, stored, and could have echoed. The attempt's own virtual
    # key is checked alongside the master key — the judge is the one place a
    # per-attempt credential is handed to an HTTP client, and its verdict, its
    # feedback and its ledger row are all durable.
    secrets = {judgement.master_key.encode(), judgement.lease.key.encode()}
    artifacts = sorted(judgement.ledger_path.parent.iterdir())
    assert artifacts, "the ledger wrote nothing to inspect"

    for artifact in artifacts:
        content = artifact.read_bytes()
        for secret in secrets:
            assert secret not in content, f"a credential is stored in {artifact.name}"

    text = judgement.verdict.feedback + "".join(
        finding.reasoning for finding in judgement.verdict.findings
    )
    for secret in secrets:
        assert secret.decode() not in text
