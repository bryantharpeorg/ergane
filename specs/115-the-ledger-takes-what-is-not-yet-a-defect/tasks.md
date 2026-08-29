# Tasks: the ledger takes what is not yet a defect

**Input**: `spec.md` and `plan.md` in this directory, both drafted 2026-08-28
against ergane-buildout at 8bb2d4b.

Tests are written first and must fail before their implementation task runs.
`[P]` marks tasks that can proceed in parallel within their story because they
touch independent test functions. No `[P]` spans stories — all three stories edit
`add_findings_parser` (`factory/cli/doctor.py:251-350`) and are serialised for
that reason.

## Phase 1: User Story 1 — The write verb says it writes

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001) Identical-row test, in a new
  `tests/test_115_us1_record_verb.py`: against one scratch store, file the same
  finding through `record` and — in a second scratch store — through `report`,
  and assert every column of the resulting row matches, including `occurrences`,
  `first_seen` and the `finding_events` trail. Assert against the store, not the
  parser: the claim FR-002 makes is that behaviour did not change, and only the
  row can prove that.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Stderr-deprecation test: run
  `findings report`, assert the exit status equals `record`'s, assert the
  deprecation line names `record` and appears on **stderr**, and assert stdout is
  byte-identical to `record`'s. Stdout for this noun is parsed —
  `findings list --json` and `findings triage --json` both exist — so a notice
  there is a breaking change wearing a helpful face (plan FR-002).
- [ ] T003 [P] [US1] (spec US1-S3, FR-003) Completion-output test: run
  `ergane completion bash` and `ergane completion zsh`, assert `record` is
  offered for the `findings` noun and `report` is not. Assert on the emitted
  script, never on whether the parser has an alias — the alias exists, and that
  is exactly why the naive assertion passes while completion advertises the dead
  name (plan T4, and § *The alias trap, measured*).
- [ ] T004 [P] [US1] (spec US1-S3, FR-003) Help-text test: assert `report`
  appears in neither `ergane findings --help` nor `ergane findings record
  --help`.
- [ ] T005 [P] [US1] (spec US1-S4, FR-004) Prose-guard test: assert the string
  `findings report` appears in no operator-facing markdown — at minimum
  `CLAUDE.md`, `docs/architecture.md`, `README.md` and `.claude/skills/**`. The
  guard must fail closed: prove it by asserting it turns red against a fixture
  string, because a sweep that finds nothing because its own discovery found no
  files is a sweep this repository has shipped before.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002) In `factory/cli/doctor.py:276-293`: register
  `record` as the write verb with today's arguments and runner, and register
  `report` so it runs the same command function, emits its deprecation to stderr,
  and does not surface in help. Either mechanism — argparse `aliases=`, or a
  second `add_parser` sharing a `parents=` parent — is acceptable; both leak into
  completion, which T007 fixes.
- [ ] T007 [US1] (FR-003) In `_noun_and_verb_map`
  (`factory/cli/completion.py:32-64`): at `:53`, emit one name per distinct
  subparser object instead of every key of `_name_parser_map`. Grouping by
  `id(parser)` recovers the canonical name because `add_parser` registers it
  before any alias — the transcript in `plan.md` shows both the leak and the fix.
- [ ] T008 [US1] (FR-004) Update `CLAUDE.md:106`, `docs/architecture.md:518` and
  `.claude/skills/away-mode/SKILL.md:158` to name `record`, and update the verb
  tuple at `tests/test_ergane_env_completion.py:120`. That tuple spells the verb
  as a bare `"report"` and is the one call site a grep for `findings report` does
  not surface (plan T8).

### Verification for this story

- [ ] T009 [US1] (spec US1-S1, spec US1-S3, SC-001) Paste into the PR: the two
  rows produced by `record` and `report` shown identical; the deprecation line
  captured from stderr with stdout shown clean beside it; the `findings)` line of
  `ergane completion bash` before and after, against the recorded baseline
  `list promote report resolve triage`; and the full-suite before-and-after
  counts.

## Phase 2: User Story 2 — A want is not a defect, and the ledger can tell

### Tests for this story (write FIRST, must fail)

- [ ] T010 [US2] (spec US2-S1, FR-006) Withheld-count test, in a new
  `tests/test_115_us2_feedback_lane.py`: with a scratch store holding both defect
  rows and `feedback/` rows, run `findings list` with no flags and assert the
  feedback rows are absent **and** that the output states how many were withheld
  and names the flag that shows them. Assert on the count as a number read from
  the store, not a literal — a hardcoded "2 withheld" passes against a fixture
  and lies against a real ledger (plan T5).
- [ ] T011 [P] [US2] (spec US2-S2, FR-005) Composed-filter test: assert
  `--category` filters on the `category` column, and that it composes with
  `--severity` and `--status` rather than replacing either. Include the
  `--category feedback` and `--all` cases in the same test's matrix so the three
  views are pinned together.
- [ ] T012 [P] [US2] (spec US2-S3, FR-007) Probe-lane guard, two halves: assert
  no probe in `REGISTRY` (`factory/doctor/probes.py:628`) files into the reserved
  category; then append a throwaway probe that does, inside the test, and assert
  the guard turns red. Only the second half proves the guard is not vacuous.
- [ ] T013 [P] [US2] (spec US2-S4, FR-008) Triage-separation test: classify a
  store holding a feedback row whose summary shares wording with three defect
  rows, and assert the feedback row is reported under its own heading and appears
  in no fragmented class from `_fragmented_groups`
  (`factory/doctor/triage.py:444`). Assert the cold rule and the
  closed-by-a-landed-spec rule still reach it — FR-008 excludes the folding
  alone, not the classification.
