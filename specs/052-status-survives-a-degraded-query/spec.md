---
state: ready
# Drafted 2026-08-16 ~10:05 PM CT from a critical finding the operator session
# filed against itself the same evening:
# `status/the-query-guard-catches-rpcerror-but-temporal-raises-workflowqueryfailederror`.
#
# Not reasoned into existence. Found by running the shipped wheel against this
# repository's own live control plane, then re-running from the source checkout
# to rule out packaging. Both fail identically. `ergane status` -- the verb
# `CLAUDE.md` names as the answer to "what is one epic doing right now" -- cannot
# start, on a fully green suite.
#
# Drafted `ready` rather than `draft` at the operator's instruction, because it
# blocks something else he has already decided: the factory is switching back
# from operator-driven dispatch to real `ergane build start` runs, and this is
# the verb for watching one. Switching to a loop nobody can observe is how a bad
# run goes unnoticed for hours.
#
# Numbered 052: 050 init preconditions, 051 first-run defaults.
---

# Feature Specification: `status` survives a query the workflow refuses

**Created**: 2026-08-16

## The defect, measured

```
$ ergane status specs
ergane: unexpected error (RoadmapStatus.__init__() missing 1 required
positional argument: 'max_concurrent_nodes'); re-run with --debug
[exit 1]
```

Identical from the installed wheel and from the source checkout, so this is not
a packaging fault. The full suite is green.

## The error message is a red herring, and that matters for the fix

`RoadmapStatus` is not the bug. `factory/cli/status.py:432` queries the live
roadmap workflow, and the query **fails inside the worker** because a running
workflow's state predates the `max_concurrent_nodes` field
(`factory/roadmap/workflow.py:366`, declared with no default while its
neighbour `paused` at `:269` has one).

The author anticipated exactly this. One line below the query, at `:435`:

```python
    except RPCError:
        # The run exists but will not answer: the disposition is still real,
```

That is the correct fallback for precisely this situation, written in advance.
**It never fires:**

```
WorkflowQueryFailedError.__mro__ = [WorkflowQueryFailedError, TemporalError,
                                    Exception, BaseException, object]
issubclass(WorkflowQueryFailedError, RPCError)  ->  False
```

`RPCError` is a **transport** failure — the server did not answer. A query the
server accepts and the workflow then rejects is a different event, so the guard
misses it, the exception escapes to the top-level handler, and the whole command
dies for a degradation it was built to survive.

Three sites in that file make the same bet: `:239`, `:435`, `:474`. Only `:435`
is proven dead; the other two are the same wrong type against the same client.

## Why two repairs, and why neither alone is enough

Giving `max_concurrent_nodes` a default would make *this* query answer, and hide
the fact that the guard is dead. The guard is what protects against the **next**
field — and there will be one, because records that cross the Temporal boundary
keep gaining fields (045's trap 5, restated as 049 FR-010).

Fixing only the guard leaves the query still failing, which is correct behaviour
but a worse report than the operator can have.

## User Scenarios & Testing

### User Story 1 - A query the workflow refuses degrades instead of killing the command (Priority: P1)

As an operator, `ergane status` reports what it can when the roadmap workflow
refuses a query, rather than exiting 1 with "unexpected error".

**Why this priority**: it is the whole defect, and the verb is the one the
operator uses to watch a running epic.

**Independent Test**: make the query raise `WorkflowQueryFailedError` — the type
the client actually raises — and confirm `ergane status` completes, exits 0, and
says the roadmap disposition is unavailable and why.

**Acceptance Scenarios**:

1. **Given** a roadmap query that raises `WorkflowQueryFailedError`, **When**
   `ergane status` runs, **Then** it completes and exits 0, reporting the
   roadmap section as unavailable with the refusal's own message — proven by a
   committed test that raises **the type `temporalio` raises**, not a
   hand-rolled stand-in that inherits from whatever the catch names.
2. **Given** a roadmap query that raises `RPCError`, **When** `ergane status`
   runs, **Then** its behaviour is byte-identical to today's — proven by a
   committed test. This repair may not change the transport path.
3. **Given** the diff, **When** `factory/cli/status.py` is read, **Then** every
   site that guards a Temporal call states which class of failure it defends
   against, and no site catches a type the client cannot raise — proven by a
   committed test asserting the guarded types by name.
4. **Given** a query that raises neither, **When** `ergane status` runs, **Then**
   the exception still escapes — a bare `except Exception` around a query
   silently converts a real defect into a blank section, and this story must not
   introduce one.

---

### User Story 2 - A record that crosses the Temporal boundary can be read from an older history (Priority: P2)

As a workflow, my query answer can be reconstructed from a history recorded
before a field was added, because every field that crosses that boundary has a
default.

**Why this priority**: P2 because US1 alone restores the verb. This is what stops
the next field doing the same thing.

**Independent Test**: reconstruct `RoadmapStatus` from a payload missing
`max_concurrent_nodes` and confirm it succeeds with a documented default.

**Acceptance Scenarios**:

1. **Given** a payload with no `max_concurrent_nodes`, **When** `RoadmapStatus`
   is reconstructed, **Then** it succeeds and the field takes a documented
   default — proven by a committed test.
2. **Given** the records this repository sends across the Temporal boundary,
   **When** they are swept, **Then** every field either has a default or is
   named in an explicit allowlist of fields that must be present — proven by a
   committed sweep with an anti-vacuity assertion that the record list it read
   is non-empty and contains `RoadmapStatus` by name.

## Functional Requirements

- **FR-001**: `ergane status` MUST complete and exit 0 when a Temporal query is
  refused by the workflow.
- **FR-002**: The refusal MUST be reported in the section it belongs to, naming
  the cause, rather than replacing the whole report.
- **FR-003**: Each guarded Temporal call site MUST catch the classes the client
  actually raises, and MUST NOT catch a class the client cannot raise.
- **FR-004**: This spec MUST NOT introduce a bare `except Exception` around a
  Temporal call.
- **FR-005**: Behaviour on `RPCError` MUST be unchanged.
- **FR-006**: Every field of a record that crosses the Temporal payload boundary
  MUST have a default, or be named in an explicit allowlist.
- **FR-007**: A sweep MUST hold FR-006, with an anti-vacuity assertion that the
  record list it read is non-empty and names `RoadmapStatus`.

## Success Criteria

- **SC-001**: `ergane status specs` exits 0 against this repository's own live
  control plane, whose roadmap workflow currently refuses the query. Evidence is
  a committed transcript, because this is a claim about a running deployment.
- **SC-002**: The count of Temporal call sites catching `RPCError` alone is zero,
  asserted by a test rather than by reading.
- **SC-003**: No test raises a stand-in exception where the real client's type is
  available.

## Out of Scope

- **Why the running roadmap workflow predates the field.** It is a real history
  on a real namespace and this spec makes the reader survive it; migrating or
  terminating that workflow is an operator act, not interpreter behaviour.
- **The paused roadmap schedule.** Separate, deliberate, and the operator's.
- **Every other command's guards.** This spec fixes `factory/cli/status.py`.
  Whether the same wrong-type bet exists elsewhere is worth knowing and is not
  this story's scope; US1-S3's test makes the next one visible in this file.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  implements: [FR-006, FR-007]
```

The two stories touch different modules and neither needs the other to exist.
US1 restores the verb; US2 stops the next field breaking it again.
