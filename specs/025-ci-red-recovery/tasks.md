# Tasks: A red check that reaches no one

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
      hosts the work, and record the answers here. Five things, because each
      has either already been wrong once or the plan turns on it: that the
      sampler-then-signal shape in `run_agent_attempt`
      (`tests/test_interpreter.py:1276-1289`) is unchanged and the fake still
      records dispatches at attempt start (US1's gate hooks in there); that
      `classify` still produces `CHECKS_FAILED` only when
      `failing_required_checks` is non-empty (`classify.py:76-77`); that
      `open_landing_pr` still drops `push_branch`'s returned sha (if someone
      began recording it, US3's FR-009 task changes shape); that `_run_recovery`
      still routes sync → attempt → `_reenqueue` with no evidence fetch in
      between (if the CI blind spot was partially fixed elsewhere, re-scope
      before dispatch); and the current line anchors of the four coincidence
      assertions (kill `:5000`, pause `:4935`, cap-overlap `:4367`,
      landing-fanout `:4655`), because the finding's own anchor had already
      rotted from `:4822` to `:4958`.

---

## Phase 2: User Story 1 — The required check must stop failing on a coincidence (Priority: P1) 🎯 MVP

**Goal**: steering signals are withheld until every node the scenario declares
in flight has been observed dispatched, so the kill/pause/overlap premises are
established by construction and the required check stops failing on scheduler
timing.

**Independent Test**: the converted kill test passes 15 consecutive runs with a
delayed third pickup, and a gate that can never be satisfied fails with a named
reason inside the bounded wait.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green; plan.md's US1 inventory claims hold — constitution II gate; STOP
      and report blocked if not satisfied.
- [ ] T003 [US1] Convert the kill test FIRST
      (`test_kill_with_n_in_flight_salvages_every_one_before_terminating`,
      `tests/test_interpreter.py:4958`): declare the dispatch gate for
      `{us1, us2, us3}` via the new `ScriptedWorld` parameter, AND script the
      third node's pickup slow via the new per-node dispatch delay (plan.md
      § US1 step 1) — the delayed pickup is US1-S1's *When*, and without it a
      lucky run cannot distinguish "the gate held the signal" from "no race
      happened". Keep every durable assertion byte-for-byte (salvage set,
      teardown set, KILLED states, branch reachability — plan.md trap 1 is why
      they stay), and keep the running-set assertion, which the gate makes
      deterministic. Must fail now: neither parameter exists yet (spec US1-S1).
- [ ] T004 [US1] Write the gate's loud-failure case FIRST: a scenario whose
      declared set can never all be in flight (concurrency limit 1 over two
      nodes, gate declared for both) fails within the harness's bounded wait
      with the gate's named marker recorded — never a hang, never a silent
      pass (spec US1-S2) — must fail.
- [ ] T005 [US1] Implement the gate in `ScriptedWorld.run_agent_attempt` per
      plan.md § US1: wait (bounded by `WAIT_TIMEOUT_S`) for the declared set to
      be observed dispatched before sampling and before sending `steer`; on
      timeout record the named marker and proceed so the failure carries
      evidence. Then convert the pause sibling (`:4866`), the cap-overlap test
      (`:4345`) and the landing-fanout test (`:4613`, assert `:4655`) to the
      same premise — the gate where a signal exists, the barrier where none
      does (plan.md § US1 step 2) — preserving their existing assertions
      (spec US1-S3). Until T003 and T004 pass.
- [ ] T006 [US1] Demonstrate the de-flake and the boundary: run the four
      converted tests 15 times consecutively in a shell loop (no new
      dependency, no `pytest-rerunfailures` — plan.md trap 2), all green; then
      confirm from the diff that no required check is retried, no pytest
      marker is added or relied on (plan.md trap 3), and no test or durable
      assertion was deleted (spec US1-S4).

---

## Phase 3: User Story 2 — A CHECKS_FAILED recovery is a retry with evidence (Priority: P1)

**Goal**: the recovery attempt's prompt carries the failing check's name, run
URL and a bounded verbatim log tail; the queue history and escalation rendering
carry the names; the fetch is a non-blocking activity that degrades instead of
aborting.

**Independent Test**: a scripted `CHECKS_FAILED` rejection produces a recovery
prompt quoting name, URL and log tail; a scripted fetch failure still
dispatches the attempt with the absence stated.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T007 [US2] Verify prerequisites in this worktree (its base contains US1 —
      the merge edge): `uv run pytest -q` green; the US2 inventory claims hold
      — STOP and report blocked if not.
