# Implementation Plan: Peer Channel

**Input**: [spec.md](spec.md) in this directory.

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## Read this before anything else: the hold is a dispatch condition

This spec has sat at `draft` since 2026-08-08, and the reason has not expired.
Its worst failure mode — a peer park that deadlocks the epic that must answer —
is a runtime property of two workflows, and the judge reads one diff. Every
scripted test in the world can pass while the feature is dead in production.
So this epic gets a **watched run**: the operator watches the first peer
exchange happen for real rather than accepting a PASS and moving on. That is a
condition on dispatch, not on readiness, and the frontmatter's hold chain says
so in the operator's own words.

The 2026-09-04 refinement made the condition *narrower and more falsifiable* —
US7-S1, US7-S2 and US7-S3 each assert one third of the deadlock from a committed
test — but it did not remove it. Two of the three properties can be satisfied by
a diff that passes every scripted test and still deadlocks the moment an
operator turns `max_concurrent_nodes` (`ergane.yaml:151`, 2 at 602a92c) back to
1 for one epic, which is a supported thing to do and the configuration every
US7 test pins.

## What already exists, and where

The channel exists; this feature adds the address. Every mechanism below is
landed and live, and every one of them was moved by a spec that landed after
this plan was first written.

### The question lifecycle is a child workflow (041-US3)

Do **not** build peer messages as sibling buffers inside the epic workflow.
That was this plan's original instruction and it is now the wrong shape: 041
took the question lifecycle *out* of the epic workflow precisely because welding
a park into it cost the next consumer, and the next consumer is you. Build a
`MessageWorkflow` child in `factory/escalation/`, modelled on
`factory/escalation/question.py:90` — `QuestionWorkflow`, and start it from the
same seam.

- The child owns its signal, its window and its row:
  `factory/escalation/question.py:101` — `question_answered` appends into
  `self._replies` (`factory/escalation/question.py:98`) and nothing else;
  `factory/escalation/question.py:112` — `run` sends, then waits on a
  `wait_condition` with the request's own timeout at
  `factory/escalation/question.py:144`, and expires the row on
  `asyncio.TimeoutError`. The wire name is `QUESTION_SIGNAL_NAME`
  (`factory/notify/service.py:110`).
- The epic starts it and parks the node at
  `factory/workgraph/workflow.py:1980`, with the id from
  `factory/escalation/workflow.py:220` — `child_correlation_id`.

### The three lines that make FR-016 hard

**One.** The park raises the pause. `factory/workgraph/workflow.py:2006` through
`factory/workgraph/workflow.py:2008` are:

```python
record.state = NodeState.WAITING_OPERATOR
record.pending_question_id = question.id
self._paused = True
```

That last line is consumed at `factory/workgraph/workflow.py:1034`, which drains
the in-flight set, sets `EpicState.PAUSED`, and re-waits in a bounded loop until
the flag clears. Mirror the question block and omit that line.

**Two.** The parked task keeps its slot, and omitting the pause does not release
it. `factory/workgraph/workflow.py:1572` — `_drain_in_flight` exempts a parked
node deliberately:

```python
drainable = {
    node_id: task
    for node_id, task in in_flight.items()
    if self._nodes[node_id].state != NodeState.WAITING_OPERATOR
    or task.done()
}
```

so the parked task stays in `in_flight` for the whole window — and the dispatch
loop stops filling at `factory/workgraph/workflow.py:1089`:

```python
if len(in_flight) >= request.max_concurrent_nodes:
    break
```

The configured value is 2 (`ergane.yaml:151`, raised from 1 on 2026-08-30), so
one parked asker holds half the epic; an operator setting it to 1 for an epic —
supported, and what every US7 test does — makes the parked asker the whole epic.
There is a second gate on the same dict thirteen lines below, at
`factory/workgraph/workflow.py:1102`, which calls
`factory/workgraph/workflow.py:1423` — `_subscription_nodes_in_flight` and
bounds subscription-routed nodes again against
`request.max_concurrent_subscription_nodes`. **That gate is inert today for two
reasons, and the earlier edition of this plan named only one of them.** The dial
is undeclared in `ergane.yaml` and defaults to `None`
(`factory/workgraph/workflow.py:577`); *and* no node of a normal epic is routed
to a subscription persona, so the branch is not entered whatever the dial says.
`factory/workgraph/workflow.py:1413` — `_is_subscription_node` compares the
persona named on the node — filled from `item.node.persona` at
`factory/workgraph/workflow.py:993` — against `SUBSCRIPTION_AGENT`
(`factory/config.py:149`), and at 602a92c `implementer` is `agent: claude-code`
(`personas.yaml:270`), moved off the subscription on 2026-09-01 by a route change
its own comment records. The only `agent: subscription` entries are `debugger`
(`personas.yaml:410`) and `opus-closer` (`personas.yaml:449`), and no story in
this spec names either. Both reasons are one operator edit from reversing, and a
park that releases the general slot while holding the subscription one is the
same deadlock through a third door — but a test that pins the dial and leaves the
persona alone proves nothing about that door. See trap 1 for what the test has to
do instead. A peer park that leaves the scheduler unpaused and still holds either
slot passes every test whose two attempts overlap.

**Three.** Nothing wakes the loop but a finished task.
`factory/workgraph/workflow.py:1137` waits on:

```python
lambda: any(task.done() for task in in_flight.values())
or self._kill_requested
or self._paused
```

A message arriving is none of the three. The open finding
`interpreter/a-merged-dependency-does-not-wake-the-scheduler-so-a-ready-node-waits-for-an-unrelated-activation`
is this same mechanism seen from the dependency side; the peer channel needs the
predicate to gain a term, not a poll.

### The park's state, and what 079-US4 did to it

