---
state: draft
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
depends_on_landed: [011-agent-sandbox, 027-gate-suite-fake-time]
---

# Feature Specification: a verdict is a fact about the code

**Feature Branch**: `058-a-verdict-is-a-fact-about-the-code`

**Created**: 2026-08-18

## The incident, and why it is worth a spec

On 2026-08-18 at 06:47 CT, node `us1` of epic 055 finished its first attempt
with a green build and a red gate:

```
E       AssertionError: SIGTERM not delivered; signals=[]
tests/test_us4_boundary.py:236: AssertionError
1 failed, 3567 passed, 47 skipped, 5 warnings in 273.52s (0:04:33)
```

The judge never ran. `output_check` passed, `criteria_drift` was 0, and the
verdict came from the gate alone. Attempts 2 and 3 ran the same test on
substantially the same tree and it passed both times. The code was never at
fault; the epic was dispatched at `--max-concurrent-nodes 2`, so node `us2` was
building on the same host throughout, and one full attempt — ten minutes of
build plus four and a half minutes of gate — was spent discovering that a
neighbour existed.

The factory's own gate module already names this hazard and calls it what it is:

> *N nodes' gates on one host contend for CPU, so the same suite takes longer
> purely because neighbours exist, and a fixed wall-clock timeout converts that
> stretch into a spurious FAIL — a verdict that is not a fact about the node's
> code.*
> — `factory/verify/gates.py:76-79`

That comment justifies `DEFAULT_GATE_CONCURRENCY = 1`, which bounds gate
subprocesses below node concurrency so gates never contend with gates. It works.
The leak is on the other side: **agents are not bounded by that semaphore.** At
cap N, one gate runs while N−1 agents run their own tool calls, and a test
inside the gated suite that races a real clock loses to them.

With `max_attempts = 3`, one spurious FAIL is a third of a story's ladder. That
is why the finding is called a random epic killer rather than a flake, and why
the honest answer to "what fan-out can we run" is currently one.

## What actually races

Two facts from the tree, both read on 2026-08-18:

- `tests/test_us4_boundary.py:212` constructs the adapter with `grace_s=1.0` and
  drives the attempt with `timeout_s=3` — a tenth of production's
  `DEFAULT_GRACE_S = 10.0` (`factory/workgraph/adapter.py:99`), tightened purely
  to keep the test fast.
- `tests/stub_agent.py:414` installs the stub's SIGTERM handler **after** it has
  drained stdin at `:407`. Until that line runs, SIGTERM lands on the default
  disposition: the process dies immediately and records nothing.

So the test starts a three-second deadline at the moment it launches a process,
and then asserts that a handler the process installs at some later, unsynchronised
point caught the signal. On an idle host the stub boots in milliseconds and the
assertion holds. Under a neighbour's load it does not, and the failure is
indistinguishable from a real boundary defect.

The stub's own source already says how a test should wait for it:

> *Last, and only once stdin is drained: a test polling for "the stub is up"
> waits on the file that proves the prompt arrived.*
> — `tests/stub_agent.py:405-406`

This test does not poll for it.

## Why this is buildable, and 032 was not

The nearest neighbour to this spec is 032-replay-determinism, which asked one
diff to carry a fail-first reproduction *and* its fix, and was unbuildable
because the gate runs the suite over that same diff — a red suite fails the
attempt, and a harness that asserts success is not a reproduction.

This spec does not have that shape, and the difference is worth stating so it is
not pattern-matched into the same corner. **The race here can be forced
deterministically.** The stub already takes control knobs from its invocation
(`ignore_sigterm` is one), so a knob that delays handler installation turns a
load-dependent flake into a reproduction that fires every time, on any host, at
no concurrency. The pre-fix code fails it; the fixed code passes it. The diff
therefore carries a **green** suite and a real regression guard, and no evidence
file is doing work that a test should be doing.

The captured pre-fix failure is committed at
`evidence/055-us1-attempt1-gate.txt` anyway — not as a substitute for the
reproduction, but because the judge sees only the diff, and the criterion "the
mechanism you fixed is the mechanism that fired" is otherwise unprovable.

## User Scenarios & Testing

### User Story 1 - The boundary test measures the boundary, not the host (Priority: P1)

The test that fired stops depending on how quickly the host scheduled a
subprocess. Its verdict becomes a fact about whether the deadline machinery
terminates an agent and its children — which is what it exists to check — and
nothing else.

