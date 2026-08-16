# Tasks: 047-durable-salvage

Three stories, chained on merge-edges: US1 → US2 → US3. Work test-first and
commit once per task. Read plan.md before the first commit — trap 2 (the gc
control is pinned alive by the remote-tracking ref US1 creates) and trap 5 (the
idempotency short-circuit at `factory/workgraph/worktree.py:396` skips your
mirror) are the two that cost a rejected attempt each if met late.

Every test in every phase lives in `tests/test_worktree.py` unless a task says
otherwise, and uses the fixture remote that file already has — `origin_repo` at
`tests/test_worktree.py:770`, a bare repository inside `tmp_path`. No test in
this spec may touch a real remote (plan trap 3).

## Phase 1: User Story 1 — A salvage commit leaves the machine that made it

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] Write the mirror case FIRST: salvage a node in a target
      clone whose `origin` is the `origin_repo` bare remote, and assert the node
      branch exists there at the sha salvage returned — the assertion shape is
      `ref_exists(bare, …)` then `head(bare, …)`, copied from
      `tests/test_worktree.py:786` (spec US1-S1, SC-001) — must fail.
- [ ] T002 [P] [US1] Write the no-remote case: a target clone with no `origin`
      at all salvages normally, returns the sha, raises nothing, and reports the
      absent remote as the reason (spec US1-S2, FR-002, SC-003). The precedent
      that a remote-less clone is a supported target is
      `tests/test_worktree.py:314` — must fail.
- [ ] T003 [P] [US1] Write the broken-remote case: `origin` pointing at a path
      that does not exist still salvages, still returns the sha, raises nothing,
      and the reported reason carries git's own stderr rather than a paraphrase
      (spec US1-S3, FR-002, plan trap 8) — must fail.
- [ ] T004 [P] [US1] Write the retry case: the same attempt salvaged twice
      against a clean tree adds no commit, leaves the remote unchanged, and
      reports the second mirror a success — this is the path
      `worktree.py:396` short-circuits, so the test fails if the mirror sits
      inside the commit branch (spec US1-S4, plan trap 5) — must fail.
- [ ] T005 [P] [US1] Write the landing-branch refusal: a node whose branch name
      is the target's declared landing branch is not pushed, the refusal names
      that branch, and the salvage commit is still made — assert the bare
      remote's landing branch is exactly where it was (spec US1-S5, FR-003;
      reuse the guard at `worktree.py:444-449`, do not restate it) — must fail.
- [ ] T006 [US1] Write the control FIRST, against the disable-seam: with the
      mirror off, the T001 worktree's branch does **not** reach the bare remote
      (spec US1-S6, SC-004). This is the test that proves the mirror is doing
      the work; ask plan trap 1's question of it before you write the
      implementation.
- [ ] T007 [P] [US1] In `tests/test_agent_activities.py`, assert
      `salvage_worktree` still returns the salvage commit sha as a plain `str`
      (spec US1-S7, FR-005) — must pass before and after; it pins the payload
      contract.

### Implementation for this story

- [ ] T008 [US1] Add the mirror to `factory/workgraph/worktree.py` beside
      `push_branch` (`:416`), per plan.md's route choice — prefer a new
      function over changing `salvage`'s return type. Every git call goes
      through the existing `_git` runner (`:827`); reuse `_has_remote` (`:907`);
      never `--force` (FR-004); an explicit disable-seam for T006, never an
      environment read.
- [ ] T009 [US1] Call it from the `salvage_worktree` activity
      (`factory/activities/agent_activities.py:561`) after `worktrees.salvage`,
      catching `WorktreeError` at the mirror boundary so it never reaches the
      `ApplicationError(WORKTREE_FAILED)` conversion at `:578-579` (FR-002,
      plan trap 8). The activity's return type stays `str` and
      `SalvageWorktreeInput` (`:543`) gains no field (FR-005, plan trap 6).
- [ ] T010 [US1] Confirm no `execute_activity` was added to
      `factory/workgraph/workflow.py` — the three salvage call sites (`:1319`,
      `:2019`, `:2534`) and `open_landing_pr`'s push
      (`factory/activities/merge_activities.py:371`) are read, not edited
      (FR-005, FR-012, plan traps 6 and 11).

## Phase 2: User Story 2 — Every recorded per-attempt salvage sha still resolves

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] Write the ref case FIRST: after attempt 1's salvage, a
      per-attempt ref naming epic, node and attempt resolves to exactly the sha
      salvage returned (spec US2-S1, FR-006) — must fail.
- [ ] T012 [US2] Write the survival case FIRST: salvage attempt 1, rewrite the
      branch in its worktree with `git commit --amend` (the rewrite
      `028-epic-relaunch-reset/us3` actually performed), then
      `git reflog expire --expire=now --all` and `git gc --prune=now` against
      the repository, and assert attempt 1's sha still resolves (spec US2-S2,
      plan probe 2) — must fail.
