# Plan: The test suite owns its stores

All line references below were **re-verified against the tree at commit
`3dbec67` on 2026-08-13**, replacing the 2026-08-11 `9594787` numbers this plan
originally carried. They are cited so you can find the code, not so you can
trust the numbers — beside each anchor is the construct to grep for, because
numbers rot before dispatch (see trap 6, and note it has now been proved twice).

**Read trap 2a before anything else.** The defect's *shape* changed after this
plan was written: 031 landed and closed the escalation-row half of the leak,
so what still fires today is a different write on the same broken boundary.
A plan that sends you hunting the wrong row wastes the attempt.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The evidence store's env-or-relative-default resolution | `factory/activities/verify_activities.py:121`/`:123` (`DEFAULT_VERIFICATION_DB_PATH`, `VERIFICATION_DB_PATH_ENV`), `_store_path` at `:540-543` | US1 proof asserts on it; US2 context |
| Its twin in the notify activities | `factory/activities/notify_activities.py:643-650` — grep `def _store_path` | US1 proof |
| The direct Telegram send from env | `factory/activities/notify_activities.py:420` (`_send`; env names at `:78`/`:83` — grep `TELEGRAM_BOT_TOKEN_ENV =`) | US1 — why the creds must leave the env |
| Factory-root resolution | `factory/activities/agent_activities.py:136`/`:163` and `factory/activities/merge_activities.py:77`/`:310`/`:374`/`:485` — grep `FACTORY_ROOT_ENV` | US1 proof |
| Ledger-path resolution | `factory/activities/usage_activities.py:96`/`:521` — grep `LEDGER_PATH_ENV` | US1 proof |
| Why `FACTORY_ROOT` must be absolute | `scripts/ergane-env.sh:80-84` (comment) and `factory/workgraph/worktree.py:73` | US1 — FR-002 |
| The leaking harness | `tests/test_roadmap_scheduler.py:411` (`run_roadmap`; real `send_escalation` imported at `:442`, registered at `:470`) and its `env` fixture at `:389` which redirects **nothing** | US1-S3; do not "fix" it per-file — trap 1 |
| The second leaking harness | `tests/test_ergane_roadmap.py:107-141` (`_worker` — grep `send_escalation`) | US1-S3 context |
| The correct per-file pattern (now superseded, not removed) | `tests/test_roadmap_failure_notifications.py:117-136` (`env` fixture setting `VERIFICATION_DB_PATH_ENV` to tmp) | US1 — the precedent the session fixture generalizes |
| The house pattern for patching the state-path trio | `tests/test_live_epic.py:414` — grep `MonkeyPatch.context` | US1 — same three variables, session-wide |
| Per-file autouse env fixtures that stay | `tests/test_agent_activities.py:206` and `tests/test_workgraph_sweep.py:294` (`worker_host`) | US1 — FR-004; they override per test |
| The default-root test that deletes the var | `tests/test_agent_activities.py:1006` — grep `delenv(FACTORY_ROOT_ENV)` | US1 edge case — must keep passing |
| The live smoke's opt-in guard | `tests/test_live_notify.py:180-187` (`live_config` — grep `pytest.skip`) and its store redirect at `:212` | US1 — FR-005 consumer of the stash |
| Existing conftest fixtures (append, don't reshape) | `tests/conftest.py:481-527` | US1 |
| The choke point | `factory/verify/store.py:167-180` (`connect`; the `mkdir` inside it is what FR-009 is about) | US2 |
| Why gate runs are already safe | `factory/verify/gates.py:85` (`SCRUBBED_ENV_ALLOWLIST`), `scrubbed_env` at `:271-281` | context — nobody should "harden" gates here |
| The live rows to clean | `.factory/verification.db`: 9 `escalations` rows (frozen since 2026-08-11, pre-031) and 1 `roadmap_failures` row (**rewritten as recently as 2026-08-13 19:42:59Z** — see trap 2a), all `roadmap-specs` | Phase 1 (operator) |

## Traps

### Trap 1 — the plausible wrong fix is per-file redirection

The leak's shape invites copying `test_roadmap_failure_notifications.py`'s `env`
fixture into `test_roadmap_scheduler.py` and calling it done. That patches the
one file you know about and leaves the class open — `test_ergane_roadmap.py` has
its own harness, `test_roadmap_operator_surface.py` and `test_roadmap_durability.py`
import the scheduler's, and the next roadmap test file will remember none of
this. The finding is explicit that only the suite-wide fixture closes it, and
the store's own history — three separate leak dates — is the proof that per-file
convention decays. Write the session fixture in `tests/conftest.py`; leave the
leaking files' fixtures alone (they become harmlessly redundant).

### Trap 2 — `FACTORY_ROOT` is not the store's address

The finding says "points FACTORY_ROOT at tmp_path". Read the tree before
obeying it literally: the evidence store is located by
`FACTORY_VERIFICATION_DB_PATH`-or-cwd-relative-default
(`verify_activities.py:121-123`), and `FACTORY_ROOT` never enters that
resolution. A fixture that owns only `FACTORY_ROOT` redirects worktrees and
transcripts while every escalation still lands in the live store — the six
`delivered=0` rows dated after the finding are exactly this hole being walked
through with no env exported at all. Own all three: `FACTORY_ROOT`,
`FACTORY_VERIFICATION_DB_PATH`, `FACTORY_LEDGER_PATH`. Overwrite, never
`setdefault`.

### Trap 2a — the leaking row is `roadmap_failures` now, not `escalations`

This spec was written on 2026-08-11 describing escalation rows as the ongoing
leak. **031 landed after that and changed which row leaks.**
`record_roadmap_failure` (`notify_activities.py:536`) now says so in its own
docstring: *"No escalation row is written here: roadmap failures are reported as
notices, not choices."* The store confirms it — the nine `roadmap-specs`
escalation rows are frozen at 2026-08-11T02:43:35Z and have not grown since.

What still fires is the `roadmap_failures` write, and because it is an upsert
keyed by `roadmap_id` it leaves **one row that is silently rewritten** rather
than a growing pile. Counting rows therefore under-reports the leak to zero.
Check `updated_at`, not `count(*)`.

**Live exhibit, generated by the operator on 2026-08-13 at 19:42:59Z**, during a
full-suite run that had `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` unset and
`FACTORY_ROOT` pointed at a fresh `mktemp -d`:

```
roadmap_failures: ('roadmap-specs', 0,
  'max_concurrent_nodes must be a positive integer, got -1',
  '2026-08-13T19:42:59Z')
```

That is fixture text from `tests/test_roadmap_scheduler.py`, in the live store,
written by a run the operator believed was isolated. It is trap 2 proved
empirically: **redirecting `FACTORY_ROOT` does not redirect the store.** The
only env var that would have stopped it is `FACTORY_VERIFICATION_DB_PATH`, and
no operator recipe in this repository sets it — which is exactly why the
boundary has to belong to `tests/conftest.py` and not to whoever remembers.

Your US1 proof should assert against this shape: a test that redirects only
`FACTORY_ROOT` must still be caught.

### Trap 3 — stubbing the sender is not the boundary; neither is unplugging the service

Two tempting non-fixes. First: hunting down every harness that registers the
real `send_escalation` and swapping in recorders — that hardens the files you
found, until someone registers the real activity again (it is the natural thing
to do; the recovery-path tests *need* the real failure-count logic). Second:
anything aimed at `factory/notify/service.py` — it is not the courier (the test
process delivers directly via `_send`), it is live on this host right now, and
FR-007 forbids touching it. The boundary is the store's and the credentials'
*location*: own the env, and every harness — present and future — is contained
without being edited.

### Trap 4 — deleting the Telegram creds session-wide silently kills the live smoke

`tests/test_live_notify.py`'s opt-in is presence-of-env (`live_config`,
`:181-187`): creds absent → skip. A session fixture that deletes them
unconditionally turns the live-Telegram smoke into a permanent skip — and a
skip is silent, so nobody notices the live tier died (a known hazard of this
suite's live tier — no doctor-ledger finding is filed for it as of `9594787`,
so do not cite one). The fix is
stash-and-consume: the session fixture captures the shell's values into a
session fixture *before* deleting the env vars, and `live_config` reads the
stash, skipping when it is empty and re-planting the values via
`monkeypatch`/`MonkeyPatch.context` within its own module scope when it is not
(the activity under test reads `os.environ`, so re-planting is required —
`:212` already shows the pattern for the db path). The skip message and the
skip condition must remain observably equivalent to today's.

