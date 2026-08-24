"""Turn enriched aliases into a proposed persona mapping (US2).

Pure functions only: input is a mapping of persona name -> `Persona` and a
tuple of `EnrichmentRecord`.  Output is a mapping of gateway persona name to
one of:

* `ProposedMapping` — a primary, a fallback, and a human-readable reason.
* `OperatorChoice` — no classified alias qualified; the operator must pick from
  the candidate list.
* `Refusal` — no candidate satisfies a hard requirement, and there are no
  unclassified aliases to defer the decision to the operator.

The requirements table (`PERSONA_REQUIREMENTS`) is declared as data and covers
every LLM persona in the shipped example registry.  Deterministic and
subscription personas are excluded by `routes_through_gateway`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from factory.config import Persona
from factory.discovery.llm_enrichment import EnrichmentRecord


class RankingCriterion(str, Enum):
    """Declarative knobs the requirements table uses to rank candidates."""

    PREF_REASONING = "pref_reasoning"
    PREF_LARGEST_CONTEXT = "pref_largest_context"
    PREF_CHEAPEST = "pref_cheapest"
    AVOID_IMPLEMENTER_PRIMARY = "avoid_implementer_primary"


class Capability(str, Enum):
    """Capabilities a persona's hard requirement can demand."""

    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    REASONING = "reasoning"


@dataclass(frozen=True)
class PersonaRequirement:
    """One row of the requirements table.

    `hard` lists capabilities an alias must declare to be eligible.
    `primary_rank` and `fallback_rank` order the eligible aliases.
    `description` is the human-readable ruling that drives the row.
    """

    name: str
    hard: tuple[Capability, ...]
    primary_rank: tuple[RankingCriterion, ...]
    fallback_rank: tuple[RankingCriterion, ...]
    description: str


#: Requirements table keyed by persona name, one row per LLM persona in the
#: shipped example.  Content follows the spec's ruling verbatim.
PERSONA_REQUIREMENTS: dict[str, PersonaRequirement] = {
    "implementer": PersonaRequirement(
        name="implementer",
        hard=(Capability.TOOL_CALLING,),
        primary_rank=(
            RankingCriterion.PREF_LARGEST_CONTEXT,
            RankingCriterion.PREF_CHEAPEST,
        ),
        fallback_rank=(
            RankingCriterion.PREF_LARGEST_CONTEXT,
            RankingCriterion.PREF_CHEAPEST,
        ),
        description="tool-calling required, largest context",
    ),
    "judge": PersonaRequirement(
        name="judge",
        hard=(Capability.STRUCTURED_OUTPUT,),
        primary_rank=(
            RankingCriterion.AVOID_IMPLEMENTER_PRIMARY,
            RankingCriterion.PREF_REASONING,
            RankingCriterion.PREF_CHEAPEST,
        ),
        fallback_rank=(
            RankingCriterion.PREF_REASONING,
            RankingCriterion.PREF_CHEAPEST,
        ),
        description="structured output required, reasoning preferred, distinct from implementer primary",
    ),
    "debugger": PersonaRequirement(
        name="debugger",
        hard=(Capability.TOOL_CALLING,),
        primary_rank=(
            RankingCriterion.PREF_CHEAPEST,
            RankingCriterion.PREF_LARGEST_CONTEXT,
        ),
        fallback_rank=(
            RankingCriterion.PREF_CHEAPEST,
            RankingCriterion.PREF_LARGEST_CONTEXT,
        ),
        description="tool-calling required",
    ),
    "closer": PersonaRequirement(
        name="closer",
        hard=(Capability.TOOL_CALLING,),
        primary_rank=(
            RankingCriterion.PREF_CHEAPEST,
            RankingCriterion.PREF_LARGEST_CONTEXT,
        ),
        fallback_rank=(
            RankingCriterion.PREF_CHEAPEST,
            RankingCriterion.PREF_LARGEST_CONTEXT,
        ),
        description="cheapest that supports tools",
    ),
    "architect": PersonaRequirement(
        name="architect",
        hard=(),
        primary_rank=(
            RankingCriterion.PREF_REASONING,
            RankingCriterion.PREF_LARGEST_CONTEXT,
            RankingCriterion.PREF_CHEAPEST,
        ),
        fallback_rank=(
            RankingCriterion.PREF_REASONING,
            RankingCriterion.PREF_LARGEST_CONTEXT,
            RankingCriterion.PREF_CHEAPEST,
        ),
        description="reasoning preferred",
    ),
    "researcher": PersonaRequirement(
        name="researcher",
        hard=(),
        primary_rank=(
            RankingCriterion.PREF_REASONING,
            RankingCriterion.PREF_CHEAPEST,
            RankingCriterion.PREF_LARGEST_CONTEXT,
        ),
        fallback_rank=(
            RankingCriterion.PREF_REASONING,
            RankingCriterion.PREF_CHEAPEST,
            RankingCriterion.PREF_LARGEST_CONTEXT,
        ),
        description="reasoning preferred",
    ),
}


