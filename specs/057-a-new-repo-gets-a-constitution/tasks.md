# Tasks: a new repo gets a constitution

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution I): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written
in any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory anchors against the
      tree. Decide which stack packs ship in this epic — the requirement is the
      mechanism (FR-010), the count is a shipping call, and Python plus a
      language-agnostic fallback is the floor of useful. Author or approve the
      invariant floor text: it is the document every future target repo inherits,
      it is written once, and it is the one artifact here that an implementer
      should not be inventing alone. Correct the plan before deriving, not the
      nodes after.

---

## Phase 2: User Story 1 — A repo with no standards document gets one (Priority: P1)

**Goal**: `init` writes a constitution when there is none, at the manifest's
`standards` path, and never touches one that exists.

**Independent Test**: `init` against a fixture repo with no standards document
produces one carrying the floor, with the manifest naming its path; `init`
against a fixture that has one leaves it byte-identical.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      passes, and record the passed/skipped counts as the SC-001 baseline.
- [ ] T003 [US1] (spec US1-S3, SC-002, FR-002) **Write this first** (plan trap
      3): a fixture repository carrying a standards document is init'd and the
      document is asserted **byte-identical** afterwards. Cover the empty-file
      case in the same test — existence, not content, is the guard (plan trap 4).
- [ ] T004 [US1] (spec US1-S1, FR-001, FR-003) Test that a fixture repo with no
      standards document gets one at the manifest's `standards` path, and that
      the written `ergane.yaml` names that path.
- [ ] T005 [P] [US1] (spec US1-S2, FR-003) Test that with no `standards` answer
      given, the path defaults to `.specify/memory/constitution.md`, the parent
      directories are created, and the manifest records it — `standards` keeps a
      default rather than becoming mandatory (plan trap 9).
- [ ] T006 [P] [US1] (spec US1-S4, FR-004, FR-005, FR-006) Test the composed
      output contains the invariant floor and a governance section, and contains
      no Ergane spec number, decision id, dependency roster, or product-specific
      principle.
- [ ] T006a [P] [US1] (spec US1-S6, US1-S7, FR-016, FR-017, SC-006) Test the
      composed output's **wording**, mechanically: every principle carries a
      one-line why (count the principles with no rationale and assert zero —
      SC-006); the two principles that follow from the factory's mechanics
      state what removing them costs rather than asserting they must not be
      removed; the document says it is the repository's to edit. Assert against
      the composed text, not against a fixture copy of it, so rewording the
      floor cannot silently drop the rationale — must fail.
- [ ] T007 [P] [US1] (spec US1-S5, FR-013) Test that `ergane init --check`
      against a repo with no standards document reports the absence as a
      readiness finding and writes nothing — no file and no created directory
      (plan trap 5).
- [ ] T008 [P] [US1] (FR-015) Test that `forget` leaves a seeded standards
      document in place while removing Ergane's own artifacts.

### Implementation for User Story 1

- [ ] T009 [US1] (FR-005, FR-016, FR-017) Author the **default floor** as package
      data with a version, resolved `importlib.resources`-first after
      `factory/config.py:44-65`'s pattern, and force-included in
      `pyproject.toml` beside `personas.yaml` — verified by inspecting a built
      wheel, not by reading the config (plan reuse note 7). Write it as a
      starting point the repository owns: a one-line why under every principle,
      and the two that follow from the factory's mechanics phrased as
      consequences (*criteria a judge cannot check against the diff will fail
      no matter how many attempts you spend*) rather than as obligations. The
      wording is the deliverable here, not packaging around it.
- [ ] T010 [US1] (FR-004) Add the composer: floor + an empty named project
      section + governance, a pure function of its inputs so it is testable
      without a repository. Take the floor text and its source as arguments
      rather than reading package data inside it — US4 supplies a different
      source through this same seam.
- [ ] T011 [US1] (FR-001, FR-002, FR-003) Wire the write into the scaffold path
      at `factory/cli/init.py:514/801`: give `standards` a default, refuse to
      overwrite an existing document, create parents only when writing.
- [ ] T012 [US1] (FR-013, FR-015) Add the `--check` finding for an absent
      standards document, and the `forget` exemption.
- [ ] T013 [US1] (SC-001) Run `uv run pytest -q` and confirm passed/skipped match
      T002's baseline; quote both counts, never the warning count.

---

## Phase 3: User Story 2 — The constitution fits the repo it is written into (Priority: P1)

**Goal**: a stack layer chosen for the repository, from pack data, proposed and
overridable.

**Independent Test**: seeding against each shipped stack's fixture produces that
stack's toolchain and commands; a fixture matching no pack produces the
language-agnostic layer.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T014 [US2] (spec US2-S1, FR-007, FR-008) Test that a fixture repo carrying
      a pack's marker files produces that pack's stack layer, and that the
      detected stack is stated to the operator before use.
- [ ] T015 [P] [US2] (spec US2-S2, FR-008) Test that an operator answer overrides
      detection.
- [ ] T016 [P] [US2] (spec US2-S3, FR-009) Test that a fixture matching no pack
      produces the language-agnostic layer and names what the user must complete.
