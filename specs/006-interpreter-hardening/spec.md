---
state: ready
depends_on_landed: [003-merge-queue, 005-workgraph-interpreter]
---

# Feature Specification: Interpreter Hardening

**Feature Branch**: `006-interpreter-hardening`

**Created**: 2026-08-06

**Status**: Drafted from defects the 003 crossover exposed by running the interpreter
against a real epic for the first time. Every item here was found live, not by review:
the first crossover run died to an operator interrupt, the restart was blocked by an
orphaned credential, and the second run's Temporal history grew at 1,320 events/hour
while doing nothing with the value it was collecting. None of these are theoretical.

**Input**: Bounded workflow history, preflight validation of an epic that cannot
succeed, restart-safety after a kill, and resilience to transient infrastructure — the
four classes of failure that cost the 003 crossover its first day.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An attempt's history cost does not grow with its duration (Priority: P1)

As the factory operator, I can run a multi-hour attempt without the epic's Temporal
history growing without bound, so that a long epic cannot run itself into the history
limit and every replay stays cheap.

Today the interpreter's inner loop uses `workflow.wait_condition(..., timeout=
poll_interval_s)` as a heartbeat and fires a `poll_usage` activity on every timeout.
Measured on the live 003 run: **11 history events every 30 seconds** — one timer
started, one fired, one activity scheduled/started/completed, and the workflow tasks
around them. That is 1,320 events/hour, ~5,300 for a single four-hour attempt, and
20–30k across a three-node epic with retries. Temporal warns at 10,240 events and
fails at 51,200; `EpicWorkflow` has no continue-as-new.

The value bought at that price has exactly one consumer. `TeardownInput.last_snapshot`
"exists solely so a teardown that cannot reach the proxy still has a dollar figure to
record" — read once, on the failure path only. Nothing acts on spend mid-attempt,
because budget *enforcement* is deferred (D-021); the factory tracks, it does not
enforce. The polling is insurance against a rare path, priced as if it were the main one.

**Why this priority**: It is the only defect here that bounds how long an epic may
run. The others cost an operator minutes; this one has a ceiling behind it.

**Independent Test**: Run one attempt under time skipping for a simulated four hours
and assert the history event count is within a constant of a one-minute attempt.

**Acceptance Scenarios**:

1. **Given** an attempt of any duration, **When** it completes, **Then** the number of
   history events it contributed is independent of how long it ran.
2. **Given** a teardown whose proxy read succeeds, **When** the ledger row is written,
   **Then** it carries the measured spend, unchanged from today's behaviour.
3. **Given** a teardown whose proxy read fails, **When** the ledger row is written,
   **Then** it carries an explicit NULL spend rather than a fabricated zero (001
   FR-005 preserved), or the last measured figure if one is available at no history cost.
4. **Given** an epic status query mid-attempt, **When** the operator asks, **Then**
   spend visibility is no worse than today for the operator's purposes — satisfied
   at the status CLI, which reads the newest heartbeat snapshot off the running
   activity via `describe()` and renders it beside the epic's internal state; no
   workflow change, no history events (mechanism decided 2026-08-07, after
   attempt 2 deleted the poll without a replacement and the judge caught it).

---

### User Story 2 - An epic that cannot succeed never starts (Priority: P2)

As the factory operator, I get a refusal at `factory-epic start` when the epic is
misconfigured, so that a mistake costs me one message instead of several attempts,
several issued credentials, and a burned node.

Found live twice in one morning. A persona registry naming `anthropic/claude-opus-5` —
an alias the proxy does not serve — dispatched normally and burned three attempts, each
400ing instantly, before anything surfaced the cause. Separately, an epic whose previous
run was killed could not restart at all: key aliases are deterministic
(`epic:node:attempt:persona`), so re-issuance collided with the orphan the dead worker
never tore down, and the epic failed in 3.84 seconds with a message about uniqueness
that named no remedy.

`factory-epic start` already re-validates the graph structurally, on the stated
principle that "a graph that fails them never becomes a workflow that has to be
killed." The same argument applies to the two facts a graph cannot carry: whether the
proxy serves the models the registry names, and whether the credentials the first
attempts need are available.

**Why this priority**: Cheapest possible fix for the most operator time lost. The
preflight is a read of `/v1/models` and a key listing.

**Independent Test**: Start an epic whose registry names an unserved alias, and one
whose first key alias is already taken; assert both refuse before any dispatch.

**Acceptance Scenarios**:

1. **Given** a registry naming a model alias the proxy does not serve, **When**
   `factory-epic start` runs, **Then** it exits non-zero naming every unserved alias and
   the persona that names it, having dispatched nothing and issued nothing.
2. **Given** a proxy that is unreachable at start, **When** validation runs, **Then**
   the failure is distinguished from "alias not served" and names the address tried.
3. **Given** an orphaned key alias that would collide with the epic's first attempt,
   **When** `factory-epic start` runs, **Then** the collision is reported before
   dispatch with the exact remediation, rather than surfacing as a mid-flight failure.
4. **Given** a fully valid configuration, **When** `factory-epic start` runs, **Then**
   preflight adds no dispatch-path behaviour and the epic proceeds exactly as today.

---

### User Story 3 - A killed epic restarts without hand-cleaning credentials (Priority: P3)

As the factory operator, I can restart an epic that was killed mid-attempt without
reaching for the proxy's admin API, so that recovering from an interruption is a
command rather than a procedure.

US2 makes the collision *visible*; this story makes it *not happen*. An interrupted
epic leaves a virtual key whose deterministic alias blocks the next run's first
attempt. The operator's only recourse today is `POST /key/delete` with the master key —
a credential the factory deliberately keeps away from every other path.

**Why this priority**: Recovery matters, but US2's clear refusal already converts this
from a mystery into a one-line fix. This story removes the line.

**Independent Test**: Kill an epic mid-attempt, restart it, and assert it dispatches
without operator intervention and without two live keys sharing an alias.

**Acceptance Scenarios**:

1. **Given** an orphaned key from a killed run, **When** the epic restarts, **Then**
   issuance recovers the alias and the attempt dispatches, with exactly one live key
   for that alias.
2. **Given** recovery of an orphan, **When** the ledger is read, **Then** the dead
   run's recorded spend remains attributable and is not merged into the new attempt.
3. **Given** an alias collision that is *not* an orphan (a live key from a running
   epic), **When** issuance runs, **Then** it refuses rather than disturbing a key in use.

---

### User Story 4 - Transient infrastructure does not discard hours of work (Priority: P3)

As the factory operator, I can survive a brief Temporal or proxy hiccup without losing
a multi-hour attempt, so that the factory's failure modes are proportional to their causes.

Two fixed constants are sized for a healthy moment rather than a long run.
`_AGENT_HEARTBEAT_TIMEOUT` is five seconds (`5 * HEARTBEAT_INTERVAL_S`): any Temporal
restart, GC pause, or host load spike longer than that abandons an attempt that may be
hours deep. Key issuance gives up in under four seconds, so a momentary proxy blip
fails the whole epic. Both were observed to matter — the heartbeat bound is currently
the reason a dev-server restart cannot be done while an epic is running.

**Why this priority**: Real, but only bites during an incident, and the tmux
supervision now in place removes the most common trigger.

**Independent Test**: Simulate a Temporal outage longer than the current bound and a
proxy outage longer than the current issuance budget; assert the attempt and the epic
both survive.

**Acceptance Scenarios**:

1. **Given** an attempt in flight, **When** Temporal is unreachable for an interval
   short relative to the attempt's own timeout, **Then** the attempt is not abandoned.
2. **Given** an attempt whose agent has genuinely stopped beating, **When** the bound
   elapses, **Then** it is still detected and classified — liveness detection is
   loosened, not removed.
3. **Given** a transient proxy failure at issuance, **When** retries are exhausted,
   **Then** the budget spent retrying was proportional to a real outage, not to seconds.

---

### User Story 5 - The operator surface reports what is true (Priority: P3)

As the factory operator, `factory-epic status` tells me whether the workflow is
actually running, so that I am never told `RUNNING` about a workflow Temporal has
already closed.

Observed live: `status` printed `epic 003-merge-queue RUNNING` for a workflow whose
Temporal execution status was `FAILED`. The command reports the epic's *internal*
state field, queried from a closed workflow, and never reports the execution status
itself. A query against a closed workflow succeeds and returns its final state, which
is exactly what makes the omission misleading rather than merely incomplete.

**Why this priority**: Small and self-contained, but it is the command an operator
reaches for first when something is wrong, and today it can actively mislead.

**Independent Test**: Query status against running, failed, terminated and completed
workflows; assert each is distinguishable.

**Acceptance Scenarios**:

1. **Given** a workflow Temporal has closed, **When** `factory-epic status` runs,
   **Then** the execution status is reported and is distinguishable from a running epic.
2. **Given** a running epic, **When** status runs, **Then** today's per-node output is
   unchanged.
3. **Given** `--json`, **When** status runs, **Then** the execution status is present
   as a field and the existing payload is not restructured.

---

### Edge Cases

- A teardown that cannot reach the proxy *and* has no figure from any source: the row
  must carry NULL, never zero (001 FR-005). This case must not regress under US1.
- An attempt shorter than one poll interval today records no snapshot at all; whatever
  US1 chooses must not make a short attempt worse than a long one.
- Preflight validates the registry the *CLI* can see; the worker resolves personas from
  its own `personas.yaml` (R8, deliberately). Preflight must not claim to have
  validated what the worker will actually resolve — it reduces a class of failure, it
  does not eliminate it, and the message must not overclaim.
- An orphan whose spend was never reconciled must not be silently discarded by recovery.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The number of workflow history events an attempt contributes MUST be
  independent of the attempt's duration — O(1), not O(elapsed time).
- **FR-002**: Usage observation MUST NOT emit a scheduled/started/completed activity
  triple or a timer pair per interval on the workflow's event log.
- **FR-003**: A teardown that can reach the proxy MUST record the measured spend. One
  that cannot MUST record the most recent figure carried off the agent activity's
  heartbeat, and an explicit NULL rather than a fabricated zero (001 FR-005) only when
  no figure was ever measured. The heartbeat MUST carry that figure without emitting
  any workflow history event.
- **FR-004**: `factory-epic start` MUST validate every model alias the resolved persona
  registry names against the model list the proxy serves, and MUST refuse to start
  when any is unserved, naming each unserved alias and the persona naming it.
- **FR-005**: `factory-epic start` MUST distinguish "proxy unreachable" from "alias not
  served", and MUST name the address it tried.
- **FR-006**: `factory-epic start` MUST detect a key alias that would collide with the
  epic's first attempts and report it before any dispatch, with its remediation.
- **FR-007**: Key issuance MUST recover from an alias orphaned by a killed run without
  operator intervention, and MUST refuse to disturb an alias held by a live epic.
- **FR-008**: The agent activity's heartbeat timeout MUST be derived from the attempt's
  configured timeout rather than fixed at a small multiple of the beat interval.
- **FR-009**: Key issuance retry MUST tolerate a transient proxy outage on the order of
  a real restart before failing the epic.
- **FR-010**: `factory-epic status` MUST report the workflow's Temporal execution status
  in both human and `--json` output, distinguishable from the epic's internal state.
- **FR-011**: No requirement here may weaken 001's credential discipline: the master key
  MUST NOT reach any path that does not already hold it, and no new credential may
  appear in any payload, artifact, or error message.

### Key Entities

- **Usage observation** — whatever mechanism replaces the polling loop; carries a spend
  figure to teardown at no per-interval history cost.
- **Preflight report** — the set of findings `factory-epic start` produces before
  dispatch; pass/fail per check, each failure naming its remedy (003's onboarding
  `Finding` is the precedent and should be reused rather than reinvented).
- **Execution status** — Temporal's status for the epic's workflow, distinct from the
  `EpicStatus` document the workflow itself answers with.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A simulated four-hour attempt contributes a history event count within a
  small constant of a one-minute attempt (today: ~5,300 vs ~15).
- **SC-002**: An epic naming an unserved model alias terminates at `start` with zero
  attempts dispatched, zero keys issued, and zero tokens spent.
- **SC-003**: An epic killed mid-attempt restarts successfully with no operator call to
  the proxy admin API.
- **SC-004**: An attempt survives a Temporal unavailability window an order of magnitude
  longer than today's five seconds.
- **SC-005**: `factory-epic status` against a closed workflow reports its execution
  status; against a running one, output is unchanged from today.
- **SC-006**: The full existing suite stays green — this feature changes cost and
  honesty, not behaviour that any current test asserts.

## Work Graph

One node per story. US1 and US2 are independent: the first rewrites the attempt's inner
loop, the second adds a pre-dispatch check in the CLI, and they share no file. US3
waits on US2 because US2's preflight is what makes an orphan legible — recovery
implemented first would be recovering a condition nothing yet names. US4 waits on US1:
both tune constants that live in the attempt loop US1 rewrites, and sequencing them
avoids a merge conflict rather than a logical dependency. US5 is a leaf on the CLI.

Attempt timeouts resolve from the persona registry; no story here argues for an override.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  implements: [FR-004, FR-005, FR-006]
US3:
  depends_on: [US2]
  implements: [FR-007]
US4:
  depends_on: [US1]
  implements: [FR-008, FR-009]
US5:
  depends_on: []
  implements: [FR-010, FR-011]
```

