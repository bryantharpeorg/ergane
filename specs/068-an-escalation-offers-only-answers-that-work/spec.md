---
state: landed
fixes:
  - interpreter/a-null-escalation-child-crashes-the-landing-path-and-kills-the-node
  - operator/build-reset-takes-a-graph-path-where-every-sibling-verb-takes-an-epic-id
# ATTESTED landed 2026-08-20 8:20 PM CT. All three stories observed on
# ergane-buildout: US1 399fa7d (PR #245), US2 0794b1f (PR #252), US3 a76c0ee
# (PR #249).
#
# US2 LANDED BY HAND-RESOLVED MERGE, and the reason is trap 8a below coming
# true. US2 and US3 both edit `factory/cli/nouns/build.py`, both declared
# `depends_on: []`, and the epic was dispatched at `max_concurrent_nodes: 3`.
# The file then conflicted twice in one evening:
#
#   1. WITHIN THIS EPIC, exactly as the trap predicted. US2's PR #246 opened
#      17:50:13Z; US3's PR #249 merged 18:42:00Z; #246 went DIRTY and was closed.
#   2. ACROSS EPICS, which no `depends_on_merged` edge could have prevented --
#      069/US3 (`9537643`) landed 22:20:38Z touching the same file, and US2's
#      re-dispatched PR #252 went DIRTY against it. Edges are within-epic only.
#
# The resolution kept both sides whole: US2's `_NODE_STATES_AT_WORK`,
# `nodes_at_work`, `nodes_awaiting_operator` and `reset_refusal` alongside
# 069/US3's `NoForge`, `_reset_forge` and `_forge_reset_lines`, on 069/US3's
# `_reset_epic(graph, *, forge=None)` signature -- that keyword is the seam its
# tests inject a repository through. The halves compose in the order both
# stories require: refuse first, resolve the forge once for the graph, clean per
# node, then print the still-waiting note. Neither story's logic was weakened.
#
# Verified at three levels rather than asserted: both stories' suites together
# (25 passed), the full declared gate on the merged tree (3934 passed, 48
# skipped, 0 failures), and the merge-group build, which is the one that gates.
#
# The trap was raised before dispatch and not acted on; that gap is now filed as
# `roadmap/a-pre-dispatch-trap-that-names-a-file-collision-does-not-reach-the-dispatch-that-causes-it`.
# US3 carries `depends_on_merged: [US2]` below as of this session -- it is the
# remedy the trap named, recorded so the spec no longer disagrees with what was
# learned, though it arrives after the collision it would have prevented.
#
# --- the flip this supersedes, kept for the chain ---
# FLIPPED draft -> ready 2026-08-20 6:40 AM CT at the operator's instruction,
# after the re-review the hold below demanded. Verified against `357d227`:
#
#   - ANCHORS: 50/50 resolve, each on the symbol it claims. Corrections included
#     three a line-number sweep cannot catch -- `_judge_rewrites_spent` was cited
#     54 lines off (`:127-145` -> `:181-199`); `_settle_answered` DOES NOT EXIST
#     (the function is `_settle_answer`, `:332-371`); and six bare `:NN` refs
#     with no filename, including traps 3 and 4.
#   - COVERAGE: 16/16 scenarios and 10/10 FRs claimed by a task, none phantom,
#     no duplicate ids.
#   - DISPATCH-BLOCKER FIXED: trap 6's prescribed red test DID NOT REPRODUCE.
#     Executed, it returns RETRY, not the ESCALATE it asserts, because
#     `_judge_rewrites_spent` keys on `history[-1]` and the trap put the debugger
#     record LAST, where its null judge_outcome short-circuits the veto. An
#     implementer would have written a red test that was green on commit one and
#     concluded US1 was already fixed. Rewritten with the order as part of the
#     recipe and both measured outcomes pasted in.
#   - SC-002's CONTROL PROVED BY MUTATION: at the defaults it cannot fail (cap
#     present and cap deleted both yield DEBUGGER); at `max_attempts=5` it
#     distinguishes. Trap 1 was right and now carries the measurement.
#   - RAN THE CLI: the US3 verb-family enumeration is accurate -- start/reset/
#     salvage take a graph, external-completion-count takes no positional, the
#     rest take epic_id. FR-010's earlier false claim is fixed.
#   - NEW TRAP 8a: US2 and US3 both edit `factory/cli/nouns/build.py` and both
#     declare `depends_on: []`. Dispatch at --max-concurrent-nodes 1, or give US3
#     `depends_on: [us2]`. THIS IS STILL AN OPEN DECISION, deliberately.
#
# NOT RUN, and not cheaply runnable: US2's FR-007 behaviour needs a live epic
# with a stalled escalation child to exercise.
#
# --- the hold this reverses, kept for the chain ---
# HELD ready -> draft 2026-08-19 5:45 PM CT, BEFORE ANY DISPATCH, by the same
# operator session that wrote this spec ninety minutes earlier. A twelve-agent
# adversarial pre-dispatch review found 68 defects across 067/068/069 rated
# would-cost-an-attempt. Dispatching as written would have burned most of nine
# nodes. This returns to `ready` only after the findings are applied AND a
# re-review comes back clean.
#
# The classes found, so the rework is checkable rather than a matter of taste:
#
#   - LINE ANCHORS SYSTEMATICALLY OFF BY ONE OR TWO. Cited from grep context
#     rather than from opened files. `ladder.py:88` is a comment line and the
#     assignment is at :89; `:122` is `_debugger_cycles_spent`, while
#     `_attempts_spent` is at :111; `:100-106` is a def plus docstring, not the
#     comparison; `workflow.py:1460` is a closing paren and the conversion is at
#     :1460-1463; `escalation/workflow.py:395-399` is the EXPIRY fail-safe
#     branch, not the operator-KILL path the task sends an implementer to.
#   - CENTRAL FACTUAL CLAIMS FALSE. 068 asserts `reset` is the ONLY build verb
#     keyed by a compiled-artifact path. `start` and `salvage` are too, which
#     makes FR-010 unachievable as written and its family test unpassable.
#   - A PRESCRIBED RED TEST THAT DOES NOT REPRODUCE. A reviewer executed 068's
#     trap-6 recipe against the real tree and got a different result than the
#     trap asserts.
#   - A CONTROL TEST STRUCTURALLY UNABLE TO FAIL, proved by mutation.
#   - STORIES DECLARED INDEPENDENT THAT SHARE A FILE, in all three specs.
#
# The lesson, recorded where the next drafter meets it: A SPEC DRAFTED FROM GREP
# OUTPUT RATHER THAN FROM OPENED FILES READS AS AUTHORITATIVE AND IS NOT. Every
# anchor above was produced by reading `grep -n -A` context and miscounting the
# offset, which is invisible to the drafter and fatal to the implementer. The
# review cost fifteen minutes and caught what would have cost a night.
# Drafted 2026-08-19 5:30 PM CT by an operator session, from the same
# build-session report that produced 067. Flipped straight to `ready` at the
# operator's instruction; 063 and 064 were held to draft to let the P0 set
# through.
#
# THE REPORTER'S DIAGNOSIS WAS WRONG, AND THE REAL ONE IS BETTER. They observed
# RETRY -> node KILLED -> an identical escalation one second later, four times,
# and concluded "there was no attempt left to retry with, so RETRY silently
# became kill-and-re-ask." Reading the ladder shows RETRY *does* grant an
# attempt. The grant is real and something else vetoes it. Traced 2026-08-19:
#
#   factory/verify/ladder.py:88   allowed = config.max_attempts + len(escalations)
#
# so after one RETRY, allowed = 3 + 1 = 4 against 3 spent. `attempts_left` is
# True. But the very next line is:
#
#   :91   if attempts_left and not _judge_rewrites_spent(history, config):
#
# and `_judge_rewrites_spent` (:127-145) returns True whenever the LATEST record
# carried `JudgeOutcome.RETRY` and the count of such records exceeds
# `max_judge_retries` (default 2, `factory/verify/models.py:646`). A node that
# exhausted itself on judge rewrites -- which is the ordinary way a node reaches
# an escalation at all -- has exactly that history. So the operator's grant is
# tested, found sufficient, and then discarded by a cap that was never about
# them. The ladder falls through the spent debugger rung and returns ESCALATE,
# and `factory/workgraph/workflow.py:1460-1465` converts that second ESCALATE
# into KILLED.
#
# The function's own docstring anticipates the mirror image of this and not this:
#
#   "an exhausted judge budget must not shorten the node's attempts over a gate
#    failure the judge had no part in"
#
# Correct, and the operator's press is the other case it does not cover.
#
# Verified against the tree before drafting: `EscalationChoice` is a `StrEnum`
# (factory/verify/models.py:124), so the string-vs-enum comparison in
# `_ends_the_node` (:100) is SAFE -- that hypothesis was checked and disproved
# rather than written down as a cause.
#
# Filed as findings before drafting:
#   escalation/retry-on-an-exhausted-ladder-cannot-retry-and-re-escalates-instantly
#   escalation/kill-stops-the-node-and-leaves-the-epic-running-holding-a-fresh-escalation
#   operator/build-reset-takes-a-graph-path-where-every-sibling-verb-takes-an-epic-id
---

