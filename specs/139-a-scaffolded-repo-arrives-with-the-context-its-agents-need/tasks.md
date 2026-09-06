# Tasks: a scaffolded repo arrives with the context its agents need

Read `plan.md` before starting. Trap 1 is the one that would waste a whole
story: the finding's `.specify/` half was fixed by spec 057 on 2026-09-03
(`factory/cli/init.py:1263`, `factory/cli/init.py:1273`), so nothing here
touches the standards path, the constitution or the manifest's `standards` key.
Trap 3 is the one that decides whether the hook is usable: `.` resolves to the
repository root, and so do `run` and `build` in a repository that has those
directories. Trap 12 is the one that would stop the factory: without FR-021 the
hook this spec installs refuses the factory's own implementer nodes, no
environment variable can rescue that past `factory/workgraph/adapter.py:104`,
and a detector keyed on the runtime root's *name* ships green and fails on every
host that set `ERGANE_ROOT`. Trap 16 is the one that would lock an operator out:
`argparse` already exits 2 for an unknown verb, and 2 is the only status a
`PreToolUse` hook blocks on. Trap 15 is the one that makes US1's first test lie:
the wheel harness copies the git index and one hardcoded block per package-data
path, so it cannot see a payload directory nobody has staged. Traps 7, 13 and 14
are silent when they fire: a `.gitignore` entry covering `.claude/` — whether
init wrote it or the repository already had it — or a staging line that omits
the unit, makes every gate pass and no agent ever see it; an unconditional first
write destroys the operator's own `.claude/` files; and a skill document at the
wrong relative path loads in nothing.

The phases are in dependency order, not numeric order: phase 4 is user story 5
and phase 5 is user story 4, because US4 is the story that needs all of the
others merged. A story number is an identity, never a sequence.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The unit exists, is declared, and travels in the wheel

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-002, trap 15) Build a wheel from
      the tree and assert the unit's declaration names at least one file and that
      every file it names is present inside the wheel under `factory/`. Assert
      the non-emptiness first: every other claim in this phase is vacuous over an
      empty payload. Follow `tests/test_057_us2_stack_pack.py:296` —
      `test_every_shipped_pack_travels_in_the_wheel` and its instruction: inspect
      the built zip, never `pyproject.toml`. Its harness
      (`tests/test_distribution_install.py:39` — `_build_wheel`,
      `tests.test_distribution_rename._wheel_contents`) does **not** generalise —
      it copies the git index and one hardcoded block per package-data path — so
      this test fails until T006 lands, and that failure is the harness, not the
      packaging. Do not repair it in `pyproject.toml` (trap 2).
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Assert both refusal directions in one
      test: a declaration naming a file that is absent, and a payload file the
      declaration does not name. One direction alone lets a new payload file ship
      undeclared.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003, trap 8) Assert no shipped payload entry
      is a `.py` file, with a failure message naming `pyproject.toml:87` —
      `testpaths = ["tests"]` — as the reason. The finding's worked example is 139
      lines of Python under `.claude/` covered by four green gates.
- [ ] T004 [P] [US1] (spec US1-S4, FR-004, trap 14) Assert the shipped skill
      document's *shape*, not only its text: its relative path inside the payload
      is `skills/<name>/SKILL.md`, its YAML frontmatter parses and carries both a
      `name` and a `description` key, and its body names the manifest's
      `standards` key and the `ergane spec new` verb as literal substrings. Four
      assertions in one test. A document at any other relative path passes the
      substring half and loads in no agent.

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-002, trap 2) Add the unit's declaration file and its
      payload directory inside `factory/`, and a resolver that reads them
      `importlib.resources`-first following `factory/stack_packs.py:182` —
      `resolve_stack_packs` and its directory resolution at
      `factory/stack_packs.py:196`. Refuse both mismatch directions (FR-002).
      The pack resolver, not `factory/config.py:81` —
      `_resolve_default_registry_path`: that one resolves a single repo-root file
      that needs the force-include, and this payload is a directory inside
      `factory/` that must not have one — `pyproject.toml:74-79` says why in the
      tree's own words, and `pyproject.toml:84`'s `default_floor.md` entry is the
      repo-root case and the wrong line to copy. No `pyproject.toml` edit is part
      of this story.
