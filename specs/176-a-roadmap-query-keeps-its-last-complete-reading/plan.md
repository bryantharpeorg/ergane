# Implementation Plan: a roadmap query keeps its last complete reading

Refined 2026-09-12 against `ergane-buildout` at `ed67af7ec6c8`.  Resolve
citations by symbol if prior landings move line numbers.

## Current mechanism

- `factory/roadmap/workflow.py:370` — `RoadmapCarryOver` preserves landed and
  parked maps, promotions, pause, bounds and idle cadence, but carries no
  complete query reading.
- `factory/roadmap/workflow.py:475` — `RoadmapStatus` is the typed query and run
  result.  Its compatibility note explicitly says `specs`, `running` and
  `parked` have no defaults because an empty value would falsely report a
  roadmap that knows about nothing.
- `factory/roadmap/workflow.py:731` — `roadmap_status` nevertheless returns
  `specs=[]`, `running=[]` and `parked=[]` whenever `_roadmap is None`.
- `factory/roadmap/workflow.py:889` — the continued run restores carry-over
  synchronously, then awaits `read_corpus_activity` at line 905.  A query can
  execute while that activity is pending and observes `_roadmap is None`.
- `factory/roadmap/workflow.py:999` — after the last child concludes, the run
  continues as new at quiescence even while paused.  This ordering is correct
  and remains unchanged.
- `factory/roadmap/workflow.py:1065` — `_continue_as_new` constructs the
  carry-over from live state immediately before the boundary; this is the
  point that can capture the complete query result.
- `tests/test_roadmap_operator_surface.py:85` — the release-gate failure queries
  after releasing the paused child and requires both spec rows to remain
  visible.
- `tests/test_temporal_payload_shape.py` — this is the binding coverage for
  defaulted additions to Temporal dataclasses.

## Proven failure mechanism

The release candidate produced two observations:

1. The exact full gate returned
   `RoadmapStatus(specs=[], running=[], parked=[], ..., paused=True)` after the
   paused child landed, causing `_status_of(..., "001-alpha")` to fail.
2. A deterministic harness wrapped `read_corpus_activity`, allowed the first
   call to complete, paused and released the child, then blocked call two.  The
   query on the continued execution returned zero specs while paused.  Releasing
   call two restored both rows and the roadmap completed normally.

That negative control removes filesystem timing and polling luck: the new run
has restored its controls but has no `_roadmap` until the activity answer is
recorded.  Returning the hard-coded empty status is the exact false reading.

## Intended design

1. Extend `RoadmapCarryOver` with one optional, defaulted previous-status field
   (or an equivalently typed immutable query snapshot).  Preserve decode
   compatibility with histories that omit it.
2. At `_continue_as_new`, capture `roadmap_status()` after child reaping and
   before crossing the boundary.  Assert through tests that this snapshot is
   quiescent and deterministic.
3. Restore the optional snapshot before the new run's first await.  While
   `_roadmap is None`, return a fresh status value derived from the snapshot,
   overlaid with live `_paused`, bounds, `_parked` and `_promotions` state.
4. Do not assign the snapshot to `_roadmap`, `_computed_landed` or `_drift`.
   The existing read/derive path remains the only scheduling authority.
5. Once `read_corpus_activity` returns and `_roadmap` is populated, use the
   existing normal query path without consulting the snapshot.
6. Add the deterministic held-second-read test.  Retain the original operator
   test assertions and timeouts, and add old-payload decoding coverage.

The exact field arrangement is implementation-owned.  If dataclass declaration
order makes a `RoadmapStatus` field awkward, a small frozen snapshot record is
acceptable only if it preserves every query fact required above and remains
the sole new payload.  Do not carry spec document text or a dispatchable
`Roadmap` merely to make the query work.

## Traps

1. **Do not fix this only in the test.** Polling past `specs=[]` would hide an
   operator-visible false reading and contradict `RoadmapStatus`'s own contract.
2. **Do not dispatch from the snapshot.** It is last-observed status during one
   initialization gap.  The corpus may have changed between runs and must be
   re-read before action.
3. **Signals remain live.** A carried `paused=True` cannot override a resume
   received by the new run; a carried park cannot reappear after `unpark_spec`.
   Apply current control maps at query time rather than returning the snapshot
   object verbatim.
4. **Preserve old histories.** Every new Temporal dataclass field needs a
   default and explicit old-shape decoding coverage.  Do not rename or remove
   an existing field.
5. **No timeout medicine.** The deterministic counterexample is independent of
   the 30-second test bound.  Longer deadlines and sleeps do not repair it.
6. **Keep continue-as-new.** Moving or suppressing the quiescent boundary would
   trade a false query for unbounded history and violate D-031.
7. **Keep the snapshot bounded and clean.** It may contain typed status rows and
   parked refusal text already exposed by the query; it may not add spec bodies,
   credentials, provider responses, logs or private evidence.

## Verification

1. Red: deterministically hold the second corpus read and assert the current
   `specs=[]` response, then encode the desired complete response as the failing
   regression.
2. Green: implement the query-only snapshot and prove the held-read response
   includes both rows, correct landing/readiness facts, live controls and no
   running child.
3. Negative controls: release the read and prove the fresh corpus replaces the
   snapshot; mutate the corpus between runs and prove dispatch follows the new
   read; exercise pause/resume and unpark during the held window.
4. Compatibility: decode a carry-over payload without the new field, round-trip
   a payload with it, and run `tests/test_temporal_payload_shape.py`.
5. Regression: run the exact operator-surface test repeatedly without changed
   timeouts, then the roadmap scheduler/durability/operator/query suites and the
   repository's declared gates.

## Scope

One workflow model/query implementation and focused roadmap/payload tests.  No
CLI redesign, dashboard change, scheduler-order change, service operation,
agent/model/routing change, registry action or release version change.