`factory/workgraph/models.py:101` — `NodeState` now has **one** park state,
`WAITING_OPERATOR` (`factory/workgraph/models.py:155`), written by two doors —
the question and a `PAUSE_EPIC` press — with the module-level alias
`_PARKED` at `factory/workgraph/workflow.py:344`. The comment above that alias
records why: a press used to park in `FAILED`, which *is* in `_UNREACHABLE`
(`factory/workgraph/workflow.py:300`), so
`factory/workgraph/workflow.py:1496` — `_lock_out_dependents` read the parked
node as a dead edge and killed everything waiting on it. One press ended three
nodes on 2026-08-19.

FR-016 still asks for a distinct state, and the reason it is worth a third state
where 079 merged two is that this one differs in the property those two share:
`WAITING_OPERATOR` means *the epic is paused while this node waits*, asserted in
`factory/workgraph/models.py:155`'s own comment and relied on by the drain and by
the status derivation at `factory/workgraph/workflow.py:903`. A peer park is not
that. But the third state must be classified everywhere the second one is, by
hand, or 2026-08-19 happens again with a different name.

### What 126 did to it after that (landed 2026-09-02)

126-a-killed-node-leaves-no-ref-to-collide-with landed on this same file on
2026-09-02 (`8d5102e` US2, `94c8cd8` US3) and gave the park state a **third**
job, this one destructive. `factory/workgraph/workflow.py:3087` — `_close_out`
now runs after `remove_worktree` on every non-parked terminal state, branching
on the state rather than on the termination, and the branch is
`factory/workgraph/workflow.py:3137`:

```python
record.state = state
if state is not _PARKED:
    # Terminal (non-parked) path: archive the branch and clear the live
    # remote ref, so a later dispatch cannot collide with stale refs
```

`archive_and_clear_remote_branch` deletes the node's live remote ref. The guard
is an identity check against **one** park state, so a distinct peer-park state
reaching any close-out path is archived and cleared like a dead node. 126 also
added `state=_PARKED` writes at `factory/workgraph/workflow.py:3320` (inside
`factory/workgraph/workflow.py:3216` — `_escalate_ref_conflict`) and
`factory/workgraph/workflow.py:4292` (inside
`factory/workgraph/workflow.py:4229` — `_apply_landing_resolution`), so the set
of writers grew too. This is why `126-a-killed-node-leaves-no-ref-to-collide-with`
is in `depends_on_landed`: FR-016's classification list is not satisfiable
without it. US7-S6 is the assertion.

### The ferry, and why in-flight delivery is a protocol change

`factory/workgraph/adapter.py:222` — `_FerryState` holds the per-attempt state
between beats; `factory/workgraph/adapter.py:243` — `read_question` reads the
file the agent wrote, `factory/workgraph/adapter.py:258` — `write_answer`
delivers one answer down. The file names are
`factory/workgraph/adapter.py:187` and `factory/workgraph/adapter.py:188`, in
`$ATTEMPT_ARCHIVE` (`factory/workgraph/adapter.py:176`).

The beat is `factory/workgraph/adapter.py:1400` — `_ferry_once`, and its answer
poll is guarded:

```python
if (
    read_ferry_answer is None
    or state.question_id is None
    or state.answer_written
    or now < next_read
):
    return False
```

`state.question_id` is set only when the agent itself wrote a question file, so
the ferry is a **pull**. US2's whole content is adding the push direction beside
it without disturbing that guard. The activity-side callbacks are
`factory/activities/notify_activities.py:958` — `ferry_send_question` and
`factory/activities/notify_activities.py:982` — `ferry_read_answer`, imported at
`factory/activities/agent_activities.py:75` and wired into the attempt at
`factory/activities/agent_activities.py:537`.

### The store, the degradation target, and the prompt section

- **Questions DDL** at `factory/verify/store.py:310` — a 12-hex id as the
  routing key, resolution states, an `expires_at` column and a partial index on
  pending. The guarded first-wins arbiter is
  `factory/verify/store.py:1808` — `resolve_question`. Messages are a sibling
  table: id, sender epic/node/attempt/persona, addressee, body, reply,
  resolution, expiry.
- **The DDL is published, and a test holds the two copies together.**
  `factory/verify/store.py:201` says `_SCHEMA_DDL` is "Verbatim from
  `contracts/verification-store.sql`", and that file is
  `specs/002-verification-gating/contracts/verification-store.sql`.
  `tests/test_verify_store.py:92` loads it and compares the live schema against
  it column by column, so a `messages` table added to `_SCHEMA_DDL` alone fails
  that test. 126-US3 (`94c8cd8`, 2026-09-02) edited both files in one commit;
  do the same.
- **Degradation target** is the whole 008 path:
  `factory/activities/notify_activities.py:803` — `send_question`,
  `factory/notify/messages.py:484` — `question_message`, and the reply route
  `factory/notify/service.py:447` — `CallbackBridge`,
  `factory/notify/service.py:631` — `handle_reply`,
  `factory/notify/service.py:810` — `_answer_signal`. Degrading a message means
  writing a question row from its content and shipping it through this path
  unchanged.
- **The prompt section** the peer-message section is a sibling of:
  `factory/workgraph/prompt.py:146` — `OperatorAnswer` is the dataclass,
  `factory/workgraph/prompt.py:814` — `_answer_section` renders it, and
  `factory/workgraph/prompt.py:502` — `build_attempt_prompt` is where it is
  appended. Its docstring says why the operator's voice rides a section of its
  own; a peer's voice is a third authority and needs a third section, not a
  reuse of the second.
- **Telegram mirror** is the notify bridge's plain-notification path (no
  keyboard, no reply key), already used for lifecycle notices.
