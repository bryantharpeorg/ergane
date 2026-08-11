# Plan: The epic's command sequence is a fact, not a race

All line references were read against the tree at commit `c6ad7d6` on
2026-08-11. They are cited so you can find the code, not so you can trust the
numbers — grep for the named construct if a number does not resolve (trap 5).

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The test that caught it: record → fetch history → replay | `tests/test_interpreter.py:2685-2709` (grep `test_replay_dispatches_nothing_twice`) | US1 — the fail-first template and the assertion set that must survive |
| Its own statement of purpose | docstring `:2686-2692` — "a set's iteration order … fails here" | US1 — the suspect list, written before the crime |
| `Replayer(workflows=[EpicWorkflow]).replay_workflow(history)` | `tests/test_interpreter.py:2705` | US1, US2 — the replay instrument |
| Onboarding step scheduling `validate_target_repo` | `factory/workgraph/workflow.py:829` (method documented at `:815-828`; invoked from the run boundary near `:644`) | US1 — one half of the mismatch pair |
| Node coroutine dispatch (`asyncio.create_task`) | `workflow.py:754` (recovery), `:758` (fresh); the determinism comment at `:685` | US1 — the other half's neighborhood |
| The reap sites (shared helper after 010/US1) | grep `_reap_finished` | US1 — context: where node tasks resolve |
| `ScriptedWorld` activity scripting | `tests/test_interpreter.py` (grep `class ScriptedWorld`) | US1 — the seam for seeded completion delays |
| `WorkflowEnvironment.start_time_skipping()` fixture | `tests/test_interpreter.py:1657-1660` | US1, US2 — the recording environment |
| CI evidence: three red runs, one signature | runs 31503294508, 31505841855 (018/us2), and 031/us1's first run, all `[TMPRL1100] validate_target_repo` vs `teardown_attempt` | US1 — what the harness must reproduce |
| Local evidence: nine green | 2 worker gates, 6 isolated 2-core runs, 1 full-suite 2-core run (2130 passed, 345s) | US1 — why unforced local repro is not a viable fail-first |
| The finding, both hypotheses recorded pre-diagnosis | `ergane findings list --json`, key `interpreter/replay-test-nondeterminism-under-load` | Both stories — the ledger row this spec resolves |

## Traps

### Trap 1 — the deploy can wedge the floor, and 018 is lying in its path

Temporal replays every in-flight epic through the current code at worker
restart. This spec changes command ordering, which is exactly the thing replay
checks. An epic recorded under the old code and restarted under the new one
fails replay unless US2's compatibility holds — and 018 sits parked-open
today, its history recorded by the old code. The plausible wrong fix is to
ship US1 alone and let the restart find out. US2 is not optional polish; it is
the half that keeps the cure from wedging the patients. If compatibility for
some recording class is genuinely impossible, FR-005/US2-S2 requires saying so
in the landing notes with the operator rule spelled out — never discovering it
at a restart.

### Trap 2 — do not fix the test; the test is the victim

Every reflex that makes the red go away without touching the workflow —
retrying the replay, marking the test, catching `NondeterminismError` and
skipping, loosening the assertion, deleting the recording phase — ships the
defect and blinds the one instrument that sees it. FR-004 forbids all of it.
The fix lives in `factory/workgraph/workflow.py`. The test file changes only
to add the adversarial harness and the fixture regression, and the original
test's assertions survive byte-for-byte.

### Trap 3 — the harness must force the interleaving, not hope for it

Nine unforced local runs are green; the defect needs scheduling pressure a
fast host does not produce. A fail-first task that just reruns the test
locally will pass before the fix and prove nothing (constitution II's trap:
a test that cannot fail first is not evidence). The harness must *inject*
adversity deterministically — seeded delays in `ScriptedWorld`'s activity
completions at the epic/node boundary, so the recording's event loop is
forced through the interleavings a loaded runner produces. Seeded, so the
reproduction is a fact anyone can re-run, not a coincidence the harness got
lucky on. If seeded delays at that seam cannot reproduce the signature,
widen the seam (delay the onboarding activity's completion specifically —
the mismatch pair names it) before concluding anything.

### Trap 4 — determinism means order, not outcomes

