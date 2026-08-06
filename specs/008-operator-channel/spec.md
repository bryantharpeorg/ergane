# Feature Specification: Operator Channel

**Feature Branch**: `008-operator-channel`

**Created**: 2026-08-06

**Status**: Drafted from a defect found live the same evening: 006-us1's first
attempt did excellent verification work — proved the plan's normal and timeout
snapshot-delivery paths against the installed SDK and caught that the kill-path
claim was unverified — and then stopped to ask the operator which of two designs
to take. It asked into a one-shot `claude -p` stdout that nothing reads. The
attempt completed with a deliberately clean worktree, failed the output check
(`has_diff: false`), and was charged as a failure: $2.57 and 23 minutes to
formulate a good question and have it die unheard. The operator learned of the
question only because a human went and read the transcript.

**Input**: An implementer mid-attempt has no channel to the operator. The factory
has exactly one operator channel today — ladder escalations over the Telegram
bridge — and it opens only after attempts are exhausted, which is precisely too
late for a question whose whole point is to avoid burning attempts.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A blocking question reaches the operator's phone (Priority: P1)

As the factory operator, when an agent hits a genuinely blocking design question,
I get that question as a Telegram message within a minute of the attempt ending,
so that the question starts costing me reading time instead of costing the node
an attempt and me an archaeology session.

The agent's side of the contract is one instruction in the prompt: a blocking
question is stated under a fixed heading in its final message (the exact marker
is the plan's; the final message is already captured and already read by the
output check, so no new artifact and no worktree pollution). Verification
detects the marker, classifies the attempt QUESTION rather than FAIL, and ships
the question text through the existing notify bridge.

**Why this priority**: This is the half that converts a silent burn into a
conversation. Without it nothing else in this spec exists.

**Independent Test**: Complete an attempt whose final message carries the
question marker; assert the attempt is classified QUESTION, the bridge sends
one message carrying the question text, and no FAIL is recorded.

**Acceptance Scenarios**:

1. **Given** an attempt whose final message carries the question marker, **When**
   verification runs, **Then** the attempt terminates QUESTION, the question text
   reaches the bridge, and the node parks WAITING_OPERATOR.
2. **Given** a question attempt that also committed work (tests written, then a
   fork was hit), **When** verification runs, **Then** the committed work is
   preserved on the branch exactly as a salvaged attempt's would be, and the
   question still ships.
3. **Given** an attempt with no marker, **When** verification runs, **Then**
   nothing changes from today — the marker is the only trigger, and its absence
   is the common case.
4. **Given** a question attempt, **When** its ledger row is written, **Then**
   spend and tokens are recorded exactly as today; QUESTION is a termination
   class, not an accounting exemption.

---

### User Story 2 - The answer reaches the next attempt, and the question costs no ladder slot (Priority: P1)

As the factory operator, my Telegram reply becomes part of the next attempt's
prompt verbatim, and the question attempt does not count against the node's
attempt ceiling, so that asking first is strictly cheaper than guessing wrong.

Tonight's manual equivalent: the operator's answer was encoded into plan.md and
tasks.md by hand (`39206e2`) so a future attempt would carry it. This story is
that path, without the human doing spec surgery at 6 PM.

**Why this priority**: US1 without the return path is a notification, not a
channel. The no-burn accounting is what makes agents choose asking over the
plausible-but-wrong guess.

**Independent Test**: Answer a parked question; assert the next attempt's
assembled prompt contains the answer text verbatim in a dedicated section, and
that the node's attempt count available to the ladder is what it was before the
question attempt dispatched.

**Acceptance Scenarios**:

1. **Given** a node parked WAITING_OPERATOR, **When** the operator replies to the
   question message, **Then** a new attempt dispatches whose prompt carries the
   answer verbatim under a dedicated operator-answer section.
2. **Given** a question attempt, **When** the ladder accounts attempts, **Then**
   the QUESTION termination consumed no slot: a node that could take 4 attempts
   before the question can still take 4 after it.
3. **Given** an unanswered question, **When** the configured expiry elapses,
   **Then** the node un-parks and the ladder proceeds as if the attempt had been
   a FAIL — a question may pause a node, never park it forever (the factory's
   existing escalation expiry is the precedent and the mechanism).
4. **Given** an answer, **When** it is stored and forwarded, **Then** it is
   recorded in the verification store alongside the question, so the epic's
   record shows what was asked and what was decided.

---

### User Story 3 - The attempt survives its own question (Priority: P3)

As the factory operator, an agent that asks mid-flight keeps its process and its
context alive while the answer travels, so that an answered question costs
seconds of resumed work rather than a fresh dispatch and a cold re-read of the
worktree.

The shape: the agent writes its question to a ferry file and polls for an answer
file; the monitor loop that already carries liveness (and, after 006-US1, spend)
ferries question up and answer down. No SDK change — the channel is the
filesystem the agent already owns and the beat that already runs.

**Why this priority**: Real, but it is an optimization of US1+US2, and its cost —
adapter ferry logic, poll cadence, a second file contract — should be paid only
once the v0 round trip has proven questions are frequent enough to matter. A
fresh dispatch with the answer in-prompt (US2) already recovers everything but
warm context.

**Independent Test**: Under a scripted answer arriving mid-attempt, assert the
same agent process reads it and proceeds to commit work, with no second dispatch.

**Acceptance Scenarios**:

1. **Given** an in-flight attempt that has written a question file, **When** the
   answer file appears, **Then** the same process resumes and the attempt's
   timeout clock is unaffected.
