# Implementation Plan: an escalation offers only answers that work

**Spec**: `specs/068-an-escalation-offers-only-answers-that-work/spec.md`

## What already exists, and where

Every line below was **re-verified against `357d227` on 2026-08-20**, after 070
and 071 landed. The original set was read on 2026-08-19 and was correct then;
070/US5 and 071 moved most of the `ladder.py`, `models.py` and `adapter.py`
anchors in the hours after, and `_judge_rewrites_spent` moved 54 lines. Check
each again before you rely on it.

**US1 — the ladder and its caller:**

- `factory/verify/ladder.py:68-105` — `next_action`. The three lines that matter:
  - `:86` — `if any(_ends_the_node(resolution) for resolution in escalations)`
  - `:94` — `allowed = config.max_attempts + len(escalations)` — **the grant is
    real and already implemented.**
  - `:96` — `if attempts_left and not _judge_rewrites_spent(history, config)` —
    **this is the veto. This line is the defect.**
- `factory/verify/ladder.py:181-199` — `_judge_rewrites_spent`. Returns True when
  `history[-1].judge_outcome == JudgeOutcome.RETRY` and the count of such records
  exceeds `config.max_judge_retries`. **Read its docstring**: it already reasons
  about not letting the judge budget shorten the node's attempts over a gate
  failure. The operator's grant is the same argument, one case further.
- `factory/verify/ladder.py:108-116` — `_ends_the_node`. `resolution !=
  EscalationChoice.RETRY`. Safe: `EscalationChoice` is a `StrEnum`
  (`factory/verify/models.py:125-134`), verified. Do not "fix" this.
- `factory/verify/models.py:653-655` — `max_attempts: int = 3`,
  `max_judge_retries: int = 2`, `debugger_cycles: int = 1`.
- `factory/verify/ladder.py:119-133` — `_attempts_spent`, which `next_action`
  reaches through `attempts_left` at `:95`. **It changed shape under 070/US5**:
  it now takes `config: VerificationConfig | None = None` and excludes
  `{DEBUGGER_PERSONA, config.promotion_persona}` rather than the debugger alone.
  Calling it without the config silently reverts that exclusion — measured, it
  returns 1 where the config-passing call returns 0. If your change touches this
  call path, pass the config.
- `factory/workgraph/workflow.py:1436-1465` — the caller. `next_action` is
  invoked at `:1436`, the escalation is raised at `:1448`, its resolution
  appended at `:1449`, `next_action` recomputed at `:1457`, and `:1460-1465`
  turns a second ESCALATE into KILLED. **That conversion is where the KILL the
  reporter saw comes from.**
- `factory/workgraph/workflow.py:1450-1456` — the PAUSE_EPIC branch, which sets
  `parked` and `self._paused`.
- `factory/workgraph/workflow.py:1467-1471` — the refusal of buffered external
  completions on a non-exhausted node.
- `factory/notify/messages.py:99-101` — the three offered options and their
  button labels.

**US2 — kill and reset:**

- `factory/escalation/workflow.py:245-263` — the `escalation_resolved` signal,
  and **`_settle_answer`** at `:332-371` — **the operator-press path**. (The name
  is singular: there is no `_settle_answered` in the tree, and this plan cited
  one until 2026-08-20.)
  **`:373-430` is `_settle_unanswered`, the expiry fail-safe; this spec's own
  Edge Cases forbid changing it.**
- `factory/workgraph/workflow.py:561-573` — `kill_epic`, which only sets a flag;
  `:2023` and `:2673` await escalation children without observing it. That is why
  a stalled escalation strands the epic.
- `factory/cli/nouns/build.py:879-915` — `_reset_epic`. It describes the epic and
  refuses on `described.status.name == "RUNNING"`. **That refusal is the one that
  must learn about a stalled escalation child.**
- `factory/cli/nouns/build.py:652-662` — `kill_command`'s confirmation, and note
  it already has `--yes` (`:1108-1112`). The reporter believed it did not; they
  were wrong, and nothing here should "add" it.