The tempting big fix is restructuring how nodes are dispatched (child
workflows, a command queue, serializing onboarding against dispatch). FR-003
draws the line: same activities, same inputs, same outcomes, same
concurrency semantics — only the *command emission order* becomes invariant.
If the diagnosis shows onboarding and node dispatch legitimately race by
design, the fix is to impose one deterministic emission order (award it in
code, e.g. sequence the onboarding command before the dispatch loop's first
commands), not to redesign dispatch. `temporal/node-child-workflows` owns the
redesign; taking it here burns this spec's urgency on that spec's scope.

### Trap 5 — these line numbers rot, and this module moves weekly

`workflow.py` is the most-edited file in the tree; 010 proved day-old refs
can be off by hundreds of lines. Grep for constructs: `validate_target_repo`,
`create_task`, `_reap_finished`, `test_replay_dispatches_nothing_twice`. The
tree wins; say so in your commit message when it does.

### Trap 6 — you are editing the module that is running you, under a red check

The worker driving your attempt imports the *old* `workflow.py` from its own
checkout; your edits cannot affect the epic building you (010's trap 6, still
true). Two consequences. First: do not restart the worker, ever — that is the
operator's act, sequenced after landing (trap 1). Second: your landing's
required check runs *your* tree — with your fix — so a correct fix lands
green through the very check that is red for everyone else. If your PR reds
on the replay test, your fix is wrong or incomplete; that is signal, not
noise, and the blind-recovery ladder (max_recovery_cycles=1, see 025) means
you get little slack: make the fail-first harness airtight locally before
your first landing attempt.

### Trap 7 — no test may touch the live evidence store

`hardening/test-suite-writes-to-the-live-evidence-store` is open and this
epic's suite runs on the worker host. Every new test builds its store under
`tmp_path`, exports nothing, and reads nothing from `.factory/`. The fixture
history file is a committed test asset, never a read of production state.

## Approach

### US1 — reproduce, diagnose, fix

1. Build the adversarial harness first: a `ScriptedWorld` variant (or a
   parameter) that applies seeded per-activity completion delays, biased to
   interleave the onboarding activity's completion with the first node's
   attempt/teardown window. Sweep a small seed range; find the seed(s) that
   reproduce `[TMPRL1100] … validate_target_repo … teardown_attempt` on the
   worker host. This is the fail-first evidence (FR-002) and T004's exit
   criterion.
2. With a reproducing seed in hand, diagnose: the mismatch means the
   recording emitted the onboarding command and a node command in an order
   replay does not re-derive. Read the run boundary (`:644` neighborhood) and
   the dispatch loop for any construct whose emission order can vary with
   wakeup order — a `create_task` racing an `await`ed activity call, a
   `gather` over heterogeneous coroutines, iteration over an unordered
   collection feeding command emission. The docstring's suspect list (clock,
   set order, naked uuid4) is the checklist; the sandbox rules out clocks, so
   expect task-wakeup ordering.
3. Fix by imposing deterministic emission: sequence the racy commands
   explicitly (await the onboarding schedule before opening the dispatch
   window, or emit through one ordered path) — the smallest change that makes
   the order a pure function (trap 4).
4. Rerun the harness across the reproducing seeds 15 times each; rerun the
   unmodified original test; rerun the full suite clean.

### US2 — the compatibility fixture

1. During US1's fail-first phase, capture and commit two history fixtures
   from the *pre-fix* code: one benign-scheduling recording (the production
   class), one adverse if a reproducing seed yields a complete history.
2. Add the standing regression: replay both fixtures through the current
   code; benign must pass (FR-005); adverse passes if the fix's mechanism
   permits, else the test documents the impossibility and the landing notes
   carry the operator rule (US2-S2).
3. The fixture test is part of the default suite forever (FR-006) — it is
   the guard that makes the *next* command-order change fail at the gate
   instead of at a worker restart.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A seeded adversarial harness instead of "run it many times" | Nine unforced runs are green; without forced interleaving there is no fail-first and no proof the fix fixed anything (trap 3). |
| Committed history fixtures | The alternative — trusting that ordering changes are compatible — is precisely the assumption that wedges 018 at the next restart (trap 1). |
| Two stories instead of one | The fix (US1) and the deploy-safety proof (US2) have different failure modes and US2's fixture must be captured from pre-fix code — a sequencing fact the merge-edge encodes. |

## Verification

`uv run pytest -q` green in the worktree, clean env, never with the operator
environment exported (trap 7). The evidence that did not exist before is the
point: a seed that reproduces the CI signature on this host against the
pre-fix tree, the same seed silent against the fixed tree, and a pre-fix
history that replays through the fixed code. If the harness cannot fail
before the fix, stop and report blocked — constitution II.
