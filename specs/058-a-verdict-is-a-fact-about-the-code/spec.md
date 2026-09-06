---
state: draft
depends_on_landed: [011-agent-sandbox, 027-gate-suite-fake-time]
fixes:
  - ci/flaky-concurrency-test-is-a-random-epic-killer
# Drafted 2026-08-18 ~6:45 PM CT by an operator session, after the operator asked
# what level of fan-out the remaining specs could take. The answer was "one",
# and this spec is the reason. `ergane build start --max-concurrent-nodes 2` has
# a measured, recurring tax: a boundary test that loses a race under a
# neighbour's CPU load, fails the gate, and burns a whole attempt on code that
# was never at fault. It has fired three times, most recently 2026-08-18 06:47
# CT on 055/us1.
#
# Scaffolded by `ergane findings promote` from
# `ci/flaky-concurrency-test-is-a-random-epic-killer` (critical, regressed,
# 3 occurrences, first seen 2026-08-17).
#
# ONE CORRECTION IS BAKED INTO THIS SPEC, and it matters because the wrong
# version was said out loud first. The mechanism was initially read from the
# source as the fixed 0.2s reap window at `tests/test_us4_boundary.py:241`. The
# captured gate output says otherwise: the failing assertion is at `:236` and
# reads `SIGTERM not delivered; signals=[]`, while `result.termination ==
# "timeout"` passed on the line above it. The deadline machinery worked. What
# was not observed was the stub *recording* the signal. Anyone fixing the reap
# window will have fixed nothing, so the reproduction is committed under
# `evidence/` rather than described.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c.
#
# THE SECOND DIAGNOSIS IS FALSIFIED TOO, BY THE SAME EVIDENCE FILE. The drafted
# plan's leading candidate was "SIGTERM arrives before the stub has drained
# stdin, so the handler at `tests/stub_agent.py:414` was never installed". That
# cannot be what happened. `invocations` reads `stdin.txt` unconditionally
# (`tests/stub_agent.py:278`), so a stub that died before `:407` makes
# `last_invocation` raise `FileNotFoundError`; the captured run raises
# `AssertionError` on the *next* line instead, which means every record file
# including `stdin.txt` was on disk. The drain finished. What is left between
# `:407` and `:414` is a closure definition and one call, and a signal landing
# there four times is not credible. The mechanism is therefore NOT established,
# and this refinement replaces "confirm which of two" with a delay-point matrix
# that names it before anything is fixed. Third candidate, newly written down:
# TERM reaches bwrap and the stub through one process group, and
# `--unshare-pid --die-with-parent` (`factory/workgraph/adapter.py:621`) takes
# the namespace down with SIGKILL when bwrap exits — the stub can lose the race
# to run its own Python handler without ever having been slow to boot.
#
# THE DEFECT CHANGED SHAPE AFTER DRAFTING, AND FAN-OUT IS NOT THE CONDITION.
# Occurrence 4 (2026-08-25, in the ledger row's own notes) fired at
# `--max-concurrent-nodes` ONE: an operator `scripts/gate-commit` run against a
# frontmatter-only change, concurrent with 105/us1's node gate. So the "run at
# fan-out 1" mitigation this spec was drafted under does not close it, and the
# drafted SC-006 — dispatch at fan-out 3 and see no neighbour-attributable
# failure — was both unprovable from a diff and aimed at the wrong variable. It
# is gone from the requirements and recorded as an operator observation in
# plan.md instead.
#
# ANCHOR ROT, MEASURED. Sixteen distinct citations re-read. `tests/stub_agent.py`
# and `tests/test_us4_boundary.py` have not changed since 2026-08-15, so their
# drift was authoring error, not movement: `:212` never was the adapter
# construction (that is `:224`), `:225` never was `timeout_s=3` (`:226`), and
# `:229` is blank (the termination assertion is `:230`). Validate refused on the
# blank one alone. The production anchors did move: `DEFAULT_GRACE_S` 99 to 127,
# `DEFAULT_GATE_CONCURRENCY` 74-87 to 99-110, `DIFF_INPUT_LIMIT` 42 to 47. Four
# bare `stub_agent.py:NN` cites now carry the `tests/` prefix and four
# unanchorable bare `:NN` cites carry full paths; every anchor that means a
# symbol is written in the tier-checked form so the next drift is machine-caught.
#
# ONE KEY DECLARED, ONE DELIBERATELY NOT. `fixes:` now names the source finding,
# whose FR set this spec covers whole. It does NOT name
# `ci/the-deadline-boundary-test-fails-intermittently-in-the-full-suite` (open,
# 3 occurrences, last 2026-08-29, epic-089/us3, one full attempt): that row
# carries a second claim this spec does not touch — the agent's own run SKIPPED
# the test while its gate RAN and failed it, a bwrap-availability asymmetry
# between an agent's sandbox and its gate. Declaring it would close a half-fixed
# row. `verify/gate-flakiness-is-not-confined-to-the-known-deadline-test` is a
# different test in a different subsystem and is out of scope by name.
#
# WHAT ELSE CHANGED IN THE DOCUMENTS. `wait_until` already exists, byte-identical,
# in three test modules, so US2 promotes a duplicate rather than inventing a
# helper; `test_final_sweep.py` sweeps production modules only
# (`tests/test_final_sweep.py:104`), so US3's guard over *test* source belongs in
# its own module on `tests/test_123_no_fixture_pins_the_builder.py`'s pattern;
# FR-004 is US1's, so US1 — not US2 — converts the reap sleep inside its own
# test; the fixed-sleep population is 69 call sites across 29 files, not 37
# across 15. Story count, story keys and every FR key are unchanged, so the
# compiled `workgraph.json` beside this file still carries the right
# `requirement_keys`.
#
# NOT IN SCOPE. Bounding agent tool calls under the gate semaphore; raising any
# concurrency dial; the two open landing-poll criticals; the skip asymmetry named
# above; any second flaky test. A repository that never runs the boundary suites
# behaves identically after this spec lands.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04) against ergane-buildout at 602a92c,
# after an adversarial review refuted the refinement above. Six defect classes,
# every one a claim about the tree that re-reading the tree falsified. The
# readiness convention this spec called absent already exists — `stub_is_up` is
# defined in three modules and eleven live `wait_until` calls poll it — so the
# gap chain and US2 are restated against it. `wait_until` is defined FIVE times
# in TWO variants, not three byte-identically, so FR-005 and the deletion list
# name the real population. The promoted helper is moved out of
# `tests/stub_agent.py`: that file is the executable the adapter launches, and an
# `async def` there costs 18-26 ms of `asyncio` import on every stub boot, inside
# the exact start-up window US1 exists to characterise. US2's "convert every
# racing launch" is retired — every launch in both boundary suites is a single
# awaited `run_attempt` with no seam, which is trap 3's own constraint left
# unreconciled — and the honest work is unifying the helper and its predicate.
# FR-002 no longer claims the delay-point matrix identifies the wild mechanism,
# because its outcome at every point is derivable from `tests/stub_agent.py:278`
# and `tests/stub_agent.py:414` without running it; the stub now records handler
# installation instead, so a `signals=[]` failure says which of the two
# mechanisms produced it. And FR-009 no longer demands a `passed` count that
# matches, which no story adding committed tests could ever produce.
#
# CORRECTIONS TO THE PARAGRAPHS ABOVE, WHICH STAY AS WRITTEN. "byte-identical, in
# three test modules" is wrong on both counts. "69 fixed-sleep call sites across
# 29 test modules" measured 72 across 29 at 602a92c, by `asyncio.sleep(` plus
# `time.sleep(` over `tests/*.py`. FR-008 is now proven from US1's own diff
# rather than by a guard in US3's phase, where it could not be written red-first
# because nothing under `factory/` names the knob before or after this spec. No
# FR key, story key or `implements` list changed, so the compiled
# `workgraph.json` beside this file still carries the right `requirement_keys`.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), second adversarial round, against
# ergane-buildout at 602a92c. Eight defects, three blocking, every one about
# what a diff can prove rather than about where a line sits. FR-002 and US1-S2
# now demand artifacts only a run can produce — each point's own `pytest`
# summary line, the failure as `pytest` printed it quoting that run's own
# `tmp_path`, and the knob echo the stub writes into that run's record directory
# — because trap 12's own argument (every outcome is derivable from the stub's
# source) made the drafted transcript composable out of this spec's quoted text.
# US1 now names its way out of the bwrap skip it only detected: no
# `/usr/bin/bwrap` in the worktree means report blocked with the skip line
# pasted, never derive a transcript. FR-007's population was the undefined
# phrase "the guarded suites" and is now every module under `tests/`, with a
# named exemption constant and a new US3-S4 keeping the exemptions load-bearing.
# FR-006's census exempts the one shared module FR-005 creates, which a literal
# census would have refused. FR-009 names the invocation that can carry its
# evidence, because the declared gate's `uv run pytest -q` prints counts and
# names no passing or skipped test. The two new transcripts carry their full
# repository-relative path under this spec's own `evidence/`. US2's and US3's
# baselines are measured in their own worktrees, because a prompt slice cut at a
# phase heading cannot see US1's. And seven, not eight, of the eleven live
# `wait_until` calls key on `stub_is_up` — `tests/test_adapter.py:832` waits on
# `not pid_alive(grandchild)`. No FR key, story key or `implements` list
# changed; US3 gains a fourth scenario and no story is split.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), third adversarial round, against
# ergane-buildout at 602a92c. Two blocking and five smaller, and both blocking
# ones were claims this trio made about a tree that contradicts them. plan.md
# rejected `tests/conftest.py` as the shared module's home on the ground that
# nothing imports a symbol from it by name; fifteen modules do, so the argument
# is replaced by the measured convention — nine non-`test_` support modules
# under `tests/` — and FR-005 now names both exclusions itself instead of
# leaving them to a task line. FR-002 and US1-S2 demanded a `pytest` failure and
# a knob echo at every start-up point, and three points cannot produce both: the
# knob is read at `tests/stub_agent.py:389` — `main`, the echo has nowhere to go
# until `tests/stub_agent.py:390` — `main`, and the point after the handler
# installation passes. Both are restated over the knobbable points with a
# per-outcome artifact set. FR-007's population is now one reading — every
# `*.py` file under `tests/`, walked recursively, which is what the precedent
# walks — FR-006's census matches its two names exactly so `wait_until_waiting`,
# `wait_until_settled` and `_wait_until` fall outside it by construction, and
# US3-S4 says what size exemption list to expect, because seven call sites match
# the banned shape today in modules US3 may not edit. No FR key, story key or
# `implements` list changed.
---

