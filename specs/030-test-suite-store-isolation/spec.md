---
state: landed
# Attested landed 2026-08-13 22:00Z by the operator. US1 c572fdb32fde (PR #61),
# US2 805f0eaeafff (PR #62) — both observed on ergane-buildout, both attempt 1.
# Dispatched by hand; the roadmap is still wedged.
# VERIFIED BY CONTROL, not by the green suite. Same command on two trees, with
# operator-shaped Telegram credentials exported and NO manual env redirect —
# the exact condition that poisoned the live store at 19:42:59Z:
#   pre-fix (f0fc00d): wrote .factory/verification.db, 81920 bytes, containing
#     ('roadmap-specs', 0, 'max_concurrent_nodes ... got -1', '...21:27:02Z')
#   post-fix (PR #61): no store file created at all
# US2's guard probed separately with the fixture deliberately defeated: it
# still raised RuntimeError naming the finding key, created neither parent
# directory (so it fires before connect()'s mkdir), and the sanctioned door
# FACTORY_EVIDENCE_STORE_ALLOW_REAL still opened. Credentials in every probe
# were obvious fakes, per the plan's trap 7.
# CONSEQUENCE FOR OPERATORS: the five-variable clean-env incantation is retired.
# Confirmed on trunk after the merge — a plain `uv run pytest` from the
# operator's checkout, no scrubbing, left the live store untouched.
# Flipped ready 2026-08-11 PM CT on the operator's word ("flip all 6"); the
# paused roadmap dispatches serially (max_concurrent_epics=1) in dir order
# once unpaused.
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `hardening/test-suite-writes-to-the-live-evidence-store` (critical), then
# refined against the tree at 9594787 on 2026-08-11.
# Pre-dispatch refinement pass 2026-08-13 at 3dbec67 (after 025-029, 031,
# 036-038 landed): every anchor in the plan re-verified, and trap 2a added
# because the defect CHANGED SHAPE. 031 stopped writing an escalation row for a
# roadmap failure, so the nine escalation rows are frozen at 2026-08-11 and the
# live leak is now the `roadmap_failures` upsert — one row, silently rewritten,
# which `count(*)` reports as no growth at all. Fresh exhibit: the operator's
# own full-suite run at 2026-08-13T19:42:59Z wrote fixture text into the live
# store while TELEGRAM_* were unset and FACTORY_ROOT pointed at a mktemp dir.
# That is trap 2 proved live: FACTORY_ROOT is not the store's address, and no
# operator recipe in this repo sets FACTORY_VERIFICATION_DB_PATH.
# Recurrence verified live during refinement: the finding counted three fixture
# rows on 2026-08-09; a read-only query on 2026-08-11 found NINE — the leak has
# fired twice more since it was filed, without the Telegram credentials even
# being exported. The cleanup in tasks.md Phase 1 is sized to what is actually
# there, not to what the finding remembered.
---

# Feature Specification: The test suite owns its stores

## The defect in one sentence

The evidence store's location is an environment variable with a cwd-relative
default, no test-suite-wide fixture owns either, and two test harnesses register
the real `send_escalation` activity — so a `pytest` run from the operator's
checkout writes fixture escalations into the live `.factory/verification.db`,
and, when the shell has also exported the Telegram credentials, pages the
operator's real phone with live RETRY/KILL buttons for a workflow that does not
exist.

## The mechanism, verified against the tree

Four facts compose into the leak, and every one was re-verified at `9594787`:

1. **The store's address is ambient.** `_store_path()` in
   `factory/activities/verify_activities.py` (and its twin in
   `notify_activities.py`) resolves `FACTORY_VERIFICATION_DB_PATH` or falls back
   to the *relative* default `.factory/verification.db`. Run pytest with cwd =
   the operator's checkout and the fallback IS the live store. No export is
   required to poison it — the six rows added since the finding was filed all
   landed with `delivered=0`, meaning no Telegram credentials were present, and
   they landed anyway.
2. **Two test harnesses register the real sender.** `run_roadmap` in
   `tests/test_roadmap_scheduler.py` (reused by `test_roadmap_operator_surface.py`
   and `test_roadmap_durability.py`) and `_worker` in
   `tests/test_ergane_roadmap.py` list the real `send_escalation`,
   `record_roadmap_failure` and `reset_roadmap_failures` activities. The
   bad-node-bound tests (`got 0`, `got -1`) drive the roadmap's failure-report
   path, and a later passing roadmap test drives the recovery message — three
   rows per full-suite run, which is exactly the cadence the live store shows:
   3 rows on 08-09, 3 on 08-10, 3 on 08-11, all `workflow_id = 'roadmap-specs'`.