# Feature Specification: an escalation offers only answers that work

**Created**: 2026-08-19

## The gap, stated precisely

An escalation is the factory asking a person a question. Three defects make the
answers not work, and they compound into a loop with no exit that does not
involve raw Temporal.

## RETRY is granted and then vetoed

The trace is in the frontmatter. Summarised: an operator presses RETRY, the
ladder correctly widens the budget to `max_attempts + 1`, and then a cap on
**judge-driven** rewrites — a cap about the judge, not about the operator —
suppresses the retry anyway. The node returns ESCALATE a second time, and the
caller turns a second ESCALATE into KILLED.

So the observable behaviour is: press RETRY, get KILLED, and get asked the same
question again about one second later. Four times in the reported session.

**An offered choice that cannot succeed is worse than no choice.** It teaches the
operator — or, increasingly, the operator's *agent* — that the escalation menu
lies, and an operator who stops trusting the menu stops using the resolve path
and reaches for `temporal workflow terminate`. Which is exactly what happened,
four times.

## KILL leaves the epic holding the bag

KILL kills the **node**. The epic stays RUNNING, and because of the defect above
it is usually holding a freshly-opened escalation child by the time the operator
looks. Escaping requires terminating the epic by hand.

## And the verb that would recover it cannot be reached

`ergane build reset` refuses while the epic is active — and a stuck escalation
child is what keeps it active. So the sanctioned recovery verb is unavailable in
precisely the state that needs it.