**US3 — the verb family:**

- `factory/cli/nouns/build.py:1067-1219` — every subparser registration, cited at
  the *argument* line: `start :1078 graph`, `status :1091 epic_id`,
  `pause/resume/kill :1106 epic_id`, `answer :1124 epic_id`,
  `resolve :1141 epic_id`, `reset :1158 graph`, `salvage :1173 graph`,
  `complete-node-externally :1186 epic_id`, `external-completion-count :1201-1219`
  (**no positional at all**). The family is **not** uniform: three verbs take a
  graph and one takes nothing. `salvage` keeps its graph path deliberately
  (`build.py:918-935`).

## Traps

**1. Do not fix this by deleting or raising the judge-rewrite cap.** SC-002 is
the control that catches it. The cap is correct for what it was written for —
bounding a judge that keeps asking for rewrites. What is wrong is that it applies
to an attempt the judge did not ask for. The fix is a distinction between
judge-driven retries and operator-granted ones, not a wider number. Read `factory/verify/ladder.py:17-22` before writing the control:
at the defaults the two caps expire together, so a control at defaults passes
with the cap deleted. **Raise `max_attempts` in the control's config.**

**This was proved by mutation against `357d227`, not reasoned about.** Three
implementer records each carrying `JudgeOutcome.RETRY`, no escalations, with
`_judge_rewrites_spent` stubbed to `False` to simulate the cap being deleted:

```
defaults        cap present -> DEBUGGER;  cap DELETED -> DEBUGGER   (identical: control CANNOT fail)
max_attempts=5  cap present -> DEBUGGER;  cap DELETED -> RETRY      (distinguishes)
```

At the defaults `allowed = max_attempts + 0 = 3` and `_attempts_spent` is already
3, so `attempts_left` is `False` and the ladder leaves the retry path before the
judge cap is ever consulted — **the control passes for a reason that has nothing
to do with the thing it claims to guard.** A reviewer who sees SC-002 green at
defaults has been told nothing.

**2. Do not remove the second-ESCALATE-means-KILLED rule.** US1-S3 and FR-004.
`factory/workgraph/workflow.py:1460-1465` exists so a node that escalates, gets
answered, and immediately re-escalates does not page forever. It is correct.
Once RETRY genuinely produces a retry, that path stops being reached by a grant —
which is the fix. Deleting the rule instead produces an infinite escalation loop,
which is a worse outage than the one being fixed.

**3. The reporter's stated cause is wrong; do not implement it.** They wrote
"RETRY must *grant* an attempt (reset or extend the counter)". It already does,
at `:94`. Implementing their remedy adds a second grant on top of the existing
one, so one press buys two attempts and FR-003 fails. Read `:94` before you
write anything.

**4. `EscalationChoice` is a `StrEnum` and the comparison at `:116` is safe.**
This was checked and disproved as a cause before drafting. If you find yourself
"fixing" a string-versus-enum comparison there, you are on the wrong trail and
have spent the attempt.

**5. Determinism.** `next_action` is called from workflow code
(`factory/workgraph/workflow.py:1436`). No clocks, no environment, no filesystem.
It is already a pure function of `(history, config, escalations)` and must stay
one — that purity is what makes US1 testable without a workflow environment at
all, which is the cheap path to a red test.

**6. US1's red test is nearly free — but only ONE history reproduces it, and
ORDER IS PART OF THE RECIPE.** `next_action` is pure and needs no Temporal. The
reproducing history is:

1. one record with `persona=DEBUGGER_PERSONA` **FIRST**, so the debugger rung at
   `ladder.py:102-103` is already spent — without it the ladder returns
   `DEBUGGER`, not `ESCALATE`;
2. then **three non-debugger records that EACH carry `JudgeOutcome.RETRY`** — the
   count must *exceed* `max_judge_retries=2`.

With `VerificationConfig()` and `escalations=[EscalationChoice.RETRY]` that
returns `ESCALATE` today and must return a retry after the fix.