## Assumptions

- 003 has landed, so `depends_on_merged` exists and the merge queue is available; this
  epic is the first that need not use the D-024 interim manual-merge dance.
- Budget enforcement remains deferred (D-021). If 004 is ever reactivated it will want
  live spend visibility, and US1's chosen mechanism must not foreclose that — a
  heartbeat-carried snapshot preserves it, deleting observation entirely does not.

## Decision: usage observation rides the agent heartbeat (decided 2026-08-06, Bryan)

The trade behind US1 was whether to keep a spend figure at all between polls. Two
answers were live: fold observation into the agent activity's heartbeat, or delete the
loop and let teardown make one read with real backoff, accepting an honest NULL when
the proxy is down.

**Decided: the heartbeat.** The adapter already beats every second for liveness, and
Temporal stores heartbeat *details* in mutable state rather than on the event log — so
carrying a snapshot there costs the same as deleting observation outright (zero history
events) while forfeiting nothing. Deletion would have been simpler and equally honest,
but it forecloses the live-spend visibility 004 needs if D-021 is ever superseded, and
it trades a capability for no saving. The heartbeat is also the pattern the adapter
wants on its own merits: one channel carrying both "still alive" and "here is what it
has cost so far", rather than a second mechanism polling from outside.

This is why FR-003 states the fallback as a guarantee rather than a best effort: with
the heartbeat carrying it, a NULL spend row now means "never measured", not "measured
but lost", which is a strictly stronger claim than the polling loop could make.

**The decision-log number is deliberately unassigned here.** 003's T022, T034 and T045
each record entries at "the next free D-number" and are in flight against a worktree
branched from `b1194a6`; claiming a number now would collide at merge. Assign this
entry its number in `docs/decisions.md` once 003 has landed, and before 006 is derived.