- [ ] T006 [US1] (FR-001, trap 15) Add one `shutil.copytree` block for the
      payload directory to `tests/test_distribution_install.py:39` —
      `_build_wheel`, beside 057/US2's block at
      `tests/test_distribution_install.py:70-75` and commented the same way. The
      harness builds from `git checkout-index`, which sees only the staged tree,
      so without this block T001 fails for a payload that is packaged perfectly.
      This is the only file outside the payload that US1 edits, and US3 does not
      touch it.
- [ ] T007 [US1] (FR-004, traps 8 and 14) Write the skill document as prose only,
      at `skills/<name>/SKILL.md` inside the payload, opening with YAML
      frontmatter carrying `name` and `description` — copy the shape of
      `.claude/skills/spec-html/SKILL.md:1-3`. It tells a dispatched agent how
      this repository's spec-driven loop works, names the manifest's `standards`
      key as the document it must obey, and names `ergane spec new` as what
      produces a compiling trio (`factory/doctor/scaffold.py:27` —
      `scaffold_spec`). No helper script: a shipped `.py` file under `.claude/`
      is ungated in every repository that receives it.

### Verification for this story

- [ ] T008 [US1] Paste, as committed evidence, the listing of the built wheel's
      entries under the payload directory — showing the skill document at
      `skills/<name>/SKILL.md` — the resolver's refusal text for a declaration
      naming a missing file, and `git diff --stat -- pyproject.toml` showing no
      change, which is trap 2 stated as output rather than as intention.

## Phase 2: User Story 2 — `init` installs the unit, and a later `init` updates it without overwriting the operator

### Tests for this story (write FIRST, must fail)

- [ ] T009 [P] [US2] (spec US2-S1, FR-005, FR-006) Given a repository with no
      `.claude/`, assert after `ergane init` that every payload file exists under
      `<repo>/.claude/` at the payload's own relative path with the shipped bytes,
      and that the install record names the unit version and one digest per file.
      The relative path is half the assertion: a flattened install puts the skill
      document outside the one channel `factory/config.py:177-179` describes.
- [ ] T010 [P] [US2] (spec US2-S2, FR-007) Given that repository unchanged, assert
      a second `ergane init` rewrites each payload file to the shipped bytes and
      names each as updated in the report.
- [ ] T011 [P] [US2] (spec US2-S3, FR-007, trap 6) **The control that matters
      most for the update half.** Given one payload file whose bytes the operator
      changed, assert a second `ergane init` leaves that file byte-for-byte, names
      it as kept, and still updates its unedited siblings in the same run. An
      existence-only guard modelled on `factory/cli/init.py:1862` —
      `_standards_document_exists` passes T009 and fails this.
- [ ] T012 [P] [US2] (spec US2-S6, FR-005, FR-006, trap 13) **The control that
      matters most for the install half.** Given a repository that already
      carries its own `<repo>/.claude/skills/<name>/SKILL.md` at the relative
      path the shipped declaration names — read it from the declaration, do not
      hardcode it — and, beside it, a file of the operator's own under
      `<repo>/.claude/` at a path the payload does not name, and no install
      record at all, assert the **first** `ergane init` leaves the payload-path
      file byte-for-byte, names it as kept, and writes no digest for it, and
      leaves the other file byte-for-byte and unnamed in the report. An
      implementer reading FR-005 as an unconditional write passes every other
      test in this phase and destroys the operator's file here. Do **not** use
      `settings.json` as the fixture and do **not** add it to the payload to
      make one: it enters the payload with FR-017, which US4 owns and T046
      writes, and its pre-existing case is US4-S4 under FR-019. At this story's
      dispatch the payload holds what US1 shipped and nothing else.
- [ ] T013 [P] [US2] (spec US2-S4, FR-008, trap 7) After init has installed the
      unit, assert the `.gitignore` init wrote matches none of the files named in
      the install record — file by file, not by looking for one literal string —
      with a failure message naming the reason: only committed worktree files
      reach a node (`factory/config.py:177-179`). This failure is otherwise
      silent — the files exist, every gate passes, and no agent sees them.
- [ ] T014 [P] [US2] (spec US2-S8, FR-008, trap 7) Given a repository
      whose own `.gitignore` carried `.claude/` **before** ergane ran, assert the
      init report names each installed file the repository's effective ignore
      rules cover and says the unit reaches no dispatched node until that changes.
      T013 alone passes here, because init's own entry is innocent: the rule that
      hides the unit is one init never wrote.
