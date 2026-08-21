"""User Story 1 — the rung that changes the persona changes the model.

The defect these tests pin: a rung selects a *persona* (the debugger on
exhaustion, the debugger again on a conflicted re-sync), and the attempt it
builds was carrying the **node's** model alias regardless. The persona reached
the virtual key's alias (D-026), so the ledger said `debugger` while the process
ran the implementer's model — which is how the defect survived being found
twice.

Every assertion here is over the `AttemptContext` the one agent-touching
activity is handed, because that is the payload that decides which model runs,
and over the `IssueKeyInput` beside it, because a key constrained to the node's
aliases would refuse the rung's model at the proxy and make a correct routing
decision fail anyway.

Two of the six tests are controls, and they are the point (plan trap 3): a
change that returned the rung's model for *every* attempt would satisfy the
debugger scenarios perfectly and silently promote every ordinary attempt to a
model nobody chose. `test_an_ordinary_attempt_carries_the_nodes_own_model` and
`test_a_clean_resync_recovery_keeps_the_nodes_own_persona_and_model` are what
make that mutation fail.

The scripted world of `tests.test_interpreter` is reused rather than rebuilt:
its registry already routes `implementer` and `debugger` to *different* model
aliases, which is exactly the fixture this story needs.
"""

from __future__ import annotations

from typing import Any

import pytest

from factory.config import SUBSCRIPTION_AGENT, Persona, WriteScope
from factory.verify.ladder import DEBUGGER_PERSONA
from factory.workgraph.models import NodeState

from tests.test_interpreter import (
    FALLBACK_ALIAS,
    MODEL_ALIAS,
    PERSONAS,
    ScriptedWorld,
    attempt_counts,
    checks_failed_snapshot,
    conflict_snapshot,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    failing,
    merged_snapshot,
    one_node,
    passing,
    run_epic,
    states,
)

#: The debugger's own alias in the interpreter's test registry — deliberately
#: not `MODEL_ALIAS`, so an attempt that carries the node's model instead of the
#: rung's is visible rather than indistinguishable.
DEBUGGER_ALIAS = PERSONAS[DEBUGGER_PERSONA].model


def _contexts(script: ScriptedWorld, node_id: str = "us1") -> list[Any]:
    """Every attempt context the world was handed for one node, in order."""
    return [c for c in script.attempts if c.node_id == node_id]


def _keys(script: ScriptedWorld, node_id: str = "us1") -> list[Any]:
    """Every key issuance request for one node, in order."""
    return [k for k in script.key_requests if k.node_id == node_id]


@pytest.fixture(autouse=True)
def registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Persona]:
    """Point every registry read — activity-side and workflow-side — at one map.

    The scripted `resolve_graph` resolves nodes against the interpreter module's
    `PERSONAS`; the workflow's own snapshot reads `factory.config.load_personas`
    for the halves a `ResolvedNode` does not carry — the `agent` value, and the
    entries for personas no node declares. A fixture that moved only one of them
    would be asserting routing against two different registries, which is the
    disagreement this story exists to make impossible.

    Autouse and returned mutable, so a test that needs a different registry
    edits this one and calls `_use_registry` again.
    """
    _use_registry(monkeypatch, dict(PERSONAS))
    return dict(PERSONAS)


def _use_registry(
    monkeypatch: pytest.MonkeyPatch, registry: dict[str, Persona]
) -> None:
    """Install one registry map on both sides of the boundary."""
    monkeypatch.setattr("tests.test_interpreter.PERSONAS", registry)
    monkeypatch.setattr("factory.config.load_personas", lambda path=None: registry)


# --- T001 [US1] (spec US1-S1) -------------------------------------------------


async def test_the_debugger_rung_carries_the_debugger_personas_model(
    env: Any,
) -> None:
    """The debugger cycle runs the debugger persona's model, not the node's.

    Three failing attempts spend the ordinary budget; the fourth is the rung.
    The node is routed to `implementer` (`MODEL_ALIAS`) and the rung to
    `debugger` (`DEBUGGER_ALIAS`), so the attempt context of the fourth must
    carry the second — and its key must be constrained to the aliases that
    persona names, or the proxy would refuse the model the rung just chose.
    """
    script = ScriptedWorld(
        {"us1": [failing(n) for n in (1, 2, 3, 4)]},
        client=env.client,
        press="KILL",
    )

    await run_epic(env, script, graph=one_node())

    contexts = _contexts(script)
    assert len(contexts) == 4, "three attempts and one debugger cycle"
    assert contexts[3].model_alias == DEBUGGER_ALIAS

    debugger_key = _keys(script)[3]
    assert debugger_key.persona == DEBUGGER_PERSONA
    assert debugger_key.models == [DEBUGGER_ALIAS]


# --- T002 [US1] (spec US1-S2) — the control -----------------------------------


async def test_an_ordinary_attempt_carries_the_nodes_own_model(env: Any) -> None:
    """The control: nothing but a rung changes the model an attempt runs.

    Same node, same world, same registry as the test above. A change that
    returned the rung's persona for every attempt passes US1-S1 and fails here,
    which is the whole reason this test exists (plan trap 3).
    """
    script = ScriptedWorld(
        {"us1": [failing(n) for n in (1, 2, 3, 4)]},
        client=env.client,
        press="KILL",
    )

    await run_epic(env, script, graph=one_node())

    contexts = _contexts(script)
    assert [c.model_alias for c in contexts[:3]] == [MODEL_ALIAS] * 3
    assert [k.models for k in _keys(script)[:3]] == [[MODEL_ALIAS, FALLBACK_ALIAS]] * 3


