---
state: landed
# Attested landed 2026-08-16 by an operator session, after `ergane spec landed
# specs/041-escalation-workflow --default-branch ergane-buildout` observed every
# story in git: US1 63b52d85, US2 1461b424, US3 faa4e7fd, US4 1fdac912.
# Every story passed the real bwrap boundary gate and an LLM judge on a diff
# measured through `size_refusal`. US1 and US2 landed on diffs later found to
# exceed the judge's input ceiling -- 93,381 and 131,078 bytes -- because the
# operator's driver called `run_judge` directly and skipped the admission
# control `check_output` runs in front of it (045 FR-003). Both were re-judged
# by chunking on 2026-08-16: US1 4 of 4, US2 7 of 7 on the union. Nothing was
# reverted, and the driver now refuses an oversized diff.
# Split out of 033-ergane-install on 2026-08-13. 033 as drafted carried seven
# stories across three unrelated domains — a config parser, a Temporal workflow
# type, and systemd unit management. This spec is the middle one: escalation
# lifecycle and the transport seam beneath it. Was 033's US5 and US6; its
# FR-001..FR-004 were 033's FR-009, FR-010, FR-011 and FR-015.
#
# The four-story shape is deliberate and is 032's lesson applied. 032 was
# killed at attempt four (128M tokens) because one story required a fail-first
# reproduction and its fix in a single diff, which no agent could satisfy
# against both the gate and the judge. The equivalent hazard here is US3: it
# refactors live, load-bearing 008 code with the operator channel in daily use.
# So the new workflow type (US2) lands and is proven STANDALONE before US3
# migrates the existing consumer onto it, and US3's whole criterion is that
# 008's behavior suite is unchanged.
depends_on_landed: [008-operator-channel, 033-ergane-install]
---

# Feature Specification: Escalation is a workflow, and its transport is an adapter

**Feature Branch**: `041-escalation-workflow`

**Created**: 2026-08-13


**Input**: An operator challenge during the 2026-08-11 provisioning session —
"shouldn't an escalation be a Temporal-hosted thing, a workflow type?" —
checked against the tree, and the messenger-seam direction from the same
session: "escalation messaging (Telegram today, with a bring-your-own-messenger
seam like hermes/openclaw)."

## What 008 already got right, and the one thing it did not

Checked against the tree, 008 is already Temporal-hosted where it matters. The
epic workflow's durable timer is the sole authority on expiry — the notify
bridge deliberately does not own the clock — and answers travel as Temporal
signals: `escalation_resolved(escalation_id, choice)`
(`factory/workgraph/workflow.py:571`) and its sibling
`question_answered(question_id, answer_text)` (`:582`). The SQLite row is
delivery evidence and press arbitration; the guarded UPDATE settles exactly the
races SQL is the right tool for — a double press, a press racing expiry, a
bridge restarted mid-hour with no state of its own. It is never the lifecycle.

What 008 did **not** build is a workflow *type*. The lifecycle is welded into
the epic workflow's park: `wait_condition` with a timeout at
`workflow.py:1974` for escalations and `:1407` for questions, each followed by
an expiry activity. Any consumer without an epic — a supervision alert, a
`--verify` test escalation, a future peer channel — cannot use it without
faking an epic. The 017 peer-park deadlock is standing evidence of what that
welding costs the second consumer: a peer park reusing 008's operator park
pauses the scheduler and deadlocks the answering peer, which is why 017 has
been held at draft rather than built.

So this spec extracts the lifecycle into an **EscalationWorkflow**, and puts an
adapter under its delivery step.

## The messenger seam, precisely

An adapter implements outbound `deliver(rendered message, correlation id)` and
inbound relay of `(correlation id, reply text, sender identity)` — nothing
else. The factory side of the seam turns an inbound relay into a signal on the
EscalationWorkflow named by the correlation id. Everything that makes
escalation *escalation* — the workflow lifecycle, expiry, answer-once, and the
standing rule that nothing ever presses an escalation button on the operator's
behalf — stays factory-side and messenger-agnostic.