# Feature Specification: a verdict is a fact about the code

**Created**: 2026-08-18

**Depends on**: `011-agent-sandbox` and `027-gate-suite-fake-time`, both landed.

## The gap, stated precisely

One test in this repository returns FAIL for a reason that is not a fact about
the code under test, and the factory pays a whole attempt for it each time. Four
occurrences are in the ledger, the most recent after this spec was drafted.

1. `tests/test_us4_boundary.py:202` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
   drives one attempt at `timeout_s=3` (`tests/test_us4_boundary.py:226` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`) against an
   adapter built with `grace_s=1.0` (`tests/test_us4_boundary.py:224` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`) — a tenth of
   production's `DEFAULT_GRACE_S = 10.0` (`factory/workgraph/adapter.py:127`),
   tightened purely to keep the test fast.
2. At the deadline the adapter signals the whole process group and then kills it:
   `factory/workgraph/adapter.py:1461` — `_reclaim` sends SIGTERM,
   `factory/workgraph/adapter.py:1463` — `_reclaim` waits `grace_s`, and
   `factory/workgraph/adapter.py:1464` — `_reclaim` sends SIGKILL.
3. The test then asserts that the stub recorded a TERM
   (`tests/test_us4_boundary.py:236-238`). `Invocation.signals` returns an empty
   list when the signals file does not exist (`tests/stub_agent.py:256` — `signals`), so `signals=[]` means the stub's Python handler never ran — not
   that it ran and recorded nothing.
