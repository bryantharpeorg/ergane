# Tasks: A one-commit PR must not land under a salvage subject

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip — except where a
task's own text says it is a standing guard that fails only on over-reach.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      hosts the work, and record the answers here. Four claims in particular,
      because each is load-bearing: that `evaluate_repo`
      (`factory/mergequeue/onboard.py:45`) still takes keyword-only facts and
      still orders repo-health findings before the gate↔check mapping; that
      `_fake_gh_conforming` (`tests/test_merge_activities.py:493`) still scripts
      exactly two calls (`repo view` and the rules read), because trap 6's
      instruction — add the settings expectation to every scripted onboarding
      test — turns on knowing what each script contains; that the worker host's
      `gh repo view --json` field roster still lacks `squashMergeCommitTitle`
      (trap 2 — if a gh upgrade added it, the plan's REST route still works but
      the trap's rationale should be corrected in the dispatch note); and that
      `test_salvage_subject_is_not_a_landing` (`tests/test_landed.py:214`) is
      still the salvage-refusal negative table US1-S5 extends.
- [ ] T002 Operator, before this epic dispatches: read the live setting with
      `gh api repos/bryantharpeorg/ergane --jq .squash_merge_commit_title` and
      confirm `PR_TITLE` (spec SC-002); only if it has regressed, run
      `gh api -X PATCH repos/bryantharpeorg/ergane -f squash_merge_commit_title=PR_TITLE`
      and read it back. Verified 2026-08-11 at spec-verification time: the read
      already returned `PR_TITLE` — the repo was corrected sometime after the
      2026-08-09 incident — so expect a confirmation, not a change. Sequencing
      is still the point: this epic's own story could come back as a one-commit
      PR, and under a regressed setting it would land under a salvage subject —
      this finding reproducing itself on its own fix. On the first one-commit
      landing after this check, confirm the merge subject on the landing branch
      is the PR title.

---

## Phase 2: User Story 1 — Onboarding refuses a repo that titles squash merges from commits (Priority: P1)

**Goal**: `ergane repo onboard` and the epic-start onboarding gate fail any
target repo whose `squash_merge_commit_title` is not `PR_TITLE`, with the
remedy in the finding's detail — and the landing reader's refusal of salvage
subjects is untouched and re-proved against PR #28's real subject.

**Independent Test**: table-test `evaluate_repo` in all three postures
(conforming, non-conforming, unreadable); drive `onboard_target_repo` through a
scripted `FakeGh` both ways; run `landed_facts` over a history carrying PR
#28's verbatim subject and its epic-anchored twin and see nothing land.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T003 [US1] Write the pure table cases FIRST, in `tests/test_onboard.py`:
      `evaluate_repo` with `squash_merge_commit_title="PR_TITLE"` on an
      otherwise conforming repo passes, with a passing `squash_title` finding
      present (spec US1-S1); with `"COMMIT_OR_PR_TITLE"` the profile fails and
      the finding's detail names the observed value and the exact remedy call
      `gh api -X PATCH repos/<owner_repo> -f squash_merge_commit_title=PR_TITLE`
      (spec US1-S2); with the argument omitted or `None` the finding fails
      closed with a detail naming the likely cause — plan.md trap 3, never a
      pass by default (spec US1-S3). These fail today with `TypeError`: the
      parameter does not exist yet — must fail.
- [ ] T004 [P] [US1] Write the scripted-gh activity cases FIRST, in
      `tests/test_merge_activities.py`: extend `_fake_gh_conforming` with the
      new settings expectation
      (`expect_json("api", "repos/OWNER/REPO", payload={"squash_merge_commit_title": "PR_TITLE"})`)
      and assert a conforming repo still passes end to end through
      `validate_target_repo` (spec US1-S1); a payload carrying
      `"COMMIT_OR_PR_TITLE"` fails the profile on the `squash_title` finding
      (spec US1-S2); a payload omitting the key fails closed (spec US1-S3); and
      an `expect_error` on the settings call yields a failed profile through
      the existing `_profile_from_gh_failure` path — never a pass (spec
      US1-S4). Per plan.md trap 6, add the settings expectation to every other
      scripted onboarding test this breaks — `FakeGh` raising on the unplanned
      call is the seam working, not a fixture bug — must fail.
- [ ] T005 [P] [US1] Write the salvage-refusal guard FIRST, in
      `tests/test_landed.py` beside `test_salvage_subject_is_not_a_landing`:
      a history carrying both the verbatim
      `salvage(021-roadmap-operability/us4): completed attempt 1 (#28)` — the
      ` (#28)` suffix included, which the existing negatives do not cover —
      and `salvage(016-delta-derivation/us1): completed attempt 1 (#28)`, the
      same suffixed shape anchored to the epic the fixture scans (`EPIC_ID` is
      `016-delta-derivation`, `repo_builder` hardcodes that spec dir, and the
      spec must declare US1), produces no landing for any story (spec US1-S5,
      FR-005). The anchored twin is the load-bearing half: the 021 subject is
      refused by the epic anchor alone, so only the twin goes red if the
      reader ever learns salvage subjects (plan.md trap 1). This is a standing
      guard in 010's T007 tradition: it passes immediately against today's
      reader and exists to catch the forbidden inverse fix. Say exactly that
      in its docstring — must fail only if the implementation over-reaches.

### Implementation for User Story 1

- [ ] T006 [P] [US1] In `factory/mergequeue/gh.py`, add the `GhClient` method
      `merge_settings(self, owner_repo: str) -> dict[str, Any]` under the US3
      onboarding section, calling `_run_json("api", f"repos/{owner_repo}")` and
      raising `GhError(GH_REFUSED, ...)` on a non-dict shape —
      `classic_branch_protection` at `:224` is the template (plan.md trap 2:
      REST, because `gh repo view --json` cannot express this setting). Until
      T004's conforming case can pass.
- [ ] T007 [P] [US1] In `factory/mergequeue/onboard.py`, give `evaluate_repo`
      the keyword `squash_merge_commit_title: str | None = None` and append a
      `_squash_title_finding` right after `_queue_finding`: pass iff the value
      is exactly `"PR_TITLE"`; fail otherwise, the detail naming the observed
      value (or that the setting was unreadable — plan.md trap 3) and the
      verbatim one-call remedy. Update the module docstring's check roster,
      which enumerates every check. Until T003 passes.
- [ ] T008 [US1] In `factory/activities/merge_activities.py`, have
      `onboard_target_repo` read `merge_settings(owner_repo)` inside the same
      `GhError`-guarded discipline as the rules read (a failed read routes to
      `_profile_from_gh_failure`, reused as-is, never modified), extract
      `squash_merge_commit_title` as `str | None` with no default value
      substituted, and pass it through to `evaluate_repo`. The setting is
      repo-scoped: do not touch `_queue_from_rules` or the classic-protection
      fallback (plan.md trap 4). Until T003–T005 all pass and the full suite is
      green, with `factory/workgraph/landed.py` and
      `factory/workgraph/worktree.py` untouched by the diff (spec SC-004).
- [ ] T009 [US1] Final sweep + docs: `docs/decisions.md` gains a numbered entry
      claimed at landing — target repos must title squash merges from the PR
      title (`squash_merge_commit_title=PR_TITLE`), onboarding enforces it as a
      failing finding from now on, and the landing grammar's parse end stays
      exactly as 020 left it: salvage subjects are refused, now proved against
      the one that actually merged. Confirm no new dependency, no new activity,
      no new store.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything. T002 in particular precedes
  dispatch: it is the half of the fix that protects this epic's own landing,
  and it needs no code.
- Phase 2 is the only story. Within it, T003/T004/T005 are disjoint files and
  parallel-safe; T006 and T007 are disjoint files; T008 wires both and comes
  last before the sweep.

## Implementation Strategy

The story is one fact threaded through three layers that all have worked
examples an arm's reach away: a REST read shaped like `classic_branch_protection`,
a finding shaped like `_queue_finding`, and a gather shaped like the rules read
it sits beside. The risk is not in the new code but in the two seams trap 6
names — the strict `FakeGh` scripts and the fail-closed default — and in the
standing temptation trap 1 forbids. The diff touches onboarding and its tests
only; the landing reader's files show no change, and T005 is the proof that
their behavior did not either.