- [ ] T017 [P] [US2] (spec US2-S4, SC-003) Test **mechanically** that every
      shipped pack names only commands valid for its own toolchain and no tool
      belonging to another pack — reading the packs is not evidence (plan trap 8).
- [ ] T018 [P] [US2] (edge case) Test that two stack markers in one repository
      produce a question, not a pick (plan trap 7).
- [ ] T019 [P] [US2] (spec US2-S5, FR-010, SC-004) Test that adding a pack
      changes no file outside the pack data — the selector reads data, not a
      branch per stack.

### Implementation for User Story 2

- [ ] T020 [US2] (FR-010) Add the pack format and the packs chosen in T001, as
      package data, force-included and wheel-verified.
- [ ] T021 [US2] (FR-007, FR-008, FR-009) Generalise `_default_gate_command`
      (`factory/cli/init.py:329`) into pack-driven detection: propose, state,
      allow override, return the agnostic pack when nothing matches and a
      question when several do.
- [ ] T022 [US2] (FR-007) Extend the composer to place the selected stack layer.
- [ ] T023 [US2] (SC-001) Run `uv run pytest -q` and confirm the baseline holds.

---

## Phase 4: User Story 3 — A seeded floor's age is visible (Priority: P2)

**Goal**: the seeded document records its floor version, and `--check` can say
current, behind, or unknown.

**Independent Test**: seed, bump the installed floor version, and `--check`
reports the repository behind, naming both versions and writing nothing.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T024 [US3] (spec US3-S1, FR-011) Test the composed output records the floor
      version it came from, readable by a machine and visible to a human.
- [ ] T025 [US3] (spec US3-S2, FR-012, SC-005) Test that a document recorded at
      floor N, checked against installed floor N+1, is reported behind, names
      both versions, and is not modified.
- [ ] T026 [P] [US3] (spec US3-S3, FR-014) Test that a hand-written document with
      no recorded version is reported unknown, not behind.
- [ ] T027 [P] [US3] (spec US3-S4) Test that a document at the installed floor
      version is reported current.
- [ ] T027a [P] [US3] (spec US3-S5, FR-019) Test that a repository reported
      behind is still reported **ready** — assert readiness directly, not the
      absence of an error string — and that the report's wording does not
      describe the repository as non-compliant. An out-of-date floor is
      information; a user who edited every principle deliberately is behind and
      correct.

### Implementation for User Story 3

- [ ] T028 [US3] (FR-011) Write the version marker into the composed output.
- [ ] T029 [US3] (FR-012, FR-014, FR-019) Add the current/behind/unknown
      determination to `--check`, in `evaluate_repo`'s existing finding
      vocabulary rather than a new report (plan reuse note 6), advisory only —
      it must not reach the readiness verdict.
- [ ] T030 [US3] (SC-001) Run `uv run pytest -q` and confirm the baseline holds.

---

## Phase 4b: User Story 4 — A team brings its own template (Priority: P2)

**Goal**: an operator-supplied template displaces the shipped default, the
source used is recorded, and a bad source is refused rather than silently
replaced.

**Independent Test**: seed from a supplied template and assert the document is
that template's content with none of the shipped default's; seed with no source
and assert the default; point at a missing path and assert a refusal naming it.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T033 [US4] (spec US4-S1, US4-S2, FR-018, SC-007) Test resolution order:
      with a supplied source the written document is that source's content and
      contains none of the shipped default's text; with no source the shipped
      default is used. Assert the *absence* of default text, not just the
      presence of the supplied text — a composer that concatenates both would
      pass the weaker check — must fail.
- [ ] T034 [P] [US4] (spec US4-S3, FR-018) Test that the source that produced the
      document is recorded in the document and stated to the operator, for both
      the supplied and the shipped case — a reader must be able to tell whose
      standards these are.
- [ ] T035 [P] [US4] (spec US4-S4, FR-018) Test that a source that is missing,
      unreadable, or empty is refused at interview time naming the path, and
      that no document is written — specifically assert the shipped default was
      **not** silently substituted (plan trap: empty-answer-means-omit is right
      for an absent answer and wrong for a wrong one).
- [ ] T036 [P] [US4] (spec US4-S5) Test that a supplied template carrying its own
      stack packs has those preferred, with the shipped packs filling only what
      it does not provide.

### Implementation for User Story 4

- [ ] T037 [US4] (FR-018) Add source resolution — supplied, then shipped —
      returning the text and the source together, and the interview question
      that supplies it, until T033–T036 pass. The composer already takes both
      as arguments (T010); this adds a branch in front of it, not a second
      write path.
- [ ] T038 [US4] (SC-001) Run `uv run pytest -q` and confirm the baseline holds.

---

## Phase 5: Verification (operator, by hand — dispatched to no node)

- [ ] T031 Operator: run `ergane init --check` in this repository and confirm it
      reports the existing constitution found and current, and that
      `.specify/memory/constitution.md` is untouched (SC-002) — the check that
      the document every dispatched agent obeys was never at risk.
- [ ] T032 Operator: build a wheel and confirm the floor text and every stack
      pack are inside it (plan reuse note 7). A stranger's install seeds nothing
      if the data did not ship, and defect #103 is the precedent.
