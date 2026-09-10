# Tasks: a worker restart does not leave a node reading RUNNING

Read `plan.md` before starting. Trap 1 is the one that decides whether this
story is worth anything: the ledger row this spec declares still names the
7,200-second heartbeat window in its summary, and that window was closed by
082-US5 — `factory/workgraph/workflow.py:487` and
`factory/workgraph/workflow.py:495` — `_agent_heartbeat_timeout`. Re-deriving a
heartbeat clamp fixes nothing and fails FR-003. Trap 4 is the first hazard inside
US1: adding the bound without classifying its expiry turns a stall into a
recorded attempt with no work behind it, sent to verification and judged, with
every gate green. Traps 16 and 17 are the second, and they are the ones that
refuted the first draft of this spec: `_attempt` has **two** call sites, and the
one at `factory/workgraph/workflow.py:3954` — `EpicWorkflow._recovery_attempt`
catches nothing, so the raise FR-004 introduces would kill a node outright on an
ordinary worker restart during a recovery cycle — and would not even arrive as
itself, because that method's `finally` reads a `termination` that is unbound
until the attempt returns, so the key leaks too. Trap 19 is the third, and it
refuted the second draft: the activity **retries** —
`factory/workgraph/workflow.py:367` is `_AGENT_RETRIES` and a heartbeat timeout
is retryable — so the sequence this spec exists for reaches `SCHEDULE_TO_START`
on a re-scheduled attempt whose predecessor ran, heartbeated and spent money. A
branch on the timeout type alone therefore records hours of paid work as an
attempt that never started, on the common path, with every gate green. Trap 20
records a repair that already landed in 127: `_close_out` now keeps the archive
report in `housekeeping_report`, separately from `terminal_reason`. Preserve
that separation and its tests; do not accept the old overwrite as a caveat or
rebuild the fix. Trap 5 says why no test drives
the expiry end to end and names the two routes that look like it and are not — do
not spend attempts there. Trap 6 is a gate trap in both stories:
`tests/test_final_sweep.py` reads every module under `factory/` and fails one
that spells `cap`, `budget`, `quota`, `throttle`, `breach`, `enforce`, `exceed`
or `exceeded` outside a docstring, so an operator string saying a limit "was
exceeded" turns the whole declared `test` gate red. Trap 7 is US2's: `HasField`
raises on a proto3 scalar, and two of the three fields FR-007 asks for are
scalars — and trap 15 closes the obvious repair, because a landed sweep pins
`_live_spend`'s exception clauses by name and a fourth one fails it. Trap 18 is
the other US2 trap with teeth: every field on the entry goes through
`json.dumps`, and `last_heartbeat_time` arrives as a protobuf `Timestamp` that it
cannot carry. Traps 10 and 12 are the two ways US2 lands green and dead — a twin
renderer nothing calls, and a token appended for nodes that have no pending
activity, which turns nine landed modules and the floor board red. Trap 14 is trap
13's shape from the other side: the **correct** US2 diff turns
`tests/test_ergane_build.py:841` red, because it compares a whole `live_spend`
entry against a two-key dict, and that red is confirmation the new fields landed
on the entry rather than beside it.

