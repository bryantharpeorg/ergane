# Tasks: the operator's manifest is not a frozen fixture

**Spec**: `specs/121-the-operators-manifest-is-not-a-frozen-fixture/spec.md`
**Plan**: `specs/121-the-operators-manifest-is-not-a-frozen-fixture/plan.md`

Read the plan's traps before the first task. Trap 1 (do not delete the
live-manifest load — it is the only thing that catches a stale `standards` path
before a live dispatch), trap 2 (the version assertion is not the whole defect;
`ladder=VerificationConfig()` in the identity test fails a declared ladder on its
own), trap 3 (a green suite is not the requirement — preserved coverage is) and
trap 7 (US1-S6 is the anti-recurrence guard and is the task most likely to be
skipped) are the four that decide whether this attempt lands.

One more thing to hold in mind throughout: this repository's gate is
`uv run pytest -q`. A red suite here is a red *gate*, so an attempt that leaves
the suite failing does not merely fail its own verification — it fails every
node of every epic that follows.

## Phase 1: User Story 1 — The live manifest is checked for validity, not for content

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, trap 2) In
      `tests/test_121_manifest_is_not_a_fixture.py`, write the scenario the whole
      spec exists for: a manifest declaring a `ladder:` block parses and the
      suite's live-manifest assertions still pass. Drive it against a copy of
      the repo manifest with a ladder appended, so the test does not depend on
      the operator having declared one.
- [ ] T002 [P] [US1] (spec US1-S2, FR-001) Assert that no live-manifest test
      names a schema version. Today `tests/test_factory_yaml.py:465` reads
      `assert config.version == 1`.
- [ ] T003 [P] [US1] (spec US1-S3, FR-004, trap 1) **The control.** Assert a
      manifest whose declared `standards` path does not exist still fails,
      naming the missing file. This coverage must survive the story.
- [ ] T004 [P] [US1] (spec US1-S4, FR-005, trap 4) Assert the v1 parse-shape
      regression still fails when v1 semantics move — now against the committed
      sample, and assert the sample is a **v1** manifest so a later copy of a v2
      `ergane.yaml` cannot quietly replace it.
- [ ] T005 [P] [US1] (spec US1-S5, FR-006) Assert the FR-011 invariant still
      holds: a node's worktree manifest differing from the landing branch's is
      refused, naming the file.
- [ ] T006 [P] [US1] (spec US1-S6, FR-007, trap 7) **The anti-recurrence guard.**
      Assert that every remaining assertion against the *live* manifest follows
      from validity rather than from choice — read the assertions themselves.
      This finding has returned four times because each fix removed one literal;
      this is the task that makes the fifth attempt fail a test instead of
      surprising an operator.

### Implementation for this story

- [ ] T007 [US1] (FR-005, trap 4) Add a v1 sample manifest under
      `tests/fixtures/target_repo/manifests/`, named for the condition it
      demonstrates as its eleven neighbours are. Its committed bytes are the
      frozen thing.
- [ ] T008 [US1] (FR-002, FR-005, traps 2 and 3) Repoint
      `test_v1_identity_against_erganes_own_manifest`
      (`tests/test_factory_yaml.py:1660-1677`) at that sample. Keep the
      field-for-field comparison — it is the parser regression fixture spec 023
      put there and FR-007 forbids dropping it.
- [ ] T009 [US1] (FR-001, FR-003, traps 1 and 6) In
      `test_erganes_own_manifest_loads` (`:454`), remove the version assertion
      and keep the load. Leave the `gates`, `standards` and `landing_branch`
      assertions alone — the comment at `:470-476` records why the
      `landing_branch` line is deliberate, and trap 6 explains why these are not
      the same kind of thing as a pinned version.
- [ ] T010 [US1] (trap 5) Run `tests/test_forge_manifest.py` and confirm the new
      sample is inert there. Its `FIXTURE_MANIFESTS` rglobs `*.yaml` beneath
      `tests/fixtures/target_repo/`, so the sample joins a corpus this story
      never reads.

### The operator's demonstration for this story

- [ ] T011 [US1] Run the sequence in the plan's § *Verification the operator will
      run*, which declares a real `ladder:` block in `ergane.yaml`, proves the
      suite green with it, prints the parsed ladder, and restores the file.
      Paste **both** the before and after runs into the attempt report — either
      alone proves nothing, because a suite that was already green proves no fix
      and a suite green only afterwards proves no regression was avoided. Before
      this spec the second run fails with `assert 2 == 1` and a `FactoryConfig`
      identity mismatch on `version` and `ladder`.
