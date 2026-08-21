"""User Story 3 — an attempt says which persona and model it ran.

US1 made the rung select the model; this story makes that selection *readable*.
The defect it answers is not a routing bug but a reporting one: between
2026-08-12 and 2026-08-20 nothing the factory printed said what an attempt had
actually run, so a rung running the wrong model was found twice by reading a
live process list, eight days apart.

Three surfaces are asserted here, all of them `ergane build status`:

- the per-attempt history in the JSON form, which is the record of what each
  attempt ran (US3-S1, FR-011);
- the human line, which is what an operator watching an epic reads (US3-S2,
  FR-012);
- and the one case that must not fall back — a rung naming a persona the epic's
  snapshot never resolved is reported as *unresolved*, never as the node's own
  model (US3-S3), because a debugger rung silently reported as the implementer's
  model is precisely how this survived being found twice.

The status these tests read is the real query result put through the real
payload converter (`as_json_document`), not a dict written here: `_query_status`
queries with no result type, so what the CLI holds is JSON decoded from the
history's bytes. A field that survives the dataclass but not the wire passes no
test in this file.

The scripted world of `tests.test_interpreter` is reused rather than rebuilt —
its registry routes `implementer` and `debugger` to different model aliases,
which is exactly the two-persona history US3-S1 asks for.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from temporalio.converter import default as default_data_converter

from factory.cli.nouns.build import render_status
from factory.config import Persona
from factory.verify.ladder import DEBUGGER_PERSONA
from factory.verify.models import UNRESOLVED_MODEL_ALIAS
from factory.workgraph.models import NodeState

from tests.test_interpreter import (
    EPIC_ID,
    MODEL_ALIAS,
    PERSONAS,
    ScriptedWorld,
    attempt_counts,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    failing,
    one_node,
    run_epic,
    states,
)

#: The debugger's own alias in the interpreter's test registry — deliberately
#: not `MODEL_ALIAS`, so a history that reports the node's model for the rung's
#: attempt is visible rather than indistinguishable.
DEBUGGER_ALIAS = PERSONAS[DEBUGGER_PERSONA].model

NODE = "us1"


@pytest.fixture(autouse=True)
def registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every registry read — activity-side and workflow-side — at one map.

    The same fixture US1's tests install, and for the same reason: the workflow
    snapshot resolves the rung personas no node declares from
    `factory.config.load_personas`, so a test that left that read pointing at
    the shipped registry would be asserting the *shipped* debugger's alias.
    """
    _use_registry(monkeypatch, dict(PERSONAS))


def _use_registry(
    monkeypatch: pytest.MonkeyPatch, registry: dict[str, Persona]
) -> None:
    """Install one registry map on both sides of the boundary."""
    monkeypatch.setattr("tests.test_interpreter.PERSONAS", registry)
    monkeypatch.setattr("factory.config.load_personas", lambda path=None: registry)


def as_json_document(status: Any) -> dict[str, Any]:
    """The document `ergane build status --json` prints, from a real status.

    `_query_status` calls `handle.query("epic_status")` with no result type, so
    what the CLI holds is the payload decoded as plain JSON rather than the
    dataclass this test was handed. Re-encoding through the converter the
    factory actually runs is that same trip, in-process.
    """
    payload = default_data_converter().payload_converter.to_payload(status)
    document: dict[str, Any] = json.loads(payload.data)
    return document


def node_line(rendered: str, node_id: str = NODE) -> str:
    """The one line of the human status that belongs to a node."""
    lines = [line for line in rendered.splitlines() if line.startswith(node_id)]
    assert len(lines) == 1, f"expected one '{node_id}' line in:\n{rendered}"
    return lines[0]


# --- T020 [US3] (spec US3-S1) -------------------------------------------------