@dataclass(frozen=True)
class ProposedMapping:
    """A persona mapped to a primary and fallback, with the reason for each."""

    persona: str
    primary: str
    fallback: str
    reason: str


@dataclass(frozen=True)
class OperatorChoice:
    """No classified alias qualified; the operator must pick."""

    persona: str
    reason: str
    candidates: tuple[str, ...]
    primary: str | None = None
    fallback: str | None = None


@dataclass(frozen=True)
class Refusal:
    """No candidate satisfies a hard requirement, with no unclassified fallback."""

    persona: str
    requirement: str
    candidates: tuple[str, ...]
    primary: str | None = None
    fallback: str | None = None


ProposalResult = ProposedMapping | OperatorChoice | Refusal


def _has_hard(record: EnrichmentRecord, capability: Capability) -> bool:
    if capability == Capability.TOOL_CALLING:
        return record.tool_calling
    if capability == Capability.STRUCTURED_OUTPUT:
        return record.structured_output
    if capability == Capability.REASONING:
        return record.reasoning
    return False


def _price(record: EnrichmentRecord) -> float:
    """Best-effort per-token price; unknown parts are treated as large."""
    inp = record.input_cost_per_token
    out = record.output_cost_per_token
    if inp is None and out is None:
        return float("inf")
    return (inp or 0.0) + (out or 0.0)


def _score(
    record: EnrichmentRecord,
    criteria: tuple[RankingCriterion, ...],
    implementer_primary: str | None,
) -> tuple:
    """Return a sortable score where lower is better.

    Each criterion contributes one tuple slot, in declaration order.  Unknown
    values are pushed to the end of the sort by using a large sentinel.
    """
    scores: list = []
    for criterion in criteria:
        if criterion == RankingCriterion.PREF_REASONING:
            # reasoning preferred -> False sorts before True when we want
            # reasoners first, so we negate by storing not-reasoning.
            scores.append(not record.reasoning)
        elif criterion == RankingCriterion.PREF_LARGEST_CONTEXT:
            ctx = record.context_window
            scores.append(-(ctx if ctx is not None else 0))
        elif criterion == RankingCriterion.PREF_CHEAPEST:
            scores.append(_price(record))
        elif criterion == RankingCriterion.AVOID_IMPLEMENTER_PRIMARY:
            same = implementer_primary is not None and record.alias == implementer_primary
            scores.append(same)
    return tuple(scores)


