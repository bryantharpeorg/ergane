---
state: ready
# Flipped ready 2026-08-11 PM CT on the operator's word ("flip all 6"); the
# paused roadmap dispatches serially (max_concurrent_epics=1) in dir order
# once unpaused.
# Synthesis 2026-08-11: file-collision serialization, not content — this spec
# is the corpus's widest toucher and goes last. It shares
# tests/test_interpreter.py's ScriptedWorld.run_agent_attempt with 027
# (adjacent lines), factory/workgraph/worktree.py + tests/test_worktree.py
# with 028, factory/mergequeue/gh.py + merge_activities.py + its tests with
# 029, and factory/worker.py + factory/notify/messages.py +
# tests/test_messages.py with 031; dispatched concurrently they would meet in
# the merge queue. 031 dispatches first by design and nothing here blocks it.
depends_on_landed: [027-gate-suite-fake-time, 028-epic-relaunch-reset, 029-salvage-landing-grammar, 031-scheduler-failure-notify]
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `interpreter/ci-failure-never-reaches-an-agent` (critical) and
# `ci/flaky-concurrency-test-is-a-random-epic-killer` (critical), then refined
# against the tree at 9594787 on 2026-08-11.
---

# Feature Specification: A red check that reaches no one

Two findings, one mechanism. When the required check goes red, the merge queue
rejects the landing as `CHECKS_FAILED` and the interpreter spends the node's
single recovery cycle — sync the branch, dispatch a recovery attempt, re-enqueue
— on the assumption that the red meant a stale base. But the recovery attempt's
prompt names only the outcome word (`CHECKS_FAILED` and timestamps —
`LandingEvidence` at `factory/workgraph/prompt.py:81` carries nothing else for a
checks failure). The agent's own gate is green in its worktree, so an agent told
"a check failed" with no log, no check name and no URL changes nothing, passes
the gates and the judge, and re-enqueues byte-identical code. The second red
exhausts `max_recovery_cycles` (default 1, `factory/mergequeue/models.py:203`)
and the node is KILLED with every dependent.

Both findings end at that same cliff and differ only in why the check was red:

- **Deterministic red** (`interpreter/ci-failure-never-reaches-an-agent`): the
  worker host has services CI lacks, so a test can be green locally and red in
  CI *by construction*. Observed 2026-08-09 on 021/us1 — a correct fix, green
  gate, judge PASS on all scenarios, then two identical CI failures and a KILLED
  node that took us2/us3/us4 down at attempt 0. `git diff` between the attempt-1
  code commit and the attempt-2 tip was empty; the only new objects were two
  salvage commits. Cost: 28.8M input tokens, 394 API calls, ~2.5 hours, zero
  landed output.
- **Stochastic red** (`ci/flaky-concurrency-test-is-a-random-epic-killer`):
  `test_kill_with_n_in_flight_salvages_every_one_before_terminating`
  (`tests/test_interpreter.py:4958` at 9594787) asserts a sampled timing
  coincidence — that the in-flight set was observed at size 3 — so under CI load
  it fails on a diff that never touched it (fired 2026-08-09 17:54Z against
  021/us3: `running_sets=[{us1, us2}, {us1, us2}]`; the re-run passed in 5m20s).
  One flake silently spends the whole recovery budget; two in a row kill the
  node and its dependents.

Three stories: stop the required check from lying at random (US1), make a
`CHECKS_FAILED` recovery a retry with evidence instead of a blind re-run (US2),
and refuse to silently re-enqueue bytes the queue already rejected (US3). US1
lands first on purpose: it de-flakes the very check that US2's and US3's own
landings must pass through.

## User Scenarios & Testing

### User Story 1 - The required check must stop failing on a coincidence (Priority: P1)

The kill test's real claims are durable — three salvage commits, three
teardowns, three KILLED states, every branch reachable — and those assertions
already exist (`tests/test_interpreter.py:5003-5046`). What flakes is the
*premise*: the kill signal is sent the instant the signalled node's attempt
starts (`run_agent_attempt`, `tests/test_interpreter.py:1284-1289`), so whether
all three nodes were genuinely in flight when it landed is a race against the
worker's activity pickup. Under CI load the third node loses, and both the
sampled-coincidence assertion *and* the salvage-all-three assertion inherit the
broken premise. The same sampled coincidence sits in the pause sibling
(`:4935`), the cap-overlap test (`:4367`), and the landing-fanout test
(`test_concurrent_passes_each_open_one_pr_and_enqueue_and_the_epic_waits`,
`:4655`) — four sites, one more than the findings named.

