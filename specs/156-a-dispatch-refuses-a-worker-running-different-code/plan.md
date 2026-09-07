# Implementation Plan: a dispatch refuses a worker running different code

Anchors read from the working tree on 2026-09-06 against ergane-buildout at
`4dcc3c9`. Verify every one at implementation time; the corpus's own lesson
(15 of 16 anchors moved under 057 in one week) is the standing rule.

## Where the mechanism lives today

- The worker captures its boot revision at module import:
  `_worker_revision` (`factory/worker.py:220`), stored `_WORKER_REVISION`
  (`factory/worker.py:240`).
- An inbound interceptor stamps it into every `EpicWorkflow` input whose
  `worker_revision` is `None` (`factory/worker.py:299`,
  `_WorkerRevisionInterceptor`; the rewrite at `factory/worker.py:324-327`).
  By-name class matching, not `is` — the SDK sandbox re-imports.
- The epic carries the stamp: `EpicInput.worker_revision`
  (`factory/workgraph/workflow.py:583`), recorded in `run` at
  `factory/workgraph/workflow.py:933`, returned by the `epic_status` query
  (`factory/workgraph/workflow.py:860`, field declared at
  `factory/workgraph/workflow.py:689`).
- The CLI compares as a NOTICE: `_cli_revision`
  (`factory/cli/nouns/build.py:966`), `_skew_notice`
  (`factory/cli/nouns/build.py:986`), consumed in `_query_status` at
  `factory/cli/nouns/build.py:1172-1173`. `None` handling is already shaped
  there: worker-`None` is its own message; CLI-`None` returns `None` (no
  notice).
- `build start`'s dispatch call site: `factory/cli/nouns/build.py:929`
  (`client.start_workflow`) inside `_start_epic`
  (`factory/cli/nouns/build.py:883`).
- The roadmap's child dispatch: `factory/roadmap/workflow.py:1294`
  (`workflow.start_child_workflow`) inside `_dispatch`
  (`factory/roadmap/workflow.py:1170`). Park grammar: `self._park(spec_dir,
  check, detail)` — see the onboarding park at
  `factory/roadmap/workflow.py:1260` for the shape to copy.
- The roadmap has NO revision stamp today. The interceptor at
  `factory/worker.py:324` matches `EpicWorkflow` only; a roadmap run's
  payload carries no worker revision, and its status answers none. US2 must
  add the stamp to `RoadmapInput` the same way 053 added it to `EpicInput` —
  or read it from the child's own dispatch path; see the design note.

## Design note: where US2's comparison comes from