Two adapters ship. `telegram` is the reference: today's behavior refactored
behind the interface, byte-compatible with the live channel. `webhook` is the
universal glue — outbound POST to a configured URL, inbound via
`ergane answer <correlation-id> <text>` — so Signal, Slack, email or a wall
display can be bridged by the operator in a few lines without ergane knowing
the messenger exists.

What multi-user messengers add is an identity problem Telegram's single chat
never had. The adapter therefore reports *who* replied, and the factory checks
that identity against a configured authorized-responders list before accepting
an answer. An unauthorized reply is recorded and ignored, never an answer.

**The adapter must be a plain library**, callable from a Temporal activity and
from a non-Temporal process alike — because 042's supervision probe calls it
directly to report that Temporal is down, and an alert about a dead
orchestrator cannot be hosted by the orchestrator.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The transport is an adapter, and Telegram is the reference (Priority: P1)

As the factory, I deliver a rendered message and ferry a reply through an
interface, not through a concrete messenger's API. The `telegram` adapter is
today's code moved behind that interface with no behavioral change: the
existing operator-channel suite passes unmodified, and the live channel sees
byte-identical messages.

**Why this priority**: everything else in this spec and one story in 042 sit on
this interface. It is also the cheapest it will ever be — Telegram's footprint
today is two environment variables, one send call, and the bridge's ferry loop.

**Independent Test**: the full 008 question round trip — ask, deliver, answer,
resume — passes against a fake adapter registered in tests; the telegram
adapter passes the existing live-channel suite unmodified.

**Evidence rule for every scenario below**: the judge is given the diff and
these criteria — never a terminal, never the base tree (constitution VIII).
Runtime claims are met by tool output pasted verbatim into a comment block in
the test file.

**Acceptance Scenarios**:

1. **Given** the telegram adapter configured, **When** the existing operator
   channel suite runs, **Then** it passes unmodified — the refactor is
   invisible at the protocol layer, and the diff shows no assertion changed to
   accommodate it.
2. **Given** the adapter interface, **When** the diff is inspected, **Then** it
   declares exactly two operations — outbound deliver of a rendered message
   plus correlation id, inbound relay of correlation id, reply text and sender
   identity — and no adapter code path can acknowledge, answer, or expire
   anything.
3. **Given** the adapter, **When** it is called from a plain Python process
   with no Temporal client and no workflow context, **Then** it delivers — the
   diff contains a test that does exactly this, because 042's supervision probe
   is that caller and it runs when Temporal is dead.
4. **Given** a fake adapter registered in tests, **When** the 008 question
   round trip runs against it, **Then** ask, deliver, answer and resume all
   behave as they do over Telegram.

---

### User Story 2 - Escalation is a workflow type (Priority: P1)

As any part of the factory that needs a human, I start an
`EscalationWorkflow` and either await its result or walk away. Its ID is the
correlation id; delivery runs as an activity through the configured adapter;
expiry is the workflow's own durable timer; the answer arrives as a signal; the
result is `answered(text, identity)` or `expired`. Store rows are written at
each transition as evidence and keep their press-arbitration role — they are
never the lifecycle authority.

**Scope fence**: this story builds the type and proves it standalone and as a
child of a test parent. It does **not** touch the epic workflow's existing
park. That migration is US3, deliberately separated — see the frontmatter.

**Why this priority**: every epic-less escalation needs a lifecycle that does
not require faking an epic, and operability improves for free: "what is waiting
on me" becomes a Temporal query over running workflows instead of a SQL scrape.

