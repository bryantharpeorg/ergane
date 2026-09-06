# Tasks: the operator's skills arrive with the CLI

Read `plan.md` before starting. Trap 1 is the one that must be settled before a
line of the verb is written: the word `skills` is already a reserved per-persona
field, and the ruling in `CONTEXT.md` comes before the name, not after it. Trap 2
names the two packaged-data mechanisms this tree already has and forbids a third.
Trap 5 is why the staleness check compares **package versions** and never the
revision string, which is `unknown` on every wheel install. Trap 6 records that
`specs/139-a-scaffolded-repo-arrives-with-the-context-its-agents-need` supersedes
this spec's target-repository ruling for the target-repo agent-context unit alone
— it is a narrowing already written down, not a contradiction to stop on. Trap 7
is why nothing here counts skills: the payload was five on 2026-08-22 and is six
now. Trap 9 is why a wheel, not `pyproject.toml`, is the thing US1's test reads.
Trap 10 is the design decision the whole install/teardown pair rests on: the
record of what Ergane wrote is content digests under Ergane's own state root,
never a timestamp and never a file inside the skills directory.

Tests are written first and must fail before the implementation that satisfies
them — except the tasks marked **The control**, which assert non-regression and
are green from the first commit; do not manufacture a failure for those. Every
acceptance scenario is provable from the diff, which is all the judge sees;
runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The skills ship inside the wheel

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, traps 7 and 9) Build a wheel and read
      its contents, asserting that every skill directory the repository ships
      under `.claude/skills/` is present with its `SKILL.md` and every other file
      it carries — `build-metrics` has `scripts/` and `reference/`, `spec-html`
      has `render.py`, so a `*/SKILL.md` assertion passes on a broken payload —
      and that **no** `__pycache__` entry travels with them. Derive the expected
      set from the repository rather than from a literal tuple (trap 7), the way
      `tests/test_057_us2_stack_pack.py:296` —
      `test_every_shipped_pack_travels_in_the_wheel` derives its own from
      `resolve_stack_packs()`. Reuse `tests/test_distribution_install.py:39` —
      `_build_wheel` and `tests/test_distribution_rename.py:116` —
      `_wheel_contents`; do not build a wheel by hand and do not assert against
      `pyproject.toml`, which is green on a `force-include` entry hatchling
      silently dropped (trap 3).
- [ ] T002 [P] [US1] (spec US1-S2, FR-003, trap 3) Assert that the release
      workflow's validation step names the skills payload: read
      `.github/workflows/release.yml` and require a guard beside the existing
      `factory/personas.yaml` one at `.github/workflows/release.yml:83-86`. The
      workflow step itself runs only on a tag push and the declared `test` gate
      never reaches it, so this committed assertion is the only thing that keeps
      the guard from being deleted by accident.
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) **The control.** Assert that in a
      development checkout, with no wheel built, the resolver returns the same
      skills from their source location by the checkout fallback
      `factory/config.py:98-101` uses. Green from the first commit; do not
      manufacture a failure for it.

### Implementation for this story

- [ ] T004 [US1] (FR-001, trap 2) Add one entry to the force-include table at
      `pyproject.toml:80` mapping `.claude/skills` into the package, beside the
      four entries already there. Read `pyproject.toml:74-79` first: the stack
      packs are deliberately **absent** from that table because they already live
      inside the import package, and `.claude/skills/` is the other case — it
      lives outside, like `personas.example.yaml`.
- [ ] T005 [US1] (FR-002, trap 2) Add the resolver module, modelled on
      `factory/stack_packs.py:196` — `resolve_stack_packs` for the packaged
      directory and on `factory/config.py:98` — `_resolve_default_registry_path`
      for the development-checkout fallback. It returns every shipped skill and
      the files under it. Do **not** introduce a third mechanism, and do not give
      the module and the packaged directory the same name: a directory
      `factory/skills/` beside a module `factory/skills.py` makes
      `importlib.resources.files("factory") / "skills"` ambiguous and the failure
      is a resolver that finds its own source file.
- [ ] T006 [US1] (FR-003, trap 3) Extend the wheel validation step at
      `.github/workflows/release.yml:68` with a guard for the skills payload, in
      the same shape and the same step as
      `.github/workflows/release.yml:83-86`, so a `force-include` typo fails the
      release instead of shipping a CLI whose install verb finds nothing.

### Verification for this story

- [ ] T007 [US1] Paste, as committed evidence, `unzip -l` output for a wheel
      built from this tree showing every shipped skill file inside it and no
      `__pycache__` entry, and the output of the release guard failing against a
      wheel with one skill deliberately stripped.

## Phase 2: User Story 2 — One verb puts them where the operator's agent looks

### Tests for this story (write FIRST, must fail)

