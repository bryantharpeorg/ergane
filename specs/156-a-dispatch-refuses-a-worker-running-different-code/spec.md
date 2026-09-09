---
state: landed
# Attested landed 2026-09-08. US1 61f63ca6af73, US2 1c96876be292,
# US3 3efb1319d39b — all three observed on ergane-buildout by content.
#
# VERIFIED BY EXERCISING THE REFUSAL, NOT BY READING THE VERDICT. The two
# decision functions were called directly across the complete case table, and
# the conservative direction FR-003 asks for was confirmed as the asymmetry it
# is meant to be:
#
#   worker != tree        -> US1 REFUSES,  US2 PARKS   (the headline case)
#   worker unknown        -> US1 REFUSES,  US2 PARKS   (an unknown revision
#                            cannot be compared, so it is treated as skew)
#   tree unknown          -> US1 allows,   US2 dispatches
#   worker == tree        -> US1 allows,   US2 dispatches
#
# The third row is the one worth naming: "the tree cannot say what it is" is not
# skew, and parking on it would lock a repository that is not a git checkout out
# of its own factory forever. `_skew_notice` (build) and `_skew_park_detail`
# (roadmap) agree on all four rows, which is FR-003's real requirement -- two
# surfaces, one rule.
#
# `_cli_revision()` answered 1c96876 against a tree at 1c96876 while this was
# checked, so the mechanism was reading the real revision, not a fixture.
#
# US3 IS A DELIBERATE ABSENCE, AND THAT IS WHY IT LOOKS EMPTY. It landed as one
# test file and no production line, which reads like a story that built nothing.
# It is not: the design decision it locks is that a refusal mints **no durable
# skew state**. `build status` and `roadmap status` re-derive the skew from live
# sources every time they are asked, so a cleared skew leaves no residue to
# explain later. Its ten tests assert both directions -- visible while skewed,
# and gone once the worker is aligned -- and all ten pass. A record would have
# been the easier story and the worse design; the absence is the deliverable.
#
# ONE LESSON FOR THE NEXT SPEC THAT TOUCHES THIS FILE. US2 landed +111 lines
# into factory/roadmap/workflow.py. Spec 131, which cites that file 128 times,
# had been brought to zero validate refusals an hour earlier; the merge moved
# all 128 of its anchors and put it back to 45 refusals with nobody editing it.
# Reported against refinement/a-landing-silently-invalidates-every-spec-anchor-
# below-it, now at four occurrences.
#
fixes:
  - interpreter/a-fresh-epic-on-a-stale-worker-wedges-in-workflow-task-retry
---
# DRAFTED 2026-09-06 by an operator session, against ergane-buildout at
# 4dcc3c9, with every anchor read from the working tree the same evening and
# verified to resolve to the symbol named.
#
# WHERE THIS CAME FROM. The finding's own notes name this spec's remedy as "the
# primary ask" that no spec delivers (specs/099's refinement pass declined to
# declare the key because 099 prevents the next wedge without refusing the
# dispatch that causes it). Three occurrences, all the same shape: a landing
# changes code the worker imports, the running worker keeps serving old
# modules, and `workflow.unsafe.imports_passed_through()` resolves a payload
# dataclass against boot-time classes — the next workflow task wedges in
# WORKFLOW_TASK_RETRY forever. Occurrence 3 (2026-08-30) wedged the roadmap
# itself for fifty minutes: a wedged roadmap dispatches nothing and the floor
# goes quiet.
#
# THE SEAM ALREADY EXISTS. 053 landed half the mechanism: the worker captures
# its boot revision (`_worker_revision`, factory/worker.py:220, captured at
# module import :240), an inbound interceptor stamps it into every
# EpicWorkflow input (factory/worker.py:299, :324-327), the epic carries it
# (`EpicInput.worker_revision`, factory/workgraph/workflow.py:583), and the
# CLI already compares it against its own revision — as a NOTICE
# (`_skew_notice`, factory/cli/nouns/build.py:986). The notice is a string
# printed beside a status report. Nothing refuses. This spec makes the last
# half-metre honest: the two dispatch seams REFUSE when the worker that will
# serve the epic is running code the tree has moved past.
#
# WHAT THIS SPEC IS NOT. It does not detect the wedge (a wedged run stays
# wedged — terminating it is the operator's `build kill`, unchanged here). It
# does not restart the worker, and it does not change 099's self-restart
# design — it is the refusal 099's own notes ask for, and the two compose:
# 099 makes the worker take itself down when safe; this makes any dispatch
# meanwhile name the skew instead of creating the next wedge.
#
# WHY THE ROADMAP SEAM MATTERS MORE THAN THE CLI SEAM. A manual
# `ergane build start` is one epic the operator can watch; the roadmap's
# child dispatch (factory/roadmap/workflow.py:1294) fires unattended every
# tick, and occurrence 3 wedged exactly that path. Both seams get the same
# refusal; the roadmap's is the one that pays.