**Independent Test**: on a dev server with a fake adapter, a standalone
EscalationWorkflow round-trips — deliver, signal an answer, result carries the
text and identity; a second run receives no signal and returns expired at its
deadline; a test parent awaiting the child observes the same results with no
timer or signal handling of its own.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** a caller with nothing to await, **When** it starts the workflow
   standalone, **Then** the full lifecycle — deliver, await, expire-or-answer,
   record — runs with no parent, and the result is `answered` or `expired`.
2. **Given** a test parent that needs an operator answer, **When** it starts an
   EscalationWorkflow as a child and awaits it, **Then** answer and expiry both
   arrive as the child's result, and the parent contains no expiry timer and no
   signal handler of its own.
3. **Given** an answer signal and the expiry timer racing, **When** both fire,
   **Then** exactly one outcome wins deterministically, the store records the
   loser as late evidence, and no error escapes.
4. **Given** open escalations, **When** the operator runs
   `ergane escalations list`, **Then** every unanswered escalation appears with
   its question and its deadline, and the list drains as answers and expiries
   land — sourced from running workflows, not from a SQL scrape.
5. **Given** the workflow, **When** the diff is inspected, **Then** no code
   path in it reads the process environment from workflow scope — 039's guard
   covers every workflow-defining module by construction, and a new workflow
   module is exactly the case it was built for.
6. **Given** a lifecycle that reaches any terminal state — answered through any
   channel, or expired — **When** the workflow completes, **Then** no pending
   row remains for it in the store: settlement is the workflow's own
   transition, never the delivery channel's. The live store proves this is not
   inherited: fourteen escalations and every question ever asked sit unsettled
   today because write-back belonged to whichever channel answered. Proven by a
   committed test that drives one lifecycle per channel and asserts the row.
7. **Given** a stored escalation carrying CI check evidence, **When** it is
   read back from the store, **Then** the evidence survives the round trip, and
   `typing.get_type_hints(EscalationRecord)` resolves without error — today the
   field is silently dropped on read and the annotation names a module the file
   never imports. Proven by a committed test.

---

### User Story 3 - The epic park becomes parent-awaits-child (Priority: P2)

**Three questions US2 left open, answered by the operator session on 2026-08-16
so this story does not re-litigate them:**

- **The package is `factory/escalation/`.** Not a preference — 002's own sweep
  forbids a workflow module under `factory/notify/`, and it failed US2's first
  full run, so the move was forced and the name is accurate. US3 and US4 import
  from there. This gets more expensive to change with every story that lands.
- **`EscalationOutcome.late` stays returned, not persisted.** US2-S3 says "the
  store records the loser as late evidence"; US2 read that as the store
  recording the *winner* — the guarded UPDATE untouched by the loser — with the
  losing proposal carried home on the outcome. That reading is accepted. The
  stricter one needs a column and a migration and no scenario demands it. The
  ambiguity is resolved here rather than left for the next agent to guess.
- **The row's `workflow_id` pointing at the escalation workflow is the intended
  migration path.** It is precisely what lets the existing `CallbackBridge`
  signal the child unchanged, which makes this story's migration the cheapest
  correct one. Build on it rather than re-pointing it.

As the epic workflow, I stop owning escalation lifecycle: my park becomes
starting an EscalationWorkflow child and awaiting its result. Observable
behavior does not change — same messages, same expiry, same answers, same
store rows.

**Why this priority**: it is the migration that makes the extraction real, and
it is the riskiest work in this spec because the operator channel is in daily
use. It rides behind US2 precisely so the new type is already proven when this
story begins, and its criterion is a suite that does not change.