- **The no-verdict guard FR-005 extends is two committed tests, not a rule in
  prose.** `tests/test_interpreter.py:3591` — `test_a_marker_never_produces_a_pass_from_its_presence`
  drives an attempt that carries both a marker and a passing diff and asserts the
  node parks rather than passes: the marker may park, never grade (008 FR-010).
  `tests/test_workgraph_sweep.py:1168` — `test_the_workflow_reads_nothing_off_an_attempt_but_its_termination`
  parses the workflow and pins the *read set* off an attempt result — today
  exactly `{termination, transcript_path, detail, credential_source}` — so any
  new field an agent could write into is a red test until the diff says why. A
  message that reached a verdict would have to widen one of those two, which is
  what "extended rather than forked" means in US9-S2: the diff shows which guard
  it extended and what the new member is for.

### The credential sweeps are driven runs, not surface lists

There is no production sweep module and no list of surfaces to append a name to.
Each component has one test that *drives the component through a real run* and
then searches every byte the run left behind, so "extend the sweep" means "make
the sweep's own run perform the new act". Two of them matter here:

- `tests/test_verification_sweep.py:418` —
  `test_no_byte_this_component_persists_carries_either_credential` runs a whole
  verification and a whole escalation, then walks
  `component.workspace.rglob("*")` and asserts neither canary appears in any
  file, in the operator's message, or in the proxy transcript. This is the sweep
  FR-007 names: `factory/verify/store.py` is in this component, so a `messages`
  row is only swept if the run wrote one.
- `tests/test_workgraph_sweep.py:410` —
  `test_no_byte_a_real_attempt_persists_carries_either_credential` runs one whole
  agent attempt and then walks `tmp_path.rglob("*")`. This is the sweep FR-020
  and FR-021 name: mailbox files and a consult's MCP config are written by the
  worker host during an attempt, and are swept only if they land inside the tree
  that walk covers. A mailbox root outside it is a surface the sweep cannot see,
  which is why the root is part of US3-S7's assertion.

The wrong reading of FR-007 is "add the message body to a list somewhere". The
right one is "the sweep's run now writes a message, and the assertion it already
makes covers those bytes because they are inside the tree it walks".

### US5 consults: the spawn and the meter (the grant is US8)

- **Ephemeral spawn machinery is every attempt**:
  `factory/workgraph/adapter.py:750` — `adapter_for` returns an
  `factory/workgraph/adapter.py:720` — `AgentAdapter`, and
  `factory/workgraph/adapter.py:993` — `ClaudeCodeAdapter` implements
  `factory/workgraph/adapter.py:1022` — `run_attempt`, which already dispatches,
  monitors, classifies and tears down a one-shot CLI run. A consult is that with
  no verification ladder behind it: the reply is the final message and
  classification is reply-or-not.

### The worktree grant already half exists — read this before writing US8-S1

This repository runs its agents under bwrap (`ergane.yaml:26`), so the backend is
`factory/workgraph/adapter.py:368` — `BwrapBackend` and the bind list is built
in `factory/workgraph/adapter.py:464` — `_build_argv`. The plan used to paste
two lines of that function and stop, which hid the thing that decides whether
FR-018's test can fail. Here is the whole relevant stretch. First the pair at
`factory/workgraph/adapter.py:523` and `factory/workgraph/adapter.py:524`:

```python
binds.append(("--ro-bind", str(worktree.parent), str(worktree.parent)))
binds.append(("--bind", str(worktree), str(worktree)))
```

and then, fourteen lines further down, at
`factory/workgraph/adapter.py:531` through
`factory/workgraph/adapter.py:538`:

```python
runtime_root_candidates = [home.parent, home.parent.parent, home.parent.parent.parent]
runtime_root = next(
    (candidate for candidate in reversed(runtime_root_candidates)
     if candidate.is_dir() and candidate.name == "homes"),
    home.parent.parent.parent,
).parent
if runtime_root.is_dir() and runtime_root not in (Path("/"), worktree.parent):
    binds.append(("--ro-bind", str(runtime_root), str(runtime_root)))
```

Follow the arithmetic. `factory/workgraph/adapter.py:815` — `home_path` puts a
node home at `<factory_root>/homes/<epic>/<node>`
(`factory/workgraph/adapter.py:823`), so `runtime_root` resolves to
`<factory_root>`. `factory/workgraph/worktree.py:289` — `worktree_path` puts a
node worktree at `<factory_root>/worktrees/<epic>/<node>`, which is inside it.
**Every node worktree is therefore already read-only-visible, and already
unwritable, inside every bwrap sandbox this factory launches.**

Three consequences, all of which change what US8 has to do (this section is
US8's brief, not US5's — the grant was split out of the consult story on
2026-09-04, and US5 owns only the call site that carries it):

1. A test that only observes the read — "the consult's context holds a file that
   is in the working tree and not on the branch" — passes on a production diff
   that adds nothing. US8-S1 is written as an argv assertion with a control
   invocation instead, and that pairing is what makes it fail on a do-nothing
   diff. Do not replace it with the read.
2. A test that only observes the refused write passes for the same reason, and on
   a host without the sandbox binary it does not run at all
   (`tests/test_us5_gates.py:44` is the guard shape this repo uses). US8-S3 keeps
   it, guarded and with its skip declared, as a check on the enforcement rather
   than as the story's evidence.
3. FR-018 may not be written as a narrowing. It is a *declaration*: one
   `--ro-bind` naming the asker's worktree, emitted through
   `factory/verify/gates.py:150` — `ordered_binds` like every other bind so a
   containing path cannot overlay it, resolved from the asker's node record via
   `worktree_path` rather than string-built a second time. Narrowing the
   runtime-root read is a different spec against a mount set every attempt
   shares; do not attempt it here, and do not claim it.

- **`AgentInvocation` has nowhere to put it yet.**
  `factory/workgraph/adapter.py:293` — `AgentInvocation` carries `argv`,
  `prompt`, `worktree`, `env`, `log`, `standards_path` and `model_alias` and no
  extra-bind field. Adding one is part of the story; smuggling the path through
  `env` and reading it inside the backend is not, because then the bind is a
  string convention rather than a typed grant — and a string convention is
  exactly what the control invocation in US8-S1 cannot distinguish.
