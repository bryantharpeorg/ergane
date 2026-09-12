---
state: ready
depends_on_landed:
  - 009-roadmap-scheduler
  - 021-roadmap-operability
  - 169-the-unpark-test-observes-its-held-child-before-it-wakes-the-roadmap
---

# Feature Specification: a roadmap query keeps its last complete reading

**Created**: 2026-09-12

## Provenance and failure boundary

The exact `ergane-buildout` candidate at `ed67af7ec6c8` failed the full release
gate in
`tests/test_roadmap_operator_surface.py::test_pause_roadmap_parks_dispatch_between_epics`.
One run queried the continued execution after the paused child had completed but
before the new run's first corpus-read activity returned.  The query answered
with `specs=[]`, so an operator-visible complete corpus momentarily became a
roadmap that knew about nothing.

An isolated 30-run replay produced one additional query-deadline failure.  More
importantly, a deterministic negative control replaced only the second
`read_corpus_activity` with a held activity.  While that read was held, the
continued run answered exactly:

```text
{'reads': 2, 'paused': True, 'running': [], 'spec_count': 0, 'specs': []}
```

Releasing the read restored both specs and allowed the run to finish.  The
failure is therefore a real query-continuity defect at the continue-as-new
boundary, not permission to weaken the test, lengthen a timeout, suppress
continue-as-new, or reuse a stale corpus for dispatch.

## User Scenarios & Testing

### User Story 1 - The status read remains truthful while a continued run initializes (Priority: P1)

As the operator, I want `roadmap_status` to preserve the last complete recorded
roadmap reading across a quiescent continue-as-new boundary, so dashboards and
CLI reads do not transiently report zero work while the new run re-reads the
corpus.

**Independent Test**: Under the real Temporal test server, run a two-spec
roadmap with the first child held, pause it, release that child, and
deterministically hold only the continued run's first corpus-read activity.
Query during that hold.  The response must contain both prior spec rows, show
the first as landed, the second as dispatchable, preserve `paused=True`, report
no running child, and expose the current bounds and parked controls.  Release
the read, resume the roadmap and prove the second child lands.  Repeat the
original operator-surface test without sleeps or a larger timeout.

**Acceptance Scenarios**:

1. **Given** a roadmap has a complete two-spec reading and its only child
   concludes while the roadmap is paused, **When** the workflow continues as
   new and the new run's first corpus read is still pending, **Then**
   `roadmap_status` returns the last complete two-spec reading rather than an
   empty `specs` list.
2. **Given** that quiescent boundary, **When** the carried status is queried,
   **Then** it reports the concluded spec landed, the waiting spec still
   present, `running=[]`, the carried bounds, the current pause flag, and the
   current parked findings.
3. **Given** a pause, resume, promote or unpark signal arrives after the new run
   restores its carry-over but before the first read completes, **When** status
   is queried, **Then** live operator controls override the carried snapshot;
   the snapshot cannot resurrect a park, lose a promotion, or report the old
   pause/bound values.
4. **Given** the first new-run corpus read completes, **When** status is queried
   again, **Then** the freshly read and freshly derived corpus replaces the
   carried reading for both status and dispatch decisions.
5. **Given** a truly fresh first run with no prior complete reading, **When** it
   is queried before its first corpus read, **Then** existing initialization
   behavior remains wire-compatible and no fabricated spec row is emitted.
6. **Given** an older history whose `RoadmapCarryOver` payload predates this
   repair, **When** the upgraded worker decodes and continues it, **Then** the
   new field's default preserves replay and payload compatibility.
7. **Given** the complete repair, **When** its diff is inspected, **Then** it
   changes no scheduling order, capacity calculation, idle cadence,
   continue-as-new boundary, child policy, service, agent route, model, timeout,
   or external side effect.

## Functional Requirements

- **FR-001**: A continued run MUST retain an optional, deterministic,
  serializable snapshot of the last complete `RoadmapStatus` solely for queries
  before its first fresh corpus read completes.
- **FR-002**: The snapshot MUST be captured at the quiescent
  continue-as-new boundary and MUST contain no child marked running.
- **FR-003**: While initialization is pending, `roadmap_status` MUST return the
  carried complete spec rows instead of `specs=[]` and MUST overlay the current
  pause flag, bounds, promotions and parked map.
- **FR-004**: The carried snapshot MUST NOT participate in readiness,
  derivation, drift, landing, capacity or dispatch decisions; the first fresh
  read remains authoritative for every action.
- **FR-005**: After the fresh read returns, every query MUST use the new corpus
  and derived readings; the carried snapshot MUST no longer be observable.
- **FR-006**: The carry-over addition MUST default to `None` so payloads recorded
  by older workers continue to decode, and temporal payload-shape tests MUST
  cover both old and new shapes.
- **FR-007**: The query fallback MUST reflect live signals restored or received
  in the new run and MUST NOT reintroduce a removed park or stale pause value.
- **FR-008**: A deterministic regression MUST hold the continued run's corpus
  read and assert the complete interim status.  Sleeps, timeout increases,
  assertion weakening and probabilistic-only loops are forbidden as the
  primary proof.
- **FR-009**: The original pause/operator-surface tests, roadmap durability
  tests, query payload tests and full roadmap test surface MUST pass unchanged
  in meaning.
- **FR-010**: The implementation MUST NOT change live services, worker
  deployment, agents, Ollama, routing, credentials, registry state or
  publication state.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010]
```

## Assumptions

- Continue-as-new still occurs only at quiescence, so the last complete status
  is a bounded query snapshot with no live child handle to preserve.
- A status snapshot is evidence for a read, not an input to a scheduling
  decision.  The fresh corpus read remains mandatory even when the snapshot is
  available.
- The isolated query-deadline failure may remain an SDK test-server concern;
  this story owns the independently proven empty-status defect and must not
  claim that unrelated transport failures are repaired without evidence.
