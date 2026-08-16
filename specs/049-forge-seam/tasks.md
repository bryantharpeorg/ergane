# Tasks: 049-forge-seam

Six stories in a straight chain: US1 → US2 → US3 → US4 → US5 → US6. Work
test-first and commit once per task. Read plan.md before the first commit — trap
1 (renaming is not seaming), trap 3 (a recording fake makes every test vacuous)
and trap 5 (the shipped package cannot spell `enforcement`) are the three that
cost a rejected attempt each if met late.

**Phase 1 is the largest and the one at risk of the 61,440-byte refusal.** Read
trap 10 before starting it. The first budget to spend is redundant evidence —
duplicated coverage and over-long pasted output — not scope. If scope must go it
goes **by door** (one seam replaced *and* its old construction deleted, in one
diff), never by deferring T011's deletions to a later story: that would leave two
factories live for one boundary between landings, which is the defect trap 14
exists to prevent.

## Phase 1: User Story 1 — Onboarding reads the repository through a forge, not through `gh`

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] Write the interface-shape test FIRST: read the protocol's
      own members and assert it declares exactly the reading operations and no
      others, and that no operation classifies, decides, retries or settles
      (spec US1-S1, FR-001; model `tests/test_messenger_adapter.py:503-518`,
      but see plan trap 9) — must fail.
- [ ] T002 [P] [US1] Write the fake forge FIRST, as a **model of a repository**:
      reads served from mutable state, writes changing it, unmodelled calls
      raising. Model it on `FakeGitHub` (`tests/test_ergane_init_wiring.py:113`,
      `:214-238`). Do **not** model it on or build it over `tests/fake_gh.py:62`
      — that fake never consumes a matched expectation
      (`ci/the-scripted-gh-fake-never-consumes-an-expectation`), so the first
      match answers a command forever and idempotence claims made through it
      cannot fail (plan trap 3). Do not fix that fake here either; it is out of
      scope by name.
- [ ] T003 [US1] Write the judged-model test FIRST: configure the fake as a
      repository that fails readiness, run the factory's own `evaluate_repo`
      against it, assert it fails; mutate the model to satisfy the questions and
      assert the same judgment passes it — the primary assertion is the profile,
      never the call log (spec US1-S3, FR-004) — must fail.
- [ ] T004 [P] [US1] Write the byte-identity test FIRST: the `github` forge
      resolved against the existing scripted `gh` produces today's
      `TargetRepoProfile` — assert against the existing onboarding expectations
      with no assertion rewritten (spec US1-S2, FR-003, SC-001) — must fail.
- [ ] T005 [P] [US1] Write the unknown-name test FIRST: resolving a forge nothing
      is registered under raises and names the registered forges; it never falls
      back to the default (spec US1-S4, FR-002) — must fail.
- [ ] T006 [P] [US1] Write the conformance suite FIRST, parametrized over the
      *registry's own* forge names rather than a literal list, plus the
      anti-vacuity assertion that the parametrization is non-empty (spec US1-S1,
      FR-005, plan traps 4 and 9) — must fail. Do not inherit 041's shape:
      `ci/the-adapter-conformance-suite-is-a-hardcoded-list-of-one` records that
      its three conformance tests are parametrized over the literal
      `["telegram"]`, so a second adapter would ship unchecked.
- [ ] T007 [P] [US1] Write the dependency test: `pyproject.toml` declares nothing
      new (spec US1-S5, FR-018) — must pass before and after; it pins the
      constraint.

### Implementation for this story

- [ ] T008 [US1] Create the forge modules **inside `factory/mergequeue/`**
      (FR-017 — settled, not a route choice: the merge-surface guards are scoped
      to that directory, plan trap 6), with the protocol's reading half —
      describe the repository, and report a branch's landing policy — plus the
      name→builder registry, `github` as the value when nothing names one, and a
      raise on an unregistered name (FR-001, FR-002). Mirror
      `factory/notify/adapter.py:134-227` in structure. Do not name anything with
      a word from `tests/test_final_sweep.py:462` (plan trap 5).
