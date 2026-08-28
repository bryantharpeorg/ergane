# Tasks: the demo sandbox starts, or says why

**Input**: `spec.md` and `plan.md` in this directory, both drafted 2026-08-27
against ergane-buildout at 3e5c940.

Tests are written first and must fail before their implementation task runs.
`[P]` marks tasks that can proceed in parallel within their story because they
touch different files or independent test functions.

## Phase 1: User Story 1 — A refused sandbox names the restriction that refused it

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-002, FR-003) AppArmor-remedy test, in a new
  `tests/test_111_us1_sandbox_remedy.py`: call the remedy function with the
  measured stderr `bwrap: setting up uid map: Permission denied` and assert the
  returned text contains `kernel.apparmor_restrict_unprivileged_userns`, states
  that `apparmor=unconfined` on a container does not lift it because AppArmor
  attaches by executable path on exec, and names the committed profile path.
  Assert the substring `unprivileged_userns_clone` is **absent** — that is the
  Debian-era knob the old text named, and its absence is the fix.
- [ ] T002 [P] [US1] (spec US1-S2, FR-004) Masked-proc remedy test: call the
  same function with `bwrap: Can't mount proc on /newroot/proc: Operation not
  permitted` and assert the text names `systempaths=unconfined`, and that it
  does **not** contain `apparmor_restrict_unprivileged_userns`. A third
  assertion pins that the two remedies are not equal strings — the whole point
  is that a different failure reads differently.
- [ ] T003 [P] [US1] (spec US1-S3, FR-005) Unrecognised-stderr test: call the
  function with a string matching neither pattern and assert the result states
  the failure is not one of the known shapes and names both remedies as
  candidates without asserting either. A companion assertion drives the demo
  driver's refusal path with that outcome and confirms the probe's own stderr is
  still printed verbatim above it (`demo_driver.py:374-379` ordering).
- [ ] T004 [P] [US1] (spec US1-S4, FR-001) One-source test: assert the demo
  driver and the host probe resolve their remedy text from the **same** imported
  callable — by identity, not by string equality — so a future edit to one tier
  cannot silently fork the advice. A string-equality assertion satisfies this
  scenario's letter and not its purpose (plan T5).
- [ ] T005 [P] [US1] (spec US1-S4, FR-001) Host-probe finding test: with an
  injected `_run_bwrap_probe` (`factory/controlplane/verify.py:286-298`)
  returning a nonzero result whose stderr is the uid_map string, assert the
  rendered `host` finding carries the AppArmor remedy. Drive it through the
  existing injectable seam; start no processes (plan T2 forbids touching the
  probe argv, and the suite must never own a real sandbox).

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, FR-003, FR-004, FR-005) Add the remedy
  function under `factory/verify/` — a pure `stderr -> str` with two compiled
  patterns and a fallback — and point both call sites at it: the demo driver's
  refusal path (replacing the `SANDBOX_REMEDY` constant used at
  `factory/supervision/demo_driver.py:369-378`) and the host probe's bwrap
  finding (`factory/controlplane/verify.py:301-330`). Do not edit
  `sandbox_probe_argv` or `_bwrap_probe_argv` (plan T2).

### Verification for this story

- [ ] T007 [US1] (spec US1-S1, spec US1-S2, SC-001) Paste into the PR: the two
  refusal transcripts side by side — the same probe failing two ways, producing
  two different remedies — and the full-suite before-and-after counts.

## Phase 2: User Story 2 — The grant is a file this project ships

### Tests for this story (write FIRST, must fail)

- [ ] T008 [US2] (spec US2-S1, FR-006, FR-007) Profile-directive test, in a new
  `tests/test_111_us2_bwrap_profile.py`: read the committed profile under
  `container/`, parse its directives, and assert it attaches at
  `/usr/bin/bwrap` and grants `userns`. Parse; do not digest. A companion
  negative case feeds the parser a profile with `userns,` removed and asserts
  the test would fail — the check is only worth having if losing the grant
  breaks it (plan T6).
- [ ] T009 [P] [US2] (spec US2-S2, spec US2-S3, FR-008, FR-009) Comment-correction
  test: assert that neither `factory/workgraph/adapter.py` nor
  `factory/controlplane/verify.py` attributes the userns grant to an Ubuntu
  release, and that both name the committed profile's path. A third assertion
  pins that `BWRAP_BACKEND_BINARY` and `_BWRAP_PINNED_PATH` are both still
  `/usr/bin/bwrap` — the premise was wrong, the pin is right, and this story
  must not remove it (plan T3).
- [ ] T010 [P] [US2] (spec US2-S4, FR-010) Docs-drift test: extract the profile
  text from the one-time load procedure documented in `README.md` and in
  `docs/onramp.html`, and assert each equals the committed profile. Extract from
  the procedure's own commands; do not assert the page contains a hard-coded
  second copy, which is the same string written twice and drifts the same way
  (plan T7).

### Implementation for this story

- [ ] T011 [US2] (FR-006) Add the AppArmor profile under `container/`, beside
  `ergane-engine.profile` and `seccomp-ergane.json`, with the six lines measured
  working on 2026-08-27 and a header comment stating what it grants, that no
  package ships it, and that loading it is the operator's deliberate act.
- [ ] T012 [US2] (FR-008, FR-009) Correct the two comments. Each states: the pin
  is required because AppArmor attaches by executable path on exec; the grant
  comes from a profile no package ships; the profile this project ships is at
  the committed path. Neither attributes it to a distribution release. Neither
  changes its pinned value.
- [ ] T013 [US2] (FR-010) Bring the one-time load procedure in `README.md` and
  `docs/onramp.html` into agreement with the committed file, so T010 passes
  against the tree rather than against a transcription.

### Verification for this story

- [ ] T014 [US2] (spec US2-S1, spec US2-S2, SC-002) Paste into the PR: the
  profile-directive test output including the negative case, the before-and-after
  text of both corrected comments, and the full-suite before-and-after counts.

## What no task here can prove

Every task above runs against captured strings and committed files. **None of
them proves the thing the spec is for**, because proving it requires a host that
the floor host is not: one where `kernel.apparmor_restrict_unprivileged_userns=1`
and `/etc/apparmor.d/bwrap` does not exist. On this machine the profile has been
in place since 2026-07-16, which is precisely why the defect survived a released
demo, a passing suite, and a successful end-to-end run on 2026-08-27.

That proof is the operator verification in `plan.md`: a stock box, or this one
with the profile moved aside and reloaded, reading the refusal and doing only
what it says. `tasks.md` forbids attempting it here on purpose — a test that
modifies host confinement policy is a test that has acquired privilege, which
plan T1 refuses.