`reset` is keyed by a **compiled-artifact path** (`factory/cli/nouns/build.py:1158`)
while every verb that signals or queries a *live* epic takes `epic_id` —
`status` (`:1091`), `pause`/`resume`/`kill` (`:1106`), `answer` (`:1124`),
`resolve` (`:1141`), `complete-node-externally` (`:1186`). `start` (`:1078`) and
`salvage` (`:1173`) also take a graph, both by design. So
`ergane build reset 001-trip-expenses` fails with `cannot read
001-trip-expenses`, and the operator must keep the derive artifact for the life
of the epic or re-derive one purely to reset.

Three defects, one closed loop: the button does nothing, the fallback strands the
epic, and the recovery verb is both refused and mis-keyed.

## User Scenarios & Testing

### User Story 1 - RETRY produces an attempt (Priority: P1)

As an operator, pressing RETRY on an exhausted node causes the node to try again.

**Why this priority**: P1. It is the button the escalation exists to offer, and
it currently does the opposite of what it says.

**Independent Test**: build a node history that exhausts both attempts and judge
rewrites, apply a RETRY resolution, and assert the decided action is a retry.

**Acceptance Scenarios**:

1. **Given** a node whose attempts are spent and whose latest record carried a
   judge RETRY outcome beyond `max_judge_retries`, **When** an operator's RETRY
   resolution is applied, **Then** the decided action is a retry — proven by a
   committed test asserting the returned action. This is the exact history that
   produces the defect; a test built from a history without an exhausted judge
   budget passes today and proves nothing.
2. **Given** the same node, **When** the retry runs, **Then** it is an attempt
   that actually dispatches — proven by a committed test asserting the node
   leaves the escalated state, not merely that a function returned a value.