**Why this priority**: it is the whole defect. Everything else in this spec
generalises the fix or guards it.

**Independent Test**: with handler installation deliberately delayed past the
attempt's deadline, the pre-fix test fails and the fixed test does not — run at
concurrency 1, on an idle host, deterministically, without contention of any
kind.

**Acceptance Scenarios**:

1. **Given** the stub configured to delay installing its SIGTERM handler beyond
   the attempt's deadline, **When** the fixed test runs, **Then** it does not
   report a boundary defect — the delay is the host being slow, and the test
   must not confuse that with the boundary failing.
2. **Given** that same delay applied to the **pre-fix** test, **When** it runs,
   **Then** it fails with the committed signature — the reproduction is
   demonstrated at a fixed knob rather than argued from a load average.
3. **Given** a genuine boundary defect — a namespace that leaks a child, or a
   deadline that never terminates the agent — **When** the fixed test runs,
   **Then** it still fails. The fix removes sensitivity to scheduling, and MUST
   NOT remove sensitivity to the thing under test; a test that cannot fail is
   worse than the flake it replaced.
4. **Given** the fixed test, **When** its diff is inspected, **Then** no
   assertion has been deleted, weakened, retried, or marked — the process-group
   kill, the survivor checks and the termination classification all survive
   intact.
5. **Given** the fixed test, **When** it waits for anything, **Then** it waits
   on an observable condition with a bounded deadline and reports what it was
   waiting for when that deadline expires — never on a fixed sleep chosen to be
   "probably long enough".

---

### User Story 2 - Every test that launches the stub waits for it the same way (Priority: P1)

The readiness gate US1 needs becomes one shared helper, and every test that
launches the stub under a deadline uses it. One test was observed failing; the
rest share its shape and simply have not been unlucky yet.

**Why this priority**: P1 because a fix applied to one call site is a fix with a
shelf life. The boundary suites launch real processes under `bwrap` and are the
population at risk; leaving the others on the old pattern means the next cap-2
run finds the next one.

**Independent Test**: every stub launch in the boundary suites goes through the
shared readiness helper, asserted mechanically by a test that counts call sites
rather than by reading them; the suites stay green.

**Acceptance Scenarios**:

1. **Given** the boundary suites, **When** a stub is launched with a deadline
   that its readiness could race, **Then** the launch waits through the shared
   helper — and the number of such launches that do not is zero, established by
   a test rather than by inspection.
2. **Given** the shared helper, **When** the stub never becomes ready, **Then**
   it fails at its own bounded deadline naming the file it waited on and how
   long it waited — a helper that hangs has replaced a flaky failure with a
   worse one.
3. **Given** the converted tests, **When** the suite runs, **Then** its passed
   and skipped counts equal the pre-change baseline. A new skip is a hidden
   test and fails this scenario.

---

### User Story 3 - The pattern cannot come back (Priority: P2)

A mechanical guard refuses a new fixed sleep used to wait for another process's
state in the boundary suites, in the vocabulary `test_final_sweep.py` already
uses for D-021.

**Why this priority**: P2 because US1 and US2 deliver the fix. This is what stops
it rotting — the pattern is ordinary, it reads as harmless, and the next person
to write one will not have read this spec.

**Independent Test**: a test that fails when a fixed sleep gating an assertion
about another process is introduced into the guarded suites, and passes on the
converted tree.

**Acceptance Scenarios**:

1. **Given** the guarded suites on the fixed tree, **When** the guard runs,
   **Then** it passes.
2. **Given** a fixed sleep reintroduced ahead of an assertion about another
   process's state, **When** the guard runs, **Then** it fails and names the
   file and line.
3. **Given** a fixed sleep used only to yield the event loop and gating no such
   assertion, **When** the guard runs, **Then** it passes — the guard
   distinguishes waiting for something from simply pausing, and a guard that
   cannot tell them apart would ban 37 legitimate call sites to catch a handful.

---

### Edge Cases

- **The delay knob leaks into production.** The stub is a test double and the
  knob is its own; nothing under `factory/` may import, detect, or special-case
  it. 032's trap, and it applies unchanged.
- **A readiness helper that waits forever** converts a loud flake into a silent
  hang, which the gate then reports as a timeout with no signature at all. Every
  wait is bounded and says what it was waiting for.