- [ ] T014 [P] [US2] (FR-006, plan T1) One-constant test: assert the CLI, the
  triage module and both guards resolve the reserved category name from a single
  imported constant, by identity. Three literals spelling `"feedback"` agree on
  the day they are written and diverge on the day one is edited.

### Implementation for this story

- [ ] T015 [US2] (FR-005, FR-006) In `findings_list_command`
  (`factory/cli/doctor.py:368-392`): add `--category` and `--all` beside the two
  filters already applied there, and emit the withheld-count line. Filter in the
  command, not in `list_findings` (`factory/doctor/store.py:454`) — that function
  takes no arguments today and changing its signature is not this story's job.
- [ ] T016 [US2] (FR-007, FR-008) Add the reserved-category constant in one
  module; import it from the CLI, the triage module and both guards. In
  `factory/doctor/triage.py`: add the separate heading and exclude the reserved
  category from `_fragmented_groups` (`:444`).

### Verification for this story

- [ ] T017 [US2] (spec US2-S1, spec US2-S2, spec US2-S3, SC-002) Paste into the
  PR: `findings list` with the lane hidden and the withheld count visible, then
  with `--category feedback`, then with `--all`; the probe guard failing against
  the deliberately mislabelled probe; the triage output showing a feedback row
  under its own heading and absent from every fragmented class; and the
  full-suite before-and-after counts.

## Phase 3: User Story 3 — Getting it out again hands over the evidence

### Tests for this story (write FIRST, must fail)

- [ ] T018 [US3] (spec US3-S1, FR-009) Read-only test, in a new
  `tests/test_115_us3_draft_brief.py`: snapshot the whole store — every row and
  every `finding_events` row — run `findings draft`, and assert the snapshot is
  unchanged. Then run it a second time and assert the brief is byte-identical. A
  queue-reading verb that mutates the queue cannot be run twice to see what it
  says.
- [ ] T019 [P] [US3] (FR-009, plan T2) Not-wrapped test: assert `draft` does not
  go through `_with_store` (`factory/cli/doctor.py:353-365`), which runs
  `_resolve_promoted_findings` — a write — before every verb it wraps. Assert by
  driving a store that has a promoted finding whose spec has landed, and proving
  `draft` did not close it. `triage` faced this same decision and the reasoning
  is written out at `factory/cli/doctor.py:340-347`.
- [ ] T020 [P] [US3] (spec US3-S2, FR-010) Full-evidence test: file a finding,
  report it twice more across two `seen_at` values, then assert the brief carries
  every stored column and every event from `list_events`
  (`factory/doctor/store.py:493`) — asserting on `occurrences == 3` and on both
  distinct dates, because those are what separate a passing thought from a
  standing complaint.
- [ ] T021 [P] [US3] (spec US3-S3, FR-011) Contract-from-templates test: assert
  the brief's statement of the trio's shape is derived at runtime from
  `.specify/templates/spec-template.md`, `plan-template.md` and
  `tasks-template.md`, and that the brief names `ergane spec validate` as its
  acceptance test. Prove the derivation by mutating a template in a scratch tree
  and asserting the brief changes — a test that only checks the words are present
  passes against a hardcoded copy, which is the drift this requirement exists to
  prevent (plan T7).
- [ ] T022 [P] [US3] (spec US3-S4, FR-012) No-invocation test: with
  `LITELLM_PROXY_URL`, `LITELLM_MASTER_KEY`, `TEMPORAL_ADDRESS` and
  `TEMPORAL_NAMESPACE` removed and network calls made to raise, run `draft` and
  assert it succeeds, that nothing was written under `specs/`, and that no
  subprocess was spawned. Assert on behaviour under a stripped environment, not
  on the absence of an import (plan T6).

### Implementation for this story

- [ ] T023 [US3] (FR-009, FR-010, FR-011, FR-012) Add the `draft` verb to
  `add_findings_parser` (`factory/cli/doctor.py:251-350`) and its command
  function: read the named findings and their events, render one brief carrying
  every column and the full trail plus the trio contract read from
  `.specify/templates/`, write it to a path under the resolved runtime root and
  print that path. Wire it outside `_with_store`.

### Verification for this story

- [ ] T024 [US3] (spec US3-S1, spec US3-S2, SC-003) Paste into the PR: a written
  brief for a finding reported three times, with its event trail visible; the
  store snapshot before and after showing no change; the second invocation's
  brief shown identical to the first; and the full-suite before-and-after counts.

## What no task here can prove

Every task above runs offline against scratch stores. **None of them proves the
brief is useful**, because usefulness is a property of what a drafting agent does
with it, and no gate runs a drafting agent.

That proof is the operator verification in `plan.md`: take a want that has been
sitting in cross-session memory rather than in the tree, file it into the lane,
run `draft` over it, hand the brief to a drafting session, and compare what comes
back against what the bare spec template would have produced. If the difference
is small, the deferred schedule should stay deferred and the honest conclusion is
that the queue earns its keep and the drafter does not yet earn automation.

One boundary this file will not blur: **no task here invokes an agent, adds a
Temporal schedule, or migrates the store's schema.** All three are named as out
of scope in `spec.md`, and each has a specific cheaper-looking version that
reintroduces what the spec was written to avoid — a second node lifecycle
(plan T6), an unattended drafter writing specs nobody asked for, and a migration
spent on a lane that has not yet proved it is used (plan T3).
