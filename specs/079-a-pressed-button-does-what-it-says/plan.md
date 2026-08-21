# Implementation Plan: a pressed button does what it says

**Spec**: `specs/079-a-pressed-button-does-what-it-says/spec.md`

## What already exists, and where

**Every line number below was verified on 2026-08-21 by printing that exact line
individually** (`sed -n '<n>p' <file>`). The findings this spec came from carry
anchors that are two hundred to four hundred lines stale — the tree moved under
them during 067-071. Check each one anyway.

**The offer, which is a constant:**

- `factory/activities/notify_activities.py:117` — `DEFAULT_CHOICES = (`, with
  `RETRY`, `KILL`, `PAUSE_EPIC`, `KILL_EPIC` on the four lines below it.
- `factory/workgraph/workflow.py:2442` — `choices=list(DEFAULT_CHOICES),` — the
  verification-ladder escalation.
- `factory/workgraph/workflow.py:3280` — `choices=list(DEFAULT_CHOICES),` — the
  landing escalation. **Both sites, or the fix is half a fix.**
- `factory/verify/models.py:125` — `class EscalationChoice(StrEnum):`, values at
  `:140-143`. Read its docstring: 068's reasoning for the four values is there
  and it is right. This spec narrows the offer, not the vocabulary.
- `factory/activities/notify_activities.py:168` —
  `choices: list[EscalationChoice] = field(default_factory=lambda: list(DEFAULT_CHOICES))`
  — the request dataclass's own default. A caller that passes nothing still gets
  all four; decide whether that default should survive.

**Where exhaustion is already known, at the moment of the offer:**

- `factory/workgraph/workflow.py:2813` — `if not granted and landing.recovery_cycles >= config.max_recovery_cycles:`
- `factory/workgraph/workflow.py:2851` — `if not granted and spent >= config.max_recovery_cycles:`
- `factory/workgraph/workflow.py:2850` — `spent = record.landing.recovery_cycles`
- `factory/workgraph/workflow.py:484` — `recovery_cycles: int = 0` on the landing
  record.
- For the verification ladder, `_attempts_spent` and the ladder's own rungs in
  `factory/verify/ladder.py` — `:39` and `:45` document what `PAUSE_EPIC` ends
  and why. Read them before changing what is offered.

**The fall-through that turns anything unoffered into a kill:**

- `factory/workgraph/workflow.py:3309` — `if resolution == EscalationChoice.KILL_EPIC.value:`
- `:3315` — `if resolution == EscalationChoice.PAUSE_EPIC.value:`
- `:3316` — `self._paused = True`, `:3317` — `self._epic_state = EpicState.PAUSED`
- `:3318-3320` — `await self._close_out(... Termination.KILLED, state=NodeState.FAILED)`
- `:3322` — `record.state = NodeState.FAILED`  ← **the PAUSE_EPIC defect, in one line**
- `:3324` — `# KILL, EXPIRED, or anything unoffered — all end the node killed.`

**Why `FAILED` kills the dependents:**

- `factory/workgraph/workflow.py:280` — `_UNREACHABLE = frozenset({NodeState.FAILED, NodeState.KILLED})`
- `factory/workgraph/workflow.py:1219` — `def _lock_out_dependents(self, resolved: Sequence[ResolvedNode]) -> None:`
- `:1248` — `self._nodes[dependency].state in _UNREACHABLE`
- `:1257` — `if record.state in _UNREACHABLE or self._landing_unmerged_terminal(`
- `factory/workgraph/models.py:93` — the comment explaining that
  `WAITING_OPERATOR` is *deliberately* not in `_UNREACHABLE`, "a parked question
  is not…". **That comment is the precedent for what PAUSE_EPIC needs.** Read it
  before inventing anything.
- The ladder's own PAUSE_EPIC half is a different path:
  `factory/workgraph/workflow.py:1781-1787`, which sets `parked = True` and
  `self._paused = True` without going through `:3322`. Trace both before you
  decide where the state assignment belongs.