Tests are written first and must fail before the implementation that satisfies
them — except the tasks marked **The control**, which assert non-regression and
are green from the first commit; do not manufacture a failure for those. T005 is
**not** one of them, and it is the one worth naming twice, because it is half
green and half red before T009 lands. Its **first** shape — the payload on the
`SCHEDULE_TO_START` timeout's own `last_heartbeat_details` — passes on today's
tree, because `factory/workgraph/workflow.py:2512` —
`EpicWorkflow._attempt_timeout` already reads that field and returns the figure.
Its **second** shape — the payload reached through the cause chain — is **red**
on today's tree, because that method binds `timeout = exc.cause` at
`factory/workgraph/workflow.py:2512` — `EpicWorkflow._attempt_timeout`, tests
that one object's type, and walks no `__cause__` anywhere, so the cause-chain
shape comes back with `last_snapshot=None` and fails the "carrying that payload's
figure" assertion. That red is the expected starting state, not a mistake in the
test: it goes green only when T009 widens the search, and it is the only
committed guard on the half of FR-015 the plan calls the same bug with a smaller
blast radius. Deleting the cause-chain shape to clear the red is the repair to
refuse — it ships T009 unproven behind a green gate. Every
acceptance scenario is provable from the diff, which is all the judge sees;
runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — An attempt no worker accepts ends, and names the reason

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-014) In a new test module built the
      way `tests/test_launch_is_not_an_attempt.py` is built — importing `env`,
      `run_epic`, `make_graph`, `make_node`, `passing` and `ScriptedWorld` from
      `tests/test_interpreter.py` rather than restating the harness — run one
      epic and assert that the `ACTIVITY_TASK_SCHEDULED` event for
      `run_agent_attempt` carries a `schedule_to_start_timeout` equal to the new
      module constant, **and** that the constant is at least the thirty-minute
      floor FR-014 states. Copy the reader at `tests/test_interpreter.py:2986` —
      `test_a_dead_agent_is_still_detected_under_a_derived_heartbeat_timeout`,
      which does exactly this for `heartbeat_timeout` at
      `tests/test_interpreter.py:2905` and asserts at
      `tests/test_interpreter.py:2909`; `_EVENT_ACTIVITY_SCHEDULED` is at
      `tests/test_interpreter.py:4089`. The field is unset today, so this is red
      before T008, and the floor assertion is the only thing standing between a
      too-short value and a node killed by an ordinary restart.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, FR-003, trap 1) Build a two-node graph
      with `tests/test_interpreter.py:405` — `make_node` whose
      `timeout_override_s` values differ by two orders of magnitude, run it, and
      assert on both scheduled events at once: the two `schedule_to_start_timeout`
      values are **equal**, the two `heartbeat_timeout` values are **not**, and
      each event's `start_to_close_timeout` and retry policy are what today's code
      produces for that node. One test, four assertions. A bound derived from
      `timeout_s` fails the first pair; a diff that moved
      `_agent_heartbeat_timeout` or `_AGENT_RETRIES` fails the rest.
- [ ] T003 [P] [US1] (spec US1-S3, FR-004, traps 4, 5 and 19) Construct an
      `ActivityError` whose cause is a `TimeoutError` of type `SCHEDULE_TO_START`
      **carrying no heartbeat measurement at all** — empty `last_heartbeat_details`
      and no `TimeoutError` in its cause chain — and call
      `EpicWorkflow()._attempt_timeout(record, exc)` directly, the way
      `tests/test_escalation_offers_only_what_it_can_do.py:444` and
      `tests/test_interpreter.py:4795` call workflow methods outside Temporal, and
      assert it **raises** the no-agent-started signal rather than returning an
      `AdapterResult`. Say in the docstring why the call is direct: the expiry is
      not reachable through the harness (trap 5), and the classification is the
      claim. Say also why the error is built empty: this is the attempt nobody
      ever accepted, and T005 is its twin for the attempt that ran first. Do not
      attempt to make a real schedule-to-start timeout fire.
- [ ] T004 [P] [US1] (spec US1-S4, FR-005) **The control that matters most.** With
      the same direct call, pass an `ActivityError` whose cause is a
      `TimeoutError` of type `HEARTBEAT` carrying a heartbeat payload, and assert
      the method still returns `AdapterResult(termination=Termination.TIMEOUT)`
      carrying that payload's figure and writing it to `record.last_snapshot` —
      byte-identical to `factory/workgraph/workflow.py:2512` —
      `EpicWorkflow._attempt_timeout` today. This is 082-US5's behaviour and the
      assertion that stops this story swallowing a worker death.
