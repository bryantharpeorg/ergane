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

- [ ] T001 Operator: **done 2026-08-07/08, recorded here as the gate's
      evidence rather than as pending work.** 009 has landed on the default
      branch (frontmatter edge satisfied). The two 2026-08-07 remainder files
      are banked byte-verbatim at `tests/fixtures/remainders/` with provenance
      in `tests/fixtures/README.md` (commit `8d57b86`) — T009 replays against
      *those* paths, not the untracked originals beside the specs. plan.md's
      reuse inventory was re-verified against the tree and corrected: the
      attribution grammar is rendered by `pr_title`
      (`factory/mergequeue/messages.py`), **not** `prepare_landing_pr`, which
      merely calls it — so FR-011's "two ends of one contract" cross-reference
      belongs in `messages.py`. The attribution scan itself found the defect
      FR-002 now handles: `5f6aef1` (`009-roadmap-scheduler/us1: US1 (#8)`) is
      unreachable from the default branch after the 009 recovery rewrite, so
      ten of eleven landed stories are attributed, not eleven.

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
- [ ] T004 [P] [US1] Write attestation-baseline cases FIRST, **per story, not
      per spec**: a spec attested `state: landed` with zero attributed commits
      baselines every story at the attesting commit, marked attested;
      provenance distinguishes attested from observed; a spec neither attested
      nor attributed yields an empty baseline; and the mixed case — attested
      `state: landed` where some stories have reachable attributed commits and
      others do not — resolves per story, the attributed ones keeping their own
      commits and the gaps falling back to the attesting commit. Include the
      real shape as a fixture: an attributing commit made unreachable by a
      branch rewrite while its content remains (009/us1). A spec-level
      all-or-nothing fallback must fail this case — must fail.
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
      (us1/us2 landed, us3/us4/us5 not) computes to
      `tests/fixtures/remainders/007-parallel-dispatch-remainder.json`
      node-for-node and edge-for-edge — the operator deleted three `us1`
      edges there, one on each remaining story; same for the 009 split
      (us1 landed, us2/us3 not) against
      `tests/fixtures/remainders/009-roadmap-scheduler-remainder.json`, which
      keeps `us3 depends_on_merged us2`. Note 009's replay exercises FR-002's
      per-story fallback, since us1's attribution is unreachable — must fail.

### Implementation for User Story 2

- [ ] T010 [US2] Implement `factory/workgraph/delta.py` (`derive_delta`,
      `DeltaResult` with provenance, subtraction and satisfaction, identity
      guard, existing-schema serialization) until T007, T008, T009 pass.

---

## Phase 4: User Story 3 — The operator can compute a delta by hand (Priority: P2)

**Goal**: the `landed` and delta CLI verbs, plus `start`'s zero-node refusal.
Owns `factory/workgraph/cli.py` and its tests, nothing else.

**Independent Test**: `main(argv)` drives both verbs against fixture repos with
the documented exit codes; `start` refuses a zero-node graph before Temporal.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T011 [P] [US3] Write CLI cases FIRST driving `main(argv)`:
      `factory-epic landed <spec>` renders facts deterministically
      (observed vs attested marked); delta derivation writes
      `workgraph.json` through the existing schema and prints provenance;
      an empty delta exits 0 with a message and writes nothing; `start` on
      a zero-node graph refuses before connecting to Temporal or issuing any
      key; exit codes 0/1/2 per the existing contract — must fail.

### Implementation for User Story 3

- [ ] T012 [US3] Implement the CLI verbs in `factory/workgraph/cli.py`,
      including `start`'s zero-node refusal, until T011 passes. Nothing today
      validates non-empty `nodes` — the model's checks are per-node — so the
      refusal is genuinely new behaviour, not a tightening.

---

## Phase 5: User Story 4 — The roadmap reconciles instead of ignoring (Priority: P3)

**Goal**: amended rendering, dispatch through the delta path universally, and
the decision-log entry. Owns the roadmap layer and docs; does **not** touch
`factory/workgraph/cli.py` (US3's file).

**Independent Test**: scripted-children dispatch tests — remainder on
re-ready, delta on amended-then-readied, byte-compatible fresh dispatch;
render shows amended distinctly.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T013 [P] [US4] Write roadmap cases FIRST: render marks a landed spec
      with drifted fingerprints as amended, distinct from `landed` and
      `ready`, computed read-only; an amended spec does not dispatch until
      `state: ready`; with scripted children, a re-readied partially-landed
      spec dispatches exactly its computed remainder under the
      reuse-on-closed id, and a fresh spec's dispatched graph is identical
      to the pre-delta path (FR-006/SC-005) — must fail.

### Implementation for User Story 4

- [ ] T014 [US4] Implement roadmap drift rendering and swap the pre-dispatch
      derivation to the delta path. Two constraints the plan spells out:
      `derive_spec`'s signature already carries `target_repo`, so the swap
      needs no new argument, but the activity stops being pure once it reads
      git; and drift facts must reach the *workflow* through the injected
      resolver seam readiness already uses (or a new activity) — a workflow
      may not shell git. The zero-node refusal here is at child-epic start,
      after the clone the delta needs, not before it. Until T013 passes.
- [ ] T015 [US4] Final sweep + docs: claim the decision-log number in
      `docs/decisions.md` (the corpus declares, the branch testifies, the
      delta is computed) recording the remainder-graph supersession
      (FR-011); cross-reference the attribution contract between
      `factory/mergequeue/messages.py`'s `pr_title` and `landed.py` — the
      renderer and the reader are the two ends of one contract; delete the
      hand-trim step from any runbook text; extend `docs/architecture.md`'s
      module table; confirm no new dependency and no store.

---

## Dependencies & Execution Order

- Phase 1 is operator work, already done, and its evidence gates everything.
- Phase 2 (US1) has no dependency and is the MVP seam: story-level landed
  facts with pinned fingerprints.
- Phase 3 (US2) imports US1's modules — merged, not passed.
- Phases 4 and 5 (US3, US4) both import US2's delta function — merged — and are
  **siblings, not a chain**: US3 owns the CLI module, US4 owns the roadmap layer
  and docs, and the file sets are disjoint. They are the natural
  `--max-concurrent-nodes 2` pair for this epic.

## Implementation Strategy

US1+US2 bank the value even if the last two stories are cut: the operator runs
the delta verb by hand and stops trimming remainders the day US2 lands. US3
makes that ergonomic; US4 removes the operator from the loop. Nothing modifies
the epic interpreter — the delta is a compiled workgraph the interpreter runs
exactly as it runs a full one, which is what keeps this spec buildable by
the factory it reconciles.