**Putting the debugger record LAST — as this trap instructed until 2026-08-20 —
does not reproduce.** Measured against `357d227`: `_judge_rewrites_spent`
(`ladder.py:181-199`) keys on `latest = history[-1]` at `:192`, so a trailing
debugger record whose `judge_outcome` is `None` short-circuits it to `False`, the
veto at `:96` never fires, and `next_action` returns **`RETRY`** — your red test
is green from the first commit and US1 looks already fixed. Both orderings were
executed:

```
debugger LAST  -> _judge_rewrites_spent False, _attempts_spent 3 -> RETRY     (wrong)
debugger FIRST -> _judge_rewrites_spent True,  _attempts_spent 3 -> ESCALATE  (right)
```

Omit either requirement, or reverse the order, and the reproduction silently
disappears.

**7. US2's refusal must stay a refusal for the running case.** US2-S4. A reset
that succeeds against a genuinely running epic will interrupt live work. Widening
`_reset_epic`'s check must be keyed on *what kind of child is alive*, not on
loosening the status test.

**8. US3 must define what happens to the old argument form.** US3-S4. An operator
with a script passing a graph path is a real case; either keep accepting it or
refuse it naming the new form. Silently reinterpreting a path as an epic id is
the one unacceptable outcome.

**8a. US2 and US3 both edit `factory/cli/nouns/build.py`, and both declare
`depends_on: []`.** US2 widens `_reset_epic` (`:879-915`); US3 rewrites the
subparser registrations (`:1067-1219`). Different regions of one file, no edge
between them, so at `--max-concurrent-nodes` above 1 they build in separate
worktrees against the same base and land in whichever order the queue picks.

That is not a conflict the merge queue reliably catches: `depends_on` models what
a story needs to **exist**, not what it will **touch**. The usual presentation is
the second node's tests dying after a clean rebase, which reads as a flaky
failure rather than as contention. Two options, and picking one is part of this
story's scope:

- dispatch this epic at `--max-concurrent-nodes 1`, or
- give US3 `depends_on: [us2]` so the file is only ever edited by one live node.

Say which in the diff. Do not leave it implicit and hope the ordering is kind.

**9. One test file per story, named here.**
- US1 → `tests/test_escalation_grant_survives_the_judge_cap.py`
- US2 → `tests/test_killed_node_leaves_a_resettable_epic.py`
- US3 → `tests/test_build_verbs_take_an_epic_id.py`
If you need a file assigned to another story, the edge declaration is wrong — say
so rather than editing across the line.

**10. The judge sees the diff and the criteria, nothing else.** Paste the decided
actions, the reset output and the subcommand enumeration into the diff.

**11. Do not plan to read the graph off the running workflow.** `describe()`
exposes memo and static details only — **no input** — and `ergane build start`
sets no memo (`build.py:500-511`), so every epic that exists today is unreachable
that way. `fetch_history()` is gone past retention, which is precisely the state
reset exists for. Resolve `<specs_root>/<epic_id>/workgraph.json` and say what
happens when it is absent. `_reset_epic` needs `graph.nodes` and
`graph.target_repo`, not only the id. Keep the positional graph path accepted:
`tests/test_ergane_build.py:1284, 1297, 1342, 1363, 1378, 1422` all pass one.

## Sizing

US1 is the important one and it is small: one condition in a pure function, plus
whatever carries "this attempt was granted" into it. The difficulty is entirely
trap 1 — expressing a distinction rather than widening a number.

US2 is a widened precondition on `_reset_epic` plus making KILL clean up its own
escalation child. Medium.

US3 is an argument change and a family test. Small.

## Verification the operator will run, independent of the gate

- **Prove US1 by control, both directions.** Same history, with and without a
  grant. With a grant it must retry; without one the cap must still bite. One
  without the other is not evidence.
- **Prove US2 by reproducing the deadlock.** Kill a node from an escalation, then
  run `ergane build reset` without touching Temporal. If that command needs a
  `temporal workflow terminate` first, the story did not land.
- **Prove US3 by running the verb.** `ergane build reset <epic-id>`.
