# Tasks: A pass failure is a fact told once, not a choice asked forever

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      hosts the work, and record the answers here. Five things, because each is
      load-bearing: that both reporters still key the store by
      `workflow.info().workflow_id` (`factory/roadmap/workflow.py:893`, `:934` —
      if something already re-keyed them, US1 shrinks); that
      `_should_notify_failure` is still linear multiples-of-three (`:142-150`);
      that `record_roadmap_failure` still inserts a pending escalation row with
      RETRY/KILL choices (`factory/activities/notify_activities.py:541-552` —
      US2's whole deletion target); that one real scheduled execution from the
      2026-08-09 06:00Z–12:05Z incident, read in the Temporal UI on `:8233`,
      carries a workflow id with the scheduled time appended — the assumption
      US1's key fix turns on; and that `manual_intervention_notice`
      (`factory/notify/messages.py:216`) still renders no keyboard, because it
      is the shape US2 copies.

      **Verified 2026-08-11 at 9594787+ (operator preflight, pre-dispatch):**
      all five hold. (1) Both reporters key by `workflow.info().workflow_id` —
      confirmed at `workflow.py:893` and `:934`. (2) `_should_notify_failure`
      is `count == 1 or count % 3 == 0` (linear multiples of three) at
      `:142-150`. (3) `record_roadmap_failure` still builds an
      `_EscalationRecord` with `choices=[RETRY, KILL]` — the deletion target
      is live. (4) The schedule's id churn is proven against production
      history: `temporal workflow list` shows the 2026-08-09 incident's
      executions as `roadmap-specs-2026-08-09T12:00:00Z`,
      `…T11:45:00Z`, `…T11:30:00Z` — one suffixed id per scheduled action,
      all Failed. (5) `manual_intervention_notice` renders no keyboard; its
      docstring states "FR-007's escalation stays the only message shape with
      a keyboard".

---

## Phase 2: User Story 1 — The failure count survives the schedule's identity churn (Priority: P1) 🎯 MVP

**Goal**: consecutive identical failures arriving as separate scheduled
executions accumulate one count keyed by the corpus, page at counts 1, 3, 9,
27, …, and reset with one recovery page on the next green pass.

**Independent Test**: consecutive failing executions under distinct
schedule-shaped workflow ids over one specs root produce one accumulating
count, pages only at geometric thresholds, and a recovery page from a green run
under yet another fresh id.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green; plan.md's inventory claims hold (`_report_run_failure` keys by
      `workflow.info().workflow_id`, `_should_notify_failure` is linear) —
      constitution II gate; STOP and report blocked if not satisfied.
- [ ] T003 [US1] Extend the harness in
      `tests/test_roadmap_failure_notifications.py` with a workflow-id override
      (plan.md trap 2 — the landed loop restarts under one id, which is exactly
      what a schedule never does), then write the churn case FIRST: three
      failing executions under three distinct schedule-shaped ids
      (`roadmap-<name>-<timestamp>`) over one specs root accumulate a single
      count to 3, page at counts 1 and 3 only, and the count-3 page names the
      count (spec US1-S1) — must fail.
- [ ] T004 [US1] Write the recovery-under-a-fresh-id case FIRST, in the same
      file: after failures under distinct ids, a green run under yet another
      distinct id pages exactly once naming the prior count, and the count
      resets (spec US1-S2) — must fail.
- [ ] T005 [US1] Write the geometric-bound case FIRST: nine consecutive
      identical failures page at counts 1, 3 and 9 — three pages, not nine
      (spec US1-S3). Then the independence case: two corpora under different
      specs roots, failing interleaved, keep independent counts and page
      independently (spec US1-S4) — must fail.

### Implementation for User Story 1

- [ ] T006 [US1] In `factory/roadmap/workflow.py`, derive
      `roadmap_id = roadmap_workflow_id(request.specs_root)` in both
      `_report_run_failure` and `_report_run_success` and use it for the store
      key and the message text (plan.md trap 1 — do not add a time bucket, a
      new table, or any second mechanism), and rewrite
      `_should_notify_failure` to page when the count is a power of three.
      Until T003–T005 pass, with every landed test in the file still green.

---

## Phase 3: User Story 2 — A pass failure is reported as a notice, and the workflow still fails (Priority: P2)

**Goal**: failure and recovery pages are notices — no keyboard, no choice, no
deadline, no pending escalation row — the durable fact stays in
`roadmap_failures` written before any send, and the workflow execution still
ends FAILED with the pass's own exception.

