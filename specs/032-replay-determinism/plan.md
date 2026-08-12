# Plan: The epic's command sequence is a fact, not a race

All line references were read against the tree at commit `c6ad7d6` on
2026-08-11 and **re-verified against the tree on 2026-08-12** — nothing landed
in between, so every anchor below still resolves. They are cited so you can
find the code, not so you can trust the numbers — grep for the named construct
if a number does not resolve (trap 5).

**Re-split into three stories on 2026-08-12 after the epic was killed at
attempt 4. Trap 8 is new and is the one that killed it. Read it first.**

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The test that caught it: record → fetch history → replay | `tests/test_interpreter.py:2685-2709` (grep `test_replay_dispatches_nothing_twice`) | US1 — the template and the assertion set that must survive unweakened |
| Its own statement of purpose | docstring `:2686-2692` — "a set's iteration order … fails here" | US1 — the suspect list, written before the crime |
| `Replayer(workflows=[EpicWorkflow]).replay_workflow(history)` | `tests/test_interpreter.py:2705` | US1, US2, US3 — the replay instrument |
| Onboarding step scheduling `validate_target_repo` | `factory/workgraph/workflow.py:829` (method documented at `:815-828`; invoked from the run boundary near `:644`) | US1 — one half of the mismatch pair |
| Node coroutine dispatch (`asyncio.create_task`) | `workflow.py:754` (recovery), `:758` (fresh); the determinism comment at `:685` | US1 — the other half's neighborhood |
| The reap sites (shared helper after 010/US1) | grep `_reap_finished` | US1 — context: where node tasks resolve |
| `ScriptedWorld` activity scripting | `tests/test_interpreter.py:837` (grep `class ScriptedWorld`) | US1 — the seam for seeded completion delays |
| `WorkflowEnvironment.start_time_skipping()` fixture | `tests/test_interpreter.py:1659` (anchor re-verified 2026-08-12) | US1, US2, US3 — the recording environment |
| CI evidence: three red runs, one signature | runs 31503294508, 31505841855 (018/us2), and 031/us1's first run, all `[TMPRL1100] validate_target_repo` vs `teardown_attempt` | US1 — what the harness must reproduce, and what the evidence file must contain verbatim |
| Local evidence: nine green | 2 worker gates, 6 isolated 2-core runs, 1 full-suite 2-core run (2130 passed, 345s) | US1 — why an unforced local run proves nothing; the forcing is the point |
| The finding, both hypotheses recorded pre-diagnosis | `ergane findings list --json`, key `interpreter/replay-test-nondeterminism-under-load` | All three stories — the ledger row this spec resolves |

## Traps

### Trap 1 — the deploy can wedge the floor, and 018 is lying in its path

Temporal replays every in-flight epic through the current code at worker
restart. This spec changes command ordering, which is exactly the thing replay
checks. An epic recorded under the old code and restarted under the new one
fails replay unless **US3**'s compatibility holds — and 018 sits parked-open
today, its history recorded by the old code. The plausible wrong fix is to
ship US1 alone and let the restart find out. US3 is not optional polish; it is
the half that keeps the cure from wedging the patients. If compatibility for
some recording class is genuinely impossible, FR-005/US3-S2 requires saying so
in the landing notes with the operator rule spelled out — never discovering it
at a restart.

(Story numbers here changed in the 2026-08-12 split: the compatibility story
was US2 and is now US3. The hazard is identical.)

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
you get little slack: prove the harness reproduces the defect, capture that to
the evidence file, and confirm the fixed suite is green locally — all before
your first landing attempt (trap 8).

### Trap 7 — no test may touch the live evidence store

`hardening/test-suite-writes-to-the-live-evidence-store` is open and this
epic's suite runs on the worker host. Every new test builds its store under
`tmp_path`, exports nothing, and reads nothing from `.factory/`. The fixture
history file is a committed test asset, never a read of production state.

### Trap 8 — a tests-only diff is how this story failed four times

**This is the trap that has already cost the most, and it is the one you are
most likely to walk into.** It is not hypothetical: on 2026-08-11 this exact
story was attempted four times (three implementer, one debugger, roughly nine
hours and 128M input tokens) and *every single attempt* produced a diff that
touched only `tests/test_interpreter.py` and never `factory/`. The judge
rejected all four with the same words. The agents were not lazy — they were
trapped by a contradiction in the old story text, which asked for a fail-first
reproduction and the fix in one diff.

Here is the bind, so you recognise it instead of rediscovering it:

- The deterministic gate runs `uv run pytest -q` over **your diff**.
- A test that genuinely reproduces this defect must **fail**.
- So a real fail-first test in your diff turns the gate red and kills the
  attempt — but writing the harness to assert *success* means you have not
  demonstrated the defect, and the judge fails you for that instead.

**The way out, which the story now mandates:** the reproduction is a
**committed evidence file**, not a live failing test. Run the harness against
the unfixed tree, capture the output to
`specs/032-replay-determinism/evidence/pre-fix-repro.txt`, commit it, *then*
fix `factory/workgraph/workflow.py`, then show the harness green. Your diff
ends up green-suite **and** carrying proof the defect was real.

Two checks before you finish:

1. `git diff --name-only` must list at least one path under `factory/`. If it
   does not, you have written the same failing attempt a fifth time.
