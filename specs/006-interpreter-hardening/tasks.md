# Tasks: Interpreter Hardening

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution I): the test task is written and **must fail**
before its implementation task runs. A task that finds its test already passing has
found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written in any
order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm 003 has landed on the target's default branch — this epic
      assumes `depends_on_merged` exists and that the merge queue, not the D-024 manual
      dance, lands its nodes. Record the decision-log number claimed for the heartbeat
      trade (spec § Decision) in `docs/decisions.md`, taking the next free D-number after
      whatever 003's T022/T034/T045 consumed.

---

## Phase 2: User Story 1 — An attempt's history cost does not grow with its duration (Priority: P1) 🎯 MVP

**Goal**: usage observation rides the agent activity's heartbeat; the per-interval timer
and `poll_usage` activity leave the workflow's event log entirely.

**Independent Test**: run one attempt for a simulated four hours under time skipping and
assert its history event count is within a small constant of a one-minute attempt.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q` is green and
      `factory/workgraph/workflow.py`, `factory/workgraph/adapter.py`,
      `factory/activities/agent_activities.py`, `factory/activities/usage_activities.py`
      exist — constitution I gate; STOP and report blocked if not satisfied.
- [x] T003 [P] [US1] Write `tests/test_adapter.py` cases FIRST: the monitor's heartbeat
      callable is invoked with a `UsageSnapshot` once a reading exists and with `None`
      before the first successful read; a usage read that raises leaves the previous
      snapshot in place **and the beat still fires** (liveness must never be killed by a
      spend read); the proxy is read at most once per `poll_interval_s` regardless of the
      beat interval — must fail.
- [x] T004 [P] [US1] Write a data-converter round-trip test FIRST: the heartbeat payload
      (`UsageSnapshot | None`) survives `temporalio`'s default data converter unchanged.
      A payload that fails to serialise degrades the heartbeat to liveness-only *silently*,
      so this is asserted directly rather than inferred — must fail.
- [x] T005 [US1] Write `tests/test_interpreter.py` delivery-path cases FIRST, one per
      path, each asserting teardown receives a **non-NULL** spend: (a) normal completion —
      the snapshot arrives on `AdapterResult`; (b) timeout — the workflow reads
      `TimeoutError.last_heartbeat_details` off the `ActivityError`; (c) kill — `_cancel`
      extracts the snapshot before swallowing the error. Today's tests assert on a polled
      value and would not catch a path that silently stops populating it — must fail.
- [x] T006 [US1] Write the history-cost test FIRST (SC-001/FR-001/FR-002): under time
      skipping, an attempt simulating four hours and an attempt simulating one minute
      contribute history event counts within a small constant of each other, and no
      `poll_usage` activity and no timer appears in the four-hour attempt's history —
      must fail.

### Implementation for User Story 1

- [x] T007 [US1] Amend `factory/workgraph/adapter.py`: the monitor's heartbeat callable
      takes details; add the bounded usage read on its own `poll_interval_s` cadence,
      failure-isolated from the beat, until T003 and T004 pass.
- [x] T008 [US1] Amend `factory/workgraph/models.py` (`AdapterResult.last_snapshot`) and
      `factory/activities/agent_activities.py` to carry the final snapshot home in the
      activity's return value.
- [x] T009 [US1] Replace the loop at `factory/workgraph/workflow.py` (the
      `wait_condition(..., timeout=poll_interval_s)` / `poll_usage` block) with a plain
      await plus the existing kill check, and read `last_heartbeat_details` on the timeout
      and kill paths, until T005 and T006 pass. `poll_usage` stays registered — 001 owns
      it and the judge path has no poller — it is simply no longer scheduled per interval.
- [x] T010 [US1] Correct `TeardownInput.last_snapshot`'s docstring in
      `factory/activities/usage_activities.py`: it no longer describes a polled value, and
      leaving that sentence is a lie the next reader inherits. State that a NULL spend now
      means "never measured", which is the stronger claim the heartbeat buys (FR-003).

---

## Phase 3: User Story 2 — An epic that cannot succeed never starts (Priority: P2)

**Goal**: `factory-epic start` refuses a misconfigured epic before dispatching anything.

**Independent Test**: start an epic naming an unserved alias, and one whose first key
alias is taken; both refuse with zero dispatches and zero keys issued.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T011 [P] [US2] Write `tests/test_usage_client.py` cases FIRST against a fake
      transport: the client can list served model ids and list key aliases; a non-200 and
      a connection error are each surfaced as distinct, named failures — must fail.
- [ ] T012 [US2] Write `tests/test_epic_cli.py` preflight cases FIRST: an unserved alias
      exits non-zero naming **each** unserved alias *with every persona that names it*,
      having started no workflow and issued no key; a proxy that does not answer is a
      distinct finding naming the address tried (FR-005), never a pass; a first-attempt
      key alias already present is reported with its remedy (FR-006); a fully valid
      configuration starts exactly as today; exit codes follow the existing contract
      (`1` operator-fixable, `2` service not answering) — must fail.
- [ ] T013 [US2] Write the honesty case FIRST: preflight validates the registry the CLI
      can see, while the worker resolves its own (R8, deliberate). Assert the wording
      states what was checked and does not claim the worker's resolution was validated —
      must fail.

### Implementation for User Story 2

- [ ] T014 [US2] Extend `factory/usage/litellm_client.py` with the two read-only calls
      until T011 passes. No key value may be logged or returned — aliases only.
- [ ] T015 [US2] Implement preflight in `factory/workgraph/cli.py`'s `start_command`,
      ahead of starting the workflow and after the existing structural re-validation,
      until T012 and T013 pass. Reuse 003's onboarding `Finding` type if importable;
      define a local shape only if it genuinely is not (plan.md § Data Model).

---

## Phase 4: User Story 3 — A killed epic restarts without hand-cleaning credentials (Priority: P3)

**Goal**: issuance reclaims an alias orphaned by a dead epic, and refuses to disturb one
held by a live epic.

**Independent Test**: kill an epic mid-attempt, restart it, assert it dispatches with no
operator call to the proxy admin API.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T016 [P] [US3] Write `tests/test_usage_activities.py` cases FIRST: an alias whose
      epic workflow is **closed** is reclaimed (delete-then-reissue) and the attempt
      proceeds with exactly one live key for that alias; an alias whose epic workflow is
      **open** is refused, untouched; when the workflow's state cannot be determined
      (Temporal unreachable) issuance **refuses rather than guesses** — deleting a live
      epic's key to fix a stopped one breaks a running node; the reclaimed alias's
      historical spend remains queryable afterwards (FR-011) — must fail.

### Implementation for User Story 3

- [ ] T017 [US3] Implement reclaim in `issue_attempt_key`
      (`factory/activities/usage_activities.py`) until T016 passes, using the epic's
      workflow id (`epic-<epic_id>`) as the live/dead discriminator. `_CREDENTIAL_REJECTED`
      stays `{401, 403}` — a rejected credential is a misconfiguration and retrying it
      only delays the diagnosis.

---

## Phase 5: User Story 4 — Transient infrastructure does not discard hours of work (Priority: P3)

**Goal**: the agent heartbeat bound and the issuance retry budget are sized for real
outages rather than for a healthy instant.

**Independent Test**: simulate a Temporal outage longer than today's bound and a proxy
outage longer than today's issuance budget; the attempt and the epic both survive.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T018 [P] [US4] Write `tests/test_interpreter.py` cases FIRST: the agent activity's
      heartbeat timeout is derived from the attempt's configured timeout (not a fixed
      small multiple of the beat) and is floored so a short attempt keeps a sane bound; an
      attempt survives an unavailability window an order of magnitude longer than today's
      five seconds (SC-004); **a genuinely dead agent is still detected and classified**
      once the looser bound elapses — the bound loosens, it does not vanish — must fail.
- [ ] T019 [P] [US4] Write issuance-retry cases FIRST: a transient proxy failure lasting
      on the order of a container restart is survived; a 401/403 still fails fast and
      non-retryably — must fail.

### Implementation for User Story 4

- [ ] T020 [US4] Amend `_AGENT_HEARTBEAT_TIMEOUT` and `_RETRIES` in
      `factory/workgraph/workflow.py` until T018 and T019 pass. Replace the existing
      comment: it derives five beats from "the slack a healthy attempt on a busy worker
      needs", which was never about a Temporal outage — the new comment must name what it
      actually protects against.

---

## Phase 6: User Story 5 — The operator surface reports what is true (Priority: P3)

**Goal**: `factory-epic status` never again prints `RUNNING` for a closed workflow.

**Independent Test**: query status against running, failed, terminated and completed
workflows; each is distinguishable.

### Tests for User Story 5 (write FIRST, must fail)

- [ ] T021 [P] [US5] Write `tests/test_epic_cli.py` cases FIRST: status against a closed
      workflow reports its Temporal execution status and is distinguishable from a running
      epic; a running epic's per-node output is byte-identical to today; under `--json` the
      execution status is a **sibling key** and the existing query payload is unchanged, so
      no consumer of the documented "dump, never a re-assembly" contract breaks — must fail.

### Implementation for User Story 5

- [ ] T022 [US5] Implement execution-status reporting in `status_command`
      (`factory/workgraph/cli.py`) via the handle's `describe()`, until T021 passes.
- [ ] T023 [US5] Final sweep + docs (FR-011): grep-backed assertion that no credential
      value reaches any preflight finding, status output, or error path; update
      `docs/architecture.md` §3 (the attempt loop no longer polls; observation rides the
      heartbeat) and §5 (teardown's fallback provenance and the stronger NULL semantics).

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 is operator work and gates everything.
- Phase 2 (US1) has no dependency and is the MVP.
- Phase 3 (US2) has no dependency on US1 — different files, different loop.
- Phase 4 (US3) depends on US2: preflight is what makes an orphan legible, and recovery
  built first would be recovering a condition nothing yet names.
- Phase 5 (US4) depends on US1: both tune constants inside the attempt loop US1 rewrites.
  This is conflict avoidance, not logic.
- Phase 6 (US5) has no dependency.

### Within stories

Tests before implementation, always. Within US1, T003/T004 are `[P]` (adapter and
converter), while T005/T006 both edit `tests/test_interpreter.py` and are sequential.

### Parallel Opportunities

US1, US2 and US5 are independent roots and may run concurrently. US3 follows US2; US4
follows US1. With 007 unbuilt the scheduler is still sequential, so this ordering is
advisory until parallel dispatch exists — at which point this graph becomes a live test
of it.

## Implementation Strategy

US1 first and alone if anything must be cut: it is the only item here with a ceiling
behind it, and the others cost an operator minutes rather than bounding how long an epic
may run. US5 is the cheapest and could be taken opportunistically by whichever node is
free. Nothing in this epic changes a decision the factory makes — only what it costs and
what the operator is told — so SC-006 (the full existing suite stays green) is the
standing check on every task.
