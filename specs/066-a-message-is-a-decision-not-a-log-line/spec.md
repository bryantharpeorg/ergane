---
state: draft
# Drafted 2026-08-19 4:35 PM CT from the operator's own screenshot of the
# Telegram channel and his verdict on it: "none of these messages are helpful."
#
# THE FOUR MESSAGES HE WAS LOOKING AT, verbatim:
#
#   7:00 AM  Roadmap roadmap-specs failed (1 consecutive run):
#            drift_for_spec(020-landing-attribution) failed: git fetch --quiet
#            origin failed in /home/admin/code/ergane-roadmap-target:
#            channel-b: refusing ref refs/tags/v0.1.0 (tags carry the v1
#            implementation) fatal: ref updates aborted by hook
#            ... and the same again for 021-roadmap-operability, and ~61 more
#
#   7:21 AM  Roadmap roadmap-specs recovered after 1 consecutive failure.
#
#   8:49 AM  Roadmap roadmap-specs failed (1 consecutive run):
#            'NoneType' object has no attribute 'epic_state'
#
#   4:05 PM  Roadmap roadmap-specs failed (3 consecutive runs):
#            'NoneType' object has no attribute 'epic_state'
#
# A CORRECTION THIS SCREENSHOT FORCED, and it is why this spec is worth more
# than it looks. 065's own spec text asserts "No page fires" for the scheduler
# wedge. That is WRONG, and the 8:49 AM and 4:05 PM messages disprove it: the
# operator WAS told, twice, hours apart. 065 landed 3/3 before the error was
# caught, so the false sentence is in the tree.
#
# The real defect is worse than the one 065 described. It was never that the
# operator was not told. It is that being told changed nothing, because
# "'NoneType' object has no attribute 'epic_state'" does not tell a person that
# their factory has stopped building, that nothing will build until they act, or
# what the act is. The floor idled 1h49m in the morning and roughly 1h38m in the
# afternoon with those pages sitting unread-because-unreadable on his phone.
#
# The one message in the corpus that already does this right is the escalation:
# "No answer by <time> applies the default: KILL the node." It states the
# consequence of silence. Every other message should be held to that standard.
#
# Related finding, folded in as US3 rather than left separate:
#   roadmap/failure-notices-have-no-dedupe-and-flood-the-operator
---

# Feature Specification: a message is a decision, not a log line

**Created**: 2026-08-19

## The gap, stated precisely

Ergane's operator channel forwards internal failure text to a human phone. A
Python exception repr, a shell stderr tail, and a spec-dir loop variable all
reach the operator unedited.

The operator's own summary, after a day in which two separate outages paged him
correctly and he acted on neither: **"none of these messages are helpful."**

He was right, and the diagnosis is precise. Every message answers *what threw*.
None answers the three things a person holding a phone actually needs:

1. **What has stopped**, in consequences rather than in symptoms.
2. **What it costs to do nothing**, which is the question every notification is
   implicitly asking.
3. **What the options are**, named as actions the operator can take.

`'NoneType' object has no attribute 'epic_state'` is a true statement about a
stack frame and a useless statement about a factory. What it meant was: *the
scheduler is dead, nothing will build until you clear it, and here is the
command.* Nobody could have derived the second sentence from the first without
reading the source — which is the same complaint that produced the whole 059-064
on-ramp set, arriving now on a different surface.

## What "helpful" means here, concretely

The corpus already contains one message that gets this right. The escalation
ends:

> No answer by `<expires_at>` applies the default: KILL the node.

That single sentence does everything the others do not: it names the default,
names the deadline, and makes silence an informed choice rather than an
accident. It is the template. This spec generalises it.

**A message is a decision aid.** If there is nothing to decide, it is a heartbeat
and should be rare. If there is something to decide, it states the decision.

## User Scenarios & Testing

### User Story 1 - A failure message says what stopped and what it blocks (Priority: P1)

