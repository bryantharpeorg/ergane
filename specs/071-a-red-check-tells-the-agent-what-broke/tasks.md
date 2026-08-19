# Tasks: a red check tells the agent what broke

**Spec**: `specs/071-a-red-check-tells-the-agent-what-broke/spec.md`
**Plan**: `specs/071-a-red-check-tells-the-agent-what-broke/plan.md`

Read the plan's traps before the first task. Trap 1 (**do not rebuild 025** — the
evidence chain works, one `gh` call upstream of it does not), trap 3 (keep the
degradation) and trap 5 (the mutation control is the story) are the three that
decide whether an attempt lands.

## Phase 1: User Story 1 — A recovery agent is told which test failed

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_check_evidence_reaches_the_agent.py`,
      gather evidence for a failing check through a fake `gh` that **refuses any
      argv the real `gh` would refuse**, and assert the returned record carries a
      name, a run URL and a NON-EMPTY log. Against today's permissive fake this
      test passes on broken code — that is the defect, and this test is where it
      stops. Decide deliberately whether the strictness belongs in
      `tests/fake_gh.py` (every existing test inherits it, which is the point) or
      in a new fake, and say which in the diff.
- [ ] T002 [P] [US1] (spec US1-S2) Assert the **assembled prompt string** contains
      the log text — build it through the same path the workflow uses, not by
      inspecting the intermediate record. Everyone already believed the record
      was right; the prompt is the artefact that was never read.
- [ ] T003 [P] [US1] (spec US1-S3) **The control.** Assert a genuine forge failure
      still returns the degraded note naming the reason, unchanged from today
      (`factory/mergequeue/github_forge.py:220-222`, trap 3). Without this, the
      story is satisfiable by deleting the fallback.
- [ ] T004 [P] [US1] (spec US1-S5) Assert per-check degradation stays per-check:
      two checks, one whose run link parses and one whose does not, and the
      parseable one still returns its log (`github_forge.py:234`).
- [ ] T005 [P] [US1] (spec US1-S4) Assert taking the degraded path is recorded
      somewhere an operator can read without opening an agent transcript.
- [ ] T006 [P] [US1] (spec Assumptions, trap 2) Assert the rollup mapping over the
      shapes that actually occur — a check run (`conclusion`, `detailsUrl`), a
      commit status (`state`, `targetUrl`), and an entry carrying neither — and
      assert the unrecognised one degrades per-check rather than failing the
      batch. **Fetch a real mixed rollup before choosing the mapping.**

### Implementation for this story

- [ ] T007 [US1] (FR-001) Replace the `gh pr checks --json` invocation at
      `factory/mergequeue/gh.py:210` with a command the installed `gh` accepts.
      The proven one, run end to end by hand and pasted in the plan, is
      `gh pr view <n> --json statusCheckRollup`. `_parse_run_id` already parses
      its `detailsUrl` unchanged — verified; do not modify it.
- [ ] T008 [US1] (FR-001) Update `tests/test_gh_client.py:233`, which asserts the
      old argv verbatim and will now fail. This is expected work, not a
      regression (trap 12). Keep the edit confined to the argv assertion.
- [ ] T009 [US1] (FR-005) Leave the per-check loop's structure alone.
- [ ] T010 [US1] (FR-003) Leave the batch-level degradation in place.
- [ ] T011 [US1] (FR-004) Make the degraded path observable.

### Verification for this story

- [ ] T012 [US1] (SC-001, spec US1-S6) Run the new command against a real pull request with a
      real failing check and paste the command and its output into the diff.
- [ ] T013 [US1] (SC-002) Paste the assembled recovery prompt's landing-rejection
      section for that pull request, showing the log where `log unavailable` was.
- [ ] T014 [US1] (SC-003) Paste the control: a genuine forge failure still
      degrading, with its reason named.

## Phase 2: User Story 2 — A `gh` command the CLI cannot parse fails the suite

**Depends on US1 having merged** (`depends_on_merged`). Both stories edit
`factory/mergequeue/gh.py`; the edge is contention, not logic. If `gh.py` does
not look as the plan describes, US1 has landed — re-read it (trap 10).

### Tests for this story (write FIRST, must fail)

- [ ] T015 [P] [US2] (spec US2-S1) In `tests/test_gh_argv_contract.py`, validate
      **every** command `GhClient` issues against the installed `gh`, with the
      command set **enumerated from the class** rather than hand-listed (trap 6).
      A list is what goes stale.
- [ ] T016 [P] [US2] (spec US2-S2) **The mutation control, and the reason this
      story exists.** Construct an argv with a flag `gh` does not have and assert
      the check fails, naming the command and the flag. A check nobody has
      watched go red is the same class of test that shipped this defect (trap 5).
- [ ] T017 [P] [US2] (spec US2-S3, FR-007) Assert the check works with no network,
      no `GH_TOKEN` and no repository — `gh` rejects unknown flags during argument
      parsing, before it authenticates (trap 7). Prove it; the story's
      affordability rests on it.
- [ ] T018 [P] [US2] (spec US2-S6) Assert the check skips by a **real runtime
      guard** when `gh` is absent, never by a `pytest.mark` — nothing here passes
      `-m` in CI or in the gate, so a marked test is an unrun test (trap 8).
- [ ] T019 [P] [US2] (spec US2-S5) Assert `create_pr`'s corrected behaviour
      directly, and update `tests/test_gh_client.py:102`, which asserts the old
      shape.

### Implementation for this story

- [ ] T020 [US2] (FR-006, FR-007) Add the argv check.
- [ ] T021 [US2] (FR-008) Fix `create_pr` at `factory/mergequeue/gh.py:172`: `gh
      pr create` prints a URL, not JSON, so it must not go through `_run_json`.
      Either derive the number from the printed URL or call `find_existing_pr`
      immediately after — choose one and say why in the diff (trap 9). **Do not
      loosen `_run_json` itself** (trap 4): it is correct, and loosening it would
      silence the calls that are right.
- [ ] T022 [US2] Fix any further command the check finds. If it finds none beyond
      these two, say so — that is SC-004's measurement, not an omission.

### Verification for this story

- [ ] T023 [US2] (SC-004, spec US2-S4) Paste the check's output against the tree BEFORE the
      fixes, showing it red on `pr_checks` and `create_pr`.
- [ ] T024 [US2] (SC-005) Paste it after, green.
- [ ] T025 [US2] (SC-006) Paste the mutation: add a flag `gh` does not have, show
      the check red and naming it, remove it.
- [ ] T026 [US2] (SC-007) Paste the check running with `GH_TOKEN` unset outside any
      git repository, still catching an unknown flag.