**The question park, and the branch that should un-park it:**

- `factory/workgraph/workflow.py:1638` — `question = await workflow.start_child_workflow(`
- `:1661` — `record.state = NodeState.WAITING_OPERATOR`
- `:1662` — `record.pending_question_id = question.id`, `:1663` — `self._paused = True`
- `:1668` — `await self._teardown(lease, termination, record.last_snapshot)`
- `:1675-1677` — `await workflow.wait_condition(lambda: question.done() or self._kill_requested)`
- `:1687` — `answered = await question`
- `:1703-1716` — the answered branch, which sets `record.operator_answer`
- `:1726-1728` — `record.pending_question_id = None`, `self._paused = False`,
  `continue`
- `factory/workgraph/workflow.py:1319` — the scheduler's skip:
  `if self._nodes[node_id].state != NodeState.WAITING_OPERATOR`
- `factory/workgraph/workflow.py:1307-1313` — the docstring describing the park's
  intended resume semantics.

**Read that block and then read this: the code above looks correct.** It waits,
it takes the answer, it clears the pause and it `continue`s. On 073/us3 it
nonetheless left the node in `WAITING_OPERATOR` with the child COMPLETED. **Do
not guess which line is wrong. Reproduce it first** (US3-S5) and let the
reproduction name the line. Two candidates worth eliminating early, neither
confirmed: the `continue` re-enters the `while True` loop but the next state
assignment is `record.state = NodeState.KEY_ISSUED` at
`factory/workgraph/workflow.py:1549` — check whether
anything can return before reaching it; and `self._paused = False` at `:1727`
must actually wake the scheduler's `wait_condition` at `:819-822`.

**The bridge, where a press can vanish:**

- `factory/notify/service.py:431` — `async def handle(self, update: Any) -> BridgeOutcome:`
- `:439` — `query = getattr(update, "callback_query", None)`
- `:449` — the unauthorized-press guard, before any lookup
- `:474` — `if not await self._signal(record, pressed):`
- `:482` — the stale-read branch after a signal is in flight
- `:287` / `:301` — `relay` and its own `callback_query` read, a second entry
  point into the same machinery
- `:497` — `async def handle_reply`, `:548` — `handle_relay`, `:563` —
  `_settle_question` — the question-answer siblings
- `:16-26` — the docstring's four numbered decisions. **Signal before resolving
  is deliberate and correct.** The 03:16Z press did neither.
- `:165` — "Every value except RESOLVED means no signal was sent." The
  `BridgeOutcome` vocabulary already exists; the question is which value the
  vanished press produced and where it went.

**The stores:**

- `factory/verify/store.py:912` — `def resolve_escalation(`
- `factory/verify/store.py:194` — the `resolution` CHECK constraint
- `factory/verify/store.py:347-348` — `_OLD_RESOLUTIONS` / `_NEW_RESOLUTIONS`,
  the migration precedent for widening a CHECK on a live store
- `factory/verify/store.py:1242` — `def resolve_question(`
- `factory/usage/ledger.py:76-78` — the `termination` CHECK, which **does** list
  `'question'` in the tree today. An installed store created before it does not.

## Traps

**1. Do not add a fifth choice.** The vocabulary is 068's and it is right. This
spec changes when each of the four is offered.

**2. Both escalation sites.** `factory/workgraph/workflow.py:2442` and `:3280`. They raise from different
paths with different budgets, and a fix applied to one leaves the other exactly
as it is. The 03:18Z loss was on the landing path; the 2026-08-19 triple-KILL was
on the ladder path.

**3. Removing `RETRY` everywhere satisfies two scenarios and destroys the
feature.** US1-S3 is the control. Watch a `RETRY` press issue an attempt key
before you believe the change.

**4. The unoffered fall-through is a real branch, not dead code.**
`factory/workgraph/workflow.py:3324`
catches `EXPIRED`, which is a legitimate outcome and must keep ending the node.
FR-004 is about a resolution naming a choice that was never offered — separate
those two cases explicitly or you will break expiry.