- [ ] T008 [P] [US2] Write the client cases FIRST in `tests/test_gh_client.py`:
      `pr_checks` issues `gh pr checks <n> --json name,state,link` and parses
      name/state/link; `run_failed_log` issues `gh run view <run-id>
      --log-failed` and returns a tail bounded by the named constants (plan.md
      trap 8); a link that does not parse to a run id degrades to name + link.
      Re-assert the structural guards still pass over the widened command
      surface (`tests/test_gh_client.py:200-207`) — must fail.
- [ ] T009 [P] [US2] Write the activity cases FIRST in
      `tests/test_merge_activities.py`: `fetch_check_failure` returns per-check
      `(name, url, log_tail, note)` evidence; every `GhError` shape returns
      degraded evidence with the unavailability stated, never a raise (spec
      US2-S3, plan.md trap 7); and the activity's source uses
      `asyncio.to_thread` — the `sync_landing_branch` shape, not
      `poll_landing`'s blocking call (spec US2-S4, plan.md trap 4) — must fail.
- [ ] T010 [P] [US2] Write the prompt cases FIRST in `tests/test_prompt.py`:
      `_landing_section` renders check name, run URL and log tail verbatim
      (spec US2-S1); evidence with no log renders the stated absence (spec
      US2-S3); a `LandingEvidence` built with only the old fields renders
      exactly as today, which is what keeps CONFLICT and recorded histories
      untouched (plan.md trap 5) — must fail.
- [ ] T011 [P] [US2] Write the history and escalation-page cases FIRST in
      `tests/test_mergequeue_models.py` and `tests/test_messages.py`:
      `ObservedOutcome.failing_checks` defaults to `()` so pre-spec histories
      deserialize (plan.md trap 5); `render_landing_history` names the
      failing checks on a `CHECKS_FAILED` line; and the escalation message
      built for a landing escalation carries the failing check name, the
      failing run's URL, and the failing test line when the fetched tail
      holds one — assert the page text itself, because the requirement is
      that the operator never has to ask a second question (spec US2-S2,
      FR-008) — must fail.
- [ ] T012 [US2] Write the interpreter case FIRST in
      `tests/test_interpreter.py`, alongside the existing recovery tests at
      `:4046`: a `CHECKS_FAILED` rejection whose snapshot names a failing check
      and whose scripted fetch returns a log tail produces a recovery prompt
      quoting name, URL and tail (assert via `prompts_for`, the `:4105` style)
      (spec US2-S1); the recorded queue history carries the names (spec
      US2-S2); and the CONFLICT path's sequence and prompt are byte-identical
      to today — no fetch runs (spec US2-S5) — must fail.

### Implementation for User Story 2

- [ ] T013 [US2] Implement the client methods (`factory/mergequeue/gh.py`,
      extending the command-table docstring) and the `fetch_check_failure`
      activity (`factory/activities/merge_activities.py`) with the bounded
      tail constants and the degrade-never-raise contract; register the
      activity in `factory/worker.py`. Until T008 and T009 pass.
- [ ] T014 [US2] Wire the model, prompt and workflow:
      `ObservedOutcome.failing_checks` filled at the recording site
      (`factory/workgraph/workflow.py:2126-2130`); `_run_recovery` fetches
      evidence only on the `CHECKS_FAILED` clean-sync path before
      `_recovery_attempt`; `LandingEvidence` gains defaulted evidence fields
      and `_landing_section` renders them verbatim
      (`factory/workgraph/prompt.py:466`); `render_landing_history`
      (`factory/notify/messages.py:197`) names the checks. Until T010, T011
      and T012 pass.

---

## Phase 4: User Story 3 — Re-enqueueing bytes the queue already rejected requires a human (Priority: P2)

**Goal**: the enqueued tip is recorded; a recovery whose resulting tree is
identical to the rejected tip escalates instead of silently re-enqueueing;
RETRY means "enqueue it anyway"; a sync that moved nothing says so in the
prompt.

**Independent Test**: a scripted recovery that changes nothing escalates before
any second enqueue; RETRY proceeds to enqueue the identical tree; a recovery
that changes the tree re-enqueues exactly as today.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T015 [US3] Verify prerequisites in this worktree (its base contains US2 —
      the merge edge): `uv run pytest -q` green; the US3 inventory claims hold
      — STOP and report blocked if not.
