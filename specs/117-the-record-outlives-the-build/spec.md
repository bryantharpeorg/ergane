---
state: ready
fixes:
  - verify/a-re-dispatch-silently-overwrites-the-previous-dispatchs-verification-evidence
  - verify/build-history-is-not-durable-so-nothing-downstream-can-remember-a-build
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# A new number: none of the 089-102 slots reserved on 2026-08-23 names this.
#
# THE DEFECT IS FOUR WORDS IN A SCHEMA. `verification_results` is keyed
# `UNIQUE (epic_id, node_id, attempt, form)` (`factory/verify/store.py`) and
# written through an upsert that replaces every non-key column
# (`:512-521`). The key has no dispatch in it. So a re-dispatch starts again at
# attempt 1 and overwrites the previous run's row for every attempt number it
# reaches.
#
# THE UPSERT IS THERE FOR A GOOD REASON, AND THAT IS WHY THIS IS SUBTLE. Temporal
# delivers at least once, so a duplicate `record_verification` must land on the
# first run's row rather than adding a second — the comment at `:510-511` says
# exactly that, and `upsert_result`'s docstring (`:526`) promises the row id is
# "stable across reruns". Both statements are correct about a *retry*. Neither is
# true of a *re-dispatch*, and nothing in the schema can tell the two apart.
#
# MEASURED. One node was dispatched three times, spending nine attempts and then
# six. Only attempts 7-9 of the second dispatch survive. The destroyed rows were
# the evidence for this run's single most useful finding — that an agent given
# *no* guidance solved a problem in three attempts while an agent given
# half-correct guidance never solved it in nine — and it could be written down at
# all only because a human was watching live.
#
# THREE CONSEQUENCES WORTH SEPARATING. (1) Forensics: a post-mortem of a killed
# dispatch is impossible once the next one runs, and the kill is the moment the
# evidence matters most. (2) Metrics are quietly wrong: the highest attempt
# number is not the attempts actually spent, so every rework figure over a
# re-dispatched repository is understated with no way to detect it from the data.
# (3) Rows read out of chronological order, because surviving rows keep their
# original ids.
#
# THE DISCRIMINATOR MUST BE THE DISPATCH, NOT THE CONTENT. `criteria_sha256`
# cannot serve: it was identical across all nine rows, being snapshotted from an
# unchanged spec. A retried activity carries the same workflow run id, so keying
# on the run preserves at-least-once idempotence exactly — which is the property
# the upsert exists to protect.
#
# AND THE ROW CANNOT SAY WHO BUILT IT. `VerificationResult` carries eighteen
# columns and not one is the persona or the model. The only authority is the
# epic's Temporal start payload, which expires with the workflow, and the
# on-disk `workgraph.json` lies for anything the roadmap dispatched because the
# roadmap derives in-process and never writes it back. So "which model built this
# story, and did the debugger rung change it" is unanswerable thirty days later.
# That is US2, and it is also the fix for a known reporting defect: the DEBUGGER
# rung relabels the persona but never re-resolves `model_alias`, so the rung and
# the model disagree and only the payload shows it.
#
# NOT IN SCOPE. Operator-settable retention — the second half of the platform
# request behind this spec — is deliberately deferred: it is a policy surface,
# it needs a sweeper, and it is worthless until the rows it would retain stop
# being overwritten. This spec does not change what Temporal keeps, does not add
# a reader beyond distinguishing dispatches, and does not touch the usage ledger.
---

# Feature Specification: the record outlives the build

**Created**: 2026-08-28
**Depends on**: nothing outside this spec.

## The gap, stated precisely

The factory can say what landed forever, and how it was built for about three
days — less if anything was re-dispatched. Four candidates could carry the
history and none does:

| Candidate | Why it cannot carry it |
| --- | --- |
| `verification_results` | upserts on `(epic_id, node_id, attempt, form)`, so a re-dispatch overwrites prior evidence |
| Temporal | gone past the retention window |
| the usage ledger | durable, but rows are not dispatch-scoped |
| the forge | durable and truthful, but only for landings — attempts, verdicts and rework are invisible to it |

And the row that does exist cannot name the persona, the model or the route that
produced it.

## The rule this spec is asking for

**A re-dispatch adds to a node's history rather than replacing it, and every
attempt row says who built it.**

### What this spec is not

It is not a removal of the upsert. At-least-once delivery means a retried
activity must still land on the row it wrote the first time. Adding the dispatch
to the key preserves that exactly, because a retry carries the same dispatch
identity.

It is not a retention policy. Deferred deliberately: retaining rows that are
still being overwritten is not worth building.

It is not a new reader. US3 makes the existing reader able to tell two dispatches
apart; it does not add a query surface.