**5. Do not weaken `_lock_out_dependents`.** US4-S4. It is correct for a killed
node: a dependency that will never merge means the dependent can never build.
The defect is that PAUSE_EPIC routes through `FAILED`, not that the lock-out
exists. `factory/workgraph/models.py:93` shows the shape of the answer that has
already been accepted once for `WAITING_OPERATOR`.

**6. Reproduce the question park before you touch the question branch.** US3-S5
and SC-006. The branch reads correctly; something outside the lines you would
naturally edit is wrong. An implementer who "fixes" the obvious-looking code
without a reproduction will produce a diff that changes behaviour nobody can
show was broken, and the judge will be right to fail it.

**7. A live store's DDL is not the DDL in the tree.** US3-S6. The `question`
termination value is in `factory/usage/ledger.py:76-78` now; a store created
before that line was written still refuses it, the teardown activity fails, and
the symptom is *identical* to the wedge this story is about. Check the installed
store's schema as part of the reproduction, and follow
`factory/verify/store.py:347-348` if a migration is the answer.

**8. Enumerate the bridge's branches from the code.** US2-S2. Hand-listing them
is how one of them came to swallow a press with no trace. `BridgeOutcome`
(`factory/notify/service.py:165`) is the enumeration you already have.

**9. Do not remove the staleness guard to make presses "land".** US2-S4 is the
control. A stale callback re-answering a live node is worse than a dropped press.

**10. The three workflow stories share one file.** US1, US3 and US4 all edit
`factory/workgraph/workflow.py` and are chained with `depends_on_merged` for that
reason. If the file does not look as this plan describes, the story before you
has landed — re-read it rather than assuming the plan is wrong.

**11. Determinism.** All three workflow stories change workflow code. New
non-deterministic reads, new `datetime.now`, new iteration over a set: any of
them breaks replay of epics already in flight. Read
`factory/workgraph/workflow.py:338`'s neighbourhood for the established retry and
timing idioms and stay inside them.

**12. The judge sees the diff and the criteria, nothing else** (Constitution
Principle VIII). Every SC requires committed, pasted output — including SC-005,
which is a real press on a real escalation. If the floor has no live escalation
to press when you get there, say so in the diff and paste the closest thing you
could construct; do not invent a transcript.

**13. One test file per story.**
- US1 → `tests/test_escalation_offers_only_what_it_can_do.py`
- US2 → `tests/test_pressed_button_reaches_the_store.py`
- US3 → `tests/test_answered_question_unparks_the_node.py`
- US4 → `tests/test_pause_is_not_a_kill.py`

## Sizing

**US1 is medium.** The computation is small; the work is threading the node's two
budgets to the two call sites without widening what those methods know, plus the
refusal path for an unoffered resolution.

**US2 is small-to-medium and almost entirely diagnostic.** The remedy may be two
lines. Finding which branch swallowed the press is the story, and it is why
US2-S2 asks for an enumeration rather than a fix to one branch.

**US3 is the least certain story in this spec.** Budget for the reproduction
taking longer than the fix. If the reproduction shows the wedge is the stale
ledger constraint rather than the workflow branch, say so plainly and fix that —
the scenarios are written to accept either answer, and an honest "it was the
store, here is the evidence" is a landing.

**US4 is small** once US3 has landed: one state assignment, one control test, and
a message that names the blast radius.

## Verification the operator will run, independent of the gate

- **Press every button on a real escalation** and watch what each one does. This
  is the only measurement that has ever caught anything in this cluster.
- **Answer a real question on a real parked node** and watch the sibling behind
  it dispatch.
- **Press PAUSE_EPIC on a node with dependents, then resume the epic**, and count
  the nodes that are still there.
- **Check the installed store's `usage_records` DDL** against the tree's. If they
  disagree, that is a finding regardless of what this spec lands.
</content>
