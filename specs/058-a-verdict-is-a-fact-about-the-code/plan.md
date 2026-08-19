# Implementation Plan: a verdict is a fact about the code

**Input**: [spec.md](spec.md) in this directory. Every anchor below was read
against the tree on 2026-08-18.

## Read the evidence before the plan

`evidence/055-us1-attempt1-gate.txt` is the captured gate output of the run this
spec exists for — 141 lines, the real `pytest` tail, not a summary. The failing
assertion, the passing assertion above it, and the suite counts are all in there.
**Read it first.** The diagnosis below was wrong once already, in the direction
that reading the source and not the failure always produces.

## Reuse inventory (verified against the tree 2026-08-18 — every anchor read)

| What | Where | Used by |
| --- | --- | --- |
| The test that fires | `tests/test_us4_boundary.py:202` (`test_hanging_agent_is_killed_at_deadline_with_no_survivors`) | US1 |
| The assertion that failed | `:236-238`, `SIGTERM not delivered; signals=[]` | US1 — the exact line, from the evidence file |
| The assertion that **passed** | `:229`, `result.termination == "timeout"` | US1 — the deadline machinery is not the defect |
| The tightened grace | `:212`, `ClaudeCodeAdapter(..., grace_s=1.0)` against production's `DEFAULT_GRACE_S = 10.0` (`factory/workgraph/adapter.py:99`) | US1 — one of the two candidate mechanisms |
| The attempt deadline | `:225`, `timeout_s=3` | US1 — the clock the stub's boot races |
| The stub's handler installation | `tests/stub_agent.py:414` (`signal.signal(signal.SIGTERM, on_term)`), the handler itself at `:409` | US1 — the other candidate, and the likelier one |
| What runs **before** it | `:407`, `recorder.write(STDIN_FILE, _read_stdin())` — stdin is drained first | US1 — the window in which SIGTERM hits the default disposition |
| The readiness file the stub documents | `:405-406` comment: *"a test polling for 'the stub is up' waits on the file that proves the prompt arrived"* | US1, US2 — the fix the source already names |
| The stub's control-knob mechanism | `ignore_sigterm` consumed at `stub_agent.py:411` | US1 — FR-002's delay knob is a sibling of this |
| Signal recording, flushed per line | `_Recorder.signal` at `:313`, `append` at `:308-311` | US1 — the write is flushed, so a missing entry means the handler never ran |
| The bwrap skip guard | `tests/test_us4_boundary.py:209` | US1, US2 — a green run on a host without bwrap proves nothing |
| The sibling boundary suite | `tests/test_us3_boundary.py` | US2 — same shape, same population |
| The D-021 sweep precedent | `tests/test_final_sweep.py` | US3 — the guard's vocabulary and structure, extended not forked |
| Why gates are bounded and agents are not | `factory/verify/gates.py:74-87` (`DEFAULT_GATE_CONCURRENCY = 1`) | context — the asymmetry this spec works around |

## The two candidate mechanisms, and how to tell them apart

The evidence establishes *that* the handler never ran. It does not establish
*why*, and there are two ways it happens. **Confirm which before fixing.**

1. **Handler installation loses to the deadline.** SIGTERM arrives before
   `stub_agent.py:414` executes, so it lands on the default disposition — the
   process dies at once and records nothing. The stub must first drain stdin
   (`:407`), which under load is not instant.
2. **The grace window is too short to be observed.** `grace_s=1.0` leaves under a
   second for the handler to be scheduled, run, and flush before SIGKILL takes
   the namespace down.

Mechanism 1 predicts `signals=[]` exactly, which is what was captured.
Mechanism 2 predicts the same symptom, so the capture does not discriminate. The
delay knob does: set it beyond the deadline and mechanism 1 reproduces at any
grace; raise `grace_s` alone and, if mechanism 2 were the whole story, the
failure would stop. Run both.

**Fixing the one you assumed is how this spec wastes an attempt.** If both are
real, both get fixed and the spec says so.

## Traps (named so the implementer does not rediscover them)

- **The reap window at `:241` is not the defect.** `await asyncio.sleep(0.2)`
  gates the *survivor* checks at `:245-251`, and those passed. It is a fixed
  sleep and US2 will convert it, but changing it fixes nothing that fired, and
  a diff that changes only it has missed the story. This exact misreading was
  made and corrected before drafting.