- [ ] T008 [P] [US2] (spec US2-S1, FR-004, trap 8) Over a **temporary** home,
      never the operator's real one, assert the verb writes every shipped skill
      under that home's agent configuration and names each as it writes it.
      Derive the destination from the home under test, not from `__file__`,
      `sys.prefix` or the resolved package path, and not through
      `factory/config.py:104-108` — `_xdg_config_home`, which is the persona
      registry's resolver and points somewhere no agent reads (trap 8).
- [ ] T009 [P] [US2] (spec US2-S2, FR-005, traps 4 and 10) Install, change one
      skill's bytes on disk, run the verb again, and assert that skill is **not**
      overwritten: it is named, kept, and the output states how to take the new
      version deliberately, while the unchanged skills beside it are handled
      normally. The comparison is against the recorded digest, never a
      modification time — a fresh checkout, a `cp -r` and a restore all move the
      timestamp.
- [ ] T010 [P] [US2] (spec US2-S3, FR-006) Install, then run the verb again with
      nothing changed, and assert it reports a no-op naming each skill as
      current rather than reporting writes it did not perform.
- [ ] T011 [P] [US2] (spec US2-S4, FR-004) Assert every run prints the
      **absolute** destination directory, including the no-op run. An operator
      must never have to guess which of several plausible configuration
      directories was written to.
- [ ] T012 [P] [US2] (spec US2-S5, FR-013, trap 10) Put a file bearing a shipped
      skill's name at the destination that the record does not mention, run the
      verb, and assert it is left byte-identical and reported as a collision
      naming the path, and that the skills beside it are still installed. Never
      clobber what this factory did not write.
- [ ] T013 [P] [US2] (spec US2-S6, FR-011, trap 1) Assert `CONTEXT.md` § "Flagged
      ambiguities" (`CONTEXT.md:212`) carries an entry distinguishing the
      reserved per-persona `skills` field from the operator tooling, and that the
      verb's name agrees with that ruling. `tests/test_062_us3_skills.py:28` —
      `test_skills_field_is_documented_as_reserved_and_construction_sites_are_explained`
      still has to pass: the persona field stays reserved and keeps its name.
- [ ] T014 [P] [US2] (spec US2-S7, FR-012) Assert `README.md` names these skills
      and the command that installs them, distinct from the Spec Kit paragraph at
      `README.md:56`, which is about a third party's skills and is not this
      payload. `tests/test_readme.py:107` —
      `test_every_path_the_file_cites_exists` and `tests/test_readme.py:50` —
      `test_every_command_the_file_names_parses` are already parametrised over
      the file, so a path that does not resolve or a command that does not parse
      fails without a new test.

### Implementation for this story

- [ ] T015 [US2] (FR-011, trap 1) **First, before the name exists anywhere.**
      Write the ruling into `CONTEXT.md:212` — § "Flagged ambiguities" — in the
      shape of the `promote` entry at `CONTEXT.md:243-248`: name the sense the
      unqualified word takes, give the other a phrase, and exempt the landed
      identifier (`personas.yaml:42`, `factory/config.py:363` — `_skills`) from
      the prose ruling. Either that, or choose a verb name that does not collide.
      A ruling that lands after the name is a ruling about something already
      decided.
- [ ] T016 [US2] (FR-004, FR-013, traps 8 and 10) Add the install half beside
      the resolver the first story landed: resolve the shipped skills, derive the destination from the
      operator's home, create it when absent, write what is absent, and record a
      content digest per file under Ergane's own state root
      (`factory/cli/uninstall.py:617` — `_state_home`). The record does **not**
      go inside the skills directory — the agent reads that directory and would
      try to make sense of it.
- [ ] T017 [US2] (FR-005, FR-006, FR-013, trap 10) Implement the five cases of
      the truth table in spec.md § "The rule this spec is asking for" against the
      record: absent writes, matching-and-unchanged is a no-op, matching-with-new
      -shipped-bytes rewrites, differing keeps and names, unrecorded is a
      collision. Comparing the destination against the shipped bytes alone cannot
      distinguish "the operator edited it" from "the operator has an older
      version".
- [ ] T018 [US2] (FR-004) Add the noun module under `factory/cli/nouns/` in the
      shape of `factory/cli/nouns/install.py:123` — `add_parser`; it is
      discovered by `factory/cli/main.py:54` —
      `_discover_nouns_with_failures` and needs no registration elsewhere. Print
      the absolute destination on every path, including the no-op.
- [ ] T019 [US2] (FR-010, FR-012, trap 6) Add the `README.md` paragraph naming
      these skills and the install command, and confirm by reading that no path
      in this story writes into a target repository or into a dispatched node's
      HOME: the destination is derived from the operator's home and from nothing
      else. `factory/workgraph/adapter.py:815` — `home_path` and
      `factory/workgraph/adapter.py:971` — `attempt_env` are why a node cannot
      see the operator's home in the first place. 139 supersedes that ruling for
      the target-repository agent-context unit alone (trap 6) — do not widen it
      here, and do not edit 139.

