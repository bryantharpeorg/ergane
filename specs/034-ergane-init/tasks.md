# Tasks: Ergane Init

Five stories. US1 → US2 is a merge chain; US3 and US4 both chain on US2 merged
and are independent of each other; US5 chains on US4 merged. Work test-first
within a story and commit once per task.

## Format: `[ID] [P?] [Story] Description`

Read `plan.md` first. Trap 1 fences the manifest name (040 owns it), trap 2 names
the seam US4 must reuse, trap 3 says the `repo` noun already exists, trap 4 is
the mechanisms with no precedent in this tree, and trap 7 says which
claims are only met by pasted output committed in the diff.

**US1 is landed** (`7055ea5`, PR #69, 2026-08-14). T001–T009 are recorded for
provenance and must not be re-executed; the prompter seam and the refusals
exist at `factory/cli/init.py`. A prior us2 attempt survives, unlanded, at
`refs/heads/archive/factory/034-ergane-init/us2/b52cf465ec42` — see the plan's
"What has landed".

## Phase 1: User Story 1 — The scaffold writes the repo's declarations (Priority: P1) 🎯 MVP — **LANDED `7055ea5`**

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T001 [US1] Write the two refusals FIRST: a `tmp_path` directory that is not
      a git repository is refused naming `git init` (spec US1-S5); a linked
      worktree of a git repo is refused naming the primary checkout (spec
      US1-S6). Build the worktree with `git worktree add` in the fixture and
      detect it by comparing `--git-dir` to `--git-common-dir` — **not** by the
      presence of a `.git` file, which a submodule also has (plan trap 4).

- [ ] T001a [US1] Write the bare-invocation case FIRST (spec US1-S7, FR-001):
      `ergane init` with no path argument resolves the repo containing the
      working directory and behaves identically to `ergane init .`, naming the
      resolved root in its output. Run it from a subdirectory too — the edge
      case says operate on the repo root, and a bare invocation is where that
      is most likely to surprise someone.

- [ ] T002 [US1] Write the scaffold case FIRST against a scripted interview
      (plan trap 5 — a seam, not a monkeypatched `input()`): the written
      `ergane.yaml` parses under `parse_factory_config` and declares every
      confirmed value and nothing else (spec US1-S1); `.gitignore` contains
      `.ergane/`; the `.ergane/` root exists and is empty.

- [ ] T003 [US1] Write the D-009 case FIRST: an interview that proposes a gate
      command inferred from a visible `pyproject.toml`, corrected by the
      operator, writes the correction and leaves no trace of the proposal (spec
      US1-S2).

- [ ] T004 [US1] Write the history-untouched case FIRST (spec US1-S3, SC-002):
      capture `git log` and `git status --porcelain` before and after init and
      assert the log is byte-identical and the status shows exactly the declared
      paths. **This is the claim the judge cannot see** — plan trap 7 — so the
      transcript is pasted verbatim into a comment block in the test file at T008.

- [ ] T005 [US1] Write the re-run case FIRST (spec US1-S4, FR-005): a second run
      changing only the standards path yields a manifest diff touching exactly
      that key with `.gitignore` untouched; an unchanged re-run yields a
      byte-identical manifest.

### Implementation for User Story 1

- [ ] T006 [US1] Add the repo-root resolution and both refusals, raising
      `OperatorError` (`factory/cli/errors.py`) with codes. Name the primary
      checkout from the parent of `--git-common-dir`.

- [ ] T007 [US1] Add the prompter seam and the interview, deriving its question
      list from the parser's own `_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:75`)
      and validating each answer with `parse_factory_config` itself (FR-004) —
      never a second copy of the rules.

- [ ] T008 [US1] Write the declared files and nothing else (FR-002): manifest,
      `.gitignore` line, `.ergane/` root. Print every path written plus the
      `git add` / `git commit` the operator will run. Paste T004's and T005's
      verbatim transcripts into the test file (plan trap 7).

- [ ] T009 [US1] Full suite green: `uv run pytest -q`. Confirm the diff renames
      no constant in `factory_yaml.py` — the manifest name is 040's (plan trap 1).

## Phase 2: User Story 2 — The engine learns the repo exists (Priority: P1)

Chains on US1 merged. **Read plan trap 4 before writing: the state home and the
lock have no precedent in this tree, and trap 8 before running anything — nothing
stops a test writing the operator's real registry.**

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T010 [US2] Write the registry-location case FIRST (spec US2-S1): after
      init with slug `myapp`, the registry maps `myapp` to the repo's absolute
      path, and no registry file exists anywhere inside the repo.

- [ ] T011 [US2] Write the collision case FIRST (spec US2-S2): a second repo
      declaring a taken slug is refused naming the existing holder's path.

- [ ] T012 [US2] Write the cache-is-a-cache cases FIRST: `repo rebuild` prunes
      an entry whose repo directory is gone, reports it, and leaves live entries
      untouched (spec US2-S3); `repo list` renders an entry whose manifest was
      deleted with manifest-missing status rather than dropping it (spec US2-S5).

- [ ] T013 [US2] Write the memory-scope case FIRST (spec US2-S4): with a control
      plane declaring a memory backend, the completed entry carries the repo's
      bank identity derived from the slug.

- [ ] T014 [US2] Write the **contended** lock case FIRST (FR-008): two writers,
      one registry, the second blocked or refused. A lock tested only
      uncontended is a lock nobody has tested (plan trap 4).

- [ ] T014a [US2] Write the destruction-convergence case FIRST (SC-005): delete
      the registry file outright, run `repo rebuild` against the still-present
      repos, and assert the rebuilt registry converges to the same entries. The
      cache's whole claim is that losing it is an inconvenience, not amnesia —
      T012 proves pruning; this proves rebirth. Paste the before/after listings'
      identity into the diff (plan trap 7).

### Implementation for User Story 2

- [ ] T015 [US2] Resolve the state home — `XDG_STATE_HOME` with the documented
      `~/.local/state` fallback — behind one environment override, and add that
      override to 030's session fixture in `tests/conftest.py` (grep
      `_isolated_test_store`) so the default is isolation, not vigilance
      (plan trap 8).

