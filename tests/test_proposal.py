"""US2: turn enriched aliases into a proposed persona mapping.

Every test here is a pure function over enrichment records; no network.
"""

from __future__ import annotations

import pytest

from factory.config import Persona, WriteScope
from factory.discovery.llm_enrichment import EnrichmentRecord
from factory.discovery.proposal import (
    PERSONA_REQUIREMENTS,
    build_proposal,
    OperatorChoice,
    ProposedMapping,
    Refusal,
)


def _personas() -> dict[str, Persona]:
    """Return the shipped example personas as parsed Persona objects."""
    return {
        "architect": Persona(
            name="architect",
            agent="claude-code",
            model="example/your-architect-model",
            fallback="example/your-fallback-model",
            skills=("codebase-design", "design-an-interface", "domain-modeling"),
            write_scope=WriteScope.DOCS,
            needs_worktree=True,
            timeout_s=7200,
        ),
        "implementer": Persona(
            name="implementer",
            agent="claude-code",
            model="example/your-implementer-model",
            fallback="example/your-fallback-model",
            skills=("implement", "tdd"),
            write_scope=WriteScope.WORKTREE,
            needs_worktree=True,
            timeout_s=14400,
            context_window=262144,
        ),
        "verifier": Persona(
            name="verifier",
            agent="none",
            model=None,
            fallback=None,
            skills=(),
            write_scope=WriteScope.READ,
            needs_worktree=True,
            timeout_s=None,
        ),
        "judge": Persona(
            name="judge",
            agent="claude-code",
            model="example/your-judge-model",
            fallback="example/your-fallback-model",
            skills=("code-review",),
            write_scope=WriteScope.READ,
            needs_worktree=False,
            timeout_s=3600,
        ),
        "closer": Persona(
            name="closer",
            agent="claude-code",
            model="example/your-closer-model",
            fallback="example/your-implementer-model",
            skills=("implement", "tdd"),
            write_scope=WriteScope.WORKTREE,
            needs_worktree=True,
            timeout_s=14400,
            context_window=1000000,
        ),
        "debugger": Persona(
            name="debugger",
            agent="claude-code",
            model="example/your-debugger-model",
            fallback="example/your-fallback-model",
            skills=("diagnosing-bugs",),
            write_scope=WriteScope.WORKTREE,
            needs_worktree=True,
            timeout_s=10800,
        ),
        "researcher": Persona(
            name="researcher",
            agent="claude-code",
            model="example/your-researcher-model",
            fallback="example/your-fallback-model",
            skills=("research", "grill-with-docs"),
            write_scope=WriteScope.READ,
            needs_worktree=False,
            timeout_s=7200,
        ),
    }


# T005 [US2]: rich fixtures yield full proposals with reasons; the judge's
# primary differs from the implementer's when a qualifying alternative exists.
def test_rich_fixtures_propose_every_gateway_persona() -> None:
    records = (
        EnrichmentRecord(
            alias="claude-sonnet-4",
            tool_calling=True,
            structured_output=True,
            reasoning=False,
            context_window=200000,
            input_cost_per_token=3.0e-6,
            output_cost_per_token=1.5e-5,
            detail="rich",
        ),
        EnrichmentRecord(
            alias="claude-opus-4",
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            context_window=200000,
            input_cost_per_token=1.5e-5,
            output_cost_per_token=7.5e-5,
            detail="rich",
        ),
        EnrichmentRecord(
            alias="cheap-tool-caller",
            tool_calling=True,
            structured_output=False,
            reasoning=False,
            context_window=8000,
            input_cost_per_token=1.0e-7,
            output_cost_per_token=1.0e-7,
            detail="rich",
        ),
    )

    proposal = build_proposal(personas=_personas(), records=records)

    # Every gateway persona gets a proposed slot; verifier is omitted.
    gateway_names = {
        name for name, p in _personas().items() if p.routes_through_gateway
    }
    assert set(proposal) == gateway_names
    assert "verifier" not in proposal

    for result in proposal.values():
        assert isinstance(result, ProposedMapping)
        assert result.primary is not None
        assert result.fallback is not None
        assert result.reason

    implementer = proposal["implementer"]
    judge = proposal["judge"]

    # Implementer: tool-calling required, largest context.
    assert implementer.primary in ("claude-sonnet-4", "claude-opus-4")
    assert "context" in implementer.reason.lower()
    assert "tool" in implementer.reason.lower() or "calling" in implementer.reason.lower()

    # Judge: structured output required; distinct from implementer if possible.
    assert judge.primary != implementer.primary
    assert judge.primary in ("claude-sonnet-4", "claude-opus-4")
    assert "structured" in judge.reason.lower()

    # Closer: cheapest that supports tools.
    closer = proposal["closer"]
    assert closer.primary == "cheap-tool-caller"
    assert "cheap" in closer.reason.lower() or "cost" in closer.reason.lower()

    # Debugger: tool-calling required.
    debugger = proposal["debugger"]
    assert debugger.primary == "cheap-tool-caller"
    assert "tool" in debugger.reason.lower() or "calling" in debugger.reason.lower()

    # Architect / researcher: reasoning preferred.
    assert proposal["architect"].primary == "claude-opus-4"
    assert proposal["researcher"].primary == "claude-opus-4"
    assert "reasoning" in proposal["architect"].reason.lower()
    assert "reasoning" in proposal["researcher"].reason.lower()

    # Requirements table is readable as data by the test.
    assert "judge" in PERSONA_REQUIREMENTS
    assert "implementer" in PERSONA_REQUIREMENTS
    req = PERSONA_REQUIREMENTS["judge"]
    assert "structured" in req.description.lower()
    assert "implementer" in req.description.lower()