- [ ] T015 [P] [US2] (spec US2-S7, FR-020, trap 7) Assert the `git ... add ...`
      line init prints (`factory/cli/init.py:1342`) names every file in the
      install record *and the record itself*, file by file over the record, and
      does not name `<repo>/.claude` as a directory. An init that reports the unit
      written and then tells the operator to stage everything except it is trap 7
      by the neighbouring mechanism; naming the directory instead sweeps in
      whatever else the operator keeps there; and an uncommitted record leaves the
      next clone with a digest for nothing.
- [ ] T016 [US2] (spec US2-S5, FR-009, FR-010) Assert init's report names the
      unit's install root and version, and states that `specs/` is empty
      deliberately because `ergane spec new` produces a compiling trio. Not
      `[P]`: it reads the same report T010, T011, T012 and T014 assert against.

### Implementation for this story

- [ ] T017 [US2] (FR-005, FR-006) Install the unit from the resolver beside the
      constitution call at `factory/cli/init.py:1273`, not inside
      `factory/cli/init.py:1816` — `_write_scaffold`, and preserve the payload's
      relative paths under `<repo>/.claude/`. The reason is the caller set, not
      `--check`: `_write_scaffold` has three production callers
      (`factory/cli/init.py:1268`, `factory/cli/install.py:1001`,
      `factory/supervision/demo_driver.py:409`), the latter two being throwaway
      demonstrations this spec deliberately leaves alone, and `--check` reaches
      neither site at all because `init_command` returns at
      `factory/cli/init.py:1148-1149` before the interview. Do not build
      `--check` reporting for a path `--check` cannot execute.
- [ ] T018 [US2] (FR-005, FR-006, FR-007, traps 6 and 13) Write the install record
      and make the decision on the recorded digest, in three states, not two: no
      file at the path, write it and record the digest; a file whose bytes match
      the recorded digest, rewrite it; a file whose bytes differ from the record
      **or for which the record holds no digest**, leave it alone, report it as
      kept, and record no digest for it. Existence is not the guard — a unit
      guarded on existence can never be updated, which is the half of the finding
      that says "installed and updated by init" — and an unconditional write
      destroys an operator's own `.claude/` file on the first run. Write the
      record under `<repo>/.claude/` as part of the unit, so T015's staging line
      names it and the next clone inherits the digests rather than reading every
      payload file as one the operator wrote.
- [ ] T019 [US2] (FR-008, trap 7) Ask git, not the file init wrote, which
      installed paths are ignored — `git -C <repo> check-ignore --stdin` over the
      record's paths — and report the covered ones by name. Do not add `.claude/`
      to `.gitignore`: `factory/cli/init.py:1830-1837` appends `.ergane/` and that
      stays the only entry init writes.
- [ ] T020 [US2] (FR-020, trap 7) Extend `factory/cli/init.py:1364` —
      `_paths_to_commit` so the printed staging line names each installed file
      from the record, and the record. Keep the existing entries; append rather
      than replace.
- [ ] T021 [US2] (FR-009, FR-010) Add the install line to the `written:` block at
      `factory/cli/init.py:1326-1331`, and the two report sentences after it
      beside `factory/cli/init.py:1332` — they are reports, not writes, and the
      block above is a list of files.

### Verification for this story

- [ ] T022 [US2] Paste, as committed evidence, three init reports for scratch
      repositories — the first run seeding the unit, a second run after one
      payload file was changed showing that file kept and its siblings updated,
      and a first run in a repository that already carried its own
      `skills/<name>/SKILL.md` at the payload path, showing it kept with no
      digest recorded and the operator's non-payload file unnamed — the report
      for a repository whose `.gitignore` already carried `.claude/`, showing the
      covered files named, and `git status --short` for the first repository
      after running the printed `git add` line verbatim, showing every installed
      file and the record staged and nothing else.

## Phase 3: User Story 3 — The gate paths are derived from the manifest, and a verb answers with them

### Tests for this story (write FIRST, must fail)