# Feature Specification: a dispatch refuses a worker running different code

## User Stories *(mandatory)*

### User Story 1 - build start refuses when the worker's revision is not the tree's (Priority: P1)

As the operator, when I start an epic by hand and the worker that will serve it
is running code the tree has moved past, the verb tells me so and dispatches
nothing — rather than starting an epic whose first workflow task wedges in
retry and burns the stall budget.

**Why this priority**: P1 because it is the finding's primary ask and the
cheapest story. Every ingredient exists: the worker already stamps its boot
revision into `EpicInput` at dispatch (factory/worker.py:324-327), the epic
already carries it in its status answer (factory/workgraph/workflow.py:910),
and the CLI already computes the comparison (`_cli_revision`,
factory/cli/nouns/build.py:966). The story is a refusal where a notice stands.

**Independent Test**: Patch the worker-revision seam to a value that differs
from the CLI's, run `build start`, and read the exit code and the message.
Run it again with the values equal and read a normal dispatch.

**Acceptance Scenarios**:

1. **Given** a worker whose advertised revision differs from the CLI's
   tree revision, **When** `ergane build start` runs, **Then** the command
   refuses before `start_workflow` (factory/cli/nouns/build.py:929) is
   called, exits non-zero, and the message names both revisions and the
   remedy (`systemctl --user restart ergane-worker` on this host).
2. **Given** a worker whose advertised revision equals the CLI's, **When**
   `build start` runs, **Then** dispatch proceeds exactly as today — the
   refusal adds no latency and no output to the aligned case.
3. **Given** a worker that advertises no revision (`None` — a worker from a
   non-git tree, or one predating 053), **When** `build start` runs, **Then**
   the command refuses with the "worker revision is unknown" wording rather
   than proceeding, because an unknown revision cannot be compared and the
   conservative direction is the same refusal that an unequal one earns.
4. **Given** a CLI that cannot resolve its own revision, **When** `build
   start` runs, **Then** the command proceeds — the CLI's own blindness must
   not lock the operator out of their factory (today's
   `_cli_revision` degrades to `None`, and the refusal must not fire on it).
5. **Given** the refusal message, **When** an operator reads it, **Then** it
   states all three facts in one line: the worker's revision, the tree's
   revision, and the restart command that clears them — no diagnosis step
   between the refusal and the remedy.

### User Story 2 - a roadmap tick parks the spec rather than dispatching into a skewed worker (Priority: P1)

As the operator, when the roadmap's child dispatch would reach a worker
running different code, the tick parks the spec with the skew named — rather
than silently starting an epic that wedges, or wedging the roadmap itself as
occurrence 3 did.

**Why this priority**: P1 shared with US1. The roadmap is the unattended seam
and the one that has actually wedged. Its dispatch
(factory/roadmap/workflow.py:1294) already parks specs for lesser causes
(clone refusal, derive failure, onboarding findings); this story adds the
skew to the same park grammar rather than inventing a second one.

**Independent Test**: Drive a scripted roadmap pass with the child-epic
worker revision differing from the tree's, and read the parked list. Run the
same pass with revisions aligned and read a dispatch.

**Acceptance Scenarios**:

1. **Given** a dispatchable spec and a worker whose advertised revision
   differs from the revision the roadmap's own code was loaded from,
   **When** the dispatch step (factory/roadmap/workflow.py:1170) reaches the
   child start, **Then** the child is not started; the spec is parked with
   `check: dispatch` and a detail naming both revisions and the restart
   remedy, and the roadmap proceeds to the next spec.
2. **Given** the same setup, **When** the operator runs `ergane roadmap
   status`, **Then** the parked entry renders through the same
   park-reason rendering every other parked cause uses (the park message
   the operator reads names branch paths and cures — the standing contract),
   not a new surface.
3. **Given** a parked-by-skew spec and a worker restarted onto the tree's
   revision, **When** the operator sends the unpark signal, **Then** the
   next tick dispatches it — the park is spent exactly as every other park
   is, no new unpark grammar.
