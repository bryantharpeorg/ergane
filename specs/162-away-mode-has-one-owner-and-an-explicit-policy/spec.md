---
state: draft
depends_on_landed:
  - 157-one-operator-contract-serves-both-clients
  - 158-operator-skills-report-and-act-by-declared-intent
  - 161-a-codex-worker-proves-its-deployment
---

# Feature Specification: away mode has one owner and an explicit policy

## Provenance and authority

This spec is work package H. It preserves the operator's approved away policy
while replacing one-session wakeup state with a durable owner and action journal.
It is an operator assistant, not a second factory scheduler: Temporal remains the
only component that decides which ready spec dispatches.

Away mode exists only after the operator explicitly enables it with a target,
deadline, and allowed actions. The preserved action set is: advance verified
landings, attest completion, request dispatch of dispatchable work, answer
grounded builder questions, and file findings. Its prohibitions remain:
escalation decisions, deletion, host provisioning or live unit changes, live
factory-code modification, held-state overrides, and unattended memory retention.

Activation remains held until spec 161 has landed and its supervised-pilot
evidence is accepted. A rendered task definition or synthetic binding fixture is
not proof that a client scheduled, fired, or notified.

### User Story 1 - Enabling away mode creates one durable, bounded authority (Priority: P1)

As an operator leaving the floor, I can state exactly what one away owner may do,
where, and until when.

**Acceptance Scenarios**:

1. **Given** no active owner, **When** the operator explicitly starts away mode with repository, runtime root, target branch, deadline, notification intent, and an allowlist drawn from the preserved action set, **Then** one durable state record is created with a unique owner/run id and every omitted action remains denied — proven by parser and temporary-store tests.
2. **Given** an attempt to authorize escalation decisions, deletion, host provisioning, live unit changes, live factory-code edits, held-state override, memory retention, or a second scheduler, **When** start parses the policy, **Then** it refuses each prohibited authority by stable code — proven by table-driven tests.
3. **Given** an active owner, **When** another client tries to start or take over the same target, **Then** it receives the current redacted owner, heartbeat, deadline, and stop remedy and cannot silently replace it — proven by concurrent start tests.
4. **Given** the deadline is absent, expired, or beyond the configured operator safety bound, **When** start or resume runs, **Then** it refuses or transitions to stopped without scheduling another tick — proven by fixed-clock tests.

**Why this priority**: A wakeup loop without durable authority cannot prove who may act after a restart.

**Independent Test**: Create and contend over a temporary away store with no Temporal, forge, or notification connection.

### User Story 2 - Each tick observes before one generic journaled action (Priority: P1)

As the away owner, I make an idempotent observation and action decision without
embedding five operation-specific adapters in the journal mechanism.

**Acceptance Scenarios**:

1. **Given** an active owner, **When** a tick begins, **Then** it records its observation cursor and reads through the pure status/escalation/attempt/spec surfaces from 158 before proposing any action — proven by ordered-call tests with mutation seams denied during observation.
2. **Given** one generic eligible action from an injected fake executor, **When** policy authorizes it, **Then** the tick writes an intent record before execution, uses a stable idempotency key, records result/evidence afterward, and a replay cannot perform the action twice — proven by a journal-mechanism test.
3. **Given** an action is not allowlisted, a spec is held, evidence is unavailable, or the action is prohibited, **When** the tick evaluates it, **Then** it records a no-action reason and performs nothing — proven by policy-matrix tests.

**Why this priority**: Transaction locking alone does not preserve ownership or prevent duplicate actions across turns.

**Independent Test**: Replay one generic allowed action and every denial twice against fakes and compare journal/call differences.

### User Story 5 - Typed actions and notifications obey closed evidence policies (Priority: P1)

As the away owner, I can enable each supported operation separately and remain
quiet or abstain when its required evidence is missing or ambiguous.

**Acceptance Scenarios**:

1. **Given** each of the five allowed action kinds, **When** its adapter is evaluated, **Then** a closed table names the existing typed operator command, exact required current evidence, idempotency identity, and forbidden state; production code does not call workflow internals or infer an action from prose — proven by table-driven fake-executor tests.
2. **Given** a builder asks a question, **When** the answer is an exact fact present in the current authoritative spec/decision evidence and selects no escalation option or tradeoff, **Then** the answer action may be proposed; ambiguous, stale, free-form, or decision-bearing questions abstain and notify the operator — proven by positive and abstention fixtures.
3. **Given** state and observations are unchanged and no user decision is required, **When** the tick completes, **Then** it emits no notification and records only its bounded heartbeat/cursor update — proven by a quiet-notifier fake.
4. **Given** completion, meaningful change, failure, abstention, or required user action, **When** the tick completes, **Then** it emits one redacted notification carrying the journal reference and schedules no duplicate notification for the same event — proven by deduplication tests.

**Why this priority**: A generic journal proves ordering, not that each real action has sufficient evidence or that a notification will not duplicate.

**Independent Test**: Exercise every action/evidence row and notification state with injected adapters after the generic journal exists.

### User Story 3 - Each client binding declares what it can actually schedule (Priority: P1)

As an operator, I can use Codex desktop or Claude scheduling when available and a
single explicit tick when the current client cannot schedule.

**Acceptance Scenarios**:

1. **Given** the Codex desktop app contract, **When** the away skill renders a binding, **Then** it produces one project-scoped task definition whose saved prompt contains owner/run id, target, deadline, allowed actions, quiet-notification policy, and stop conditions and reports only `definition rendered` — proven by a captured definition fixture and contract test.
2. **Given** Codex CLI or the IDE extension, **When** scheduling is requested, **Then** the skill reports that scheduled-task management is unavailable there and offers the explicit single-tick command without inventing a Python `ScheduleWakeup` API — proven by capability fixtures.
3. **Given** Claude exposes its wakeup and notification tools, **When** the same policy is bound, **Then** only harness-specific scheduling/notification syntax differs; the durable owner and tick contract remain identical — proven by normalized binding tests.
4. **Given** a binding is missing, fails, or loses notification permission, **When** bind or tick runs, **Then** the durable state reports unavailable/failed, no authority widens, and an explicit tick remains possible — proven by failure-path tests.
5. **Given** separately authorized live qualification for a supported client/version, **When** the binding is actually created and a disposable run fires, **Then** state advances separately through `binding created` and `verified fired/notified` with redacted evidence; absent evidence cannot activate away mode — proven by a qualification-evidence parser and state tests.

**Why this priority**: A skill file cannot schedule itself, and the clients do not share one scheduling API.

**Independent Test**: Normalize Codex desktop, Codex CLI/IDE, Claude, and unavailable fixtures into the same owner state without contacting a live scheduler.

### User Story 4 - Stop and recovery outlive client restarts (Priority: P1)

As an operator, I can stop one away run permanently, and a restarted client can
recover without stealing or duplicating its work.

**Acceptance Scenarios**:

1. **Given** an active run, **When** the operator stops it, its deadline expires, or its terminal goal is reached, **Then** durable state becomes stopped before the binding is cancelled and every later tick exits without action or notification — proven by crash-point tests.
2. **Given** a crash before or after action execution or notification, **When** a client restarts, **Then** it resumes from the journal cursor, reconciles any in-doubt intent by its idempotency key, and neither repeats nor loses the recorded action — proven by replay tests at every boundary.
3. **Given** the scheduler binding cannot be cancelled, **When** stop runs, **Then** the durable stop still makes future wakeups no-ops and the status reports the binding cleanup failure separately — proven by a failing-cancel fake.
4. **Given** two clients wake near-simultaneously, **When** both tick the same run, **Then** one short transaction claims that tick, the other exits quietly, and ownership persists after the transaction releases — proven by concurrent tests.

**Why this priority**: Stop is a durable policy state, not merely cancellation of the currently visible timer.

**Independent Test**: Drive a temporary run through every crash point and dual-client wake, then assert one action history and permanent stop.

## Functional Requirements

- **FR-001**: Away mode MUST require explicit start with target, deadline, notification intent, and an action allowlist; omitted actions MUST be denied.
- **FR-002**: Allowed action kinds MUST be limited to advancing verified landings, attesting completion, requesting dispatchable work, answering grounded builder questions, and filing findings.
- **FR-003**: Escalation decisions, deletion, host provisioning/live unit changes, live factory-code modification, held-state override, unattended memory retention, and a second scheduler MUST remain prohibited.
- **FR-004**: Exactly one durable owner/run MUST exist per target and a second client MUST NOT silently take it over.
- **FR-005**: Every tick MUST observe through read-only surfaces before considering action.
- **FR-006**: Every action MUST use intent-before-execution journaling, a stable idempotency key, result evidence, and replay reconciliation.
- **FR-007**: A denied, held, or unprovable action MUST produce no mutation.
- **FR-008**: Unchanged non-actionable ticks MUST remain quiet; notification occurs only for meaningful change, completion, failure, or required user action.
- **FR-009**: Scheduling and notification MUST be client bindings around one shared durable policy, not names hardcoded into the policy model.
- **FR-010**: Codex CLI and IDE MUST report scheduled management unavailable and MUST support an explicit single tick.
- **FR-011**: Codex desktop scheduling MUST use the actual scheduled-task surface and a project-scoped saved prompt; it MUST NOT invent a universal Python API.
- **FR-012**: Durable stop MUST precede binding cancellation and MUST make every later wakeup a no-op even when cancellation fails.
- **FR-013**: Recovery MUST reconcile in-doubt journal intents and MUST not duplicate actions or notifications.
- **FR-014**: Temporal MUST remain the only factory scheduler; away mode may request existing typed operator actions only.
- **FR-015**: Binding status MUST distinguish `definition rendered`, `binding created`, and `verified fired/notified`; fixtures alone MUST NOT produce the last two states.
- **FR-016**: Away-mode activation MUST remain held until spec 161's supervised pilot and separately authorized live scheduler/notification qualification are accepted.
- **FR-017**: Each allowed action MUST use a closed typed-command/evidence/idempotency policy; a builder answer MUST be an exact current authoritative fact and MUST abstain from ambiguous, stale, free-form, tradeoff, or escalation-choice questions.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007]
US5:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-017]
US3:
  depends_on: []
  depends_on_merged: [US1, US5]
  implements: [FR-009, FR-010, FR-011, FR-015, FR-016]
US4:
  depends_on: []
  depends_on_merged: [US2, US3, US5]
  implements: [FR-012, FR-013, FR-014]
```
