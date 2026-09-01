# Tasks: a stale anchor fails validate, not the attempt

**Spec**: `specs/072-a-stale-anchor-fails-validate-not-the-attempt/spec.md`
**Plan**: `specs/072-a-stale-anchor-fails-validate-not-the-attempt/plan.md`

Read the plan's traps before the first task. Trap 1 (skip `spec.md` frontmatter
or every held spec becomes unvalidatable), trap 8 (fixtures are supplied trees,
never this repository), trap 7 (the controls are the story) and traps 10–11
(resolve against `--target-repo`, and skip rather than refuse when that tree
cannot be read) are the four that decide whether an attempt lands.

Read the plan's opening section too. Three of its own six anchors had rotted by
253, 254 and 443 lines while `ergane spec validate` passed the spec clean, and
**all three still resolved to real, non-blank lines** — US1's tier would have
caught none of them. That is the spec's own evidence and it changes which story
carries the weight.

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
- [ ] T006a [P] [US1] (spec US1-S7, traps 10 and 11) **The second control.**
      Assert that with `--target-repo` pointing at a path that does not exist,
      the anchor layer appears in `skipped` naming that path and adds nothing to
      `findings`. Validate's default `--target-repo` is
      `/srv/factory/targets/short-links`, absent on most hosts, so without this
      the layer turns every spec into a wall of false refusals.

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-004) Scan `plan.md` and `tasks.md` for `path:NN` and
      `path:NN-MM` citations and report absent file, past-EOF and blank-line
      cases, naming the citing document and line. Copy `_check_evidence`'s shape
      (`factory/cli/nouns/spec.py:1325-1409`) — it is the only existing layer
      that takes the target repository and the only one that models skipping —
      and append to the same `findings` list `_validate_command` already reads
      (`factory/cli/nouns/spec.py:483-728`). `_check_scenario_coverage`
      (`factory/cli/nouns/spec.py:923-960`) is the simpler shape for the
      appending itself.
- [ ] T008 [US1] (FR-002) Mask fenced blocks using
      `factory/verify/criteria.py:189-219` — `mask_fences`. Do not write a second
      fence scanner (trap 2).
- [ ] T009 [US1] (FR-003) Skip citations above `spec.md`'s closing frontmatter
      `---` (trap 1).
- [ ] T010 [US1] (FR-005) Check both endpoints of a range, and report a range
      whose end precedes its start.
- [ ] T011 [US1] (FR-010) Emit anchor findings as `severity="advisory"` for a
      spec that can no longer dispatch and as the default refusal otherwise.
      `_ValidateFinding` already takes the keyword
      (`factory/cli/nouns/spec.py:476-480`, `__init__` at `:477`); do not add a
      severity (trap 6).
- [ ] T011a [US1] (FR-011, trap 10) Resolve every cited path against
      `args.target_repo`, never against `Path.cwd()`. `_check_evidence` takes it
      at `factory/cli/nouns/spec.py:1325-1331`; take it the same way. A check
      that resolves against the working directory works in the operator's shell
      and behaves differently under the roadmap and inside a node.
- [ ] T011b [US1] (FR-011, trap 11) When that tree cannot be read, append to
      `skipped` with a reason naming the path and add nothing to `findings`.
      `factory/cli/nouns/spec.py:749-760` — `_tasks_text` — states the rule: a
      document nobody opened has no findings, and calling that a clean bill of
      health is how a check comes to be trusted for something it never did.
- [ ] T011c [US1] (FR-004, trap 12) Register the layer **twice**: append its name
      to `checked` (built at `factory/cli/nouns/spec.py:497-502`) and add its
      phrase to `_all_pass_phrases` (`factory/cli/nouns/spec.py:731-746`). The
      all-pass sentence is a hardcoded list; a layer missing from it prints a
      clean bill of health that never names the anchors. The conditional `fixes`
      phrase at `:744-745` is the worked example.
- [ ] T012 [US1] Cache file contents in a dict keyed by path so a module cited
      forty times is read once — 3607 anchors across 116 specs, and
      `factory/workgraph/workflow.py` is 4314 lines (trap 5).

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
- [ ] T017a [US2] (FR-006, trap 4) Handle the two shapes live in the corpus: a
      dotted citation (`_ValidateFinding.__init__`) resolves on its last segment,
      and a name defined more than once in a module is satisfied by a cited line
      inside **any** of its definitions. Reporting a citation that is in fact
      correct is the one failure this check cannot afford.
- [ ] T018 [US2] (FR-008) Report an absent symbol as its own finding kind.
- [ ] T018a [US2] (FR-007) Parse each module's AST at most once, alongside T012's
      content cache (trap 5). A `SyntaxError` in a cited file is not an anchor
      finding — it is a file this layer cannot answer for.

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
- [ ] T027 (SC-004) Restore this plan's own pre-2026-09-01 citations —
      `_validate_command` at :230-390 and `_check_scenario_coverage` at
      :480-517 — in a scratch copy, validate, paste the report, then correct
      them and paste the silence. Both still resolve to real non-blank lines, so
      this also demonstrates that US1 alone passes them.
- [ ] T028 (SC-005) Run validate with `--target-repo` pointing at a tree without
      the cited files and paste the output: the layer named as not checked, and
      no anchor finding.
