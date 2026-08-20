# Tasks: the on-ramp proves itself end to end

**Spec**: `specs/061-the-on-ramp-proves-itself-end-to-end/spec.md`
**Plan**: `specs/061-the-on-ramp-proves-itself-end-to-end/plan.md`

Read the plan's **Traps** before the first task. Trap 1 is not a detail: this
spec is *about* the difference between asserting a declaration and asserting a
capability, and it is entirely possible to fix three bugs here while rebuilding
the shape that caused them.

**Trap 14 has already killed this epic twice and will kill it again.** Any
fixture that runs `git commit` in a scratch repository MUST set `user.email` and
`user.name` on that repository explicitly. Your sandbox HOME is seeded with a
`.gitconfig` so it passes in front of you; a CI runner has no git identity and
`git commit` exits 128. On 2026-08-19 that one line lost `us2`, and `us3` and
`us4` died with it at attempt 0 having never run — twice. Read trap 14 in full
before writing any test that touches git.

Tests are written before the implementation and must fail for the stated reason
before anything is made to pass.

Edges: US2 → US3 (both edit `factory/cli/init.py`). US4 depends on US1, US2 and
US3, and on specs 059 and 060 having landed.

## Phase 1: User Story 1 — Verification proves the gateway can mint a key

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) Drive `LLMProbe` through its injected seam against a
      simulated endpoint that answers `/v1/models` and `/v1/chat/completions`
      and 404s `/key/generate`; assert the `llm` check **fails** and that the
      message names key management and database backing.
- [ ] T002 [P] [US1] (spec US1-S2) Same seam, simulated fully-dispatchable endpoint; assert
      the check **passes** (trap 2).
- [ ] T003 [P] [US1] (spec US1-S3) Assert the probe mints, asserts, and revokes — and that
      revocation still happens when the intervening assertion raises (trap 3).
      Call `revoke_key_by_tokens` directly rather than `revoke_key`, which is
      currently defined twice (`factory/usage/litellm_client.py:246` and `:339`)
      until 064/US3 removes the dead one.
- [ ] T004 [P] [US1] (spec US1-S4) Assert the classification symbol is imported from
      `factory/discovery/llm_scanner.py`, not redefined.
- [ ] T005 [P] [US1] (spec US1-S5) Simulate a gateway minting an unconstrained key; assert
      the check fails naming the missing model constraint.
- [ ] T006 [P] [US1] (spec Edge Cases) Simulate `/key/generate` answering while
      `/spend/logs/v2` 404s; assert the failure names which endpoint failed.
- [ ] T007 [P] [US1] Assert 054/US3's per-distinct-alias behaviour survives: the number of
      completions equals the number of distinct aliases, not the number of
      personas, and the key work does not multiply per persona.

### Implementation for this story

- [ ] T008 [US1] (FR-001, FR-002, FR-003, FR-004) Extend `LLMProbe.gather`
      (`factory/controlplane/verify.py:296`) to mint a short-TTL key, assert its
      model constraint, and revoke it in a `finally`. Reuse the scanner's
      classification.
- [ ] T009 [US1] Write the failure message so it names the remedy, not only the defect:
      a config-only LiteLLM answers completions and 404s key management, and the
      usual cause is a proxy started without `DATABASE_URL`.

## Phase 2: User Story 2 — A fresh repository survives its first roadmap tick

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1) Assert `read_roadmap` on a **missing** root returns an
      empty roadmap.
- [ ] T011 [P] [US2] (spec US2-S2) Assert `read_roadmap` on an **existing empty** root
      returns an empty roadmap — the cell that already works and must keep
      working (trap 2).
- [ ] T012 [P] [US2] (spec US2-S3) Assert a **malformed** corpus still raises naming every
      fault, preserving the docstring's emits-nothing-on-failure discipline
      (traps 4, 5).
- [ ] T013 [P] [US2] (spec Edge Cases) Assert a root that exists but is a **file** is
      distinguished from all three above.
- [ ] T014 [P] [US2] (spec US2-S4) Assert `ergane init` creates `specs/` on a fresh
      repository.
- [ ] T015 [P] [US2] (spec US2-S5) Drive the roadmap workflow's read path against a
      freshly-initialised tree and assert the first tick completes rendering
      zero rows.

### Implementation for this story

- [ ] T016 [US2] (FR-005, FR-006) In `factory/roadmap/models.py:398`, check for the
      root's existence explicitly before `iterdir()`. Do not wrap it in a broad
      `except` — that would satisfy T010 and destroy T012 (trap 5).
