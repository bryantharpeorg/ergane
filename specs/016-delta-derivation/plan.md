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
  `<epic_id>/<node_id>: <STORY_KEY> (#<pr>)` — verified uniform across all
  eleven landed stories of 007/008/009 on `ergane-buildout` (e.g.
  `009-roadmap-scheduler/us2: US2 (#9)`). Rendered by `prepare_landing_pr`
  (`factory/activities/merge_activities.py:301-307`, title returned and
  passed to `open_pr` at :343); GitHub appends the `(#N)` suffix at squash.
  The reader's regex and this renderer are two ends of one contract — note
  the cross-reference in both files.
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
- **The remainder fixtures**: `specs/007-parallel-dispatch/
  workgraph-remainder.json` and `specs/009-roadmap-scheduler/
  workgraph-remainder.json` — the 2026-08-07 hand-trims, currently
  untracked. Commit them under `tests/fixtures/` as SC-002's expected
  outputs before they are lost; they are the only ground truth of the
  operator judgment this feature mechanizes.
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
latest-wins). Attestation fallback: no attributed commits and frontmatter
`state: landed` → `git log --follow -1` for the commit introducing the
attestation, every story landed there, `attested=True`. `fingerprint(repo,
rev, spec_dir, story_key) -> Fingerprint` — `git show` + `parse_spec` + the
deriver's block parser, structural hash as inventoried above.

Trap: `git show <rev>:<path>` needs the path as of that revision. Spec dirs
never move today; assert the file exists at the revision and refuse with a
named finding if not — a missing historical file is a fact worth a loud
answer, not an empty fingerprint.

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

### US3 — CLI verbs and roadmap reconciliation (FR-008..011)

CLI: `factory-epic landed <spec>` renders facts; delta mode on derivation
writes `workgraph.json` from `DeltaResult` and prints provenance; empty
delta → success, message, no file, and `start` refuses a zero-node graph
before any clone (FR-010's cheap half lives in the CLI too). Roadmap:
render marks `landed` specs with drifted fingerprints as amended (computed
in the pure layer beside readiness); the pre-dispatch derivation activity
calls the delta path — same input, same refusal rendering. Docs: decision
number claimed, remainder-file supersession recorded, runbook trim step
deleted.

Trap: drift detection on every render shells `git show` per landed story —
fine for ten specs, but batch the log scan (one pass, all specs) rather
than per-spec invocations, or render latency grows quadratically with the
corpus. The reader takes the batch shape from day one.

## Complexity Tracking

None. No new dependency, no store, no workflow-type change, no interpreter
change — two pure modules, two CLI verbs, one activity call swapped, one
render column.