- [ ] T023 [P] [US3] (spec US3-S1, FR-012, trap 3) **The control that decides the
      spec.** Given a repository carrying the shipped Python pack's markers and
      gate commands (`factory/stack_packs/python.yaml`: `uv run pytest -q`,
      `uv run ruff check .`, `uv run mypy .`), a `tests/` directory and no `src/`,
      assert the repository root is not among the derived paths, that `tests` is,
      and that the pack's other declared root `src` is not. `.` resolves to an
      existing directory, so a derivation that keeps every resolving token refuses
      every write in the repository — including the operator's specs, which
      spec.md promises are out of reach — and a declared root the repository does
      not contain is a guess the hook would report as protection.
- [ ] T024 [P] [US3] (spec US3-S2, FR-012, trap 3) Given a repository with both a
      `web/` and a `build/` directory and the gate command
      `npm --prefix web run build`, assert `web` is derived and attributed to that
      gate by name, and that neither `build` nor `run` is. All three name existing
      directories; only `web` is a path-shaped argument under FR-012's rule.
- [ ] T025 [P] [US3] (spec US3-S3, FR-012, FR-013) Given gate commands naming no
      path-shaped argument and a stack pack declaring no source root the
      repository contains, assert the derived set is empty and the verb prints a
      line saying so, rather than falling back to the repository root.
- [ ] T026 [P] [US3] (spec US3-S4, FR-013) Given a repository whose derivation
      yields two paths from two different gates, assert `ergane repo gate-paths`
      prints one line per path naming the path and its gate, asserted against the
      captured output.

### Implementation for this story

- [ ] T027 [US3] (FR-011) Add the optional `sources` list to
      `factory/stack_packs.py:50` — `StackPack` beside `tools`, and validate it at
      `factory/stack_packs.py:141` — `_pack_from_data` the way `tools` is
      validated at `factory/stack_packs.py:148` and `factory/stack_packs.py:157`.
      Declare it in the shipped pack files with the values plan.md § "What each
      shipped pack declares" fixes: `factory/stack_packs/python.yaml` gets
      `[src, tests]`, `factory/stack_packs/node.yaml` gets
      `[src, lib, app, test, tests]`, and `factory/stack_packs/agnostic.yaml` gets
      none, for the reason its own header gives for declaring no commands. Do not
      invent other values, and do not name `factory` in a shipped pack: that is
      one repository's layout. No code may branch on a pack's name —
      `factory/stack_packs.py:13-17` states that rule and
      `tests/test_057_us2_stack_pack.py` asserts it.
- [ ] T028 [US3] (FR-012, trap 3) Write the derivation over
      `factory/verify/models.py:310` — the manifest's `gates` mapping on
      `factory/verify/models.py:291` — `FactoryConfig` — and the resolved pack. A
      word counts as a path-shaped argument only when it names an existing path
      **and** contains a separator, or is the value of a preceding flag, or is one
      of the pack's declared source roots. Order matters for the flag test, so
      read the tokens with `shlex.split` as `factory/stack_packs.py:253` —
      `_leading_executable` does; `factory/stack_packs.py:248` — `_command_words`
      returns a set and drops order. Exclude the repository root by any route, and
      for a gate that names no path fall through to the pack's declared roots,
      dropping any the repository does not contain. Do **not** reuse
      `factory/stack_packs.py:262` — `check_tool_hygiene`: it answers a question
      about executables, not paths.
- [ ] T029 [US3] (FR-013) Add the listing verb to `factory/cli/repo.py:105` —
      `add_repo_parser`, following the shape of the `onboard` block at
      `factory/cli/repo.py:113` and the `list` block at `factory/cli/repo.py:138`,
      each with its own `set_defaults(run=...)`. One line per derived path naming
      its gate, and one line saying the set is empty and why when it is.

### Verification for this story

- [ ] T030 [US3] Paste, as committed evidence, the output of the verb against a
      repository declaring the shipped Python pack's gate commands — showing the
      repository root and the absent `src` both missing from the listing — and its
      output against the `npm --prefix web run build` repository, showing `web`
      listed with its gate and `build` absent.

## Phase 4: User Story 5 — `--check` answers a tool hook, and knows an operator from a dispatched node

### Tests for this story (write FIRST, must fail)

- [ ] T031 [P] [US5] (spec US5-S1, FR-014) Given a tool payload on standard input
      naming a file under a derived path, and an invocation that is not a
      dispatched node, assert `ergane repo gate-paths --check` exits with the
      declared refusal status and that its message names the file, the gate and
      the rule.
