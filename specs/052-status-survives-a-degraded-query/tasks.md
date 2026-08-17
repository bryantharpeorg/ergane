# Tasks: 052-status-survives-a-degraded-query

Two stories, **independent** — neither `depends_on` nor `depends_on_merged`
connects them. The phases below are in reading order only.

Work test-first and commit once per task. Read `plan.md` before the first
commit — trap 2 (raise the type the client raises) is the one that ships a green
suite over an unfixed defect.

## Phase 1: User Story 1 — A refused query degrades instead of killing the command

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1) Write the degradation case FIRST: a roadmap query
      raising `WorkflowQueryFailedError` — **imported from `temporalio.client`,
      never a local subclass of `RPCError`** (plan trap 2) — leaves `ergane
      status` completing at exit 0 with the roadmap section reported unavailable
      and the refusal's own message shown. Must fail.
- [ ] T002 [P] [US1] (spec US1-S2) Write the transport-path case FIRST: an
      `RPCError` produces byte-identical behaviour to today's. Must fail only if
      the repair changes it — write it, watch it pass, and say so.
- [ ] T003 [P] [US1] (spec US1-S3) Write the guarded-types case FIRST: assert by
      name which exception classes each Temporal call site in
      `factory/cli/status.py` guards, and that none is a class the client cannot
      raise. Must fail.
- [ ] T004 [P] [US1] (spec US1-S4, FR-004) Write the no-bare-catch case FIRST:
      no `except Exception` guards a Temporal call in this file. Must fail if one
      is introduced; write it before the implementation so it cannot be.

### Implementation for this story

- [ ] T005 [US1] Catch what the client raises at `factory/cli/status.py:435`,
      and decide deliberately for `:239` and `:474` — a transport failure and a
      workflow-side refusal are different events and `status` may want to say
      different things about them. Whatever you choose, T003 pins it.
- [ ] T006 [US1] Commit the SC-001 transcript: `ergane status specs` against the
      live control plane, exit code captured with `rc=$?` **before** any pipe
      (plan trap 7).

## Phase 2: User Story 2 — An older history can still be read

### Tests for this story (write FIRST, must fail)

- [ ] T007 [US2] (spec US2-S1) Write the older-payload case FIRST:
      `RoadmapStatus` reconstructs from a payload with no
      `max_concurrent_nodes`, taking a documented default. Must fail.
- [ ] T008 [P] [US2] (spec US2-S2, FR-007) Write the sweep FIRST: every field of
      every record crossing the Temporal payload boundary has a default or is
      allowlisted, with an anti-vacuity assertion that the record list read is
      non-empty and names `RoadmapStatus` (plan trap 4). Must fail.

### Implementation for this story

- [ ] T009 [US2] Give `factory/roadmap/workflow.py:366` a default, matching the
      shape `paused: bool = False` already uses at `:269`, and document why in
      the class docstring rather than only in the diff.

## Verification

- [ ] T010 Full suite, verbatim, with the cache state it was run in. Baseline
      skips are 44; a new skip is a hidden test and must be declared.
- [ ] T011 Mutation battery with a point-at-nothing control as its **first** row,
      `__pycache__` purged between mutants (plan trap 8), tree asserted clean —
      tracked and untracked — before and after.
- [ ] T012 Diff measured through `size_refusal` from
      `factory/verify/diffbounds.py`, with the number quoted.