- **`needs_worktree` in `personas.yaml` is not this.** It is a real field
  (`factory/config.py:188`, required by `factory/config.py:151`, parsed at
  `factory/config.py:313`) meaning *provision this persona its own worktree from
  a base* — and `architect` already carries `needs_worktree: true`
  (`personas.yaml:64`) with `write_scope: docs` (`personas.yaml:63`). Reaching
  for the existing field because it has the right name is how this becomes a
  write.
- **Metering**: `factory/usage/ledger.py:69` is
  `key_alias TEXT NOT NULL UNIQUE`, documented as `{epic}:{node}:{attempt}:{persona}`
  and used as the idempotency guard. `factory/usage/models.py:27` —
  `Termination` is the closed vocabulary the CHECK at
  `factory/usage/ledger.py:77` admits, widened on connect by
  `factory/usage/ledger.py:188` — `_widen_terminations`.
- **Memory layer**: an MCP config file written per consult pointing at the
  factory-owned bank (FR-014) — endpoint from operator-owned factory config,
  absent means no config is written and the consult runs bare, a second endpoint
  means the write is refused. The attempt-side sweep drives that write (FR-021).
  A retain path, if one is ever added, verifies extraction rather than the
  acknowledgment; the bank's own outage history is the reason.

### New modules this spec adds

- `factory/escalation/message.py` — the `MessageWorkflow` child: one message,
  one window, one signal, one row. Modelled on `factory/escalation/question.py`.
- `factory/notify/peers.py` — registry load and validate (`peers.yaml`, sibling
  of `personas.yaml`): name, transport (`mailbox` today; the A2A seam), address,
  expiry seconds. Pure parse plus named findings, personas-loader style.
- `factory/activities/peer_activities.py` — routing: mailbox write (one JSON
  file, atomic rename), outbox sweep (returns reply rows for the workflow to
  buffer), cross-epic client signal (the activity holds the Temporal client; the
  workflow never does).
- `factory/activities/consult_activities.py` — the consult runner: context
  assembly, MCP config write, spawn bracket (key, adapter, teardown), reply
  extraction, spawn-limit enforcement. No verdict types imported: a consult
  cannot reach the ladder by construction.

## Traps

**Trap 1 — Removing `self._paused = True` does not make the epic dispatch.**
The mechanism has more doors than the pause. The parked task stays in the
in-flight dict (`factory/workgraph/workflow.py:1606` exempts it from the drain),
the general fill loop breaks once that dict is full
(`factory/workgraph/workflow.py:1089`), and a subscription-routed node is
bounded a second time against the same dict at
`factory/workgraph/workflow.py:1102` through
`factory/workgraph/workflow.py:1423` — `_subscription_nodes_in_flight`. This
enforces FR-016 and is asserted by US7-S1. The tempting wrong move is to write
the park by copying the question block minus one line, run the suite at the test
default concurrency, see green, and ship. Pin **both** limits to 1 in the test
that proves this scenario: above 1 on either, the test passes whether or not the
slot was released.

Pinning is necessary and not sufficient, and this is the half the previous
edition got wrong. The subscription bound is only evaluated for a node whose
persona is `agent: subscription`
(`factory/workgraph/workflow.py:1413` — `_is_subscription_node`, reading the
persona filled at `factory/workgraph/workflow.py:993`), and the shipped
`implementer` is `agent: claude-code` (`personas.yaml:270`). So a test that pins
`max_concurrent_subscription_nodes` to 1 and leaves its nodes on the default
persona asserts **nothing** about the subscription slot: the branch is never
entered, and the test passes at any dial value whether or not the park released
that slot. Route the two scripted nodes through a subscription persona as well,
the way `tests/test_subscription_accounting.py:242` — `test_subscription_concurrency_is_bounded_by_declared_limit`
already does: it monkeypatches `load_personas` to return
`tests/test_subscription_accounting.py:73`'s registry, adds the persona at
`tests/test_subscription_accounting.py:63`, and builds nodes with
`tests/test_subscription_accounting.py:79` — `_subscription_nodes`. Copy that
shape; do not invent a second one.

**Trap 2 — The scheduler does not wake on a message.** The wait predicate at
`factory/workgraph/workflow.py:1137` is `any(task.done()) or self._kill_requested
or self._paused`. This enforces FR-016 and is asserted by US7-S2. The wrong move
is a timeout on that `wait_condition` so the loop re-evaluates on a clock: that
converts a deadlock into a delay, passes the scenario in a time-skipping test
environment, and is invisible in production until somebody times a round trip.
The predicate gains a term reading buffered messages, or the buffer's arrival
sets a flag the predicate already reads.

**Trap 3 — The question path's un-park clears the pause unconditionally.**
`factory/workgraph/workflow.py:2072` is `self._paused = False`, run on every
answer or expiry, and `factory/workgraph/workflow.py:2311` does the same on the
raise path. This enforces FR-016's "MUST NOT clear a pause that another path
set" and is asserted by US7-S3. Copying that line into the peer un-park means a
peer message resuming an epic the operator pressed pause on — a press whose
whole contract (079-US4, FR-013) is that it holds until the operator resumes.
A peer park raised no pause, so it clears none.

**Trap 4 — A new `NodeState` member is a membership decision at every site that
reads the park, and this trap will not tell you how many there are.** The
previous edition of this plan named five and called the list closed; the tree had
more, and two of the ones it missed decide things a retry cannot undo. Derive the
list yourself, at the sha you are working from:

```
grep -n 'WAITING_OPERATOR\|_PARKED' factory/workgraph/workflow.py
```