4. **Given** a worker that advertises no revision, **When** a tick reaches
   dispatch, **Then** the spec parks with the "worker revision is unknown"
   wording — the same conservative direction as US1-S3.
5. **Given** the roadmap's own code changed while the worker still runs old
   code (occurrence 3's exact shape), **When** the tick starts, **Then** the
   tick itself does not wedge: the skew refusal is evaluated in workflow
   code the worker already has loaded (a comparison of two strings already
   in the payload), so the refusal can never depend on the code that moved.

### User Story 3 - the skew a dispatch refused on is visible after the fact (Priority: P2)

As the operator, when I come back to a floor that refused my dispatch, I can
see why without having watched it happen — the refusal left a record, not
just a terminal message.

**Why this priority**: P2. US1 and US2 answer at the moment of dispatch;
this story answers the question an operator asks an hour later: "why did
nothing run?" The status report already carries `worker_revision` in its
answer (factory/workgraph/workflow.py:689); what is missing is a record of
the refusal that never became an epic.

**Independent Test**: Trigger the US1 refusal, then run `ergane build status`
on the spec and read the skew finding from the same answer path.

**Acceptance Scenarios**:

1. **Given** a `build start` refused under US1, **When** the operator re-runs
   it (or any command that reports the tree's revision), **Then** the skew
   is recomputable from live sources — the refusal message itself names both
   revisions, so the "record" is the operator's own scrollback plus the
   live worker revision in `build status` (factory/cli/nouns/build.py:1172
   reads it today); no new store is minted.
2. **Given** a spec parked under US2, **When** the operator runs
   `ergane roadmap status specs`, **Then** the park detail carries both
   revisions verbatim — the parked list IS the record for the roadmap seam,
   and it survives the tick that wrote it.
3. **Given** either refusal, **When** the worker is restarted and the skew
   clears, **Then** re-running the same command shows no residue: the
   refusal was a fact about a moment, not a durable state to clean up.

## Functional Requirements *(mandatory)*

- **FR-001**: `ergane build start` MUST refuse — no `start_workflow` call,
  non-zero exit — when the serving worker's advertised revision is not equal
  to the CLI's tree revision, and the refusal message MUST name both
  revisions and the restart remedy in one line.
- **FR-002**: The comparison MUST use the values the existing seam already
  produces: the worker's `_WORKER_REVISION` as carried in
  `EpicStatus.worker_revision` (factory/workgraph/workflow.py:689), and the
  CLI's `_cli_revision()` (factory/cli/nouns/build.py:966). No second
  revision source may be minted.
- **FR-003**: A worker revision of `None` MUST refuse with the
  "revision is unknown" wording; a CLI revision of `None` MUST NOT refuse.
- **FR-004**: The roadmap's dispatch step MUST park the spec (check
  `dispatch`) instead of starting a child when the worker's advertised
  revision differs from the revision the roadmap's own module was loaded
  from, and the park detail MUST carry both revisions and the remedy.
- **FR-005**: Both refusals MUST be computable from values already in the
  running payload — the worker's revision as stamped at dispatch and the
  workflow's own loaded revision — so no refusal path may import code the
  worker has not already imported.
- **FR-006**: An aligned case MUST behave byte-identically to today: same
  output, same exit code, same latency, for both `build start` and a
  roadmap tick.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-006]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-001, FR-004]
```

US1 is the refusal in its simplest home (one verb, both revisions in hand);
US2 reuses the same comparison inside the roadmap's existing park grammar and
waits for US1's comparison seam to exist; US3 is the operator-facing record and
waits for both refusal shapes to exist to describe them.

## Constitution References *(mandatory)*

- **Principle VIII — the evidence doctrine**: the refusal must be provable
  from what the command actually did. US1-S1's proof is that
  `start_workflow` was never called — an invocation count, not an absence of
  output.
- **Principle V — no credential in code or logs**: both revisions are commit
  shas; neither is a credential and both already appear in status output.
- **D-009 — declared, never auto-detected**: the refusal compares two
  declared revisions, not a probe of loaded symbols; a worker that lies
  about its revision is out of scope and no requirement here probes for it.

## Success Criteria *(mandatory)*

- `build start` under skew refuses before dispatch, naming both revisions
  and the remedy; under alignment it dispatches as today.
- A roadmap tick under skew parks the spec with both revisions in the park
  detail; the tick itself completes and proceeds to the next spec.
- Both refusals degrade safely on `None`: worker-unknown refuses, CLI-unknown
  does not.
- `uv run pytest -q` green — the whole gate (`ergane.yaml`).