3. **Given** a node that reaches ESCALATE a second time for a reason that is
   **not** an operator grant, **When** the action is decided, **Then** it still
   becomes KILLED as today — proven by a committed test. The caller's
   second-ESCALATE-means-KILLED rule at `factory/workgraph/workflow.py:1460` is
   correct for the case it was written for and must survive.
4. **Given** the same exhausted history, **When** the action is decided once with
   `escalations=[EscalationChoice.RETRY]` and once with `escalations=()` **under a
   config that raises `max_attempts` above the attempts spent**, **Then** the
   first returns a retry and the second does not — proven by a single committed
   test asserting both results side by side, with both decided actions pasted
   into the diff. Under the shipped defaults the attempt budget expires together
   with the cap (`factory/verify/ladder.py:17-22`), so a control at defaults
   cannot fail and proves nothing.
5. **Given** repeated RETRY presses, **When** each is applied, **Then** each buys
   exactly one attempt and no more — proven by a committed test asserting the
   budget after two grants. An operator must be able to keep granting; they must
   not be able to grant an unbounded number by accident.
6. **Given** the diff, **When** the escalation options are inspected, **Then**
   every option offered can change the node's state — proven by a committed test
   enumerating the offered options against the actions each produces. This is the
   story's real claim: the menu must not contain a no-op.

---

### User Story 2 - KILL leaves the epic in a state the CLI can recover (Priority: P1)

As an operator, killing a node from an escalation leaves the epic in a state
`ergane build reset` can act on, without raw Temporal surgery.

**Why this priority**: P1. It is the second half of the closed loop — with RETRY
fixed but this unfixed, an operator who chooses to give up still cannot.

**Independent Test**: kill a node from an escalation and assert `reset` succeeds
against the resulting epic.

**Acceptance Scenarios**:

1. **Given** a node killed by an escalation resolution, **When** the epic is
   inspected, **Then** it holds no living escalation child — proven by a
   committed test.
2. **Given** the same epic, **When** `ergane build reset` runs against it,
   **Then** it succeeds — proven by a committed test asserting the exit status
   and the reset effect, not merely that no exception was raised.
3. **Given** an epic whose only living child is a stalled escalation, **When**
   `reset` runs, **Then** it succeeds rather than refusing for activity — proven
   by a committed test. This is the deadlock's own shape and is the scenario the
   story exists for.
4. **Given** an epic with a genuinely running node, **When** `reset` runs,
   **Then** it still refuses, naming what is running — proven by a committed
   test. The refusal is correct in general; only the escalation case is wrong.
5. **Given** the operator's choices, **When** the offered options are read,
   **Then** ending the node and ending the epic are distinguishable — proven by
   a committed test. An operator who wants the epic gone should not have to kill
   nodes one at a time and then reach for Temporal.

---

### User Story 3 - Every build verb is keyed by the epic id (Priority: P2)

As an operator, `ergane build reset <epic-id>` works, like every other build verb.

**Why this priority**: P2. Five interventions in the reported session, and the
workaround exists once known — but it is also what makes US2's fix reachable in
practice rather than in principle.

**Independent Test**: run `reset` with an epic id and assert it resolves the
graph itself.

**Acceptance Scenarios**:

1. **Given** an epic id, **When** `ergane build reset` runs, **Then** it resolves
   that epic's compiled graph from `<specs_root>/<epic_id>/workgraph.json`
   **without requiring Temporal history** and resets it — proven by a committed
   test asserting the reset reached the right nodes with the epic's workflow
   absent from Temporal. The workflow record carries no input (`describe()`
   exposes memo and static details only, and `build.py:500-511` sets no memo) and
   `fetch_history()` is gone past retention, which is the state reset exists for.
2. **Given** an epic id naming no known epic, **When** `reset` runs, **Then** it
   fails naming the epic id and where it looked — proven by a committed test.
3. **Given** the diff, **When** the first positional argument of every `build`
   subcommand **that acts on an already-started epic** — `status`, `pause`,
   `resume`, `kill`, `answer`, `resolve`, `reset`, `complete-node-externally` —
   is inspected, **Then** each is `epic_id` — proven by a committed test that
   enumerates the subparsers, names `start`, `salvage` and
   `external-completion-count` as declared exclusions **with the reason stated in
   the test**, and fails if a new subcommand appears outside both lists.