## User Scenarios & Testing

### User Story 1 - A re-dispatch adds to the history (Priority: P1)

As an operator, the evidence from a killed dispatch survives the next one, so a
post-mortem is possible at the moment it matters most.

**Why this priority**: P1 and it depends on nothing. Every other story here is
decoration if the record is gone by morning.

**Acceptance Scenarios**:

1. **Given** a node dispatched once and recorded through attempt three, **When**
   the same node is dispatched again and records its own attempt one, **Then**
   both dispatches' attempt-one rows exist and are distinguishable — proven by a
   committed test.
2. **Given** an activity that records the same attempt twice within one
   dispatch, **When** the second recording runs, **Then** it updates the first
   row rather than adding another — proven by a committed test. At-least-once
   idempotence is the property the upsert exists for and it must not regress.
3. **Given** a store written before this change, **When** it is opened, **Then**
   it migrates in place, its existing rows remain readable, and its column order
   matches a freshly created store — proven by a committed test.
4. **Given** a migrated store, **When** its pre-existing rows are read, **Then**
   each carries a dispatch value that does not collide with a new dispatch —
   proven by a committed test. Rows written before dispatches were distinguished
   belong to one unnamed dispatch, and must not merge with the next one.

### User Story 2 - The row says who built it (Priority: P1)

As an operator, I can ask which model and persona built a story thirty days
later, from the store alone, with no Temporal query.

**Why this priority**: P1. The only current authority expires with the workflow,
and the on-disk graph lies for anything the roadmap dispatched.

**Acceptance Scenarios**:

1. **Given** an attempt run by a persona through the gateway, **When** its row is
   written, **Then** the row carries the persona, the model alias and the route —
   proven by a committed test.
2. **Given** an attempt run through the subscription route, **When** its row is
   written, **Then** the route is recorded as the subscription rather than left
   null — proven by a committed test.
3. **Given** a debugger-rung attempt, **When** its row is written, **Then** the
   model alias recorded is the one that actually ran — proven by a committed
   test. The rung relabels the persona; the row must not inherit a stale alias.
4. **Given** a store written before this change, **When** its old rows are read,
   **Then** the new columns read as unknown rather than as a wrong value —
   proven by a committed test.

### User Story 3 - A reader can tell two dispatches apart (Priority: P2)

As an operator, "this story was built twice" is something I can see rather than
something I have to have witnessed.

**Why this priority**: P2. US1 preserves the rows; this makes them legible.

**Acceptance Scenarios**:

1. **Given** a node with two dispatches recorded, **When** its history is read,
   **Then** the attempts are grouped by dispatch and ordered oldest first within
   each — proven by a committed test.
2. **Given** the same node, **When** the operator reads it through the CLI,
   **Then** the number of dispatches is stated — proven by a committed test.
3. **Given** a node with one dispatch, **When** its history is read, **Then** the
   output is shaped as it is today — proven by a committed test.
4. **Given** two dispatches whose rows share attempt numbers, **When** the
   history is read, **Then** rows are ordered by when they were written rather
   than by row id — proven by a committed test. Surviving rows keep their
   original ids, which is why id order is not chronological order.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

All three change `factory/verify/store.py` — US1 the key and the migration, US2
three columns and the same migration path, US3 the reader — so they are
serialised on file ownership rather than on logic. US1 precedes the others
because both build on the migration it establishes.

## Requirements

- **FR-001**: A node's attempt rows MUST be keyed such that a second dispatch
  adds rows rather than replacing the first dispatch's.
- **FR-002**: A repeated recording of the same attempt within one dispatch MUST
  continue to update the existing row.
- **FR-003**: An existing store MUST migrate in place, preserving its rows and
  producing the same column order as a freshly created store.
- **FR-004**: Rows written before dispatches were distinguished MUST carry a
  dispatch value that cannot collide with a later dispatch.
- **FR-005**: An attempt row MUST carry the persona, the model alias and the
  route that produced it.
- **FR-006**: A debugger-rung attempt MUST record the model alias that actually
  ran.
- **FR-007**: Rows predating the new columns MUST read as unknown, never as a
  wrong value.
- **FR-008**: A node's history MUST be readable grouped by dispatch and ordered
  by when each row was written.
- **FR-009**: A node with a single dispatch MUST read exactly as it does today.
- **FR-010**: Every story MUST leave the usage ledger and Temporal's retention
  unchanged.

## Success Criteria (summary)

- After a `build reset` and a re-dispatch of the same spec, both dispatches'
  attempts are readable, distinguishable and ordered.
- "Which model built this story, and did the debugger rung change it" is
  answerable from the store alone, thirty days later.
- A rework figure computed over a re-dispatched repository counts the attempts
  actually spent.