3. **Delivery is direct, from the test process.** `_send` in
   `notify_activities.py` reads `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
   straight from `os.environ` and calls the Bot API itself. With the operator
   env exported (`scripts/ergane-env.sh` exports both), the *test process*
   pages the phone — the notify service is not the courier.
4. **The long-running bridge makes the buttons live.** `factory/notify/service.py`
   polls Telegram continuously against the live store; a press on a fixture
   message signals a workflow named `roadmap-specs`, which nothing is running.
   The finding's ref `service.py:175` is that signal call.

The test files already believe they are isolated — `test_roadmap_failure_notifications.py`
stubs its own sender and redirects its own store — but stubbing the sender is not
the boundary that matters. **Owning the store is.** That boundary must belong to
the suite, not to whichever file remembered to draw it, because the per-file
convention has now decayed three separate times on this one path.

One deliberate scoping fact: gate runs are already safe. `run_gates` scrubs the
subprocess env down to `SCRUBBED_ENV_ALLOWLIST` (no `FACTORY_*`, no `TELEGRAM_*`)
and runs with cwd = the node's worktree, so an attempt's own suite run cannot
reach the live store or the phone. The exposure is operator-side shells — which
is why the fix is a test-suite fixture, not a gate change.

## User Scenarios & Testing

### User Story 1 - No test can reach the real store, no matter what the shell exported (Priority: P1)

A session-scoped autouse fixture in `tests/conftest.py` unconditionally points
every state-locating environment variable — `FACTORY_ROOT`,
`FACTORY_VERIFICATION_DB_PATH`, `FACTORY_LEDGER_PATH` — at per-session paths
under pytest's tmp base before any test runs, and removes the two Telegram
delivery credentials from the process environment, stashing their values so the
live-tier smoke can still consume them deliberately. Overwrite, never
`setdefault`: the whole point is that the shell's exports lose.

The finding named `FACTORY_ROOT`; the tree says `FACTORY_ROOT` alone is not
enough. The evidence store is located by `FACTORY_VERIFICATION_DB_PATH`-or-
relative-default, not by `FACTORY_ROOT`, and the six `delivered=0` rows prove
the relative default is the door that keeps getting walked through. The fixture
owns all three variables or it closes nothing.

**Goal**: a full-suite run from the operator's checkout, with the operator env
exported, adds zero rows to the live evidence store and sends zero Telegram
messages — and the suite stays green in a bare shell with nothing exported.

**Independent Test**: run a designated proof test via a subprocess pytest whose
environment carries poisoned (fabricated, never-real) values for all three state
variables plus fake Telegram credentials, and assert the resolved store paths
all land under the run's tmp base, the poisoned paths were never created, and
the credentials are absent from the inner test's environment.

**Acceptance Scenarios**:

1. **Given** a pytest run whose parent shell exported fabricated non-tmp values
   for `FACTORY_ROOT`, `FACTORY_VERIFICATION_DB_PATH` and `FACTORY_LEDGER_PATH`
   (poison paths that are not any real `.factory`), **When** a test inside that
   run resolves the store locations the way the activities do
   (`verify_activities._store_path()`, `notify_activities._store_path()`, the
   agent activities' factory root, the usage activities' ledger path), **Then**
   every resolution lands under the session's tmp base and nothing was created
   at any poisoned path.
2. **Given** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` exported in the parent
   shell, **When** any test that exercises the real `send_escalation` activity
   runs, **Then** the activity finds no credential in its environment, records
   the row with `delivered=False`, and no request leaves the process — while a
   test that plants fake credentials with `monkeypatch.setenv` still sees its
   fakes.
3. **Given** the previously-leaking path — a roadmap harness test that drives
   the failure-report or recovery path through the real `send_escalation` —
   **When** it runs under the fixture, **Then** its escalation and
   `roadmap_failures` rows are present in the store under the session tmp base
   (read that store and find them) and absent from any path outside it.
4. **Given** a bare shell with none of the five variables exported, **When** the
   full suite runs, **Then** it is green with behavior unchanged: tests that
   `delenv` a variable and assert on documented defaults, and tests that assert
   the undeliverable path when credentials are absent, all still pass.
5. **Given** the operator's real Telegram credentials in the shell, **When** the
   live smoke `tests/test_live_notify.py` is selected, **Then** it still runs
   (consuming the stashed credentials); **Given** a shell without them, **Then**
   it still skips with the same message as today.

### User Story 2 - The store refuses to be built outside tmp while a test is running (Priority: P2)

Defense in depth at the single choke point: `factory/verify/store.py`'s
`connect()` refuses to open a store at a path outside the process's tmp tree
when pytest's `PYTEST_CURRENT_TEST` sentinel is present — unless the operator
has set the explicit acknowledgment variable that the live smoke's
sanctioned-real-store mode requires. The refusal happens before the `mkdir` and
before `sqlite3.connect`, so a refused call leaves no trace on disk.

