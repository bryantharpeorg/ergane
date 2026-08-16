# Tasks: 051-first-run-defaults

Two stories, **independent** — neither `depends_on` nor `depends_on_merged`
connects them. The phases below are in reading order only; a higher phase number
does not mean your story waits on the one before it.

Work test-first and commit once per task. Read `plan.md` before the first
commit — trap 3 (a test asserting the accepted value does not test the offer),
trap 5 (an empty repository is not an error) and trap 8 (the sweep must be able
to fail) are the three that cost a rejected attempt each if met late.

Neither story may add a manifest key (FR-010). If you see "prompter ran out of
answers" in a test file you never opened, you have added one.

## Phase 1: User Story 1 — The interview offers the branch the repository is on

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] Write the prompt-text case FIRST: in a repository whose current
      branch is `master`, the landing-branch question's offered default reads
      `master` — asserted against the **prompt text**, not the accepted value
      (spec US1-S1, FR-001; plan trap 3) — must fail.
- [ ] T002 [P] [US1] Write the end-to-end case: accepting every default in that
      repository writes a manifest declaring `master`, and the real
      `_landing_branch_finding` (`factory/mergequeue/onboard.py:408`) passes
      against the real written file — never against a constructed profile
      (spec US1-S2, FR-001) — must fail.
- [ ] T003 [P] [US1] Write the empty-repository case: a repository with no
      commits and no resolvable HEAD offers the existing literal and `ergane
      init` completes (spec US1-S3, FR-002; plan trap 5) — must fail.
- [ ] T004 [P] [US1] Write the override case: a typed branch name wins unchanged
      over the derived default (spec US1-S4, FR-003) — must fail.
- [ ] T005 [P] [US1] Write the re-run case: a manifest that already declares a
      landing branch offers that value ahead of the repository reading
      (spec US1-S5, FR-004) — must fail. Read `factory/cli/init.py:323` first;
      this behaviour already exists and the test pins it rather than building it.

### Implementation for this story

- [ ] T006 [US1] Derive the landing-branch default from the repository's current
      branch, replacing the `"main"` literal at `factory/cli/init.py:256` as the
      *fallback* rather than as the answer (FR-001, FR-002). The derivation goes
      underneath `:323`'s existing-manifest preference, not in front of it.
- [ ] T007 [US1] Confirm the offer is presented as an offer, not as a verified
      fact (FR-005) — the readiness check at `onboard.py:408` remains the
      verdict and is not touched by this story.
- [ ] T008 [US1] Commit the transcript for SC-001: a machine whose git creates
      `master`, `git init . && ergane init` with every default accepted, and the
      `landing_branch` line of the readiness report. Capture `rc=$?` before any
      pipe (plan trap 2). Committed file or it does not exist (plan trap 1).

## Phase 2: User Story 2 — The Temporal namespace is one fact, spelled once

### Tests for this story (write FIRST, must fail)

- [ ] T009 [US2] Write the sweep FIRST: exactly one Temporal-namespace literal
      exists in the shipped package, held **by path**, with an anti-vacuity
      assertion that the file list read is non-empty and names both
      `factory/cli/install.py` and `factory/notify/service.py`
      (spec US2-S1, US2-S4, FR-006, FR-009; plan trap 8) — must fail.
- [ ] T010 [P] [US2] Write the agreement case: with no config and no
      environment, the resolved namespace is the same value `ergane install`
      seeds — asserted as one source, never as two equal string literals
      (spec US2-S2, FR-007) — must fail.
- [ ] T011 [P] [US2] Write the precedence case: a declared namespace still wins
      over the single default (spec US2-S3, FR-008) — must fail.

### Implementation for this story

- [ ] T012 [US2] Make one literal the source of the other, so
      `factory/cli/install.py:71` and `factory/notify/service.py:111` cannot
      disagree (FR-006, FR-007). **Which value wins is not this story's
      decision** — see plan trap 9 and the spec's Out of Scope; if it has not
      been made, stop and ask.
- [ ] T013 [US2] Run and quote
      `test_no_connect_site_keeps_its_own_copy_of_the_temporal_contract`
      (048/US4's AST guard) — it is the test this change is most likely to break
      silently (FR-008, plan trap 6).
- [ ] T014 [US2] Read `factory/notify/service.py:679`, which still spells
      `os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE`.
      Report whether it is outside 048/US4's connect-site definition or a gap in
      that guard. **Do not fix it here** (plan trap 7).

## Verification

- [ ] T015 Full suite, verbatim, with the cache state it was run in. Baseline
      skips are 44; a new skip is a hidden test and must be declared.
- [ ] T016 Mutation battery with a point-at-nothing control as its **first** row,
      `__pycache__` purged between mutants (plan traps 8, 10), and the tree
      asserted clean — tracked and untracked — before and after.
- [ ] T017 Diff measured through `size_refusal` from
      `factory/verify/diffbounds.py`, with the number quoted.
- [ ] T018 Confirm SC-004: the number of questions `ergane init` asks is
      unchanged and no scripted-interview answer list under `tests/` was edited.