**Independent Test**: the landed 008 behavior suite passes with the park
re-expressed, with no assertion edited to accommodate the refactor; the
question park and the escalation park both migrate; a live escalation delivers,
is answered, and resumes the epic exactly as before.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** the landed 008 behavior suite — `tests/test_notify.py`,
   `tests/test_notify_activities.py`, `tests/test_operator_question.py`,
   `tests/test_question_delivery.py`, `tests/test_question_reply.py` — **When**
   the epic park is re-expressed as parent-awaits-child, **Then** the suite
   passes and the diff shows those five files unchanged — a suite edited to
   accommodate a refactor has stopped being a guard.
   <!-- The five filenames were added on 2026-08-16, after the judge failed this
   scenario for an assertion changed in `tests/test_interpreter.py`. The plan
   enumerates the suite exhaustively and that file is not in it — it is the
   002/005/006 interpreter suite — but the criterion named no files, and the
   judge sees the diff and the criteria and nothing else (D-037). A criterion
   that requires reading `plan.md` to be checkable is not checkable by the
   audience it was written for. The judge's reading was the only one available
   to it. -->
2. **Given** the epic workflow after migration, **When** the diff is inspected,
   **Then** it holds no escalation expiry timer and no escalation signal
   handler of its own; both belong to the child.
3. **Given** a parked node whose escalation expires, **When** expiry fires,
   **Then** the epic observes the same terminal state and writes the same store
   rows it does today.
4. **Given** the 017 peer-park hazard, **When** the diff is inspected, **Then**
   awaiting an escalation child does not pause the epic's scheduler — the
   deadlock 017 was held at draft over is structurally impossible for a second
   consumer, and a test proves a second concurrent escalation is not blocked by
   the first.
5. **Given** the operator verbs `ergane build answer` and `ergane build resolve`
   — which today signal the epic's own handlers, the exact handlers this story
   deletes — **When** the migration lands, **Then** both verbs still work,
   proven by a committed test, and a resolution sent through either one settles
   its store row exactly as a Telegram button press does. Today it does not:
   only the button path writes the row
   (`interpreter/resolved-escalation-never-clears-in-the-store`, recurred), and
   a migration that silently broke or half-migrated these verbs would take the
   operator's daily tools with it.

---

### User Story 4 - Any messenger, and only authorized answers (Priority: P2)

As an operator, I set `escalation.adapter = "webhook"` and the entire protocol
works identically over it: the rendered message and correlation id POST to my
URL, and I answer with `ergane answer <correlation-id> <text>`. Whatever the
adapter, a reply becomes an answer only if its sender identity is in the
configured authorized-responders list.

**Why this priority**: the webhook adapter is the extension point that makes
the seam worth having, and identity is the problem it introduces — Telegram's
single chat never had one.

**Independent Test**: the full round trip passes over the webhook adapter with
a test HTTP listener and `ergane answer` as the inbound path; an answer from an
identity not in the authorized list does not resume the waiting workflow, and a
subsequent authorized answer does.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** the webhook adapter configured with a test HTTP listener, **When**
   a question is asked, **Then** the listener receives the rendered message and
   the correlation id, and `ergane answer <id> "ship it"` resumes the waiting
   workflow with that text.
2. **Given** an inbound reply whose sender identity is not in
   `escalation.authorized_responders`, **When** it is ferried, **Then** the
   waiting workflow does not resume, the reply is recorded with its identity,
   and the escalation's expiry clock is untouched.
3. **Given** that same escalation, **When** an authorized reply arrives after
   the unauthorized one, **Then** it is accepted normally — ignoring an
   intruder must not poison the question.
4. **Given** any adapter, **When** an escalation expires unanswered, **Then**
   expiry fires from the EscalationWorkflow's own durable timer and is recorded
   by a factory activity — no adapter code path can expire, answer, or
   acknowledge.

---

### Edge Cases

- The webhook endpoint is down at delivery time: the delivery failure is
  recorded on the escalation record (the existing pending → delivered
  distinction already models this); retry and expiry semantics are unchanged.
- A relay arrives for a correlation id with no running workflow (answered,
  expired, or never existed): recorded as late evidence, no error escapes, the
  operator's `ergane answer` reports which of the three it was.
- Two adapters configured: refused at config parse time by 033's closed-set
  rule, not discovered here.