- [ ] T005 [P] [US1] (spec US1-S7, FR-015, trap 19) **The assertion that catches
      the branch written on the timeout type alone.** With the same direct call,
      pass an `ActivityError` whose cause is a `TimeoutError` of type
      `SCHEDULE_TO_START` that **does** carry a heartbeat measurement, in both of
      the shapes the server may produce: once with the payload on that timeout's
      own `last_heartbeat_details`, and once with it on a `TimeoutError` reached
      through the cause chain. Assert each returns
      `AdapterResult(termination=Termination.TIMEOUT)` carrying that payload's
      figure and that neither raises. This is the normal path of the whole defect,
      not an edge: `factory/workgraph/workflow.py:367` gives the activity a second
      attempt, a heartbeat timeout is retryable, and the bound therefore fires on
      a retry whose predecessor ran and spent money — classifying it as an ending
      in which no agent started would record hours of paid work as never having
      happened (constitution V, trap 8). Half of this test is red before T009 and
      is meant to be: the first shape passes on today's tree, and the cause-chain
      shape fails on it, because `factory/workgraph/workflow.py:2512` —
      `EpicWorkflow._attempt_timeout` binds `exc.cause` and never walks
      `__cause__`. Write both shapes and leave that red standing — it goes green
      when T009 widens the search, and red again the moment T009 is written as a
      type test alone, which is the point of writing it first.
- [ ] T006 [US1] (spec US1-S5, FR-006) Assert both halves of the reason in one
      test. First: drive the adapter's own launch fault end to end the way
      `tests/test_launch_is_not_an_attempt.py:145` —
      `test_launch_failure_is_reported_distinctly_naming_the_fault` drives it,
      read the node's `terminal_reason`, and assert it is **equal** to what the
      new reason function returns for that signal and count — which pins the
      function as the producer rather than a second string beside it. Second: call
      the same function with the no-worker signal and assert it names the
      schedule-to-start cause and does **not** contain `AGENT_LAUNCH_FAILED`. Not
      `[P]`: it drives the epic and the function over one fixture.
- [ ] T007 [US1] (spec US1-S6, FR-013, traps 16 and 17) **The second call site,
      which no landed test covers.** Compose three landed shapes: script a
      rejected landing into a recovery cycle the way
      `tests/test_interpreter.py:4787` —
      `test_recovery_escalation_kill_preserves_the_branch` does (`script_landing`
      with `checks_failed_snapshot()`, `script_sync`, and a scripted `press`);
      replace `EpicWorkflow._attempt` with a stub that raises the no-agent-started
      signal on the recovery attempt, the way `tests/test_interpreter.py:2714` —
      `test_an_attempt_raise_still_teardowns_and_propagates` replaces it; and
      count the recovery teardowns by `lease.attempt == 2` the way
      `tests/test_interpreter.py:2646` does inside
      `tests/test_interpreter.py:2646` —
      `test_a_verify_raise_in_recovery_still_teardowns_and_propagates`. Assert
      four things: exactly one escalation was sent for the node, its landing state
      is the one the scripted press produces, its `terminal_reason` is not the
      raised signal recorded as a crashed coroutine, and the recovery key was torn
      down exactly once. On today's tree this is red twice over — the raise
      becomes an `UnboundLocalError` in the `finally` and the key never closes.
      Not `[P]`: it drives one epic end to end over the same fixture as T006.

### Implementation for this story

- [ ] T008 [US1] (FR-001, FR-002, FR-014, traps 2, 3 and 6) Add a module-level
      constant beside `factory/workgraph/workflow.py:487` holding the
      schedule-to-start bound, at least thirty minutes (FR-014), and pass it on
      the call at `factory/workgraph/workflow.py:2429` — `EpicWorkflow._attempt`
      beside the four options already there. Derived from nothing: a node with a
      twelve-second deadline and one with a four-hour deadline get the same value,
      because the bound measures how long a worker may be absent. Put the argument
      in the constant's **docstring** — Temporal's own comment says this option
      "should usually not be set: it's useful in specific scenarios like
      worker-specific task queues", and `factory/worker.py:283` — `build_worker`
      is that scenario — and mind trap 6: the word is **bound** or **limit**,
      never `cap`, and no string in the module may say a limit was `exceeded`.