2. **Given** an in-flight question, **When** no answer arrives within the ferry
   window, **Then** the agent proceeds exactly as the US1 path — final-message
   marker, QUESTION termination — so the ferry degrades to v0, never to a hang.

---

### Edge Cases

- A question marker plus a substantive diff: the diff is preserved (US1-S2), and
  the answer-carrying retry builds on the same branch — asking must never cost
  committed work.
- A "question" that is really a status update (no question mark, no fork stated):
  the classifier's job is marker detection, not literary judgment. If the agent
  marks it, it ships; prompt guidance (not code) is what teaches agents that only
  genuinely blocking forks qualify. The spec's contract with agents: a question
  must name the fork and the options considered.
- The operator answers twice, or answers after expiry: first answer wins; a late
  answer is recorded but changes nothing — the ladder has already moved.
- Question text must be safe to leave the machine: it goes to Telegram. No
  credential value may survive into the message (the existing escalation sweep
  is the precedent; the same assertion extends to question payloads).
- Two nodes park questions concurrently: answers must route by escalation id,
  not by "the most recent question" — the bridge's reply-to threading is the
  discriminator.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: An attempt whose final message carries the question marker MUST
  terminate with a distinct QUESTION classification, not FAIL, and MUST NOT be
  charged against the node's attempt ceiling.
- **FR-002**: The question text MUST reach the operator over the existing notify
  bridge, attributed to its epic, node, and attempt.
- **FR-003**: The operator's reply MUST be delivered verbatim into the next
  attempt's prompt under a dedicated section, and MUST be persisted alongside
  the question in the verification store.
- **FR-004**: A node parked on a question MUST un-park on a configurable expiry,
  after which the ladder proceeds as if the attempt had FAILed. Expiry MUST
  reuse the existing escalation-expiry mechanism, not duplicate it.
- **FR-005**: Committed work in a question attempt's worktree MUST be preserved
  identically to a salvaged attempt's.
- **FR-006**: A question attempt's usage MUST be recorded in the ledger exactly
  as any other termination class.
- **FR-007**: No credential value may appear in a question message, an answer
  payload, or their stored records (001's discipline, extended to this channel).
- **FR-008**: Free-text operator replies MUST route to the correct parked
  question when several are open, using the bridge's message threading.
- **FR-009** *(US3 only)*: An in-attempt ferry MUST degrade to the US1 path when
  unanswered — it may never convert a question into a hang or a timeout burn.

### Key Entities

- **Question** — text extracted from an attempt's final message; carries epic,
  node, attempt, and the marker-delimited body. Stored with escalations.
- **Answer** — the operator's reply text; stored with its question, delivered
  into exactly one subsequent prompt.
- **QUESTION termination** — a new attempt-termination class, sibling to
  completed/agent_error/killed, with its own ladder routing (park, not burn).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Tonight's 006-us1 scenario, replayed: the kill-path question
  reaches Telegram within 60 seconds of attempt end, and the node still has its
  full attempt ceiling when the answer arrives.
- **SC-002**: The answer round trip — reply in Telegram to text present in the
  next assembled prompt — completes with no human touching a spec file.
- **SC-003**: An unanswered question un-parks its node at expiry and the epic
  finishes without operator action, questions notwithstanding.
- **SC-004**: A grep-backed sweep shows no key value can reach a question
  message, answer, or stored record.
- **SC-005**: The full existing suite stays green; no current escalation test
  changes meaning.

## Work Graph

US2 depends on US1 because an answer path presupposes a question path — the
stories share the store and the bridge extension, and US1 lands the vocabulary
(QUESTION termination, WAITING_OPERATOR) that US2's accounting and routing
build on. US3 is deliberately last and deliberately optional: it optimizes the
round trip US1+US2 create, and it waits on 006-US1's monitor-loop changes
landing so the two features edit the adapter's loop sequentially, not in
parallel (the same conflict-avoidance argument as 006's US4-after-US1).

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-005, FR-006, FR-007]
US2:
  depends_on: [US1]
  implements: [FR-003, FR-004, FR-008]
US3:
  depends_on: [US2]
  implements: [FR-009]
```

## Assumptions

- The notify bridge and escalation store exist and are live (they are; 003's
  escalations and tonight's operations both exercised them).
- 006-US1's heartbeat work may land before or after this feature; only US3
  sequences behind it, by the work graph above.
- Telegram remains the operator surface of record (Bryan is the POC and the
  bridge is proven). Nothing here precludes a second surface later; FR-002 names
  the bridge, not the app.

## Decision: start with the message, not the ferry (decided 2026-08-06, Bryan)

Two shapes were live: send the question as a Telegram message and answer into
the *next* attempt's prompt (v0 — US1+US2), or keep the asking attempt alive and
ferry the answer back into the same process (v1 — US3). **Decided: v0 first,
v1 explicitly deferred behind it.** The bridge, the expiry semantics, and the
retry-feedback prompt slot all exist, so v0 is nearly pure reuse; the ferry adds
adapter machinery whose value depends on how often questions actually occur —
a frequency nobody has measured yet, one live occurrence in. The deciding
argument: a fresh dispatch carrying the answer recovers everything except warm
process context, and warm context is worth paying for only if questions turn
out to be common.

**The decision-log number is deliberately unassigned here** — same reasoning as
006's heartbeat decision: D-numbers are claimed at landing time, in
`docs/decisions.md`, after whatever 003 and 006 consume.
