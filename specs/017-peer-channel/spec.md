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
   it and no consult is available for the addressee (US4), **Then** the
   message degrades to the 008 operator-question path — a peer message may go
   unanswered, it must never hang a node or vanish.

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

### User Story 4 - A message with no live recipient spawns its answerer (Priority: P2)

As the factory operator, when a message names a persona — or a node whose
attempts are done — the factory spins up an ephemeral consult to answer it:
one process, dispatched with that persona's model, read-only, alive exactly
long enough to produce the reply, then discarded, so that "ask the architect"
works whether or not an architect happens to be running, and the operator
rung is reached only when a machine genuinely could not answer.

The factory already runs this shape everywhere: every attempt is an ephemeral
agent an activity spawns, monitors, and tears down, and the judge is a whole
persona that lives one request at a time. A consult is an attempt with the
ladder removed — no gates, no judge, no verdict, no diff expected — whose
entire output contract is the reply. Its context is assembled from what the
factory already knows deterministically (the message, the epic's spec and
plan, the asker's identity and branch), and its longer memory is the second
layer: recall against a factory-owned memory bank, never the operator's
personal one, so cross-epic knowledge accumulates without the operator's
bank silting up with machine churn (§ Decision).

**Why this priority**: This is the escalation vision the channel exists for —
questions answered by the cheapest competent answerer, with the operator as
the floor rather than the default. It is P2 because it rides entirely on
US1's routing, threading, and degradation.

**Independent Test**: With a scripted consult adapter, a persona-addressed
message spawns exactly one consult, the reply threads back to the asker, the
consult's spend lands in the ledger attributed to the asking node, and a
failing consult degrades to an operator question.

**Acceptance Scenarios**:

1. **Given** a message addressed to a persona with no live attempt, or to a
   node whose attempts are terminal, **When** routing evaluates it and a
   consult is available, **Then** exactly one ephemeral consult spawns with
   that persona's registry model, its reply threads back by message id, and
   its process, key, and context are discarded after the reply.
2. **Given** a consult that fails, times out, or declines to answer, **When**
   its attempt ends, **Then** the message degrades to the 008 operator
   question path — the consult rung sits above the floor, never replaces it.
3. **Given** a consult whose own output carries a peer-addressed marker,
   **When** routing evaluates it, **Then** the marker is refused — consults
   answer, they do not converse, and their unanswerable case is scenario 2.
4. **Given** a consult with the factory memory bank configured, **When** it
   runs, **Then** recall is available against that bank and nothing grants
   any factory agent the operator's personal bank; **Given** no bank is
   configured, **Then** the consult still answers from assembled context.
5. **Given** consult spawns reaching the configured bound, **When** one more
   is requested, **Then** it is refused and the message degrades to the
   operator — spawning is bounded by configuration, not by message volume.

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
- A consult asked something only a human can decide: it declines, and the
  decline is scenario US4-S2 — one consult's worth of tokens spent to route
  a question correctly is the price of trying the machine first.
- A flood of persona-addressed messages: the spawn bound (FR-015) refuses
  the excess into the operator path — consults amplify answers, never spend.

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
- **FR-013**: A message addressed to a persona, or to a node with no live or
  future attempt, MUST be answerable by an ephemeral consult when one is
  available: spawned read-only with the persona registry's model, no gates,
  no judge, no verdict; its reply MUST thread back by message id and its
  process, key, and context MUST be discarded after the reply. A consult
  that fails, expires, or declines MUST degrade per FR-004, and a consult
  MUST NOT send peer messages.
- **FR-014**: Consult memory access MUST be scoped to a factory-owned memory
  bank named in operator-owned configuration; no factory agent may be
  granted the operator's personal bank; and a consult with no bank
  configured MUST still answer from assembled context alone.
- **FR-015**: Consult spawns MUST be bounded by configuration, and each
  consult's spend MUST be metered and attributed in the ledger to the asking
  node exactly as any attempt is metered.

### Key Entities

- **Message** — addressee-bearing sibling of 008's Question: id, sender
  (epic, node, attempt, persona), addressee, body. Stored with questions.
- **Reply** — a peer's answer, threaded by message id, delivered into exactly
  one ferry or prompt section.
- **Peer registry** — operator-owned file naming external agents: name,
  transport, address, expiry. The A2A seam lives in `transport`.
- **Degradation** — the conversion of an undelivered or expired message into
  an 008 operator question; the floor every path lands on.
- **Consult** — an ephemeral answering attempt: a persona's model spawned for
  one message, read-only, ladder-free, discarded after its reply. The middle
  rung between a dead peer and the operator's phone.

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
- **SC-007**: A persona-addressed question with no live peer completes its
  round trip through exactly one consult spawn with the spend visible in the
  ledger against the asking node, and the same question with consults
  disabled reaches the operator — both demonstrated by test.

## Work Graph

US2 depends on US1 because external delivery presupposes routing, store rows,
expiry, and degradation that US1 lands — the registry and mailbox are a new
transport under an existing channel, not a new channel. US3 depends on US2
because the cross-epic hop reuses the routing activity US1 lands and the
addressee grammar US2 finishes (registry names and epic names share one
namespace that must exist before a third kind of address joins it), and
because it carries the closing documentation duties. US4 depends only on US1:
the consult rung slots into US1's degradation ladder and threads replies
through US1's ids, touching neither the registry nor the cross-epic hop, so
it may land in parallel with the US2→US3 chain. All edges are
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
US4:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-013, FR-014, FR-015]
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
- A Hindsight server is reachable on the LAN and a factory-owned bank can be
  provisioned for it; provisioning and the endpoint value are operator
  preflight (T001), and FR-014 makes the whole memory layer optional — a
  factory with no bank configured still consults, from assembled context.

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

