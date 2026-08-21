---
state: ready
# FLIPPED draft -> ready 2026-08-20 1:44 PM CT at the operator's instruction,
# after he read the rendered page. What the pre-dispatch review did:
#
#   - ANCHORS: 53, all resolving against `origin/ergane-buildout` at 9274625 —
#     AND, separately, all 11 load-bearing ones asserted to land on the symbol
#     their prose names, which the resolver cannot check.
#   - EVERY CLAIM RUN, not read. `self._personas.get(DEBUGGER_PERSONA)` is None
#     against a real registry; `recovery_agent` degrades to `""`; the rung should
#     use ollama-cloud/deepseek-v4-flash and the node uses claude-opus-5. Bare
#     `VerificationConfig()` gives promotion_persona None; `_promotion_available`
#     returns False unconfigured and True configured; zero CLI flags on either
#     start command.
#   - TWO DEFECTS FOUND IN THIS SPEC AND FIXED. Five bare `:NN` refs whose
#     nearest antecedent was a different file (a reader hits the same wall), and
#     US3 sharing `factory/cli/nouns/build.py` with US2 while declaring no edge
#     between them — 068's exact collision, in a spec written hours after it.
#     US3 is now `depends_on_merged: [US1, US2]`.
#
# ANCHOR ROT WARNING, measured on this spec twice in one day. It was clean at
# 1:33 PM; 069/us1 merged at 9274625 and moved every one of its workflow.py
# anchors, and the resolver flagged only 2 of the 10 because the other 8 landed
# on real code in different functions. RE-VERIFY BEFORE DISPATCH if anything has
# landed since — `python3 .claude/skills/spec-html/render.py` against a fresh
# checkout of the landing branch is the cheap way to look.
#
# --- the draft note this supersedes ---
# Drafted 2026-08-20 1:05 PM CT by an operator session, from a live measurement
# rather than a review: the operator asked whether merge conflicts could be sent
# to a Fable persona, and the answer turned out to be no -- not because the seam
# is missing, but because it is already there and does nothing.
#
# Filed first as the SECOND OCCURRENCE of
# `interpreter/debugger-escalation-does-not-change-the-model` (critical, now at
# 2). The first occurrence was the ladder's debugger rung on 2026-08-12; this
# one is the merge-conflict recovery path, a different call site with the same
# root cause.
#
# DO NOT FLIP READY without a pre-dispatch review.
---

# Feature Specification: a stronger rung runs a stronger model

**Created**: 2026-08-20

## The gap, stated precisely

The ladder has three rungs above an ordinary attempt. Each one selects a
different persona. **None of them changes the model the agent runs.**

- The **debugger** rung, at `factory/workgraph/workflow.py:1608`:
  `DEBUGGER_PERSONA if action == NextAction.DEBUGGER else node.persona`.
- The **merge-conflict recovery** path, at `2653`:
  `persona = DEBUGGER_PERSONA` when the sync is not clean.
- The **promotion** rung that 070/US5 landed, at `factory/verify/ladder.py:173`.

All three set a persona name. That name reaches the virtual key's alias and the
`AttemptRecord` in history — and stops there. The attempt context still takes
`model_alias=resolved.model_alias` (`factory/workgraph/workflow.py:1380` for an ordinary attempt,
`factory/workgraph/workflow.py:2785` for
a recovery), and `resolved` is the `ResolvedNode` computed **once per node**,
before the attempt loop, at `factory/workgraph/workflow.py:712`.

So an escalated attempt re-runs the model that just failed, under a different
name. The most expensive rungs on the ladder are cosmetic.

### The code already does half of it

This is not a missing feature. `factory/workgraph/workflow.py:2753-2622` reads:

```python
recovery_persona_entry = self._personas.get(persona)
recovery_agent = recovery_persona_entry.agent if recovery_persona_entry is not None else ""
```

The recovery path **already re-resolves the persona** and takes its `agent` — the
field that decides gateway versus subscription routing — and passes it into the
attempt. It simply never takes `model_alias` from the same entry. One field is
re-resolved; the neighbouring one is not.

