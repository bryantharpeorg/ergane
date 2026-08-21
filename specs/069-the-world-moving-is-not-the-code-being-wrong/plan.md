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
- `factory/verify/ladder.py:119-133` — `_attempts_spent`. **Not "every
  non-debugger record" — that description was true when this plan was written and
  070/US5 falsified it.** It now takes `config: VerificationConfig | None = None`
  and excludes `{DEBUGGER_PERSONA, config.promotion_persona}`, the set built at
  `:132`. Measured: with the config a promoted record scores 0, without it 1. Any
  assertion this story makes about ladder counts must pass the config, or it will
  silently measure the pre-US5 behaviour and pass for the wrong reason.
- `factory/verify/ladder.py:136-138` — `_debugger_cycles_spent`. (`:181-199` is
  `_judge_rewrites_spent`, a different cap — not this story's.)
- `factory/verify/models.py:653-655` — `max_attempts: 3`, `max_judge_retries: 2`,
  `debugger_cycles: 1`.

**US1 — THERE ARE TWO BUDGETS HERE AND A FIX THAT NAMES ONLY ONE IS WRONG.**
This was got wrong once already during refinement, in both directions, so it is
spelled out. Verify each of these lines yourself before you rely on it.

- `factory/workgraph/workflow.py:2317` —
  `if not granted and landing.recovery_cycles >= config.max_recovery_cycles:`.
  **This is what BOUNDS the recovery loop.** The ladder is not consulted to
  decide whether a recovery happens at all; this counter is.
- `factory/mergequeue/models.py:134` — `recovery_cycles: int = 0` on the landing.
- `factory/mergequeue/models.py:292` — `max_recovery_cycles: int = 1`. **The
  shipped default is ONE**, it is constructed bare at every call site, and unlike
  the four `_LADDER_KEYS` dials it has no operator-facing config surface at all.
  That is a separate open finding; do not fix it here, but do not write a test
  that silently depends on it either.
- `factory/workgraph/workflow.py:2325` — `recovery_cycles=landing.recovery_cycles + 1`,
  the increment.
- `factory/workgraph/workflow.py:2502-2508` — **and this is the half that is easy
  to miss.** `_recovery_attempt` ends by appending an `AttemptRecord` to
  `record.history` with `persona=persona`. `persona` is `resolved.node.persona`
  on a clean sync and `DEBUGGER_PERSONA` on a conflicted one (set just above, at
  `:2374-2379`). So a recovery **also spends a LADDER slot**: an ordinary attempt
  after a clean sync, a debugger cycle after a conflicted one.

Put together: a moved-base rejection today costs the node **one recovery cycle
out of one, AND one ordinary attempt out of three**. US1 must make it cost
neither, and the tests must assert both. Asserting only `recovery_cycles` leaves
the node still being charged for the world moving; asserting only the ladder
counts leaves it dying at the recovery bound with attempts to spare.

**US2 — derivation and slices:**

**CORRECTED 2026-08-19 after checking the tree. An earlier draft of this plan
said "the slice-coverage machinery already parses per-story file paths from
`tasks.md` … reuse it". IT DOES NOT, AND THERE IS NO SUCH PARSER ANYWHERE.**
Sending an implementer to find and reuse a function that does not exist costs an
attempt in search alone. What actually exists:

- `factory/workgraph/prompt.py:558` — `def task_slice_bounds(node, tasks_text)`,
  returning half-open line indices into `tasks_text.splitlines()`. **This is the
  real reusable piece**, and its docstring says why: it is the assembler's own
  scan, so the lines it calls a story's slice are exactly the lines dispatch
  cuts. Anything that decides "which lines belong to which story" must go through
  this and not re-derive it.
- `factory/workgraph/preflight.py:400` — `def slice_coverage_findings(graph, *, tasks_text)`.
  What `ergane spec validate`'s `[slice_coverage]` advisory comes from. It maps
  **task id → story → slice**. Its regexes are
  `_TASK_LINE_RE` (`:298`, task ids), `_STORY_TAG_RE` (`:304`, `[US1]`) and
  `_STORY_CITATION_RE` (`:305`, `spec US1-`). **None of them looks at a file
  path.** It answers "does this task reach an agent", not "what does it touch".
- `factory/verify/diffbounds.py:52` — `_FILE_HEADER_RE`, which does parse file
  paths — out of a **unified diff**, not out of prose. Not reusable for a
  `tasks.md` scan, and a diff does not exist before dispatch anyway.

So **extracting file paths from task prose is NEW code with no precedent in this
tree.** Say so in your own reasoning rather than hunting for the function this
plan used to promise. Build it on top of `task_slice_bounds` so the slicing half
still cannot drift from dispatch, and keep the path-recognition half small and
testable on its own.

- `depends_on_merged` is the existing contention edge type. US2 infers edges of
  that kind; it does not invent a third.

**US3 — reset and the forge:**

- `factory/cli/nouns/build.py:879-915` — `_reset_epic`. Local only; nothing in it
  reaches the forge.
- `factory/mergequeue/gh.py:163-193` — `create_pr`, the forge client's open-a-PR
  path. **This plan said until 2026-08-20 that it was broken — calling
  `_run_json("pr","create", …)` without `--json` so `json.loads` raised on every
  first attempt. That was true when it was written and 071 fixed it** (`476713a`,
  `225cb31`). It now uses `self._run` and derives the number from the URL `gh`
  prints on stdout; there is no `json.loads` on this path at all. Treat a failure
  inside `create_pr` as **yours**, not as the known finding.

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

**7. Reuse the SLICING; the path extraction does not exist and you are writing
it.** This trap previously claimed the slice-coverage machinery already produces
per-story file paths. It does not — see the corrected US2 anchors above, where
each regex is named. Two halves, and they have different answers:
- *Which lines are this story's?* — already solved, by
  `task_slice_bounds` (`factory/workgraph/prompt.py:558`). Go through it. A
  second slicer that disagrees with `spec validate` is worse than no inference,
  and it will disagree at exactly the boundary cases that matter.
- *Which file paths do those lines name?* — **new code.** Nothing in the tree
  does it. Keep it a small pure function over a block of text so it can be tested
  against the corpus's real spelling variety (backticked paths, bare paths, paths
  inside prose, paths that are directories, paths that do not exist yet because
  the story creates them) rather than only against the shape you had in mind.

**8. US3 must not reach outside `factory/<epic>/<node>`.** US3-S4. A cleanup verb
that closes a pull request an operator opened by hand is a far worse defect than
the one being fixed. Scope every forge call by that namespace and test the
negative.

**9. US3 must degrade rather than fail.** US3-S5. If the forge is unreachable the
local reset still completes and says what it could not do. A cleanup verb that
aborts on a network error strands the operator in the state it exists to clear.

**10. `create_pr` is NOT broken any more — a failure there is yours.** This trap
used to say the opposite, and following it now would cost you the attempt: you
would see a real regression you introduced, read this line, and dismiss it as a
known finding. 071 fixed `create_pr` (`476713a`, `225cb31`). Verified against
`357d227`: `factory/mergequeue/gh.py:163-193` calls `self._run`, not
`_run_json`, and parses the PR number out of the URL `gh` prints — no `json.loads`
on that path. **Treat any failure inside it as something you caused.**

The general lesson, since this is the second stale "known broken" note found in
this spec set: a trap that grants permission to ignore a failure has a short
shelf life, and it fails dangerously rather than safely. State the commit you
verified it against, as this one now does.

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
