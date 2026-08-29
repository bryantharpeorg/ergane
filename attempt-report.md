# Attempt 1 — US3: An attempt reads the standards on the landing branch

## What changed

Four committed files of production code and four of tests, five commits, in
this order: red tests first (T017–T021, committed failing at import —
`resolve_standards` did not yet exist), then the resolution activity
(T022/T023), then the workflow wiring, then the boundary-record allowlist.

- `tests/test_118_standards_per_attempt.py` (new) — the story's five
  acceptance tests over a real git repository in `ActivityEnvironment`.
- `factory/activities/agent_activities.py` — new `resolve_standards`
  activity (+`ResolveStandardsInput`): per attempt, resolves the declared
  document from the landing head via `capture_base_ref`/`_git show`, falls
  back to the pinned tree's copy on any read failure, and reports the reason.
- `factory/workgraph/prompt.py` — the builder takes an optional
  `standards_resolution` and renders a source note plus the resolved text,
  quoted. It reads no filesystem and imports no new module: purity kept (T021
  asserts it structurally).
- `factory/workgraph/models.py` — `StandardsResolution` (text, source, detail)
  plus the two source constants `STANDARDS_SOURCE_LANDING` / `..._PINNED`.
- `factory/workgraph/workflow.py` — both prompt assemblies (the ladder's and
  the recovery's) resolve per attempt, under
  `workflow.patched("standards-resolved-per-attempt")`.
- `factory/worker.py` — the activity registered.
- `tests/test_temporal_payload_shape.py` — the two new boundary records
  allowlisted with kind justifications.
- `tests/test_interpreter.py`, `tests/test_ergane_build.py`,
  `tests/test_external_completion.py` — the three scripted worlds serve the
  new activity name, and their pinned per-node sequences gained it.

## How the scenarios are covered

- **US3-S1 (T017)** — the worktree is prepared, the correction is landed on
  the landing branch, the second resolution carries the corrected text while
  the worktree's copy still holds the original — and the assembled prompt
  contains the corrected text and not the stale bytes.
- **US3-S2 (T018)** — two arms, both proven not to fail the attempt: the
  document absent at the landing head (removed upstream), and the landing
  branch unreachable (origin repointed at a nonexistent path). Both fall back
  to the pinned copy, carry its text and a non-empty `detail` into the prompt.
- **US3-S3 (T019)** — the prompt records `Standards source: \`landing-branch\``
  on the clean arm and `\`pinned-tree\`` with the failure's own reason quoted,
  on the fallback arm.
- **US3-S4 (T020)** — the fixture repo (whose manifest declares no standards)
  reads `standards=None` out of `load_prompt_sources`, resolves `None` through
  the new activity, and assembles a prompt byte-identical to one built with no
  resolution at all, with no Standards section.
- **T021** — structural, two tests: the builder still takes the path and the
  resolution with `None` defaults; and the prompt module's whole import set is
  refused against {subprocess, shutil, tempfile, git, pathlib} plus a walk of
  every call expression for `open`/`Popen`/`run`.

## FR-010, answered for this story (T024's second half)

The two things FR-010 names — the criteria snapshot and the
reuse-across-attempts rule — are unchanged by this epic: `git diff 6659a8e --
factory/verify/ factory/workgraph/worktree.py` is empty on this branch, and
the diff contains no edit to either module. The per-attempt resolution was
deliberately placed outside the reuse rule's reach: it writes nothing into the
worktree (the resolved text travels in the prompt, not the tree), so no
attempt's diff, salvage or reuse is affected by it.

## The dispatch-path shape, and why it is patched

`load_prompt_sources` still reads the declared path once per epic; what
changed is that each attempt's prompt is assembled from a resolution made
that attempt, before the key is issued, in both prompt-assembly sites. The
call sits behind `workflow.patched(...)`: the ten replay-032 fixture
histories record multi-attempt nodes whose `load_prompt_sources` was their
only standards hop, and under a bare call a replayed ladder would schedule an
activity its history does not contain and diverge. With the patch, the
recorded histories replay green (14 replay/determinism tests, included in the
gate) while every new epic resolves per attempt.

## The one design turn the tests forced

Written first as "note the source beside the path directive", the tests
failed honestly: the correction reached nowhere the agent reads, because the
prompt only names a path and the path's copy in the pinned tree is stale by
construction — writing the fresh copy into the worktree would pollute the
judged diff. So the resolution travels as *text in the prompt*, quoted,
under a note that says which copy wins when the two differ. That is also what
makes FR-009 real rather than cosmetic: the archived prompt carries the
document an attempt was actually given, not a pointer that may disagree with
it.

## Gate result

`uv run pytest -q` on the final tree — **5178 passed, 58 skipped, 0
failed** (6m41s). (The first full run failed 2 payload-boundary tests over
the new records — the guard the constitution's FR-006 mechanism exists for;
fixed in 44e72c4, and the re-run above is the green one.)

Scoped: `tests/test_118_standards_per_attempt.py` 7 passed;
`tests/test_interpreter.py` 92; `tests/test_worker.py` /
`test_worker_versioning.py` / `test_worker_deploy.py` 43;
`tests/test_agent_activities.py` 45; prompt suites 40; the ScriptedWorld
family (023, 109, 114-family, pause, sweep, subscription, escalation,
landing, rung, status) 269; `test_ergane_build.py` 45;
`test_external_completion.py` and `test_launch_is_not_an_attempt.py` 12;
replay-032 fixtures green.

## Traps, accounted

6. **Builder purity kept** — resolution runs in the activity that already
   reads the repository; the builder takes already-read data and imports
   nothing new (asserted, not promised).
7. **A standards fetch may not fail a node** — every failure mode on the
   resolution path (no origin, failed fetch, absent path, decode error, even
   a pinned copy missing too) returns a resolution rather than raising; the
   activity's return type is `StandardsResolution | None`, and the pinned arm
   carries the reason verbatim into the prompt.
8. **The source is on the archived prompt** — both arms render a source line,
   and the fallback's reason is quoted through the same verbatim-fencing
   every other quoted block in the prompt travels by.

(The remaining five traps are US1/US2's and sit in sibling slices; nothing
here touches `worktree.py` or the record.)

## Not done, and not in scope

- **T025 (the operator's live-floor demonstration) was not run.** It needs
  `ergane build start` against a live Temporal and a landing branch that
  moves under a running epic — the factory's own live environment. The gate
  cannot produce it and this attempt cannot either; it remains the
  operator's demonstration, and US1/US2's status line is the artifact it
  waits on.
- No rebase or refresh verb, no criteria-snapshot edit, no worktree-module
  edit — the spec's not-in-scope list, held.
- `ergane.yaml` and `personas.yaml` untouched.