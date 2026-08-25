# Tasks: a landing refuses before the build, not after

**Spec**: `specs/107-a-landing-refuses-before-the-build-not-after/spec.md`
**Plan**: `specs/107-a-landing-refuses-before-the-build-not-after/plan.md`

Read the plan's rulings and traps before the first task. Four traps decide
whether an attempt lands, and one of them is a measured false pass. Three
rulings — R7, R13 and R14 — settle seams that each had two defensible answers of
different blast radius; they are settled, and re-opening one mid-story is the
scope discovery trap 17 exists to prevent.

- **Trap 1 (US1, US4)**: the ownership check is TWO assertions. The factory root
  sits inside the operator's clone, so git walks UP out of a bare directory and
  reports that clone as its owner — exit 0, no error. Assert the resolved top
  level equals the directory itself as well as comparing the common git
  directory, or you will ship a green test that proves nothing.
- **Trap 3 (US3)**: the base fix is NOT in `ensure()`. A landed 020 test pins
  `PreparedWorktree.default_branch` to the checked-out branch on purpose, with a
  written rationale. Change the routing, never the value — and note that a fix
  inside `ensure()` could not repair the sidecars already on disk anyway.
- **Trap 6 (US1)**: nothing sweeps the stale worktrees this spec refuses on, and
  the operator's obvious cleanup command does not work — `git worktree remove`
  run in the dispatched target repo answers `fatal: not a working tree`. The
  remedy string, issued against the OWNING clone, is an acceptance criterion.
- **Traps 8 and 9 (US5)**: the session-id collision is intra-node and sequential.
  It crosses exactly one boundary — an activity retry — and `record.attempt` does
  not distinguish the two executions. Concurrency is the trigger, not the
  mechanism.

**These are real tests, not seam captures** (trap 15). Two `git init`
repositories, one shared directory and a local bare origin reproduce every
failure in US1–US4 offline, with no network and no docker: the drafting session
ran it and got `error: src refspec ... does not match any` and `fatal: ... is not
a working tree` verbatim. Do not mock git and do not move anything to an operator
list. **US5 is the one exception**: its runner refusal needs a real `claude`
binary, so its criteria are the pure derivation plus an injected-runner seam
capture labelled as such, with the two-execution reproduction on the operator's
list in `plan.md` where it gates nothing.

**Size every diff for 65,536 bytes** (trap 16). Past `DIFF_INPUT_LIMIT` the
deterministic check refuses the diff and the judge is never called. Two landed
nine-to-ten-task stories in this codebase measured 64,127 and 63,674 bytes —
within 2 KB of the refusal — so a nine-task story here is AT the cap, not
comfortably inside it. No story here may refactor a function it did not come to
change, and US1 and US6 each have a named fallback split seam in `plan.md`
§ Sizing: use the seam rather than trimming tests.

## Phase 1: User Story 1 — A worktree says which repository owns it

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001, FR-002, FR-003) A new test module builds
      two `git init` repositories, A and B, sharing one worktree root; registers
      a node worktree to A; then calls `worktrees.ensure` naming B. Assert it
      raises rather than returning the recorded worktree, and that the message
      contains the worktree path, A, B, and a remedy command issued **against A**
      — the owning clone — because the same command run against B answers
      `fatal: not a working tree` (trap 6).
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) The same cross-registered directory
      with its sidecar deleted: assert `ensure` refuses on the adopt path too,
      that no sidecar is written, and that the foreign tree is not adopted. This
      is the branch a sidecar field could never have protected (trap 2).
- [ ] T003 [P] [US1] (spec US1-S3, FR-001) A plain `mkdir` directory nested
      inside a repository's own working tree, with no `.git` of any kind: assert
      the ownership helper reports it as not-a-worktree and `ensure` refuses.
      Assert explicitly that it does **not** pass by inheriting the enclosing
      clone — the enclosing clone is a legitimate git repository and answers the
      common-directory question happily (trap 1).
- [ ] T004 [P] [US1] (spec US1-S4, FR-002) A worktree correctly registered to the
      dispatched repo: assert `ensure` returns exactly what it returns today on
      both the recorded and the create paths, and that `tests/test_worktree.py`
      passes unmodified.