- [ ] T016 [US2] Implement the registry with `fcntl.flock` held across every
      mutation, and record in the commit message why that mechanism was chosen —
      it is the first lock in this tree.

- [ ] T017 [US2] Add `list` and `rebuild` to the **existing** `repo` parser
      (`factory/cli/repo.py:74`, grep `add_repo_parser`). Do not create a second
      noun and do not touch `repo onboard`; new verbs raise `OperatorError`
      directly rather than growing the legacy `_OperatorError` path (plan trap 3).

- [ ] T018 [US2] Full suite green: `uv run pytest -q`.

## Phase 3: User Story 3 — GitHub is wired to enforce the declarations (Priority: P2)

Chains on US2 merged. Independent of US4.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T019 [US3] Write the wiring case FIRST against a scripted `GhRunner`
      (`factory/mergequeue/gh.py:106`) — never the live tier: declared gates
      `test` and `lint` produce a queue enabled on the landing branch with
      exactly those two required checks, and a scaffolded workflow whose jobs are
      named `test` and `lint` running the declared commands (spec US3-S1).
      (Was `smoke` until 2026-08-16; the manifest schema refuses it — see the
      note under spec US3-S1.)

- [ ] T020 [US3] Write the idempotence case FIRST (spec US3-S2): a re-run reports
      every step already-satisfied and changes no setting.

- [ ] T021 [US3] Write both refusals FIRST: a repo whose visibility forbids the
      queue is refused at the visibility check citing D-007 and both remedies,
      with the scaffold half still usable (spec US3-S3); absent or
      unauthenticated `gh` is refused naming the prerequisite and the exact login
      command, offering the manual steps (spec US3-S4).