- **A test that cannot fail is worse than a flaky one.** Every reflex that makes
  this green — widening the wait until anything settles, dropping the signal
  assertion, marking the test — ships the boundary defect the test exists to
  catch. FR-003 forbids all of it, and US1-S3 requires the fixed test to still
  go red on a real leak. Prove that by mutation, not by argument: break the
  namespace teardown on a scratch branch and watch it fail.
- **Do not "fix" this by raising `--max-concurrent-nodes` sensitivity elsewhere.**
  The fix is in the test's synchronisation. Bounding agent tool calls under the
  gate semaphore is explicitly out of scope and would be a change to how every
  attempt on this factory runs.
- **The knob is the stub's, not the factory's** (FR-008). `tests/stub_agent.py`
  is a test double. Nothing under `factory/` may import it, detect it, or branch
  on it — 032's trap, unchanged, and the sweep in US3 is a good place to assert
  it.
- **Prove it on a host with bwrap.** `:209` skips the whole test when
  `bwrap` is missing, so "the suite is green" is compatible with "the test never
  ran". Quote `passed` **and** `skipped`; baseline is 3567 / 47 under the gate,
  and a new skip is a hidden test (this is 026's lesson and it is in the
  evidence file's own tail).
- **Purge `__pycache__` between mutants**, or run under
  `PYTHONDONTWRITEBYTECODE=1`. CPython validates a cached `.pyc` on
  `(mtime-in-whole-seconds, size)` only, so two same-size mutants written inside
  one wall-clock second make the second run execute the first's bytecode. It
  fails toward green and reproduces stably.
- **Do not tune to this host.** 20 cores today, and a bound calibrated against
  that is a bound that breaks on the next machine. Express every wait as a
  deadline on an observable condition.
- **US3's guard must distinguish waiting from pausing.** There are 37 fixed-sleep
  call sites across 15 test files and most are legitimate — yielding the event
  loop, not waiting for a process. A guard that bans the construct outright will
  be deleted by the next person who needs one. Ban the *pattern*: a fixed sleep
  standing between launching something and asserting about its state.

## Evidence discipline

Criteria are judged from the diff alone (constitution VIII / D-037): no base
tree, no terminal, no commit message. Two consequences here.

The reproduction is a **passing test**, not pasted output — which is what makes
this spec buildable where 032 was not (spec § Why this is buildable). Do not
leave a failing test behind to represent the defect; the gate runs the suite over
your diff.

But SC-002 asks that the *pre-fix* code fails under the knob, and a diff cannot
show a tree that no longer exists. Capture that run and commit it beside the
existing evidence — `evidence/pre-fix-under-knob.txt`, with the command, the
knob value, and the verbatim failure. The judge can then check the claim.

## Structure

US1: `tests/test_us4_boundary.py` (the synchronisation) and `tests/stub_agent.py`
(the delay knob), plus the committed pre-fix capture. US2: the readiness helper
extracted to the tests' shared support module, every racing launch in
`test_us4_boundary.py` and `test_us3_boundary.py` converted, and the call-site
count asserted. US3: the guard, in `tests/test_final_sweep.py`'s existing
vocabulary.

## Sizing

Small. US1 is two test files plus a capture; US2 is a helper and its call sites;
US3 is one guard. Nothing approaches the judge ceiling — import
`DIFF_INPUT_LIMIT` from `factory/verify/diffbounds.py:42` rather than quoting a
number, since it has moved once already. If a story does not fit whole, say
where you would split it rather than trimming checks.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A delay knob in the stub rather than induced load | Load is not reproducible and cannot be asserted on. The knob turns a statistical failure into a deterministic one, which is the difference between a regression test and a coin flip. |
| A shared helper (US2) rather than fixing one test | One observed failure, one shape, many call sites. A fix at one site has a shelf life measured in cap-2 runs. |
| A mechanical guard (US3) rather than a note | The pattern is ordinary and reads as harmless. Every previous "remember not to do this" in this repo became a finding. |
| Confirming the mechanism before fixing | Two mechanisms produce the identical symptom and the source was already misread once. An attempt spent on the wrong one is the exact cost this spec exists to stop. |
