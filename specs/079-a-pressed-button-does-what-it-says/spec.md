---
state: landed
fixes:
  - escalation/an-answered-question-never-unparks-the-node
  - escalation/kill-stops-the-node-and-leaves-the-epic-running-holding-a-fresh-escalation
  - escalation/retry-on-an-exhausted-ladder-cannot-retry-and-re-escalates-instantly
  - escalation/retry-on-an-exhausted-ladder-kills-the-node
  - interpreter/escalation-retry-kills-the-node
  - interpreter/pause-epic-park-kills-dependents
  - notify/a-pressed-button-on-a-live-escalation-never-reaches-the-store
# Attested landed 2026-08-22. US1 9e41dbc42ef6 (#274), US2 89b9a9bb144b (#275),
# US3 a20e5b63427c (#276), US4 0fcbbc041a39 (#277) -- all four observed on
# ergane-buildout. US2 through US4 were the first stories dispatched after
# constitution 2.5.0 (D-050) reached the landing branch; all landed first-attempt.
#
# FLIPPED draft -> ready 2026-08-21 8:25 AM CT at the operator's instruction,
# after he read the rendered page. What the pre-dispatch review did:
#
#   - ANCHORS: 93 — the most of any spec in this batch — all resolving against
#     `origin/ergane-buildout` at 669006d.
#   - **THE FIRST PASS WAS AGAINST THE WRONG TREE**, and this spec took the worst
#     of it: nearly every `factory/workgraph/workflow.py` citation was stale,
#     because the operator checkout was five commits behind and that file had
#     grown 61 lines. Re-derived by exact line-text match against the origin
#     tree, never by offset. See 078's frontmatter for the full account.
#   - Six bare `:NN` references in trap paragraphs named no file. Now qualified.
#   - ONE FINDING DROPPED AS ALREADY FIXED rather than built:
#     `interpreter/a-null-escalation-child-crashes-the-landing-path-and-kills-
#     the-node` is guarded at both dereference sites in the tree today. It is
#     named out of scope below so no implementer rebuilds it.
#
# Drafted 2026-08-21 ~8:00 AM CT by an operator session, at the operator's
# instruction, before the first PyPI release since v0.1.0 and before a repeat of
# the tharpebox install/build experiment.
#
# WHY THIS SPEC AND NOT A LIST OF FIXES. Four open criticals share one shape:
# the operator's only control surface offers actions that do not do what they
# say. Three of the four were measured in the last thirty-six hours, on this
# floor, by the operator himself:
#
#   2026-08-19 22:08  KILL pressed three times on one node; each answered KILL
#                     was followed within a second by a NEW escalation asking the
#                     identical question. Four workflow ids, four store rows, and
#                     only a hand-run `temporal workflow terminate` ended it.
#   2026-08-21 03:18  RETRY pressed on 075/us1's escalation AFTER recovery_cycles
#                     hit its cap of 1. The signal was delivered and the row
#                     resolved RETRY pre-expiry. The epic's next activity was
#                     `remove_worktree` -- no `issue_attempt_key`, no
#                     `run_agent_attempt`. us1 KILLED at attempt 2, us3
#                     cascade-KILLED at attempt 0. **A choice that is offered
#                     must be executable, or pressing it is a kill wearing a
#                     retry label.**
#   2026-08-21 03:16  A RETRY pressed on a LIVE escalation (f54b3a73c3b9, the
#                     operator confirmed it was not a stale message) produced NO
#                     Temporal signal, NO store transition, and the row still read
#                     resolution=NULL an hour later. `ergane-bridge.service` was
#                     loaded/active/running the whole window.
#   2026-08-21 06:05  073/us3's operator question was ANSWERED -- the
#                     `question_answered` signal delivered, the QuestionWorkflow
#                     child COMPLETED at 06:05:56Z -- and the node stayed
#                     WAITING_OPERATOR, holding us4 and us5 PENDING behind it. A
#                     no-handler nudge changed nothing; a worker restart replayed
#                     the full history with zero pending activities and reproduced
#                     the identical park, so the wedge is deterministic in the
#                     workflow's answered branch, not a lost wakeup.
#
# WHAT 068 ALREADY LANDED, and why this is not a re-run of it. 068 gave the
# escalation a four-value vocabulary and made KILL_EPIC and PAUSE_EPIC distinct
# from KILL. That was right and it holds. What 068 did not do is make the OFFER
# depend on the node's actual remaining budget: `DEFAULT_CHOICES`
# (`factory/activities/notify_activities.py:117`) is a module constant, and both
# escalation sites pass `choices=list(DEFAULT_CHOICES)` unconditionally
# (`factory/workgraph/workflow.py:2442` and `:3280`). The node's exhaustion is
# known at exactly those two call sites and is not consulted.
#
# ONE FINDING FROM THIS CLUSTER IS ALREADY FIXED AND IS DELIBERATELY OUT OF
# SCOPE. `interpreter/a-null-escalation-child-crashes-the-landing-path-and-kills-
# the-node` cited an unguarded dereference. Both sites are guarded in the tree
# today -- `factory/workgraph/workflow.py:2446` (`if outcome is None: return
# None`) and `:3285` (`if outcome is None or not outcome.delivered:`). It should
# be verified and resolved in the ledger, not built again.
#
# Filed as, all critical and all open:
#   escalation/retry-on-an-exhausted-ladder-kills-the-node
#   escalation/kill-stops-the-node-and-leaves-the-epic-running-holding-a-fresh-escalation
#   notify/a-pressed-button-on-a-live-escalation-never-reaches-the-store
#   escalation/an-answered-question-never-unparks-the-node
#   interpreter/pause-epic-park-kills-dependents
---

