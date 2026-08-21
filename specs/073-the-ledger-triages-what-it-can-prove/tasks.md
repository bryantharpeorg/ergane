# Tasks: the ledger triages what it can prove

**Spec**: `specs/073-the-ledger-triages-what-it-can-prove/spec.md`
**Plan**: `specs/073-the-ledger-triages-what-it-can-prove/plan.md`

Read the plan's traps before the first task. Trap 1 (naming is not fixing — the
first draft of this spec got it wrong and the review caught it), trap 4 (`triage`
must not inherit `_with_store`), trap 5 (`report()` is not an annotation path)
and trap 13 (fixtures are supplied trees, never `.factory/`) are the four that
decide whether an attempt lands.

## Phase 1: User Story 1 — A spec declares which findings it fixes

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_spec_declares_its_fixes.py`,
      supply a corpus with a spec whose frontmatter carries `fixes:` as a list of
      finding keys, and assert the parsed record exposes them.
- [ ] T002 [P] [US1] (spec US1-S2) Assert a spec omitting `fixes:` parses with an
      empty list and is valid.
- [ ] T003 [P] [US1] (spec US1-S3) Assert a `fixes:` written as a bare string is
      refused, naming the offending spec.
- [ ] T004 [P] [US1] (spec US1-S4) **The control.** Assert a frontmatter key that
      is none of `state`, `depends_on_landed`, `fixes` is still refused (trap 16).
- [ ] T005 [P] [US1] (spec US1-S5) Assert `ergane spec validate` reports the same
      result as before over a supplied corpus carrying both forms.

### Implementation for this story

- [ ] T006 [US1] (FR-003) Add `fixes` to `_KNOWN_KEYS`
      (`factory/roadmap/models.py:113`). Read the comment at
      `factory/roadmap/models.py:107-112` first — it says why the set is closed.
      The `unknown_key` refusal at `factory/roadmap/models.py:293-301` needs no
      change.
- [ ] T007 [US1] (FR-001, FR-002) Shape-check `fixes` exactly as
      `depends_on_landed` is checked at `factory/roadmap/models.py:325-333`:
      absent reads `[]`, `None` reads `[]`, anything not a list of strings is a
      finding. Do not invent a second idiom.
- [ ] T008 [US1] (FR-001) Add the field to `SpecEntry`
      (`factory/roadmap/models.py:122-138`) after `source`, with
      `field(default_factory=list)` — a bare `= []` on a frozen dataclass is a
      shared-mutable bug. Pass it at the construction site
      (`factory/roadmap/models.py:336-340`).
- [ ] T009 [US1] Update the existing test that asserts the grammar is exactly two
      keys, in this diff rather than around it (trap 16).

## Phase 2: User Story 2 — A sweep tells the operator what it can prove

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1) In `tests/test_findings_triage_classifies.py`,
      supply a specs corpus and a store, and assert a finding declared under a
      landed spec's `fixes:` with `last_seen` at or before that spec's landing
      commit is classed fixed, with the declaring spec named. Supply both trees;
      never read `.factory/` or real `specs/` (trap 13).
- [ ] T011 [P] [US2] (spec US2-S2) **The control that matters most.** Assert the
      same finding with `last_seen` after the landing commit is classed as seen
      after its fix landed and is **not** fixed.
- [ ] T012 [P] [US2] (spec US2-S3) Assert a finding declared by a landed spec
      whose landing commit cannot be dated is classed as needing a human, never
      fixed (trap 2).
- [ ] T013 [P] [US2] (spec US2-S4) Assert a finding no `fixes:` declares, whose
      key appears in a landed spec's prose, is classed as a candidate and names
      **every** spec whose prose contains it — over a fixture with two such specs
      (trap 1).
- [ ] T014 [P] [US2] (spec US2-S5) Assert two open findings whose keys carry three
      or more segments, share their first two, and share one `source` are reported
      as one fragmented class naming the prefix and the member count.
- [ ] T015 [P] [US2] (spec US2-S6) **The control.** Assert a two-segment key and a
      lone three-segment key form no fragmented class (trap 7).
- [ ] T016 [P] [US2] (spec US2-S7) Assert a finding older than the cold threshold
      at one occurrence is classed cold, and one inside the threshold is not, in
      one test carrying both.
- [ ] T017 [P] [US2] (spec US2-S8) Assert running triage without `--apply` leaves
      the store file's bytes identical, by hashing before and after (trap 4).
- [ ] T018 [P] [US2] (spec US2-S9) Assert the class counts sum to the number of
      open and regressed findings, so no row is dropped.

### Implementation for this story

- [ ] T019 [US2] (FR-004) Register a `triage` verb on the shared `db_parent` in
      `add_findings_parser` (`factory/cli/doctor.py:238-304`) with **its own
      runner**, not `_with_store` (`factory/cli/doctor.py:307-319`), because that
      wrapper writes (trap 4). Follow `findings_list_command`'s output shape
      (`factory/cli/doctor.py:322-345`) including `--json`.
- [ ] T020 [US2] (FR-005, FR-012) Read each spec's `fixes:` and `state` from the
      roadmap reader's parsed record, so both come from one parse, and index
      finding key → declaring spec dirs.
- [ ] T021 [US2] (FR-005, FR-006) Date each declaring spec's landing with
      `git log --reverse -S'state: landed'` over its `spec.md`, taking the
      **first** commit (trap 3), caching per spec directory, and split fixed from
      seen-after-fix on `last_seen` against that date.
- [ ] T022 [US2] (FR-007) Class an undated landing as needing a human. Do not fall
      back to mtime, to the `# ATTESTED landed …` comment, or to "assume it
      landed" (trap 2).