- [ ] T016 [P] [US3] Write the tree-identity cases FIRST in
      `tests/test_worktree.py`, against a `tmp_path` git repo: two commits that
      differ only by an empty salvage commit on top compare as identical —
      tree identity, never commit identity, the wrong fix plan.md trap 6 names
      — and a one-byte content change compares as different (spec US3-S5) —
      must fail.
- [ ] T017 [US3] Write the futility cases FIRST in `tests/test_interpreter.py`:
      a `CHECKS_FAILED` recovery whose sync moves nothing and whose attempt
      changes nothing escalates before any second `enqueue_landing` (assert on
      the activity sequence: exactly one enqueue) with choices
      `[RETRY | KILL | PAUSE_EPIC]` and a `history_summary` that names the
      futility — the identical-tree fact, not just the queue history (spec
      US3-S1, plan.md § US3 step 3's note seam); a scripted `RETRY` press
      then pushes and enqueues the identical tree and the landing returns to
      polling, with `recovery_cycles` incremented exactly once for the whole
      cycle (spec US3-S2); `KILL` (and expiry) ends the node KILLED with its
      branch still named in the final status (spec US3-S3); and a recovery
      whose attempt changes the tree re-enqueues with today's exact sequence —
      no escalation (spec US3-S4) — must fail.
- [ ] T018 [P] [US3] Write the staleness-refuted case FIRST in
      `tests/test_prompt.py`: evidence carrying the base-unmoved fact renders
      the sentence FR-013 asks for, and evidence without it renders nothing new
      (spec US3-S6) — must fail.
- [ ] T019 [US3] Write the pre-spec-history case FIRST in
      `tests/test_interpreter.py`: a landing with no recorded `enqueued_tip`
      re-enqueues exactly as today — absence is never read as futility (spec
      US3-S4, the edge case named in spec.md) — must fail only if the
      implementation over-reaches; say so in the docstring.

### Implementation for User Story 3

- [ ] T020 [US3] Record the tip and compare the trees:
      `OpenLandingPrResult.pushed_sha: str | None = None`
      (`factory/activities/merge_activities.py:311-346` stops dropping
      `push_branch`'s return), `Landing.enqueued_tip: str | None = None`
      (`factory/mergequeue/models.py:84`) set at both enqueue sites; the
      `trees_identical` helper in `factory/workgraph/worktree.py` and its
      activity in the `asyncio.to_thread` shape (plan.md trap 4), registered in
      `factory/worker.py`. No new `QueueOutcome` or `LandingState` member
      (plan.md trap 5). Until T016 passes.
- [ ] T021 [US3] Gate `_reenqueue` and wire the escalation: compare before
      `prepare_landing_pr`; on identical trees call `_escalate_landing`, with
      `RETRY` completing the interrupted enqueue of the same cycle and every
      other resolution routed through `_apply_landing_resolution` unchanged;
      carry the `base_unmoved` fact from `_run_recovery`'s two refs into the
      landing evidence and render it (`factory/workgraph/prompt.py:466`).
      Until T017, T018 and T019 pass.
- [ ] T022 [US3] Final sweep + docs: `docs/decisions.md` gains a numbered entry
      claimed at landing — a `CHECKS_FAILED` recovery is a retry with evidence,
      and re-enqueueing a tree the queue already rejected now requires an
      operator's decision — because both change a rule the factory previously
      held (blind sync-and-re-enqueue). Confirm no new dependency, no
      automatic check retry anywhere, and that the CONFLICT / pending /
      MERGED / DEQUEUED_BY_HUMAN / STALLED paths are untouched (spec SC-004,
      SC-005).

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything.
- US1 has no dependency and lands first by design: it de-flakes the required
  check that US2's and US3's own landings must ride through.
- US2 chains on US1 **merged** — both edit `tests/test_interpreter.py`, and the
  merge edge is what keeps the second worktree's base honest.
- US3 chains on US2 **merged** — it extends the evidence fields, the recovery
  path in `factory/workgraph/workflow.py` and the same test file US2 just
  touched. Dispatched as siblings they would meet in the merge queue.

## Implementation Strategy

US1 alone is worth landing: it removes the stochastic half of the killer from
the one check every future landing depends on, for the price of a test-harness
parameter. US2 is the substantive fix — after it, a recovery attempt reads the
CI log instead of guessing — and US3 closes the loop by making a no-op recovery
cost an operator's button-press instead of a CI run, a two-hour stall and a
dead subtree. None of the three changes what the judge scores, what a gate
runs, or how a check is retried — the queue's one deterministic gate stays
exactly as trustworthy as it is today.