# Feature Specification: a pressed button does what it says

## The gap, stated precisely

An escalation is the factory's only synchronous request to a human. It arrives
on a phone with four buttons. Today the offer is a constant: every escalation
shows the same four choices regardless of whether the node behind them has an
attempt left, a recovery cycle left, or a coroutine still waiting to act on the
answer.

The consequences are not cosmetic and they are not rare:

- **RETRY on a node with nothing to retry with ends it.** The press is recorded,
  the signal is delivered, the ladder finds no grant, and the node is torn down.
  The operator reads that as the factory ignoring them; it is worse, because a
  dependent chain is cascade-killed in the same pass.
- **A press can vanish.** One press on a live escalation produced no signal and
  no row transition, with the bridge running, and the operator had no path to
  answer short of replicating the bridge's signal-and-resolve sequence by hand.
- **An answer can be consumed without effect.** The question channel delivered
  the answer, completed its child, and left the node parked.
- **PAUSE_EPIC is a third way to end the work.** It parks the node into `FAILED`,
  which is in `_UNREACHABLE`, so `_lock_out_dependents` kills every dependent at
  attempt 0 — and neither the Telegram message nor any CLI output names that
  blast radius before the press.

## The rule this spec is asking for

**An offered choice is an executable choice, a press is an act, and an act the
factory cannot perform is refused by name rather than performed as something
else.** Every requirement below is that sentence applied to one surface.

## What this spec does not change

- The four-value vocabulary. 068's `EscalationChoice` is correct; this narrows
  *when* each is offered, and never invents a fifth.
- The escalation transport. Delivery, the inline keyboard, the callback format
  and the expiry timer all work and are explicitly praised in the field report.
- The signal-before-resolve ordering in the bridge
  (`factory/notify/service.py:16-26`). That ordering is deliberate and correct;
  US2 is about a press that reached neither step.
- The ladder's rungs, the budgets themselves, or `max_recovery_cycles`'s value.
  That the landing budget has no operator dial is a separate spec.
- Anything about the question channel other than the park it leaves behind.

## User Scenarios & Testing

### User Story 1 - An escalation offers only what this node can execute (Priority: P1)

As an operator answering an escalation, every button I am shown will do what its
label says when I press it, because the offer was computed from what the node
can still do.

**Why this priority**: P1 and it is the spine. Two of this cluster's criticals
are one press each; this is the change that makes a press meaningful at all.

**Independent Test**: raise an escalation on a node with no attempt and no
recovery cycle left and assert `RETRY` is not among the offered choices.

**Acceptance Scenarios**:

1. **Given** a node whose verification ladder has no attempt left, **When** its
   escalation is raised, **Then** `RETRY` is not offered — proven by a committed
   test asserting the choice list handed to the escalation, not the enum.
2. **Given** a node whose landing recovery cycles are spent
   (`recovery_cycles >= max_recovery_cycles`), **When** its landing escalation is
   raised, **Then** `RETRY` is not offered — proven by a committed test. This is
   the exact configuration of 075/us1 at 03:18Z on 2026-08-21.
3. **Given** a node with an attempt remaining, **When** its escalation is raised,
   **Then** `RETRY` **is** offered and pressing it grants an attempt — proven by
   a committed test asserting the attempt is issued. **This is the control**: a
   change that satisfies scenarios 1 and 2 by never offering `RETRY` has removed
   the feature rather than fixed it.
4. **Given** any escalation, **When** it is raised, **Then** at least one choice
   is offered and every offered choice is executable — proven by a committed
   test. An escalation with an empty keyboard is a park with no exit.
5. **Given** a resolution arrives naming a choice that was not offered — a stale
   message, a replayed callback — **When** it is applied, **Then** it is refused
   by name and recorded, rather than falling through to the kill branch — proven
   by a committed test. The fall-through at `factory/workgraph/workflow.py:3324`
   currently turns *anything unoffered* into a kill.
