---
state: draft
# TBD — DRAFTED 2026-08-30 by the operator session, against ergane-buildout at
# c03eb32, at Bryan's request: "a TBD story about ergane lifecycle events that we
# could patch into. for instance, i want to be able to register events that
# happen at the end of every agent turn. that would partly be a pass through
# listener on dev agent harness events."
#
# THIS IS DELIBERATELY NOT A TRIO. There is no plan.md, no tasks.md and no
# workgraph.json, because the design questions at the bottom of this file are
# genuinely open and writing a task list over an unsettled design is how a story
# reaches an agent under-specified. `CLAUDE.md` is explicit that the measured
# leverage is in refinement, not dispatch; this file exists so the idea is
# durable, not so it is dispatchable. It must not be flipped to `ready` until the
# open questions have answers.
#
# SO `ergane spec validate` REFUSES THIS, AND THAT IS THE CORRECT STATE. The
# frontmatter, story and `## Work Graph` layers all pass; the only refusals are
# `plan.md` and `tasks.md` missing, which is the deferred work naming itself.
# When those two exist the refusal goes away on its own. Do not "fix" the
# refusal by scaffolding empty files — the refusal is the honest signal that
# this cannot be dispatched yet.
#
# ANCHORS ARE SYMBOLS, NOT LINE NUMBERS, ON PURPOSE. On 2026-08-30 a landing
# shifted `factory/workgraph/worktree.py` and every line-anchored citation below
# it went stale inside the hour; 100/us2 parked for 17 minutes on exactly that,
# and spec 100's own tasks.md accused a node of an edit the operator had made.
# A draft that may sit for weeks cannot carry line numbers. Every symbol named
# below was grepped from the tree at c03eb32, not recalled.
---

# The factory emits what it just did

## Why this exists

The factory is observable only by asking it. `ergane build status`, `ergane
status` and `ergane findings list` all pull; Temporal's UI pulls; the operator
pulls. Nothing the factory does *pushes*, except two narrow paths built for one
message each.

That means every integration anyone might want — a desktop notification when a
node lands, a metrics row per attempt, a transcript archived somewhere durable,
a Slack line when the ladder promotes, a linter run over what an agent just
wrote — has to be built as a poller, or not built at all. The operator wanted to
"patch into" the factory and found there is no socket to patch into.

## What already exists, and why none of it is the seam

Three things in the tree are event-shaped. Each is worth reading before anyone
writes a fourth, because two of them are deliberately narrow and the third is a
constraint rather than a starting point.

