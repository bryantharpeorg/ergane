# Tasks: a landed read says what it could not see

Read `plan.md` before starting. Two traps decide whether this story is worth
anything. Trap 1: the obvious fix — make the attestation fallback return nothing
on a truncated history — reproduces the defect in a second form, because the empty
mapping is what `tests/test_landed.py:587` —
`test_unattested_unattributed_spec_yields_empty_baseline` asserts means "nothing
landed". Trap 2: a shallow fixture cloned by plain path is not shallow at all —
git prints `warning: --depth is ignored in local clones; use file:// instead.` and
gives you a complete clone — so the test that was meant to prove the defect proves
nothing and lands green. Trap 3 names the one thing this spec must not build.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The read measures the history before it trusts it

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-002, traps 1 and 2) Build one
      repository with a real attributed landing using `tests/test_landed.py:101` —
      `repo_builder`, clone it twice — once complete, once with
      `git clone --depth 1 file://<path>` — and assert **both halves in one test**:
      the complete read returns the story pinned at its real landing commit, and
      the truncated read raises a degradation whose message names the incomplete
      history. Assert `rev-parse --is-shallow-repository` prints `true` for the
      shallow clone inside the test, so a fixture that silently came back complete
      fails loudly instead of passing.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, trap 1) Assert, in one test, that a
      truncated history over an **unattested** spec raises the same named
      degradation, and that a complete history over that same unattested spec still
      returns the empty mapping. Only the pair can fail a diff that "fixed" the
      shallow case by returning `{}`.
- [ ] T003 [P] [US1] (spec US1-S3, FR-004) **The control.** Assert the facts
      returned for a complete history are identical to today's, entry for entry,
      and that the measurement costs exactly one additional git invocation.
- [ ] T004 [P] [US1] (spec US1-S4, FR-002, trap 4) Assert the derivation path over
      a truncated target clone refuses with a message naming the incomplete history
      rather than compiling a delta. Drive
      `factory/activities/roadmap_activities.py:393` — `_derive_from_git`, not the
      activity, so the assertion needs no Temporal server.
- [ ] T005 [P] [US1] (spec US1-S5, FR-005, trap 10) Assert the readiness basis for
      a specs root held by a truncated repository names the incomplete history, and
      assert the sentence emitted at `factory/cli/status.py:413-419` — the one
      claiming landings on the branch were read — does **not** appear in it.

### Implementation for this story

- [ ] T006 [US1] (FR-001, trap 10) Add one exported helper to
      `factory/workgraph/landed.py` that answers whether a repository's history is
      complete, by shelling `rev-parse --is-shallow-repository` through the module's
      existing `_git`. Both doors must call this one helper; do not write a second
      `rev-parse` in `factory/cli/status.py`.
- [ ] T007 [US1] (FR-002, FR-003, trap 9) Add the degradation type as a subclass of
      `WorktreeError` and raise it from `factory/workgraph/landed.py:130` —
      `landed_facts` **before** the scan begins. Raising it from any helper called
      underneath `factory/workgraph/landed.py:360` — `_attesting_commit` is
      swallowed by the `except WorktreeError` at
      `factory/workgraph/landed.py:375` and turns back into "root commit".
- [ ] T008 [US1] (FR-004) Confirm by reading that the complete-history path is
      unchanged: the guard is one call and one branch above the existing body, and
      no line of the scan, the fallback at `factory/workgraph/landed.py:229` or
      `factory/workgraph/landed.py:257` — `_resolve_default_head` is edited.
- [ ] T009 [US1] (FR-005, trap 10) Branch `factory/cli/status.py:378` —
      `_readiness_basis` on the helper's answer and return a `ReadinessBasis` with
      `observed=False` and a detail naming the incomplete history, modelled on the
      degraded arm already at `factory/cli/status.py:404-411`. Import the helper the
      way `factory/cli/status.py:106` already imports `_resolve_default_head`.

### Verification for this story

- [ ] T010 [US1] Paste, as committed evidence, the reader's output for the same
      spec read from a complete clone and from a depth-1 clone of the same
      repository — the first naming the real landing commits, the second the
      refusal — together with the `rev-parse --is-shallow-repository` line for each
      clone that proves which is which.