At 602a92c that returns lines 332, 344, 905, 1534, 1594, 1606, 1992, 2006, 2290,
2302, 2309, 2370, 2379, 2381, 3137, 3249, 3318, 3320, 4282, 4284 and 4292 —
comments included, which you read rather than skip, because
`factory/workgraph/workflow.py:344`'s comment records what happened the last time
a park landed in the wrong set: one `PAUSE_EPIC` press ended three nodes on
2026-08-19 because `factory/workgraph/workflow.py:1496` — `_lock_out_dependents`
read `FAILED` as a dead edge. Two more sites do **not** appear in that grep and
have to be added by hand, which is the second half of this trap: the unreachable
set (`factory/workgraph/workflow.py:300`) and the terminal set
(`factory/workgraph/workflow.py:313`) name states by their own names, so a park
is defined by its *absence* from them and a grep for the park's spelling can
never find them. The decisions to take are those two, the status derivation
(`factory/workgraph/workflow.py:903`), the **merge-gated dead-edge predicate**
(`factory/workgraph/workflow.py:1534`, inside
`factory/workgraph/workflow.py:1522` — `_dead_edge`, which `continue`s past a
node in `_PARKED` and will not do so for a state that is not it — and that is
precisely the "MUST NOT change any other node's dispatch eligibility" sentence
FR-016 ends on), the drain exemption
(`factory/workgraph/workflow.py:1606`), and the **kill-while-parked branch**
(`factory/workgraph/workflow.py:2381`, inside
`factory/workgraph/workflow.py:1715` — `_run_node`, whose `elif` matches
`WAITING_OPERATOR` and whose `else` closes the node out KILLED — so a distinct
peer-park state falls through to a close-out while its coroutine is still parked
on the message wait). This enforces FR-016 and is asserted by US7-S4 and US7-S5.
The wrong move is adding the enum member, fixing whatever test goes red, and
assuming silence from the rest means correctness: most of those sites fail open.

**Trap 5 — Do not put the message lifecycle in the epic workflow.** 041-US3
moved the question lifecycle out into
`factory/escalation/question.py:90` — `QuestionWorkflow` for exactly the reason
this spec exists, and the epic now only starts a child at
`factory/workgraph/workflow.py:1980`. This enforces FR-002. The wrong move —
and it is what the 2026-08-08 edition of this plan instructed — is per-node
sibling buffers, timers and expiry loops inside the epic's own class. It swims
against the tree, re-commits the mistake 041 was written to undo, and puts a
second clock beside the child's.

**Trap 6 — Addressee-less compatibility is the contract, and it is a
short-circuit, not a branch that happens to agree.** The detector is
`factory/verify/question.py:85` — `detect_operator_question` and the heading it
matches is `factory/verify/question.py:51`. This enforces FR-001 and is asserted
by US1-S3. Parse the addressee as an optional first line of the marker or ferry
body; absence must reach the existing code path before any new code runs, and
the 008 fixtures must pass unedited. The wrong move is a new routing function
that handles `addressee is None` as one of its cases: it will be correct on the
day it is written and drift on the day somebody adds a second case above it.

**Trap 7 — Signals only buffer.** `factory/escalation/question.py:101` —
`question_answered` appends to a list and does nothing else, and the comment
above it says the handler is as incurious about the id as the epic's was. A
signal handler that routes or acts runs inside whatever workflow task delivered
it, which is how a replay stops being deterministic. This enforces FR-002 and
FR-011. All delivery decisions live on the wait-condition side.

**Trap 8 — The ferry is a pull, and US2's change must not convert it into one.**
The guard is at `factory/workgraph/adapter.py:1440`, inside
`factory/workgraph/adapter.py:1400` — `_ferry_once`. This enforces FR-019 and is
asserted by US2-S1. The wrong move is relaxing that guard so the answer poll
runs unconditionally: the existing ferry tests would still pass, and every
attempt in the factory would start polling a file nobody writes. Add an inbound
file and an inbound poll beside the existing pair, with its own state on
`factory/workgraph/adapter.py:222` — `_FerryState`.

**Trap 9 — A test whose two attempts do not overlap cannot fail.** A message
that arrives at the *next* attempt and one that arrives *mid* attempt look
identical to any test whose attempts are sequential. This enforces FR-019 and is
why US2's Independent Test says the attempts overlap in the test's own timeline.
The wrong move is a test that starts attempt B after attempt A has returned and
calls the delivery "in flight" because the code path was in-flight-shaped.

**Trap 10 — The read you are about to test for is already granted, so the test
you are about to write cannot fail.** `_build_argv` binds the whole runtime root
read-only at `factory/workgraph/adapter.py:538`, and every node worktree lives
inside it (`factory/workgraph/worktree.py:289` — `worktree_path` against
`factory/workgraph/adapter.py:815` — `home_path`). So a consult can already read
the asker's uncommitted files, and already cannot write to them, on a production
diff that changes nothing. This enforces FR-018 and is asserted by US8-S1, whose
shape exists for this reason: assert the *declared* bind in the argv the launcher
built, and assert its absence from a control invocation that carries no grant.
Two wrong moves. The first is writing the obvious test — read a file, watch a
write fail — and shipping on green; it is green today. The second is trying to
close the wider read from inside this story: that bind is on the path every
attempt takes, and narrowing it is a different spec against a shared mount set.
`hardening/agent-worktree-boundary` is open and critical at **ninety** recorded
occurrences and every one of those agents had been told to stay put, which is why
the grant is a bind and never a sentence in the prompt — but it is not evidence
that the bind is missing.

**Trap 11 — The boundary detector will charge the consult for what it read.**
`hardening/the-worktree-boundary-detector-charges-a-node-with-its-siblings-worktree`
is open at two occurrences: the detector snapshots the whole runtime root, so a
process that touches another node's worktree is attributed an out-of-boundary write against it. A
consult reading the asker's tree is precisely that shape with a second process in
it. This enforces FR-018. The wrong move is to discover the resulting critical
finding after the run and treat it as evidence the grant leaked; decide before
implementing whether the consult is inside the detector's scope at all, and say
which in the diff.