async def test_every_attempt_in_a_history_names_the_persona_and_model_it_ran(
    env: Any,
) -> None:
    """A history spanning two personas names both, attempt by attempt.

    Three failing attempts spend the ordinary budget on the node's own persona;
    the fourth is the debugger rung, which US1 made run the debugger's model.
    The JSON status is where that difference becomes checkable without a live
    process list — so every record carries the alias its own attempt ran under,
    and the rung's record carries the rung's.
    """
    script = ScriptedWorld(
        {NODE: [failing(n) for n in (1, 2, 3, 4)]},
        client=env.client,
        press="KILL",
    )

    status = await run_epic(env, script, graph=one_node())

    history = as_json_document(status)["nodes"][NODE]["history"]
    assert [record["attempt"] for record in history] == [1, 2, 3, 4]
    assert [record["persona"] for record in history] == [
        "implementer",
        "implementer",
        "implementer",
        DEBUGGER_PERSONA,
    ]
    assert [record["model_alias"] for record in history] == [
        MODEL_ALIAS,
        MODEL_ALIAS,
        MODEL_ALIAS,
        DEBUGGER_ALIAS,
    ]


# --- T021 [US3] (spec US3-S2) -------------------------------------------------


async def test_the_human_status_names_the_current_attempts_persona_and_model(
    env: Any,
) -> None:
    """The line an operator reads says what the node's latest attempt ran.

    The JSON above is the record; this is the surface anyone watching an epic
    actually sees. The node's fourth attempt is the debugger rung, so its line
    must name the debugger and the debugger's alias — and must not still be
    reporting the implementer's, which is what the first eight days of this
    defect looked like from the outside.
    """
    script = ScriptedWorld(
        {NODE: [failing(n) for n in (1, 2, 3, 4)]},
        client=env.client,
        press="KILL",
    )

    status = await run_epic(env, script, graph=one_node())

    document = as_json_document(status)
    line = node_line(render_status(EPIC_ID, document, "COMPLETED"))
    assert DEBUGGER_PERSONA in line
    assert DEBUGGER_ALIAS in line
    assert MODEL_ALIAS not in line


async def test_a_node_that_never_dispatched_names_no_persona_or_model() -> None:
    """The control: a node with no attempt reports no routing at all.

    A status line that named a persona for work nobody has done would be the
    same fabrication in the other direction — the operator would read a model
    that has not run, and cannot tell it from one that has.
    """
    document: dict[str, Any] = {
        "epic_state": "RUNNING",
        "nodes": {
            NODE: {
                "state": NodeState.PENDING,
                "attempt": 0,
                "branch": f"factory/{EPIC_ID}/{NODE}",
                "persona": "",
                "model_alias": UNRESOLVED_MODEL_ALIAS,
                "history": [],
            }
        },
    }

    line = node_line(render_status(EPIC_ID, document, "RUNNING"))
    assert "persona" not in line
    assert UNRESOLVED_MODEL_ALIAS not in line


# --- T022 [US3] (spec US3-S3) -------------------------------------------------


async def test_an_unresolvable_rung_is_reported_as_such_not_as_the_nodes_model(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rung nobody could resolve reports no model — never the node's.

    US1 kills the node rather than quietly running the node's model for the
    rung (US1-S5). This is the reporting half of that refusal: the persona the
    rung asked for is named, the alias reads `unresolved`, and the node's own
    alias appears nowhere on the line. Reporting `implementer-alias` here would
    tell an operator the epic did exactly what it failed to do.
    """
    _use_registry(
        monkeypatch,
        {name: p for name, p in PERSONAS.items() if name != DEBUGGER_PERSONA},
    )

    script = ScriptedWorld(
        {NODE: [failing(n) for n in (1, 2, 3)]},
        client=env.client,
    )

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {NODE: NodeState.KILLED}
    assert attempt_counts(status) == {NODE: 3}, "the unresolvable rung ran nothing"

    node = as_json_document(status)["nodes"][NODE]
    assert node["persona"] == DEBUGGER_PERSONA
    assert node["model_alias"] == UNRESOLVED_MODEL_ALIAS

    # The three attempts that did run are unaffected: what the rung could not
    # resolve is not retro-applied to the work the node's own persona did.
    assert [record["model_alias"] for record in node["history"]] == [MODEL_ALIAS] * 3

    line = node_line(render_status(EPIC_ID, as_json_document(status), "COMPLETED"))
    assert DEBUGGER_PERSONA in line
    assert UNRESOLVED_MODEL_ALIAS in line
    assert MODEL_ALIAS not in line