### And the lookup it uses is empty for exactly these personas

`self._personas` is built at `factory/workgraph/workflow.py:947`:

```python
self._personas = {item.node.persona: self._resolve_persona(item.node.persona) for item in resolved}
```

Keyed by the personas **nodes declare**. `DEBUGGER_PERSONA` is not one, unless a
story happens to declare it. So `self._personas.get(persona)` returns `None` on
every conflicted recovery, `recovery_agent` falls back to `""`, and even the half
that works does not work for the rung that needs it.

### Measured, on a live floor

2026-08-20 17:51:15Z. 068/us2's PR #246 was rejected `CONFLICT` on
`tests/test_interpreter.py` and entered recovery as attempt 2. `personas.yaml`
declares `debugger` as `ollama-cloud/deepseek-v4-flash`. The node is routed
`opus-closer`, which is `claude-opus-5`. **Nothing on the floor was running
deepseek.** The recovery ran the same model as the attempt that produced the
conflict.

### The third consumer, inert for a second reason

070/US5's promotion rung is reachable only when `config.promotion_persona` is
set (`factory/verify/ladder.py:173`). `VerificationConfig()` is constructed **bare** at
`factory/cli/roadmap.py:236` and `factory/cli/nouns/build.py:511`, and neither
`ergane build start` nor `ergane roadmap start` exposes a flag for it. So it is
always `None` and the rung never fires — a landed story that cannot be switched
on.

One root cause, three dead rungs.

## User Scenarios & Testing

### User Story 1 - The rung that changes the persona changes the model (Priority: P1)

As an operator, when the ladder escalates to a different persona, the agent runs
that persona's model — so a stronger rung is actually a stronger builder.

**Why this priority**: P1 and the whole of the defect. Without it the other two
stories describe machinery that still runs one model.

**Acceptance Scenarios**:

1. **Given** a node routed to persona A and a debugger rung routed to persona B
   with a different model, **When** the debugger attempt is built, **Then** its
   attempt context carries B's model alias, not A's — proven by a committed test.
2. **Given** the same node on an ordinary attempt, **When** the attempt is built,
   **Then** it carries A's model alias — proven by a committed test. This is the
   control for scenario 1: a change that returns B for every attempt passes
   scenario 1 and is wrong.
3. **Given** a landing rejected as a conflict, **When** the recovery attempt is
   built, **Then** it carries the conflict rung's persona and that persona's
   model alias — proven by a committed test.
4. **Given** a landing rejected and re-synced **cleanly**, **When** the recovery
   attempt is built, **Then** it carries the node's own persona and model —
   proven by a committed test. The clean and conflicted paths differ today
   (`factory/workgraph/workflow.py:2650` versus `:2653`) and must keep differing.
5. **Given** a rung whose persona is absent from the registry, **When** the
   attempt is built, **Then** the node fails naming the persona and the rung,
   rather than silently falling back to the node's model — proven by a committed
   test.
6. **Given** the diff, **When** the attempt context is inspected, **Then**
   `agent` and `model_alias` are taken from the **same** resolved persona entry —
   proven by the absence of any path that resolves one without the other.

### User Story 2 - The promotion rung can be switched on (Priority: P1)

As an operator, I can declare which persona a struggling node is promoted to, so
070/US5's rung stops being a landed no-op.

**Why this priority**: P1 and independent of US1 — the flag is worth having even
if the model resolution were already correct, because today the rung cannot fire
at all.

**Acceptance Scenarios**:

1. **Given** `ergane build start` with a promotion persona declared, **When** the
   epic starts, **Then** the workflow's `VerificationConfig` carries it — proven
   by a committed test that reads the start payload.
2. **Given** `ergane roadmap start` with the same flag, **Then** every child epic
   receives it — proven by a committed test.
3. **Given** no flag, **When** an epic starts, **Then** `promotion_persona` is
   `None` and the rung stays off — proven by a committed test. Today's behaviour
   must be the default.
