# Tasks: a stale anchor fails validate, not the attempt

**Spec**: `specs/072-a-stale-anchor-fails-validate-not-the-attempt/spec.md`
**Plan**: `specs/072-a-stale-anchor-fails-validate-not-the-attempt/plan.md`

Read the plan's traps before the first task. Trap 1 (skip `spec.md` frontmatter
or every held spec becomes unvalidatable), trap 8 (fixtures are supplied trees,
never this repository) and trap 7 (the controls are the story) are the three that
decide whether an attempt lands.

## Phase 1: User Story 1 — An anchor that does not resolve is named

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_anchor_resolution.py`, supply a
      tree and a plan citing a line past end-of-file, and assert validate reports
      it naming the citing document, the citing line, the cited path and the
      cited line. Supply the tree; never cite real `factory/` lines (trap 8).
- [ ] T002 [P] [US1] (spec US1-S2) Assert a citation landing on a blank line is
      reported.
- [ ] T003 [P] [US1] (spec US1-S3) Assert a citation to an absent file is
      reported naming the path.
- [ ] T004 [P] [US1] (spec US1-S4) Assert a citation inside a fenced code block
      is **not** reported, over a fixture whose fence contains an otherwise
      broken anchor (trap 2).
- [ ] T005 [P] [US1] (spec US1-S5) Assert a citation inside `spec.md`'s
      frontmatter is **not** reported. Build the fixture with a second `---` and
      a deliberately broken anchor above it — this is trap 1, and it is the test
      that keeps held specs validatable.
- [ ] T006 [P] [US1] (spec US1-S6) **The control.** Assert a plan whose every
      anchor resolves reports nothing. Prove it can fail by breaking one anchor
      in the same fixture (trap 7).

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-004) Scan `plan.md` and `tasks.md` for `path:NN` and
      `path:NN-MM` citations and report absent file, past-EOF and blank-line
      cases, naming the citing document and line. Follow
      `_check_scenario_coverage`'s shape (`factory/cli/nouns/spec.py:480-517`)
      and append to the same `findings` list `_validate_command` already reads
      (`factory/cli/nouns/spec.py:230-390`).
- [ ] T008 [US1] (FR-002) Mask fenced blocks using
      `factory/verify/criteria.py:189` — `mask_fences`. Do not write a second
      fence scanner (trap 2).
- [ ] T009 [US1] (FR-003) Skip citations above `spec.md`'s closing frontmatter
      `---` (trap 1).
- [ ] T010 [US1] (FR-005) Check both endpoints of a range, and report a range
      whose end precedes its start.
- [ ] T011 [US1] (FR-010) Emit anchor findings as `severity="advisory"` for a
      spec that can no longer dispatch and as the default refusal otherwise.
      `_ValidateFinding` already takes the keyword
      (`factory/cli/nouns/spec.py:223-227`); do not add a severity (trap 6).
- [ ] T012 [US1] Cache file contents in a dict keyed by path so a module cited
      forty times is read once (trap 5).

## Phase 2: User Story 2 — An anchor that lands on the wrong symbol is named

### Tests for this story (write FIRST, must fail)

- [ ] T013 [P] [US2] (spec US2-S1) In `tests/test_anchor_names_its_symbol.py`,
      assert a citation naming a symbol whose line falls outside that symbol's
      span is reported with the symbol, the cited line and the real span.
- [ ] T014 [P] [US2] (spec US2-S2) **The control.** Assert a citation whose line
      falls inside the named symbol reports nothing, and prove it can fail by
      moving the line one past `end_lineno` (trap 7).
- [ ] T015 [P] [US2] (spec US2-S3) Assert a named symbol absent from the cited
      file is reported as absent, distinctly from a line-outside-span report.
- [ ] T016 [P] [US2] (spec US2-S4) Assert a citation whose prose names no symbol
      is checked only by US1's rules, with no symbol claim invented.

### Implementation for this story

- [ ] T017 [US2] (FR-006, FR-007) Resolve symbol spans with `ast.parse` and a
      walk over `FunctionDef`, `AsyncFunctionDef` and `ClassDef`, reading
      `lineno` and `end_lineno`. Never a regex (trap 4).
- [ ] T018 [US2] (FR-008) Report an absent symbol as its own finding kind.

## Phase 3: User Story 3 — A bare line reference is resolved or refused

### Tests for this story (write FIRST, must fail)

- [ ] T019 [P] [US3] (spec US3-S1) In `tests/test_bare_line_references.py`,
      assert a bare `` `:NN` `` is resolved against the most recent path cited
      before it and checked as US1 checks any anchor.
- [ ] T020 [P] [US3] (spec US3-S2) Assert a bare reference with no preceding path
      in its section is reported as unanchorable, not skipped.
- [ ] T021 [P] [US3] (spec US3-S3) Assert a bare reference resolving to a blank
      line is reported exactly as US1 reports one.
- [ ] T022 [P] [US3] (spec US3-S4) **The control.** Assert a document with no
      bare references reports nothing and US1's behaviour is unchanged.

### Implementation for this story

- [ ] T023 [US3] (FR-009) Carry the last cited path forward in a stateful pass
      and resolve bare references against it. State in the diff what bounds "the
      same section" and why — a heading is the natural boundary and a bullet is
      too narrow (trap 3).

## Verification

- [ ] T024 (SC-001) Validate a supplied spec with deliberately stale anchors and
      paste the report. Every stale anchor must appear.
- [ ] T025 (SC-002) Validate a supplied spec whose anchors all resolve and paste
      the report. Nothing must appear.
- [ ] T026 (SC-003) Run the check across every spec in `specs/` and paste the
      per-state totals, showing landed advisory and ready/draft refusing.
- [ ] T027 (SC-004) Restore `_judge_rewrites_spent` to `:127-145` in a copy of
      068's plan, validate, paste the report, then correct it to `:181-199` and
      paste the silence.
