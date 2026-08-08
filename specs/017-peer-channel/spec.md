---
state: draft
# Drafted 2026-08-08 from the operator's request: agents should be able to
# talk to each other — an instance of claude code messaging another instance
# of claude code — for escalations and coordination, including a named
# external agent (the homelab operator agent in ~/code/homelab). Options
# considered and decided in § Decision: Temporal signals over A2A over MCP.
# Numbered 017: 010–014 reserved for audit-triage epics, 015 doctor, 016 delta.
depends_on_landed: [008-operator-channel]
---

# Feature Specification: Peer Channel

**Feature Branch**: `017-peer-channel`

**Created**: 2026-08-08

**Status**: Drafted while the operator channel's ink was still wet. 008 landed
the factory's first conversation: an agent's blocking question reaches the
operator's phone, the reply reaches the next attempt, and asking costs no
ladder slot. Every question still lands on one human. But the cheapest
answerer of "which of these two designs does the epic want" is usually not
the operator asleep in Dallas — it is the architect node that wrote the plan,
running (or runnable) in the same epic. And some questions belong to an agent
outside the factory entirely: the homelab operator agent that owns the proxy,
the stack, and the machines this factory runs on.

**Input**: 008 built a channel with exactly one addressee. The marker grammar,
the ferry files, the QUESTION termination, the park/expiry semantics, the
free-text answer signal, the store's threading key — all of it exists and all
of it is hardwired to route to Telegram. This spec adds the address: a message
names its recipient, the recipient may be a peer node in the same epic, a
named external agent, or a sibling epic — and the operator becomes the floor
every undelivered message degrades to, never the only line.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A question reaches a peer agent in the same epic (Priority: P1)

As the factory operator, when an agent hits a question another agent in the
same epic can answer — the implementer asking the architect which of two
interface designs the plan intends, a debugger asking the implementer what an
uncommitted change was for — the question routes to that peer and the answer
comes back, so that the operator's phone is reserved for questions only a
human can answer.

The agent's side is one extension of a contract it already knows: the 008
question grammar (marker in the final message, or the in-flight ferry file)
gains an addressee line. No addressee means the operator — every 008 behavior
is preserved bit-for-bit as the default. The factory's side is routing: the
epic workflow already owns every node's state, so a peer-addressed message is
buffered in workflow state exactly as operator answers are, delivered down the
target's in-flight ferry when the peer is running, or into the target's next
assembled prompt under a dedicated peer-message section when it is not. The
reply threads back by message id and reaches the asker the same two ways —
ferry down if the asker kept its process alive, next-attempt prompt section if
it parked.

**Why this priority**: This is the story that converts the operator from
single point of attention into escalation floor. Without it nothing else in
this spec exists, and with it alone the factory already self-answers the
class of question that burned 006-us1's first attempt.

**Independent Test**: With two scripted agents in one epic, one addresses a
question to the other; assert the message is delivered, the reply reaches the
asker verbatim, no Telegram message is sent, and both nodes' attempt ceilings
are what they were before the exchange.

**Acceptance Scenarios**:

1. **Given** an in-flight attempt whose ferry question file names a peer node
   as addressee, **When** the monitor loop ferries it up, **Then** the message
   is routed to the peer without ending either attempt, and no operator
   notification is sent.
2. **Given** a peer message addressed to a node with an attempt in flight,
   **When** routing delivers it, **Then** the target's adapter surfaces the
   message through the in-flight ferry within one poll interval, and the
   target's reply threads back to the asker by message id.
3. **Given** a peer message addressed to a node with no attempt in flight and
   attempts remaining, **When** the target's next attempt dispatches, **Then**
   its assembled prompt carries the message verbatim under a dedicated
   peer-message section, and the reply reaches the asker.
4. **Given** a question with no addressee, **When** verification and routing
   run, **Then** behavior is byte-identical to 008: QUESTION termination,
   Telegram delivery, WAITING_OPERATOR park — the absent addressee is the
   common case and the compatibility contract.
5. **Given** a peer message addressed to a terminal node, to an unknown name,
   or unanswered at its expiry, **When** routing or the expiry loop evaluates
   it, **Then** the message degrades to the 008 operator-question path — a
   peer message may go unanswered, it must never hang a node or vanish.