US1 is convention: a fixture a future edit can weaken and a `delenv` can step
around, in a suite where this exact convention has decayed three times. US2 is
enforcement, and it is deliberately tiny — one guard clause in one function that
every evidence-store writer already routes through, taken behind a sentinel that
is never set in production. The justification against the constitution's
simplicity bar is written in Assumptions.

**Goal**: while a test is running, constructing the evidence store anywhere
outside the tmp tree is an error naming the path and this finding — except
through the one explicit, operator-set door the live smoke uses.

**Independent Test**: with `PYTEST_CURRENT_TEST` naturally present, call
`connect()` on a fabricated absolute path outside tmp whose parent does not
exist, assert it raises, and assert the path and its parent still do not exist.
The poison path must be fabricated (e.g. under a nonexistent root) so that even
a red run of this test — the guard not yet written — fails with an ordinary
`OSError` rather than by creating a real store.

**Acceptance Scenarios**:

1. **Given** a running test and a fabricated absolute path outside the tmp tree,
   **When** `connect()` is called on it, **Then** it raises an error naming the
   offending path and the isolation rule, and neither the file nor any parent
   directory was created.
2. **Given** the same path with the explicit acknowledgment variable set, **When**
   `connect()` is called, **Then** it connects — the door
   `tests/test_live_notify.py` uses when the operator points `LIVE_NOTIFY_DB_PATH`
   at a shared store stays open, and stays deliberate.
3. **Given** a path under the tmp tree, **When** `connect()` is called during a
   test, **Then** it connects exactly as today — the guard never fires on the
   isolated suite US1 establishes.
4. **Given** `PYTEST_CURRENT_TEST` absent (production: the worker, the notify
   service, the CLI), **When** `connect()` is called on any path, **Then**
   behavior is byte-identical to today — no refusal, no new I/O, no new log
   line.

## Functional Requirements

- **FR-001**: A session-scoped autouse fixture in `tests/conftest.py` MUST set
  `FACTORY_ROOT`, `FACTORY_VERIFICATION_DB_PATH` and `FACTORY_LEDGER_PATH` to
  paths under pytest's session tmp base before any test runs, unconditionally
  overwriting whatever the shell exported.
- **FR-002**: The value the fixture sets for `FACTORY_ROOT` MUST be absolute —
  `worktree.py` hands it to `git -C <clone> worktree add`, which resolves a
  relative path against the clone while Python resolves it against cwd, the
  split documented in `scripts/ergane-env.sh`.
- **FR-003**: The same fixture MUST remove `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` from the process environment, capturing the removed values
  in a session-scoped stash fixture that tests may consume explicitly.
- **FR-004**: Per-test environment manipulation MUST keep working: a test's
  `monkeypatch.setenv`/`delenv` of any owned variable overrides the session
  fixture within that test and is undone after it, exactly as those tests behave
  today.
- **FR-005**: `tests/test_live_notify.py`'s opt-in guard MUST read the stash
  instead of `os.environ`, preserving its contract: skip without operator
  credentials, run with them, and re-plant them into the environment only within
  its own scope (the activity under test reads env).
- **FR-006**: A proof test MUST demonstrate US1 end to end via a subprocess
  pytest run carrying poisoned values for all five variables, asserting
  resolution under tmp, non-creation of the poisoned paths, and absence of the
  credentials — with every poisoned path fabricated so no outcome of the test,
  pass or fail, can touch a real `.factory`.
- **FR-007**: US1 MUST NOT modify production code, touch or restart the notify
  service, or alter `scripts/ergane-env.sh`. The worker's env contract is not
  this spec's to change.
- **FR-008**: `factory/verify/store.py::connect()` MUST refuse to open a path
  outside the process tmp tree while `PYTEST_CURRENT_TEST` is present, unless
  the explicit acknowledgment variable is set; the error MUST name the path and
  the finding key `hardening/test-suite-writes-to-the-live-evidence-store`.
- **FR-009**: The refusal MUST occur before any filesystem side effect —
  today's `connect()` calls `mkdir(parents=True)` before `sqlite3.connect`, and
  a refused call must leave neither.
- **FR-010**: With the sentinel absent, `connect()` MUST be byte-identical to
  today's behavior. No new dependency anywhere in this spec (constitution III).

## Success Criteria

- **SC-001**: A full-suite run from the operator's checkout with the operator
  env exported adds zero rows to `/home/admin/code/ergane/.factory/verification.db`
  — verified at landing by comparing `SELECT COUNT(*) FROM escalations` before
  and after such a run, after the Phase 1 cleanup has pinned the baseline.
- **SC-002**: The same run sends zero Telegram messages: the only credentials
  any unit test can see are fakes it planted itself.
- **SC-003**: The live smoke remains runnable by an operator who exported real
  credentials, and remains a skip for everyone else.
- **SC-004**: The full suite is green in a bare shell, green with the operator
  env exported, and no dependency was added.