### Trap 5 — US2's guard, dispatched before US1's fixture is merged, turns the suite red

The guard refuses non-tmp store paths during tests. Today, the leaking
harnesses connect to a *non-tmp* path on every run — that is the whole defect.
Until US1's fixture is live in the base your worktree is created from, the
guard makes those tests fail, and the "fix" that suggests itself in the moment
(weaken the guard, or skip the failing tests) destroys both stories. This is
why the work graph chains US2 on US1 **merged** — if you are implementing US2
and `tests/conftest.py` has no session isolation fixture, stop: your base is
wrong. Also honor the guard's carve-out: `test_live_notify.py` may point at a
real store when the operator sets `LIVE_NOTIFY_DB_PATH` — that path goes
through the explicit acknowledgment variable (US2-S2), not through a hole in
the rule.

### Trap 6 — these line numbers rot, and this file's have a shorter half-life than most

Proved twice now. The 2026-08-11 numbers in the first draft of this plan were
all wrong by 2026-08-13: `notify_activities._store_path` had moved ~58 lines,
`gates.scrubbed_env` ~55, and `test_agent_activities`'s delenv case ~150, as
025, 026, 027, 028, 029, 031, 036, 037 and 038 all landed in between. The
inventory above was rewritten at `3dbec67`; assume it has started rotting again.