---

### User Story 2 - A message reaches a named external agent (Priority: P2)

As the factory operator, an agent can send a message to an agent I have named
in a registry outside the epic — first among them the homelab operator agent
working in `~/code/homelab` on this same host — and a reply that agent writes
comes back into the asking node's next prompt, so that questions about the
proxy, the stack, or the machines land with the agent that owns them instead
of with me.

External peers live in an operator-owned registry file, sibling to
`personas.yaml`: each entry names the peer, its transport, its address, and
its expiry window. The first transport is a durable filesystem mailbox — one
JSON file per message in the peer's inbox directory, replies swept from its
outbox by the same beat that already ticks the asker's expiry. The registry's
transport field is deliberately the seam where a future A2A client slots in
(§ Decision); the mailbox is what the homelab agent can consume today with
one line in its own instructions. Because an external agent answers on its
own schedule — or never — every external send is mirrored to the operator's
Telegram as a notification (not a question), and the unanswered-at-expiry
path is the same degradation US1 established: the operator inherits it.

**Why this priority**: This is the operator's explicitly named want — Ergane
talking to the homelab agent — and it is the story that takes the channel
outside one Temporal workflow. It is P2 only because US1 lands the routing,
store, and degradation semantics it rides on.

**Independent Test**: With a registry naming a mailbox peer, a scripted agent
addresses it; assert the message file appears in the inbox with the documented
schema, the Telegram mirror is sent, a reply file placed in the outbox reaches
the asker's next prompt verbatim, and an unanswered message degrades to an
operator question at expiry.

**Acceptance Scenarios**:

1. **Given** a message addressed to a registered mailbox peer, **When** routing
   delivers it, **Then** exactly one message file appears in the peer's inbox
   carrying id, sender epic/node/persona, body, and reply instructions, and a
   Telegram mirror notification is sent.
2. **Given** a reply file in the peer's outbox naming an open message id,
   **When** the sweep beat reads it, **Then** the reply reaches the asking
   node exactly as a US1 peer reply would — ferry down in flight, prompt
   section otherwise — and the exchange is recorded in the store.
3. **Given** an external message unanswered at its registry expiry, **When**
   the expiry loop evaluates it, **Then** it degrades to the 008 operator
   question path, and a reply arriving later is stored and never read.
4. **Given** a message addressed to a name in no registry, **When** routing
   evaluates it, **Then** it is refused to the asker as undeliverable —
   named, immediate, and without consuming the asker's attempt.

---

### User Story 3 - A message crosses epics, and the channel is documented (Priority: P3)

As the factory operator, when two epics run concurrently, an agent in one can
message a node in the other — routed as a signal to the sibling epic's
workflow, buffered with the same incurious discipline every existing signal
uses — and the whole channel's decision trail is recorded, so that the
factory's conversation topology is complete and explained.

**Why this priority**: Real, but the factory runs epics at a concurrency cap
that makes same-epic and external peers the live need; the cross-epic hop is
deliberately last, priced only after US1's routing and US2's registry exist,
and it carries the channel's documentation and decision-log duties as the
completing story.

**Independent Test**: With two workflow instances and scripted children, a
message addressed to a node in the sibling epic is delivered into that node's
prompt and the reply returns; the decision log and architecture docs name the
channel.

**Acceptance Scenarios**:

1. **Given** a message addressed to a node in a named sibling epic, **When**
   routing delivers it, **Then** the sibling workflow receives it as a signal,
   buffers it without validating against state it may not have written yet,
   and delivers it to the target node by US1's rules.
2. **Given** a cross-epic message whose sibling epic is not running or never
   answers, **When** the expiry loop evaluates it, **Then** the US1
   degradation applies unchanged — the operator inherits it.
3. **Given** the feature lands, **When** the decision log and architecture
   docs are read, **Then** the channel's transport decision (§ Decision) and
   the FR-012 amendment's extension are recorded as claimed entries.

---

### Edge Cases

