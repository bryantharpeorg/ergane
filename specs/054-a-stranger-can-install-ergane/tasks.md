# Tasks: a stranger can install Ergane

**Spec**: `specs/054-a-stranger-can-install-ergane/spec.md`
**Plan**: `specs/054-a-stranger-can-install-ergane/plan.md`

Read the plan's **Traps** before the first task. Trap 1 decides whether US2 takes
one attempt or four.

Tests are written before the implementation and must fail for the stated reason
before anything is made to pass. A test that passes on first write has not
established what it claims.

## Phase 1: User Story 1 — The repository tells a new operator where to start

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) `tests/test_readme.py`: extract every command `README.md` names
      and assert each resolves against the CLI's own `--help`. Reuse
      `tests/test_claude_md.py`'s `_commands()` (:52), `_verbs_of()` (:79),
      `_split()` (:87) and `_help()` (:110) — lift them to a shared helper if
      that is cleaner, but do not write a second extractor (trap 3).
- [ ] T002 [P] [US1] (spec US1-S2) `tests/test_readme.py`: anti-vacuity — assert the extracted
      command list is non-empty and contains `ergane install` and `ergane init`
      by name. Model it on `test_the_command_sweep_actually_read_the_file`
      (`tests/test_claude_md.py:160`). Without this, T001 passes on an empty
      page (trap 2).
- [ ] T003 [P] [US1] (spec US1-S3) `tests/test_readme.py`: assert every path `README.md` cites
      exists, with its own anti-vacuity assertion (`_paths()` :177, test :193,
      guard :204).
- [ ] T004 [P] [US1] (spec US1-S4) `tests/test_readme.py`: assert the page contains no secret
      value — environment variable *names* only, and no token, key or live
      address.
- [ ] T005 [P] [US1] (spec US1-S5) `tests/test_readme.py`: assert the page states no spec state,
      story count or spend figure, on the same principle
      `tests/test_claude_md.py` already enforces for `CLAUDE.md` (:249, guard
      :297).

### Implementation for this story

- [ ] T006 [US1] (spec US1-S1, FR-001, FR-002) Write `README.md` at the repository root: what Ergane is in a
      paragraph, the prerequisites that must already be true of the host
      (a LiteLLM-shaped gateway, an authenticated `gh`, `bwrap`, `git`, `uv`,
      Python >= 3.11, node for the agent CLI, a systemd user session), then the
      command chain in order — obtain the source, `ergane install`,
      `ergane install --verify`, `ergane worker install`, `ergane init --wire`,
      `ergane repo onboard`, and the first `ergane build start`.
- [ ] T007 [US1] (spec US1-S1, FR-002) Quote the gateway prerequisite from
      `factory/controlplane/config.py`'s own refusal text rather than
      paraphrasing it, and say plainly that standing one up is outside what
      Ergane does.
- [ ] T008 [US1] (spec US1-S5, FR-004) Point the reader at the live sources for anything that changes —
      `ergane spec list specs`, `ergane build status`, `ergane findings list` —
      rather than stating a number (trap 8).
- [ ] T009 [US1] (spec US1-S1, FR-001) Add the leaving path: `ergane repo forget` and
      `ergane worker uninstall`, so the page covers arrival and departure.
- [ ] T010 [US1] (spec SC-001) Commit the SC-001 transcript: run the chain top to bottom on a
      host that satisfies the prerequisites and paste the output into
      `specs/054-a-stranger-can-install-ergane/evidence/us1-sc-001.md`. The judge
      sees only the diff, so uncommitted runtime evidence does not exist (trap 6).

## Phase 2: User Story 2 — Install refuses a host that cannot run an agent

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1) `tests/test_controlplane_host_probe.py`: a host missing `bwrap`
      yields a failing finding naming `bwrap` and its purpose. **Simulate the
      host through the probe's injected seam** — never call the real host
      (trap 1).
- [ ] T012 [P] [US2] (spec US2-S2) Same file: `gh` present but unauthenticated yields a finding
      distinguishable from `gh` absent, because the remedies differ.
- [ ] T013 [P] [US2] (spec US2-S3) Same file: a host with everything present passes, and the five
      existing probes' findings are byte-identical to today's.
- [ ] T014 [P] [US2] (spec US2-S4, FR-007) Same file: assert the probe's host access is injectable, and
      that no test in this module reaches the real host — a sweep over the
      module asserting no unpatched `subprocess`, `shutil.which` or `systemctl`
      call escapes the seam.
- [ ] T015 [P] [US2] (spec US2-S5, FR-010) Same file: assert the probe writes nothing and installs nothing
      (FR-010, trap 10).

### Implementation for this story

- [ ] T016 [US2] (spec US2-S1, FR-005) Add `HostProbe` to `factory/controlplane/verify.py` following
      the existing contract exactly: `.name`, `.gather(config)`,
      `.evaluate(snapshot)`, reporting in the `Finding(check, passed, detail)`
      grammar imported at `:29`. Model the shape on `TelemetryProbe` (:434).
- [ ] T017 [US2] (spec US2-S4, FR-007) Give it one injected seam for all host access, defaulting to the
      real host and overridable in tests.
- [ ] T018 [US2] (spec US2-S3, FR-005) Append it to `REGISTRY` (`:567`). Do not change the sweep's
      exception handling at `:585`.
- [ ] T019 [US2] (spec US2-S2, FR-006) Make each finding name the prerequisite, what it is needed for,
      and the remedy — separately for absent and for present-but-unusable.

## Phase 3: User Story 3 — Verify proves every model the registry can dispatch

Depends on US2 being merged: both stories edit `factory/controlplane/verify.py`
(trap 9).

### Tests for this story (write FIRST, must fail)

- [ ] T020 [P] [US3] (spec US3-S1) `tests/test_controlplane_llm_probe.py`: the set of aliases
      probed equals the set of distinct dispatchable aliases in the registry,
      not `{implementer's}`.
- [ ] T021 [P] [US3] (spec US3-S2) Same file: two personas sharing one alias cause exactly one
      completion.
- [ ] T022 [P] [US3] (spec US3-S3) Same file: one unknown alias produces a finding naming the
      alias and the personas that would have used it, and the remaining aliases
      are still reported — the sweep does not stop at the first failure.
- [ ] T023 [P] [US3] (spec US3-S4) Same file: a persona declared `agent: none` is skipped with no
      completion attempted.
- [ ] T024 [P] [US3] (spec US3-S5) Same file: hold the fallback-alias decision explicitly,
      whichever way US3 decides it (trap 5).

### Implementation for this story

- [ ] T025 [US3] (spec US3-S1, FR-008) Replace `persona = "implementer"`
      (`factory/controlplane/verify.py:195`) with a distinct-alias set derived
      from the registry via `factory.config.load_personas` — never by reading
      `personas.yaml` from a path (trap 4).
- [ ] T026 [US3] (spec US3-S2, US3-S3, FR-008, FR-009) Probe each distinct alias exactly once and accumulate findings
      per alias; a failure must not abort the remaining probes.
- [ ] T027 [US3] (spec US3-S1) Keep the `llm` check's passing output as informative as today's
      when everything resolves.

## Verification

- [ ] T028 Run the full gate suite and confirm it is green for the right reason:
      each new test fails when its subject is reverted.
- [ ] T029 Prove US2 by control — make `bwrap` unreachable on `PATH` on a scratch
      host, confirm `ergane install --verify` emits the finding, restore it and
      confirm the finding clears.
- [ ] T030 Prove US3 by mutation — point one persona at an alias the gateway does
      not know, confirm the finding names it and that the others still report,
      and confirm the completion count equals the distinct-alias count.