- [ ] T009 [US1] Implement the `github` forge over the existing `GhClient`
      (`factory/mergequeue/gh.py:131`), registering itself the way
      `factory/notify/service.py:311` does. Move `_queue_from_rules`
      (`merge_activities.py:696`) and `_classic_contexts` (`:729`) into it —
      they are GitHub payload parsers, not shared activity logic (FR-003).
- [ ] T010 [US1] Rewire `onboard_target_repo` (`merge_activities.py:589`) to
      gather through a resolved forge, and move all three construction seams —
      `merge_activities.py:296`, `factory/workgraph/cli.py:70`,
      `factory/cli/init.py:80` — to resolve a forge by name (FR-003, plan
      trap 14). `evaluate_repo`'s findings do not change in this story.
- [ ] T011 [US1] Delete each `GhClient` construction seam in the same diff that
      replaces it — `merge_activities.py:296`, `factory/workgraph/cli.py:70`,
      `factory/cli/init.py:80` — so no file ever holds two module-level factories
      for this boundary. On 2026-08-16 two concurrent 034 stories each added a
      `_gh_client_factory` to `factory/cli/init.py` in different regions; there
      was no textual conflict, the merge kept both, the second shadowed the
      first, and nine tests died (plan trap 14). Update the three test modules
      that bind them: `tests/test_merge_activities.py:133` and siblings,
      `tests/test_ergane_ports.py:214`, `tests/test_ergane_init_check.py:145`
      and `:150`.

## Phase 2: User Story 2 — The readiness questions are forge-neutral, and D-007 belongs to GitHub

### Tests for this story (write FIRST, must fail)

- [ ] T012 [US2] Write the no-visibility test FIRST: a repository model that
      gates landing on named checks, lands without a human, requires exactly the
      declared gates and titles the landing commit from the proposal — and
      reports no visibility fact at all — passes readiness (spec US2-S1, SC-002)
      — must fail.
- [ ] T013 [US2] Write the **control** FIRST: the same model with its gating
      removed fails readiness, so the neutral question is shown to decide an
      outcome rather than the case having been impossible (SC-003, plan trap 4)
      — must fail.
- [ ] T014 [P] [US2] Write the D-007 test: the GitHub forge and a private
      repository still fail, with the same remedy an operator reads today, and
      the finding is authored in the GitHub implementation (spec US2-S2, FR-007)
      — must fail.
- [ ] T015 [P] [US2] Write the source test: `factory/mergequeue/onboard.py`
      names no merge queue, no repository visibility and no squash-title setting
      (spec US2-S3, FR-006) — must fail.
- [ ] T016 [P] [US2] Write the separability test: a forge that gates on named
      checks but will not land without a human fails with a finding distinct
      from the gating finding (spec US2-S4) — must fail.
- [ ] T017 [P] [US2] Write the sole-author regression case: the guard at
      `tests/test_ergane_init_check.py:441` still passes — `gate_check:`,
      `unknown_check:` and 034's local facts stay authored by the shared
      judgment (spec US2-S5, FR-008, plan trap 7) — must pass before and after.

### Implementation for this story

- [ ] T018 [US2] Rewrite `evaluate_repo`'s checks (`onboard.py:174`, `:190`,
      `:225`) as the neutral questions Q1–Q5, reading the forge's landing-policy
      record. Keep `factory_yaml` (`:209`), the parity checks (`:255`, `:272`)
      and `evaluate_init_facts` (`:287`) exactly where they are (FR-006,
      FR-008).
- [ ] T019 [US2] Move the D-007 visibility finding into the GitHub
      implementation as a forge-contributed finding, carrying the remedy verbatim
      from `onboard.py:179-186`, and have the shared judgment append it
      (FR-007). Keep the report's reading order stable for
      `_render_onboard` (`factory/workgraph/cli.py:400`).