**Goal**: the scripted world withholds a steering signal until every node the
scenario declares in flight has actually been observed dispatched, so the
concurrency premise is established by construction, not sampled by luck — and
the required check stops killing unrelated epics.

**Why this priority**: it is the cheapest story and it protects the other two.
Every landing in this spec must ride through the check this story de-flakes.

**Independent Test**: run the converted kill test repeatedly (15 consecutive
runs) against a scripted world that delays the third node's attempt pickup; the
premise holds every time, and a scenario whose declared set can never all
dispatch fails with a named reason inside the harness's bounded wait.

**Acceptance Scenarios**:

1. **Given** the three-node kill scenario with the scripted world's dispatch
   gate declared for `{us1, us2, us3}`, **When** the third node's attempt is
   slow to be picked up, **Then** the kill signal is delivered only after all
   three have been observed in flight, and every durable assertion — three
   salvages, three teardowns, three KILLED states, all branches reachable —
   passes deterministically.
2. **Given** a scenario whose declared in-flight set can never be reached (a
   concurrency limit of 1 with a gate declared for two nodes), **When** the
   bounded wait expires, **Then** the test fails with a named reason — never a
   hang, and never a silent pass.
3. **Given** the pause sibling, the cap-overlap test and the landing-fanout
   test, which assert the same sampled coincidence, **When** the same premise
   discipline is applied to them, **Then** their in-flight premises are
   deterministic too, and their existing assertions are preserved.
4. **Given** the landed story, **When** its diff is inspected, **Then** no
   required check is retried, no pytest marker is relied on, no test is
   deleted, and the kill test's durable assertions are intact or strengthened.

### User Story 2 - A CHECKS_FAILED recovery is a retry with evidence (Priority: P1)

The classifier already knows *which* required checks failed — `PrSnapshot`
carries their names (`factory/mergequeue/models.py:123`), and `CHECKS_FAILED`
is only ever produced when that tuple is non-empty
(`factory/mergequeue/classify.py:76-77`) — but the names are dropped the moment
the outcome is recorded (`ObservedOutcome` keeps only a timestamp and the
outcome word, `models.py:76-80`). Nothing fetches the failing run's log. The
recovery attempt is dispatched blind, and a blind agent whose local gate is
green rationally changes nothing.

**Goal**: when a landing is rejected `CHECKS_FAILED`, the recovery attempt's
prompt carries the failing check's name, the failing run's URL, and a bounded
tail of its failed-step log, verbatim — and the operator's escalation history
names the failing checks too.

**Independent Test**: script a `CHECKS_FAILED` rejection whose snapshot names a
failing check and whose scripted evidence fetch returns a log tail; assert the
recovery attempt's prompt quotes the check name, the URL and the log tail, and
that a scripted fetch failure still dispatches the attempt with the absence
stated.

**Acceptance Scenarios**:

1. **Given** a landing rejected `CHECKS_FAILED` with a named failing check,
   **When** the recovery attempt's prompt is assembled, **Then** its landing
   rejection section quotes the failing check's name, the failing run's URL,
   and a bounded tail of the failing log, verbatim — never a paraphrase.
2. **Given** that same rejection, **When** the outcome is recorded and the
   landing later escalates, **Then** the landing's queue history carries the
   failing check names and the rendered escalation history shows them to the
   operator.
3. **Given** an evidence fetch that fails (gh error or outage), **When** the
   recovery cycle runs, **Then** the recovery attempt still dispatches with the
   check names and queue history in its prompt, the prompt states that the log
   could not be fetched, and the cycle is not lost to the fetch.
4. **Given** the evidence fetch's implementation, **When** it executes, **Then**
   it runs as a Temporal activity using the non-blocking subprocess shape
   (`asyncio.to_thread`), and no `gh` subprocess is spawned from workflow code.
5. **Given** a `CONFLICT` rejection, **When** its recovery cycle runs, **Then**
   behaviour is unchanged: the debugger persona, the conflicted file list, and
   no evidence fetch.

### User Story 3 - Re-enqueueing bytes the queue already rejected requires a human (Priority: P2)