**`WebhookAdapter` in `factory/notify/webhook.py`** is the closest thing to an
extension point the factory has, and its module docstring is the best statement
of the doctrine any new seam has to obey. It is "the universal glue: an outbound
POST, and a reply the operator hands back" — one URL, one JSON body, so that
"Signal, Slack, email or a wall display is a bridge the operator writes in a few
lines". It then says, in its own words, three things it deliberately is **not**:
not a decider, not a listener ("an inbound HTTP server would put a socket on the
factory's side of a boundary whose purpose is that the operator's side is
theirs"), and not Temporal-aware. But it carries exactly one kind of traffic —
operator notifications — and it is reached only from the notify path.

**The ferry** (`_FerryState` in `factory/workgraph/adapter.py`, and its landing
half in `factory/activities/notify_activities.py`) already proves the hard part
is solvable: it ships a question *out of a running attempt* and records it,
without breaking replay. It is single-purpose — questions only — but it is the
existence proof that a mid-attempt event can leave the sandbox safely.

**Claude Code's own hooks** are the half the operator named, and the factory is
already standing in the right place to use them. `_seed_node_home` in
`factory/workgraph/adapter.py` materialises a per-node `HOME`, located by
`home_path`, and the running agents on this host have a real `.claude/`
directory inside it — `.ergane/homes/<epic>/<node>/.claude/`, with `sessions/`,
`projects/` and `shell-snapshots/` already in it. A `settings.json` written
there is how "the end of every agent turn" becomes an event the factory can
observe, and the factory already owns that directory. Nothing today writes hook
configuration into it.

## The gap, stated precisely

There is no way to say *"when X happens, run this"* to Ergane. Specifically:

1. **No factory-side lifecycle events.** An attempt starting, a gate verdict, a
   judge verdict, a rung promotion, a node landing, an epic completing, an
   escalation opening — all of these are state transitions the factory already
   computes and none of them are emitted anywhere a third party can receive.

2. **No pass-through of harness events.** The agent harness emits its own
   lifecycle (turn boundaries, tool calls, session end). The factory owns the
   home that would configure them and forwards none of them.

3. **No registry.** Even if both existed there is no declared place to say which
   listeners are active, the way `personas.yaml` declares personas and
   `factory.yaml` declares gates.

## What this is asking for

A **listener registry** and an **emit seam**, such that an operator can register
a listener against named lifecycle events and receive them without modifying
factory code — and such that the harness's own turn-level events arrive through
the same door as the factory's.

Two halves, and the second is the one the operator asked for first:

- **Factory events**, emitted from activities, describing what the factory did.
- **Harness events**, passed through from the agent's own hooks, describing what
  the agent did — of which *end of turn* is the motivating case.

## Traps any refinement must carry

These are the constraints the tree already imposes. They are listed here rather
than discovered later at an implementer's expense.

- **Emit from activities, never from workflow code.** Workflow code replays, and
  a replay must not re-fire an event. This is the same hazard that corrupted the
  attempt-history model field on 2026-08-30 (`verify/attempt-history-re-resolves-
  the-model-at-read-time-so-the-record-claims-models-that-did-not-run`), where a
  value derived at read time reported models that never ran.
- **A listener must not be able to fail an attempt.** A hook that raises, hangs
  or exits non-zero has to be contained. `webhook.py`'s `delivered=False`
  vocabulary is the precedent: nothing raises, because the factory's move is
  identical whether the URL was unset, refused or 500'd.
- **No inbound socket.** `webhook.py` refuses to be a listener for a stated
  reason, and a registry that quietly becomes an HTTP server repeals that
  decision without arguing with it.
- **`.ergane/homes/` may never be committed.** `factory/verify/diffcheck.py`
  refuses it by leading path component, because on 2026-08-14 two agents
  committed their own session homes. Anything seeded into the node home for hook
  configuration inherits that refusal and must be tested against it.
- **The sandbox is real.** The node home is bind-mounted writable inside bwrap
  while the runtime root around it is read-only. A hook that writes outside the
  home will be refused by the sandbox, not by policy.
- **Agents have no MCP tools by design.** Hooks are the sanctioned in-sandbox
  extension surface, which raises the stakes on getting their contract right.
- **Credentials.** Any event payload crosses a boundary. The ledger and the
  webhook both refuse credential-like input on the way out; a third emitter that
  does not is a leak with a new name.
- **Volume.** One agent turn is not one event. A node that runs eighty
  completions in half an hour — measured on 095/us2 on 2026-08-30 — will emit at
  that rate if turn events are forwarded naively.

## User Scenarios & Testing

### User Story 1 - A factory lifecycle event reaches a declared listener (Priority: P1)

As an operator, I declare a listener once and receive the factory's own state
transitions, so that integrating with Ergane does not mean polling it.

**Why this priority**: P1 and first. It establishes the registry and the payload
shape that US2 then reuses. Building the harness pass-through first would mint a
second, incompatible envelope.

**Independent Test**: declare a listener against a scratch endpoint, run one
epic to a landing, and compare the events received against the state transitions
`ergane build status` reports for the same epic.

These are written at the level of the invariant, not the mechanism, because the
delivery question below is genuinely open and a scenario naming a transport
would decide it by accident.

**Acceptance Scenarios**:

1. **Given** a registry declaring one listener, **When** an epic runs from
   dispatch to a landing, **Then** the listener receives an event for every node
   state transition `ergane build status` reports for that epic, and no event
   for a transition it does not report — compared against the store, not against
   the emitter, because the point is that the two agree.
2. **Given** the same epic replayed by Temporal after a worker restart, **When**
   the replay re-executes the workflow, **Then** the listener receives no
   duplicate events, because emission is an activity effect and not a workflow
   one.
3. **Given** no registry file at all, **When** an epic runs, **Then** the epic's
   outcome and its recorded history are byte-identical to a run with the feature
   absent — absence is not an error and costs nothing.
4. **Given** an event payload whose source field contains a credential-shaped
   string, **When** it is emitted, **Then** the credential does not appear in
   any delivered byte, held to the same refusal the ledger and webhook already
   apply.

### User Story 2 - The end of an agent turn is an event (Priority: P1)

As an operator, I receive an event when an agent turn ends, forwarded from the
harness's own hooks, so that I can act on what the agent just did without
parsing a transcript after the fact.

**Why this priority**: P1 and the motivating case. It is also the half that
proves the seam is genuinely a pass-through rather than a factory-only feature.

**Independent Test**: dispatch one node, and compare the turn-end events received
against the turn boundaries visible in that attempt's own transcript under
`.factory/transcripts/<epic>/<node>/attempt-N/`.

**Acceptance Scenarios**:

1. **Given** a node dispatched with the registry active, **When** its agent
   completes a turn, **Then** a turn-end event reaches the listener carrying
   enough identity to attribute it — epic, node and attempt — because an event
   that cannot be attributed to an attempt is a log line, not a signal.
2. **Given** the same node, **When** the attempt finishes, **Then** the count of
   turn-end events matches the turn boundaries in that attempt's own transcript.
3. **Given** an agent that writes hook configuration or session files into its
   node home, **When** the diff check runs at the boundary, **Then** the landing
   is refused if any `.ergane/homes/` path was committed — the 2026-08-14
   protection still holds with hooks seeded.
4. **Given** a node home seeded with hook configuration, **When** the agent runs
   under bwrap, **Then** the hook writes only inside the node home, and an
   attempt to write outside it is refused by the sandbox rather than by policy.

### User Story 3 - A listener cannot damage an attempt (Priority: P1)

As an operator, a listener that hangs, crashes or floods is contained, so that
registering an integration can never cost a node.

**Why this priority**: P1 despite reading like hardening. The factory's own
record is that automated actors lose verified nodes in the landing path — three
on 2026-08-16 — and a new failure mode wired into every attempt is exactly that
shape. This story is what makes US1 and US2 safe to turn on.

**Independent Test**: register a listener that sleeps past any timeout and one
that exits non-zero; run a node to a landing and show the attempt is unaffected
and the failures are visible somewhere the operator will look.

**Acceptance Scenarios**:

1. **Given** a listener that never returns, **When** an epic runs to a landing,
   **Then** the epic's wall time and outcome are indistinguishable from a run
   with no listener, and the stall is reported rather than swallowed.
2. **Given** a listener that exits non-zero on every event, **When** an epic
   runs, **Then** no attempt fails, no rung is consumed, and the landing is
   unchanged — a broken integration costs the operator information, never a
   node.
3. **Given** a listener that raises, **When** the next event fires, **Then** it
   is still delivered, because one bad event must not silently unsubscribe an
   integration the operator believes is running.
4. **Given** any of the three failures above, **When** the operator asks the
   factory what happened, **Then** the failure is visible from a command rather
   than only in a log the operator would have to know to read.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

Serialised deliberately, and this ordering is provisional until the open
questions are answered. US1 mints the registry and the event envelope; US2
reuses both for harness events and would otherwise invent a second envelope; US3
constrains the surface both of them added, so it cannot be written before there
is a surface to constrain. If refinement decides delivery is `WebhookAdapter`'s
shape, US1 and US2 will also contend on `factory/notify/`, which would make the
`depends_on_merged` edges load-bearing for file ownership as well as for logic.

## Open questions — why this is TBD and not ready

None of these have answers yet, and each of them changes the task list.

1. **What is the event vocabulary?** Which transitions are events, and what is
   the stable name of each. Too few and nobody can build what they want; too
   many and every one is a compatibility promise.
2. **What is the delivery mechanism?** Reusing `WebhookAdapter`'s one-URL-one-
   JSON-body shape is the obvious candidate and keeps one doctrine instead of
   two. A subprocess listener is more powerful and much harder to contain. An
   in-process Python callable is fastest and the worst for isolation.
3. **Where are listeners declared?** `factory.yaml` is the manifest a node reads
   and is already declared-not-detected; a separate `listeners.yaml` mirrors
   `personas.yaml`. Note that `factory.yaml` is parsed by the *worker's* parser,
   not the worktree's, so adding a key there has a deployment ordering cost that
   cost 020/US1 four deaths.
4. **How do harness events cross the sandbox boundary?** The hook runs inside
   bwrap with a read-only runtime root. Whether it writes to a path the factory
   later reads, or posts to something reachable from inside the sandbox, is
   undecided and is the single most load-bearing unknown here.
5. **What happens to volume?** Batching, sampling, or per-event opt-in.
6. **Is delivery best-effort or durable?** Best-effort matches `webhook.py`.
   Durable means a queue and a store, and that is a much larger spec.
7. **Does this belong to the factory or to the target repo?** Ergane is
   portable; a listener registry that only works on this repo is a different and
   smaller thing than one that ships with the CLI.

## Requirements (summary — numbered at refinement)

- A declared registry of listeners, read from a named path, validated at load.
- Named lifecycle events emitted from activity code, never from workflow code.
- Pass-through of agent-harness turn events via the factory-owned node home.
- Containment: a listener cannot fail, stall or slow an attempt.
- Refusal of credential-like content in any emitted payload.
- Absence of a registry is not an error; the factory runs unchanged with none.

## Success Criteria (summary)

- An operator can receive every named event without editing factory code.
- An operator can act on the end of an agent turn.
- A deliberately broken listener leaves node outcomes byte-identical.
- Nothing seeded into the node home can be committed by an agent.
