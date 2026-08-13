# Tasks: The names an operator types

Three stories, strictly serial — each chains on the previous **merged**, because
US2 moves live state and US3 edits the fixture that keeps the suite off the
operator's store. Work test-first within a story and commit once per task.

## Format: `[ID] [P?] [Story] Description`

Read `plan.md` first. Trap 1 is why this is not a `sed`, trap 4 fences what you
must not rename, and trap 8 says the migration transcript is a deliverable
rather than a step you performed.

## Phase 1: User Story 1 — The manifest is `ergane.yaml` (Priority: P1) 🎯 MVP

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T001 [US1] Write the resolution cases FIRST in the manifest parser's test
      file: a fixture repo with only `ergane.yaml` loads (spec US1-S1); one with
      only `factory.yaml` loads and reports a deprecation naming the file (spec
      US1-S2); one with both loads the new name and names the ignored file (spec
      US1-S3). Use `tmp_path` repos, never a real checkout.

- [ ] T002 [US1] Write the no-literals guard FIRST (spec US1-S4, FR-004),
      copying the shape of `test_no_code_path_passes_delete_branch` in
      `tests/test_gh_client.py`: scan the source of the modules that read the
      manifest and assert the literal `"factory.yaml"` appears in none of them.
      It must fail now — there are three such sites (plan trap 1).

- [ ] T003 [US1] Write the fence FIRST (spec US1-S5, FR-010): assert the
      `factory_yaml` finding key still appears in `evaluate_repo`'s output. That
      key is how the ledger counts recurrence; renaming it would silently reset
      the history that decides constitution promotions (plan trap 2).

### Implementation for User Story 1

- [ ] T004 [US1] Add the resolver to `factory/verify/factory_yaml.py`: preferred
      name `ergane.yaml`, legacy `factory.yaml`, returning the path and which
      name matched. Keep the parse itself untouched — only path discovery
      changes.

- [ ] T005 [US1] Route every reader through it: the three literal sites
      (`merge_activities.py:612`, `onboard.py:161`, `onboard.py:165`) and the
      constant user (`agent_activities.py:666`). T002 goes green here.

- [ ] T006 [US1] Emit the deprecation ONCE per command, not once per read (plan
      trap 7) — these resolvers are called on every activity, and a per-read
      warning trains the operator to ignore it.

- [ ] T007 [US1] Full suite green: `uv run pytest -q`. Confirm the diff renames
      no module and no branch prefix (plan trap 4).

## Phase 2: User Story 2 — The runtime root is `.ergane/` (Priority: P1)

Chains on US1 merged. **This story moves live state — read plan trap 3 before
writing anything.**

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T008 [US2] Write root resolution FIRST: no root → creates `.ergane/` (spec
      US2-S1); legacy root only → uses it and names the migration command (spec
      US2-S2). Tmp roots only; 030's store guard refuses a real path under
      pytest and you must not lean on that as your safety net.

- [ ] T009 [US2] Write the migration cases FIRST: a populated legacy root with a
      verification store containing rows migrates with identical row counts
      (spec US2-S3); a second run reports already-migrated and moves nothing
      (spec US2-S4); a run with an epic in flight refuses naming the epic (spec
      US2-S5, FR-006 — use the existing capacity read, not a new mechanism).

### Implementation for User Story 2

- [ ] T010 [US2] Turn `DEFAULT_FACTORY_ROOT` (`worktree.py:75`) into a two-name
      resolver reporting which it chose, and route the five resolution sites
      through it (`agent_activities.py:163`; `merge_activities.py:310`, `:374`,
      `:485`; `cli/nouns/build.py:556`).

- [ ] T011 [US2] Implement the migration as an operator command. Put it under
      the existing `repo` noun or under `doctor` — either is fine, but say which
      and why in the commit message. Do not bury it inside an unrelated verb.

- [ ] T012 [US2] Produce the FR-007 evidence and COMMIT IT (plan trap 8): run
      the migration against a populated tmp root, capture the verification and
      usage row counts before and after, and paste both verbatim into a comment
      block in the test file. A migration that loses rows can leave a green
      suite if nothing counts them.

- [ ] T013 [US2] Full suite green: `uv run pytest -q`.

## Phase 3: User Story 3 — The environment variables are `ERGANE_*` (Priority: P2)

Chains on US2 merged.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T014 [US3] Write the four honored-name cases FIRST (spec US3-S1), the
      legacy-with-one-deprecation case (spec US3-S2), and the conflict case where
      the new name wins and both are named (spec US3-S3).

- [ ] T015 [US3] Write the fixture-parity assertion FIRST (spec US3-S4, plan
      trap 5): whatever variable names the engine now reads, 030's
      `_isolated_test_store` fixture in `tests/conftest.py` sets them. A rename
      that leaves that fixture pointing at dead variables re-opens the live-store
      leak 030 closed, and it would do so silently.

### Implementation for User Story 3

- [ ] T016 [US3] Add `ERGANE_ROOT`, `ERGANE_VERIFICATION_DB_PATH`,
      `ERGANE_LEDGER_PATH` and `ERGANE_EVIDENCE_STORE_ALLOW_REAL` alongside the
      `FACTORY_*` names; new wins, one deprecation per command (plan trap 7).

- [ ] T017 [US3] Update `scripts/ergane-env.sh` to export the new names, and
      update the conftest fixture to set both old and new — a partially migrated
      tree must not leak (FR-009).

- [ ] T018 [US3] Full suite green: `uv run pytest -q`, and confirm the live
      evidence store still holds the rows it held before (SC-003).

## Verification

- [ ] Final gate command passes green.
- [ ] The migration transcript is in the diff, verbatim, with before/after counts.
- [ ] No module renamed, no branch prefix changed, `factory_yaml` key intact.