- [ ] T022 [US3] Write the parity guard FIRST (plan trap 9): feed the generated
      workflow's job names and the required checks through `evaluate_repo` and
      assert no `unknown_check:*` finding — an extra required job makes the repo
      fail its own `--check` one step later.

### Implementation for User Story 3

- [ ] T023 [US3] Implement wiring through the `GhClient` seam, each act
      idempotent and reported applied-or-already-satisfied, refusals raised at
      the point of refusal with the constraint and remedy named.

- [ ] T024 [US3] Generate the workflow file into the tree — one job per declared
      gate, named exactly after it, running exactly its command, requiring
      nothing else — and commit nothing, like every other file this spec writes.

- [ ] T025 [US3] Full suite green: `uv run pytest -q`.

## Phase 4: User Story 4 — Readiness is judged, not assumed (Priority: P2)

Chains on US2 merged. Independent of US3. **Read plan trap 2 first: the seam is
`onboard_target_repo`, not the `@activity.defn` wrapper.**

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T026 [US4] Write the all-pass case FIRST (spec US4-S1): a scaffolded,
      registered, wired fixture renders every finding passing with exit 0.

- [ ] T027 [US4] Write the one-at-a-time cases FIRST (SC-004): removing `.ergane/`
      from `.gitignore` flips exactly that finding, naming the exact line to add
      (spec US4-S2); a declared gate with no matching required check flips the
      existing parity finding exactly as dispatch does today (spec US4-S3);
      dropping the registry entry and renaming the landing branch each flip
      exactly their own finding. Assert *exactly one* finding changes per break —
      no masking.

- [ ] T028 [US4] Write the degraded case FIRST (spec US4-S4): with the control
      plane down, the control-plane finding fails carrying 033's probe detail and
      every repo-local finding still renders.

- [ ] T029 [US4] Write the two-doors assertion FIRST (FR-010, SC-004): the parity
      findings the CLI renders and the ones the 003 dispatch path renders come
      from one call to `evaluate_repo`, exercised against one fixture set.

### Implementation for User Story 4

- [ ] T030 [US4] Implement `ergane init --check` on top of `onboard_target_repo`
      (`factory/activities/merge_activities.py:590`), adding init's checks as
      `Finding`s in the existing three-field grammar
      (`factory/mergequeue/models.py:208`) — extend the judgment, never fork it.

- [ ] T031 [US4] Wire the check as the automatic last act of a full `ergane init`
      run (FR-010), non-zero exit on any failure.

- [ ] T032 [US4] Full suite green: `uv run pytest -q`.

## Phase 5: User Story 6 — The repo gets a scheduler (Priority: P1)

Chains on US4 merged — both extend the same readiness finding set, so they do
not run beside each other. **Read plan trap 11 first: nothing in this tree
creates a schedule, so there is no seam to reuse and no precedent to copy.**
Task ids continue from US5's block below; execution order is this phase, then
that one.

### Tests for User Story 6 (write FIRST, must fail)

- [ ] T039 [US6] Write the schedule-creation case FIRST against a scripted
      control-plane seam — never a live server (spec US6-S1, FR-014): after
      init, a schedule exists whose identifier carries the repo's slug and
      whose arguments carry that repo's specs root, target repo and landing
      branch. Assert the slug is *in the identifier*; a shared control plane
      with one namespace is the whole reason (plan trap 11).

- [ ] T040 [US6] Write the declared-dials case FIRST (spec US6-S2, FR-015):
      a manifest declaring cadence, `max_concurrent_epics` and
      `max_concurrent_nodes` produces a live schedule carrying those values;
      changing the manifest and re-running reconciles the live schedule.

- [ ] T041 [US6] Write the idempotence case FIRST (spec US6-S3): an unchanged
      re-run reports already-satisfied and mutates nothing.

### Implementation for User Story 6

