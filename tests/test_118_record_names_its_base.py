"""The record says what the verdict was measured against (118 US2).

US1 stopped a node being *dispatched* onto a stale base. This story is the
other half: after the fact, a PASS must name the base it was measured on, or
every past and future verdict stays unauditable — a PASS that could never
merge looks identical to one that could, which is exactly the shape the
measured defect took on the live floor.

Three properties these tests defend:

- **The row carries the pin, taken from the prepared worktree (US2-S1,
  FR-006, trap 5).** `PreparedWorktree` already knows its `base_ref`; reading
  git a second time at record-writing time would give an answer that can
  differ from the one the attempt actually ran against — the very defect
  class this spec exists to end. The scripted interpreter is what makes the
  provenance checkable: its prepared worktree's base is ``"9" * 40``, and its
  target repo (``/srv/factory/targets/library``) exists nowhere on this
  machine, so no re-derivation could have produced the value the row carries.
- **The status line shows the base beside the landing head (US2-S2, FR-007).**
  One line, both SHAs — the diagnosis that would have made the stale-base
  PASS visible in seconds. The landing head is the one the forge reported at
  the last poll (`PrSnapshot.base_sha`), which is the only landing-branch
  observation a workflow can hold without running git (constitution IV).
- **A row from before this change reads as unknown (US2-S3, FR-006).** The
  unknown representation is `None` — a NULL column, never backfilled, never
  defaulted to a guess. A missing base must not be quietly mistaken for a
  current one.

The store surface is asserted against the real evidence store, and the
status surfaces against the real `epic_status` query put through the real
payload converter — the same discipline `tests/test_attempt_reports_persona_and_model.py`
states: a field that survives the dataclass but not the wire passes no test
in this file.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
from temporalio.converter import default as default_data_converter

from factory.cli.nouns.build import render_status
from factory.mergequeue.models import PrSnapshot  # noqa: F401
from factory.verify.models import (
    GateResult,
    GateStatus,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    compose_result,
)
from factory.verify.store import connect, node_history, upsert_result
from factory.workgraph.models import NodeState

from tests.test_interpreter import (
    EPIC_ID,
    ScriptedWorld,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    merged_snapshot,
    one_node,
    pending_snapshot,
    run_epic,
)

NODE = "us1"

#: The base the scripted `prepare_worktree` pins. Only the prepared worktree
#: carries this value — and its target repository does not exist on this host,
#: so a row holding it was read from the preparation, never derived from git.
SCRIPTED_BASE = "9" * 40

#: What a poll of the landing branch reports as its current head — a sha the
#: scripted world has no other source for, so a status line showing it read
#: the forge's observation.
LANDING_HEAD = "abc123" * 6 + "de"  # 38 hex chars, distinct from the base


# --- helpers -----------------------------------------------------------------


def as_json_document(status: Any) -> dict[str, Any]:
    """The document `ergane build status --json` prints, from a real status.

    `_query_status` queries with no result type, so what the CLI holds is the
    payload decoded as plain JSON rather than the dataclass this test was
    handed. Re-encoding through the converter the factory actually runs is
    that same trip, in-process.
    """
    payload = default_data_converter().payload_converter.to_payload(status)
    document: dict[str, Any] = json.loads(payload.data)
    return document


def node_line(rendered: str, node_id: str = NODE) -> str:
    """The one line of the human status that belongs to a node."""
    lines = [line for line in rendered.splitlines() if line.startswith(node_id)]
    assert len(lines) == 1, f"expected one '{node_id}' line in:\n{rendered}"
    return lines[0]


def _output_check() -> OutputCheck:
    """The output half of a passing row — a diff was present and clean."""
    return OutputCheck(
        write_scope="node",
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )


def compose_row(base_ref: str | None) -> Any:
    """One PASS row as `_verify` composes it, with or without a recorded base."""
    return compose_result(
        epic_id=EPIC_ID,
        node_id=NODE,
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="uv run pytest -q",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=1.0,
                output_tail="1 passed",
            )
        ],
        output_check=_output_check(),
        judge=None,
        criteria_sha256="a" * 64,
        spec_ref="118/US2",
        started_at="2026-08-29T09:00:00Z",
        finished_at="2026-08-29T09:01:00Z",
        base_ref=base_ref,
    )


def forged_base_sha(base: str) -> Any:
    """A pending poll answer whose forge-reported base is `base`."""
    return replace(pending_snapshot(), base_sha=base)


# --- US2-S1: the row carries the prepared base (T011, trap 5) -----------------


def test_the_composer_put_the_prepared_base_on_the_row() -> None:
    """T011 / FR-006: the row's base is exactly what the caller handed it.

    `_verify` is the caller, and it passes `prepared.base_ref`; this unit
    pins the composing surface, and the interpreter run below pins who the
    caller is.
    """
    result = compose_row(SCRIPTED_BASE)
    assert result.base_ref == SCRIPTED_BASE


def test_a_row_without_a_base_reads_as_unknown_not_as_a_guess() -> None:
    """The unknown representation, decided once (T015): `None`.

    Not an empty string, not the landing branch's name, not a re-derived
    head. A row that does not know its base must be unreadable as a sha, so
    nothing downstream can mistake the absence for a value.
    """
    result = compose_row(None)
    assert result.base_ref is None
    assert result.base_ref != ""


async def test_a_verified_attempt_s_row_carries_the_prepared_base(
    env: Any,
) -> None:
    """US2-S1 / trap 5: the recorded base is the prepared worktree's pin.

    The scripted world's target repo does not exist, so the only place a sha
    can come from is `PreparedWorktree.base_ref` — a row carrying
    ``"9" * 40`` was read off the preparation at dispatch time, not derived
    from git at record-writing time.
    """
    script = ScriptedWorld({NODE: [merged_snapshot_node()]}, client=env.client)

    status = await run_epic(env, script, graph=one_node())

    assert is_merged(status)
    assert script.prepare_requests, "the node never prepared its worktree"
    recorded = script.records[0]
    assert recorded.verdict == OverallVerdict.PASS
    assert recorded.base_ref == SCRIPTED_BASE


def merged_snapshot_node() -> Any:
    """One passing attempt — the ladder PASSes on the first run."""
    from tests.test_interpreter import passing

    return passing()


def is_merged(status: Any) -> bool:
    """Terminal sanity: the node ended MERGED."""
    return status.nodes[NODE].state == NodeState.MERGED


# --- US2-S2: status shows the base beside the landing head (T012) -------------


async def test_the_status_line_shows_the_base_beside_the_landing_head(
    env: Any,
) -> None:
    """US2-S2 / FR-007: one line, both SHAs.

    The base is the pin the node was dispatched against; the landing head is
    what the forge said the landing branch was at the last poll. When the two
    differ by more than the tolerance, this line is the whole diagnosis.
    """
    script = ScriptedWorld({NODE: [merged_snapshot_node()]}, client=env.client)
    script.script_landing(NODE, forged_base_sha(LANDING_HEAD), merged_snapshot())

    status = await run_epic(env, script, graph=one_node())
    document = as_json_document(status)

    node_view = document["nodes"][NODE]
    assert node_view["base_ref"] == SCRIPTED_BASE
    assert node_view["landing_head"] == LANDING_HEAD

    line = node_line(render_status(EPIC_ID, document, "COMPLETED"))
    assert SCRIPTED_BASE[:12] in line
    assert LANDING_HEAD[:12] in line


async def test_a_node_with_no_landing_shows_the_base_alone(env: Any) -> None:
    """The landing head is not invented when nothing has polled it.

    A node verified in halting mode never opened a landing; its line says
    what it was measured against and nothing about a head nobody read.
    """
    script = ScriptedWorld({NODE: [merged_snapshot_node()]}, client=env.client)

    status = await run_epic(env, script, graph=one_node(), halt_after_pass=True)
    document = as_json_document(status)

    node_view = document["nodes"][NODE]
    assert node_view["base_ref"] == SCRIPTED_BASE
    assert node_view["landing_head"] is None

    line = node_line(render_status(EPIC_ID, document, "COMPLETED"))
    assert SCRIPTED_BASE[:12] in line
    assert "landing head" not in line


def test_a_node_that_never_dispatched_names_no_base() -> None:
    """The control: no base is rendered for work nobody measured.

    A pre-118 worker's document carries neither key at all; the line renders
    unchanged rather than inventing a sha from somewhere.
    """
    document: dict[str, Any] = {
        "epic_state": "RUNNING",
        "nodes": {
            NODE: {
                "state": NodeState.PENDING,
                "attempt": 0,
                "branch": f"factory/{EPIC_ID}/{NODE}",
            }
        },
    }

    line = node_line(render_status(EPIC_ID, document, "RUNNING"))
    assert "base" not in line
    assert "landing head" not in line


# --- US2-S3: rows predating this change read as unknown (T013) ----------------


def test_a_row_from_before_this_change_reads_as_unknown(store: Any) -> None:
    """US2-S3 / FR-006: an old row's base is unknown, never a wrong value.

    The store migrates the table, the row keeps NULL, and reading it back
    yields `None` — "nobody recorded a base" — rather than a default that
    looks like a sha. Every verdict written before this story is unauditable
    for its base; the record must say so, not paper over it.
    """
    _raw_insert_pre_118_row(store)

    (row,) = node_history(store, EPIC_ID, NODE)

    assert row.verdict == OverallVerdict.PASS
    assert row.base_ref is None


def test_the_base_survives_the_store_round_trip(store: Any) -> None:
    """The column is a column: written and read back, verbatim."""
    upsert_result(store, compose_row(SCRIPTED_BASE))

    (row,) = node_history(store, EPIC_ID, NODE)
    assert row.base_ref == SCRIPTED_BASE


def _raw_insert_pre_118_row(store: Any) -> None:
    """Insert one PASS row in exactly the shape 118 found the store in.

    Only the columns a pre-118 writer knew. The store's own migration adds
    `base_ref` during `connect`, so the missing column arrives as NULL — the
    shape of every row written before this story.
    """
    store.execute(
        """
        INSERT INTO verification_results (
            epic_id, node_id, attempt, form, verdict, gate_results,
            output_check, judge_verdict, judge_unavailable, criteria_drift,
            criteria_sha256, spec_ref, started_at, finished_at,
            provenance, loop_digest, loop_summary
        ) VALUES (
            :epic_id, :node_id, :attempt, :form, :verdict, :gate_results,
            :output_check, NULL, 0, 0,
            :criteria_sha256, :spec_ref, :started_at, :finished_at,
            NULL, :loop_digest, :loop_summary
        )
        """,
        {
            "epic_id": EPIC_ID,
            "node_id": NODE,
            "attempt": 1,
            "form": "PHASE",
            "verdict": "PASS",
            "gate_results": "[]",
            "output_check": (
                '{"write_scope": "node", "has_diff": true, '
                '"expected_artifacts": [], "artifacts_present": null, '
                '"passed": true, "hygiene_violations": [], "size_refusal": null}'
            ),
            "criteria_sha256": "b" * 64,
            "spec_ref": "118/US2",
            "started_at": "2026-08-01T09:00:00Z",
            "finished_at": "2026-08-01T09:01:00Z",
            "loop_digest": "d" * 64,
            "loop_summary": "pre-118",
        },
    )
    store.commit()


# --- the store fixture --------------------------------------------------------


@pytest.fixture
def store(tmp_path: Any) -> Any:
    """A real evidence store under tmp, closed by the caller.

    `connect` is the writer's door: it creates the file, the schema and the
    migrations (which are how a pre-118 table gains its `base_ref` column).
    """
    conn = connect(tmp_path / "verification.db")
    try:
        yield conn
    finally:
        conn.close()