- Two nodes message each other and both park waiting: each side's expiry
  degrades independently to the operator — mutual waiting is bounded by the
  same clock that bounds solitary waiting, and no deadlock outlives it.
- A ping-pong exchange that never converges: the per-node outstanding-message
  cap (FR-006) refuses the send that would exceed it, and the refusal names
  the cap — spend on conversation is bounded by configuration, not by hope.
- A message addressed to the sender itself: refused at routing as
  undeliverable — a node that wants to remember something has its worktree.
- A peer reply arriving after the asker went terminal: stored and never read,
  the `_answers` discipline extended to messages.
- Credential values in a message body: the same sweep that guards questions
  and answers guards messages, inbox files included — a mailbox file leaves
  the factory's trust boundary and must be as clean as a Telegram message.
- A registry entry whose mailbox path is unwritable: the send is refused as
  undeliverable to the asker (US2-S4); routing must never hang on a disk.
- An operator reply and a peer reply racing for the same degraded question:
  first-wins through the store's guarded resolution, the 008 rule unchanged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The question grammar (final-message marker and ferry file) MUST
  accept an optional addressee; a message with no addressee MUST behave
  byte-identically to 008's operator question on every path.
- **FR-002**: A message addressed to a same-epic peer MUST be routed through
  workflow state — buffered, replay-safe, keyed by message id — and delivered
  to the target's in-flight ferry when an attempt is running, or into the
  target's next assembled prompt under a dedicated peer-message section when
  one is not.
- **FR-003**: A peer's reply MUST thread back to the asker by message id and
  reach it by the same two paths, verbatim.
- **FR-004**: A message that is undeliverable — unknown addressee, terminal
  target, unwritable transport — or unanswered at its expiry MUST degrade to
  the 008 operator question path; no message may hang a node or be silently
  dropped.
- **FR-005**: Message and reply text MUST NOT reach any verdict: the FR-012
  amendment's hole widens only from "park and page the operator" to "park and
  route", and a test MUST assert message content cannot influence gates or
  judge.
- **FR-006**: Outstanding peer messages per node MUST be capped by
  configuration, and a send exceeding the cap MUST be refused to the asker
  with the cap named.
- **FR-007**: No credential value MUST appear in any message body, reply,
  mailbox file, mirror notification, or stored record; the existing sweep
  MUST assert each new surface.
- **FR-008**: Every message and reply MUST be persisted in the verification
  store, attributed to sender and recipient, alongside 008's questions.
- **FR-009**: External peers MUST be declared in an operator-owned registry
  naming peer, transport, address, and expiry; the first transport MUST be a
  durable filesystem mailbox with one file per message and replies swept from
  an outbox, and unregistered names MUST be refused as undeliverable.
- **FR-010**: Every external send MUST be mirrored to the operator over the
  existing notify bridge as a notification requiring no action.
- **FR-011**: A message addressed to a node in a sibling epic MUST be
  delivered as a signal to that epic's workflow and buffered with the
  incurious discipline of the existing signals — stored even when unknown,
  never validated against unwritten state.
- **FR-012**: The channel's transport decision and the FR-012-amendment
  extension MUST be recorded in the decision log at landing, and the
  architecture docs MUST name the peer channel and its registry.

### Key Entities

- **Message** — addressee-bearing sibling of 008's Question: id, sender
  (epic, node, attempt, persona), addressee, body. Stored with questions.
- **Reply** — a peer's answer, threaded by message id, delivered into exactly
  one ferry or prompt section.
- **Peer registry** — operator-owned file naming external agents: name,
  transport, address, expiry. The A2A seam lives in `transport`.
- **Degradation** — the conversion of an undelivered or expired message into
  an 008 operator question; the floor every path lands on.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The 006-us1 scenario replayed peer-first: the kill-path design
  question addressed to the epic's architect completes its round trip with
  zero operator messages sent, and the answer text appears verbatim in the
  asker's context.
- **SC-002**: A message to the registered homelab peer lands in its inbox and
  mirrors to Telegram within 60 seconds of the ferry read, and a reply file
  reaches the asker's next assembled prompt with no human touching a spec or
  prompt file.