## Decision: ephemeral consults, and the two-layer memory split (decided 2026-08-08, Bryan)

The operator asked whether Temporal could spin up an agent to process a
message when none is attached to receive it, discard it afterward, and lean
on Temporal plus Hindsight for what such ephemeral agents remember.
**Decided: yes, as US4, with the memory split drawn deliberately.**

The spawn is not new machinery — every attempt in this factory is already an
ephemeral agent an activity dispatches, monitors, and tears down, and the
judge is a persona that lives one request at a time. What US4 adds is an
attempt with the ladder removed, whose output contract is a reply instead of
a diff.

Memory splits in two layers. **Deterministic, epic-scoped context comes from
Temporal and the repo** — the message, the spec and plan, the asker's
identity, the workflow's own question history — assembled into the consult's
prompt from records the factory already keeps, replay-safe and free.
**Durable cross-epic memory comes from Hindsight, through a factory-owned
bank** — never the operator's personal bank, which stays closed to headless
agents so machine churn cannot silt up what the operator reads (the
operator's standing rule, adopted here as factory policy: FR-014). This is
also the channel's first agent-facing MCP surface, and it does not reopen
the messaging-tool rejection above: recall reads memory and retain writes
memory — neither touches node state, so the FR-012 hole stays at "park and
route". One operational lesson is inherited from the bank's own history: a
retain acknowledgment cannot distinguish "stored" from "extracted", so any
factory retain path verifies extraction, never the ack.

## Decision: the operator is the floor, never the ceiling (decided 2026-08-08)

Every failure mode of every path in this spec — unknown name, dead peer,
silent mailbox, expired wait — lands on the 008 operator question path,
because that path is the one channel whose delivery and expiry semantics are
proven in production. The peer channel may only ever reduce the operator's
load; it can never add a way for a question to die unheard, because the
worst case of every branch is precisely the 008 behavior the factory ships
today. The decision-log numbers are deliberately unassigned here — claimed
at landing in `docs/decisions.md`, per the 006/008 precedent.