- [ ] T045 [US6] Implement create/reconcile/delete behind one seam, with the
      slug-scoped identifier and the manifest-declared cadence and dials.
      Extend the manifest's typed shape rather than reading raw config.

- [ ] T047 [US6] Full suite green: `uv run pytest -q`. Paste the SC-007
      evidence verbatim into a comment block: a spec flipped to `ready`
      dispatching with no hand-run command and no hand-created schedule. If
      you cannot run a control plane in your environment, say so plainly in
      the commit rather than asserting it.

## Phase 5b: User Story 7 — A repo without a scheduler does not read as ready (Priority: P2)

Split out of US6 on 2026-08-16: US6 was built whole and measured 82,173 bytes
against the 61,440-byte judge refusal, which is deterministic and pre-judge, so
the work could not land at all. The seam is the one the implementing session
named — creation and reconciliation stay in US6; this phase takes the readiness
finding and forget, and imports `factory/roadmap/schedule.py` unchanged.

### Tests for User Story 7 (write FIRST, must fail)

- [ ] T042 [US7] Write the forget case FIRST (spec US7-S1, FR-016): forget
      deletes the schedule. Assert deletion, not "forget succeeded" — an
      orphaned schedule keeps firing at a specs root that may not exist.

- [ ] T043 [US7] Write the check-finding cases FIRST (spec US7-S2, FR-016):
      absent, paused, and argument-drifted schedules each flip exactly their
      own finding with a remedy named. Follow US4's one-break-one-finding
      discipline — no masking.

- [ ] T044 [US7] Write the unreachable-control-plane case FIRST (spec US7-S3,
      FR-017): scaffold and registry complete; the schedule step reports
      failed with its reason; nothing repo-local is rolled back.

### Implementation for User Story 7

- [ ] T046 [US7] Add the schedule findings to the existing `evaluate_repo`
      set — the same extension US4 made, never a second judgment — and wire
      creation as a reported step of a full init run.

## Phase 6: User Story 5 — A repo can leave (Priority: P3)

Chains on US6 merged — `forget` must delete the schedule US6 creates.

### Tests for User Story 5 (write FIRST, must fail)

- [ ] T033 [US5] Write the clean-departure case FIRST (spec US5-S1, SC-006):
      after forget the entry is gone, the repo's tree and history are untouched,
      and a fresh `ergane init .` re-registers the same slug to a byte-identical
      tree.

- [ ] T034 [US5] Write the refusal case FIRST (spec US5-S2): with an epic open,
      `--clean-runtime` refuses naming what it saw. Read plan trap 6 — the open
      count is namespace-wide because workflow ids carry no repo token, so refuse
      on *any* open epic and say so; do not filter ids that cannot be filtered.

- [ ] T035 [US5] Write the export cases FIRST: `--export ./out` writes one JSONL
      per store holding exactly this repo's rows plus a markdown digest, removes
      the registry entry, and writes nothing anywhere else (spec US5-S3); forget
      without the flag writes no export at all (spec US5-S4).

### Implementation for User Story 5

- [ ] T036 [US5] Add `forget` to the existing `repo` parser with `--clean-runtime`
      and `--export`, entry removal only by default — plus the schedule
      deletion US6's T042 asserts.

- [ ] T037 [US5] Implement export: slug-selected rows, outside `.ergane/`, no
      secret values, committing nothing. Produce the byte-identity evidence and
      COMMIT IT (plan trap 7) — run two exports against an untouched engine and
      paste both digests verbatim into a comment block in the test file.

- [ ] T038 [US5] Full suite green: `uv run pytest -q`.

## Verification

- [ ] Final gate command passes green.
- [ ] The three pasted transcripts are in the diff: history-untouched, re-run
      byte-identity, export byte-identity.
- [ ] The lock has a contended test.
- [ ] No second readiness judgment exists — `evaluate_repo` has one caller shape.
- [ ] No manifest-name constant was edited (040 owns it).
- [ ] The schedule identifier carries the repo slug, and `forget` deletes it.