- **The fix makes the test unable to fail.** Waiting long enough for anything to
  settle also waits long enough for a real leak to look clean if the bound is
  chosen carelessly. The bound is generous against scheduling and far below a
  real leak's forever, and US1-S3 is the check.
- **Contention is not the only cause.** The committed evidence establishes the
  race exists; it does not prove it is the *only* way this test fails. A second
  mechanism found during the work is a finding to file, not a reason to widen
  this spec.
- **This host has 20 cores.** Anything tuned to that number is tuned to one
  machine. Bounds are expressed as deadlines on observable conditions, never as
  sleeps calibrated against a core count.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `test_hanging_agent_is_killed_at_deadline_with_no_survivors` MUST
  NOT fail because of host scheduling delay, and MUST still fail on a genuine
  boundary defect.
- **FR-002**: The race MUST be reproduced deterministically through a stub
  control knob that delays handler installation, at concurrency 1 and without
  induced load; the reproduction MUST ship as a passing regression test on the
  fixed tree.
- **FR-003**: Every assertion of the affected test MUST survive unweakened: none
  deleted, none relaxed, none retried, none marked.
- **FR-004**: A test that waits for another process's state MUST wait on an
  observable condition with a bounded deadline, and MUST report the condition
  and the elapsed wait when that deadline expires.
- **FR-005**: Stub readiness MUST be established by one shared helper, and every
  launch in the boundary suites whose deadline could race readiness MUST use it.
- **FR-006**: The count of such launches that do not use the helper MUST be
  established by a test, not by inspection.
- **FR-007**: A mechanical guard MUST refuse a fixed sleep used to gate an
  assertion about another process's state in the guarded suites, and MUST NOT
  refuse a fixed sleep that gates no such assertion.
- **FR-008**: Production modules under `factory/` MUST NOT import, detect, or
  special-case the stub's delay knob.
- **FR-009**: The suite's passed and skipped counts MUST equal the pre-change
  baseline.

## Success Criteria

- **SC-001**: The number of assertions in the affected test that can fail
  because of scheduling delay alone is zero, demonstrated by the delay knob at
  its maximum.
- **SC-002**: With the delay knob applied, the pre-fix test fails with the
  signature in `evidence/055-us1-attempt1-gate.txt` and the fixed test passes —
  both on an idle host at concurrency 1.
- **SC-003**: A mutation that breaks the boundary — a leaked child, a deadline
  that does not terminate — still turns the fixed test red.
- **SC-004**: The number of stub launches in the boundary suites that race
  readiness is zero, counted by a test.
- **SC-005**: Suite passed and skipped counts match the baseline; the boundary
  suites' wall-clock does not grow beyond the gate's budget.
- **SC-006**: After this lands, `ergane build start --max-concurrent-nodes 3`
  completes an epic with no gate failure attributable to a neighbour. This is
  the criterion the spec exists for, it is an **observation over time rather
  than a test**, and it is recorded here as the operator's acceptance rather
  than as anything a node can prove from its diff.

## Out of Scope

- **Bounding agent tool calls under the gate semaphore.** The asymmetry named
  above — gates are bounded, agents are not — is real and larger than this spec.
  Fixing the tests removes the observed harm; bounding agents is a change to
  `DEFAULT_GATE_CONCURRENCY`'s whole premise and wants its own decision.
- **The two open landing-poll criticals.** Fan-out multiplies exposure to
  `mergequeue/a-single-misread-poll-kills-a-verified-node-irreversibly` and
  `mergequeue/landing-base-follows-the-operator-checkout`. Both are real reasons
  to be careful at cap > 1 and neither is a test-timing defect.
- **Raising the concurrency dials.** This spec makes cap 3 safe to *choose*; it
  does not choose it.

## Assumptions

- `bwrap` is available on the worker host, so the boundary suites run rather
  than skip (`tests/test_us4_boundary.py:209` skips without it — a fix proven
  only on a host that skipped the test is not proven).
- The stub's control mechanism can carry one more knob without disturbing the
  invocations already recorded through it.
- The suite baseline at drafting is 3567 passed / 47 skipped under the gate, and
  a story re-measures rather than trusting that number.

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

US1 fixes the test that fired and lands the delay knob its reproduction needs.
US2 promotes the readiness wait into a shared helper and converts the rest of
the boundary launches — it merge-depends on US1 because the helper it extracts
is the one US1 writes. US3 guards the pattern and merge-depends on US2, because
a guard written before the conversion would fail on the tree it is meant to
protect.
