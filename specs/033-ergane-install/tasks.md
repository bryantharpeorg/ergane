# Tasks: Ergane Install — the control plane's config

Three stories, strictly serial: US2 consumes US1's typed shape, and US3's last
act is to run US2's verify (FR-007). Work test-first within a story and commit
once per task.

## Format: `[ID] [P?] [Story] Description`

Read `plan.md` first. Trap 1 is the scope fence — no workflow, no systemd unit,
no messenger adapter in this epic. Trap 2 is the one that will bite hardest:
"the doctor's findings grammar" names the wrong `Finding` class.

**US1 is landed** (`5b4351a`, PR #68, 2026-08-14). T001–T010 are recorded for
provenance and must not be re-executed. The remaining work is US2 and US3, and
US2 consumes the landed shape at `factory/controlplane/config.py:99` — as it
exists on the branch, not as this file describes it.

## Phase 1: User Story 1 — The control plane has a typed, refusing config (Priority: P1) 🎯 MVP — **LANDED `5b4351a`**

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T001 [US1] Write the happy parse FIRST (spec US1-S1): a `version: 1`
      config declaring `llm.mode = "direct"` with one persona block,
      `memory.backend = "hindsight"`, `temporal.mode = "external"` with address
      and namespace, an OTLP endpoint, and `escalation.adapter = "telegram"`
      parses to the typed shape with every undeclared optional at its
      documented default. Assert the defaults explicitly — an untested default
      is a guess.

- [ ] T002 [US1] Write the one-namespace refusal FIRST (spec US1-S2, FR-005):
      a `[temporal]` block declaring a list of namespaces is refused with a
      named rule stating the design reason.

- [ ] T003 [US1] Write the secret-shape refusals FIRST as a table (spec US1-S3,
      FR-003): an `api_key_env` holding a credential-shaped literal rather than
      an env-var name is refused naming the field. Include the two shapes this
      host actually uses — an `sk-` prefix and a bot token's `digits:base64`
      grammar — and an identifier-shaped value that must be accepted.

- [ ] T004 [US1] Write the unknown-adapter refusal FIRST (spec US1-S4): an
      unregistered `escalation.adapter` is refused naming it and listing the
      registered ones.

- [ ] T005 [US1] Write the fail-closed case FIRST (spec US1-S5, FR-013): with
      no config file, a command needing the control plane fails closed naming
      `ergane install` — never a half-configured default.

- [ ] T006 [US1] Write the managed-mode refusal FIRST (spec US1-S6, FR-004):
      `temporal.mode = "managed"` is refused naming 042 as the epic that
      implements it. A mode that parses but installs nothing is discovered
      hours later as an absent server.

### Implementation for User Story 1

- [ ] T007 [US1] Resolve the config path from the XDG config home with an
      environment override, and add that override to 030's session fixture in
      `tests/conftest.py` (grep `_isolated_test_store`). **Read plan trap 5
      first**: if 034 has landed, reuse its resolver rather than adding a
      second one. A test that writes the operator's real
      `~/.config/ergane/config.toml` has rewritten this host's control plane.

- [ ] T008 [US1] Implement the parser: `tomllib` read, frozen typed
      `ControlPlaneConfig`, five mode-discriminated blocks, every violation
      raising the `FactoryConfigError` shape (`factory/verify/factory_yaml.py:80`)
      with a stable rule slug, the value `repr`-rendered, the source named.

- [ ] T009 [US1] Make the `direct`-mode LLM block compatible with the persona
      registry's semantics (FR-014) — `factory/config.py:65` (`class Persona`),
      `:88` (`load_personas`) — sufficient for both accounting designs to read
      without moving any accounting (024 owns that).

- [ ] T010 [US1] Full suite green: `uv run pytest -q`.

## Phase 2: User Story 2 — Install proves every connection (Priority: P1)

Chains on US1 merged. **Read plan trap 2 before writing a line, and trap 1
before touching the escalation probe.**

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T011 [US2] Write the all-pass case FIRST (spec US2-S1): with every
      subsystem reachable, all findings pass, each detail names what was
      actually done ("completed a 1-token completion against persona
      `implementer`", not "ok"), and exit is 0.

- [ ] T012 [US2] Write the no-masking case FIRST (spec US2-S2): Temporal
      reachable but the declared namespace absent fails the temporal finding
      naming the namespace and the creating command, while the other four
      findings still render.

- [ ] T013 [US2] Write the escalation-probe case FIRST (spec US2-S3): a test
      message is delivered through the configured transport and the finding
      names the transport and what was delivered, **and** records that
      lifecycle verification is deferred to 041 (FR-006's last clause). Do not
      build an adapter seam here — plan trap 1.

- [ ] T014 [US2] Write the timeout case FIRST (spec US2-S4) by pointing a probe
      at `127.0.0.1:1` and asserting it fails *within* its declared bound with
      the timeout named. Assert on the bound, not on a predicted exception type
      — plan trap 7 records why that distinction has already cost this repo.

- [ ] T015 [US2] Write the skipped-by-declaration case FIRST (spec US2-S5): a
      subsystem declared `none` renders an explicit chosen-absence finding,
      distinguishable from both a deferral and a `ServiceNotAnswering`
      (plan trap 3 — all three must be tellable apart).

- [ ] T015a [US2] Write the absent-client-library case FIRST (spec edge case):
      a probe whose client library cannot be imported renders a *failing
      finding naming the missing dependency*, never a traceback — the
      operator's remedy is an install command, not a stack read.

### Implementation for User Story 2

- [ ] T016 [US2] Implement the five probes against the doctor's `Probe`
      protocol (`factory/doctor/probes.py:69`) — thin `gather()`, frozen
      snapshot, pure `evaluate()` — copying the shape of `OrphanedKeyProbe`
      (`:243`), not its subject.

- [ ] T017 [US2] Render results as `Finding(check, passed, detail)` from
      `factory/mergequeue/models.py:208` — the grammar FR-006 actually
      describes — and write **nothing** to the findings store. Filing verify
      results as ledger rows would count a down collector as a recurring defect
      beside real ones (plan trap 2).

- [ ] T018 [US2] Exercise every probe's `gather()` at least once against a live
      double (SC-006): a loopback OTLP listener, a local Temporal dev server, a
      stub HTTP endpoint. Follow the auto-skip discipline in
      `tests/test_live_proxy.py`'s docstring and the markers at
      `pyproject.toml:33-37`. SC-006 is a claim about which code paths ran, so
      name in the commit which double covered which gather. **Read plan trap 10
      before starting any server**: the Temporal double runs inside a
      `try/finally` shutdown bracket (the `tests/test_verification_flow.py:466-470`
      shape) or an existing fixture — never a bare `Popen`. Orphans of exactly
      this process class OOM-killed the host on 2026-08-11.

- [ ] T019 [US2] Full suite green: `uv run pytest -q`.

## Phase 3: User Story 3 — The walkthrough writes what the parser accepts (Priority: P2)

Chains on US2 merged.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T020 [US3] Write the blank-host case FIRST (spec US3-S1) against a
      scripted interview (plan trap 6 — a seam, not a monkeypatched `input()`):
      the resulting file parses under US1 and the automatic verify runs, its
      findings being the command's final output.

- [ ] T021 [US3] Write the surgical-edit case FIRST (spec US3-S2): a re-run
      changing only the OTLP endpoint yields a config diff touching exactly the
      `[telemetry]` block, and a re-run with unchanged answers is byte-identical.
      Plan trap 4 says how this is made true by construction rather than by a
      round-tripping library.

- [ ] T022 [US3] Write the refuse-at-entry case FIRST (spec US3-S3): a
      plaintext secret entered where a reference belongs is refused at entry
      with the same named rule the parser would use — one rule table, not two.

- [ ] T022a [US3] Write the managed-mode-at-entry case FIRST: answering
      `temporal.mode = "managed"` in the interview is refused at entry naming
      042 as the epic that implements it, with the same named rule the landed
      parser uses (US1-S6's rule — one table, not two).

- [ ] T022b [US3] Write the unreadable-config case FIRST (spec edge case): an
      existing config file the process cannot read (permissions) fails closed
      naming the path and the permission problem — in the walkthrough's
      defaults load and in any consumer reaching it through the landed
      resolver. Never a half-parsed default.

- [ ] T023 [US3] Write the **contended** lock case FIRST (spec US3-S4, FR-007):
      two install processes, one config path, the second waits or is refused. A
      lock only ever tested uncontended is a lock nobody has tested.

### Implementation for User Story 3

- [ ] T024 [US3] Add the prompter seam and the subsystem-by-subsystem
      interview: mode first, then only that mode's fields, existing values as
      defaults on re-run.

- [ ] T025 [US3] Render the config file deterministically from the typed shape
      — fixed block and key order (plan trap 4) — and note in the commit that a
      hand-edited file's comments are not preserved, because that is a real
      consequence an operator should meet in a doc rather than in a diff.

- [ ] T026 [US3] Hold the exclusive lock for the whole run, reusing 034's lock
      helper if that epic landed first (plan trap 5).

- [ ] T027 [US3] End the command by executing US2's verification (FR-007).

- [ ] T027a [US3] Prove SC-002: in a scripted end-to-end walkthrough-and-verify
      run, grep the written config file and every captured log for each
      credential value the session used and assert zero hits; commit the pasted
      output (SC-002 — the spec's evidence rule applies: pasted verbatim, in
      the diff).

- [ ] T028 [US3] Full suite green: `uv run pytest -q`.

## Verification

- [ ] Final gate command passes green.
- [ ] Nothing in the diff writes to the findings store.
- [ ] Every probe's gather ran against a live double, and the commit says which.
- [ ] The config lock has a contended test.
- [ ] No workflow, no systemd unit, no messenger adapter — those are 041 and 042.