- [ ] T017 [US2] (FR-007) Create `specs/` alongside the runtime root at
      `factory/cli/init.py:816`.
- [ ] T018 [US2] Update `read_roadmap`'s docstring to state that an absent root is an
      empty corpus and a malformed one still raises, so the next reader does not
      have to infer the distinction from the code.

## Phase 3: User Story 3 — A gate that cannot fail is named as one

### Tests for this story (write FIRST, must fail)

- [ ] T019 [P] [US3] (spec US3-S1, US3-S2) Parametrised over `true`, `:` and the empty string:
      assert `ergane init --check` reports a distinct no-op finding naming that
      no gate can fail.
- [ ] T020 [P] [US3] (spec US3-S3) Assert a real gate command still reports the existing
      pass, unchanged (trap 2).
- [ ] T021 [P] [US3] (spec US3-S4) Assert the no-op finding does not fail `--check` (trap 6).
- [ ] T022 [P] [US3] (spec US3-S5) Assert a freshly-initialised manifest does not declare
      `true` as a gate.

### Implementation for this story

- [ ] T023 [US3] (FR-008) Add no-op detection to `_gate_check_finding`
      (`factory/mergequeue/onboard.py:254`), emitting a distinct finding rather
      than the `required check '{gate}' exists` pass at :257.
- [ ] T024 [US3] (FR-009) Give the finding a severity that does not fail the run.
- [ ] T025 [US3] (FR-010) Remove or rename the gate entry in `_PLACEHOLDERS`
      (`factory/cli/init.py:273`) so a value the code calls a placeholder cannot
      become a live gate. Coordinate with 060's shared defaults source if 060 has
      landed.
- [ ] T026 [US3] Update the `gate_check:<gate>` contract documented at
      `factory/mergequeue/onboard.py:29` in the same diff.

## Phase 4: User Story 4 — The on-ramp is exercised end to end

### Tests for this story (write FIRST, must fail)

- [ ] T027 [P] [US4] (spec US4-S2) Assert each stage's failure is reported by stage name,
      driving a simulated failure at each stage in turn.
- [ ] T028 [P] [US4] (spec US4-S4) Assert the exercise skips with a message naming the
      missing prerequisite when live dependencies are absent. Prove the guard
      catches what the client actually raises — verify with
      `TEMPORAL_ADDRESS=127.0.0.1:1` (trap 8).
- [ ] T029 [P] [US4] (spec US4-S5) Assert every path the exercise writes lies beneath its own
      temporary root, and that it resolves no runtime root from the ambient
      environment (trap 9).
- [ ] T030 [P] [US4] (spec Edge Cases) Assert cleanup runs on the failure path as well as the
      success path.

### Implementation for this story

- [ ] T031 [US4] (FR-011, spec US4-S1) Build the exercise: `ergane install --from-file` →
      `ergane init --wire --non-interactive` → `ergane repo onboard` → dispatch a
      trivial epic → assert a landed pull request. Use 060's non-interactive
      flags; use 033's scripted-prompter harness as the staging model.
- [ ] T032 [US4] (FR-011, US4-S3) Make the final assertion a landed pull request read
      back from GitHub — never the exit status of the last command (trap 7).
- [ ] T033 [US4] (FR-012) Per-stage failure reporting, clean skip, and cleanup on both
      paths.
- [ ] T034 [US4] Document how to run the exercise and what it costs, so a maintainer
      can decide when to run it rather than discovering its cost by running it.

## Verification

- [ ] T035 (SC-001) Start LiteLLM with no `DATABASE_URL`; run `ergane install
      --verify`; confirm the `llm` check fails naming key management. Restart with
      a database; confirm it passes. **Paste both transcripts into the diff**
      (trap 11).
- [ ] T036 (SC-002) On a fresh `ergane init`, let three roadmap ticks run and confirm
      `ActionCounts` shows zero `SkippedOverlap`. Paste the output.
- [ ] T037 (SC-003) Run `ergane init` with defaults on a scratch repository, then
      `--check`, and confirm the gate is reported as a no-op.
- [ ] T038 (SC-004) Run the end-to-end exercise against a scratch organization-owned
      repository and confirm it lands a pull request with no human input. Paste
      the output naming the merged pull request.
- [ ] T039 (SC-005) Revert each of US1, US2 and US3's fixes in turn and confirm the
      US4 exercise fails each time. If it does not, US4 is not measuring the
      composition and is not done.