Note also that 027 and 025 have now *landed* their edits to shared test
infrastructure (`tests/test_interpreter.py`, `tests/test_workgraph_sweep.py`),
so that particular collision is behind you rather than ahead. Grep for
the construct named beside each anchor — `def _store_path`, `FACTORY_ROOT_ENV`,
`SCRUBBED_ENV_ALLOWLIST`, `def connect`, `def run_roadmap` — and if what you
find disagrees with a citation here, the code wins and you say so in your
commit message. If `tests/conftest.py` already contains a session-scoped env
fixture when you arrive, 027 or a sibling landed first: extend it to satisfy
the FRs rather than adding a second one — two autouse session fixtures fighting
over the same variables is this bug's next incarnation.

### Trap 7 — the proof must be safe even when it fails

Both stories' proof tests involve paths outside tmp. Fabricate them under a
root that cannot exist (`/nonexistent-030-proof/...`), never under any real
`.factory`, and prefer parents that do not exist — then a red run (guard or
fixture not yet written) fails with `OSError`/assertion, not by writing a real
store or paging a phone. The subprocess proof's poisoned credential values must
be obvious fakes (`"poisoned-token"`), so even a total isolation failure sends
nothing deliverable. Never point any test, red or green, at
`/home/admin/code/ergane/.factory`.

## Approach

### US1 — one session fixture, one stash, one subprocess proof

1. In `tests/conftest.py`, add a session-scoped autouse fixture (order it first
   among session fixtures). Use `pytest.MonkeyPatch()` directly with an `undo()`
   finalizer — the function-scoped `monkeypatch` fixture cannot be session
   scoped — and `tmp_path_factory.getbasetemp()` for the base. Set
   `FACTORY_ROOT` to `<base>/session-factory-root` (absolute by construction,
   FR-002), `FACTORY_VERIFICATION_DB_PATH` to `<base>/session-verification.db`,
   `FACTORY_LEDGER_PATH` to `<base>/session-ledger.db`. `setenv`, not
   `setdefault` — the shell must lose.
