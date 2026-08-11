# Tasks: The test suite owns its stores

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs, except where a task's docstring says
it guards against over-reach and passes today. A task that finds its must-fail
test already passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order. US1's and US2's tests share one new file
(`tests/test_store_isolation.py`), so almost nothing here parallelizes — that is
deliberate.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      hosts the work, and record the answers here. Four things in particular,
      because each moves the plan if wrong: that `tests/conftest.py` still has
      **no** session-scoped env fixture (if one appeared, 027 or a sibling
      landed first — plan trap 6 says extend it, not add a second); that the
      store resolution is still env-or-relative-default at
      `verify_activities.py:121-123` and `notify_activities.py:585-592` (grep
      `def _store_path`); that `run_roadmap` in `tests/test_roadmap_scheduler.py`
      and `_worker` in `tests/test_ergane_roadmap.py` still register the real
      `send_escalation` (if someone stubbed them per-file, US1-S3's demonstration
      seam moved); and that `connect()` in `factory/verify/store.py` still does
      its `mkdir` before `sqlite3.connect` (grep `def connect`), because FR-009
      is worded against exactly that ordering.
- [ ] T002 Operator: clean the fixture rows out of the live store — verification
      query first, and no schema change, no VACUUM, no service restart (an epic
      and the notify bridge are live against this file). Step 1, verify:
      `sqlite3 -readonly /home/admin/code/ergane/.factory/verification.db
      "SELECT escalation_id, sent_at, delivered FROM escalations WHERE
      workflow_id = 'roadmap-specs' ORDER BY sent_at;"` — expected as of
      2026-08-11: **nine** rows (the finding's three from 08-09 plus two later
      leak runs), ids `f13716f72c9e`, `564d5541ad69`, `72d3e6de02be`,
      `e41273af7a65`, `b0b605c06930`, `982a635030c2`, `3a2cc7343b5e`,
      `116d08d9f36d`, `4203b5c9531c`. If more have appeared, confirm each new
      row's `history_summary` (the column's actual name — there is no `summary`
      column) matches the fixture grammar (`max_concurrent_nodes must be a
      positive integer, got …` or `Roadmap roadmap-specs recovered …`) before
      proceeding. Step 2, also verify the sibling table:
      `SELECT * FROM roadmap_failures WHERE roadmap_id = 'roadmap-specs';` —
      expected: one row, `consecutive_count = 0`, fixture text. Step 3, delete
      both: `DELETE FROM escalations WHERE workflow_id = 'roadmap-specs';` and
      `DELETE FROM roadmap_failures WHERE roadmap_id = 'roadmap-specs';`.
      Step 4, re-verify: zero `roadmap-specs` rows remain, and the four genuine
      escalations (`epic-003-merge-queue`, `epic-007-parallel-dispatch`,
      `epic-020-landing-attribution`, `epic-021-roadmap-operability`, one each)
      are untouched. Record the final `SELECT COUNT(*) FROM escalations` — that
      number is SC-001's baseline. A later button press on a deleted row's
      message is answered "no longer on record" by the bridge's own unknown-id
      path; that is the designed outcome, not a loose end.

---

## Phase 2: User Story 1 — No test can reach the real store (Priority: P1) 🎯 MVP

**Goal**: a session-scoped autouse fixture owns `FACTORY_ROOT`,
`FACTORY_VERIFICATION_DB_PATH`, `FACTORY_LEDGER_PATH` and the two Telegram
credentials for every test, unconditionally, so the operator's exports can no
longer reach any test — and the live smoke still gets the credentials through
one visible, deliberate door.

**Independent Test**: a subprocess pytest run with all five variables poisoned
proves resolution lands under tmp, nothing was created at the poisoned paths,
and no credential is visible to the inner tests.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T003 [US1] Verify prerequisites in this worktree: full suite green
      (`uv run pytest -q`); `tests/conftest.py`, `tests/test_live_notify.py`
      and the plan's inventory claims hold — constitution II gate; STOP and
      report blocked if not satisfied.