- **SC-005**: With US2 landed, `connect()` on a non-tmp path during a test is an
  error that leaves no file behind, and production call sites are provably
  unchanged (sentinel-absent behavior covered by test).

## Edge Cases

- **The doctor's ledger has no env knob.** `factory/doctor/cli.py` resolves
  `--db` or the cwd-relative default `.factory/doctor.db`; its tests all pass
  `--db` explicitly. The fixture cannot own what env does not locate; adding an
  env knob for it is new production surface and out of scope here.
- **`tests/test_agent_activities.py` deletes `FACTORY_ROOT` and chdirs to tmp**
  to assert the documented default. The session fixture guarantees the variable
  is set (so `delenv` keeps working) and the chdir keeps the relative default
  under tmp. No change to that test.
- **Per-file `worker_host` autouse fixtures** (`test_agent_activities.py`,
  `test_workgraph_sweep.py`) already set `FACTORY_ROOT` and plant fake
  credentials per test. They continue to override the session fixture per
  FR-004; they are not removed by this spec.
- **`--basetemp` outside `tempfile.gettempdir()`**: US2's guard is production
  code that cannot see pytest's session base, so the plan pins its "tmp tree"
  rule to `tempfile.gettempdir()` — which honors `TMPDIR`, the supported
  relocation knob (nothing in this repo passes `--basetemp`, and `TMPDIR` is on
  the gates' allowlist). Pytest's default basetemp lives under `gettempdir()`,
  so US1's session paths satisfy the rule; a run that passes `--basetemp`
  outside the system tmp tree meets the guard and goes through the
  acknowledgment variable — documented behavior, not a bug.
- **The three rows per run are not always three.** The recovery row only
  appears when a passing roadmap test follows the failing ones; a partial run
  (`-k bad_node_bound`) writes two. The cleanup task verifies by
  `workflow_id = 'roadmap-specs'`, never by count alone.

## Assumptions

- **US2's complexity is justified in writing here**, per the constitution's
  governance clause. The evidence that convention alone does not hold: the leak
  recurred twice *after* the finding was filed and known (six new rows dated
  08-10 and 08-11), the suite already contains the correct per-file pattern
  (`test_roadmap_failure_notifications.py`) that the leaking files simply do not
  use, and the blast radius on recurrence is a human's phone carrying a live
  KILL button. Against that, the cost is one guard clause behind a sentinel
  that production never sets, in the one function every evidence-store writer
  already routes through — no new dependency, no new activity, no schema
  change, sentinel-absent behavior covered by its own test (US2-S4).
- pytest's session tmp base (`tmp_path_factory.getbasetemp()`) is the
  authoritative "tmp tree" for both stories; it respects `TMPDIR` and
  `--basetemp`.
- The stash's consumer set is exactly one file today (`test_live_notify.py`).
  Other live-tier modules patch their own state paths already
  (`test_live_epic.py`) and do not read Telegram credentials.
- The epic building this spec runs its gates under the scrubbed allowlist env
  with cwd = the node worktree, so the implementing attempts cannot themselves
  trip the leak they are fixing.

## Out of Scope

- **Editing `scripts/ergane-env.sh`** (the finding's ranked fix 3). Narrowing
  what the operator's shell exports narrows the paging blast radius but leaves
  the store poisoning intact — the `delivered=0` recurrences prove it — and the
  script is the worker's deployment contract, not the test suite's.
- **Deleting the delivered Telegram messages.** The two 08-09 pages cannot be
  unsent; the cleanup task removes the rows, not the chat history.
- **Extending the US2 guard to the usage ledger or the doctor store.** Same
  shape, separate stores, separate decision — this spec enforces the boundary
  at the store the finding names. If the class recurs on a sibling store, that
  recurrence is the promotion argument.
- **Touching or restarting `factory/notify/service.py`.** The service polls
  Telegram, not the store's schema; nothing here changes what it reads, and an
  epic is live on this host. FR-007 makes this binding on US1; US2 changes only
  `connect()`'s test-time behavior, which the service (sentinel absent) never
  sees.
- **CI wiring** (`-m` marker plumbing, gate command changes). Gates are already
  safe by the allowlist; the live tier's guard-not-marker mechanics are a known,
  separate concern — no doctor-ledger finding is filed for it as of `9594787`,
  and this spec does not create one.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-008, FR-009, FR-010]
```

US2 chains on US1 **merged**, and the edge is semantic, not just conflict
avoidance: US2's guard refuses non-tmp store paths during tests, and until
US1's fixture has redirected the whole suite under tmp, the guard would turn
the leaking harnesses' every run red. Dispatched against a base without US1,
US2 cannot pass its own gate. They also share a test file
(`tests/test_store_isolation.py`), which would make siblings collide in the
queue regardless.