- [ ] T032 [P] [US5] (spec US5-S2, FR-014) **The control.** Given a payload naming
      a file under none of the derived paths, assert exit 0 and no message.
- [ ] T033 [P] [US5] (spec US5-S3, FR-021, trap 12) **The control that keeps the
      factory running.** Given a payload naming a file under a derived path,
      assert exit 0 and a line naming the node exemption in three environments:
      one whose `HOME` is a factory per-node home
      (`factory/workgraph/adapter.py:815` — `home_path`, the value
      `factory/workgraph/adapter.py:947` — `attempt_env` gives every dispatched
      child), one whose target path lies inside a node worktree
      (`factory/workgraph/worktree.py:289` — `worktree_path`), and both of those
      again under a runtime root whose directory name is neither `.ergane` nor
      `.factory`. The third is the one that fails a detector keyed on
      `factory/workgraph/worktree.py:93` and `factory/workgraph/worktree.py:96`,
      which `factory/workgraph/worktree.py:191` — `resolve_factory_root` overrides
      from the environment. Without all three, every implementer node's production
      write is the refuse row on some host.
- [ ] T034 [P] [US5] (spec US5-S4, FR-015, traps 9 and 10) Given an unreadable
      manifest, and separately a payload that does not parse, assert exit 0 in
      both cases with one line naming what could not be read. Commit a fixture of
      the payload shape and assert the parse against it: the shape is an external
      contract, and a hardcoded parser that stops matching starts allowing
      everything with no test failing.
- [ ] T035 [P] [US5] (spec US5-S5, FR-016) Given
      `ERGANE_SKIP_GATE_PATH_CHECK=1` in the environment, assert a payload that
      would otherwise be refused exits 0 with a line saying the escape was used.
      Write the name literally in the test; FR-016 fixes it, and an operator
      following plan.md § "Verification the operator will run" step 7 types it
      without reading this diff.
- [ ] T036 [P] [US5] (spec US5-S6, FR-014, trap 16) Capture two exit statuses in
      one test: the refusal path's, and the one the `ergane repo` parser produces
      for a verb it does not have. Assert the second is 2 and the first is not.
      Exit 2 is the only status a `PreToolUse` hook blocks on, so a refusal that
      shares `argparse`'s usage status makes every installation predating this
      verb refuse every write in its repository.

### Implementation for this story

- [ ] T037 [US5] (FR-014, FR-015, FR-016) Add `--check` and the stdin path to the
      verb US3 added at `factory/cli/repo.py:105` — `add_repo_parser`. The
      decision lives here, in the CLI under `factory/`, rather than in a script
      the payload copies — the gates compile `factory/` and do not compile
      `.claude/` (trap 8).
- [ ] T038 [US5] (FR-021, trap 12) Read the node markers the factory already sets
      by their **shape**, which survives a relocated root: a `HOME` whose trailing
      segments are `homes/<epic>/<node>`, a target path with a
      `worktrees/<epic>/<node>` tail, or the checked-out branch
      `factory/workgraph/worktree.py:284` — `branch_name`. Do **not** key on the
      directory names at `factory/workgraph/worktree.py:93` and
      `factory/workgraph/worktree.py:96`: `factory/workgraph/worktree.py:191` —
      `resolve_factory_root` returns an `ERGANE_ROOT`/`FACTORY_ROOT` override
      verbatim at `factory/workgraph/worktree.py:211-216`, this floor sets one at
      `scripts/ergane-env.sh:84`, and `factory/cli/repo.py:328` says so in the
      tree's own words. Do not add a name to `factory/workgraph/adapter.py:104`'s
      passthrough allowlist and do not edit that file:
      `factory/workgraph/adapter.py:947` — `attempt_env` builds the child's
      environment rather than filtering it, so an exported variable reaches no
      node and FR-016's escape cannot serve as this mechanism.
- [ ] T039 [US5] (FR-014, FR-015, FR-016, traps 9 and 16) Give the refusal a
      status of its own that `argparse` cannot produce, name it as a module
      constant, and make every unreadable case exit 0 with a line on standard
      error. A hook that fails closed locks an operator out of their own
      repository; a hook that fails silently is worse than none, because it reads
      as protection. `ergane` absent from `PATH` is not one of these cases and is
      not yours to catch — the command never runs — and no wrapper script may be
      shipped in the payload to try (trap 8, FR-003). `ergane` *present but older
      than this verb* is the case that matters and it is answered in US4 by
      FR-022, which is why this status must not be 2.

