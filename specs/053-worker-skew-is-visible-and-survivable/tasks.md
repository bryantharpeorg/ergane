# Tasks: 053-worker-skew-is-visible-and-survivable

Three stories. US2 and US3 each carry a **merge edge** to US1 — they need its
guard decisions to exist before they can assert or extend them, and all three
touch `factory/cli/nouns/build.py` or the tests that read it.

Work test-first and commit once per task. Read `plan.md` before the first
commit: **trap 1** (the finding's own notes name the wrong file) and **trap 2**
(`provenance` already has a default) are the two that produce a confident,
green, useless diff.

## Phase 1: User Story 1 — A refused query degrades `build status` instead of killing it

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1) Write the degradation case FIRST: an
      `epic_status` query raising `WorkflowQueryFailedError` — **imported from
      `temporalio.client`, never a local subclass of `RPCError`** (plan trap 6) —
      leaves `ergane build status <epic>` completing at exit 0, with the epic
      reported unavailable and the refusal's own message shown. Must fail.
- [ ] T002 [P] [US1] (spec US1-S2) Write the transport-path case FIRST: an
      `RPCError` produces byte-identical behaviour to today's, **including the
      `NOT_FOUND` path** that reports "no epic is running here"
      (`build.py:470`). Write it, watch it pass, and say so in the commit.
- [ ] T003 [P] [US1] (spec US1-S3, FR-004) Write the write-verb case FIRST: at
      least one signal-sending verb still exits non-zero when its call fails. A
      write must not learn to shrug. Must fail if the repair over-widens.
- [ ] T004 [P] [US1] (spec US1-S4, FR-005) Write the no-bare-catch case FIRST: no
      `except Exception` guards a Temporal call in
      `factory/cli/nouns/build.py`. Write it before the implementation so one
      cannot be introduced.

### Implementation for this story

- [ ] T005 [US1] Import the classes the client actually raises into
      `factory/cli/nouns/build.py` — it has none today (`build.py:26`) — and
      catch them at the query site, `:468`/`:469`.
- [ ] T006 [US1] Decide the remaining seven sites **individually** and record the
      reasoning in the source, not only in the diff: `:285` (`_live_spend`, a
      read), `:492` (`describe`, a read), and the five write paths `:616`,
      `:636`, `:717`, `:758`, `:917`. Reads degrade, writes die (plan trap 4).
      T003 and T004 pin whatever you choose.
- [ ] T007 [US1] Commit the SC-001 transcript: `ergane build status <epic>`
      against a workflow that refuses `epic_status`, exit code captured with
      `rc=$?` **before** any pipe (plan trap 11). Capture it before the worker is
      next restarted — the machine stops being able to produce this evidence at
      that moment.

## Phase 2: User Story 2 — The guard sweep covers every module that awaits Temporal

### Tests for this story (write FIRST, must fail)

- [ ] T008 [US2] (spec US2-S1, FR-007) Write the discovery sweep FIRST: it finds
      every CLI module containing a function that awaits Temporal — reusing
      `_awaiting_functions()` at `tests/test_ergane_status.py:1505`, which is
      already module-agnostic — and asserts each such function's guard set by
      name. Must fail.
- [ ] T009 [P] [US2] (spec US2-S2) Write the anti-vacuity assertion FIRST: the
      discovered module set is non-empty and names both
      `factory/cli/status.py` and `factory/cli/nouns/build.py`. Run the
      point-at-nothing mutation **first**, before any other mutant (plan trap 7).
- [ ] T010 [P] [US2] (spec US2-S3) Write the negative case FIRST: a module whose
      guard names a class the client cannot raise fails the sweep, and the
      failure names the module, the function and the class. Must fail.

### Implementation for this story

- [ ] T011 [US2] Generalize `EXPECTED_GUARDS`
      (`tests/test_ergane_status.py:1494`) and its input from one `__file__` to
      the discovered set, **leaving its existing entries for `collect_floor`,
      `_disposition` and `_running_epics` holding unchanged** (spec US2-S4, plan
      trap 8).

## Phase 3: User Story 3 — The operator can see that the worker is not the tree

### Tests for this story (write FIRST, must fail)

- [ ] T012 [US3] (spec US3-S1, FR-009) Write the skew case FIRST: a worker
      revision differing from the CLI's makes a degraded read verb name both
      revisions and state that the worker is running different code. Must fail.
- [ ] T013 [P] [US3] (spec US3-S2, FR-009) Write the quiet case FIRST: matching
      revisions produce no skew notice anywhere. A warning that is always on is
      not a warning (plan trap 10). Must fail if the notice is unconditional.
- [ ] T014 [P] [US3] (spec US3-S3, FR-010) Write the absent case FIRST: a worker
      that recorded no revision — pre-dating this story, or not a git checkout —
      degrades to today's behaviour without raising and is reported as unknown,
      never inferred. Must fail.
- [ ] T015 [P] [US3] (spec US3-S4, FR-008) Write the capture-once case FIRST: the
      revision is read at worker start and carried, not recomputed per call. A
      per-call read reports the tree's revision, so the two would always match
      and T012 could never fail (plan trap 9). Must fail.

### Implementation for this story

- [ ] T016 [US3] Capture the revision once at `factory/worker.py:201`
      (`build_worker`) and carry it in the query answer.
- [ ] T017 [US3] Compare at the CLI and render the notice on the degraded path
      only.

## Verification

- [ ] T018 Full suite, verbatim, with the cache state it was run in. Quote
      `passed` and `skipped`, never the warning count (plan trap 13); a new skip
      is a hidden test and must be declared.
- [ ] T019 Mutation battery with a point-at-nothing control as its **first** row,
      `__pycache__` purged between mutants or `PYTHONDONTWRITEBYTECODE=1` set
      (plan trap 12), tree asserted clean — tracked and untracked — before and
      after.
- [ ] T020 Commit the SC-005 before/after transcript pair proving same-revision
      output is byte-identical to today's.
- [ ] T021 Diff measured through `size_refusal` from
      `factory/verify/diffbounds.py`, importing `DIFF_INPUT_LIMIT` rather than
      quoting it, with the number reported.