- [ ] T013 [US2] Write the control FIRST, against the ref seam: the identical
      amend-then-gc sequence with the per-attempt ref suppressed must leave the
      sha **unresolvable** (spec US2-S3, SC-002). Build it in a clone with no
      remote, or delete `refs/remotes/origin/<branch>` first — a remote-tracking
      ref written by US1's push keeps the object alive and turns this control
      into a test that cannot fail (plan trap 2).
- [ ] T014 [P] [US2] Write the clean-retry case: an attempt salvaged twice
      against a clean tree leaves exactly one ref for that attempt, unmoved
      (spec US2-S4) — must fail.
- [ ] T015 [P] [US2] Write the dirty-re-salvage case: an attempt salvaged twice
      with the worktree dirtied in between — the path
      `worktree.py:387-389` deliberately permits — leaves **both** commits named
      by refs, neither reachable from zero refs (spec US2-S5, FR-007) — must
      fail.
- [ ] T016 [P] [US2] Write the mirrored-refs case: against the `origin_repo`
      bare remote, the per-attempt refs are present on the remote too (spec
      US2-S6, FR-008) — must fail.
- [ ] T017 [P] [US2] Write the refusing-remote case: a fixture remote that
      rejects the ref namespace leaves the salvage commit made, the local ref
      written, nothing raised, and the refusal reported (spec US2-S7, FR-002,
      FR-008, plan trap 3) — must fail.
- [ ] T018 [P] [US2] Write the empty-salvage case: an attempt that produced
      nothing gets a per-attempt ref exactly as a dirty one does (spec US2-S8,
      FR-011, plan trap 4) — must fail.

### Implementation for this story

- [ ] T019 [US2] Write the per-attempt ref at salvage time, in the target
      repository's shared ref store, per plan.md's route choice — prefer a name
      that embeds the commit's short sha so the write is idempotent by
      construction and FR-007 needs no move-or-refuse rule. `git update-ref`
      from inside the worktree reaches the shared store (plan probe 1). Do not
      copy `_archive_node`'s refuse-to-overwrite guard (`worktree.py:816`): it
      raises, and constitution VI forbids raising here.
- [ ] T020 [US2] Extend the mirror from T008 to carry the per-attempt refs,
      degrading exactly as FR-002 requires when the remote refuses the
      namespace (FR-008).
- [ ] T021 [US2] Confirm `_archive_node` (`worktree.py:775`) and `reset`
      (`:652`) are unchanged — per-attempt refs are independent of the branch
      and survive both untouched (plan trap 11).

## Phase 3: User Story 3 — An operator can ask what a terminated node left behind

### Tests for this story (write FIRST, must fail)

- [ ] T022 [US3] Write the report case FIRST, in `tests/test_ergane_build.py`:
      a compiled work graph plus a target clone holding a terminated node's
      branch and two per-attempt refs, and the verb's output names the branch,
      its tip sha and subject, and one line per attempt ref with that attempt's
      sha and subject (spec US3-S1) — must fail.
- [ ] T023 [P] [US3] Write the never-dispatched case: a node with no branch and
      no refs is reported as having left nothing, exit 0 (spec US3-S2, FR-010)
      — must fail.
- [ ] T024 [P] [US3] Write the off-machine case: one node's branch on the bare
      fixture remote and one only local, each labelled accordingly (spec
      US3-S3, FR-009) — must fail.
- [ ] T025 [P] [US3] Write the no-remote case: a target clone with no remote
      reports the off-machine question as unanswered, exit 0, never an error
      (spec US3-S4, FR-010) — must fail.
- [ ] T026 [US3] Write the read-only case: capture the target repository's full
      ref list and `git worktree list` before and after the verb and assert they
      are identical (spec US3-S5, FR-009). `git fetch` is forbidden — it writes
      tracking refs (plan route choice) — must fail if the verb writes anything.
- [ ] T027 [P] [US3] Write the no-Temporal case: the verb answers with no
      Temporal server reachable, and the code path opens no connection (spec
      US3-S6, FR-010, SC-005) — must fail.

### Implementation for this story

- [ ] T028 [US3] Add the verb handler to `factory/cli/nouns/build.py`, shaped
      like `reset_command` / `_reset_epic` (`:590`, `:600`): take a compiled
      work graph, loop `graph.nodes`, read git through `worktree.py`, print one
      block per node. No Temporal client, no writes (FR-009, FR-010).
- [ ] T029 [US3] Register it beside the `reset` verb at
      `factory/cli/nouns/build.py:812-817` — `commands.add_parser(...)` then
      `set_defaults(run=…)`. `NOUN` at `:820` needs no edit, and no new noun is
      added: `ergane status` (`factory/cli/status.py:199`) is the live floor and
      `ergane spec landed` (`factory/workgraph/cli.py:154`) is landings, and
      neither can answer for a terminated epic.

## Verification

- [ ] Every existing `test_salvage_*` (`tests/test_worktree.py:466` onward) and
      every push test (`:409`, `:786`, `:805`, `:822`, `:839`) passes unchanged
      — the parity half, FR-012 and SC-006.
- [ ] Final gate command passes green.