### Verification for this story

- [ ] T040 [US5] Paste, as committed evidence, the five `--check` outcomes side by
      side with their exit statuses: the refusal with its status, the silent
      allow, the node exemption under a per-node `HOME`, the same exemption under
      a relocated runtime root, and the escape line — together with the status
      `ergane repo` returns for an unknown verb, so the two are visibly different.

## Phase 5: User Story 4 — The installed unit declares the hook, and says what it will and will not refuse

### Tests for this story (write FIRST, must fail)

- [ ] T041 [P] [US4] (spec US4-S1, FR-017) Assert the shipped payload's
      `settings.json`, parsed as a document rather than matched as text, declares
      a `PreToolUse` entry whose matcher covers both `Write` and `Edit` and whose
      command invokes `ergane repo gate-paths --check`.
- [ ] T042 [P] [US4] (spec US4-S2, FR-018, trap 9) Given a repository whose derived
      gate-path set is empty, assert `ergane init` reports that the installed hook
      will refuse nothing, and why. An installed hook that permits everything
      silently is worse than no hook.
- [ ] T043 [P] [US4] (spec US4-S3, FR-018) Given a repository whose derived set is
      two paths, assert the init report names both paths with their gates. A set
      that covers the tests and not the production code reads as protection, and
      this line is where the operator can see it.
- [ ] T044 [P] [US4] (spec US4-S4, FR-019, trap 13) Given a repository whose
      `<repo>/.claude/settings.json` the operator changed, assert `ergane init`
      leaves it byte-for-byte and says the hook was not installed there — for a
      file whose bytes differ from the record and for one the record never named.
      The second half is the case T012 could not assert: `settings.json` becomes
      a payload path only here, at T046, so this story is where a
      `settings.json` the operator had first is proven to survive.
- [ ] T045 [P] [US4] (spec US4-S5, FR-022, trap 16) **The control that keeps an
      operator out of a lockout.** Execute the command string the shipped
      `settings.json` declares, twice, with a stub `ergane` first on `PATH`: one
      that exits 2 with an `argparse` usage message, and one that exits the
      declared refusal status. Assert the first composed run exits 0 and the
      second exits 2. The first direction is the ordinary rollout state — 0.5.0
      is what is released and it has no such verb — and a declared command that
      passes 2 straight through refuses every Write in that repository.

### Implementation for this story

- [ ] T046 [US4] (FR-017, FR-022, traps 5 and 16) Add `settings.json` to the
      payload and to the unit's declaration, so US1's both-directions check
      (FR-002) covers it. Its `PreToolUse` command must map only FR-014's refusal
      status to exit 2 and every other status of the invoked `ergane`, 2 included,
      to exit 0 — the translation lives in the declared command, not in the verb,
      because the verb is exactly what a stale installation does not have. No file
      this spec ships may be named `CLAUDE.md`: D-025
      (`docs/decisions.md:600-608`) put standards in the manifest's `standards`
      key precisely to avoid relying on `CLAUDE.md` auto-loading.
- [ ] T047 [US4] (FR-018, FR-019, trap 11) Add the report lines to
      `factory/cli/init.py:1326-1331`'s neighbourhood. US2 must be merged first —
      it is what installs the unit and writes the record this story reports
      against; building an install here duplicates US2.

### Verification for this story

- [ ] T048 [US4] Paste, as committed evidence, the init report for a repository
      whose derivation is empty, the init report for one whose derivation is two
      paths showing both with their gates, the init report for a repository whose
      `settings.json` was changed by the operator showing the hook not installed
      and named, and the two composed-command runs of T045 with their exit
      statuses beside the stub each used.

## Verification

- [ ] T049 The full gate command passes green.
- [ ] T050 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 5 is trap 3 run forwards and decides
      whether the hook is usable at all; step 6 is the falsifiable test of the
      whole spec in both halves, because the claim at `factory/config.py:177-179`
      — that a committed `<repo>/.claude/skills/` reaches a dispatched node — has
      never been exercised with a file ergane put there, and FR-021 is what keeps
      that same mechanism from stopping every node's own writes; steps 8 and 9 are
      traps 16 and 12 run forwards, and each is a state no committed test written
      against the defaults would reach.