def _pick_primary_fallback(
    records: tuple[EnrichmentRecord, ...],
    requirement: PersonaRequirement,
    implementer_primary: str | None,
) -> tuple[EnrichmentRecord, EnrichmentRecord] | None:
    """Return (primary, fallback) from classified, eligible records, or None."""
    eligible = [
        r for r in records if not r.unclassified and all(_has_hard(r, h) for h in requirement.hard)
    ]
    if len(eligible) >= 1:
        primary = min(
            eligible,
            key=lambda r: _score(r, requirement.primary_rank, implementer_primary),
        )
        fallback_candidates = [r for r in eligible if r.alias != primary.alias]
        if fallback_candidates:
            fallback = min(
                fallback_candidates,
                key=lambda r: _score(r, requirement.fallback_rank, implementer_primary),
            )
        else:
            fallback = primary
        return primary, fallback
    return None


def _build_reason(
    primary: EnrichmentRecord,
    requirement: PersonaRequirement,
    implementer_primary: str | None,
) -> str:
    """A short human-readable reason for the proposed primary."""
    parts: list[str] = []
    for capability in requirement.hard:
        if capability == Capability.TOOL_CALLING:
            parts.append("tool-calling ✓")
        elif capability == Capability.STRUCTURED_OUTPUT:
            parts.append("structured output ✓")
    if primary.reasoning and RankingCriterion.PREF_REASONING in requirement.primary_rank:
        parts.append("reasoning ✓")
    if RankingCriterion.PREF_LARGEST_CONTEXT in requirement.primary_rank and primary.context_window:
        parts.append(f"largest context ({primary.context_window:,} tokens)")
    if RankingCriterion.PREF_CHEAPEST in requirement.primary_rank:
        price = _price(primary)
        if price != float("inf"):
            parts.append("cheapest of qualifying candidates")
    if RankingCriterion.AVOID_IMPLEMENTER_PRIMARY in requirement.primary_rank:
        if implementer_primary and primary.alias != implementer_primary:
            parts.append("distinct from implementer primary")
        elif implementer_primary:
            parts.append("only qualifying candidate")
    if not parts:
        parts.append(requirement.description)
    return "; ".join(parts)


def build_proposal(
    personas: dict[str, Persona],
    records: tuple[EnrichmentRecord, ...],
) -> dict[str, ProposalResult]:
    """Build a proposal mapping every gateway persona to a primary/fallback or a refusal.

    The returned mapping contains one entry for every persona whose
    `routes_through_gateway` property is True.  Unclassified aliases are never
    auto-assigned: when no classified alias satisfies a persona's hard
    requirements but unclassified aliases exist, the slot is an `OperatorChoice`
    with the full candidate list.  When no candidate of any kind satisfies a hard
    requirement, the slot is a `Refusal` naming the persona, the requirement and
    the considered aliases.
    """
    classified = tuple(r for r in records if not r.unclassified)
    unclassified = tuple(r for r in records if r.unclassified)
    all_aliases = tuple(r.alias for r in records)

    # Implementer is ranked first because the judge's ranking depends on it.
    ordered_personas = sorted(
        (name for name, p in personas.items() if p.routes_through_gateway),
        key=lambda n: (n != "implementer", n),
    )

    result: dict[str, ProposalResult] = {}
    implementer_primary: str | None = None

    for name in ordered_personas:
        requirement = PERSONA_REQUIREMENTS.get(name)
        if requirement is None:
            # Should not happen for a complete table; treat as operator choice
            # so we do not silently assign.
            result[name] = OperatorChoice(
                persona=name,
                reason="needs the operator's choice (no requirements row)",
                candidates=all_aliases,
            )
            continue

        pick = _pick_primary_fallback(classified, requirement, implementer_primary)

        if pick is not None:
            primary, fallback = pick
            if name == "implementer":
                implementer_primary = primary.alias
            result[name] = ProposedMapping(
                persona=name,
                primary=primary.alias,
                fallback=fallback.alias,
                reason=_build_reason(primary, requirement, implementer_primary),
            )
            continue

        if unclassified:
            result[name] = OperatorChoice(
                persona=name,
                reason="needs the operator's choice (no classified alias met the requirements)",
                candidates=all_aliases,
            )
            continue

        result[name] = Refusal(
            persona=name,
            requirement=requirement.description,
            candidates=all_aliases,
        )

    return result