4. **Given** a promotion persona naming a persona absent from the registry,
   **When** the command runs, **Then** it is refused **before** the epic starts,
   naming the persona — proven by a committed test.

### User Story 3 - An attempt says which persona and model it ran (Priority: P2)

As an operator, `ergane build status` tells me the persona and model of each
attempt, so a rung that silently runs the wrong model is visible the first time
rather than the eighth day.

**Why this priority**: P2, and it is the check that would have caught this. The
defect survived from 2026-08-12 to 2026-08-20 because nothing reported what an
attempt actually ran; both occurrences were found by reading a live process list.

**Acceptance Scenarios**:

1. **Given** a node with attempts on two different personas, **When**
   `ergane build status --json` is read, **Then** each attempt in its history
   carries the persona and model alias it ran — proven by a committed test.
2. **Given** the same, **When** the human-readable status is printed, **Then**
   the current attempt's persona and model appear — proven by a committed test.
3. **Given** an attempt whose persona could not be resolved, **When** status is
   read, **Then** the field says so rather than reporting the node's model —
   proven by a committed test.

## Requirements

- **FR-001**: An attempt's `model_alias` MUST be taken from the persona selected
  for **that attempt**, not from the node's resolution.
- **FR-002**: `agent` and `model_alias` for one attempt MUST come from a single
  resolved persona entry, so the two can never disagree about routing.
- **FR-003**: The persona snapshot MUST contain every persona any rung may
  select — the node personas, the debugger persona, and the configured promotion
  persona — resolved once at epic start.
- **FR-004**: Resolving a rung's persona MUST NOT read the persona registry from
  workflow code, and MUST NOT re-read it mid-epic; an operator editing
  `personas.yaml` MUST still change only the next epic.
- **FR-005**: A rung naming a persona absent from the snapshot MUST fail the node
  naming the persona and the rung, never silently fall back.
- **FR-006**: The clean-sync recovery path MUST keep using the node's own
  persona, and the conflicted path MUST use the conflict rung's.
- **FR-007**: `ergane build start` MUST accept a promotion persona and pass it
  through to `VerificationConfig`.
- **FR-008**: `ergane roadmap start` MUST accept the same and pass it to every
  child epic.
- **FR-009**: Both commands MUST refuse a promotion persona absent from the
  registry before starting anything.
- **FR-010**: Omitting the flag MUST leave `promotion_persona` `None`.
- **FR-011**: Each `AttemptRecord` MUST carry the persona and the model alias the
  attempt ran under.
- **FR-012**: `ergane build status`, in both JSON and human-readable form, MUST
  report them.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  implements: [FR-007, FR-008, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-011, FR-012]
```

## Success Criteria

- **SC-001**: Drive a debugger rung against a persona with a different model and
  paste the attempt's resolved model alias. It must be the rung's.
- **SC-002**: Drive an ordinary attempt on the same node and paste its model
  alias. It must be the node's. Without this control SC-001 is satisfied by a
  change that always returns the rung's model.
- **SC-003**: Drive a conflicted recovery and paste the persona and model. Then
  drive a clean re-sync and paste both again. They must differ.
- **SC-004**: Start an epic with a promotion persona declared and paste the start
  payload's `VerificationConfig`. Then start one without and paste it again.
- **SC-005**: Paste `ergane build status --json` for a node with attempts on two
  personas, showing the per-attempt persona and model.

## Assumptions

- The promotion persona is an epic-level dial, not a per-story one. 070/US1
  already gives per-story routing via the `persona:` key; this is the rung a node
  falls **to**, which is a property of the run.
- `PROMOTION_PERSONA = "__promotion__"` (`factory/verify/ladder.py:71`) stays the synthetic
  placeholder for the unconfigured case and is never resolved as a real persona.
- The virtual key's alias already carries the persona (D-026), so ledger
  attribution is already correct — only the model is wrong. This spec does not
  change key issuance.
- `_attempts_spent` already excludes the promotion persona (`factory/verify/ladder.py:141`), so
  the attempt accounting needs no change when the rung starts firing.