- [ ] T009 [US1] (FR-004, FR-005, FR-015, traps 4 and 19) In
      `factory/workgraph/workflow.py:2512` — `EpicWorkflow._attempt_timeout`,
      add the one branch this story needs, in this order. First keep the existing
      heartbeat read at `factory/workgraph/workflow.py:2512` —
      `EpicWorkflow._attempt_timeout`, widened to look for the payload on the
      cause's own `last_heartbeat_details` **and** on the `TimeoutError`s
      reachable through its cause chain, so the snapshot is computed before
      anything is decided. Then, and only when that search found nothing, a
      `SCHEDULE_TO_START` timeout raises the same workflow-internal signal
      `factory/workgraph/workflow.py:748` — `_LaunchFailed` carries, so
      `factory/workgraph/workflow.py:2222` — `EpicWorkflow._run_node` records
      launch evidence instead of an `AttemptRecord` and the node is bounded by
      `factory/verify/models.py:1224` — `VerificationConfig`. A
      `SCHEDULE_TO_START` that **did** carry a measurement falls through to
      today's `AdapterResult(termination=Termination.TIMEOUT)` with that figure
      (FR-015), and so does every other cause. A condition on
      `cause.type` alone is the wrong move trap 19 describes and T005 catches:
      it is the common case, not the rare one. Do **not** add a retry of your
      own: the server treats this expiry as non-retryable once it fires, so
      `_AGENT_RETRIES` cannot absorb it (trap 3). This task is only correct
      together with T011 — the same raise reaches a second caller that catches
      nothing.
- [ ] T010 [US1] (FR-006) Give `factory/workgraph/workflow.py:748` —
      `_LaunchFailed` a field naming which fault raised it, and build **one**
      reason function that both `factory/workgraph/workflow.py:2235` —
      `EpicWorkflow._run_node` and `factory/workgraph/workflow.py:2243` —
      `EpicWorkflow._run_node` call, so the adapter's fault goes on producing a
      reason containing `AGENT_LAUNCH_FAILED` — `tests/test_launch_is_not_an_attempt.py:159`
      is the landed assertion that must stay green, untouched — while the
      no-worker ending names the schedule-to-start cause instead. Two hardcoded
      strings, one per branch, satisfy T006's second half and fail its first.
- [ ] T011 [US1] (FR-013, traps 16 and 17) Handle the signal at the **second**
      call site. At `factory/workgraph/workflow.py:3954` —
      `EpicWorkflow._recovery_attempt` the raise must end that recovery cycle as
      one that produced no result — the same `None` its other failures return,
      which `factory/workgraph/workflow.py:3817` — `EpicWorkflow._run_recovery`
      already turns into a landing escalation — rather than escaping through
      `EpicWorkflow._run_recovery` (which has no `except` anywhere) to
      `factory/workgraph/workflow.py:1656` — `EpicWorkflow._reap_finished`, whose
      `except Exception` KILLs the node. Bind `termination` before the `try` at
      `factory/workgraph/workflow.py:4054` — `EpicWorkflow._recovery_attempt` the
      way `factory/workgraph/workflow.py:1780` — `EpicWorkflow._run_node` binds
      its own, so the `finally` at `factory/workgraph/workflow.py:4114` —
      `EpicWorkflow._recovery_attempt` still closes the recovery key exactly once
      instead of raising `UnboundLocalError` over the ending. Do not widen the
      handler to bare `Exception`: the landed contract that a raise in recovery
      reaches the reaper (`tests/test_interpreter.py:2646`) must survive for every
      other exception.

### Verification for this story

- [ ] T012 [US1] Paste, as committed evidence, the two scheduled events read out
      of one epic's recorded history — activity type, `schedule_to_start_timeout`,
      `heartbeat_timeout` and `start_to_close_timeout` per node — the two reason
      strings the function returns for the two signals side by side, the two
      `_attempt_timeout` outcomes from T005 and T003 beside each other (the
      `SCHEDULE_TO_START` that carried a measurement, returned as a `TIMEOUT`
      result with its figure, and the one that carried none, raised), and the
      recovery-path ending from T007: the escalation count, the landing state and
      the teardown count.

## Phase 2: User Story 2 — The status line says which nodes have an agent actually working

### Tests for this story (write FIRST, must fail)