- [ ] T020 [US2] Update `tests/test_onboard.py`'s table to the neutral
      questions, keeping it pure — no fakes, no `gh`, no filesystem.

## Phase 3: User Story 3 — The landing path proposes, lands and observes through the forge

### Tests for this story (write FIRST, must fail)

- [ ] T021 [US3] Write the landing round trip FIRST, against the fake forge:
      find, open, request landing, observe merged, observe rejected, withdraw
      (spec US3-S1, FR-009) — must fail.
- [ ] T022 [P] [US3] Write the no-`gh` test: no landing activity constructs a
      client or names `gh`, asserted against the module source, and the existing
      landing suite passes unmodified (spec US3-S1, FR-009) — must fail.
- [ ] T023 [US3] Write the conflict test FIRST: a forge reporting a proposal in
      conflict yields `CONFLICT` from a neutral fact, plus a source assertion
      that `factory/mergequeue/classify.py` contains no forge-native status
      literal (spec US3-S2, FR-010) — must fail.
- [ ] T024 [P] [US3] Write the replay case: a `PrSnapshot` serialized before this
      spec deserializes unchanged and classifies identically (spec US3-S3,
      FR-010, plan trap 8) — must fail if a new field lacks a default.
- [ ] T025 [P] [US3] Write the workflow-untouched test: the epic workflow imports
      and calls exactly what it does today (spec US3-S4, FR-011, SC-004, plan
      trap 2) — must pass before and after; it pins the fence.
- [ ] T026 [P] [US3] Write the merge-surface case: the structural guards still
      hold over the moved code — no branch deletion, no forced push, only the
      automatic merge form (spec US3-S5, FR-017, plan traps 6 and 11) — must
      pass before and after.

### Implementation for this story

- [ ] T027 [US3] Add the landing half of the protocol — find a proposal, open
      one, request landing, observe, withdraw, fetch failing-check evidence —
      and implement it on the `github` forge over `GhClient`'s existing methods
      (`gh.py:149`, `:163`, `:184`, `:197`, `:202`, `:208`, `:229`). Carry
      `enqueue_pr`'s no-strategy-flag behaviour across verbatim (plan trap 11).
- [ ] T028 [US3] Rewire `open_landing_pr`, `enqueue_landing`, `poll_landing`,
      `disable_auto_merge` and `fetch_check_failure`
      (`factory/activities/merge_activities.py:357`, `:400`, `:417`, `:424`,
      `:505`) onto the forge (FR-009).
- [ ] T029 [US3] Add the neutral conflict fact to `PrSnapshot`
      (`factory/mergequeue/models.py:138`) with a default, set it in the GitHub
      observation, and have `classify` (`classify.py:74`) decide from it.
      `auto_merge_requested` still decides nothing (plan trap 12).

## Phase 4: User Story 4 — Wiring a repository is a forge operation

### Tests for this story (write FIRST, must fail)

- [ ] T030 [US4] Write the wire-then-judge round trip FIRST against the fake
      repository model: wiring mutates it, and the factory's own `evaluate_repo`
      then passes it — the assertion is the judged state, never the call log
      (spec US4-S1, FR-012; the pattern is
      `tests/test_ergane_init_wiring.py:348`, `:367-396`) — must fail.
- [ ] T031 [P] [US4] Write the idempotence case: a second run reports every act
      already satisfied and mutates nothing, asserted against the **repository
      model's** mutation list (spec US4-S2) — must fail. It may not be routed
      through `tests/fake_gh.py`: an idempotence claim tested there is
      unfalsifiable by construction (plan trap 3).
- [ ] T032 [P] [US4] Write the refusal case: a forge whose credentials cannot
      change settings refuses before any write, carrying the by-hand steps, and
      nothing was mutated (spec US4-S3, FR-013) — must fail.
- [ ] T033 [P] [US4] Write the CLI case: `--wire` resolves a forge by name rather
      than constructing a client, and the existing `--wire` suite passes with no
      assertion changed (spec US4-S4) — must fail.