**Trap 12 — The ledger's key alias is `UNIQUE` and its termination list is
closed.** `factory/usage/ledger.py:69` is the alias column, documented as
`{epic}:{node}:{attempt}:{persona}` and used as the idempotency guard;
`factory/usage/ledger.py:77` is the `termination` CHECK, and
`factory/usage/ledger.py:188` — `_widen_terminations` is the only thing that
widens it, at connect time, from `_SCHEMA_DDL`. This enforces FR-015 and is
asserted by US5-S6. Two wrong moves, both silent: building a consult's alias the
way an attempt's is built collapses two consults into one row and overwrites the
asker's own; and adding a `Termination` member
(`factory/usage/models.py:27`) without adding it to the DDL's `IN` list means the
insert is refused on a live store. That second one already happened — the open
finding `interpreter/question-park-wedges-node-on-stale-ledger-constraint`
records a node wedged permanently by exactly that CHECK.

**Trap 13 — `cap`, `budget` and `quota` are banned words under `factory/`.**
`tests/test_final_sweep.py:471` through `tests/test_final_sweep.py:477` is the
list, and D-021 is why: this factory does not enforce spend, so its code may not
speak as though it does. This enforces FR-006 and FR-015. The requirement text
reaches you verbatim inside your prompt, so it deliberately says *limit* and
*bound*: name the configuration field and the refusal message the way
`max_concurrent_nodes must be a positive integer` is named, and the sweep stays
green. Quoting an existing symbol by its real name is fine; minting
`max_message_cap` is not.

**Trap 14 — The diff refusal threshold is its own constant now.** 092 split the
judge's attention limit from the refusal: `factory/verify/diffbounds.py:47` is
`DIFF_INPUT_LIMIT` and `factory/verify/diffbounds.py:66` is
`DIFF_REFUSAL_THRESHOLD`, both 64 KiB today, and the refusal is computed by
`factory/verify/diffbounds.py:182` — `size_refusal`. Import the constant rather
than quoting the number; any 60 KiB or 61,440 figure in an older document is
stale, and the abridgement that keeps the *judge* under its limit does not
shrink what the *refusal* counts.

**Trap 15 — A mailbox write leaves the trust boundary in both directions.**
This enforces FR-007, FR-017 and FR-020, and is asserted by US3-S1, US3-S3 and
US3-S7. Write one JSON file per message by atomic rename so no peer ever reads a
half file; an unwritable path is an immediate refusal to the asker (US3-S5),
never a retry loop inside routing. And a reply read back out of an outbox is text
a stranger could have written: it reaches a model's context, so it arrives
attributed and advisory, and it never reaches a gate or the judge.

**Trap 16 — A cross-epic signal to a workflow that is gone raises.** This
enforces FR-011 and is asserted by US4-S2. The client signal lives in an
activity because the workflow may not hold a client; catch the raise there and
degrade, because a sibling epic being finished is the same fact as a terminal
peer and must not become a workflow task failure.

**Trap 17 — A consult that asks for help is a decline.** This enforces FR-013
and is asserted by US5-S3. Scan a consult's output for the peer marker only in
order to refuse it. Without that rule a consult chain is an unbounded spawn tree
whose only stopping condition is the spawn limit, reached one message at a time.

**Trap 18 — The memory bank is optional equipment.** This enforces FR-014 and is
asserted by US5-S4's later parts. Every consult test must pass with no bank
configured; the factory must never require a Hindsight server to route a message.
The wrong move is a fixture that always configures a bank, which makes the
no-bank path untested and, worse, makes its absence look like a failure.

**Trap 19 — A close-out on the wrong side of one identity check deletes the
node's remote ref.** `factory/workgraph/workflow.py:3087` — `_close_out` gates
`archive_and_clear_remote_branch` on `factory/workgraph/workflow.py:3137`'s
`if state is not _PARKED:`, landed by 126-US2 on 2026-09-02. `_PARKED` is one
state, not a category, so a distinct peer-park state reaching any close-out path
is archived and cleared exactly like a dead node — the branch a live, parked
attempt is still working on. This enforces FR-016 and is asserted by US7-S6. The
wrong move is to read that line as "not parked" and assume a park is a park; the
right one is to make the predicate ask about the category and to say in the diff
which states are in it. The same reading applies to
`factory/workgraph/workflow.py:3320` and `factory/workgraph/workflow.py:4292`,
which write `_PARKED` on paths that did not exist when this spec was drafted.

**Trap 20 — US6 lands no park, no limit and no guard, and taking one is how the
split gets undone.** The 2026-09-04 splits put every scheduler property in US7
and the two safety properties in US9, leaving US6 the routing, the buffers, the
child workflow, the prompt section and the degradation floor. US6's asker sends
and its attempt ends; the reply arrives in its next assembled prompt. This
enforces FR-002 and is what US6's Independent Test measures. The wrong move is an
implementer who reaches for `factory/workgraph/workflow.py:2006`'s park block
"while I am in here anyway" — that is US7's whole content and US7's whole risk —
or who adds the outstanding-message limit because the routing code is open in
front of them, which is US9's. Both stories are sized without the routing, and
the routing is sized without them.

**Trap 21 — There is no sweep surface list to add a name to.** Both credential
sweeps drive the component and then walk a tree
(`tests/test_verification_sweep.py:418` and `tests/test_workgraph_sweep.py:410`).
This enforces FR-007, FR-020 and FR-021. The wrong move is to grep for a list of
surface names, find none, and invent a production sweep module — the killed
2026-08-29 attempt did exactly that, adding `factory/verify/sweeps.py`, and the
result was 2.7 KiB of new production code doing what an existing test already
does. Extend the run instead: make the sweep write a message, send an external
message, or write a consult config, and its existing walk covers those bytes.