6. **Given** an answered `KILL`, **When** the node ends, **Then** no new
   escalation is raised for that node — proven by a committed test that answers
   `KILL` and asserts exactly one escalation exists for the node afterwards. On
   2026-08-19 three answered kills produced three fresh escalations.

---

### User Story 2 - A pressed button lands, or the operator is told why (Priority: P1)

As an operator pressing a button on my phone, the press either changes the
node's state or comes back to me as a named refusal in the same chat — never
silence.

**Why this priority**: P1. The offer being correct is worth nothing if the press
does not arrive, and on 2026-08-21 a press on a live escalation arrived nowhere
at all.

**Independent Test**: drive one callback press through the bridge and assert
exactly one of {signal sent and row resolved} or {named refusal returned to the
operator} happens, for every reachable branch.

**Acceptance Scenarios**:

1. **Given** a press on a live escalation, **When** the bridge handles it,
   **Then** the signal is sent and the row is resolved — proven by a committed
   test.
2. **Given** a press the bridge cannot act on — the row is gone, the signal
   fails, the workflow is not running, the press is unauthorized — **When** the
   bridge handles it, **Then** the operator receives a message naming the reason
   — proven by a committed test per reachable branch. **Every branch must be
   enumerated from the code rather than listed by hand**; one of them swallowed a
   press and nobody can say which.
3. **Given** any press, **When** the bridge handles it, **Then** the handling is
   recorded where an operator can read it without attaching a debugger — proven
   by a committed test. The 03:16Z press left no trace anywhere: no signal, no
   row change, no log line naming the escalation id.
4. **Given** a press that is genuinely stale — an escalation already resolved or
   expired — **When** it is handled, **Then** the existing behaviour is unchanged
   and the operator is told it was stale — proven by a committed test. **This is
   the control**: making every press "land" by removing the staleness guard would
   let an old message re-answer a live node.
5. **Given** the live bridge on this host, **When** the operator presses a button
   on a real escalation, **Then** paste the resulting store row and signal into
   the diff. The suite passing is what was true at 03:16Z.

---

### User Story 3 - An answered question un-parks the node (Priority: P1)

As an operator who has answered an agent's question, the node resumes and the
answer reaches the next attempt's prompt.

**Why this priority**: P1. The question channel's first live exercise failed end
to end, and it failed in the most expensive shape available: the epic held its
undispatched nodes behind a park that no signal could clear.

**Independent Test**: park a node on a question, answer it, and assert the node
leaves `WAITING_OPERATOR` and the next attempt's prompt carries the exchange.

**Acceptance Scenarios**:

1. **Given** a node parked on an operator question, **When** the question is
   answered, **Then** the node leaves `WAITING_OPERATOR` and a new attempt is
   dispatched — proven by a committed test.
2. **Given** the same, **When** the next attempt's prompt is assembled, **Then**
   it carries the question and the answer verbatim — proven by a committed test
   asserting the assembled prompt string.
3. **Given** the same, **When** the node resumes, **Then** the epic's scheduler
   resumes dispatching its other nodes — proven by a committed test asserting a
   sibling that was `PENDING` behind the park is dispatched. This is the half
   that cost 073 its morning: two stories waited behind one park.
4. **Given** a question that expires unanswered, **When** the window closes,
   **Then** the existing behaviour is unchanged — the ladder re-enters with a
   FAIL — proven by a committed test. **This is the control.**
5. **Given** the tree as it stands, **When** the reproduction is run before the
   fix, **Then** it parks — paste that run into the diff alongside the run after.
   The park replayed identically across a worker restart with zero pending
   activities; it is deterministic and it reproduces.
6. **Given** a live store whose `usage_records` DDL predates the `question`
   termination value, **When** an attempt parks on a question, **Then** the
   teardown succeeds or the failure is named — proven by a committed test. The
   DDL in the tree (`factory/usage/ledger.py:76-78`) already lists `question`;
   an installed store from before it does not, and that is a different failure
   with the same symptom.

---

### User Story 4 - A pause parks; it does not kill what is left (Priority: P2)

As an operator pressing PAUSE_EPIC, the epic stops dispatching and its
undispatched nodes are still there when I resume.

**Why this priority**: P2, below the three above only because it has been
observed once rather than repeatedly. Its blast radius is the largest of the
four: one press ended three nodes.

**Independent Test**: press PAUSE_EPIC on a node with dependents and assert the
dependents are still dispatchable after a resume.

**Acceptance Scenarios**:

1. **Given** a node with dependents, **When** PAUSE_EPIC is answered on its
   escalation, **Then** the dependents are not killed — proven by a committed
   test asserting their states.
