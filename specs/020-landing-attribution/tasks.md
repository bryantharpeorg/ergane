# Tasks: Landing Attribution

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      hosts the work, and record the answers here. Three things specifically,
      because each one carries a story: that `_TOP_LEVEL_KEYS` still holds five
      names; that `_default_branch` still has exactly the six callers the table
      lists, classified the same way (a seventh means the table is incomplete,
      not that the seventh is safe); and that `_git_log_subjects` still passes no
      `--no-merges`, because US2 is dead code the moment it does. Also settle the
      import question plan.md § US1 leaves open — whether
      `factory/workgraph/worktree.py` can import `factory.verify.factory_yaml`
      without a cycle — and say which way it went.

---

## Phase 2: User Story 1 — The landing branch is declared once (Priority: P1) 🎯 MVP

**Goal**: `landing_branch` is declared in the manifest and read by every site
that *decides* on a branch; sites that report a clone's checked-out branch are
untouched.

**Independent Test**: with a manifest declaring a branch and a clone checked out
on an unrelated one, the base ref a node pins and the branch a reader scans are
both the declared branch.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q` green;
      `factory/verify/factory_yaml.py`, `factory/workgraph/worktree.py`,
      `factory/workgraph/cli.py` and `factory/activities/roadmap_activities.py`
      exist and plan.md's inventory claims hold — constitution II gate; STOP and
      report blocked if not satisfied.
- [ ] T003 [P] [US1] Write manifest-schema cases FIRST against
      `parse_factory_config`: `landing_branch: some-branch` parses and lands on
      `FactoryConfig`; a manifest omitting it yields `"main"`; `landing_branch:`
      with no value, a non-string, and an empty/whitespace string each fail
      naming the key, in the same shape `standards` uses
      (`factory/verify/factory_yaml.py:268-288` is the template); the key is
      accepted by `_reject_unknown_keys` — must fail.
- [ ] T004 [P] [US1] Write resolution cases FIRST for the new
      `landing_branch(target_repo)` helper: a repo whose manifest declares one
      returns it; a repo with **no** `factory.yaml` falls back to the clone's
      checked-out branch (today's behaviour, FR-003); a repo whose manifest the
      schema refuses does the same rather than raising, matching
      `_declared_standards`'s posture (`factory/activities/agent_activities.py:655`)
      — must fail.
- [ ] T005 [US1] Write the base-ref case FIRST against a **fixture git
      repository**, which is the live failure `ergane-003-target` demonstrates:
      a clone checked out on an unrelated branch, whose manifest declares the
      landing branch, pins `origin/<declared>` as its base ref — not the
      checked-out branch's head. This is the story's reason for being P1: the
      same helper feeds `capture_base_ref` (`factory/workgraph/worktree.py:176`),
      so it decides what every node builds from — must fail.
- [ ] T006 [P] [US1] Write the push-guard case FIRST (plan.md § US1, third
      trap): with a clone checked out on an unrelated branch and a manifest
      declaring the landing branch, a node branch whose name equals the
      **declared** branch is refused (`factory/workgraph/worktree.py:302`) — a
      guard reading the clone's branch would let it through — must fail.
- [ ] T007 [P] [US1] Write the observation-sites regression FIRST — the negative
      half of the story: `PreparedWorktree.default_branch` and the roadmap's
      `CloneResult.default_branch` still report the branch the clone has checked
      out, **not** the declared one, because they record an observation about the
      clone. Repointing them is the plausible over-reach this test exists to
      catch — must fail only if the implementation over-reaches, so state that
      explicitly in the test's docstring.
- [ ] T008 [US1] Write CLI-default cases FIRST, the ones that cannot be faked:
      `factory-epic landed` with **no** `--default-branch` scans the declared
      branch; an explicit `--default-branch` overrides the manifest; a delta
      derivation's baseline comes from the declared branch rather than from the
      literal `"main"` at `factory/workgraph/cli.py:348`. plan.md § US1's first
      trap is the failure mode: the parser's `default="main"` (`:895`) must
      become `None` or the manifest can never win — must fail.

### Implementation for User Story 1

- [ ] T009 [US1] Implement the manifest key: `_TOP_LEVEL_KEYS`, a
      `_read_landing_branch` beside `_read_standards`, and the field on
      `FactoryConfig` — until T003 passes.
- [ ] T010 [US1] Implement `landing_branch(target_repo)` and point the **four
      decision sites** at it: `capture_base_ref` (`:176`), the push guard
      (`:302`), `land`'s fetch (`:363`), and the roadmap's landed-facts read
      (`factory/activities/roadmap_activities.py:268`, whose own `"main"`
      fallback at `:216-223` is FR-004's subject). **Leave the four observation
      sites alone** — `worktree.py:212`, `:228`,
      `roadmap_activities.py:108`, `:184`. Until T004, T005, T006 and T007 pass.
- [ ] T011 [US1] Implement the CLI resolution until T008 passes: the parser
      default becomes `None`, `landed_command` resolves flag-then-manifest-then-
      `"main"`, and `_build_baseline` reads the manifest instead of assigning the
      literal. Both already hold the repo path via `_target_repo_for_spec`, so
      neither needs a new argument.
- [ ] T012 **OPERATOR ONLY — NO NODE MAY DO THIS.** Declaring
      `landing_branch: ergane-buildout` in this repository's own `factory.yaml`
      is one line, and it **killed the 2026-08-09 run of this story**. Read plan
      trap 1 before touching that file. The config gate parses a node's
      `factory.yaml` with the **worker's installed parser**, not the worktree's,
      so a node that declares the key is rejected with `CONFIG_ERROR` at 0.0s
      before any gate command runs — no matter that its own worktree contains a
      parser which accepts it. Four attempts failed identically and the epic was
      parked.
      The key may be declared only after (a) US1's parser change has **landed**
      and (b) the worker has been **restarted** on it. Neither can happen inside
      this epic, so this is not US1's task, not US2's, and not any node's. The
      operator does it afterwards, in a plain commit.

---

## Phase 3: User Story 2 — Landings older than the merge queue are read as history (Priority: P1)

**Goal**: `landed_facts` recognizes the pre-queue merge subject, with its own
provenance kind, in the same `git log` pass.

**Independent Test**: against a repository holding 006's three pre-queue merges,
`factory-epic landed` reports US1, US2 and US5 with the historical kind, and a
delta derivation emits only what is genuinely absent.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T013 [US2] Write the **negative** cases FIRST, before the positive ones,
      because they are the ones that cost something if wrong (plan.md § US2,
      fourth trap): `salvage(006-interpreter-hardening/us5): completed attempt 1`
      is not a landing under either recognizer — it carries `<epic>/<node>` in
      the same order and is in every branch's history; nor is
      `salvage(003-merge-queue/us1): killed attempt 1`; nor are the operator
      subjects `017-peer-channel: US4 — <prose>` and `006 US1: <prose>`; nor is a
      merge for a different epic — must fail.
- [ ] T014 [US2] Write the positive cases FIRST: `Merge branch
      'factory/006-interpreter-hardening/us1' into ergane-buildout` is a landing
      for `006-interpreter-hardening` story `US1` at that commit; the story key
      comes from the node id by upper-casing; an inferred key the spec does not
      declare is **not** a landing (spec § Edge Cases) — must fail.
- [ ] T015 [P] [US2] Write the provenance case FIRST: the fact carries a
      `LandedKind` distinct from both `OBSERVED` and `ATTESTED`, and
      `factory-epic landed`'s line shows it — `landed_command` already prints
      `fact.kind.value` (`factory/workgraph/cli.py:239`), and asserting it is how
      a rendering regression gets caught rather than assumed away — must fail.
- [ ] T016 [US2] Write the precedence case FIRST (FR-007): a story with both a
      pre-queue merge and a **newer** queue landing resolves to the queue
      landing. Today this holds only because the scan is newest-first and the
      loop says `if story_key not in observed`
      (`factory/workgraph/landed.py:110`) — a property of the loop's shape, which
      the next restructuring will not know is load-bearing — must fail.
- [ ] T017 [US2] Write the end-to-end case FIRST against a **fixture git
      repository containing a real merge commit** (plan.md § US2, third trap):
      `landed_facts` over that repository reports the story. A string-level test
      alone would keep passing if `_git_log_subjects`
      (`factory/workgraph/landed.py:154`) ever gained `--no-merges`, which would
      make this entire story dead code with a green suite — must fail.

### Implementation for User Story 2

- [ ] T018 [US2] Implement the second recognizer and the third `LandedKind` in
      `factory/workgraph/landed.py` until T013–T017 pass. Anchor the pattern end
      to end and require the whole subject to be the merge sentence. Cite
      `factory/workgraph/derive.py:184` (`id=story_key.lower()`) in the comment
      above the upper-casing — it is the entire justification for the inference,
      and without it a reader sees a guess. Add the comment FR-007 asks for:
      newest-first plus first-seen-wins is why a queue landing beats an older
      merge, and it must survive a restructuring of the loop.
- [ ] T019 [US2] Final sweep + docs: `docs/decisions.md` gains a numbered entry
      claimed at landing — the landing branch is declared, and the pre-queue
      grammar is read as history with its own provenance — and
      `docs/architecture.md`'s attribution section records both. State the
      boundary: this makes the reader honest about history the factory already
      wrote; it adds **no writer** and the historical grammar is closed (spec §
      Assumptions). Confirm no new dependency and no store.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything; T001's `--no-merges` check in
  particular, because a negative answer invalidates US2 before it is dispatched.
- Phase 2 (US1) has no dependency and is the MVP: the branch stops being a guess,
  and `capture_base_ref` stops depending on what a clone happens to have checked
  out.
- Phase 3 (US2) chains on US1 **merged**. The two share no file, so this is not
  conflict avoidance — it is that US2's acceptance evidence is `factory-epic
  landed` returning 006's landings *with no flag*, which is US1's behaviour.
  Dispatched as siblings, US2 would be verified against a workaround.

## Implementation Strategy

US1 alone is worth landing: it converts a convention into a declaration, and it
fixes a dispatch-time defect rather than a reporting one — a clone left on the
wrong branch currently decides what every node of an epic builds from. US2 is
what retires the hand-written remainder graph, and it is small: one pattern, one
enum member, one comment that explains an inference.

Neither story changes what any agent is asked to do, what the judge scores, or
what the merge queue writes. The factory's *writer* of landing subjects is
untouched; this is entirely about what its readers understand.
