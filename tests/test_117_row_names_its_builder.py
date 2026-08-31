"""The attempt row says who built it (117 US2).

`VerificationResult` carried eighteen columns and not one of them was the
persona, the model or the route. The only authority for "which model built this
story" was the epic's Temporal start payload, which expires with the workflow,
and the on-disk `workgraph.json`, which lies for anything the roadmap
dispatched — so the question was unanswerable thirty days later, which is
exactly when it is asked.

Three columns answer it, and the whole difficulty is *where they are filled*
(plan trap 5). The debugger rung relabels the persona without re-resolving the
alias, so a row that looked the persona up at write time would record the
implementer's model for the one attempt the implementer did not run. These
tests therefore drive the real interpreter rather than the store: whether the
row names what actually ran is decided by the workflow, and only a run of the
workflow can say.

- **A gateway attempt names all three (US2-S1).** Through the store, so the
  claim is about the row an operator reads back and not about the object the
  composer returned.
- **A subscription attempt names its route (US2-S2).** The route is recorded as
  the subscription rather than left null — a null here would be
  indistinguishable from an unrecorded one.
- **A debugger rung names the model that ran (US2-S3, trap 5).** The rung's
  persona, the rung's alias and the rung's route, none of them the node's.
- **Old rows read unknown (US2-S4, trap 6).** Unknown is a *value*: a row
  written before the columns existed reads as one sentinel, never as an empty
  string that renders like a persona named "".
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from temporalio.testing import WorkflowEnvironment

from factory.config import ERGANE_PERSONAS_PATH_ENV
from factory.verify.ladder import DEBUGGER_PERSONA
from factory.verify.models import (
    ROUTE_GATEWAY,
    ROUTE_SUBSCRIPTION,
    UNKNOWN_BUILDER,
    VerificationResult,
)
from factory.verify.store import connect, node_history, upsert_result

#: The aliases the *registry* declares. Distinct from `MODEL_ALIAS`, which is
#: what the scripted `resolve_graph` resolves the node to, so a test can tell a
#: row that recorded the routing it ran under from one that re-derived an alias
#: from the registry at write time.
DEBUGGER_REGISTRY_ALIAS = "debugger-registry-alias"
IMPLEMENTER_REGISTRY_ALIAS = "implementer-registry-alias"


def _persona_entry(name: str, agent: str, model: str, timeout: int) -> str:
    return (
        f"{name}:\n"
        f"  agent: {agent}\n"
        f"  model: {model}\n"
        "  fallback: null\n"
        "  skills: []\n"
        "  write_scope: worktree\n"
        "  needs_worktree: true\n"
        f"  timeout: {timeout}\n"
    )


def registry(tmp_path: Path, *, implementer_agent: str) -> Path:
    """A registry the epic resolves against, written where the env var points.

    The interpreter reads the persona registry once at epic start for the facts
    a `ResolvedNode` does not carry — the `agent` beside each node's persona,
    and the entries for personas no node declares but a rung may select. That
    read is what decides an attempt's route, so a test that asserted a route
    while leaving the registry to whatever the host happens to have installed
    would be asserting the operator's dial (constitution IX).

    The debugger is deliberately routed differently from the node: its rung must
    move the persona, the alias *and* the route together.
    """
    path = tmp_path / "personas.yaml"
    path.write_text(
        _persona_entry(
            "implementer", implementer_agent, IMPLEMENTER_REGISTRY_ALIAS, 5400
        )
        + _persona_entry(
            DEBUGGER_PERSONA, "subscription", DEBUGGER_REGISTRY_ALIAS, 7200
        ),
        encoding="utf-8",
    )
    return path


def stored(tmp_path: Path, result: VerificationResult) -> VerificationResult:
    """The result as the store hands it back — the row, not the object.

    The scenarios are about what an operator reads thirty days later, so every
    assertion below is made against a value that survived a write and a read
    rather than against the bundle the composer returned.
    """
    with closing(connect(tmp_path / "read-back" / "verification.db")) as store:
        upsert_result(store, result)
        (row,) = node_history(store, result.epic_id, result.node_id)
    return row


async def records_of(
    tmp_path: Path, monkeypatch: Any, *, implementer_agent: str, node: str, script: Any
) -> list[VerificationResult]:
    """Run one epic against a scripted world and hand back a node's rows."""
    from tests.test_interpreter import run_epic

    monkeypatch.setenv(
        ERGANE_PERSONAS_PATH_ENV,
        str(registry(tmp_path, implementer_agent=implementer_agent)),
    )
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        world = script(env.client)
        await run_epic(env, world)
    finally:
        await env.shutdown()
    return [r for r in world.records if r.node_id == node]


# --- T010 [US2] (spec US2-S1) ------------------------------------------------