2. Same fixture: capture `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` into a small
   frozen dataclass, then `delenv(raising=False)` both. Expose the dataclass
   through a separate session fixture (the stash) that tests must *request* —
   consuming real credentials becomes a visible act in a signature.
3. Update `live_config` in `tests/test_live_notify.py` to take the stash, skip
   when either value is missing (same message), and re-plant both into env for
   its module scope when present. No other live file reads these credentials.
4. New file `tests/test_store_isolation.py`, two tests:
   - the in-suite invariant: all three owned variables point under
     `tmp_path_factory.getbasetemp()`, both credentials are absent from
     `os.environ`, and the four production resolvers
     (`verify_activities._store_path()`, `notify_activities._store_path()`,
     agent root, ledger path) resolve under the base;
   - the subprocess proof (FR-006): run
     `sys.executable -m pytest tests/test_store_isolation.py -k invariant -q`
     with an env of `os.environ` plus the five poisoned values, from the repo
     root; assert exit code 0 and that no poisoned path exists afterward. One
     subprocess, one test, a few seconds — do not parametrize it into more
     (the suite already has a slowness finding).

### US2 — one guard clause at the choke point

In `factory/verify/store.py::connect()`, before the `mkdir` at `:174`: if
`PYTEST_CURRENT_TEST` is in the environment, the acknowledgment variable
(name it in the module next to the DDL constants; something like
`FACTORY_EVIDENCE_STORE_ALLOW_REAL` — and mind
`tests/test_verification_sweep.py`'s credential-name sweeps over this module,
which enforce constitution V: `store.py` may not spell either credential's env
name) is not set, and the resolved path is not under the tmp tree, raise
`RuntimeError` naming the path and the finding key. "Under the tmp tree" =
`Path(path).resolve()` is relative to `Path(tempfile.gettempdir()).resolve()`
— pytest's *default* basetemp lives under `gettempdir()` (which honors
`TMPDIR`, the supported relocation knob — it is even on the gates' allowlist).
An explicit `--basetemp` outside the system tmp tree is invisible to
production code and would trip the guard; the spec's edge case documents that
as supported behavior routed through the acknowledgment variable, not a bug.
State both halves in the guard's comment.
Tests live in `tests/test_store_isolation.py` beside US1's: the refusal case
(fabricated path, parent must not exist afterward — trap 7), the acknowledgment
case, the tmp-allowed case, and the sentinel-absent case (delete
`PYTEST_CURRENT_TEST` via monkeypatch, call `connect` on a tmp path, assert
normal behavior — that is the production-unchanged proof, FR-010/US2-S4).
Then update `live_config` (or the smoke's store fixture) to set the
acknowledgment variable when the operator supplied `LIVE_NOTIFY_DB_PATH`
(US2-S2).

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| Owning three variables instead of the one the finding named | `FACTORY_ROOT` does not locate the store (trap 2); the `delivered=0` recurrences are the measurement |
| A stash instead of just deleting the creds | Deletion alone turns the live smoke into a permanent, silent skip (trap 4) |
| A subprocess proof instead of only in-process assertions | "No matter what the shell exported" is a claim about env that exists *before* session start; only a child process can carry a poisoned pre-session env |
| A production guard for a test-time problem (US2) | The fixture is convention, and this convention has decayed three times on this path; the guard is enforcement at the one function every store writer routes through, behind a sentinel production never sets — justification written in the spec's Assumptions |
| An acknowledgment variable on the guard | Without it, US2 closes the operator's sanctioned live-smoke door (`LIVE_NOTIFY_DB_PATH` at a shared store) and the "fix" would be deleting the guard |

## Verification

The suite green twice: once in a bare shell, once with all five variables
exported as poison — the gate only ever gives you the first, so run the second
yourself before handing over. The two tests that did not exist before are the
point: the subprocess proof (US1) and the refusal-leaves-no-trace case (US2).
If either passes before its implementation exists, the test is wrong —
constitution II. The operator-side proof (SC-001's before/after count against
the live store) belongs to the operator at landing, not to any dispatched node:
no test may touch that store, including to prove it was not touched.