- An adapter raises: delivery is an activity, so Temporal's retry policy
  applies; the workflow's expiry timer is unaffected, because expiry is the
  workflow's and not the transport's.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The escalation transport MUST be an adapter with an interface of
  exactly: outbound delivery of a rendered message plus correlation id;
  inbound relay of correlation id, reply text, and sender identity. Lifecycle,
  expiry, answer-once, and delivery-state tracking remain factory-owned; no
  adapter MAY acknowledge, answer, or expire.
- **FR-002**: The adapter MUST be a plain library, callable from a Temporal
  activity and from a non-Temporal process alike, with no workflow context and
  no Temporal client required.
- **FR-003**: Two adapters MUST ship: `telegram`, byte-compatible with the live
  channel (the existing suite passes unmodified), and `webhook` (outbound POST
  of rendered message plus correlation id; inbound via a new
  `ergane answer <correlation-id> <text>` verb).
- **FR-004**: Escalation lifecycle MUST be hosted by a dedicated
  `EscalationWorkflow` type: workflow ID is the correlation id; delivery is an
  activity through the configured adapter; expiry is the workflow's own durable
  timer; the answer arrives as a signal; the result is
  `answered(text, identity)` or `expired`.
- **FR-005**: The workflow MUST be startable as a child, whose parent awaits the
  result, and standalone, by callers that walk away.
- **FR-006**: Store rows MUST be written at each transition as evidence and MUST
  retain their press-arbitration role — the guarded UPDATE settles duplicate and
  racing replies. They MUST NOT be the lifecycle authority.
- **FR-007**: An answer signal racing the expiry timer MUST resolve to exactly
  one deterministic outcome, with the loser recorded as late evidence and no
  error escaping.
- **FR-008**: `ergane escalations list` MUST enumerate every open escalation
  with its question and deadline, sourced from running EscalationWorkflows
  rather than from a store scrape.
- **FR-009**: The epic workflow's existing park MUST be re-expressed as
  parent-awaits-child with observable behavior unchanged — same messages, same
  expiry, same answers, and the same store rows in every field but one:
  `workflow_id` now names the `EscalationWorkflow`/`QuestionWorkflow` that is
  waiting rather than the epic. The landed 008 behavior suite (the five files
  named in US3-S1) MUST pass with no assertion edited.
  <!-- The `workflow_id` exception was added on 2026-08-16, after US3 was built
  and this requirement's "same store rows" proved unkeepable. Recording why,
  because amending a criterion to fit an implementation is exactly what this
  spec forbids elsewhere and the reasoning has to survive the commit.
  The alternative was proved impossible, not merely inconvenient. `CallbackBridge`
  routes on `record.workflow_id` verbatim (`factory/notify/service.py:529`,
  `:569`), and four assertions inside the protected five pin that it does —
  `tests/test_notify.py:603` and `tests/test_question_reply.py:360`, `:489`,
  `:520` — using a fixture whose `escalation_id` and `workflow_id` are
  deliberately different values. So routing on the correlation id instead, which
  would have left the column untouched, requires editing assertions in the very
  files this story may not edit. The 008 suite does not merely permit the row's
  `workflow_id` to be the routing pointer; it mandates it.
  The moved column is the one field the same suite proves is never observable:
  `tests/test_notify.py:354` asserts it never reaches `callback_data`,
  `factory/notify/messages.py` never mentions it, and the `resolve`/`answer`
  listings print the correlation id, node and deadline instead. Every other
  column is byte-identical. So "same messages, same expiry, same answers" hold
  exactly, and "same store rows" fails only for the pointer that says who is
  waiting — which had to move because the thing waiting moved. -->
- **FR-010**: After migration the epic workflow MUST hold no escalation expiry
  timer and no escalation signal handler of its own, and awaiting an escalation
  child MUST NOT pause the epic's scheduler (the 017 hazard).