# T006 [US2]: all-unclassified fixtures: every slot is "needs the operator's
# choice" with candidates attached; nothing auto-assigned.
def test_all_unclassified_asks_operator_for_every_slot() -> None:
    records = (
        EnrichmentRecord(alias="my-gpu-box", unclassified=True, detail="bare gateway"),
        EnrichmentRecord(alias="my-gpu-box-large", unclassified=True, detail="bare gateway"),
    )

    proposal = build_proposal(personas=_personas(), records=records)

    gateway_names = {
        name for name, p in _personas().items() if p.routes_through_gateway
    }
    assert set(proposal) == gateway_names

    for name, result in proposal.items():
        assert isinstance(result, OperatorChoice), f"{name} was auto-assigned: {result}"
        assert result.primary is None
        assert result.fallback is None
        assert "operator" in result.reason.lower()
        assert set(result.candidates) == {"my-gpu-box", "my-gpu-box-large"}


# T007 [US2]: no alias satisfies the judge's hard requirement -> a refusal
# naming the judge, the requirement, and the aliases considered.
def test_no_qualifying_judge_is_a_refusal() -> None:
    # Tool-callers exist, so implementer / debugger / closer can qualify, but
    # nothing supports structured output, so the judge cannot.
    records = (
        EnrichmentRecord(
            alias="llama3.1",
            tool_calling=True,
            structured_output=False,
            reasoning=False,
            context_window=131072,
            detail="ollama",
        ),
        EnrichmentRecord(
            alias="qwq",
            tool_calling=False,
            structured_output=False,
            reasoning=True,
            context_window=32768,
            detail="ollama",
        ),
    )

    proposal = build_proposal(personas=_personas(), records=records)

    assert isinstance(proposal["judge"], Refusal)
    refusal = proposal["judge"]
    assert refusal.persona == "judge"
    assert "structured output" in refusal.requirement.lower()
    assert set(refusal.candidates) == {"llama3.1", "qwq"}

    # Other personas still get proposals from the tool-caller / reasoner.
    assert isinstance(proposal["implementer"], ProposedMapping)
    assert isinstance(proposal["debugger"], ProposedMapping)
    assert isinstance(proposal["researcher"], ProposedMapping)


# T007b: empty alias list -> every gateway persona refused, naming the
# requirement and an empty candidate list.
def test_empty_alias_list_refuses_every_persona() -> None:
    proposal = build_proposal(personas=_personas(), records=())

    gateway_names = {
        name for name, p in _personas().items() if p.routes_through_gateway
    }
    assert set(proposal) == gateway_names

    for result in proposal.values():
        assert isinstance(result, Refusal)
        assert result.candidates == ()
        assert result.requirement
