# Tasks: the README is the whole truth

**Spec**: `specs/063-the-readme-is-the-whole-truth/spec.md`
**Plan**: `specs/063-the-readme-is-the-whole-truth/plan.md`

Read the plan's **Traps** before the first task. Trap 1 is the one that decides
whether this spec fixes the guard or rebuilds its blind spot one level up.

Tests are written before the implementation and must fail for the stated reason
before anything is made to pass.

Edges: US1 → US2 → US3 (all three touch `README.md`).

## Phase 1: User Story 1 — The sweep cannot pass over a command it failed to recognise

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, US1-S5) Build a fixture page containing a near-miss command
      span and assert the sweep **fails** naming the unrecognised word. Assert
      failure, not the detector's existence (trap 1).
- [ ] T002 [P] [US1] (spec US1-S2) Assert a fixture page naming `git clone`, `uv venv`,
      `gh auth login` and `systemctl --user daemon-reload` passes with zero flags
      (trap 2).
- [ ] T003 [P] [US1] (spec US1-S4) Assert `tests/test_claude_md.py` and `tests/test_readme.py`
      exercise the same shared code path (traps 3, 4).
- [ ] T004 [P] [US1] (spec US1-S3) Assert both `README.md` and `CLAUDE.md` pass the fixed
      sweep. This test cannot pass until T006 lands (trap 5).
- [ ] T005 [P] [US1] (spec Edge Cases) Assert a code span beginning with a shell pipeline whose
      first word is a legitimate non-Ergane command does not trip the detector,
      and that a correctly-spelled but nonexistent command still fails through
      the clearer `--help` path rather than being masked.

### Implementation for this story

- [ ] T006 [US1] (FR-004) Correct `README.md:105` and `README.md:111`: `nergane` →
      `ergane`.
- [ ] T007 [US1] (FR-001, FR-002, FR-003) Add near-miss detection to
      `tests/page_holds_true.py`, replacing the silent `continue` at :54. Derive
      the known-entrypoint set from the CLI's own help output using the existing
      `_CHOICES` / `_POSITIONALS` / `_INDENTED_VERB` machinery at :62–69 — never
      from a hand-written literal (trap 3). Flag only words within a small edit
      distance of a known entrypoint.
- [ ] T008 [US1] Tune the detector against both real pages and confirm zero false
      positives before declaring the story done (trap 2).

## Phase 2: User Story 2 — The page states every prerequisite that decides whether the gateway works

### Tests for this story (write FIRST, must fail)

- [ ] T009 [P] [US2] (spec US2-S1) Assert the prerequisites section states the gateway must be
      database-backed, names the dependent endpoints, and says a config-only
      proxy answers `/v1/models` and 404s the rest.
- [ ] T010 [P] [US2] (spec US2-S2) Assert the page states the gateway must serve every
      `model` and `fallback` alias the registry declares.
- [ ] T011 [P] [US2] (spec US2-S3) Assert both install paths are named and distinguished:
      published package as primary, checkout for working on Ergane.
- [ ] T012 [P] [US2] (spec US2-S4) Assert the page states the two paths resolve the persona
      registry differently.
- [ ] T013 [P] [US2] (spec US2-S5) Assert every existing 054 sweep still passes: no secret
      value, no spec state, no story count, no spend figure, all paths exist
      (FR-008).

### Implementation for this story

- [ ] T014 [US2] (FR-005, FR-006) Extend `README.md:13–27` with the database requirement,
      the dependent endpoints, and the alias-coverage requirement. Suggested
      wording for the first: "The gateway must be backed by a database. Ergane
      mints, inspects and revokes a virtual key per attempt and reads
      `/spend/logs/v2`; a config-only proxy answers `/v1/models` and 404s all of
      it."
- [ ] T015 [US2] (FR-007) Reframe `README.md:46–50`: `uv tool install ergane-cli` as the
      primary path, the checkout as the path for working on Ergane, and a note
      that the two resolve the registry differently.
- [ ] T016 [US2] Keep the page an entry page. No requirements for how code is written
      (trap 6); no status figures (trap 7).

## Phase 3: User Story 3 — The CLI can print what the gateway must serve

### Tests for this story (write FIRST, must fail)

- [ ] T017 [P] [US3] (spec US3-S1) Assert `ergane install --requirements` prints every
      distinct `model` and `fallback` alias for a fixture registry.
- [ ] T018 [P] [US3] (spec US3-S2) Assert it names the key-management endpoints the gateway
      must answer.
- [ ] T019 [P] [US3] (spec US3-S3) Assert personas declared `agent: none` contribute no alias
      (trap 9).
- [ ] T020 [P] [US3] (spec US3-S4) Assert `--requirements` and `--verify` resolve identical
      alias sets from one fixture (FR-010).
- [ ] T021 [P] [US3] (spec Edge Cases) Assert `--requirements` with no configured registry
      prints the requirement to configure one, naming the resolution order.
- [ ] T022 [P] [US3] (trap 8) Assert `--requirements` mints no key and issues no completion.

### Implementation for this story

- [ ] T023 [US3] (FR-009, FR-010) Extract the alias derivation from `LLMProbe.gather`
      (`factory/controlplane/verify.py:296`) into a shared function and add
      `--requirements` to `add_install_arguments`
      (`factory/cli/install.py:118`). If 061 has landed, re-read `gather` first —
      061/US1 changes it.
- [ ] T024 [US3] (FR-006, US3-S5) Replace any inline alias list in `README.md` with a
      reference to the command, so the page cannot go stale (trap 7).

## Verification

- [ ] T025 (SC-001) Introduce a one-character typo into a command in `README.md`, run
      the suite, confirm it fails; repeat in `CLAUDE.md`; revert both. **Paste
      the failing output into the diff** (trap 10).
- [ ] T026 (SC-002) On a host meeting the stated prerequisites, follow `README.md` top
      to bottom — including standing up a gateway from its description alone —
      and confirm every command runs as written.
- [ ] T027 (SC-003) Confirm no source file needs opening to determine any gateway
      requirement.
- [ ] T028 (SC-004) Run `--requirements` and `--verify` against the same registry and
      confirm the alias sets match.