**Trap 22 — pasting an assembled prompt as evidence spends the story's whole
size.** `factory/workgraph/prompt.py` states its own rule in its module
docstring: nothing is summarized or truncated, and "the story's section, the
whole plan and the task slice arrive exactly as they were authored". So an
assembled prompt for *this* spec carries the whole of `plan.md` — 41,581 bytes at
602a92c and over 45 KiB once this pass's traps and sizing were written into it —
before its story section and its slice. The refusal threshold is 65,536
(`factory/verify/diffbounds.py:66`), computed over the assembled diff text
including pasted evidence (`factory/verify/diffbounds.py:182` — `size_refusal`).
This enforces D-050 and it is why every verification task in `tasks.md` that
wanted "the assembled prompt" now asks for the peer-message section and the lines
immediately around it. The wrong move is to paste the prompt whole because it is
the most convincing artifact available: it is also larger than the headroom of
every story in this spec, and the attempt is refused unjudged rather than failed
— no verdict, no feedback, one dispatch spent.

## Sizing

Two kinds of figure appear below and they are labelled, because the previous
edition opened "every figure below is measured, not estimated" and then gave
figures for three stories of seven.

**Measured, from `3c04efd`.** That commit (2026-08-29) is the salvage of the
**killed** attempt on the old US1 — the story that carried US1, US6, US9 and US7
at once. Fifteen files, 111,655 diff bytes, no pasted evidence in any of them,
against `factory/verify/diffbounds.py:66`'s `DIFF_REFUSAL_THRESHOLD` of 65,536
(`factory/verify/diffbounds.py:182` — `size_refusal` is what applies it). Its
per-file bytes are:

```
29125 tests/test_peer_message.py          3623 factory/workgraph/models.py
24916 factory/workgraph/workflow.py       2872 factory/verify/question.py
12275 factory/verify/store.py             2710 factory/verify/sweeps.py
11014 factory/activities/notify_activities.py  2326 factory/worker.py
 6982 factory/workgraph/prompt.py         1558 factory/verify/models.py
 5750 factory/escalation/message.py       1369 tests/test_verify_store.py
 4428 factory/verify/peer_grammar.py      1117 factory/notify/service.py
 4425 tests/test_interpreter.py
```

Read that as a **floor, not a size**: the attempt was killed before it finished,
so what it had written is a lower bound on what the story costs to land. Every
figure apportioned from it inherits that. The margin for the unfinished remainder
is carried in the test bytes, and it is stated here as a figure rather than left
implicit: the four stories cut out of that attempt are allotted roughly 49.5 KiB
of tests between them (US1 near 16.5, US6 14, US7 9, US9 10) against the 33,550
test bytes the salvage actually contains — a ~50% over-allocation, deliberate,
and it is the floor correction rather than headroom to spend on pasted evidence.
Every per-story figure below is quoted with that allowance already inside it.
(`factory/verify/sweeps.py` is in the list as a warning, not a line item: trap 21
says why that module should not exist.)

**Estimated, against named comparables.** The four stories with no salvage
counterpart — US5, US8, US2, US3 — are sized against modules of the same shape
already in this tree, named in each paragraph. An estimate against a named
comparable is not a measurement and is not written as one.

**US1** (measured) touches `factory/verify/question.py`,
`factory/verify/store.py` and
`specs/002-verification-gating/contracts/verification-store.sql` (the `messages`
table, in both copies), a new `factory/verify/peer_grammar.py`, and the driven
run inside `tests/test_verification_sweep.py`. No interpreter file. Its side of
the salvage totals 22,502 bytes of production and near-production; with its share
of the peer-message tests it lands near 39 KiB. Comfortable.

**US6** (measured) touches `factory/workgraph/workflow.py` (routing, buffers, the
child start), `factory/workgraph/prompt.py` (the peer-message section and its
dataclass), `factory/activities/notify_activities.py`, `factory/notify/service.py`,
`factory/worker.py` (the new child must be registered), and adds
`factory/escalation/message.py`. Those files total 52,105 bytes in the salvage,
from which US7 takes the park sites (near 14 KiB) and US9 takes the limit and the
guard: what is left for US6 is near 34 KiB of production. With its share of the
salvage's 33,550 bytes of tests — call it 14 KiB — US6 lands near 48 KiB against
65,536, and T059's evidence is bounded to the peer-message section of one prompt
rather than a whole prompt (trap 22). The previous edition put this story at
55 KiB "with roughly 10 KiB of headroom", against an evidence list that omitted an
assembled prompt; the prompt alone would have consumed all of it, which is why
US9 is a story and not a paragraph of this one. **US6 is the story to re-measure
first if any figure here proves low**, and the one to split again if it does: it
is the largest in the spec, its 17 KiB of nominal headroom is the thinnest, and
it is the only story whose production base is a killed attempt rather than a
finished comparable. A story that crosses 65,536 is refused unjudged — no
verdict, no feedback, one dispatch spent (trap 22) — so the cost of being wrong
about US6 is higher than being wrong about any other paragraph here.

**US9** (estimated) touches the routing seam US6 lands — the configuration field
and its refusal — plus the two guard tests
(`tests/test_interpreter.py:3591` and `tests/test_workgraph_sweep.py:1168`).
Comparable: the scheduler's own limit refusal is a handful of lines at
`factory/workgraph/workflow.py:970`. Near 8 KiB of production and 10 KiB of
tests, plus T068's refusal line. It is the smallest story here, deliberately: it
exists to take two safety properties off a story whose measurement is a floor.

**US7** (measured) touches `factory/workgraph/workflow.py` at the park sites Trap
4 enumerates and `factory/workgraph/models.py` (one enum member): near 14 KiB of
production and 9 KiB of tests, plus T058's node-state timeline and T064's branch
listing — near 25 KiB. It is the smallest interpreter story and the most
dangerous one, which is the shape the split was made to produce.