# --- T003 [US1] (spec US1-S3) -------------------------------------------------


async def test_a_conflicted_recovery_carries_the_conflict_rungs_model(
    env: Any,
) -> None:
    """A conflicted re-sync routes to the debugger — persona *and* model.

    The recovery attempt already minted its key for the conflict rung's persona
    (D-026); what it did not do was run that persona's model. Both halves are
    asserted here, because the persona alone is what made this defect invisible.
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=env.client)
    script.script_landing("us1", conflict_snapshot(), merged_snapshot())
    script.script_sync(
        "us1", clean=False, base_ref="c0ffee", conflicted_files=("src/calc.py",)
    )

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    recovery = _contexts(script)[1]
    assert recovery.model_alias == DEBUGGER_ALIAS

    recovery_key = _keys(script)[1]
    assert recovery_key.persona == DEBUGGER_PERSONA
    assert recovery_key.models == [DEBUGGER_ALIAS]


# --- T004 [US1] (spec US1-S4) — the second control ----------------------------


async def test_a_clean_resync_recovery_keeps_the_nodes_own_persona_and_model(
    env: Any,
) -> None:
    """The second control: a clean re-sync is still the node's own work.

    The two recovery paths fork on `sync.clean` — the conflicted one hands the
    tree to the debugger, the clean one re-runs the node's own persona against a
    base that moved under it — and they must keep forking. A change that routed
    every recovery to the conflict rung passes US1-S3 and fails here.
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=env.client)
    script.script_landing("us1", checks_failed_snapshot(), merged_snapshot())
    script.script_sync("us1", clean=True, base_ref="c0ffee")

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    recovery = _contexts(script)[1]
    assert recovery.model_alias == MODEL_ALIAS

    recovery_key = _keys(script)[1]
    assert recovery_key.persona == "implementer"
    assert recovery_key.models == [MODEL_ALIAS, FALLBACK_ALIAS]


# --- T005 [US1] (spec US1-S5) -------------------------------------------------


async def test_a_rung_persona_absent_from_the_snapshot_fails_the_node(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rung nobody can resolve ends the node, naming the persona and the rung.

    The silent fallback is the failure mode being ruled out: a debugger rung
    that quietly ran the node's model would spend a cycle pretending to be a
    stronger builder. The node is killed instead, with a reason an operator can
    act on — and no fourth attempt is dispatched.
    """
    _use_registry(
        monkeypatch,
        {name: p for name, p in PERSONAS.items() if name != DEBUGGER_PERSONA},
    )

    script = ScriptedWorld(
        {"us1": [failing(n) for n in (1, 2, 3)]},
        client=env.client,
    )

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.KILLED}
    assert attempt_counts(status) == {"us1": 3}
    assert len(_contexts(script)) == 3, "the unresolvable rung dispatched nothing"

    reason = status.nodes["us1"].terminal_reason or ""
    assert DEBUGGER_PERSONA in reason
    assert "rung" in reason


# --- T006 [US1] (spec US1-S6) -------------------------------------------------


async def test_agent_and_model_alias_come_from_one_resolved_entry(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One entry answers both questions, so the two can never disagree (FR-002).

    The fixture is a debugger persona whose `agent` *and* `model` both differ
    from the node's. Resolved separately — the agent from one lookup, the alias
    from the node's resolution — the attempt would carry a subscription agent
    running a gateway alias, which is the disagreement this requirement exists
    to make impossible. Both fields move together, at the same rung, or neither
    does.
    """
    disagreeing = dict(PERSONAS)
    disagreeing[DEBUGGER_PERSONA] = Persona(
        name=DEBUGGER_PERSONA,
        agent=SUBSCRIPTION_AGENT,
        model=DEBUGGER_ALIAS,
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=PERSONAS[DEBUGGER_PERSONA].timeout_s,
    )
    _use_registry(monkeypatch, disagreeing)

    script = ScriptedWorld(
        {"us1": [failing(n) for n in (1, 2, 3, 4)]},
        client=env.client,
        press="KILL",
    )

    await run_epic(env, script, graph=one_node())

    ordinary, rung = _contexts(script)[0], _contexts(script)[3]
    assert (ordinary.agent, ordinary.model_alias) == (
        PERSONAS["implementer"].agent,
        MODEL_ALIAS,
    )
    assert (rung.agent, rung.model_alias) == (SUBSCRIPTION_AGENT, DEBUGGER_ALIAS)

    # The same pair reaches key issuance, from the same entry: an attempt whose
    # key was minted for one persona's agent and run under another's model is
    # the disagreement in its most expensive form (constitution V).
    ordinary_key, rung_key = _keys(script)[0], _keys(script)[3]
    assert (ordinary_key.agent, ordinary_key.models) == (
        PERSONAS["implementer"].agent,
        [MODEL_ALIAS, FALLBACK_ALIAS],
    )
    assert (rung_key.agent, rung_key.models) == (SUBSCRIPTION_AGENT, [DEBUGGER_ALIAS])