2. **Given** the same epic, **When** it is resumed, **Then** the undispatched
   nodes dispatch — proven by a committed test. A park whose work cannot be
   resumed is a kill with a longer name.
3. **Given** an escalation offering PAUSE_EPIC, **When** the operator reads it,
   **Then** the message names what the press will do to the node and to the
   epic's other work — proven by a committed test asserting the rendered message
   text. The blast radius must be readable before the press, not inferred after.
4. **Given** a KILL press, **When** it is applied, **Then** the dependent
   lock-out behaves exactly as it does today — proven by a committed test.
   **This is the control**: `_lock_out_dependents` is correct for a killed node
   and must not be weakened.
5. **Given** a PAUSE_EPIC press, **When** the epic is later reset or killed by an
   operator, **Then** `ergane build reset` can act on the resulting state —
   proven by a committed test. A park the operator cannot get out of by the
   documented verb is the deadlock the field report named.

## Requirements

### Functional Requirements

- **FR-001**: The choices offered on an escalation MUST be computed from the
  node's remaining budgets at the moment the escalation is raised.
- **FR-002**: `RETRY` MUST NOT be offered when no attempt or recovery cycle
  remains, and MUST grant one when it is offered and pressed.
- **FR-003**: Every escalation MUST offer at least one executable choice.
- **FR-004**: A resolution naming a choice that was not offered MUST be refused
  by name and recorded, not applied as a kill.
- **FR-005**: An answered `KILL` MUST NOT be followed by a fresh escalation for
  the same node.
- **FR-006**: Every handled press MUST result in exactly one of: a delivered
  signal with a resolved row, or a named refusal returned to the operator.
- **FR-007**: Every handled press MUST be recorded where an operator can read it
  without a debugger, naming the escalation id.
- **FR-008**: A stale press MUST remain refused, and the refusal MUST say it was
  stale.
- **FR-009**: An answered question MUST un-park its node and dispatch a new
  attempt.
- **FR-010**: The question and its answer MUST reach the next attempt's prompt.
- **FR-011**: Un-parking a node MUST release the epic's scheduler to dispatch
  siblings.
- **FR-012**: An expired question MUST retain today's behaviour.
- **FR-013**: `PAUSE_EPIC` MUST NOT place a node in a state that locks out its
  dependents.
- **FR-014**: A paused epic's undispatched nodes MUST dispatch on resume.
- **FR-015**: An escalation message MUST name what each offered choice does to
  the node and to the epic.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
  persona: opus-closer
US2:
  depends_on: []
  implements: [FR-006, FR-007, FR-008]
  persona: opus-closer
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-009, FR-010, FR-011, FR-012]
  persona: opus-closer
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-013, FR-014, FR-015]
  persona: opus-closer
```

US1, US3 and US4 all edit `factory/workgraph/workflow.py`; the chain is
contention, not logic, and declaring them independent while they share that file
is the defect 069-US2 exists to prevent. US2 edits `factory/notify/service.py`
and shares nothing with the chain, so it runs alongside.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste the choice list raised for a node with nothing left, showing
  `RETRY` absent, and for a node with an attempt left, showing it present.
- **SC-002**: Paste a `RETRY` press on a node with budget, showing the attempt
  key issued after it.
- **SC-003**: Paste an answered `KILL` and the count of escalations for that node
  afterwards.
- **SC-004**: Paste the enumeration of the bridge's press-handling branches and
  the outcome each produces.
- **SC-005**: Paste a real press on a real escalation on this host, with the
  resulting store row and the signal.
- **SC-006**: Paste the question reproduction before the fix (parked) and after
  (resumed), including the sibling that was waiting.
- **SC-007**: Paste the assembled prompt carrying the question and answer.
- **SC-008**: Paste a PAUSE_EPIC press with dependents, showing their states
  after, and the same epic dispatching them after a resume.
- **SC-009**: Paste the rendered escalation message showing what each offered
  choice will do.

## Assumptions

- The node's remaining verification attempts and remaining landing recovery
  cycles are both known at the two sites that raise escalations. Verified
  2026-08-21: `factory/workgraph/workflow.py:2813` and `:2851` both compute
  exhaustion against `config.max_recovery_cycles` in the same method that raises
  the landing escalation.
- The 073/us3 question park is deterministic in workflow code. Evidenced by a
  worker restart that replayed the full history with zero pending activities and
  produced the identical park.
- `interpreter/a-null-escalation-child-crashes-the-landing-path-and-kills-the-node`
  is already fixed in the tree and is out of scope. If an implementer finds an
  unguarded dereference this spec did not name, it is in scope and should be said
  out loud in the diff.
</content>
