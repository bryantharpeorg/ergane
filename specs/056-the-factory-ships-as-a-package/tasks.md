# Tasks: the factory ships as a package

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution I): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written
in any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm `ergane-cli` is still unclaimed on PyPI before
      dispatch (it was 404 on 2026-08-18; a name can be taken between refinement
      and landing, and every requirement here assumes it is free). Re-verify
      plan.md's reuse inventory anchors. Decide whether the first real publish
      goes to PyPI or TestPyPI, and record which — US3 builds the path but the
      operator triggers it. Correct the plan before deriving, not the nodes
      after.

---

## Phase 2: User Story 1 — The distribution is named what it can be published as (Priority: P1)

**Goal**: distribution renamed to `ergane-cli`, version read from installed
metadata with one declared source, and every other name provably unchanged.

**Independent Test**: build the wheel; its distribution metadata says
`ergane-cli` while its import package is still `factory` and its console script
is still `ergane`; and `--version` reports the metadata version even when that
version differs from any literal in the source.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      passes, and record the passed/skipped counts as the SC-001 baseline.
- [ ] T003 [US1] (spec US1-S1, FR-001) Test that a built wheel's distribution
      name is `ergane-cli` and its version equals the declared version.
- [ ] T004 [P] [US1] (spec US1-S2, FR-002, FR-003, FR-007) Same file: a built
      wheel still contains `factory/` as its import package, with
      `personas.yaml` and `merge_queue_ruleset.json` inside it, and a console
      script named `ergane` pointing at `factory.cli.main`.
- [ ] T005 [US1] (spec US1-S3, FR-004) Test that `_version_text` reports the
      version `importlib.metadata` gives for `ergane-cli`, constructed so the
      metadata version **differs** from any literal in the source — the
      assertion is that the metadata value wins. A test comparing against
      `0.1.0` would pass against the bug and is not acceptable here (plan trap
      3).
- [ ] T006 [US1] (spec US1-S4, FR-006) Test that when the metadata lookup
      fails, `--version` reports the version as unknown and emits no
      version-shaped literal.
- [ ] T007 [P] [US1] (spec US1-S5, FR-013) Test that the branch namespace is
      still `factory/<epic>/<node>`, asserted against a literal, and that the
      Temporal namespace default is unchanged.

### Implementation for User Story 1

- [ ] T008 [US1] (spec US1-S1, FR-001) Change `pyproject.toml:2` to
      `name = "ergane-cli"`, leaving `packages = ["factory"]` and the
      force-include block untouched.
- [ ] T009 [US1] (spec US1-S3, US1-S4, FR-004, FR-006) Change
      `factory/cli/main.py:135` to look up `"ergane-cli"`, and replace the
      `except Exception: pkg_version = "0.1.0"` fallback with one that reports
      the version as unknown, so no literal can be mistaken for a real version.
- [ ] T010 [US1] (FR-005, SC-002) Make the declared version the single source:
      remove the shadowing literal so `pyproject.toml` is the only place a
      version is written.
- [ ] T011 [US1] (SC-001) Run `uv run pytest -q` and confirm passed/skipped
      match T002's baseline; quote both counts, never the warning count.

---

## Phase 3: User Story 2 — A stranger installs it and it works (Priority: P1)

**Goal**: the built artifact works on a machine that has never held this
repository.

**Independent Test**: install the wheel into a clean virtual environment with no
checkout of this repository on any parent path; `ergane --version` prints the
built version and a persona-registry read succeeds from inside the package.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T012 [US2] (spec US2-S1, FR-008) Test that builds the wheel, installs it
      into a temporary environment located where **no parent directory holds a
      `personas.yaml`** (plan trap 6 — otherwise the checkout-walk fallback
      hides a packaging break), then asserts `ergane --version` exits zero with
      the built version.
- [ ] T013 [US2] (spec US2-S2, FR-008) Extend that test to resolve the persona
      registry in the installed environment and assert the path it resolves is
      inside the installed package, not a repository root.
- [ ] T014 [P] [US2] (spec US2-S4) Test that installing this distribution into
      an environment that already provides a distribution named `ergane`
      succeeds — the two are distinct distribution names and must not collide.

### Implementation for User Story 2

- [ ] T015 [US2] Make the tests pass, changing packaging configuration only if
      it is genuinely broken — if a test already passes on first run, that is
      the defect case named above, not a task to skip.
- [ ] T016 [US2] (spec US2-S3, SC-004) Commit the run's output as pasted
      evidence under this spec's `evidence/` directory, including the
      interpreter path inside the temporary environment. The judge sees only the
      diff, so an uncommitted terminal proves nothing.

---

## Phase 4: User Story 3 — Publishing is a repeatable act the operator triggers (Priority: P2)

**Goal**: metadata fit for a public index, and a release path that no agent and
no ordinary CI run can fire.

**Independent Test**: the release path builds and validates the artifact without
contacting the real index, and the metadata a public index would display is
present and identifies this project.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T017 [US3] (spec US3-S1, FR-009, FR-010) Test that built distribution
      metadata carries a description, a readme, a license and project URLs
      identifying this project, and does not describe itself in terms
      confusable with the unrelated `ergane` distribution on PyPI.
- [ ] T018 [P] [US3] (spec US3-S2) Test that the release path, run with no index
      credential present, builds and validates the artifact and stops before the
      publish step — rather than failing partway and leaving a partial release.
- [ ] T019 [P] [US3] (spec US3-S4, FR-012) Test that a version tag disagreeing
      with the declared version is refused before any upload step is reached.
- [ ] T020 [P] [US3] (spec US3-S3, FR-011, SC-005) Test that no workflow in
      `.github/workflows/` can publish on a branch push, a pull request, or a
      merge-group event — publishing is reachable only from an explicit operator
      action on a version tag.

### Implementation for User Story 3

- [ ] T021 [US3] (spec US3-S1, FR-009) Add the metadata keys to
      `pyproject.toml`: description, readme, license, project URLs, authors.
- [ ] T022 [US3] (spec US3-S2, US3-S3, FR-011) Add the release workflow: build,
      validate, and a publish step gated behind an operator-triggered tag event,
      stopping cleanly before publishing when no index credential is present.
- [ ] T023 [US3] (SC-001) Run `uv run pytest -q` and confirm passed/skipped
      still match the Phase 2 baseline.

---

## Phase 5: Verification (operator, by hand — dispatched to no node)

- [ ] T024 Operator: run `ergane spec landed specs/<a-landed-spec>
      --default-branch ergane-buildout` before and after this epic and confirm
      the story-to-commit mapping is identical (SC-003) — the check that the
      attribution grammar was untouched.
- [ ] T025 Operator: trigger the first real publish, on a tag, to the index
      chosen in T001. This step is deliberately outside the graph: it is
      irreversible, and no dispatched agent may perform it.