- [ ] T004 [US1] Write the in-suite invariant test FIRST, in a new
      `tests/test_store_isolation.py`: `FACTORY_ROOT`,
      `FACTORY_VERIFICATION_DB_PATH` and `FACTORY_LEDGER_PATH` all point under
      `tmp_path_factory.getbasetemp()`, `FACTORY_ROOT`'s value is absolute
      (FR-002), `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are absent from
      `os.environ`, and the four production resolvers —
      `verify_activities._store_path()`, `notify_activities._store_path()`, the
      agent activities' factory root, the usage activities' ledger path — each
      resolve under that base (spec US1-S1, US1-S2) — must fail.
- [ ] T005 [US1] Write the poisoned-shell subprocess proof FIRST, in the same
      file: run `sys.executable -m pytest tests/test_store_isolation.py -k
      invariant -q` from the repo root with an env of `os.environ` plus
      fabricated values for all three path variables (plan trap 7: roots that
      cannot exist, never any real `.factory`) and fake Telegram credentials;
      assert exit code 0, assert no poisoned path exists afterward, and have the
      inner invariant test additionally assert the stash holds exactly what the
      parent shell exported — the fake credentials in this proof, empty in a
      bare run, so the same test stays green when the ordinary suite runs it —
      while `os.environ` lacks them either way; that capture is the live
      smoke's supply line (spec US1-S1, US1-S5) — must fail. One subprocess, not parametrized: the suite has an open slowness
      finding.
- [ ] T006 [US1] Write the leaking-writer containment case FIRST, same file:
      execute the real `send_escalation` **and** `record_roadmap_failure`
      activities (the exact writers the roadmap harnesses register — plan
      inventory) via `ActivityEnvironment` with `roadmap-specs`-shaped inputs
      and **no** env manipulation of your own; assert the escalation row and
      the `roadmap_failures` row both land in the store at the session's
      `FACTORY_VERIFICATION_DB_PATH` under tmp, that the escalation result
      reports `delivered=False` (no credential reached the activity), that no
      request left the process, and that the cwd-relative default
      `.factory/verification.db` was not created (spec US1-S2, US1-S3) — must
      fail.

### Implementation for User Story 1

- [ ] T007 [US1] Add the session-scoped autouse fixture and the credential
      stash to `tests/conftest.py`, per plan § US1: `pytest.MonkeyPatch()` with
      an `undo()` finalizer, paths under `tmp_path_factory.getbasetemp()`,
      `setenv` never `setdefault` (plan trap 2 — all three variables, not just
      `FACTORY_ROOT`), capture-then-`delenv` for the two credentials, stash
      exposed as its own session fixture that tests must request by name. Do
      not edit the leaking harnesses (plan traps 1 and 3) and do not touch
      `scripts/ergane-env.sh` (FR-007). Until T004–T006 pass.
- [ ] T008 [US1] Update `live_config` in `tests/test_live_notify.py` to consume
      the stash (plan trap 4): skip when either credential is absent from the
      stash — capture the skip output of
      `uv run pytest tests/test_live_notify.py -q` in a bare shell before and
      after this change and include both in the handoff as the equivalence
      evidence — and when present, re-plant both into env within the module's
      existing `MonkeyPatch` scope so the activity under test still reads them
      (spec US1-S5). No other file consumes the stash.
- [ ] T009 [US1] Run the full suite twice and record both outcomes: once in the
      gate's ordinary env, once with all five variables exported as poison
      (fabricated paths, fake credentials). Both green, with the delenv-default
      tests (`tests/test_agent_activities.py`, grep `delenv(FACTORY_ROOT_ENV)`)
      and the absent-credential tests passing unchanged (spec US1-S4). If the
      poisoned run and the bare run disagree, the fixture has a conditional in
      it — find it.

---

## Phase 3: User Story 2 — The store refuses non-tmp construction under pytest (Priority: P2)

**Goal**: `factory/verify/store.py::connect()` is the enforcement the fixture's
convention cannot be: during a test, a store outside the tmp tree is an error
that leaves no trace — except through the operator's explicit acknowledgment
variable, which keeps the live smoke's sanctioned door open.

**Independent Test**: with `PYTEST_CURRENT_TEST` naturally present, `connect()`
on a fabricated non-tmp path raises before creating anything; with the
acknowledgment set, it proceeds; with the sentinel absent, behavior is
byte-identical to today.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T010 [US2] Verify the base first — plan trap 5: `tests/conftest.py` in
      this worktree must already contain US1's session isolation fixture. If it
      does not, the merge edge was not honored; STOP and report blocked rather
      than weakening the guard to get the suite green.
- [ ] T011 [US2] Write the refusal case FIRST, in
      `tests/test_store_isolation.py`: `connect()` on a fabricated absolute
      path outside tmp whose parent does not exist raises an error naming the
      path and the finding key
      `hardening/test-suite-writes-to-the-live-evidence-store`, and afterward
      neither the file nor any parent directory exists — FR-009's ordering,
      refusal before the `mkdir` (spec US2-S1). Plan trap 7 applies: the
      fabricated root makes even the red run fail with `OSError`, never by
      creating a real store — must fail.
- [ ] T012 [US2] Write the three negative halves FIRST, same file, each with a
      docstring saying it guards against over-reach and passes today: with the
      acknowledgment variable set, `connect()` on a writable path outside the
      tmp tree but **inside the test's own checkout** (a scratch directory
      under the repo root, removed in a `finally` — never a shared system path,
      never any real `.factory`) proceeds (spec US2-S2); a path under tmp connects exactly as today (spec US2-S3); and
      with `PYTEST_CURRENT_TEST` removed via monkeypatch — production's shape —
      `connect()` behaves byte-identically on a tmp path, which is the proof
      FR-010 demands that the worker, the notify service and the CLI never meet
      this guard (spec US2-S4) — must fail only if the implementation
      over-reaches.

### Implementation for User Story 2

- [ ] T013 [US2] Add the guard clause to `connect()` in
      `factory/verify/store.py`, before the `mkdir`, per plan § US2: sentinel
      present + acknowledgment absent + resolved path not under
      `tempfile.gettempdir()` → raise, naming path and finding key. Name the
      acknowledgment constant in the module and mind the credential-name sweeps
      in `tests/test_verification_sweep.py` that cover `store.py` (they enforce
      constitution V — the new constant must not spell either credential's env
      name). No new dependency, no schema change,
      no change to any caller. Until T011 passes with T012 still green.
- [ ] T014 [US2] Wire the sanctioned door: when the operator supplies
      `LIVE_NOTIFY_DB_PATH`, `tests/test_live_notify.py` sets the
      acknowledgment variable within the same scope that sets the store path
      (grep `VERIFICATION_DB_PATH_ENV` in that file), so the live smoke against
      a shared store keeps working by explicit operator action, never by
      accident (spec US2-S2).
- [ ] T015 [US2] Final sweep + docs: full suite green; confirm no new
      dependency, activity or store; and add the `docs/decisions.md` entry —
      claimed at landing, immutable once numbered — recording the rule this
      spec changes: test-time isolation from the factory's live state is
      **enforced** (session fixture + store guard), no longer a per-file
      convention, with the operator's acknowledgment variable as the one
      deliberate exception.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything; T002's baseline count is what
  makes SC-001 measurable at landing.
- Phase 2 (US1) has no dependency and is the MVP: after it, no pytest run —
  bare shell or fully exported operator env — can write the live store or page
  the phone.
- Phase 3 (US2) chains on US1 **merged**, and the edge is load-bearing both
  ways (plan trap 5): without US1's fixture in the base, US2's guard turns the
  still-leaking harnesses red, and the two stories write the same test file.

## Implementation Strategy

US1 alone closes the finding as filed — it is the finding's own ranked fix (1),
widened to the three variables the tree says actually locate state. It is one
conftest fixture, one live-smoke consumer change, and three tests; no
production code moves.

US2 is smaller than it reads: one guard clause behind a sentinel production
never sets, in the one function every evidence-store writer already routes
through. Its risk is entirely in over-reach — refusing what should connect —
which is why T012's three negative halves are written before the guard exists.