- [ ] T013 [P] [US2] (spec US2-S1, FR-007, trap 7) In a new test module, build the
      fake `describe()` answer this repository does not have —
      `tests/test_ergane_build_status_refusal.py:54` — `_FakeWorkflowHandle`
      returns `pending_activities=[]` at
      `tests/test_ergane_build_status_refusal.py:68`, so no **fake** drives
      `_live_spend`'s loop with a populated list — the one landed test that does,
      `tests/test_ergane_build.py:815`, drives it with real protos and only for a
      STARTED activity carrying a payload, which is the case that already works.
      Give the fake one pending `run_agent_attempt` whose activity id names a node
      in the document and which carries **no** decodable heartbeat payload, and
      assert the map holds an entry for that node carrying **all three** fields
      FR-007 requires, field by field: the pending activity's state under its own
      key, that activity's own retry attempt as an integer, and its last heartbeat
      time — none of them a protobuf message. Asserting the state alone would let
      the two fields trap 9 and trap 18 are about ship silently or not at all.
      Today `factory/cli/nouns/build.py:456` — `_live_spend` discards the whole
      entry and the map is empty. The fake must answer `HasField` for the message fields only —
      `state` and `attempt` are proto3 scalars and `HasField` raises `ValueError`
      on them (trap 7), so build the fake so a production call that gets this
      wrong fails loudly here rather than in an operator's terminal. Do **not**
      let the production repair be a `try/except ValueError`:
      `tests/test_ergane_status.py:1528` pins this function's exception clauses to
      exactly three and `tests/test_ergane_status.py:1822` —
      `test_no_temporal_call_site_catches_the_transport_failure_alone` sweeps for
      a fourth (trap 15).
- [ ] T014 [P] [US2] (spec US2-S2, FR-009) Assert the pair: two documents
      differing only in the pending activity's state — one SCHEDULED, one STARTED
      — produce node lines that are **not equal**, and the line built from the
      SCHEDULED one names that state. Assert both halves; equality-of-difference
      alone would pass on any token that varies, and the naming half alone would
      pass on a token that is always present.
- [ ] T015 [P] [US2] (spec US2-S3, FR-010, trap 8) Given a pending activity
      carrying a decodable heartbeat payload, assert the node line carries both
      the spend figure and the capture time it was measured at. Temporal retains
      `heartbeat_details` across retry attempts, so this is the assertion that
      stops a dead worker's last measurement reading as a live one — and the
      figure itself must still be printed, never dropped or zeroed
      (constitution V).
- [ ] T016 [P] [US2] (spec US2-S4, FR-011, traps 14 and 18) **The control, and the
      one landed assertion this story amends.** Assert that the `live_spend`
      object `build status --json` emits at `factory/cli/nouns/build.py:1298` —
      `_query_status` still carries `spend_usd` and `captured_at` under those
      exact keys with those exact types for every entry that has a figure, **and**
      that the document loads as JSON at all — `factory/cli/nouns/build.py:1298` —
      `_query_status` runs the whole map through `json.dumps`, which refuses the
      protobuf `Timestamp` that `last_heartbeat_time` arrives as (trap 18).
      `tests/test_ergane_build.py:815` —
      `test_status_reads_live_spend_off_the_running_attempt` already asserts the
      keys today, but as a **whole-dict equality** at
      `tests/test_ergane_build.py:841`, so the correct T018 turns it red: widen
      that assertion in the same commit to name the fields the entry now carries,
      and leave its human-side assertion at `tests/test_ergane_build.py:845`
      untouched — it must go on passing, because FR-010 keeps printing the figure.
      The wrong move is to read the red as "the entry may not change" and hang the
      new fields off a second sibling map.
- [ ] T017 [P] [US2] (spec US2-S5, FR-012, trap 12) **The control that keeps a
      landed module green.** Assert that a status document whose nodes have no
      pending agent activity produces node lines byte-identical to today's — no
      state token, no padding, no sentinel. Every `render_status` call in
      `tests/test_status_shows_the_dials_in_force.py` omits `live_spend`, and
      `tests/test_status_shows_the_dials_in_force.py:167` — `epic_and_node_lines`
      compares whole node lines across five degraded documents, so a renderer that
      always appends a column turns that module red for a reason this story is not
      about — and with it the other nine modules that call `render_status` without
      a live map, and `ergane status`'s own floor board, which reuses this
      renderer at `factory/cli/status.py:805` — `_epic_lines` and supplies no live
      map either. Write this test before T018.

### Implementation for this story