The observed incident's signature is provable from git alone: the re-enqueued
tip differed from the rejected tip by two salvage commits while the *tree* was
byte-identical. A byte-identical tree re-enters CI as the identical test run —
if the red was deterministic it fails identically by construction, and only a
flake could pass. That judgment call (was it a flake?) belongs to a human, and
today nobody is asked: the identical re-enqueue happens silently, burns a CI
run, and its second rejection kills the node.

**Goal**: the interpreter records the tip it enqueued, compares the tree it is
about to re-enqueue against the tree the queue rejected, and — when they are
identical — escalates instead of enqueueing, with `RETRY` meaning "enqueue it
anyway, I judge the red a flake". A sync that merged in nothing (the target
head never moved) is also named in the recovery prompt, because it refutes the
stale-base hypothesis the recovery routing was built on.

**Independent Test**: script a `CHECKS_FAILED` recovery whose sync moves
nothing and whose recovery attempt changes nothing; assert the landing
escalates before any second enqueue, that `RETRY` proceeds to enqueue the
identical tree, and that a recovery which *does* change the tree re-enqueues
exactly as today.

**Acceptance Scenarios**:

1. **Given** a recovery cycle whose resulting tree is byte-identical to the
   tip the queue rejected, **When** the interpreter reaches re-enqueue, **Then**
   no enqueue happens; a landing escalation fires naming the futility, with
   choices `[RETRY | KILL | PAUSE_EPIC]`.
2. **Given** that futility escalation, **When** the operator presses `RETRY`,
   **Then** the identical tree is pushed and enqueued — the flake judgment is
   the operator's — and the landing returns to polling.
3. **Given** that futility escalation, **When** the operator presses `KILL` or
   an hour passes in silence, **Then** the node ends KILLED with its branch
   preserved, exactly as landing escalations already end.
4. **Given** a recovery cycle whose attempt changed the tree, or whose sync
   merged in a moved target head, **When** re-enqueue runs, **Then** it
   proceeds exactly as today — no escalation, no new friction.
5. **Given** a recovery tip that differs from the rejected tip only by salvage
   and sync merge commits (trees equal, commits different), **When** the
   comparison runs, **Then** it reads as identical — the comparison is tree
   identity, never commit identity.
6. **Given** a sync that merged in nothing because the target head had not
   moved, **When** the recovery attempt's prompt is assembled, **Then** it
   states that the base was not stale — the failure lives in the branch's own
   content.

## Functional Requirements

- **FR-001**: The scripted world MUST be able to withhold a steering signal
  until every node in a test-declared set has been observed dispatched, so a
  concurrency premise is established before the signal lands, not sampled after.
- **FR-002**: That wait MUST be bounded, and a scenario whose declared set is
  never reached MUST fail with a named reason — never a hang and never a pass.
- **FR-003**: The de-flake MUST NOT weaken the kill test's durable assertions
  (salvage set, teardown set, KILLED states, branch reachability), MUST NOT
  retry or rerun any required check, and MUST NOT rely on pytest markers —
  nothing passes `-m` in the gate or in CI, so a marker changes nothing.
- **FR-004**: When a poll classifies `CHECKS_FAILED`, the interpreter MUST
  record the failing required checks' names from the classifying snapshot into
  the landing's queue history.
- **FR-005**: A `CHECKS_FAILED` recovery attempt's prompt MUST carry the failing
  check evidence — check name(s), the failing run's URL when resolvable, and a
  bounded verbatim tail of the failing log — in the landing rejection section.
- **FR-006**: The evidence fetch MUST run as a Temporal activity (never a
  subprocess spawned from workflow code) and MUST NOT block the worker's event
  loop — the `asyncio.to_thread` shape `sync_landing_branch` already uses.
- **FR-007**: A failed evidence fetch MUST degrade, not abort: the recovery
  attempt still dispatches with the check names and queue history, and the
  prompt states that the log was unavailable.
- **FR-008**: The rendered escalation history for a landing MUST name the
  failing checks recorded in its queue history.
- **FR-009**: The interpreter MUST record the commit it enqueued for each
  landing, so a later rejection can be compared against exactly what the queue
  tested.
- **FR-010**: Before re-enqueueing after a recovery cycle, the interpreter MUST
  compare the tree about to be enqueued against the tree of the rejected tip —
  tree identity, not commit identity.
- **FR-011**: A byte-identical re-enqueue MUST NOT happen without an operator's
  decision: the landing escalates with choices `[RETRY | KILL | PAUSE_EPIC]`,
  where `RETRY` proceeds with the enqueue and the other paths keep their
  existing meanings. No automatic retry of a required check, ever.