async def test_a_gateway_attempt_records_its_persona_alias_and_route(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """FR-005: the row carries the persona, the model alias and the route.

    The alias asserted is the one the *routing* resolved — the value the agent
    was actually dispatched under — and not the registry's, which is a second
    resolution that can disagree with it.
    """
    from tests.test_interpreter import MODEL_ALIAS, ScriptedWorld, all_passing

    [record] = await records_of(
        tmp_path,
        monkeypatch,
        implementer_agent="claude-code",
        node="us1",
        script=lambda client: ScriptedWorld(all_passing(), client=client),
    )

    row = stored(tmp_path, record)
    assert row.persona == "implementer"
    assert row.model_alias == MODEL_ALIAS
    assert row.route == ROUTE_GATEWAY
    # None of the three is the admitted gap: this attempt was recorded.
    assert UNKNOWN_BUILDER not in (row.persona, row.model_alias, row.route)


# --- T011 [US2] (spec US2-S2) ------------------------------------------------


async def test_a_subscription_attempt_records_the_subscription_route(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """FR-005: the route is the subscription, not a null nobody can read.

    A NULL route would be indistinguishable from a row nobody recorded a route
    for, which is precisely the reading FR-007 reserves for rows that predate
    the column.
    """
    from tests.test_interpreter import ScriptedWorld, all_passing

    [record] = await records_of(
        tmp_path,
        monkeypatch,
        implementer_agent="subscription",
        node="us1",
        script=lambda client: ScriptedWorld(all_passing(), client=client),
    )

    row = stored(tmp_path, record)
    assert row.route == ROUTE_SUBSCRIPTION
    assert row.route not in (None, "", UNKNOWN_BUILDER)
    assert row.persona == "implementer"


# --- T012 [US2] (spec US2-S3, trap 5) ----------------------------------------


async def test_a_debugger_rung_records_the_model_that_actually_ran(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """FR-006: the rung relabels the persona and the row must follow it.

    Three implementer attempts fail, the debugger cycle runs as the fourth, and
    a human presses KILL. The defect this rules out is a row that took the
    persona from the rung and the alias from the node — which is how a rung ran
    one model and reported another for eight days. The registry routes the
    debugger through the subscription and the node through the gateway, so an
    inherited value shows up on all three columns rather than only on the one
    the fixture happened to vary.
    """
    from tests.test_interpreter import MODEL_ALIAS, exhausted

    records = await records_of(
        tmp_path,
        monkeypatch,
        implementer_agent="claude-code",
        node="us1",
        script=lambda client: exhausted("KILL", client),
    )

    assert [r.attempt for r in records] == [1, 2, 3, 4]
    ordinary, rung = records[:3], stored(tmp_path, records[3])
    assert [r.persona for r in ordinary] == ["implementer"] * 3
    assert [r.model_alias for r in ordinary] == [MODEL_ALIAS] * 3

    assert rung.persona == DEBUGGER_PERSONA
    # The alias the rung resolved, never the node's — the stale one.
    assert rung.model_alias == DEBUGGER_REGISTRY_ALIAS
    assert rung.model_alias != MODEL_ALIAS
    assert rung.route == ROUTE_SUBSCRIPTION


# --- T013 [US2] (spec US2-S4, trap 6) ----------------------------------------


def test_rows_predating_the_columns_read_as_unknown(tmp_path: Path) -> None:
    """FR-007: unknown is a value, and a migrated store keeps a fresh one's order.

    A store written before these columns existed knows nothing about who built
    its rows. The honest reading is one reserved sentinel — not NULL, which a
    renderer prints as nothing, and not `""`, which renders like a persona whose
    name is empty. And because the 117-US1 migration *rebuilds* this table while
    these three are appended to it, the two migrations have to compose in the
    one order that leaves a migrated store column-for-column identical to a
    fresh one (plan trap 2): the rebuild first, the additions after.
    """
    from tests.test_117_dispatch_scoped_rows import columns_of, legacy_store

    db_path = legacy_store(tmp_path)

    with closing(connect(db_path)) as migrated:
        with closing(connect(tmp_path / "fresh" / "verification.db")) as fresh:
            assert columns_of(migrated) == columns_of(fresh)
        assert [name for name, *_ in columns_of(migrated)[-3:]] == [
            "persona",
            "model_alias",
            "route",
        ]

        (old,) = node_history(migrated, *_LEGACY_ROW)
        assert (old.persona, old.model_alias, old.route) == (
            UNKNOWN_BUILDER,
            UNKNOWN_BUILDER,
            UNKNOWN_BUILDER,
        )
        # Stated separately because the sentinel is the whole point: none of
        # them may read as a silence or as a plausible value.
        for value in (old.persona, old.model_alias, old.route):
            assert value not in (None, "")


#: The epic and node the pre-117 fixture row belongs to.
_LEGACY_ROW = ("117-the-record-outlives-the-build", "us1")