4. The stub installs that handler at `tests/stub_agent.py:414` — `main`, after
   it has drained stdin at `tests/stub_agent.py:407` — `main`. Its own source
   names the readiness file a test should poll for
   (`tests/stub_agent.py:405-406`). **This test polls for nothing, and it is the
   exception rather than the rule.** Three other modules define exactly that
   poll — `tests/test_adapter.py:292` — `stub_is_up`,
   `tests/test_agent_activities.py:408` — `stub_is_up` and the per-attempt
   `tests/test_us1_detector.py:198` — `stub_is_up` — and of the eleven live
   `wait_until` calls in the tree, seven key on that very file. Neither boundary
   suite has a single one.
5. On 2026-08-18 06:47 CT the assertion failed on node `us1` of epic 055 with
   `signals=[]`, while `result.termination == "timeout"`
   (`tests/test_us4_boundary.py:230` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`) passed on the
   line above it. The whole run is committed at
   `evidence/055-us1-attempt1-gate.txt`. Attempts 2 and 3 passed on
   substantially the same tree.
6. The judge never ran: `output_check` passed, `criteria_drift` was zero, and the
   verdict came from the gate alone. With `max_attempts = 3` one spurious FAIL is
   a third of a story's ladder, which is why the finding is called a random epic
   killer rather than a flake.
7. The factory already names this hazard in its own gate module — *"N nodes'
   gates on one host contend for CPU … a verdict that is not a fact about the
   node's code"* (`factory/verify/gates.py:99-102`) — and bounds gate
   concurrency below node concurrency because of it
   (`factory/verify/gates.py:110`). The bound is on gates. Agents are not inside
   it, and neither is an operator's shell.
8. The convention that would have caught this is not missing from the tree; it
   is scattered across it. `wait_until` is defined **five** times in **two**
   variants: a loop-clock body defaulting to a literal `20.0` at
   `tests/test_us4_boundary.py:146` — `wait_until`,
   `tests/test_us3_boundary.py:147` — `wait_until` and
   `tests/test_us1_detector.py:175` — `wait_until`, and a documented
   `time.monotonic()` body defaulting to `PATIENCE_S` at
   `tests/test_adapter.py:280` — `wait_until` and
   `tests/test_agent_activities.py:396` — `wait_until`. Two of the five are dead:
   neither boundary suite calls its own copy. A convention that is copied rather
   than imported is a convention one module can quietly lack.

**Two things the ledger has learned since this was drafted, both of which change
what may be believed about the mechanism.**

Occurrence 4 fired at `--max-concurrent-nodes` **one**: an operator
`scripts/gate-commit` run on a comment-only change, concurrent with another
epic's node gate on the same host. Fan-out is not the condition; a second suite
on the box is, and an operator gate is one.

And the committed evidence rules out the diagnosis this spec was drafted around.
`invocations` reads `stdin.txt` unconditionally (`tests/stub_agent.py:278` — `invocations`), so a stub killed before `tests/stub_agent.py:407` — `main` makes
`last_invocation` (`tests/stub_agent.py:287` — `last_invocation`) raise rather
than return. The captured failure is an `AssertionError` on the line *after*
that call, so every record file was on disk and the drain had finished. What
remains between the drain and the handler is a closure definition and one call.
**The mechanism is not established, and this spec may not assume one.**

That last sentence has a consequence the previous refinement missed. Because the
stub's own source fixes what every start-up delay produces — no usable record
directory gives `LookupError` from `last_invocation`, a record directory missing
any file `invocations` reads gives `FileNotFoundError`, and only the window
between
`tests/stub_agent.py:407` — `main` and `tests/stub_agent.py:414` — `main` gives
`signals=[]` — a delay-point matrix reproduces the captured *signature* without
identifying the *mechanism*. Two mechanisms produce `signals=[]`: a handler that
was never installed, and a handler that was installed and never invoked because
the namespace collapsed under SIGKILL. Only the stub can tell them apart, and
only if it records which state it reached.

**And a transcript of that matrix is worth exactly what it cost to produce.**
Because every column's outcome is predictable from the source, a matrix written
as four prose verdicts is a document anyone could compose from this page without
running anything — the failing assertion string is quoted three times in this
trio already. So the matrix is specified below as run-only material: each point's
own `pytest` summary line, the knob echo the stub itself wrote into that run's
record directory, and — for each point whose run fails — the failure as `pytest`
printed it carrying that run's own `tmp_path`. The matrix runs over the points
the stub can echo from, which begins where it claims that directory
(`tests/stub_agent.py:390` — `main`), and the last of those points passes and so
carries no failure at all. What makes an experiment evidence is that it could have come out
otherwise; what makes a transcript evidence is that it could not have been
written without the run.

## The rule this spec is asking for

**A test's verdict must be a fact about the code it exercises: a slow host may
not make this test report a boundary defect, and a broken boundary must still
make it fail.**

The four cases, complete:

| the boundary works | the stub is slow to reach its handler | today | this spec |
|---|---|---|---|
| yes | no | pass | pass |
| yes | **yes** | **FAIL: `SIGTERM not delivered; signals=[]`** | pass |
| **no** — a namespaced child outlives the attempt | no | fail | fail |
| **no** | yes | fail, on the wrong assertion | fail, on the survivor assertion |

The bottom two rows are why this cannot be fixed by waiting longer for anything.
A wait generous enough to absorb any scheduling delay is also generous enough to
let a leaked child look reaped, and the row this spec exists to change is the
second one alone.

### What this spec is not

**It is not a change to any concurrency dial.** Nothing here raises
`--max-concurrent-nodes`, and occurrence 4 shows lowering it does not help
either. Whether to fan out remains the operator's choice, made after this lands
rather than by it.

**It is not the gate-semaphore asymmetry.** Gates are bounded
(`factory/verify/gates.py:110`) and agents are not. That is real, larger than
this spec, and a change to `DEFAULT_GATE_CONCURRENCY`'s whole premise.

**It is not a claim about every flaky test.**
`verify/gate-flakiness-is-not-confined-to-the-known-deadline-test` names a
different test in a different subsystem with no deadline in it. Out of scope by
name.

**It is not the skip asymmetry.**
`ci/the-deadline-boundary-test-fails-intermittently-in-the-full-suite`'s third
occurrence records an agent's own run *skipping* this test while its gate *ran*
and failed it. That is a bwrap-availability difference between an agent's
sandbox and its gate, and it is deliberately not declared fixed here. What this
spec does about it is narrower and local: US1 may not proceed on a worktree
where the test skips, and says so as an instruction rather than as a fix.

**It is not a readiness wait wrapped around the boundary suites' launches.**
Every launch in `tests/test_us4_boundary.py` and `tests/test_us3_boundary.py` is
one awaited call — `tests/test_us4_boundary.py:225` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors` and
`tests/test_us3_boundary.py:207` — `test_git_plumbing_succeeds_inside_bwrap_boundary`
are two of the ten — and the deadline clock starts *inside* it
(`factory/workgraph/adapter.py:1144` — `run_attempt`,
`factory/workgraph/adapter.py:1148` — `run_attempt`), so there is no seam at
which the test could wait for readiness first. Restructuring those ten launches
onto `tests/test_adapter.py:979` — `test_a_live_process_group_from_a_previous_run_is_reaped_before_relaunch`'s
`asyncio.create_task` shape would change what those tests measure, and is out of
scope. US2 unifies the helper and the predicate it polls, not the launch shape.

**It is not an observation over time.** "Dispatch at fan-out 3 and see no
neighbour-attributable failure" is what the operator gets out of this, and it is
unprovable from a diff (constitution VIII). It lives in plan.md's operator
verification, never as a story criterion.

## User Scenarios & Testing

### User Story 1 - The boundary test measures the boundary, not the host (Priority: P1)

The test that fired stops depending on how quickly the host scheduled a
subprocess. Its verdict becomes a fact about whether the deadline machinery
terminates an agent and its children — which is what it exists to check — and
nothing else. Two devices make the claim readable rather than asserted. A stub
knob delays one named point in start-up, and the transcript of what each point
produces is committed in the same diff as the fix — but that transcript
demonstrates the captured *signature*, since the stub's own source already fixes
each point's outcome, and this story says so in the transcript rather than
overclaiming. What actually separates the two candidate mechanisms is the stub
recording the moment it installs its handler, so that a `signals=[]` failure
names which of them produced it — here, and on the next recurrence in the wild.

**Why this priority**: it is the whole defect. Everything else in this spec
generalises the fix or guards it.

**Independent Test**: with the stub's delay knob at the point the committed
transcript names, the pre-fix test fails and the fixed test passes — at fan-out
1, on an idle host, deterministically, with no induced load of any kind. This
story cannot be done at all where `/usr/bin/bwrap` is absent: the guard at
`tests/test_us4_boundary.py:209` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
skips the whole test, every measurement below becomes vacuous, and the story
reports blocked with the skip line pasted rather than reconstructing any
transcript from the stub's source.

**Acceptance Scenarios**:

1. **Given** the stub's delay knob set at the start-up point the committed
   transcript names as producing the captured signature, with a delay longer than
   the attempt's deadline, **When** the fixed test runs, **Then** it passes —
   proven by a committed test that sets the knob itself, so a diff that adds the
   knob without moving what races cannot satisfy it.
2. **Given** the knob set in turn at every *knobbable* start-up point the plan's
   table names — the points from the record-directory claim
   (`tests/stub_agent.py:390` — `main`) onward, which are the only ones at which
   the stub can echo the knob it applied before a delay longer than the deadline
   kills it — **When** the pre-fix test is run once per point, **Then** the
   committed transcript pastes, for that point, material no reader of this spec
   could have written without the run: the invocation, that run's own `pytest`
   summary line with its elapsed seconds, and the contents of the knob echo the
   stub wrote into that run's record directory, plus — for every point whose run
   fails — the failure as `pytest` printed it including the run's own `tmp_path`,
   with any point that passes carrying its summary line and echo and saying so
   in place of a failure; covering all four outcomes the stub's own source
   predicts (`LookupError` from `last_invocation`, `FileNotFoundError` from
   `invocations`, the captured `SIGTERM not delivered; signals=[]`, and a pass),
   and stating in its own words that reproducing the third is a demonstration of
   the signature and not an identification of what fired in the wild.
3. **Given** a genuine boundary defect — a namespaced child that outlives the
   attempt, or a deadline that does not terminate the agent — **When** the fixed
   test runs, **Then** it still fails, proven by a mutation transcript pasted
   into the diff showing the mutant, the red run and the restored tree. A test
   that cannot fail is worse than the flake it replaced.
4. **Given** the fixed test, **When** its diff is read, **Then** the termination
   classification, the SIGTERM check and the two survivor checks are all still
   asserted, and the diff contains no skip marker, no `xfail`, no retry loop and
   no widened tolerance on any of them.
5. **Given** the fixed test waiting for another process to reach a state — the
   reap window at `tests/test_us4_boundary.py:241` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors` included —
   **When** that wait expires, **Then** the failure names the condition waited
   for and the elapsed time, proven by a committed test that drives the wait
   against a condition which never becomes true and asserts on the message.
6. **Given** a run in which the stub recorded no signal, **When** the test
   reports it, **Then** the message distinguishes the two mechanisms that produce
   that state — the handler was never installed, or the handler was installed and
   no TERM was ever delivered to it — by reading the marker the stub writes when
   it installs the handler, proven by a committed test that drives both states and
   asserts on both messages.
7. **Given** this story's diff, **When** it is read, **Then** no path under
   `factory/` appears in it and the knob's name appears only under `tests/`,
   proven by pasted `git diff --name-only` output for the story and a pasted
   search of `factory/` for the knob's name returning nothing.

---

### User Story 2 - Every test that launches the stub waits for it the same way (Priority: P1)

The readiness wait becomes one shared helper, its predicate becomes one shared
function, and every module that polls for the stub imports both. There is no
helper to invent, but there is more than one to reconcile: `wait_until` is
defined five times in two variants — the loop-clock body at
`tests/test_us4_boundary.py:146` — `wait_until`,
`tests/test_us3_boundary.py:147` — `wait_until` and
`tests/test_us1_detector.py:175` — `wait_until`, and the documented
`time.monotonic()` body at `tests/test_adapter.py:280` — `wait_until` and
`tests/test_agent_activities.py:396` — `wait_until` — while the predicate they
poll, `stub_is_up`, is defined three times in two signatures
(`tests/test_adapter.py:292` — `stub_is_up`,
`tests/test_agent_activities.py:408` — `stub_is_up`, and the per-attempt
`tests/test_us1_detector.py:198` — `stub_is_up`). This story lands one module
both come from, deletes all eight definitions, and points every live call site at
it.

**Why this priority**: P1 because the convention the failing test lacked already
exists five times over, and a convention that is copied rather than imported is
exactly how one module comes to lack it. Unifying it is what stops the next
module being written without it.

**Independent Test**: a census test asserts that the shared module is the only
module under `tests/` defining `wait_until` or `stub_is_up`, and that the list of
modules importing the shared ones is non-empty and contains each module the plan
names; the suites stay green.

**Acceptance Scenarios**:

1. **Given** the tree after the promotion, **When** the census test runs,
   **Then** it asserts both that the shared module FR-005 names is the *only*
   module under `tests/` defining `wait_until` or `stub_is_up` — matched by
   those exact names, so the same-prefix
   `tests/test_escalation_workflow.py:300` — `wait_until_waiting`,
   `tests/test_escalation_workflow.py:319` — `wait_until_settled` and
   `tests/test_110_us1_demo_first_boot.py:193` — `_wait_until` fall outside the
   population by construction rather than being exempted out of it, and every
   other module's count is zero while the shared module's is one apiece —
   **and** that
   the list of modules importing the shared ones is non-empty and contains
   `tests/test_adapter.py`, `tests/test_agent_activities.py` and
   `tests/test_us1_detector.py` by name. A census that passes by matching
   nothing is the failure this scenario exists to exclude, and only the pair of
   assertions can fail a diff that shipped an empty matcher.
2. **Given** the shared helper, **When** the condition it waits on never becomes
   true, **Then** it raises at its own bounded deadline naming the condition and
   the elapsed time, proven by a committed test that calls it directly — a helper
   proven only through the tests that use it is a helper whose failure path is
   untested, and a helper that hangs has replaced a flaky failure with a worse
   one.
3. **Given** the converted suites, **When** the full suite is run before and
   after **in this story's own worktree**, **Then** the pasted `skipped` counts
   are equal, the pasted `passed` count has risen by exactly the number of tests
   this story commits with each of them named in the paste, and the paste shows
   `test_hanging_agent_is_killed_at_deadline_with_no_survivors` selected rather
   than skipped — the naming coming from a run that prints test ids, since the
   declared `test` gate's own `uv run pytest -q` prints counts and names no
   passing or skipped test. A new skip is a hidden test and fails this scenario.
4. **Given** the five `wait_until` bodies as they stand when this story is
   dispatched, **When** the promotion is made, **Then** the diff pastes the two
   variants side by side and states which body was promoted and why, so that
   swapping the clock source under a live call site is a recorded decision rather
   than a side effect of a deletion.

---

### User Story 3 - The pattern cannot come back (Priority: P2)

A mechanical guard reads the source of **every module under `tests/`** and
refuses a new fixed sleep used to wait for another process's state, on the
pattern
`tests/test_123_no_fixture_pins_the_builder.py:445` — `test_no_fixture_leases_a_virtual_key_against_a_registry_persona` already
establishes for a source guard over this repository's tests. The population is
every `*.py` file under `tests/`, walked recursively as that precedent walks it —
the same population FR-006's census uses — and not the two boundary suites alone:
US1 converts the only fixed sleep in either that gates an assertion and US2
deletes both modules' `wait_until` copies, so by the time this story dispatches
those two files hold no fixed sleep at all and a guard scoped to them would match
nothing, which is the failure mode trap 10 exists for.

**Why this priority**: P2 because US1 and US2 deliver the fix. This is what stops
it rotting — the pattern is ordinary, it reads as harmless, and the next person
to write one will not have read this spec.

**Independent Test**: the guard passes over every module under `tests/` on the
converted tree, fails on synthetic source carrying the banned pattern, and passes
on synthetic source carrying a fixed sleep that gates no such assertion.

**Acceptance Scenarios**:

1. **Given** every module under `tests/` on the converted tree, **When** the
   guard runs, **Then** it passes, and a committed companion test asserts the
   guard's own file list contains `tests/test_us4_boundary.py`,
   `tests/test_us3_boundary.py`, `tests/test_adapter.py`,
   `tests/test_agent_activities.py` and `tests/test_us1_detector.py` by name, so
   the guard cannot go quiet when the layout moves.
2. **Given** synthetic source in which a fixed sleep stands between launching a
   process and an assertion about that process's state, **When** the guard runs
   over it, **Then** it fails and names the file and the line — driven against
   source the test itself supplies, so the guard is proven to catch the pattern
   rather than assumed to.
3. **Given** synthetic source in which a fixed sleep only yields the event loop
   and gates no assertion about another process, **When** the guard runs over it,
   **Then** it passes — the guard distinguishes waiting for something from simply
   pausing, and there are seventy-odd fixed-sleep call sites across 29 test
   modules (72 by text and 65 by syntax tree at the sha this spec was repaired
   against; the two matchers disagree because some hits are string literals, and
   the story measures its own) of which most are legitimate, so a guard that
   banned the construct outright would be deleted by the next person who needed
   one.
4. **Given** a call site the guard's matcher refuses on the converted tree,
   **When** the story exempts it rather than editing another test module,
   **Then** the exemption is a named entry in the guard module carrying the file,
   the line and its one-line reason, and a committed companion test asserts both
   that every entry still matches the raw matcher — so a dead exemption cannot
   accumulate unnoticed — and that the exemptions leave the synthetic source of
   US3-S2 still refused. The list is expected to be short and **not** empty: at
   the sha this spec was repaired against, seven call sites match the banned
   shape by hand — three in `tests/test_engine_identity.py`, two in
   `tests/test_110_us1_demo_first_boot.py`, one in `tests/test_interpreter.py`
   and the reap window US1 converts — and Sizing forbids this story to edit any
   of those modules, so all but the last are grandfathered by name rather than
   misclassified.

## Functional Requirements

- **FR-001**: `test_hanging_agent_is_killed_at_deadline_with_no_survivors` MUST
  NOT fail because the host was slow to schedule the stub, and MUST still fail on
  a genuine boundary defect.
- **FR-002**: The captured signature MUST be reproduced deterministically at
  fan-out 1 and without induced load, through a stub control knob that delays one
  named point in the stub's start-up sequence. The knob's points are the ones the
  stub can report from: the knob is read out of the control file at
  `tests/stub_agent.py:389` — `main` and echoed into the record directory claimed
  at `tests/stub_agent.py:390` — `main`, so the stub MUST write that echo before
  it sleeps and the transcript MUST cover every point from that claim onward. The
  transcript MUST be committed as pasted output and MUST carry, per point, the
  invocation, that run's own `pytest` summary line, and the knob echo the stub
  wrote into that run's record directory, and — for every point whose run fails —
  the failure as `pytest` printed it including the run's own `tmp_path`; any point
  that passes MUST carry its summary line and echo and say so in place of a
  failure. That is material a reader of this spec could not compose without
  running it. The transcript MUST state that the outcome of each point is
  predicted by the stub's own source, so the matrix demonstrates the signature
  rather than identifying the mechanism; the stub MUST additionally record the
  moment it installs its SIGTERM handler, and the affected test's failure message
  MUST use that record to distinguish a handler that was never installed from a
  handler that was installed and never invoked; and the reproduction MUST ship as
  a passing regression test on the fixed tree.
- **FR-003**: Every assertion of the affected test MUST survive unweakened: none
  deleted, none relaxed, none retried, none marked.
- **FR-004**: A wait in the affected test for another process's state MUST be an
  observable condition with a bounded deadline whose expiry reports the condition
  and the elapsed wait; the fixed sleep at `tests/test_us4_boundary.py:241` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors` MUST be converted
  to one.
- **FR-005**: Stub readiness MUST be established by one shared `wait_until` and
  one shared `stub_is_up`, imported from a single module under `tests/` that is
  neither `tests/stub_agent.py` — the executable the adapter launches, which the
  helper would burden with an `asyncio` import on every boot — nor
  `tests/conftest.py`, which pytest auto-loads into every session, rather than by
  the five `wait_until` definitions in two variants and the three `stub_is_up`
  definitions in two signatures that exist today; every live call site MUST import
  them, and the promoted `wait_until` MUST be the body that reports the elapsed
  wait FR-004 requires.
- **FR-006**: A committed census test MUST assert both that the shared module
  FR-005 names is the only module under `tests/` defining `wait_until` or
  `stub_is_up` — that module defines both, so a census that exempted nothing
  would refuse the very promotion FR-005 requires — and that the list of modules
  importing the shared ones is non-empty and names each module it found. The
  census MUST match those two names exactly, so that the same-prefix
  `wait_until_waiting`, `wait_until_settled` and `_wait_until` defined elsewhere
  under `tests/` fall outside its population by construction rather than by
  exemption, and no module this story may not edit is refused by it.
- **FR-007**: A mechanical guard MUST refuse a fixed sleep used to gate an
  assertion about another process's state anywhere under `tests/` — the
  population is every `*.py` file under `tests/`, walked recursively, as
  `tests/test_123_no_fixture_pins_the_builder.py:445` — `test_no_fixture_leases_a_virtual_key_against_a_registry_persona`
  walks it, and not a subset — MUST NOT refuse a fixed
  sleep that gates no such assertion, MUST be driven against synthetic source
  carrying both cases so it cannot pass by matching nothing, and MUST carry any
  exemption it needs as a named entry in its own module, each entry proven still
  load-bearing by a committed test.
- **FR-008**: Production modules under `factory/` MUST NOT import, detect, or
  special-case the stub's delay knob, and the story that adds the knob MUST prove
  it from its own diff.
- **FR-009**: The suite's summary line MUST be pasted before and after the
  change, both measured in the story's own worktree; the `skipped` count MUST be
  unchanged, the `passed` count MUST have risen by exactly the number of tests
  the story commits with each one named in the paste, and the paste MUST show the
  affected test selected rather than skipped. Because the declared `test` gate is
  `uv run pytest -q`, which prints counts and names no passing or skipped test,
  the naming and the selection MUST come from an invocation that prints test ids
  — `uv run pytest -q -rs` for the skip report and a targeted
  `uv run pytest tests/test_us4_boundary.py -k hanging_agent -v` run — pasted
  beside the `-q` summaries rather than in place of them.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-008]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-009]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-007]
```

US1 demonstrates the signature, lands the knob and the handler-installation
record its diagnosis needs, and fixes the test that fired. US2 unifies the
readiness helper and its predicate into one module and points every live call
site at it — it merge-depends on US1 because US1 mutates the copy of `wait_until`
in `tests/test_us4_boundary.py` to report the elapsed wait, and that mutated body
is the one US2 promotes, so US2 dispatched beside US1 would promote a body that no
longer exists; the edge also buys freedom from contention, since both stories edit
`tests/test_us4_boundary.py`. US3 guards the pattern and merge-depends on US2,
because a guard written before the conversion would fail on the tree it is meant
to protect — and because its population is every module under `tests/`, which US2
is still editing. No story runs concurrently with another; the graph is a chain by
construction, and each story measures its own suite baseline because a prompt
slice cut at a phase heading cannot read the one before it.
