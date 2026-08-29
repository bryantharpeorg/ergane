# Implementation Plan: the ladder charges only the story

**Spec**: `specs/095-the-ladder-charges-only-the-story/spec.md`

Make the pre-agent failure distinguishable, exclude it from the budget with a
bound of its own, and render which bound ended a node.

## What already exists, and where

- **The decision**: `next_action(history, config, *, escalations=())`
  (`factory/verify/ladder.py:177`). Its order is grant → promote → debugger →
  escalate (`:195-217`). The grant line is `if attempts_left and not
  _judge_vetoes_a_retry(history, config, grants)` (`:208`).
- **The accounting, and the precedent for US2**: `_attempts_spent(history,
  config)` (`:231`). Read its docstring in full before writing: it already
  excludes the debugger persona because "it is a rung of its own", and already
  excludes a promoted attempt when a promotion persona is configured, "because it
  belongs to its own rung (US5-S5)". The implementation is a single
  `sum(1 for record in history if record.persona not in excluded)` (`:245`).
  US2 is a third exclusion in a function shaped for exactly this.
- **The veto, read-only to this epic**: `_judge_vetoes_a_retry` (`:293`), whose
  docstring calls itself "a distinction, not a wider number (068 FR-002)".
- **The dials and their bounds**: `factory/verify/factory_yaml.py:127-141` —
  `max_attempts` (1, 10), `max_judge_retries` (0, 10), `debugger_cycles` (0, 3).
  US2's new bound follows this shape, including a bounds refusal.
- **The terminations**: `factory/workgraph/adapter.py:45` maps a non-zero exit to
  `AGENT_ERROR`, a deadline to `TIMEOUT`, cancellation to `KILLED`. The
  `AGENT_ERROR` assignment is at `:1272`. The comments at `:356` and `:392`
  describe a failure "reaching the operator as a diffless `agent_error`", which is
  the presentation US1 replaces for the pre-agent case.
- **`loop_summary`** already names the exact ladder that ran, per attempt. US3
  should render what exists rather than recompute it.

## Traps

**Trap 1 — detect the pre-agent case on the process, not on the message.** The
tell that was measured is a 73-byte stdout containing "Failed to authenticate:
OAuth session expired and could not be refreshed", and it is tempting to grep for
it. Do not: that string belongs to one adapter and one release of it, and a
string match will silently stop matching. The durable fact is structural — the
agent process never produced a token, ran for a length of time no build takes,
and left the worktree untouched. Key on that, and use the message only to
enrich the operator-facing reason.

**Trap 2 — an exclusion without a bound is worse than the defect.** If pre-agent
failures do not count and nothing else counts them, a permanently dead credential
retries forever, spending a worker slot at cap 1 and starving every other spec.
FR-006 is not optional and US2-S4 is its proof. Give the new class its own
bound, in the manifest, following the `_LADDER_BOUNDS` shape.

**Trap 3 — the gates still run, and their failure is still real.** After a
pre-agent failure the worktree has no dependencies, so a typecheck genuinely
fails with a missing binary. Do not suppress the gate results — FR-004 asks for
context on the record, not for hidden evidence. Suppressing them would make the
attempt unreadable in a different direction.

**Trap 4 — `_attempts_spent` is called from two places with different
signatures.** Its `config` parameter is optional (`:232`), so a caller that omits
it gets the debugger exclusion only. Check every call site before changing the
exclusion set; a new exclusion that depends on `config` will silently not apply
wherever `config` is None.

**Trap 5 — US3 renders, it does not recompute.** The ladder already knows which
bound stopped it, and `loop_summary` already carries the rung that ran. A second
derivation in the CLI will disagree with the first the day a bound changes. Have
`next_action` — or a sibling that shares its logic — report the reason, and
render that.

**Trap 6 — the escalation's default must change with its cause.** FR-007 says an
authentication escalation must not default to KILL. The default is part of the
escalation's contract with the operator, so changing it for one cause means the
contract now varies by cause; state that in the escalation text rather than
leaving an operator to notice the button moved.

**Trap 7 — do not touch the veto.** An attempt that "fixes" the shadowing by
widening `_judge_vetoes_a_retry` has changed what the ladder decides, which
FR-010 forbids. Half two of this spec is a reporting story, deliberately.

## Sizing

US1 is a termination value, a detection, and two renderings. US2 is the smallest
change in the epic — one exclusion and one bound — and the largest risk, because
trap 2 turns a fix into a starvation bug. US3 is rendering.

If an attempt is editing `_judge_vetoes_a_retry` or reordering `next_action`, it
has gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the exclusion and the bound. It cannot prove the operator
experience, which is the whole point. After US2 lands, with a deliberately
invalidated subscription session:

```bash
eval "$(scripts/ergane-env.sh)"
# dispatch a one-story spec against a persona routed to the subscription
uv run ergane build start <spec-dir> --target-repo .
# then, within a minute:
uv run ergane build status <epic-id>
```

The demonstration succeeds when the status names authentication, the attempt
count has not moved past the new bound, and the escalation — if one was raised —
names the remedy rather than offering KILL as its default. Paste the status
output and the escalation text into the attestation. Before this spec the same
run shows four attempts, a typecheck failure naming a missing binary, and
nothing about a credential anywhere.