## Phase 2: User Story 2 — The one verb an operator aims at the reader can read offline, and reports what it could not see

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1, FR-006) Assert the verb invoked with
      `--no-fetch` calls the reader with `fetch=False`, proven by a recorded call
      rather than by the absence of network traffic.
- [ ] T012 [P] [US2] (spec US2-S2, FR-007, trap 7) Assert, in one test, that the
      verb without the flag calls the reader with the fetching default **and** that
      an argument object carrying neither the new flag nor `as_json` — the shape
      `tests/test_landed.py:350` already constructs — still succeeds. The second
      half is what fails a diff that reads `args.no_fetch` directly;
      `factory/workgraph/cli.py:205` already shows the `getattr` form.
- [ ] T013 [P] [US2] (spec US2-S3, FR-008) Assert a read that cannot resolve the
      landing branch produces a message naming the degradation and the branch, and
      assert the string `cannot read landed facts for` does **not** appear in it.
- [ ] T014 [P] [US2] (spec US2-S4, FR-009, trap 8) Assert a degraded run prints
      every declared story as unconfirmed **and** that neither the rescue
      pull-request title nor the rescue trailer appears anywhere in the output.
      Today the command prints nothing at all, so the first half cannot pass before
      the change and the second half cannot pass after a lazy one.
- [ ] T015 [US2] (spec US2-S5, FR-010, trap 6) Assert the degraded run's exit code
      through `factory/cli/nouns/spec.py:452` — `_landed_command`, not through
      `landed_command` alone: it must be `3` and must be neither `1` nor `2`.
      Assert in the same test that the `--json` document carries the degradation as
      a field beside `facts`. Not `[P]`: it drives both output forms over one
      fixture.

### Implementation for this story

- [ ] T016 [US2] (FR-006, FR-007, trap 7) Add `--no-fetch` beside `--json` at
      `factory/cli/nouns/spec.py:225`, in the subparser at
      `factory/cli/nouns/spec.py:216`, and read it in
      `factory/workgraph/cli.py:168` — `landed_command` with
      `getattr(args, "no_fetch", False)`, passing it as `fetch=not no_fetch` to the
      call at `factory/workgraph/cli.py:188`.
- [ ] T017 [US2] (FR-008, FR-009, trap 8) Replace the raise at
      `factory/workgraph/cli.py:190-192` with a named degradation that carries git's
      own reason, and render the report in the degraded form: every declared story
      listed as unconfirmed, and none of the rescue output at
      `factory/workgraph/cli.py:230-238` or its `--json` counterpart at
      `factory/workgraph/cli.py:209-221`.
- [ ] T018 [US2] (FR-010, trap 6) Make the degraded run exit with the unified
      transport code at `factory/cli/errors.py:26`. Do **not** return
      `factory/workgraph/cli.py:69`'s `EXIT_TRANSPORT`, which is `2` and which
      `factory/cli/errors.py:25` defines as the usage code: only a *raised* old code
      is translated, at `factory/cli/nouns/spec.py:107`, and a returned one reaches
      the shell through `factory/cli/errors.py:52` — `run_cli` untouched.
- [ ] T019 [US2] (FR-006, trap 4) Confirm by reading that no `fetch=` argument was
      added or changed at `factory/workgraph/cli.py:452`,
      `factory/activities/roadmap_activities.py:409` or
      `factory/activities/roadmap_activities.py:532`. **If any of them changed, the
      design is wrong**: those three decide what gets built and may not read a stale
      baseline.

### Verification for this story

- [ ] T020 [US2] Paste, as committed evidence, three transcripts of the verb over
      one spec: the fetching form succeeding, the `--no-fetch` form succeeding, and
      the degraded form — showing the named degradation, the unconfirmed story
      list, the absence of any rescue line, and the exit code captured with
      `echo $?`.

## Verification

- [ ] T021 The full gate command passes green.
- [ ] T022 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Steps 1 and 2 together are the falsifiable test
      of this whole spec: the same spec, read from a depth-1 clone and from the full
      tree, must give one honest refusal and one unchanged answer instead of two
      confident answers of which one is false.