As an operator reading my phone, I learn what has stopped working and what it
costs me, without opening a terminal.

**Why this priority**: P1. It is the whole complaint. Two outages paged
correctly today and neither page communicated that the factory had stopped.

**Independent Test**: render a notice for a known internal failure and assert
the rendered text states the impact and contains no raw exception text.

**Acceptance Scenarios**:

1. **Given** an internal failure whose text is a Python exception repr, **When**
   the operator notice is rendered, **Then** the body states what has stopped in
   terms of the factory's own vocabulary — dispatch, landing, an epic, a spec —
   and does **not** contain the exception repr — proven by a committed test
   asserting both, using `'NoneType' object has no attribute 'epic_state'` as
   the input, because that is the string that actually failed a human.
2. **Given** the same, **When** the notice is read, **Then** it states the blast
   radius: what will not happen until this is resolved — proven by a committed
   test. "The scheduler failed" and "nothing will build until you act" are
   different messages and only the second is actionable.
3. **Given** an internal failure the composer has no specific rendering for,
   **When** the notice is rendered, **Then** it still states impact and options
   generically, and carries a pointer to where the verbatim text can be read —
   proven by a committed test over an unrecognised failure. A composer that
   degrades to the raw text for anything it does not recognise has not changed
   the operator's experience, it has only postponed it.
4. **Given** the diff, **When** the verbatim failure text is looked for, **Then**
   it is still recorded durably where an operator can retrieve it — proven by a
   committed test asserting the record. Making the page readable must not
   destroy the evidence; the message and the record are different artifacts with
   different audiences.
5. **Given** a rendered notice, **When** its length is measured, **Then** it fits
   a phone screen without scrolling past the actionable part — proven by a
   committed test asserting the impact and options appear before any detail.
   The 7:00 AM message put six lines of shell stderr above everything that
   mattered.

---

### User Story 2 - Every message states the options and what silence does (Priority: P1)

As an operator, I can decide from the message itself, and I know what happens if
I decide nothing.

**Why this priority**: P1. This is the operator's literal request: a brief
description of the issue and the options to make the decision.

**Independent Test**: render each message kind and assert each names its options
and its default-on-silence.

**Acceptance Scenarios**:

1. **Given** any operator-facing failure notice, **When** it is rendered,
   **Then** it names the options available — proven by a committed test over
   every notice kind. Options are actions, not descriptions: "terminate the run
   so a fresh one starts" is an option; "the workflow is in a failed state" is
   not.
2. **Given** any operator-facing notice, **When** it is rendered, **Then** it
   states what happens if the operator does nothing — proven by a committed test
   over every notice kind. This is the escalation's existing sentence
   generalised, and it is the single highest-value line in the corpus.
3. **Given** a notice for a condition that will not clear itself, **When** it is
   rendered, **Then** it says so explicitly — proven by a committed test. The
   scheduler wedge never cleared on its own; a message that reads like a
   transient error invites exactly the waiting that cost two hours today.
4. **Given** a notice for a condition that will retry, **When** it is rendered,
   **Then** it states when — proven by a committed test. "I will try again in
   five minutes" is often the whole message, and it converts an alarm into an
   acknowledgement.
5. **Given** the diff, **When** an option names a command, **Then** the command
   is one the CLI actually resolves — proven by a committed test that runs each
   named command's `--help`, reusing the sweep in `tests/page_holds_true.py`
   rather than writing a second one. A message that recommends a command that
   does not exist is worse than one that recommends nothing.

---

### User Story 3 - One cause is one message (Priority: P2)

As an operator, a single fault that touches fifty specs pages me once.

**Why this priority**: P2 only because US1 and US2 make each individual message
worth reading. Sixty-three readable messages is still an unusable phone.

**Independent Test**: drive one persistent fault across a full corpus pass and
assert the operator receives one notice.

**Acceptance Scenarios**:

1. **Given** a fault that fails every spec in one pass with texts differing only
   by spec name, **When** the pass completes, **Then** the operator receives one
   notice naming the count of affected specs — proven by a committed test. On
   2026-08-19 this shape produced 63 messages in six minutes.
2. **Given** the same fault persisting across consecutive passes, **When** later
   passes run, **Then** repetition is throttled — proven by a committed test.
   `_should_notify_failure` already throttles geometrically and was defeated
   because each message named a different spec dir, so the count never rose
   above one. The throttle is right; what it keys on is wrong.
3. **Given** two genuinely different faults in one pass, **When** the pass
   completes, **Then** both are reported — proven by a committed test.
   Collapsing distinct causes is a worse failure than repeating one.
4. **Given** a fault that clears, **When** recovery is reported, **Then** the
   notice states what resumed, not only that recovery happened — proven by a
   committed test. "Recovered after 1 consecutive failure" does not tell an
   operator whether their work started moving again.

### Edge Cases

- **A failure text that contains a credential.** The composer must not widen the
  leak surface; `factory/controlplane/config.py`'s secret patterns already exist
  and the notice path should use them.
- **A notice rendered when no options exist.** Say so — "nothing to decide, this
  is for your awareness" is a legitimate and short message.
- **The heartbeat.** `💚 ergane stack healthy` has no decision and should stay
  short and rare; this spec must not turn it into a paragraph.

## Requirements

### Functional Requirements

- **FR-001**: An operator notice MUST state what has stopped in factory
  vocabulary and MUST NOT contain a raw exception repr or shell stderr.
- **FR-002**: It MUST state the blast radius — what will not happen until it is
  resolved.
- **FR-003**: An unrecognised internal failure MUST still produce an
  impact-and-options notice, with a pointer to the verbatim text.
- **FR-004**: The verbatim failure text MUST remain durably recorded and
  retrievable.
- **FR-005**: The actionable part of a notice MUST precede any detail.
- **FR-006**: Every operator-facing notice MUST name the available options as
  actions.
- **FR-007**: Every operator-facing notice MUST state what happens on silence.
- **FR-008**: A notice MUST state whether the condition clears itself, and when
  it will retry if it does.
- **FR-009**: Any command a notice names MUST resolve, proven by the existing
  page sweep.
- **FR-010**: One cause affecting many specs in one pass MUST produce one
  notice naming the affected count.
- **FR-011**: Throttling MUST key on the cause, not on the rendered text.
- **FR-012**: Distinct causes in one pass MUST both be reported.
- **FR-013**: A recovery notice MUST state what resumed.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: [US1]
  implements: [FR-006, FR-007, FR-008, FR-009]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-010, FR-011, FR-012, FR-013]
```

US2's edge on US1 is a **pass** edge: options and silence-defaults attach to the
notice structure US1 establishes, and building them against the current
free-text composer would produce a second structure that US1 then replaces.

US3's edge on US1 is a **merge** edge for contention on
`factory/notify/messages.py`. Its own logic lives in the roadmap's failure
recording and is independent, but both stories edit the composer.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Re-rendering the four messages from the 2026-08-19 screenshot
  produces text that states impact and options — evidenced by the before-and-
  after of all four committed in the diff.
- **SC-002**: A reader who is not an Ergane maintainer can say, from any notice
  alone, what has stopped and what their choices are.
- **SC-003**: The 2026-08-19 fetch fault, replayed across a full corpus pass,
  produces one notice rather than 63 — evidenced by committed test output.
- **SC-004**: No notice names a command that does not resolve.

## Assumptions

- The escalation's existing "no answer by X applies the default" sentence is the
  model, not a special case. Where a notice has no default to state, saying
  "this will not clear itself" is the equivalent.
- Making messages readable does not reduce what is recorded. The journal and the
  findings ledger keep the verbatim text; the phone gets the decision.
- The operator wants fewer messages, not more. A spec that improves quality and
  raises volume has failed.