**Independent Test**: a scripted failing pass with a recording send seam shows
a buttonless, deadline-free message, a FAILED execution carrying the original
exception, zero pending escalation rows, and — with the seam raising — the
fact still recorded.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T007 [US2] Verify prerequisites in this worktree: US1 is merged in the
      base (both reporters key by the stable id) and the suite is green —
      constitution II gate; STOP and report blocked if not satisfied.
- [ ] T008 [P] [US2] Write the renderer cases FIRST, in
      `tests/test_messages.py`: `roadmap_failure_notice` carries the failure
      text verbatim and the consecutive count, contains no response deadline
      (no "No answer by", no `expires_at`) and offers nothing;
      `roadmap_recovery_notice` names the prior count under the same
      constraints (spec US2-S1, US2-S5) — must fail.
- [ ] T009 [P] [US2] Rework `tests/test_roadmap_failure_notifications.py`
      FIRST: re-register the recording seam under the new send activity's name,
      then write: a failed pass sends the notice and the workflow execution
      still fails carrying the pass's own exception (spec US2-S2); with the
      seam raising, the `roadmap_failures` row still holds the failure and its
      count, and **zero** escalation rows exist for the roadmap — re-point the
      landed durability assertion from the escalations table to
      `roadmap_failures` and add its inverse (plan.md trap 4) (spec US2-S3);
      and with `record_roadmap_failure` patched to raise, the workflow's
      recorded failure is still the pass's own exception, not the reporter's
      (spec US2-S4); and the recovery case (the landed green-pass test,
      re-pointed at the notice seam) leaves zero escalation rows for the
      roadmap — today the recovery send itself inserts a pending row through
      `send_escalation`'s insert-when-None branch (plan.md trap 4)
      (spec US2-S5) — must fail.

### Implementation for User Story 2

- [ ] T010 [US2] Add the two pure renderers to `factory/notify/messages.py`,
      copying `manual_intervention_notice`'s fact-not-choice doctrine and
      `_compose`'s clipping. No keyboard function exists for them. Until T008
      passes.
- [ ] T011 [US2] In `factory/activities/notify_activities.py`, add the notice
      send activity copying `_send_question`'s shape (token and chat id read
      from the worker environment inside the activity, no `reply_markup`, a
      failed delivery is data, never a raise); **delete** the escalation-row
      insert from `record_roadmap_failure` and the `escalation_id` field from
      its result. Leave `send_escalation`'s `escalation_id` reuse branch alone
      (plan.md trap 5). Until T009's durability cases pass.
- [ ] T012 [US2] In `factory/roadmap/workflow.py`, point both reporters at the
      new activity with `**_NOTIFY`, and wrap the reporting call at the `run()`
      boundary so a reporter failure is logged with
      `workflow.logger.exception` and the original exception still propagates
      — report, then `raise`, never a clean exit (plan.md trap 3, spec US2-S1,
      US2-S2, US2-S4, US2-S5). Register the activity in `factory/worker.py`
      beside `record_roadmap_failure`. Until T009 passes in full.
- [ ] T013 [US2] Final sweep + docs: `docs/decisions.md` gains a numbered entry
      claimed at landing — a scheduler pass failure is reported as a notice
      (a fact, not a choice: no buttons, no expiry, no pending row), the
      durable fact is the corpus-keyed `roadmap_failures` record written before
      any send, and the failed execution stays FAILED in Temporal — and
      `docs/architecture.md`'s `factory/roadmap/workflow.py` row is updated to
      describe the notice path. Confirm no new dependency, no historical
      escalation row touched (SC-004), and that the full suite is green with
      every test building its own store under `tmp_path` (plan.md trap 7).

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything; its fourth check matters most,
  because if scheduled executions turn out to share one workflow id, US1's
  premise is wrong and the spec must return to the operator rather than
  dispatch.
- Phase 2 (US1) has no dependency and is the MVP: under the schedule's real
  identity behavior, an incident's worth of identical failures becomes three
  pages and a recovery page instead of spam with no recovery.
- Phase 3 (US2) chains on US1 **merged**: both stories edit the same two
  functions in `factory/roadmap/workflow.py` and the same test file, so
  dispatched as siblings they would meet in the merge queue and one would lose
  its attempt to a rebase.

## Implementation Strategy

US1 alone is worth landing: it is two argument changes and one predicate, and
it makes the landed 021/us4 machinery mean under the schedule what its tests
already prove under a single id. US2 is the grammar fix: one message shape
swapped for another that already exists in the codebase twice, one row insert
deleted, and the boundary's re-raise kept exactly where it is. Neither story
changes what any epic or node does, what the judge scores, or what the merge
queue writes.