- [ ] T018 [US2] (FR-007, FR-008, traps 7, 9 and 18) In
      `factory/cli/nouns/build.py:421` — `_live_spend`, move the heartbeat filter
      at `factory/cli/nouns/build.py:456` — `_live_spend` off the entry's
      existence and onto the figure alone: every pending `run_agent_attempt` whose
      activity id names a node gets an entry, and `spend_usd`/`captured_at` are
      present only when a payload decodes. Carry the pending activity's `state`,
      its own retry `attempt` and its `last_heartbeat_time`, each as a JSON scalar
      — the state as its enum name, the heartbeat time as an ISO-8601 string
      beside the plain `str` that `captured_at` already is at
      `factory/cli/nouns/build.py:459` — `_live_spend` — because
      `factory/cli/nouns/build.py:1298` — `_query_status` serialises the whole map
      and `json.dumps` refuses a protobuf `Timestamp` (trap 18). Read `state` and
      `attempt` **directly** — `HasField` raises on a proto3 scalar and nothing in
      this function guards it — and label the activity's retry count so it cannot
      be read as the ladder's attempt, which the node line already prints from the
      query document (trap 9). Add no exception clause to this function: a landed
      sweep pins its three by name (trap 15).
- [ ] T019 [US2] (FR-009, FR-010, FR-012, trap 12) In
      `factory/cli/nouns/build.py:478` — `render_status`, replace the bare figure
      at `factory/cli/nouns/build.py:494` — `render_status` with a token that
      names the pending activity's state and, when a figure is present, carries
      the capture time beside it. Follow the three token helpers already there —
      `factory/cli/nouns/build.py:800` — `_routing_token`,
      `factory/cli/nouns/build.py:539` — `_base_token` and
      `factory/cli/nouns/build.py:733` — `_reason_token` — rather than growing the
      format string at `factory/cli/nouns/build.py:501` — `render_status`. A node
      with no entry gets the empty string, exactly as today.
- [ ] T020 [US2] (trap 10) Confirm by reading that
      `factory/workgraph/cli.py:855` — `_live_spend` and
      `factory/workgraph/cli.py:929` — `render_status` were **not** edited. They
      are a pre-`ergane` copy that no module under `factory/` and no test imports,
      and `ergane build status` dispatches the `factory/cli/nouns/build.py` pair
      through the parser at `factory/cli/nouns/build.py:2166`. Editing the twin
      satisfies no scenario; editing only the twin ships a green gate and an
      unchanged floor.

### Verification for this story

- [ ] T021 [US2] Paste, as committed evidence, the node lines produced from three
      documents — one with no pending activity, one whose pending activity is
      SCHEDULED with a retained figure, and one whose pending activity is STARTED
      — and the `live_spend` object `--json` emits for the middle one.

## Verification

- [ ] T022 The full gate command passes green, including `tests/test_final_sweep.py`
      (trap 6), `tests/test_status_shows_the_dials_in_force.py` (trap 12),
      `tests/test_ergane_status.py`'s guard sweep (trap 15) and
      `tests/test_interpreter.py`'s recovery cases (traps 16 and 17) — none of
      which this spec edits and all of which a careless diff turns red — and
      including `tests/test_ergane_build.py`, whose one amended assertion (trap
      14) is the only landed test line this spec changes.
- [ ] T023 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Steps 2 and 3 together are the falsifiable test
      of this whole spec, because they are the 2026-08-19/20 two-hour stall and
      the consumer's ninety minutes of `RUNNING attempt 6` run forwards — and they
      are two steps rather than one for a reason the plan states: after a single
      expiry no operator surface names the cause, so step 2's evidence is the
      server's own `ACTIVITY_TASK_TIMED_OUT` event with `timeout_type`
      `SCHEDULE_TO_START` in the epic's history, and step 3 takes the node to its
      second launch strike, where the ending and its escalation become readable.
      Note what step 2 says about the window itself: with the worker down there is
      no node line to read at all, because one worker serves both the workflow and
      the activity. Step 4 is the false-positive check that decides whether the
      constant's value is right, step 5 proves 082-US5's heartbeat path survived
      and takes two worker deaths rather than one, and step 6 is the same event on
      the recovery path FR-013 closes.