2. The evidence file must exist and must contain the actual `[TMPRL1100]`
   output — not a description of it, not a summary you wrote from memory.

## Approach

> **Re-planned 2026-08-12** for the three-story split. All line anchors in the
> reuse inventory were re-verified against the tree on that date and are
> current; nothing landed between drafting and now, so they did not rot.

### US1 — reproduce as evidence, diagnose, fix

**Read trap 8 before you write a line.** The single failure mode of this story
is delivering a tests-only diff, and it has already happened four times.

1. Build the adversarial harness first: a `ScriptedWorld` variant (or a
   parameter) that applies seeded per-activity completion delays, biased to
   interleave the onboarding activity's completion with the first node's
   attempt/teardown window. Sweep a small seed range; find the seed(s) that
   reproduce `[TMPRL1100] … validate_target_repo … teardown_attempt` on the
   worker host.
2. **Capture that reproduction to a file and commit it** —
   `specs/032-replay-determinism/evidence/pre-fix-repro.txt`, containing the
   seed, the command, and the verbatim failure output. This is FR-002's
   evidence. Do **not** leave a failing test behind to represent it; the gate
   runs the suite over your diff and a red suite fails the attempt (trap 8).
3. With a reproducing seed in hand, diagnose: the mismatch means the
   recording emitted the onboarding command and a node command in an order
   replay does not re-derive. Read the run boundary (`:644` neighborhood) and
   the dispatch loop for any construct whose emission order can vary with
   wakeup order — a `create_task` racing an `await`ed activity call, a
   `gather` over heterogeneous coroutines, iteration over an unordered
   collection feeding command emission. The docstring's suspect list (clock,
   set order, naked uuid4) is the checklist; the sandbox rules out clocks, so
   expect task-wakeup ordering.
4. Fix by imposing deterministic emission: sequence the racy commands
   explicitly (await the onboarding schedule before opening the dispatch
   window, or emit through one ordered path) — the smallest change that makes
   the order a pure function (trap 4). **This step edits
   `factory/workgraph/workflow.py`. If your diff ends with no change under
   `factory/`, you have not done this story.**
5. Rerun the harness at the reproducing seed **3** consecutive times; rerun the
   unmodified original test; rerun the full suite clean. Three, not fifteen —
   the 15-cycle standing proof is US2's, deliberately kept off the story that
   must clear a red check to land.

### US2 — the standing regression

Dispatches only after US1 has **merged**, so the required check is green and
this story can afford slow proof.

1. Promote US1's harness into a permanent suite fixture running **15**
   consecutive record-replay cycles at a fixed seed (FR-008).
2. Capture and commit a benign-scheduling history fixture recorded from
   pre-fix code — US1's evidence file names the seed and the procedure, so
   this is a re-run, not a re-derivation. If the pre-fix tree is no longer
   reachable by then, `git worktree add` at US1's base ref is the supported
   way to get it; say so in the PR rather than fabricating a fixture.
3. Keep the 15-cycle run inside the gate's time budget. If it does not fit,
   **the cycle count gives, not the store isolation** (trap 7) — an isolated
   3-cycle test beats a fast one that writes to the live store.

### US3 — the compatibility fixture

Dispatches after US1 merges; independent of US2.

1. Replay the committed pre-fix benign history through the fixed code; it must
   pass (FR-005).
2. The fixture test is part of the default suite forever (FR-006) — it is
   the guard that makes the *next* command-order change fail at the gate
   instead of at a worker restart, and it is what keeps 018 replayable across
   the deploy (trap 1).

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A seeded adversarial harness instead of "run it many times" | Nine unforced runs are green; without forced interleaving there is no reproduction and no proof the fix fixed anything (trap 3). |
| Committed history fixtures | The alternative — trusting that ordering changes are compatible — is precisely the assumption that wedges 018 at the next restart (trap 1). |
| An evidence *file* rather than a fail-first test | A failing test cannot coexist with a green gate in the same diff. Four attempts proved the contradiction empirically before it was seen in the text (trap 8). |
| Three stories, both edges on US1 | US1 must contain the fix because its PR is the one that turns the required check green — no story of this spec can merge before the fix does. US2 (standing proof) and US3 (deploy safety) have different failure modes and neither needs the other, so both hang off US1 rather than forming a chain. |
| 3 cycles in US1, 15 in US2 | Everything US1 carries must clear a red check to land. The heavy proof is real but it can wait one merge; loading it onto the unblock is what made the original story unbuildable. |

## Verification

`uv run pytest -q` green in the worktree, clean env, never with the operator
environment exported (trap 7). The evidence that did not exist before is the
point: a seed that reproduces the CI signature on this host against the
pre-fix tree — **captured to the committed evidence file, not left as a failing
test** (trap 8) — the same seed silent against the fixed tree, and a pre-fix
history that replays through the fixed code.

For US1 specifically, the suite being green is necessary but nowhere near
sufficient: all four failed attempts had a green suite. The two additional
checks are `git diff --name-only` listing a path under `factory/`, and an
evidence file containing real `[TMPRL1100]` output.

If the harness cannot reproduce the defect before the fix, stop and report
blocked — constitution II. Do not proceed to a fix you cannot demonstrate was
needed, and do not substitute a harness that asserts success.