- [ ] T023 [US2] (FR-008) Scan spec prose for undeclared keys and report them as
      candidates naming every containing spec. Match on segment boundaries, never
      a bare substring (trap 6).
- [ ] T024 [US2] (FR-009) Group by three-or-more-segment keys sharing their first
      two segments and one `source`; a group of one is not a class (trap 7).
- [ ] T025 [US2] (FR-010) Add the cold threshold as an operator-settable option
      defaulting to 14 days.
- [ ] T026 [US2] (FR-011) Assign everything else to needs-a-human and print the
      sum check.
- [ ] T027 [US2] (FR-013) Ensure the verb opens no write transaction of its own
      and runs no sweep that would, and state in the diff which tree spec state
      was read from (spec Assumptions).

## Phase 3: User Story 3 — The sweep can enact only what was declared

### Tests for this story (write FIRST, must fail)

- [ ] T028 [P] [US3] (spec US3-S1) In `tests/test_findings_triage_applies.py`,
      assert `--apply` resolves a fixed finding with the declaring spec directory
      as its resolution.
- [ ] T029 [P] [US3] (spec US3-S2) Assert a prose candidate is untouched by
      `--apply` (trap 1).
- [ ] T030 [P] [US3] (spec US3-S3) Assert a seen-after-fix finding is untouched —
      status, occurrences, `last_seen` and event count all unchanged.
- [ ] T031 [P] [US3] (spec US3-S4) Assert every member of a fragmented class is
      resolved with a resolution naming the shared prefix and the fold count, and
      the surviving class key is printed.
- [ ] T032 [P] [US3] (spec US3-S5) Assert a cold and a needs-a-human finding stay
      `open` with only their notes changed.
- [ ] T033 [P] [US3] (spec US3-S6) Assert a second `--apply` does not duplicate an
      annotation and leaves occurrences, `last_seen` and the event trail unchanged
      (trap 5).
- [ ] T034 [P] [US3] (spec US3-S7) **The control.** Assert a store where nothing
      is declared comes out of `--apply` with no status changed at all.

### Implementation for this story

- [ ] T035 [US3] (FR-014) Resolve fixed findings through the existing
      `resolve_by_spec` (`factory/doctor/store.py:271-310`). Do not add a second
      resolution path.
- [ ] T036 [US3] (FR-015) Exclude the seen-after-fix and candidate classes from
      every write.
- [ ] T037 [US3] (FR-016) Fold a fragmented class with `resolve`
      (`factory/doctor/store.py:229-268`), passing the shared prefix and the count
      as the reason, print the surviving class key, and say in the output that the
      fold re-fragments until US5 lands (trap 12).
- [ ] T038 [US3] (FR-017, FR-018) Add `annotate(conn, key, ...)` beside `resolve`
      in `factory/doctor/store.py` that updates `notes` alone — no event, no
      occurrence increment, no `last_seen` advance — and make it idempotent
      (trap 5).
