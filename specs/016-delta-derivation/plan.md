# Implementation Plan: Delta Derivation

**Branch**: `016-delta-derivation` | **Date**: 2026-08-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/016-delta-derivation/spec.md`

## Summary

Desired-state reconciliation over registers the repo already keeps: a pure
reader turns default-branch history into per-story landed facts and pins each
landed story's fingerprint at its landing commit; a pure delta function
subtracts unchanged-landed stories from full derivation (with provenance) and
re-opens amended ones; the roadmap renders drift and dispatches through the
delta path universally. Fresh spec, split resume, and amendment become one
mechanism with three baselines, and hand-trimmed remainder files are retired.

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so every fact an implementer node needs is inlined,
each verified against the tree the day of drafting — and T001 re-verifies
them against the tree that actually hosts the work.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: `temporalio`, `yaml` (roster); `git` via
subprocess, which the codebase already shells to throughout
`factory/workgraph/worktree.py`. **This feature adds none.**

**Verified reuse inventory** (file:line as of drafting; T001 re-checks):

- **Attribution grammar**: landing squash subjects are
  `<epic_id>/<node_id>: <STORY_KEY> (#<pr>)` — uniform across every
  *reachable* attributed landing of 007/008/009 on `ergane-buildout`, which is
  ten of eleven stories (e.g. `009-roadmap-scheduler/us2: US2 (#9)` =
  `7d9f207`). The eleventh, `5f6aef1` (`009-roadmap-scheduler/us1: US1 (#8)`),
  is **not reachable** from the branch: the 2026-08-07 009 recovery rewrote
  past that squash and us1's content re-entered inside us2's. This is the
  motivating case for FR-002's per-story attestation fallback, and T004 owns it.
  Rendered by `pr_title` (`factory/mergequeue/messages.py`) as
  `f"{epic_id}/{node_id}: {story_title}"`, with `story_title=node.story_key`
  threaded from the interpreter; `prepare_landing_pr`
  (`factory/activities/merge_activities.py`) merely calls it, and the title
  reaches `client.create_pr` via `open_landing_pr`. GitHub appends the `(#N)`
  suffix at squash. The reader's regex and `pr_title` are the two ends of one
  contract — put the cross-reference in `messages.py`, not in the activity.
- **Reading history**: `git log --format=%H%x09%s <default-branch>` and
  `git show <rev>:specs/<dir>/spec.md` — plumbing invocations in the
  `_git`-helper style of `factory/workgraph/worktree.py` (its `_git`
  wrapper and `WorktreeError` naming discipline are the template; the new
  reader takes a repo path and never touches global state).
- **Fingerprints**: `parse_spec` (`factory/verify/criteria.py:122`) yields
  stories with scenarios and FR bodies; the work-graph declaration comes
  from the deriver's own block parser. Both are pure text-in functions, so
  "fingerprint at revision" is `git show` + existing parsers — no new
  parsing. Fingerprint = story scenarios + implemented FR bodies +
  declaration, hashed structurally (sorted, whitespace-normalized), not
  byte-hashed — a reflowed paragraph is not an amendment.
- **Full derivation**: `derive_workgraph` (`factory/workgraph/derive.py:139`,
  pure) and its staged `_Rejections` discipline (:125) — the delta function
  wraps it: derive fully, then subtract per the baseline, refusing by name
  through the same `Rejection`/`DerivationError` types so the CLI renders
  delta refusals exactly as derive refusals.
- **The remainder fixtures**: banked byte-verbatim at
  `tests/fixtures/remainders/007-parallel-dispatch-remainder.json` and
  `.../009-roadmap-scheduler-remainder.json` (commit `8d57b86`, provenance in
  `tests/fixtures/README.md`). T009 replays against those paths. They are the
  only ground truth of the operator judgment this feature mechanizes; the
  untracked originals still sit beside their specs and are not the fixture.
- **Roadmap surface**: `factory/roadmap/models.py` (frontmatter reader,
  `_KNOWN_KEYS`, :107 — unchanged: amended is computed, never written),
  render in `factory/roadmap/cli.py` (deterministic listing to extend with
  the amended mark), dispatch pipeline in the roadmap workflow's
  pre-dispatch activities (derivation already behind a thin activity per
  009's plan — swap its call to the delta path, signature unchanged).
- **Id conventions**: `workflow_id(epic_id) -> f"epic-{epic_id}"`
  (`factory/workgraph/cli.py`) and the reuse-on-closed precedent — delta
  re-dispatch reuses the id; collision-with-RUNNING parks (009's rule,
  inherited untouched).
- **CLI shape**: offline verbs follow `factory-roadmap render`'s precedent
  (no service, stdout carries only the artifact, exit codes 0/1/2 in the
  module docstring). New verbs live on `factory-epic` beside `derive`
  (`factory/workgraph/cli.py:707` subparsers): `landed` and a
  `--delta`/baseline mode on derive — naming decided at implementation
  against D-021's vocabulary discipline.

**Storage**: none, by requirement (FR-011). Facts and deltas recompute from
git + corpus on demand. Durability through purity: any historical delta is
recomputable by pinning both inputs to commits.

**Testing**: `pytest`. Fixture git repositories built per-test (init, commit
scripted histories with attributed subjects — the worktree tests' repo-
building helpers are the template); corpus fixtures per
`tests/fixtures/README.md`. The delta function itself is pure and needs no
git at all — only the facts/fingerprint reader touches fixture repos. US3
reuses 009's scripted-children pattern for dispatch tests.

**Project Type**: single Python package. New module
`factory/workgraph/landed.py` (facts + fingerprints) and
`factory/workgraph/delta.py` (subtraction + provenance), beside the deriver
they wrap; roadmap changes stay in `factory/roadmap/`.

## Constitution Check

- **I (test-first)**: every task pairs a failing test with implementation.
- **III (dependencies)**: none added.
- **V (credentials)**: no new surface touches keys; provenance carries
  commits and diffs of spec text only — spec text is already
  payload-borne (009's FR-009 closed frontmatter keeps it inert).
- **VI (salvage)**: untouched — no node terminal path changes.
- **VII (persona routing)**: untouched.

## Approach by story

### US1 — landed facts and fingerprints (FR-001..003)

`factory/workgraph/landed.py`: `landed_facts(repo, spec_dir, default_branch)
-> dict[str, LandedFact]` — one `git log` scan, subject regex anchored to
the spec's epic id, newest-first so the first match per story wins (FR-001's
latest-wins). Attestation fallback is **per story**: for each story with no
reachable attributed commit, if the frontmatter is attested `state: landed`,
baseline at the commit that introduced the attestation with `attested=True`.
Writing it as a spec-level `if not any(attributed)` branch is the bug T004
exists to catch — 009 has attributed commits *and* a gap.
`fingerprint(repo, rev, spec_dir, story_key) -> Fingerprint` — `git show` +
`parse_spec` + the deriver's block parser, structural hash as inventoried.

Trap: `git show <rev>:<path>` needs the path as of that revision. Spec dirs
never move today; assert the file exists at the revision and refuse with a
named finding if not — a missing historical file is a fact worth a loud
answer, not an empty fingerprint.

Trap: **reachability is the whole question, so the ref must be fresh.** Reading
the clone's local branch ref repeats the defect `ab54279` fixed in
`capture_base_ref` — the clone's own HEAD is stale exactly when a landing just
happened, which is exactly when facts are asked for. Mirror that discipline:
fetch origin when the repo has one, resolve against `origin/<default>`, fall
back to local HEAD only for a remote-less repo, and raise rather than silently
reading a stale ref. The roadmap path is already safe (its clone step fetches
and resets before deriving), but the standalone `factory-epic landed` verb runs
against whatever clone the operator names.

### US2 — the delta function (FR-004..007)

`factory/workgraph/delta.py`: `derive_delta(spec_text, baseline) ->
DeltaResult` — full `derive_workgraph` first (all its rejections apply
unchanged), then per-node: unlanded → keep; landed + fingerprint equal →
subtract, record satisfied edges with commits; landed + fingerprint differs
→ keep with a `reopened` provenance entry quoting the structural diff.
Identity guard before subtraction: baseline keys absent from the derived
graph, or present with content the fingerprint comparison cannot classify,
→ `Rejection` per story, collected, all-or-nothing. `DeltaResult` carries
the `WorkGraph` plus provenance; the graph serializes through the existing
schema untouched.

Trap: subtraction must re-root edges, not just drop nodes — a kept story
whose `depends_on_merged` named a subtracted story has that edge *satisfied*
(removed with provenance), which is exactly the operator's 007 hand-trim.
Never rewrite an edge to point elsewhere; satisfaction removes, amendment
re-opens, nothing re-targets.

### US3 — the CLI verbs (FR-008)

`factory-epic landed <spec>` renders facts (observed vs attested marked);
delta mode on derivation writes `workgraph.json` from `DeltaResult` and prints
provenance; an empty delta is success with a message and no file. `start`
refuses a zero-node graph — genuinely before any clone or Temporal connection,
because the CLI has cloned nothing at that point. Nothing today validates
non-empty `nodes` (the model's checks are per-node), so this is new behaviour.

Owns `factory/workgraph/cli.py` and its test file, and nothing else — that
disjointness is what lets US3 and US4 run as siblings.

### US4 — roadmap reconciliation (FR-009..011)

Render marks `landed` specs with drifted fingerprints as amended, computed in
the pure layer beside readiness. The pre-dispatch derivation activity
(`derive_spec` in `factory/activities/roadmap_activities.py`) calls the delta
path — its `DeriveInput` already carries `target_repo`, so the signature is
unchanged, but note the activity stops being pure once it reads git, and its
docstring should say so. Docs: decision number claimed, remainder-file
supersession recorded, runbook trim step deleted, `messages.py` cross-reference
added.

Trap: a workflow may not shell git — determinism forbids it. Drift facts must
reach `RoadmapWorkflow` the way readiness facts already do, through the
injected resolver seam (the `landed_for` parameter pattern), or through a new
activity. Computing drift inside the workflow body would be a non-deterministic
replay hazard, not merely slow.

Trap: FR-010's refusal point differs by caller. In the roadmap the clone comes
first and the delta is computed against it — it must, since facts are read from
the refreshed target repo — so the zero-node refusal there is before child-epic
start, not before the clone. Only the CLI's refusal is pre-clone.

Trap: drift detection on every render shells `git show` per landed story —
fine for ten specs, but batch the log scan (one pass, all specs) rather
than per-spec invocations, or render latency grows quadratically with the
corpus. The reader takes the batch shape from day one.

## Complexity Tracking

None. No new dependency, no store, no workflow-type change, no interpreter
change — two pure modules, two CLI verbs, one activity call swapped, one
render column.