### Implementation for this story

- [ ] T034 [US4] Add the wiring operation to the protocol and implement it on the
      `github` forge by moving `wire_repo` (`factory/mergequeue/wiring.py:258`)
      behind it — not reverting it, not rewriting it (FR-012). Keep
      `merge_queue_ruleset.json`'s role as the data file that spells what the
      shipped package may not (plan trap 5), and keep `WiringRefused` (`:78`) as
      the refusal shape (FR-013).
- [ ] T035 [US4] Rewire `factory/cli/init.py:471` and `:706` to resolve a forge,
      leaving the report format and the manual steps (`wiring.py:117`) as they
      read today.

## Phase 5: User Story 5 — The forge is declared in the manifest, and an unknown forge is refused before dispatch

### Tests for this story (write FIRST, must fail)

- [ ] T036 [P] [US5] Write the known-forge case FIRST: a fixture manifest
      declaring `forge: github` parses and resolves to `github` (spec US5-S1,
      FR-014) — must fail.
- [ ] T037 [P] [US5] Write the unknown-forge case FIRST: a fixture manifest
      declaring an unregistered forge is refused with the registered names
      listed — never a silent fallback (spec US5-S2, FR-014) — must fail.
- [ ] T038 [P] [US5] Write the absent-key case: a manifest declaring no forge
      resolves to `github`, and every existing manifest fixture parses unchanged
      (spec US5-S3, FR-014) — must fail only if the default breaks.
- [ ] T039 [P] [US5] Write the scope-fence case: this repository's own
      `ergane.yaml` is unchanged by this story's diff (spec US5-S4, FR-015, plan
      trap 13) — must pass before and after.

### Implementation for this story

- [ ] T040 [US5] Add `forge` to `_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:86`) with a reader that defaults to
      `github` and refuses an unregistered name, following `_read_landing_branch`'s
      shape (FR-014). **Do not add the key to this repository's `ergane.yaml`** —
      the config gate parses with the worker's installed parser, and 020/US1 died
      four times on exactly this (plan trap 13).
- [ ] T041 [US5] Have every door that resolves a forge — onboarding, landing,
      wiring — read the manifest's declared name, keeping the default path
      byte-identical for a manifest that declares nothing.

## Phase 6: User Story 6 — The seam cannot silently re-leak

### Tests for this story (write FIRST, must fail)

- [ ] T042 [US6] Write the vocabulary sweep FIRST: forge-native terms appear in
      the shipped package only in the modules an explicit **path** allowlist
      names (spec US6-S1, FR-016) — must fail against a deliberately planted
      term, then pass once it is removed.
- [ ] T043 [P] [US6] Write the anti-vacuity assertion: the sweep asserts its own
      file list is non-empty and contains the forge implementation (spec US6-S2,
      FR-016, plan trap 4; precedent `tests/test_final_sweep.py:644`) — must
      fail if the glob matches nothing.
- [ ] T044 [P] [US6] Write the guard-coverage case: every forge module appears in
      `tests/test_mergequeue_sweep.py`'s `COMMAND_MODULES` (`:52-58`) *because it
      lives under `factory/mergequeue/`*, with no path added to the swept set by
      this spec — assert both halves, since "covered" and "covered by
      construction" are different claims and only the second survives the next
      refactor (spec US6-S3, FR-017, plan trap 6) — must fail if a forge module
      is moved out of the directory.
- [ ] T045 [P] [US6] Write the reserved-vocabulary case: nothing this spec added
      spells a word from `tests/test_final_sweep.py:462` (spec US6-S4, plan
      trap 5) — must pass before and after.

### Implementation for this story

- [ ] T046 [US6] Land the sweep with its path allowlist and its coverage
      assertion, and record in the module docstring which modules are allowed to
      name a forge natively and why (FR-016, FR-017).

## Verification

- [ ] Final gate command passes green.
