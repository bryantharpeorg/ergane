# Implementation Plan: an escalation offers only answers that work

**Spec**: `specs/068-an-escalation-offers-only-answers-that-work/spec.md`

## What already exists, and where

Every line below was read on 2026-08-19. Check each against the tree before you
rely on it.

**US1 — the ladder and its caller:**

- `factory/verify/ladder.py:63-97` — `next_action`. The three lines that matter:
  - `:82` — `if any(_ends_the_node(r) for r in escalations): return KILLED`
  - `:88` — `allowed = config.max_attempts + len(escalations)` — **the grant is
    real and already implemented.**
  - `:91` — `if attempts_left and not _judge_rewrites_spent(history, config)` —
    **this is the veto. This line is the defect.**
- `factory/verify/ladder.py:127-145` — `_judge_rewrites_spent`. Returns True when
  `history[-1].judge_outcome == JudgeOutcome.RETRY` and the count of such records
  exceeds `config.max_judge_retries`. **Read its docstring**: it already reasons
  about not letting the judge budget shorten the node's attempts over a gate
  failure. The operator's grant is the same argument, one case further.
- `factory/verify/ladder.py:100-106` — `_ends_the_node`. `resolution !=
  EscalationChoice.RETRY`. Safe: `EscalationChoice` is a `StrEnum`
  (`factory/verify/models.py:124`), verified. Do not "fix" this.
- `factory/verify/models.py:645-647` — `max_attempts: int = 3`,
  `max_judge_retries: int = 2`, `debugger_cycles: int = 1`.
- `factory/workgraph/workflow.py:1436-1463` — the caller. `next_action` is
  invoked at `:1436`, the escalation is raised at `:1448`, its resolution
  appended at `:1449`, `next_action` recomputed at `:1457`, and `:1459-1463`
  turns a second ESCALATE into KILLED. **That conversion is where the KILL the
  reporter saw comes from.**
- `factory/workgraph/workflow.py:1449-1455` — the PAUSE_EPIC branch, which sets
  `parked` and `self._paused`.
- `factory/workgraph/workflow.py:1466-1470` — the refusal of buffered external
  completions on a non-exhausted node.
- `factory/notify/messages.py:99-101` — the three offered options and their
  button labels.

**US2 — kill and reset:**

- `factory/escalation/workflow.py:245-263` — the `escalation_resolved` signal,
  and `_settle_answered` at `:341-371` — **the operator-press path**.
  **`:373-402` is `_settle_unanswered`, the expiry fail-safe; this spec's own
  Edge Cases forbid changing it.**
- `factory/workgraph/workflow.py:561-573` — `kill_epic`, which only sets a flag;
  `:2023` and `:2673` await escalation children without observing it. That is why
  a stalled escalation strands the epic.
- `factory/cli/nouns/build.py:878-900` — `_reset_epic`. It describes the epic and
  refuses on `described.status.name == "RUNNING"`. **That refusal is the one that
  must learn about a stalled escalation child.**
- `factory/cli/nouns/build.py:653-659` — `kill_command`'s confirmation, and note
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

**2. Do not remove the second-ESCALATE-means-KILLED rule.** US1-S3 and FR-004.
`factory/workgraph/workflow.py:1459-1463` exists so a node that escalates, gets
answered, and immediately re-escalates does not page forever. It is correct.
Once RETRY genuinely produces a retry, that path stops being reached by a grant —
which is the fix. Deleting the rule instead produces an infinite escalation loop,
which is a worse outage than the one being fixed.

**3. The reporter's stated cause is wrong; do not implement it.** They wrote
"RETRY must *grant* an attempt (reset or extend the counter)". It already does,
at `:88`. Implementing their remedy adds a second grant on top of the existing
one, so one press buys two attempts and FR-003 fails. Read `:88` before you
write anything.

**4. `EscalationChoice` is a `StrEnum` and the comparison at `:100` is safe.**
This was checked and disproved as a cause before drafting. If you find yourself
"fixing" a string-versus-enum comparison there, you are on the wrong trail and
have spent the attempt.

**5. Determinism.** `next_action` is called from workflow code
(`factory/workgraph/workflow.py:1436`). No clocks, no environment, no filesystem.
It is already a pure function of `(history, config, escalations)` and must stay
one — that purity is what makes US1 testable without a workflow environment at
all, which is the cheap path to a red test.

**6. US1's red test is nearly free — but only ONE history reproduces it.**
`next_action` is pure. The reproducing history is **three non-debugger
`AttemptRecord`s that EACH carry `JudgeOutcome.RETRY`** — the count must *exceed*
`max_judge_retries=2`, so a history where only the latest carries it returns
`RETRY` today and your test is green from the first commit — **plus one further
record with `persona=DEBUGGER_PERSONA`** so the debugger rung at `ladder.py:94`
is already spent; without it the ladder returns `DEBUGGER`, not `ESCALATE`. With
`VerificationConfig()` and `escalations=[EscalationChoice.RETRY]` that history
returns `ESCALATE` today and must return a retry after the fix. Omit either
requirement and the reproduction silently disappears. Measured against the tree,
not reasoned about. It needs no Temporal.

**7. US2's refusal must stay a refusal for the running case.** US2-S4. A reset
that succeeds against a genuinely running epic will interrupt live work. Widening
`_reset_epic`'s check must be keyed on *what kind of child is alive*, not on
loosening the status test.

**8. US3 must define what happens to the old argument form.** US3-S4. An operator
with a script passing a graph path is a real case; either keep accepting it or
refuse it naming the new form. Silently reinterpreting a path as an epic id is
the one unacceptable outcome.

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