- **SC-003**: Every degradation path — unknown addressee, terminal target,
  expiry, unwritable mailbox — ends observably at the operator question path
  or an immediate refusal, demonstrated by test; no test run hangs.
- **SC-004**: A scripted mutual ping-pong terminates at the configured cap
  with both nodes proceeding and the refusal recorded.
- **SC-005**: The grep-backed sweep extended to messages, mailbox files, and
  mirrors shows no key value can reach any of them.
- **SC-006**: The full existing suite stays green; every 008 test keeps its
  meaning unchanged — the addressee-less path is bit-compatible.

## Work Graph

US2 depends on US1 because external delivery presupposes routing, store rows,
expiry, and degradation that US1 lands — the registry and mailbox are a new
transport under an existing channel, not a new channel. US3 depends on US2
because the cross-epic hop reuses the routing activity US1 lands and the
addressee grammar US2 finishes (registry names and epic names share one
namespace that must exist before a third kind of address joins it), and
because it carries the closing documentation duties. Both edges are
`depends_on_merged` (003 FR-009): each dependent imports modules its
predecessor lands, so its worktree must clone a base already containing the
predecessor's merge. The deriver requires `depends_on: []` spelled out even
when empty.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-011, FR-012]
```

## Assumptions

- 008 is landed and live (it is — attested 2026-08-07): marker grammar, ferry
  files, QUESTION termination, park/expiry, answer signal, question store,
  and the Telegram bridge are all present to extend.
- The homelab agent is a Claude Code instance on this host; the mailbox path
  and the one-line instruction telling it to sweep its inbox are operator
  wiring recorded at onboarding, not factory code. Delivery is durable;
  attention is the peer's own affair — which is exactly why FR-010 mirrors
  every external send to the operator.
- Epic concurrency stays at the operator's configured cap; US3 is valuable at
  cap > 1 and harmless below it.

## Decision: Temporal signals as the spine, A2A at the edge, no MCP tool (decided 2026-08-08, Bryan + assistant)

Three transports were considered for the factory's internal message routing.

**Temporal signals win.** Messages between agents in this factory are
messages between the workflows that own those agents — the agents themselves
are ephemeral subprocesses that the interpreter dispatches, monitors, and
kills. Signals are the durable, replayed, ordered primitive this codebase
already trusts for exactly this shape: `question_answered` carries free text,
`escalation_resolved` carries decisions, and both survive worker crashes and
replay by construction. Queries are read-only by design and cannot deliver;
they remain what they are today, the status surface. The last mile to a
running agent is the 008-US3 ferry — the filesystem the agent already owns,
polled by the monitor beat that already runs.

**A2A is deferred to the registry's transport seam.** The Agent2Agent
protocol solves inter-organization agent discovery and messaging between
long-lived HTTP servers. Ergane's agents live minutes and own no port;
standing an A2A server per attempt inverts the process model, and adopting
A2A as the internal bus would rebuild — with a new dependency and a new
attack surface — the durability and routing Temporal already provides.
Today zero peers speak A2A: the homelab agent is a Claude Code instance
that can read a mailbox with one instruction line. When a real A2A peer
exists, it becomes one more `transport` value in the registry, implemented
behind the same interface as the mailbox, and nothing above the registry
changes.

**An in-agent MCP messaging tool was rejected.** Handing every agent a
`send_message` tool means wiring an MCP server into every dispatch and
widening the FR-012 surface — agent-authored calls mutating factory state —
that D-018 deliberately keeps at one marker. The ferry file grammar keeps
the adapter in control of what leaves an attempt and keeps the amendment's
hole at "park and route".

## Decision: the operator is the floor, never the ceiling (decided 2026-08-08)

Every failure mode of every path in this spec — unknown name, dead peer,
silent mailbox, expired wait — lands on the 008 operator question path,
because that path is the one channel whose delivery and expiry semantics are
proven in production. The peer channel may only ever reduce the operator's
load; it can never add a way for a question to die unheard, because the
worst case of every branch is precisely the 008 behavior the factory ships
today. The decision-log numbers are deliberately unassigned here — claimed
at landing in `docs/decisions.md`, per the 006/008 precedent.