- **FR-011**: An inbound reply MUST be accepted as an answer only when its
  sender identity is in the configured `authorized_responders` list;
  non-matching replies are recorded with their identity and do not touch the
  escalation's state or expiry clock, and do not prevent a later authorized
  reply from being accepted.
- **FR-012**: No module defining the EscalationWorkflow MAY read the process
  environment from workflow scope — 039's guard applies by construction and
  MUST stay green.
- **FR-013**: Store settlement MUST be performed by the workflow's own
  transitions and MUST be channel-independent: an escalation answered via
  button, CLI verb, webhook relay or expiry MUST leave no pending row. No
  delivery channel may be the difference between a settled row and an abandoned
  one.
- **FR-014**: `EscalationRecord` MUST survive a store round trip with every
  field intact — including `check_evidence` — and every annotation on it MUST
  resolve under `typing.get_type_hints`.

### Key Entities

- **EscalationWorkflow**: the lifecycle host — one workflow per escalation,
  ID = correlation id, child or standalone; result `answered | expired`.
- **MessengerAdapter**: the transport interface — outbound deliver, inbound
  relay with sender identity; implementations `telegram`, `webhook`; a plain
  library, callable with or without Temporal.
- **AuthorizedResponders**: the configured identity list an inbound reply must
  match to become an answer.

## Success Criteria *(mandatory)*

- **SC-001**: Switching `escalation.adapter` from `telegram` to `webhook` is a
  config-only change after which the full round trip — ask → deliver →
  `ergane answer` → workflow resumes — passes; the existing Telegram live suite
  passes unmodified before and after the refactor.
- **SC-002**: An unauthorized inbound reply never resumes a waiting workflow, in
  a test that proves the waiting workflow subsequently accepts an authorized one.
- **SC-003**: Every open escalation is visible as a running EscalationWorkflow:
  `ergane escalations list` enumerates each with its question and deadline, and
  the list drains as answers and expiries land.
- **SC-004**: The landed 008 behavior suite passes after US3 with no assertion
  edited — proven by the diff, in which that suite's files are unchanged.
- **SC-005**: A second concurrent escalation is not blocked by the first, and
  no escalation await pauses an epic's scheduler — the 017 deadlock is
  structurally impossible rather than merely absent.

## Assumptions

- 033's config parser has landed (2026-08-15) and provides `escalation.adapter`
  in the typed config (`factory/controlplane/config.py:165-172`, with
  `chat_id_env`, `bot_token_env`, `timeout_s`). **It does not provide
  `authorized_responders`** — US4 adds that field to the typed config itself,
  following the parser's existing refusal conventions. The remaining 033
  stories (verify, walkthrough) land ahead of this epic per
  `depends_on_landed`.
- 008's store schema and its guarded-UPDATE arbitration are kept as they are;
  this spec changes who owns the clock, not what the rows mean.
- The operator channel is in daily use throughout this epic, so US3's
  migration must be behavior-preserving in the strongest available sense: an
  unedited suite.

## Out of Scope

- The supervision probe's out-of-band alert path and every systemd unit (042).
- The peer channel (017) — this spec removes the structural obstacle that held
  it at draft; it does not build it.
- Additional adapters beyond `telegram` and `webhook` — `webhook` is the
  extension point, deliberately.
- Any change to what an escalation *says*; message rendering is 008's and stays.
- **Fixing the RETRY disposition** (`interpreter/escalation-retry-kills-the-node`,
  open critical: answering RETRY at the recovery-exhausted stage tears the node
  down instead of retrying). US3 migrates that response mapping and MUST
  preserve it as-is, characterized by a test that documents the defect and
  cites the finding — a behavior-preserving migration that silently fixed it
  would hide the defect behind fresh code, and one that accidentally fixed it
  would fail its own unedited-suite criterion. The fix is its own spec.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-006, FR-007, FR-008, FR-012, FR-013, FR-014]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009, FR-010]
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-003, FR-011]
```