### Verification for this story

- [ ] T020 [US2] Paste, as committed evidence, two short runs against a scratch
      home: a first install naming each skill and its absolute destination, and a
      second run after editing one skill by hand, showing that one named and kept
      and the rest reported as current. Two runs, not a transcript — this story's
      diff is the largest in the spec and shares the 64 KiB bound with its
      evidence.

## Phase 3: User Story 3 — The install says whether it is current

### Tests for this story (write FIRST, must fail)

- [ ] T021 [P] [US3] (spec US3-S1, FR-007, trap 5) Given a record naming one
      package version and a CLI reporting another, assert the check names both
      versions and says which skills are stale. Key the comparison on
      `factory/supervision/engine_identity.py:38` — `cli_version`. A check keyed
      on the revision string compares `unknown` against `unknown`
      (`factory/cli/main.py:144`) and reports a match on every packaged install,
      forever.
- [ ] T022 [P] [US3] (spec US3-S2, FR-007) Given a record naming the running
      package version, assert the check reports current and states the directory
      it looked in.
- [ ] T023 [P] [US3] (spec US3-S3, FR-008) Given no skills installed at all,
      assert the check says so plainly and names the verb that would install
      them, rather than erroring and rather than reporting zero stale skills —
      technically true and useless.

### Implementation for this story

- [ ] T024 [US3] (FR-007, trap 5) Add the staleness answer beside the resolver:
      compare the package version recorded at install time against
      `factory/supervision/engine_identity.py:38` — `cli_version`. Never read
      `git rev-parse`.
- [ ] T025 [US3] (FR-008) Expose it on the noun the verb story added, and give the empty
      case its own answer naming the install verb. Three states, not two:
      nothing installed, all current, some stale.

### Verification for this story

- [ ] T026 [US3] Paste, as committed evidence, the check's output in all three
      states, and `ergane --version` from the same installation showing the
      revision half reading `unknown` — the value trap 5 says the check must
      never compare.

## Phase 4: User Story 4 — Teardown removes what install wrote

### Tests for this story (write FIRST, must fail)

- [ ] T027 [P] [US4] (spec US4-S1, FR-009, trap 4) Given installed skills
      matching the record, assert teardown removes them and names each using the
      existing grammar — `factory/cli/uninstall.py:613` — `_removed` — so the
      step speaks the same dialect as every other one.
- [ ] T028 [P] [US4] (spec US4-S2, FR-009, traps 4 and 10) Given a skill
      the operator modified after installing, assert teardown **keeps** it and
      names it as kept with its reason — `factory/cli/uninstall.py:609` —
      `_kept`. The operator's edits are theirs; this is trap 4 from the other
      end.
- [ ] T029 [P] [US4] (spec US4-S3, FR-009) Given no installed skills, assert the
      step says it had nothing to do, as every other teardown step does —
      `factory/cli/uninstall.py:160` — `StepSurvey` calls that the
      `nothing_to_do` answer.
- [ ] T030 [P] [US4] (spec US4-S4, FR-009) Given installed skills and
      `--check`, assert the survey names what it would remove and what it would
      keep before anything is removed. `StepSurvey.notes` prints on `--check`, on
      a real run and on a step with nothing to do alike; a report that only
      speaks when it deletes is the defect 083 closed.

### Implementation for this story

- [ ] T031 [US4] (FR-009) Add one `Step` entry
      (`factory/cli/uninstall.py:188` — `Step`) to the ordered table at
      `factory/cli/uninstall.py:933`, with its read-only survey and its acting
      perform. Read the record through the function the verb story landed; do not re-derive
      it here, and touch no file the earlier stories own — that is what the
      Work Graph's `concurrent_with` edge on this story promises.
- [ ] T032 [US4] (FR-009, trap 10) In the perform half, remove only what
      matches the record, keep and name anything that differs, and never touch a
      file the record does not mention. Then delete the record entries for what
      was removed, so a second teardown reports nothing to do rather than
      re-reporting the same files.

### Verification for this story

- [ ] T033 [US4] Paste, as committed evidence, `ergane uninstall --check`
      naming the skills step's keeps and removals, the real run's output, and a
      second run reporting nothing to do.

## Verification

- [ ] T034 The full gate command passes green.
- [ ] T035 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 1 is the falsifiable test of this whole
      spec — `pip install ergane-cli` on a host with **no clone of this
      repository**, then one command, then a Claude Code session in which every
      skill resolves by name — because a checkout cannot fake it and a green
      suite has already shipped a command that could not start.
