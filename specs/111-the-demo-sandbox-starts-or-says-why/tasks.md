# Tasks: the demo sandbox starts, or says why

**Input**: `spec.md` and `plan.md` in this directory, drafted 2026-08-27 against
ergane-buildout at 3e5c940 and amended 2026-08-28 with US3 against `1045370`.

Tests are written first and must fail before their implementation task runs.
`[P]` marks tasks that can proceed in parallel within their story because they
touch different files or independent test functions.

**Phase order is US3 → US1 → US2**, which is not the story-key order. US3 is the
failure that has already happened on a real machine; US1 and US2 are the one that
will happen on the next stranger's. See the Work Graph in `plan.md`.

## Phase 1: User Story 3 — The demo refuses a credential it has already proven unusable

### Tests for this story (write FIRST, must fail)

- [ ] T101 [US3] (spec US3-S1, FR-013, FR-015) Fatal-finding test, in a new
  `tests/test_111_us3_credential_preflight.py`: drive `run_prepare_phase` with an
  injected preflight seam returning `Finding(check="llm", passed=False,
  detail="<the gateway's own error>")` and assert three things — the return is
  nonzero, the printed output contains that detail verbatim **and** the string
  `UPSTREAM_MODEL_API_KEY`, and `sentinel_path(state_home,
  PREPARED_SENTINEL).exists()` is False. The sentinel assertion is the one that
  matters: a stranger who fixes their key must get a demo, not a sulk.
- [ ] T102 [P] [US3] (spec US3-S2, FR-014) Non-fatal-finding test: drive the same
  phase with a failed `host` finding and a passing `llm` finding and assert
  preparation continues to the sandbox probe and returns 0. An unauthenticated
  `gh` is the ordinary state of a demo container and must stay non-fatal (plan
  T9); this test is what stops the next editor widening the set by accident.
- [ ] T103 [P] [US3] (spec US3-S3, FR-014) Fatal-set test: assert the named
  constant equals exactly `{"llm"}`. Assert on the constant, not on behaviour —
  the point is that changing which checks stop the demo is an edit with a test
  attached.
- [ ] T104 [P] [US3] (spec US3-S1, FR-016) No-lookup test: assert the remedy text
  contains `UPSTREAM_MODEL_API_KEY` **and** that
  `factory/supervision/demo_driver.py` never reads that name from the
  environment — the variable is set only on the gateway service
  (`container/compose.demo.yaml:125`; the engine's environment is `:38-103`), so
  a driver that looks for it refuses every healthy stack (plan T8).
- [ ] T105 [P] [US3] (FR-017) Raising-probe test: make the preflight seam's
  underlying probe raise, and assert the phase produces the refusal with the
  exception named — not a traceback caught by `main`'s handler at
  `demo_driver.py:738-740`, which prints `first boot failed:` and names no
  remedy.
- [ ] T106 [P] [US3] (spec US3-S4, FR-011) Compose-declaration test, in
  `tests/test_109_us2_demo_compose.py`: assert the gateway service declares
  `UPSTREAM_MODEL_API_KEY` in the `${NAME:?message}` required form and that the
  message names both the variable and where an Ollama key comes from. Add the
  live half behind the existing docker gate (`:633-651`): with the variable
  absent from the environment, `docker compose config` exits nonzero and its
  stderr names the variable.
- [ ] T107 [P] [US3] (spec US3-S5, FR-012) Anti-vacuity test, same file: assert
  `_is_mandatory("${UPSTREAM_MODEL_API_KEY:?anything}")` is True, directly on the
  helper at `:181-193`. Four committed tests are computed from
  `_mandatory_compose_vars()`; if that set silently empties, all four pass while
  checking nothing (plan T11).

### Implementation for this story

- [ ] T108 [US3] (FR-011) Change `container/compose.demo.yaml:125` to the
  required form with a message naming the variable and `https://ollama.com/settings/keys`.
  One line. Do not touch the engine service's environment, and do not change the
  teardown command documented at `docs/onramp.html:297-298` (plan T15).
- [ ] T109 [US3] (FR-012) Update `_is_mandatory`'s docstring examples to include
  the `:?` case, so the helper's contract and its new caller agree in writing.
- [ ] T110 [US3] (FR-013, FR-014, FR-015, FR-016, FR-017) Add the preflight to
  `run_prepare_phase`, immediately after the install block at
  `factory/supervision/demo_driver.py:329-347` and before step 2's `git init`: a
  seam defaulting to a function that loads the config install just wrote, runs
  `LLMProbe().gather(...)` / `.evaluate(...)` under `asyncio.run`, and wraps a
  raising probe into a failed finding the way `factory/controlplane/verify.py:1170-1181`
  does. Run **only** that probe, never the whole sweep (plan, US3 approach). Add
  the fatal-set constant and the remedy constant beside `SANDBOX_REMEDY`. Keep
  the `gh` reasoning in the comment at `:339-347`; narrow its width only. Do not
  renumber `step N/5` (plan T13).
- [ ] T111 [US3] (T10) Update the seven existing `run_prepare_phase` call sites in
  `tests/test_110_us1_demo_first_boot.py` (`:349, 442, 494, 538, 552, 596, 610`)
  to inject a passing `llm` finding. **This is part of this story.** Without it a
  seam with a production default sends every one of those tests down the new
  refusal path, and the story lands red.

### Verification for this story

- [ ] T112 [US3] (spec US3-S1, spec US3-S4, SC-003) Paste into the PR: the
  refusal as the driver prints it for a failed `llm` finding — the gateway's own
  detail above, the remedy below — beside the `docker compose config` refusal for
  an unset variable; and the full-suite before-and-after counts, which must show
  the seven updated 110 tests still passing.

## Phase 2: User Story 1 — A refused sandbox names the restriction that refused it

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

## Phase 3: User Story 2 — The grant is a file this project ships

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

Every task above runs against captured strings and committed files. **For US1 and
US2, none of them proves the thing the spec is for**, because proving it requires
a host that the floor host is not: one where
`kernel.apparmor_restrict_unprivileged_userns=1` and `/etc/apparmor.d/bwrap` does
not exist. On this machine the profile has been in place since 2026-07-16, which
is precisely why the defect survived a released demo, a passing suite, and a
successful end-to-end run on 2026-08-27.

That proof is the operator verification in `plan.md`: a stock box, or this one
with the profile moved aside and reloaded, reading the refusal and doing only
what it says. `tasks.md` forbids attempting it here on purpose — a test that
modifies host confinement policy is a test that has acquired privilege, which
plan T1 refuses.

**US3 is different, and it is worth saying why.** Its tasks prove the refusal
fires, that it names the right variable, that the non-fatal case still passes,
and that the compose file declares the credential as required — all of it from
committed files and injected findings, none of it needing a special host. What
they cannot prove is that the *released artifact* carries the change: strangers
fetch `compose.yaml` from a GitHub release and run an image from ghcr, and
neither exists until the next release publishes them. A landed US3 and a fixed
demo are two events, and the second one needs an operator (plan, dispatch
hazards).
