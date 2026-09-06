# Tasks: a verdict is a fact about the code

Read `plan.md` before starting, and read
`specs/058-a-verdict-is-a-fact-about-the-code/evidence/055-us1-attempt1-gate.txt`
before that. This spec's diagnosis has been wrong twice on paper — trap 1 names
the second wrong version and the line of evidence that falsifies it — so US1
opens with an experiment, not a fix. Trap 3 is the constraint that makes the
obvious fix inexpressible and that bounds what US2 may touch: the deadline clock
starts inside the same awaited call that launches the process, so there is no
seam at which a test can wait for readiness before the clock begins, and no
launch in either boundary suite is convertible. Trap 6 is the condition that can
stop US1 before it starts — no `bwrap`, no measurement, report blocked. Trap 12
is the honest limit of the experiment: one column of the matrix always
reproduces, so the matrix demonstrates the signature, its value is in the
run-only material it carries, and the stub's handler-install record is what tells
the two candidate mechanisms apart.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence — the delay-point matrix, the pre-fix capture, the
mutation transcript, the suite counts — is committed as pasted output, and each
story measures its own baseline because a prompt slice cut at a phase heading
cannot read another story's.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The boundary test measures the boundary, not the host

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (trap 6, trap 7) Measure the baseline in **this** worktree: run
      `uv run pytest -q` and record `passed` and `skipped`, never the warning
      count, then run `uv run pytest tests/test_us4_boundary.py -k hanging_agent
      -v` and confirm from its own line that
      `test_hanging_agent_is_killed_at_deadline_with_no_survivors` was
      **selected** rather than skipped — the `-q` summary cannot tell you, since
      it names no passing or skipped test. If it skips, `/usr/bin/bwrap`
      (`factory/workgraph/adapter.py:334`) is missing or not executable
      (`tests/test_us4_boundary.py:165` — `_bwrap_available`,
      `tests/test_us4_boundary.py:209` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`):
      **stop, report blocked, and paste the skip line**. Do not derive, estimate
      or reconstruct any transcript from the stub's source — every outcome below
      is predictable on paper (trap 12), which is exactly why a reconstructed one
      is worthless. Do not carry forward any number from spec.md, plan.md or the
      evidence file.
- [ ] T002 [US1] (FR-002, FR-008, trap 5) Add the delay knob to the stub: one new
      `Control` field naming a start-up point plus a delay, added to the dataclass
      (`tests/stub_agent.py:139` — `Control`) **and** to `as_dict`
      (`tests/stub_agent.py:167` — `as_dict`), which is written out field by field
      so an omission there round-trips as the default. Honour it inside
      `tests/stub_agent.py:385` — `main` at the points the plan's start-up table
      lists, and have the stub echo the point and delay it actually applied into
      the launch's own record directory through
      `tests/stub_agent.py:305` — `write`, so a transcript can quote a file the
      run itself produced and an unknobbed run is distinguishable from a knobbed
      one. Write the echo **before** the delay sleeps, and only at points from
      the record-directory claim (`tests/stub_agent.py:390` — `main`) onward: the
      knob is read at `tests/stub_agent.py:389` — `main` so nothing earlier can
      be delayed, and a delay longer than the deadline kills the stub where it
      stands, so an echo written after the sleep is never written. Model the
      field on `ignore_sigterm`
      (`tests/stub_agent.py:152` — `Control`), which is the knob mechanism that
      already exists. Nothing under `factory/` may read it (FR-008).
- [ ] T003 [US1] (spec US1-S6, FR-002, trap 12) Make the stub record the moment it
      installs its SIGTERM handler — a durable file written immediately after
      `tests/stub_agent.py:414` — `main`, read back the way
      `tests/stub_agent.py:248` — `signals` reads the signal log. This is the only
      thing that separates "the handler was never installed" from "the handler was
      installed and no catchable TERM arrived", and both produce `signals=[]`.
- [ ] T004 [US1] (spec US1-S2, FR-002, trap 8, trap 12) **Demonstrate the
      signature before fixing anything.** Run the affected test once per
      **knobbable** start-up point in the plan's table — steps 3 through 8, the
      range the stub can echo from — with a delay longer than the attempt's
      deadline, at fan-out 1 on an idle host, with `PYTHONDONTWRITEBYTECODE=1`.
      Capture for each point, from the run itself and not from any document: the
      invocation, that run's own `pytest` summary line, and the contents of
      T002's knob echo from that run's record directory — and, for every point
      whose run fails, the failure exactly as `pytest` printed it, which carries
      that run's `tmp_path`. Each point produces one of **four** outcomes:
      `LookupError` from `last_invocation`
      (`tests/stub_agent.py:287` — `last_invocation`), `FileNotFoundError` from
      `invocations` (`tests/stub_agent.py:278` — `invocations`), the captured
      `SIGTERM not delivered; signals=[]`, or a pass. A point delayed after the handler
      installation passes, so that row has a summary line and an echo and no
      failure — do not manufacture one. Exactly one point yields the third, and the stub's source
      says which before you run it — that is the point of trap 12, and it is why
      the captured material and not the verdict is what makes this evidence.
- [ ] T005 [US1] (spec US1-S2, FR-002, trap 12) Commit the matrix as
      `specs/058-a-verdict-is-a-fact-about-the-code/evidence/delay-point-matrix.txt`
      — there is no top-level `evidence/` in this repository, and a diff that
      creates one is wrong — carrying, per point, the items T004 captured rather
      than a prose verdict: the invocation, the run's own summary line, the knob
      echo the stub wrote, and — for each point that fails — the failure as
      `pytest` printed it including that run's `tmp_path`, with the passing point
      saying so in place of a failure. Paste the failure's run-only half verbatim
      — the argument header with that run's `tmp_path`, every `E` line and the
      `AssertionError` location line — and elide the echoed test source with an
      ellipsis; a whole entry is fifty lines
      (`specs/058-a-verdict-is-a-fact-about-the-code/evidence/055-us1-attempt1-gate.txt:70-119`)
      and forty-five of them are source this repository already holds (Sizing).
      Commit the reproducing run alone as
      `specs/058-a-verdict-is-a-fact-about-the-code/evidence/pre-fix-under-knob.txt`
      in the same form. Write in the matrix, in your own words, that the
      reproducing column demonstrates the captured signature and does **not**
      identify what fired in the wild, and name the two mechanisms T003's record
      distinguishes. Hold the matrix to a hundred and twenty lines and the single
      capture to sixty (Sizing).
- [ ] T006 [P] [US1] (spec US1-S1, FR-001, FR-002) Write the regression case
      FIRST: with the knob set at the point T005's matrix names and a delay
      longer than the deadline, the test reports no boundary defect. It must fail
      on today's tree — that is the same run T005 captured — and the test itself
      must set the knob, so a diff that added the knob without moving what races
      cannot pass it.
- [ ] T007 [P] [US1] (spec US1-S6, FR-002, trap 12) Write the discriminator case
      FIRST: given a run that recorded no signal, the failure message names which
      of the two mechanisms produced it, by reading T003's handler-install record.
      Drive **both** states — record absent, and record present with an empty
      signal log — and assert on both messages. Today's message says only
      `SIGTERM not delivered; signals=[]` — must fail.
- [ ] T008 [P] [US1] (spec US1-S5, FR-004, trap 2) Write the bounded-wait case
      FIRST: every wait the test performs for another process's state raises at
      its own deadline naming the condition and the **elapsed** time. Drive it
      against a condition that never becomes true and assert on the message. The
      existing `wait_until` (`tests/test_us4_boundary.py:146` — `wait_until`)
      names the condition and the bound but not the elapsed wait — must fail.
- [ ] T009 [P] [US1] (spec US1-S3, FR-001, trap 4, trap 8) Write the
      still-sensitive case FIRST: with the boundary genuinely broken — a leaked
      namespaced child, or a deadline that does not terminate the agent — the
      fixed test goes **red**. Prove it by mutation, purging `__pycache__`
      between mutants, and keep the transcript for T013.

### Implementation for this story

- [ ] T010 [US1] (spec US1-S4, FR-001, FR-003, trap 2, trap 3, trap 12) Fix the
      synchronisation until T006, T007, T008 and T009 pass. The fix lives in
      `tests/stub_agent.py` or in what `tests/test_us4_boundary.py:202` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors` observes —
      never in production code, and never as "wait before the clock starts",
      which trap 3 shows is inexpressible here. The stub's own ordering is the
      candidate the evidence points at, since `on_term` needs only `recorder`
      (`tests/stub_agent.py:390` — `main`) and `control`
      (`tests/stub_agent.py:389` — `main`); demonstrate it rather than assume it.
      Do **not** delete, weaken, retry or mark any assertion: the termination
      classification
      (`tests/test_us4_boundary.py:230` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`), the SIGTERM
      check (`tests/test_us4_boundary.py:236-238`) and the two survivor checks
      (`tests/test_us4_boundary.py:245-251`) all survive.
- [ ] T011 [US1] (spec US1-S5, FR-004, trap 2, trap 13) Convert the reap window at
      `tests/test_us4_boundary.py:241` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors` to a bounded
      wait on the survivor condition, and add elapsed-time reporting to this
      module's `wait_until` (`tests/test_us4_boundary.py:146` — `wait_until`).
      That body becomes the one US2 promotes, so leave it in the shape you want
      shared. The reap window is not what fired, and it is a fixed sleep gating
      an assertion about another process's state inside the test FR-004 governs,
      so it is US1's to convert — not US2's, whatever an earlier draft said.

### Verification for this story

- [ ] T012 [US1] (spec US1-S7, FR-008, trap 5) Paste, as committed evidence,
      `git diff --name-only` for this story showing no path under `factory/`, and
      a search of `factory/` for the knob's field name returning nothing. FR-008
      is proven from this diff rather than by a guard, because nothing under
      `factory/` names the knob before this story or after it, so a guard for it
      cannot be written red-first.
- [ ] T013 [US1] (spec US1-S3, spec US1-S4, FR-003, trap 6) Paste, as committed
      evidence, the mutation transcript from T009 — the mutant, the red run, and
      `git status --porcelain` empty after restoring — together with the
      post-change `uv run pytest -q` summary showing `skipped` unchanged from the
      baseline **you** measured in T001 and `passed` risen by exactly the tests
      this story commits, plus a `uv run pytest -q -rs` skip report and a
      targeted `uv run pytest tests/test_us4_boundary.py -k hanging_agent -v` run
      naming each committed test and showing the affected test selected — the
      `-q` summary alone names no test. Name in the PR body every assertion the
      diff leaves untouched.

---

## Phase 2: User Story 2 — Every test that launches the stub waits for it the same way

### Tests for this story (write FIRST, must fail)

- [ ] T014 [US2] (spec US2-S2, FR-005) Write the helper's own cases FIRST: it
      returns when the condition becomes true; it raises at its bounded deadline
      when the condition never does; the failure names the condition and the
      elapsed wait. Call the helper directly — a helper proven only through the
      tests that use it is a helper whose failure path is untested — must fail.
- [ ] T015 [P] [US2] (spec US2-S1, FR-006, trap 10) Write the census FIRST: a test
      that asserts both that the shared module T017 creates is the **sole**
      definer of `wait_until` and `stub_is_up` under `tests/` — one definition
      apiece there, zero in every other module — **and** that the list of modules
      importing the shared ones is non-empty and contains `tests/test_adapter.py`,
      `tests/test_agent_activities.py` and `tests/test_us1_detector.py` by name.
      Match the two names **exactly**, with `ast` rather than as text, on the
      `tests/test_123_no_fixture_pins_the_builder.py:445` — `test_no_fixture_leases_a_virtual_key_against_a_registry_persona`
      precedent: the tree holds three same-prefix definitions —
      `tests/test_escalation_workflow.py:300` — `wait_until_waiting`,
      `tests/test_escalation_workflow.py:319` — `wait_until_settled` and
      `tests/test_110_us1_demo_first_boot.py:193` — `_wait_until` — in modules
      this story may not edit and for which FR-006 grants no exemption, so a text
      matcher would refuse them and leave you inventing the self-exemption trap 10
      forbids.
      The sole-definer form is deliberate: "no module under `tests/` defines its
      own `wait_until`" is false the moment the promotion lands, since the shared
      module is itself under `tests/`, and an unstated self-exemption is a census
      a judge can refuse (trap 10). Bind the non-vacuity half to that named list,
      not to the files the scan opened — a scan satisfies "I read some files" on
      every possible diff. Copy the shape from
      `tests/test_final_sweep.py:684` — `test_the_source_sweep_actually_read_the_component`.
      A census that passes by matching nothing is the failure this task exists to
      exclude — must fail.

### Implementation for this story

- [ ] T016 [US2] (spec US2-S4, FR-005, trap 5, trap 13) Re-read and diff all five
      `wait_until` bodies before touching anything — US1 has landed by now and has
      mutated `tests/test_us4_boundary.py:146` — `wait_until`, which is the body
      FR-005 says to promote. Paste the two variants side by side in the diff and
      state which was promoted and why: variant A
      (`tests/test_us3_boundary.py:147` — `wait_until`,
      `tests/test_us1_detector.py:175` — `wait_until`) reads the loop clock,
      variant B (`tests/test_adapter.py:280` — `wait_until`,
      `tests/test_agent_activities.py:396` — `wait_until`) reads
      `time.monotonic()` and carries the docstring, and both bound at 20 seconds
      (`PATIENCE_S` is `20.0` at `tests/test_adapter.py:146` and at
      `tests/test_agent_activities.py:190`, the same as variant A's literal).
      Swapping the clock under five live call sites is a decision to record, not
      a deletion side effect.
- [ ] T017 [US2] (FR-005) Create the shared module under `tests/` — a new file
      beside the nine non-`test_` support modules already there, imported as
      `from tests.<module> import wait_until, stub_is_up` the way **twelve**
      modules already import `tests.stub_agent`
      (`grep -rl 'tests\.stub_agent' tests/*.py`; nineteen paths match repo-wide
      and seven are stale worktree copies). FR-005 excludes two homes by name and
      both exclusions are load-bearing. It must **not** be `tests/stub_agent.py`:
      that file is the executable the adapter launches
      (`tests/stub_agent.py:385` — `main`), it imports no `asyncio` today
      (`tests/stub_agent.py:56-65`), and adding it costs a measured 18-26 ms on
      every stub launch inside the exact start-up window US1 just fixed — trap 5.
      And it must **not** be `tests/conftest.py`, which is 840 lines and
      auto-loaded into every session — note that fifteen modules do import
      symbols from conftest by name, so if you measure the tree looking for a
      reason to reject it, that is not the reason; the size and the auto-load
      are.
      Move the promoted `wait_until` and one `stub_is_up` there, giving
      `stub_is_up` a signature that serves both existing shapes: the globbing one
      (`tests/test_adapter.py:292` — `stub_is_up`,
      `tests/test_agent_activities.py:408` — `stub_is_up`) and the per-attempt one
      (`tests/test_us1_detector.py:198` — `stub_is_up`).
- [ ] T018 [US2] (spec US2-S1, FR-005, FR-006) Delete all five `wait_until`
      definitions and all three `stub_is_up` definitions, and point every live
      call site at the shared module by editing each module's import block —
      `tests/test_adapter.py`, `tests/test_agent_activities.py`,
      `tests/test_us1_detector.py` for the eleven live calls, seven of which poll
      `stub_is_up` and four of which poll something else, and
      `tests/test_us4_boundary.py` for the wait US1 landed.
      `tests/test_us3_boundary.py` loses a definition it never called and gains
      nothing. Do **not** restructure any launch: every one in both boundary
      suites is a single awaited `run_attempt` with no seam (trap 3), and the
      launch shape is out of scope by name in `### What this spec is not`.
- [ ] T019 [US2] (FR-009, trap 6, trap 7) Measure the baseline in **this**
      worktree before your first change — `uv run pytest -q` for the counts and
      `uv run pytest tests/test_us4_boundary.py -k hanging_agent -v` for the
      selection — and re-run both afterwards, comparing against the numbers you
      measured here and against no number carried in from another phase, which
      your prompt slice does not contain. `skipped` must be unchanged, `passed`
      risen by exactly the tests this story commits, and the affected test still
      selected. If the wall clock has grown, tighten the readiness deadline —
      never the assertions.

### Verification for this story

- [ ] T020 [US2] (spec US2-S3, FR-006, FR-009) Paste, as committed evidence, the
      before-and-after `uv run pytest -q` summary lines from T019, a
      `uv run pytest -q -rs` skip report, a targeted
      `uv run pytest tests/test_us4_boundary.py -k hanging_agent -v` run showing
      `test_hanging_agent_is_killed_at_deadline_with_no_survivors` selected
      rather than skipped, each newly committed test named by a run that prints
      test ids, and the census test's own output listing the modules it examined.
      The `-q` summary carries the counts and nothing else — the names and the
      selection come from the other two invocations.

---

## Phase 3: User Story 3 — The pattern cannot come back

### Tests for this story (write FIRST, must fail)

- [ ] T021 [US3] (spec US3-S2, FR-007, trap 11) Write the catch case FIRST,
      against **synthetic** source the test itself supplies: a fixed sleep
      standing between launching a process and an assertion about that process's
      state is refused, and the refusal names the file and the line. Copy the
      driven-against-synthetic-source shape from
      `tests/test_123_no_fixture_pins_the_builder.py:510` — `test_the_guard_catches_the_pin_this_story_removes` — must fail.
- [ ] T022 [P] [US3] (spec US3-S3, FR-007, trap 11) Write the false-positive case
      FIRST, also against synthetic source: a fixed sleep that only yields the
      event loop and gates no assertion about another process passes. Count the
      population yourself with a matcher you write down, and say which matcher
      produced the number: at 602a92c a text scan of `asyncio.sleep(` plus
      `time.sleep(` over `tests/*.py` counts 72 call sites across 29 modules
      while an `ast` walk counts 65 across 27, the gap being string literals such
      as `tests/test_us4_boundary.py:250` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`.
      Most are legitimate, including the one inside the readiness helper US2
      landed — at 602a92c it sat at
      `tests/test_us4_boundary.py:153` — `wait_until`, and by the time this story
      dispatches that definition is deleted and the sleep lives in the shared
      module. A guard that bans the
      construct outright gets deleted by the next person who needs one. The
      exemption precedent is `tests/test_final_sweep.py:625` — `test_the_compose_exemption_buys_exactly_one_compound_and_no_more` — must
      fail.
- [ ] T023 [P] [US3] (spec US3-S1, FR-007, trap 10, trap 14) Write the non-vacuity
      case FIRST, bound to a literal file list rather than to a phrase: the
      guard's own population is every module under `tests/`, and the companion
      asserts that list contains `tests/test_us4_boundary.py`,
      `tests/test_us3_boundary.py`, `tests/test_adapter.py`,
      `tests/test_agent_activities.py` and `tests/test_us1_detector.py` by name,
      so a sweep over an empty list cannot pass as a green tick — must fail.
- [ ] T024 [P] [US3] (spec US3-S4, FR-007, trap 14) Write the exemption companion
      FIRST: every entry in the guard module's named exemption list still matches
      the raw matcher — a dead exemption is deleted, not carried — and the
      exemptions leave T021's synthetic source still refused. Model it on
      `tests/test_final_sweep.py:625` — `test_the_compose_exemption_buys_exactly_one_compound_and_no_more`,
      where the exemption is proven to remove a false positive and not the
      guard — must fail.

### Implementation for this story

- [ ] T025 [US3] (spec US3-S1, FR-007, trap 14) Implement the guard in its own new
      test module on the pattern of
      `tests/test_123_no_fixture_pins_the_builder.py:445` — `test_no_fixture_leases_a_virtual_key_against_a_registry_persona`, which
      reads this repository's own test source with `ast`. Its population is
      **every `*.py` file under `tests/`, walked recursively** — 335 files at
      602a92c, the reading the precedent itself uses — and not the two boundary
      suites: US1 converts
      `tests/test_us4_boundary.py:241` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
      and US2 deletes both modules' `wait_until` definitions, so by the time this
      story dispatches those two files contain no fixed sleep at all and a guard
      scoped to them would pass by matching nothing. It does **not** go into
      `tests/test_final_sweep.py`: that file's sweeps are parametrized over
      `COMPONENT_MODULES` (`tests/test_final_sweep.py:104`), production modules
      under `factory/` and never tests. Where the matcher refuses a legitimate
      call site, add a named entry — file, line, one-line reason — to this
      module's own exemption list; never edit the module it misjudged, which
      Sizing forbids. Expect that list to be short and not empty: seven call
      sites match the banned shape by hand at 602a92c — three in
      `tests/test_engine_identity.py`, two in
      `tests/test_110_us1_demo_first_boot.py`, one in `tests/test_interpreter.py`
      and the reap window US1 converts — all but the last in modules you may not
      edit, so they are grandfathered by name rather than misclassified (trap 14).
      Run until T021, T022, T023 and T024 pass.

### Verification for this story

- [ ] T026 [US3] (FR-007, trap 6, trap 7) Paste, as committed evidence, the
      guard's output over every module under `tests/` on the converted tree, its
      output on each synthetic fixture, the exemption list with its reasons, and
      the before-and-after `uv run pytest -q` summaries measured in **this**
      worktree — `skipped` unchanged and `passed` risen by exactly the tests this
      story commits — beside a targeted
      `uv run pytest tests/test_us4_boundary.py -k hanging_agent -v` run showing
      the affected test still selected. Measure the baseline here; the number in
      another story's phase is not in your prompt.

---

## Verification

- [ ] T027 Operator: confirm the declared `test` gate is green on the landed
      tree, then re-run the affected test alone twenty times on an idle host as
      the control, and once under a deliberate second full suite on the same host
      as the discriminator. The second run is the one a node cannot perform.
- [ ] T028 Operator: read
      `specs/058-a-verdict-is-a-fact-about-the-code/evidence/delay-point-matrix.txt`
      and check first that each point carries run-only material — a `pytest`
      summary line, a failure printed by `pytest` quoting that run's own
      `tmp_path`, and the stub's knob echo — rather than four prose verdicts,
      which this spec's own pages let anyone compose; then that it records all
      four outcomes; then that it says the reproducing column demonstrates the
      signature rather than identifying the mechanism; and only then that the
      landed diff moved the window it names. Checking the last alone confirms a
      tautology — one column always reproduces (trap 12). Then force a
      `signals=[]` outcome by hand and confirm the failure message names which of
      the two mechanisms it found.
- [ ] T029 Operator: dispatch the next epic at
      `ergane build start --max-concurrent-nodes 3` and watch for a gate failure
      attributable to a neighbour, and separately run `scripts/gate-commit` on a
      comment-only change while a node gate is in flight — the configuration
      occurrence 4 fired under, at fan-out one. Both are observations over time,
      not story criteria.
- [ ] T030 Operator: resolve `ci/flaky-concurrency-test-is-a-random-epic-killer`
      only once T027, T028 and T029 hold — and not before. The row was resolved
      once already, against `specs/025-ci-red-recovery`, and regressed. Do **not**
      resolve `ci/the-deadline-boundary-test-fails-intermittently-in-the-full-suite`
      under this spec: its skip-asymmetry half is untouched here, and closing it
      would credit a half-fix.
