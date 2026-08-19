# Implementation Plan: the world moving is not the code being wrong

**Spec**: `specs/069-the-world-moving-is-not-the-code-being-wrong/spec.md`

## What already exists, and where

Every line below was read on 2026-08-19. Check each against the tree before you
rely on it.

**US1 — the rejection path and the ladder:**

- `factory/workgraph/workflow.py:2163` and `:2629` — `if enqueued.rejected:`, the
  two places a rejection is acted on.
- `factory/workgraph/workflow.py:2254` — "rejected but not finished — US2's
  bounded recovery cycle owns …". The bounded recovery already exists; this story
  changes what it is charged.
- `factory/workgraph/workflow.py:2539-2565` — **read this before anything else.**
  It already reasons about a recovery being futile when the tree would be
  identical to the one the queue rejected, and it already carries
  `rejected_tip=landing.enqueued_tip`. So the code already holds the facts needed
  to tell "the base moved" from "the code is unchanged". FR-005's classification
  is closer to hand than it looks.
- `factory/workgraph/workflow.py:286` — "return a rejected landing to ENQUEUED."
- `factory/workgraph/workflow.py:462` — the queue history an operator reads.
- `factory/verify/ladder.py:122-130` — `_attempts_spent`, counting every
  non-debugger record.
- `factory/verify/ladder.py:127-145` — `_debugger_cycles_spent`.
- `factory/verify/models.py:645-647` — `max_attempts: 3`, `max_judge_retries: 2`,
  `debugger_cycles: 1`.

**US2 — derivation and slices:**

- The slice-coverage machinery already parses per-story file paths from
  `tasks.md`; `ergane spec validate` reports on it (its `[slice_coverage]`
  advisory names task ids per story). Find where that parse lives and reuse it —
  do not write a second task parser.
- `depends_on_merged` is the existing contention edge type. US2 infers edges of
  that kind; it does not invent a third.

**US3 — reset and the forge:**

- `factory/cli/nouns/build.py:878-900` — `_reset_epic`. Local only; nothing in it
  reaches the forge.
- `factory/mergequeue/gh.py` — the forge client. **Note before you use it:
  `create_pr` at `:172` calls `_run_json("pr","create", …)` without `--json`, so
  `json.loads` raises on every first attempt.** That is a known open finding and
  is NOT in this spec's scope; do not fix it here, and do not build on the
  assumption that this module is clean.

## Traps

**1. Charge nothing less is not the goal; charge the right thing is.** US1-S3 and
SC-002 are the control. A diff that stops charging rejections in general passes
the headline scenario and removes the budget's meaning. Every free path needs its
paired control test in the same file.

**2. Classify by cause, not by message text.** FR-005. A string match on the
forge's rejection wording is a guess that breaks the first time GitHub rewords
something, and it will look like it works. The facts are already available
structurally at `:2539-2565` — `rejected_tip` versus the current base.

**3. The free path needs its own bound.** US1-S5, FR-004. This is the same trap
as 067's US2 and it is the one a reviewer will look for. Moving work off a
budget without bounding it converts a bounded expensive failure into an unbounded
free one.

**4. Do not remove the identical-tree refusal.** `factory/workgraph/workflow.py:2539-2565`
exists because requeueing a tree the queue already rejected is futile. FR-006. It
is adjacent to the code you are changing and easy to break in passing.

**5. Determinism.** This is workflow code. No clocks, no environment, no
filesystem. 039 landed because a workflow read `os.environ` and silently disabled
a whole schedule.

**6. US2 must not serialise everything.** US2-S2. An inference that fires too
readily removes the concurrency the factory exists to provide, and it will be
switched off — the same failure shape as 065's trap 7 about a probe that cannot
tell idle from wedged. The test over disjoint stories is not optional.

**7. Reuse the slice parser.** US2 needs per-story file paths and the
slice-coverage machinery already produces them. A second parser that disagrees
with `spec validate` is worse than no inference.

**8. US3 must not reach outside `factory/<epic>/<node>`.** US3-S4. A cleanup verb
that closes a pull request an operator opened by hand is a far worse defect than
the one being fixed. Scope every forge call by that namespace and test the
negative.

**9. US3 must degrade rather than fail.** US3-S5. If the forge is unreachable the
local reset still completes and says what it could not do. A cleanup verb that
aborts on a network error strands the operator in the state it exists to clear.

**10. `create_pr` is already broken and is not yours.** See above. If your
attempt starts failing inside `factory/mergequeue/gh.py:172`, that is the known
open finding, not something you introduced and not something to fix here.

**11. One test file per story, named here.**
- US1 → `tests/test_moved_base_is_not_charged.py`
- US2 → `tests/test_colliding_slices_are_ordered.py`
- US3 → `tests/test_reset_clears_the_forge.py`
If you need a file assigned to another story, the edge declaration is wrong — say
so rather than editing across the line.

**12. The judge sees the diff and the criteria, nothing else.** SC-001 through
SC-005 all require committed output.

## Sizing

US1 is the story that matters and it is medium: a classification, a path that
skips the charge, and a bound. Most of its risk is trap 1 and trap 2.

US2 is the largest and least certain. It touches derivation, which every spec in
the repository depends on. If it proves bigger than one attempt, US1 alone
delivers the outcome — US2 makes collisions rarer, US1 makes them survivable.

US3 is a handful of forge calls behind a namespace guard, plus the degraded path.
Medium, and entirely about the negative tests.

## Verification the operator will run, independent of the gate

- **Prove US1 by control, both directions.** A moved-base rejection must move
  neither counter; a code-fault rejection must move one. Paste both.
- **Prove US1 by reproducing the reported failure.** Land a three-way fan-out
  sharing one file at the shipped `debugger_cycles: 1`. That is the run that
  exhausted a defect-free node, and surviving it is the only proof that counts.
- **Prove US2 in both directions.** An inferred edge on overlapping slices, and
  no edge on disjoint ones.
- **Prove US3 by rebuilding.** Reset an epic with an open PR and a remote branch,
  then push a rebuilt node. If that push needs a hand-deleted branch, the story
  did not land.