- [ ] T005 [P] [US1] (spec US1-S5, FR-003) Drive `prepare_worktree` in
      `factory/activities/agent_activities.py` over the cross-registered fixture
      and assert the failure is a non-retryable application error whose type is
      **not** `WORKTREE_FAILED` — a repository mismatch never resolves by
      retrying — following the `STANDARDS_MISSING` precedent in the same module.
      Assert too that an ordinary `WorktreeError` still becomes a retryable
      `WORKTREE_FAILED`, so the discrimination is proven in both directions.

### Implementation for this story

- [ ] T006 [US1] (FR-001) One private helper in `factory/workgraph/worktree.py`,
      beside `_main_worktree`, answering "is this directory a worktree of that
      repository". One `git rev-parse --path-format=absolute --show-toplevel
      --git-common-dir` in the directory, compared against the same read in the
      target repo, asserting BOTH lines (plan R1). A directory that is not a
      worktree is a returned answer, never an escaping exception. **This is the
      only derivation of worktree ownership this spec adds** (plan R2).
- [ ] T007 [US1] (FR-002) Guard both existing-directory branches of `ensure` —
      the recorded-sidecar branch at `:331-337` and the adopt branch at
      `:339-348` — with the helper. Refuse; do not repair, remove or rebuild
      anything in the owning clone (plan R3). Leave the reuse rule, the pin
      ancestry check and the two create paths (`:368` and `:374`) alone.
- [ ] T008 [US1] (FR-003) One new error-type constant in
      `factory/activities/agent_activities.py`, in the style of the constants
      already there, with a docstring saying why it is non-retryable; raise it
      from `prepare_worktree` when the refusal is an ownership mismatch, keeping
      every other `WorktreeError` on today's retryable path. The refusal must be
      raised from `worktree.py` as an exception type **distinguishable from an
      ordinary `WorktreeError`** — this activity needs the discrimination and so
      does US2's landing activity (plan R14), so a message-substring check is not
      enough.
- [ ] T009 [US1] (FR-003) The refusal text itself: worktree path, owning clone,
      dispatched target repo, and the copy-pasteable remedy against the owning
      clone. Paste the message into the test as a literal expectation, because
      the operator's next move is the only thing standing between a refusal and a
      hard stop.

### Verification for this story

- [ ] T010 [US1] (spec US1-S1, SC-001) Commit pasted output of the ownership
      helper for three directories — correctly owned, owned by another clone, and
      not a worktree at all — beside the full refusal an operator would see.

## Phase 2: User Story 2 — The landing push names the repository that holds the branch

### Tests for this story (write FIRST, must fail)

- [ ] T011 [US2] (spec US2-S1, FR-004) With the cross-registered fixture, call
      `worktrees.push_branch` against the non-owning repository and assert it
      refuses **before** any push subprocess runs — assert on the recorded
      subprocess calls, not only on the exception — and that the message names
      the branch, the worktree, the repository that actually holds the ref and
      the one that was asked to push.
- [ ] T012 [P] [US2] (spec US2-S2, FR-005) The same fixture through
      `sync_with_target`: assert it refuses rather than fetching in one
      repository and merging a remote-tracking ref inside a directory that
      belongs to another.
- [ ] T013 [P] [US2] (spec US2-S1, FR-004) A directory that exists under the
      factory root but is not a git worktree at all: assert the push path refuses
      by name rather than letting an exception raise through from the ownership
      probe, and that it does not pass by inheriting the enclosing clone
      (trap 1). The existing guard here is only `is_dir()`, which proves nothing.
- [ ] T014 [P] [US2] (spec US2-S3, FR-004, FR-005) A correctly owned worktree:
      assert the push still happens, the trunk guard still refuses a branch named
      like the landing branch on its own terms, the returned sha is still the
      worktree's head, and `tests/test_worktree.py` passes unmodified.
- [ ] T015 [P] [US2] (spec US2-S4, FR-004) Drive `open_landing_pr` in
      `factory/activities/merge_activities.py` over the cross-registered fixture
      and assert the ownership refusal arrives as a **non-retryable** application
      error whose type is not `PUSH_FAILED`; then drive an ordinary git failure
      through the same activity and assert it is still `PUSH_FAILED` and still
      retryable. Both halves, or the discrimination is unproven (plan R14).

### Implementation for this story

- [ ] T016 [US2] (FR-004) The assertion in `push_branch`, placed after the
      existing directory check and before the push, using the helper US1 landed
      in `factory/workgraph/worktree.py`. **Do not relocate the push into the
      worktree** — both clones on this host share one origin, so relocation would
      pass every test here while pushing on behalf of the wrong repository
      (trap 7).
- [ ] T017 [US2] (FR-005) The same assertion in `sync_with_target`, before the
      fetch. Same helper, same message shape; do not write a second derivation.
- [ ] T018 [US2] (FR-004) One new non-retryable error-type constant in
      `factory/activities/merge_activities.py`, in the style of `LANDING_REFUSED`
      already there, and one `except` clause for US1's ownership exception type
      placed **ahead of** the existing catch-all `except worktrees.WorktreeError`
      at `:367-368`. Every other `WorktreeError` keeps today's retryable
      `PUSH_FAILED` path unchanged. Do not widen the catch-all and do not make
      `PUSH_FAILED` itself non-retryable — a lock and a slow filesystem still are
      what a second attempt fixes (plan R14).

### Verification for this story

- [ ] T019 [US2] (spec US2-S1, SC-002) Commit the refused push: the message the
      factory now prints, pasted beside the bare `error: src refspec ... does not
      match any` it replaces, captured from the two-repository fixture.

## Phase 3: User Story 3 — The landing base is the branch the repo declares

### Tests for this story (write FIRST, must fail)

- [ ] T020 [US3] (spec US3-S1, FR-006) A fixture clone whose checked-out branch
      and whose declared landing branch DIFFER — no fixture in this tree does
      that today, which is why the suite is green against a broken base. Assert
      the opened proposal's base is the declared branch.
- [ ] T021 [P] [US3] (spec US3-S2, FR-007) Two clones: one declaring the branch
      in its manifest, one whose manifest is missing or malformed. Assert the
      resolved base is right in both cases **and** that the result states which
      arm answered — declaration or checked-out-HEAD fallback. The fallback path
      silently reinstates this defect if it is not labelled (trap 5).
- [ ] T022 [P] [US3] (spec US3-S3, FR-008) Assert both landing call sites in
      `factory/workgraph/workflow.py` — the first landing and the requeue after a
      rejection — reach the base through the one resolution path, with an
      explicit assertion for the requeue site, which is the one a busy epic runs
      most (trap 4).
- [ ] T023 [P] [US3] (spec US3-S4, FR-006) A node whose sidecar already records
      an operator branch as its `default_branch`: assert the base is still the
      declared branch. A fix that only changed what future sidecars record would
      leave every already-prepared node landing wrong.
- [ ] T024 [P] [US3] (spec US3-S2, FR-007) A request that still carries a
      non-empty `base` disagreeing with the declared branch — the shape a task
      scheduled by a pre-upgrade worker carries, and on this host the shape it
      carries *today*. Assert the activity opens against the DECLARED branch, does
      not raise, and logs that the supplied value was ignored and what it
      disagreed with. A refusal here would kill the ordinary upgrade-window
      payload, which is this spec's own defect class (plan R7).

### Implementation for this story

- [ ] T025 [US3] (FR-006, FR-007) Resolve the base inside `open_landing_pr` in
      `factory/activities/merge_activities.py` from the dispatched target repo's
      declared landing branch, using the resolver already in the tree — a git and
      manifest read inside an activity is legal where the workflow's would not
      be. Carry which arm answered in the result.
- [ ] T026 [US3] (FR-006, FR-008) Stop the workflow deciding it: both call sites
      in `factory/workgraph/workflow.py` pass no base, and the input field keeps
      an empty default so a task scheduled by an older worker still deserialises.
      A non-empty value is **ignored, never refused** (plan R7). **Do not touch
      the landed 020 test that pins `PreparedWorktree.default_branch`, and do not
      repoint the three captures inside `ensure` (trap 3).**
- [ ] T027 [US3] (FR-007) The log line the activity emits when it opens a
      proposal: the resolved base, the repository it was read from, which arm
      answered, and — only when one was supplied and differed — the ignored value.

### Verification for this story

- [ ] T028 [US3] (spec US3-S1, SC-003) Commit pasted output for both clones: the
      declared branch winning over a differing checkout with the arm named, and
      the fallback answer labelled as a fallback.

## Phase 4: User Story 4 — The epic refuses at dispatch, before it spends

### Tests for this story (write FIRST, must fail)

- [ ] T029 [US4] (spec US4-S1, FR-009) A fixture factory root holding worktrees
      for two nodes of one graph, both registered to another repository: assert
      the check returns a finding for **both** — not the first — each naming its
      owning clone, and that the finding names the factory root the check read.
      Two dispatch surfaces may read different roots, so the root is part of the
      answer, never an assumption.
- [ ] T030 [P] [US4] (spec US4-S2, FR-009) A graph whose nodes have no worktrees
      on disk, and one whose worktrees are correctly owned: assert the check
      returns nothing at all in both cases, and that it issues no git call for a
      directory that does not exist.
- [ ] T031 [P] [US4] (spec US4-S3, FR-010) A target repo declaring its landing
      branch: nothing reported. One whose manifest is missing or malformed, so
      the branch resolves from the checked-out HEAD: a finding naming the
      repository, the branch that would be used, and the fact that it was
      inferred rather than declared.
- [ ] T032 [P] [US4] (spec US4-S4, FR-011) Drive the roadmap's pre-dispatch
      activity in `factory/activities/roadmap_activities.py` over the same
      fixture and assert it returns the same findings as the CLI path — one
      implementation, two surfaces, asserted rather than assumed.

### Implementation for this story

- [ ] T033 [US4] (FR-009) The pure check in `factory/workgraph/preflight.py`,
      returning the finding type that module already defines. It takes the graph
      and a factory root and calls the ownership helper US1 landed in
      `factory/workgraph/worktree.py` — **import it, do not re-derive it**
      (plan R2), and do not edit either of the two functions US2 owns in that
      file. The root is the caller's to supply: the module reads no environment,
      because the CLI's root and the worker's root can differ (plan R5).
- [ ] T034 [US4] (FR-010) The landing-branch check in the same module: resolve
      the branch the way the landing will and report a finding only when it
      resolved by fallback rather than by declaration.
- [ ] T035 [US4] (FR-011) Wire both checks into `_run_preflight` in
      `factory/cli/nouns/build.py`, collected with the existing checks rather
      than short-circuiting them, so an author fixing one refusal per run is not
      the failure mode.
- [ ] T036 [US4] (FR-011) Wire the same two calls into the roadmap's pre-dispatch
      activity, which already imports the shared module. The activity owns the
      root; the module owns the check and the wording.

### Verification for this story

- [ ] T037 [US4] (spec US4-S1, SC-004) Commit the pre-dispatch report for a graph
      with two cross-registered nodes: both named in one pass, each with its
      owning clone, the factory root stated, and the remedy block an operator
      would run.

## Phase 5: User Story 5 — One agent execution, one session id

### Tests for this story (write FIRST, must fail)

- [ ] T038 [US5] (spec US5-S1, FR-012) The derivation as a pure function: given
      the issued id and execution attempt 1, it returns the issued id unchanged,
      so every existing archive name and status reading is untouched for the runs
      that never retry.
- [ ] T039 [P] [US5] (spec US5-S2, FR-012) Attempt 2 over the identical issued
      id returns a different value that parses as a UUID, and the same inputs
      always return the same output. Assert UUID validity explicitly: the runner
      rejects a malformed id before it rejects a duplicate one (plan R8).
- [ ] T040 [P] [US5] (spec US5-S3, FR-012) Through an injected runner seam,
      assert the invocation's session argument and the archived transcript
      filename name the same derived id — the launch key and the archive key are
      one string and must move together (plan R9). Label this transcript a seam
      capture.
- [ ] T041 [P] [US5] (spec US5-S4, FR-013) An attempt archive already holding a
      non-empty stdout log: after the next execution runs, assert the earlier log
      survives under a name stating which execution wrote it, and that the file
      the detector reads keeps its name and its meaning.
- [ ] T042 [P] [US5] (spec US5-S5, spec US5-S6, FR-014) One test module, both
      directions. A stdout log whose content is the runner's already-in-use
      refusal: assert the attempt becomes the existing non-retryable
      launch-failure error type, quoting the runner's own line, and **not** a
      missing transcript. Assert the behaviour; **do not assert the 74-byte
      length**, which is one CLI release from being wrong (trap 11). Then an
      ordinary non-zero exit carrying no marker: assert it is still an ordinary
      agent error and still ordinary ladder input — a classifier that raised on
      every non-zero exit would stop the node ever being graded.

### Implementation for this story

- [ ] T043 [US5] (FR-012) Derive the runner-visible id once, at the top of
      `run_agent_attempt` in `factory/activities/agent_activities.py`, from the
      workflow-issued id and this execution's attempt number, and pass the
      replaced frozen context down. The workflow's two issuance sites are
      untouched — the replay property is preserved because the workflow computes
      nothing new (traps 9 and 10). Add no field to the attempt context: its
      field set is closed on purpose.
- [ ] T044 [US5] (FR-013) In `factory/workgraph/adapter.py`, move an existing
      non-empty stdout log aside before the truncating open, under a name that
      states which execution wrote it. Do not rename the live file and do not
      append to it (plan R10).
- [ ] T045 [US5] (FR-014) The refusal marker constant beside
      `SUBSCRIPTION_REFUSAL_MARKER`, and its classifier following that
      precedent's DETECTION only. The outcome is `AGENT_LAUNCH_FAILED`,
      non-retryable, raised on the success path beside the existing
      `except AdapterError` — **not** a new `Termination` member, not a DDL
      change, not a ledger migration (plan R13). The subscription classifier
      *returns* a reclassified result; this one *raises*.
- [ ] T046 [US5] (spec US5-S3, FR-012) Confirm nothing else reads the issued id
      directly: the invocation argument and the transcript archive lookup both
      read it off the context, so one replacement covers both. If a third reader
      exists, route it through the same value rather than re-deriving.

### Verification for this story

- [ ] T047 [US5] (spec US5-S2, SC-005) Commit the derived ids for execution
      attempts 1 and 2 from one issued id — attempt 1 unchanged, attempt 2 a
      different valid UUID — and the archive directory listing after a second
      execution, showing both logs present. Label both as seam captures.

## Phase 6: User Story 6 — A rescued landing is visible

### Tests for this story (write FIRST, must fail)

- [ ] T048 [US6] (spec US6-S1, FR-015) A fixture repository whose landing branch
      carries a commit with a prose subject and a rescue trailer in its body
      naming this epic, node and story: assert the story reads as landed at that
      commit with a provenance kind distinct from the queue-observed one.
- [ ] T049 [P] [US6] (spec US6-S2, FR-016) A history of commits with multi-line
      bodies, blank lines, and subjects containing every delimiter the reader
      uses: assert every commit parses and that no body line is read as a
      subject. Widening the read is a change to how the log is SPLIT, not a regex
      change (trap 12).
- [ ] T050 [P] [US6] (spec US6-S3, FR-015) One commit that matches a subject
      grammar and also carries the trailer: assert the declared precedence
      decides which kind is recorded, rather than leaving it to scan order.
- [ ] T051 [P] [US6] (spec US6-S4, FR-015) A trailer naming an epic or a story
      the spec does not declare: assert it is ignored exactly as an unrecognised
      subject is. A rescue grammar may never mark an unbuilt story landed
      (trap 13).
- [ ] T052 [P] [US6] (spec US6-S5, FR-017) Drive the landed reader's CLI over a
      spec with one landed story and two unlanded ones: assert it prints, for
      each unlanded story only, the exact pull-request title and the exact
      trailer line a rescue must carry.

### Implementation for this story

- [ ] T053 [US6] (FR-016) Widen the log read in `factory/workgraph/landed.py` to
      commit bodies using a record separator, and rewrite the splitting loop.
      `git log -z --format=%H%x1f%B` is verified working on this tree. This half
      is shippable green on its own and is the first half of US6's fallback split
      seam (plan § Sizing) — do it first, and if the diff approaches the cap,
      stop here and take the seam.
- [ ] T054 [US6] (FR-015) The trailer grammar beside the two existing ones, its
      own provenance kind on the reader's enum, and the precedence rule: subject
      grammars first, trailer last, newest-first and first-seen-per-story
      unchanged. **Add a grammar; do not widen the existing anchored one**
      (trap 13). Check whether any code converts this enum into the roadmap's
      separate two-member one; cover it or state that no conversion exists.
- [ ] T055 [US6] (FR-017) The printer in `factory/workgraph/cli.py`: for every
      story the reader found no landing for, print the exact title and trailer,
      ready to paste. The story list comes from the spec text that function has
      already read.

### Verification for this story

- [ ] T056 [US6] (spec US6-S1, SC-006) Commit pasted output of the landed reader
      for a fixture spec with one rescued story and one unbuilt one: the rescued
      story reported landed with its own kind, and the unbuilt one printed with
      the exact title and trailer a rescue would need. State in the file that no
      grammar recovers an already-merged prose-titled rescue (trap 14).
