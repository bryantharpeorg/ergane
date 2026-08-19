# Tasks: install can be driven without a human

**Spec**: `specs/060-install-can-be-driven-without-a-human/spec.md`
**Plan**: `specs/060-install-can-be-driven-without-a-human/plan.md`

Read the plan's **Traps** before the first task. Trap 1 decides the size of this
epic: an implementer who forks the interview writes a large diff that fails
US1-S2 and has to start again.

Tests are written before the implementation and must fail for the stated reason
before anything is made to pass.

Edges: US1 → US2. US3 is independent of both and may run in parallel.

## Phase 1: User Story 1 — Install runs from a file, with no terminal

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) `tests/test_ergane_install_walkthrough.py` or a sibling:
      run `ergane install --from-file <path>` with stdin closed and assert the
      config is written and the interactive prompter was never invoked.
- [ ] T002 [P] [US1] (spec US1-S2) Assert the file-driven path and the scripted-prompter
      walkthrough produce **identical** configs from identical answers. This is
      the anti-fork test (trap 1); write it before the implementation, not after.
- [ ] T003 [P] [US1] (spec US1-S3) Assert a field omitted from the file takes its documented
      default **and** that the applied default appears in the command's output
      (trap 5).
- [ ] T004 [P] [US1] (spec US1-S4) Assert a field with no safe default exits non-zero naming
      the field, and that no config file exists afterwards (FR-004: refuse before
      `_write_config` at `factory/cli/install.py:157`).
- [ ] T005 [P] [US1] (spec US1-S5) Assert a literal credential supplied *by file* is refused
      by `_reject_secret_shape` with the same wording the interactive path emits
      (trap 4).
- [ ] T006 [P] [US1] (spec US1-S6) Assert the documented worked example parses and drives a
      successful install, unmodified.

### Implementation for this story

- [ ] T007 [US1] (FR-001) Add `--from-file` to `add_install_arguments`
      (`factory/cli/install.py:118`).
- [ ] T008 [US1] (FR-001, FR-006) Implement a non-interactive prompter satisfying the same
      contract as `factory.cli.init._prompter()`, answering from the supplied
      document. Feed it to the existing `_interview` (`factory/cli/install.py:169`)
      — do **not** add a second interview function (trap 1).
- [ ] T009 [US1] (FR-003, FR-006) Establish the single shared defaults source both paths
      read. Do not create a second table (trap 2).
- [ ] T010 [US1] (FR-004) Collect unfillable fields and refuse with all of them named,
      before any write.
- [ ] T011 [US1] (FR-007) Route file-supplied values through the existing secret-shape
      guard.
- [ ] T012 [US1] (FR-008) Document the answer-file format with a complete worked example,
      in the location T006 asserts against.

## Phase 2: User Story 2 — Init runs non-interactively, and a closed stdin is not consent

### Tests for this story (write FIRST, must fail)

- [ ] T013 [P] [US2] (spec US2-S1) Assert `ergane init` with stdin closed and **no** flag
      exits non-zero naming the unanswerable question, and that no `ergane.yaml`
      was written. This is the `/dev/null` defect inverted (trap 3).
- [ ] T014 [P] [US2] (spec US2-S2) Assert `ergane init --non-interactive` with stdin closed
      completes, and that every applied default is printed.
- [ ] T015 [P] [US2] (spec US2-S3) Assert a field with no safe default exits non-zero naming
      it.
- [ ] T016 [P] [US2] (spec US2-S4) Assert an explicit per-field override beats the default,
      for at least gates and landing branch.
- [ ] T017 [P] [US2] (spec US2-S5) Assert the interactive and non-interactive defaults agree
      field by field, read from one source (trap 2).

### Implementation for this story

- [ ] T018 [US2] (FR-002) Add `--non-interactive` to both `install` and `init` argument
      builders.
- [ ] T019 [US2] (FR-005) Make an unreadable stdin without the flag a named refusal
      rather than silent default-acceptance. Distinguish on the **flag**, not on
      the state of stdin (trap 3).
- [ ] T020 [US2] (FR-002, FR-003) Wire `--non-interactive` in `factory/cli/init.py` to the
      shared defaults source from T009.
- [ ] T021 [US2] (FR-004) Refuse, naming the field, where no safe default exists —
      writing no manifest.

## Phase 3: User Story 3 — Escalation can be declared off, and says so

### Tests for this story (write FIRST, must fail)

- [ ] T022 [P] [US3] (spec US3-S1) Assert a config declaring `escalation.adapter = "none"`
      parses.
- [ ] T023 [P] [US3] (spec US3-S2) Assert `--verify` emits a finding stating escalations will
      be dropped, and naming the operational consequence: a node that would have
      asked a question fails instead of waiting.
- [ ] T024 [P] [US3] (spec US3-S3) Assert that finding does **not** fail the run (trap 7).
- [ ] T025 [P] [US3] (spec US3-S4) Assert the two-directional conformance contract at
      `factory/controlplane/config.py:48` still holds with `"none"` present
      (trap 6).
- [ ] T026 [P] [US3] (spec Edge Cases) Assert an explicit `"none"` is not silently upgraded to
      telegram when a bot token happens to be present in the environment.

### Implementation for this story

- [ ] T027 [US3] (FR-009) Add `"none"` to `KNOWN_ESC_ADAPTERS`
      (`factory/controlplane/config.py:51`) and satisfy the registry contract in
      both directions — either a registered null adapter or an explicit
      exemption, held by T025.
- [ ] T028 [US3] (FR-010) Emit the non-failing verification finding.
- [ ] T029 [US3] Make `_ask_escalation` (`factory/cli/install.py:183`) offer `none` as a
      selectable answer, so the interactive path reaches the same state the
      non-interactive one can declare.

## Verification

- [ ] T030 (SC-001) On a scratch host, drive a complete install **and** init with
      stdin closed throughout, then run `ergane install --verify` and `ergane
      init --check` and confirm both accept. **Paste the transcript into the
      diff** — the judge sees nothing else (trap 9).
- [ ] T031 (SC-002) Run each command with stdin closed and no flag; confirm non-zero
      exit and confirm no artifact was written. Paste the output.
- [ ] T032 (SC-003) Copy the documented worked example without editing it and drive an
      install with it.
- [ ] T033 (SC-004) On a host with no Telegram token set at all, complete install and
      `--verify` to a green result.
