# Tasks: Delta Derivation

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution I): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written
in any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm 009 has landed on the target's default branch
      (this spec's frontmatter edge); re-verify plan.md's reuse inventory —
      the attribution grammar against `git log` on the current default
      branch (all landed-story subjects still `<epic>/<node>: <STORY>
      (#PR)`), `prepare_landing_pr`'s title construction
      (`factory/activities/merge_activities.py:301-307`), the deriver and
      criteria parser line refs, and 009's pre-dispatch derivation activity
      seam. **Commit the two 2026-08-07 remainder files into
      `tests/fixtures/` now** (`specs/007-parallel-dispatch/
      workgraph-remainder.json`, `specs/009-roadmap-scheduler/
      workgraph-remainder.json`) — they are untracked, they are SC-002's
      only ground truth, and a `git clean` erases them forever. Correct the
      plan before deriving, not the nodes after.

---

## Phase 2: User Story 1 — Landed facts are computed from the repo (Priority: P1) 🎯 MVP

**Goal**: per-story landed facts from default-branch attributions (latest
wins, attestation fallback) and fingerprints pinned at any revision.

**Independent Test**: fixture repos with scripted histories yield the right
facts; unattributed commits are invisible; fingerprints at a revision match
that revision's file, never the working tree.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green; `factory/workgraph/derive.py`, `factory/verify/criteria.py`,
      `factory/roadmap/models.py` exist and plan.md's inventory claims hold —
      constitution I gate; STOP and report blocked if not satisfied.
- [ ] T003 [P] [US1] Write landed-facts cases FIRST against fixture repos
      built per-test (the worktree tests' repo-building style): an
      attributed commit yields its story landed at that commit; unattributed
      subjects contribute nothing; a story attributed twice reports the
      newer commit; stories with no attribution report unlanded; the scan is
      one `git log` pass batched across specs (plan.md § US3 trap — the
      batch shape exists from day one) — must fail.
- [ ] T004 [P] [US1] Write attestation-baseline cases FIRST: a spec with
      frontmatter `state: landed` and zero attributed commits baselines
      every story at the commit that introduced the attestation, marked
      attested; provenance distinguishes attested from observed; a spec
      neither attested nor attributed yields an empty baseline — must fail.
- [ ] T005 [P] [US1] Write fingerprint cases FIRST: fingerprint at a
      revision equals the criteria parser's reading of `git show
      <rev>:...spec.md` (scenarios + implemented FR bodies + work-graph
      declaration); a working-tree edit never changes a pinned fingerprint;
      whitespace reflow changes nothing while a scenario edit, an FR-body
      edit, and a declaration edit each change it; a spec file absent at the
      revision refuses with a named finding — must fail.

### Implementation for User Story 1

- [ ] T006 [US1] Implement `factory/workgraph/landed.py` (facts scan with
      anchored subject regex, attestation fallback, batch shape,
      `Fingerprint` with structural hash, `_git`-helper discipline) until
      T003, T004, T005 pass.

---

## Phase 3: User Story 2 — Derivation subtracts what already landed (Priority: P1)

**Goal**: the pure delta function — full derive, subtract unchanged-landed
with provenance, re-open amended, refuse broken identity, empty baseline =
full graph.

**Independent Test**: corpus fixtures drive every rule; the 007 and 009
splits replay to their hand-trimmed remainders.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T007 [P] [US2] Write delta-rule cases FIRST against corpus fixtures
      (`tests/fixtures/README.md` convention): empty baseline equals
      `derive_workgraph` node-for-node (ids, edges, requirement keys);
      unchanged-landed subtracts with satisfied-edge provenance naming the
      landing commit; a changed scenario, changed implemented-FR body, and
      changed declaration each re-open their story with the structural diff
      quoted in provenance; edges are satisfied by removal only — never
      re-targeted (plan.md § US2 trap); prose-only edits yield an empty
      delta reported as success — must fail.
- [ ] T008 [P] [US2] Write identity-guard cases FIRST: a landed story absent
      from the current spec refuses naming it; a landed story number
      carrying unclassifiable content refuses; refusals are collected
      all-at-once through the deriver's `Rejection` types and nothing is
      emitted — must fail.
- [ ] T009 [P] [US2] Write the replay cases FIRST (SC-002): the 007 split
      (us1/us2 landed, us3/us4/us5 not) computes to the committed
      2026-08-07 remainder fixture node-for-node and edge-for-edge; same for
      the 009 split (us1 landed, us2/us3 not) — must fail.

### Implementation for User Story 2

- [ ] T010 [US2] Implement `factory/workgraph/delta.py` (`derive_delta`,
      `DeltaResult` with provenance, subtraction and satisfaction, identity
      guard, existing-schema serialization) until T007, T008, T009 pass.

---

## Phase 4: User Story 3 — The roadmap reconciles instead of ignoring (Priority: P2)

**Goal**: `landed` and delta CLI verbs; amended rendering; dispatch through
the delta path universally; zero-node dispatch refused; docs and decision
recorded.

**Independent Test**: scripted-children dispatch tests — remainder on
re-ready, delta on amended-then-readied, byte-compatible fresh dispatch;
render shows amended distinctly.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T011 [P] [US3] Write CLI cases FIRST driving `main(argv)`:
      `factory-epic landed <spec>` renders facts deterministically
      (observed vs attested marked); delta derivation writes
      `workgraph.json` through the existing schema and prints provenance;
      an empty delta exits 0 with a message and writes nothing; `start` on
      a zero-node graph refuses before any clone or key issuance; exit
      codes 0/1/2 per the existing contract — must fail.
- [ ] T012 [P] [US3] Write roadmap cases FIRST: render marks a landed spec
      with drifted fingerprints as amended, distinct from `landed` and
      `ready`, computed read-only; an amended spec does not dispatch until
      `state: ready`; with scripted children, a re-readied partially-landed
      spec dispatches exactly its computed remainder under the
      reuse-on-closed id, and a fresh spec's dispatched graph is identical
      to the pre-delta path (FR-006/SC-005) — must fail.

### Implementation for User Story 3

- [ ] T013 [US3] Implement the CLI verbs in `factory/workgraph/cli.py` until
      T011 passes.
- [ ] T014 [US3] Implement roadmap drift rendering and swap the pre-dispatch
      derivation activity to the delta path (signature unchanged, refusals
      rendered identically) until T012 passes.
- [ ] T015 [US3] Final sweep + docs: claim the decision-log number in
      `docs/decisions.md` (the corpus declares, the branch testifies, the
      delta is computed) recording the remainder-graph supersession
      (FR-011); cross-reference the attribution contract in
      `merge_activities.py` and `landed.py`; delete the hand-trim step from
      any runbook text; extend `docs/architecture.md`'s module table;
      confirm no new dependency and no store.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything — including preserving the
  remainder fixtures this spec's ground truth depends on.
- Phase 2 (US1) has no dependency and is the MVP seam: story-level landed
  facts with pinned fingerprints.
- Phase 3 (US2) imports US1's modules — merged, not passed.
- Phase 4 (US3) imports both and touches the roadmap — merged, sequential.

## Implementation Strategy

US1+US2 bank the value even if US3 is cut: the operator runs the delta verb
by hand and stops trimming remainders the day US2 lands. US3 makes the
roadmap honest about amendment and unifies dispatch. Nothing modifies the
epic interpreter — the delta is a compiled workgraph the interpreter runs
exactly as it runs a full one, which is what keeps this spec buildable by
the factory it reconciles.