- [ ] T039 [US3] (FR-019) Refuse to resolve anything outside the fixed and folded
      classes, and state in the diff the single `resolution` predicate that
      reverses a whole pass.

## Phase 4: User Story 4 — The boundary detector reports what it says it reports

### Tests for this story (write FIRST, must fail)

- [ ] T040 [P] [US4] (spec US4-S1) In
      `tests/test_detector_reports_removals_only.py`, supply a runtime root, let a
      sibling worktree gain files during the attempt, and assert no finding is
      filed (trap 10).
- [ ] T041 [P] [US4] (spec US4-S2) **The control.** Assert removing a sibling
      worktree during the attempt still files a finding naming it.
- [ ] T042 [P] [US4] (spec US4-S3) Assert truncating an evidence store still files
      a finding naming it.
- [ ] T043 [P] [US4] (spec US4-S4) Assert `doctor.db` merely growing files no
      finding (trap 9).
- [ ] T044 [P] [US4] (spec US4-S5) Assert an attempt that modifies a tracked path
      in the target repo still files a finding, unchanged (trap 11, FR-023).

### Implementation for this story

- [ ] T045 [US4] (FR-020) Change `RuntimeRootState.changes_since`
      (`factory/workgraph/detector.py:77-86`) to report only removal and
      truncation, and correct the notes heading at
      `factory/workgraph/detector.py:355` if it no longer describes the output
      (trap 8).
- [ ] T046 [US4] (FR-021) Keep the three evidence stores named at
      `factory/workgraph/detector.py:253` under removal and truncation checks
      while exempting growth (trap 9).
- [ ] T047 [US4] (FR-022) Exclude `__pycache__`, `.pytest_cache` and `*.pyc` at
      capture inside `_runtime_root_state`
      (`factory/workgraph/detector.py:241-276`; the walk is at
      `factory/workgraph/detector.py:272`), not at comparison, so the snapshot
      shrinks too (trap 10).
- [ ] T048 [US4] (FR-023) Leave `TrackedState.changed`
      (`factory/workgraph/detector.py:56-62`) and `_tracked_state`
      (`factory/workgraph/detector.py:127-206`) untouched.

## Phase 5: User Story 5 — One class, one key, bounded evidence

### Tests for this story (write FIRST, must fail)

- [ ] T049 [P] [US5] (spec US5-S1) In
      `tests/test_detector_keys_on_the_class.py`, assert two violations on two
      different nodes produce one row with two occurrences.
- [ ] T050 [P] [US5] (spec US5-S2) Assert that row's refs name the epic and node
      of the attempt that filed it.
- [ ] T051 [P] [US5] (spec US5-S3) Assert notes are truncated to the bound with a
      count of the remainder when an attempt exceeds it.
- [ ] T052 [P] [US5] (spec US5-S4) **The control.** Assert an attempt under the
      bound has every path in its notes and no truncation notice (trap 15).

### Implementation for this story

- [ ] T053 [US5] (FR-024) Drop the epic and node suffix from `_finding_key`
      (`factory/workgraph/detector.py:329-330`).
- [ ] T054 [US5] (FR-025, FR-026) In `_build_finding`
      (`factory/workgraph/detector.py:333-385`), carry the epic and node in refs
      and bound the notes to a fixed number of paths plus a remainder count.

## Verification

- [ ] T055 (SC-001) Run `ergane findings triage` against the archived pre-sweep
      store and paste the output; at least 40 candidates, each naming every spec
      whose prose contains it.
- [ ] T056 (SC-002) Paste the fixed and seen-after-fix counts from that run; both
      must be zero against a corpus that declares no `fixes:`.
- [ ] T057 (SC-003) Add `fixes:` to one landed spec in a scratch corpus copy,
      re-run, and paste the finding moving from candidate to fixed.
- [ ] T058 (SC-004) Paste `sha256sum` of the store before, between and after two
      no-apply runs; all three must match.
- [ ] T059 (SC-005) Copy the archive, run `--apply` on the copy, paste open counts
      before and after, and show `interpreter/ci-failure-never-reaches-an-agent`
      still open.
- [ ] T060 (SC-006) Paste the detector's silence on a sibling gaining a
      `.pytest_cache`, then the finding after deleting that sibling.
- [ ] T061 (SC-007) Paste one row with two occurrences from two nodes, and the
      length of its notes.