4. **Given** an operator who supplies a graph path, **When** `reset` runs,
   **Then** it is still accepted — proven by a committed test.
   `tests/test_ergane_build.py:1284, 1297, 1342, 1363, 1378, 1422` all pass one,
   and a silent change of meaning for an argument that used to work is its own
   defect.
5. **Given** an epic id whose workflow is gone from Temporal, **When** `reset`
   runs, **Then** it still archives the survivors — proven by a committed test.
   `factory/cli/nouns/build.py:882-891` proceeds on `NOT_FOUND` today and
   `tests/test_ergane_build.py:1363` pins it; that behaviour must survive the
   argument change.

---

### Edge Cases

- **A grant applied to a node that was already killed.** The resolution arrives
  after the node ended. It must not resurrect it; US1-S3's preserved
  second-ESCALATE rule and the existing `_ends_the_node` check both bear on this.
- **An escalation that expires rather than being answered.** `EXPIRED` is written
  by the timeout path and by no button (`factory/verify/ladder.py:100-106`).
  Expiry must remain terminal — silence is a decision the operator is entitled
  to make, and this spec does not change that contract.
- **PAUSE_EPIC.** It ends the node like every non-grant and additionally parks the
  epic (`factory/workgraph/workflow.py:1449-1455`). US2-S5's distinction between
  ending a node and ending an epic must not collapse PAUSE_EPIC into either.
- **Two escalations open at once on sibling nodes.** Each carries its own
  correlation id; a grant must reach only its own node.

## Requirements

### Functional Requirements

- **FR-001**: An operator's RETRY resolution MUST produce an attempt that
  dispatches, on a node whose ordinary attempts and judge rewrites are both
  spent.
- **FR-002**: The judge-rewrite cap MUST NOT suppress an attempt granted by an
  operator, while continuing to bound judge-driven retries.
- **FR-003**: Each grant MUST buy exactly one attempt.
- **FR-004**: A second ESCALATE arising from anything other than an operator
  grant MUST remain terminal, as today.
- **FR-005**: Every option an escalation offers MUST be able to change the node's
  state.
- **FR-006**: A node killed by an escalation resolution MUST leave the epic with
  no living escalation child.
- **FR-007**: `ergane build reset` MUST succeed against an epic whose only living
  child is a stalled escalation, and MUST continue to refuse an epic with a
  running node.
- **FR-008**: Ending the node and ending the epic MUST be distinguishable
  operator choices.
- **FR-009**: `ergane build reset` MUST accept an epic id and resolve the graph
  itself.
- **FR-010**: Every `build` subcommand that acts on an already-started epic MUST
  take `epic_id` as its first positional argument. `start` and `salvage` are
  declared exceptions — both are keyed by a compiled artifact by design (`start`
  creates the epic; `salvage` deliberately needs no Temporal,
  `factory/cli/nouns/build.py:918-935`) — and `external-completion-count` takes
  no positional at all.

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
  depends_on_merged: [US2]
  implements: [FR-009, FR-010]
  persona: opus-closer
```

## Success Criteria

### Measurable Outcomes

- **SC-001**: Construct the exact history from the frontmatter's trace — attempts
  spent, judge rewrites beyond the cap — apply RETRY, and paste the decided
  action before and after the fix.
- **SC-002**: Confirm the judge-rewrite cap still bounds judge-driven retries
  with no grant present, and paste that run. Without this control, SC-001 could
  be satisfied by deleting the cap.
- **SC-003**: Kill a node from an escalation, then run `ergane build reset`
  against the epic and paste the output.
- **SC-004**: Run `ergane build reset <epic-id>` and paste the output.
- **SC-005**: Enumerate every `build` subcommand's first positional argument and
  paste the list.

## Assumptions

- The escalation transport is sound and is not in scope. The reporter praised it
  explicitly — marker detection, Telegram page, resolve by correlation id — and
  every defect here is in the policy behind the buttons.
- Never pressing an escalation button on the operator's behalf remains binding.
  Making RETRY grant an attempt changes what the button does, not who presses it.
- `max_attempts: 3`, `max_judge_retries: 2`, `debugger_cycles: 1` are today's
  defaults (`factory/verify/models.py:645-647`). Nothing here proposes changing
  them; 069 addresses what the ladder is charged for.