The roadmap workflow cannot call `_cli_revision` — it runs inside the
worker, so "the CLI's revision" inside a workflow is the worker's own
revision, and the comparison would always be equal. What the roadmap CAN
compare is the revision its own module was loaded from against the
revision the worker stamped at boot. Both are worker-side strings that
already exist (`_WORKER_REVISION` and a second capture at the moment the
RoadmapWorkflow module was imported — but the SDK sandbox re-imports the
workflow module per run, so a module-level capture is the FILE's current
content, which is the tree, not the worker's boot-time import). The honest
shape is: extend `_WorkerRevisionInterceptor`
(`factory/worker.py:299`) to stamp `RoadmapInput` too, add
`worker_revision` to `RoadmapInput` (`factory/roadmap/workflow.py:229`),
and have the roadmap carry a second field — `tree_revision`, captured the
same way the CLI does it but inside a workflow-legal seam (an ACTIVITY: a
one-shot activity that runs `git rev-parse` in the worker's package
directory; activities run in the worker process, where `_WORKER_REVISION`
was imported at boot, so the activity returns the CURRENT tree revision
while the input stamp carries the BOOT revision — the two values the
comparison needs). FR-005's "no refusal path may import code the worker has
not already imported" is satisfied: the activity is registered at boot with
the worker; only its return value is new.

## What to build, in order

1. **The comparison seam** (US1): a pure function
   `skew_refusal(worker_revision, cli_revision) -> str | None` beside
   `_skew_notice` (`factory/cli/nouns/build.py:986`), returning the refusal
   message or `None`. Reuse `_skew_notice`'s `None` handling verbatim:
   worker-`None` refuses ("worker revision is unknown"), CLI-`None` does
   not. `_skew_notice` itself is unchanged — the notice keeps rendering in
   status output.
2. **The refusal in `_start_epic`** (US1): call the seam after preflight,
   before `start_workflow` (`factory/cli/nouns/build.py:929`). On a
   refusal: print the message to stderr, exit non-zero, dispatch nothing.
   The aligned case must add no output and no measurable latency (FR-006).
3. **The worker-side revision for the roadmap** (US2): widen
   `_WorkerRevisionInterceptor` (`factory/worker.py:299`) to stamp
   `RoadmapInput` exactly as it stamps `EpicInput` (same by-name match, same
   `None` guard), add `worker_revision: str | None = None` to
   `RoadmapInput` (`factory/roadmap/workflow.py:229`), and add the
   tree-revision ACTIVITY (design note above): registered in the worker's
   activity list, returning `git rev-parse --short HEAD` from the worker's
   package directory.
4. **The park in `_dispatch`** (US2): before the child start at
   `factory/roadmap/workflow.py:1294`, execute the tree-revision activity,
   compare against `request.worker_revision`, and on inequality
   `self._park(spec_dir, "dispatch", detail)` with both revisions and the
   restart remedy in the detail — then `return`, letting the tick proceed
   to the next spec. Copy the onboarding park's shape
   (`factory/roadmap/workflow.py:1260`). Worker-`None` parks with the
   "unknown" wording (FR-003's conservative direction, applied to US2-S4).
5. **The record** (US3): nothing to build — the refusal message and the
   park detail ARE the record. US3's scenarios are the verification that no
   residue and no second surface exist. If implementation adds a store,
   US3-S3's "no residue" test must fail it.

## Traps (consolidated — meet them as declared scope, not as failure)

1. **Do not put the refusal inside `_skew_notice`.** The notice renders in
   status output for every epic; the refusal must fire only at dispatch.
   Two functions, one comparison table: the seam (step 1) may share
   `_skew_notice`'s `None` arms but not its call sites.
2. **By-name class matching, not `is`** — `factory/worker.py:324`'s comment
   is the measured reason: the SDK sandbox re-imports the module, so
   identity never matches. Copy the `getattr(input.type, "__name__", "")`
   shape exactly; a `is EpicInput` comparison silently stamps nothing.
3. **A workflow may not run `git`.** The tree revision must come from an
   ACTIVITY (worker process), never from workflow code — workflow code
   that shells out wedges on the sandbox's determinism checks. This is
   FR-005's real meaning, and the design note above is the compliant shape.
4. **`RoadmapInput` is a dataclass crossing the workflow boundary** — the
   very defect class this spec fixes. Adding `worker_revision` to it is
   safe ONLY because the interceptor stamps it at dispatch (worker-side,
   boot-time code) and `None` remains the default for payloads written
   before this story. Tests that construct `RoadmapInput` by hand must not
   be broken by the new field's presence.
5. **The park must not fail the tick.** `self._park` then `return` — never
   raise. A raised skew refusal in `_dispatch` is a wedged roadmap wearing
   a different message.
6. **`temporal` tests need the fake client to carry the revision** — the
   existing `RoadmapWorld`/`ScriptedWorld` fakes answer `epic_status`
   queries; US2's tests must extend the fake's `epic_status` answer with
   `worker_revision` rather than minting a second fake.

## Verification

- Re-read every anchor against the tree at implementation time.
- `uv run pytest -q` green — the whole gate (`ergane.yaml`).
- Run the thing: with the worker deliberately stopped on an old revision
  (or the seam patched in a scratch worktree), `uv run ergane build start`
  on a one-node throwaway spec refuses with both revisions named; aligned,
  it dispatches. Evidence pasted, not asserted.
- A scripted roadmap pass parks a spec under skew and proceeds to the next
  tick — the parked list is the record (US3-S2).