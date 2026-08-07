"""The pre-dispatch preflight checks a graph cannot carry (US2 FR-004/005/006).

Two read-only facts a `WorkGraph` cannot hold, read from the proxy before any
epic dispatches: the model aliases the registry names for an epic's personas
are *served*, and the first-attempt key aliases that epic will mint do not
*collide* with a live key. Both are knowable before a single credential is
issued, and finding them at dispatch costs one message instead of attempts,
issued keys and a burned node.

This is the pure core shared by the two callers that run a preflight:

- `factory-epic start` runs it in-process (CLI) before starting the workflow,
  so a misconfigured epic never becomes a workflow that has to be killed.
- the roadmap workflow (US2) runs it as an activity before starting each
  dispatchable spec's child epic, so a misconfigured spec *parks* with the
  finding verbatim rather than stalling the line (FR-006).

The split is the same one `factory/activities/merge_activities.py` draws for
onboarding: a pure library function (`check_aliases`) that both an offline
CLI path and an activity call, so the two surfaces cannot drift. The CLI owns
its own client/registry construction (it reads `personas.yaml` from its host
and dials the proxy from the environment); the activity owns its own. What
neither owns — the alias math, the finding wording, the read-failure shape —
lives here, once.

A proxy that does not answer is a **distinct** finding (`transport=True`)
naming the address tried — never a silent pass, and never conflated with
"not served" (FR-005). The caller decides what that means for an operator:
the CLI maps it to `EXIT_TRANSPORT`; the roadmap parks the spec with the
finding verbatim regardless, because a parked finding is what FR-006 demands
and a transport outage parks the same way an unserved alias does.

`PreflightFinding` is the same shape as 003's onboarding `Finding`
(check/passed/detail) so the two surfaces read alike; `transport` is the
FR-005 discriminator. It lived in the CLI until US2 gave it a second caller —
the roadmap pre-dispatch activity — so it moved here, and the CLI re-exports
it so nothing that imported the CLI's name changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from factory.activities.usage_activities import key_alias_for
from factory.config import Persona
from factory.usage.litellm_client import LiteLLMClient, LiteLLMError
from factory.workgraph.models import WorkGraph
from factory.workgraph.workflow import JUDGE_PERSONA


@dataclass(frozen=True)
class PreflightFinding:
    """One fact the preflight checked before dispatch (US2 FR-004/005/006).

    The same shape as 003's onboarding `Finding` (check/passed/detail) so the
    two surfaces read alike; a local type was defined only because 003 had not
    landed, and it must be swapped for the shared type the moment it is
    importable rather than kept as a near-duplicate.

    `transport` is the FR-005 discriminator: `True` when the proxy would not
    answer a preflight read (so the operator's move is to go look at the
    proxy), `False` when it answered and something the operator can fix in the
    registry or the credential store is wrong.
    """

    check: str
    passed: bool
    detail: str
    transport: bool = False


def first_attempt_aliases(graph: WorkGraph) -> set[str]:
    """The aliases this epic's first attempts will mint (US2 FR-006).

    Each node's attempt-1 key (under its persona) and the judge's attempt-1 key
    (the judge scores while the node's key is live, on its own alias). These are
    the deterministic aliases the proxy would reject a duplicate of at dispatch
    — a collision knowable before any key is issued.
    """
    aliases: set[str] = set()
    for node in graph.nodes:
        aliases.add(key_alias_for(graph.epic_id, node.id, 1, node.persona))
        aliases.add(key_alias_for(graph.epic_id, node.id, 1, JUDGE_PERSONA))
    return aliases


def aliases_to_check(
    graph: WorkGraph, registry: Mapping[str, Persona]
) -> dict[str, set[str]]:
    """alias -> personas naming it, for the graph's LLM personas and the judge.

    A deterministic persona (`agent == "none"`) gets no key and mints nothing, so
    it contributes no alias. The judge is included even when no node names it,
    because it is always resolved and always mints a first-attempt key.
    """
    persona_names = {node.persona for node in graph.nodes}
    persona_names.add(JUDGE_PERSONA)
    named_by: dict[str, set[str]] = {}
    for name in persona_names:
        persona = registry.get(name)
        if persona is None or not persona.is_llm:
            continue
        for alias in (persona.model, persona.fallback):
            if alias:
                named_by.setdefault(alias, set()).add(name)
    return named_by


async def check_aliases(
    graph: WorkGraph, registry: Mapping[str, Persona], client: LiteLLMClient
) -> list[PreflightFinding]:
    """Run both preflight checks against a live proxy, returning every finding.

    The two reads are independent: a proxy that answers one endpoint but not
    the other gets a finding for the one it refused and a verdict for the one
    it answered, so the operator is told which is which rather than a single
    "preflight failed". A read failure is recorded with `transport=True` and the
    address tried, never a silent pass (FR-005).

    The caller owns the client and the registry — the CLI builds both from its
    host, the roadmap activity builds both from the worker host — so this
    function touches no environment and reads no files. Returns `[]` when every
    check passes.
    """
    findings: list[PreflightFinding] = []
    try:
        try:
            served = await client.list_model_ids()
        except LiteLLMError as exc:
            findings.append(
                PreflightFinding(
                    check="model-aliases-served",
                    passed=False,
                    transport=True,
                    detail=(
                        f"cannot read the model list from the proxy at "
                        f"{client.base_url}: {exc} — the aliases this epic names "
                        "cannot be confirmed served, so nothing was dispatched"
                    ),
                )
            )
        else:
            unserved = {
                alias: personas
                for alias, personas in aliases_to_check(graph, registry).items()
                if alias not in served
            }
            if unserved:
                _named = ", ".join(
                    f"`{alias}` ({' / '.join(sorted(personas))})"
                    for alias, personas in sorted(unserved.items())
                )
                findings.append(
                    PreflightFinding(
                        check="model-aliases-served",
                        passed=False,
                        detail=(
                            "the proxy does not serve every alias this registry "
                            f"names for the epic's personas: {_named}. Nothing "
                            "was dispatched."
                        ),
                    )
                )

        try:
            live = await client.list_key_aliases()
        except LiteLLMError as exc:
            findings.append(
                PreflightFinding(
                    check="first-attempt-key-aliases",
                    passed=False,
                    transport=True,
                    detail=(
                        f"cannot read the key list from the proxy at "
                        f"{client.base_url}: {exc} — a first-attempt alias "
                        "collision cannot be ruled out, so nothing was dispatched"
                    ),
                )
            )
        else:
            collisions = sorted(first_attempt_aliases(graph) & live)
            if collisions:
                findings.append(
                    PreflightFinding(
                        check="first-attempt-key-aliases",
                        passed=False,
                        detail=(
                            "a live key already holds an alias this epic's first "
                            "attempts will mint: "
                            + ", ".join(f"`{alias}`" for alias in collisions)
                            + ". Revoke that orphaned key (or let its TTL expire) "
                            "so the first attempt can mint it; nothing was "
                            "dispatched."
                        ),
                    )
                )
    finally:
        await client.aclose()

    return findings