**US5** (estimated) touches `factory/activities/consult_activities.py` (new), the
routing seam US6 landed, and the ledger's termination vocabulary in both copies
of the DDL. Comparable: the activity modules already in this tree run 26,311
(`factory/activities/usage_activities.py`) to 46,821
(`factory/activities/agent_activities.py`) bytes whole; a consult runner is the
narrow end of that family — context assembly, spawn bracket, reply extraction,
recursion refusal, spawn limit, config write — so near 24 KiB of production, near
16 KiB of tests, and evidence that is two ledger rows and a refusal. Near 42 KiB.
This story had **no figure at all** before 2026-09-04 and carried the sandbox
grant as well; US8 is what came out of it.

**US8** (estimated) touches `factory/workgraph/adapter.py`: a typed field on
`factory/workgraph/adapter.py:293` — `AgentInvocation` (16 lines, 532 bytes
today) and one bind tuple inside
`factory/workgraph/adapter.py:464` — `_build_argv` (163 lines, 8,560 bytes
today) — plus one call site in `factory/activities/consult_activities.py`, the
module US5 lands, where the field is set. Near 3 KiB of production, near 9 KiB of
tests including the guarded live one, and evidence that is two argv listings and
one failed write. Near 14 KiB. The shared call site is one reason its edge on US5
is a merge-edge; the other is that a field with no setter is untestable end to
end.

**US2** (estimated) touches `factory/workgraph/adapter.py` (the inbound direction
on `_FerryState` and `_ferry_once`), `factory/activities/notify_activities.py`
and `factory/activities/agent_activities.py` (the callback wiring), and the
prompt instructions. Comparable, and it is an exact one: the existing *pull*
direction is `factory/workgraph/adapter.py:222` — `_FerryState` (2,564 bytes),
`factory/workgraph/adapter.py:1400` — `_ferry_once` (2,510),
`factory/activities/notify_activities.py:958` — `ferry_send_question` (953) and
`factory/activities/notify_activities.py:982` — `ferry_read_answer` (1,052) —
7,079 bytes for the whole direction. The push direction is that shape again: near
8 KiB of production, near 14 KiB of tests, near 24 KiB with T016's bounded
evidence.

**US3** (estimated) adds `factory/notify/peers.py` and
`factory/activities/peer_activities.py`, both new, plus the mirror and the driven
run inside `tests/test_workgraph_sweep.py`. Comparables:
`factory/notify/adapter.py` is 10,568 bytes whole and
`factory/escalation/client.py` is 6,811. Near 17 KiB of production, near 18 KiB
of tests across seven scenarios, near 37 KiB. It is the largest *estimated*
story, with 28 KiB of headroom against the refusal threshold — comfortable enough
that US6, not this one, is what gets re-measured first.

**US4** (estimated) touches `factory/activities/peer_activities.py` and the two
documents. Near 15 KiB, most of it prose.

Stories sharing no production file: US1 and US2 share none; US1 and US3 share
none; US1 and US5 share none; US3 and US5 share none; US5 and US7 share none;
US8 and US9 share none. US5 and US8 share exactly one — the consult launcher's
call site — which is why US8 follows US5 through the merge queue rather than
beside it. That is a statement about merge
conflicts, not about dispatch — every edge in this spec is a merge-edge because
every dependent imports a module its predecessor lands, so the chain is serial
whatever the file overlap. At the configured concurrency of 2 (`ergane.yaml:151`)
that serialisation costs real wall-clock: the epic runs one node at a time where
it could run two. It is paid on purpose.

## Verification the operator will run, independent of the gate

1. **Watch one peer exchange live.** Start the epic with
   `max_concurrent_nodes` at 1, let a node address a question to a peer, and
   watch Temporal's Web UI on port 8233: the asker parks, and the *addressee is
   dispatched while it is parked*. If the epic goes quiet, the park took a slot
   or the scheduler never woke — trap 1 or trap 2 — and no test will tell you.
2. **Press pause during a peer park, then let the reply land.** The epic must
   stay paused. If it resumes, trap 3 landed.
3. **Kill a node whose dependents are waiting behind a peer-parked node.** The
   dependents must stay PENDING, not KILLED — and the peer-parked node's own
   remote branch must still exist afterwards (trap 19). That is the 2026-08-19
   shape (trap 4) reproduced deliberately, with 126's ref deletion on top of it.
4. **Read the consult's own worktree grant from the argv, and prove the control
   (US8).**
   With a consult in flight, inspect the launched `bwrap` argv for exactly one
   `--ro-bind` naming the asker's worktree and no `--bind` naming it. Then note
   what the same argv already contains: a `--ro-bind` over the runtime root
   (`factory/workgraph/adapter.py:538`), which covers that worktree anyway. The
   check that means something is the negative — launch a consult with the grant
   field unset and confirm no bind names the asker's worktree. Only then run the
   epic once with the don't-write instruction removed from the consult prompt and
   confirm the write still fails.
5. **Check the ledger after two consults from one attempt.** `ergane usage --by
   epic` must show two rows, not one, and the asker's own attempt row must be
   intact (trap 12).
6. **Send one message to the homelab peer by hand** and confirm the inbox file,
   the mirror notification, and that a reply file placed in the outbox reaches
   the asker's next prompt — with no human touching a spec or prompt file.

## Instrument traps carried forward from 2026-08-16

**Purge `__pycache__` between mutants**, or run under `PYTHONDONTWRITEBYTECODE=1`.
CPython validates a cached `.pyc` on `(mtime-in-whole-seconds, size)` only, so
two same-size mutants written inside one wall-clock second make the second run
execute the *first* mutant's bytecode. It fails toward green and reproduces
stably.

**Quote `passed` and `skipped`, never the warning count** — a warm cache
suppresses compile-time warnings. A new skip is a hidden test you must declare,
and US8-S3 declares one deliberately.

**Assert against the world, not a call log.** "We routed the message" is a claim
about your own code; "the addressee's assembled prompt contains it", "the
addressee was dispatched while the asker was parked" and "neither attempt
terminated" are claims about the world. Only the second kind would have caught
the park deadlock this spec was held for.