- **FR-012**: The futility routing MUST NOT add a member to `QueueOutcome` or
  `LandingState` — both vocabularies are closed by design — and every new field
  on a record that crosses a Temporal boundary MUST carry a default so recorded
  histories still replay.
- **FR-013**: A recovery whose sync merged in nothing (target head unmoved)
  MUST state that fact in the recovery attempt's prompt: the stale-base
  hypothesis is refuted, and the agent should read the failure as its own.

## Success Criteria

- **SC-001**: The converted kill test passes 15 consecutive runs, and its
  concurrency premise can no longer fail on dispatch timing by construction.
- **SC-002**: A `CHECKS_FAILED` recovery attempt's prompt contains a line of
  the failing check's log and the failing run's URL (demonstrated through the
  scripted world; no live CI required).
- **SC-003**: A recovery cycle that changes nothing costs zero CI runs: the
  re-enqueue is replaced by an escalation an operator answers.
- **SC-004**: No new dependency, no new `QueueOutcome` or `LandingState`
  member, and the full suite green.
- **SC-005**: The `CONFLICT`, pending, `MERGED`, `DEQUEUED_BY_HUMAN` and
  `STALLED` paths behave byte-identically to today.

## Edge Cases

- **Several failing checks at once**: every failing check is named; the log
  fetch is bounded per check and in total, so a pathological rollup cannot
  flood the prompt. The bound is a constant next to its precedent
  (`_STDERR_TAIL_LIMIT`, `factory/mergequeue/gh.py:55`), not an unbounded read.
- **Empty check names**: unreachable at classification — `CHECKS_FAILED` is
  produced only when `failing_required_checks` is non-empty
  (`classify.py:76-77`) — but the evidence path must tolerate a name whose run
  URL cannot be resolved (FR-007's degrade covers it).
- **Replay compatibility**: `ObservedOutcome`, `Landing`, `LandingEvidence` and
  the landing activities' result records are frozen dataclasses that cross
  Temporal boundaries; every new field takes a default so histories recorded
  before this spec still deserialize and replay (FR-012).
- **Recovery-cycle accounting**: the futility escalation replaces the enqueue
  *inside* an already-counted cycle; it must not increment `recovery_cycles` a
  second time, and an operator's `RETRY` on futility completes that same
  cycle's enqueue rather than granting a new cycle.
- **The harness gate on a genuine regression**: a scheduler that truly stops
  dispatching a third node now fails the kill test at the gate's named timeout
  — that is a true signal, not a reintroduced flake, and the named reason is
  what distinguishes it.
- **A landing with no recorded enqueued tip** (history from before this spec):
  the comparison cannot run, so the re-enqueue proceeds as today — absence of
  the record must never be read as futility.

## Assumptions

- The worker host's `gh` (already authenticated for the queue) can read the
  target repo's check runs and Actions logs; the evidence fetch uses the same
  client seam (`GhClient`, `factory/mergequeue/gh.py:111`) and the same
  scrubbed environment.
- Only `open_landing_pr` pushes the node branch (`factory/activities/`
  `merge_activities.py:311`, via `worktrees.push_branch`); salvage commits but
  never pushes (`factory/workgraph/worktree.py:234-275`). The recorded enqueued
  tip therefore names exactly what CI tested.
- Tree-object equality is the right notion of "byte-identical": two commits
  with equal trees present identical inputs to the required check.
- No new dependency is needed: `gh` is already the queue's client, and the
  harness work is plain `asyncio`.

## Out of Scope

- **Making the gate environment match CI.** The audit's two-tier-verification
  design owns that; this spec makes the failure legible and recoverable, not
  impossible.
- **The queue-ejection-invisible-to-the-poller stall** — a separate known gap
  with its own finding; `stall_after_s` guidance is unchanged here.
- **Automatically retrying a required check.** Not deferred — forbidden. It
  would hide real regressions inside the one gate the merge queue trusts.
- **Fixing the existing blocking `gh` activities** (`poll_landing` and
  siblings call the sync client directly): that is the open finding
  `interpreter/gh-subprocess-blocks-event-loop`'s scope. This spec must not
  add another instance, and must not refactor the existing ones.
- **Raising `max_recovery_cycles`.** The bound is not the defect; the blindness
  inside the bounded cycle is.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-006, FR-007, FR-008]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009, FR-010, FR-011, FR-012, FR-013]
```
