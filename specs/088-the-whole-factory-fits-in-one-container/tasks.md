# Tasks: the whole factory fits in one container

**Spec**: `specs/088-the-whole-factory-fits-in-one-container/spec.md`
**Plan**: `specs/088-the-whole-factory-fits-in-one-container/plan.md`

Read the plan's traps before the first task. Four decide whether an attempt
lands. Trap 1: the probe executes `/usr/bin/bwrap`, the pinned path. Trap 2:
the probe's argv carries the production mount shape (`--proc`, `--dev`,
tmpfs, ro `/usr`) — the minimal invocation passes where the real one fails.
Trap 6: the supervisor's tests drive stubs, never real children. Trap 8: you
cannot build the image you write; US3's proof is drift tests over committed
text, red before green.

## Phase 1: User Story 1 — The preflight proves the sandbox runs

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001, FR-004) Drive `_inspect_host`
      (`factory/controlplane/verify.py:253`) with the bwrap execution seam
      stubbed to fail; assert `present: true`, `usable: false`. **Run against
      the unfixed tree and capture the red** — today `:281` and `:282` are the
      same expression. That red is SC-001's first half.
- [ ] T002 [P] [US1] (spec US1-S2, FR-003) Assert the present-but-unrunnable
      remedy is textually distinct from the absent-case remedy at `:284`, and
      that it names unprivileged user namespaces and both committed
      confinement artifacts by path (`container/seccomp-ergane.json`,
      `container/ergane-engine.profile`).
- [ ] T003 [P] [US1] (spec US1-S3, FR-004) The real-binary case: when
      `/usr/bin/bwrap` executes on this host, `usable` is true. Skip by a
      guard evaluated at call time, never a marker (trap 5).
- [ ] T003b [P] [US1] (spec US1-S4, FR-002) Inspect the probe's assembled
      argv: it executes the pinned path and carries `--proc`, `--dev`, a
      tmpfs and a read-only `/usr` bind (trap 2).

### Implementation for this story

- [ ] T004 [US1] (FR-001..FR-004) In `factory/controlplane/verify.py`, give
      `_inspect_host` a bounded, injectable execution of the pinned bwrap path
      with the production mount shape, deriving `usable` (`:282`) from it
      while `present` (`:281`) keeps coming from `shutil.which` (`:261`).
      Copy the gh check's discipline (`:265-275`) and its two-remedy shape
      (`:296-297`). Exec stays in `_inspect_host`; `evaluate` stays pure
      (trap 4).

### Verification for this story

- [ ] T017 [US1] (spec US1-S1, SC-001) Paste the probe's three branches with
      distinct remedies and the production-shape argv, plus T001's red.

## Phase 2: User Story 2 — One process supervises the factory

### Tests for this story (write FIRST, must fail)

- [ ] T005 [US2] (spec US2-S1, US2-S2, FR-005, FR-006) Stub children: Temporal
      starts first; the worker waits for the address; an address that never
      answers exits nonzero naming address and timeout.
- [ ] T006 [P] [US2] (spec US2-S3, FR-007) One child exits: others stopped,
      exit names the first-dead child and status.
- [ ] T007 [P] [US2] (spec US2-S4, FR-008) SIGTERM: fan-out, grace period,
      SIGKILL only for stragglers.
- [ ] T008 [P] [US2] (spec US2-S5, FR-009) No assembled child argv contains
      `python -` (`factory/supervision/temporal_server.py:9-12`).
- [ ] T008b [P] [US2] (spec US2-S6, US2-S7, FR-009) Same-path check, both
      branches: a registry naming a missing path refuses **before any child
      starts**, naming slug and path and both remedies (wrong mount / stale
      cache, trap 7b); an empty registry and an absent registry file both
      start normally (trap 7a). Build registries through `load_registry`
      (`factory/registry.py:375`) against a relocated `ERGANE_STATE_HOME`.

### Implementation for this story

- [ ] T009 [US2] (FR-005..FR-009) The container supervisor module under
      `factory/supervision/`: three children
      (`factory.supervision.temporal_server` — `--db-filename` required,
      `factory.worker`, `factory.notify.service`) declared in one mapping,
      shaped like `factory/supervision/units.py:115-119` without importing it.
      Temporal binds `0.0.0.0` inside the container so a published port
      reaches it; the worker points at `127.0.0.1:7233`. The registry check
      runs before the first child, resolving before comparing
      (`factory/registry.py:266-271`).

### Verification for this story

- [ ] T018 [US2] (spec US2-S1, SC-002) Paste the supervisor run: readiness,
      timeout refusal, child-death naming, SIGTERM fan-out, both same-path
      branches.

## Phase 3: User Story 3 — The image and committed artifacts cannot drift

### Tests for this story (write FIRST, must fail)

- [ ] T010 [US3] (spec US3-S1, FR-013) Dockerfile drift test: derives the
      binary list from the probe and `factory/workgraph/adapter.py:398-401`
      (+ `DEFAULT_EXECUTABLE` `:97`) — derived, never restated (trap 9);
      asserts bwrap at `/usr/bin/bwrap`, non-root user, US2 entrypoint. Red
      first against a Dockerfile with one binary removed.
- [ ] T010b [P] [US3] (spec US3-S2, US3-S3, FR-011, FR-013) Confinement drift
      tests: the seccomp JSON parses, unconditionally allows exactly the
      seven syscalls beyond the vendored baseline (set shared as one
      constant, trap 9), and carries no clone3-ERRNO rule; the AppArmor text
      contains `userns,` `mount,` `pivot_root,`, retains the deny lines, and
      contains no `flags=(unconfined)`.
- [ ] T011 [P] [US3] (spec US3-S4, FR-012, FR-013) Reference-compose drift
      test: one service; `init: true`; non-root `user`; `cap_drop: [ALL]`;
      `no-new-privileges`; seccomp artifact by path; `apparmor=ergane-engine`;
      same-path binds for state root and supervision home; env passthrough
      for the five blocks; per-repo same-path mount list; **no `unconfined`
      token anywhere** (trap 11).

### Implementation for this story

- [ ] T012 [US3] (FR-010) Write the `Dockerfile`: bubblewrap at
      `/usr/bin/bwrap`, git, gh, uv, node, python, the agent runner
      (`DEFAULT_EXECUTABLE`); install `ergane-cli`; non-root runtime user;
      entrypoint = T009's supervisor.
- [ ] T012b [US3] (FR-011) Commit `container/seccomp-ergane.json` and
      `container/ergane-engine.profile` **from the findings appendix text**
      (trap 10), each with a comment naming upstream base and version.
- [ ] T013 [US3] (FR-012) Commit `container/compose.reference.yaml` per
      FR-012's list.
- [ ] T014 [US3] (spec US3-S5, FR-014) Write `docs/container.md` per US3 scenario 5: the
      same-path rule and FR-009; the supervision-home mount and why; the
      artifacts and config F as fallback; the subscription-credential
      trade-off (`factory/workgraph/adapter.py:767`, `:803`, `:817-820`); the
      `FROM` pattern; unsupported verbs; and that the reference compose is a
      reference — `ergane install` (spec 104) generates the operational
      project.

### Verification for this story

- [ ] T019 [US3] (spec US3-S1, SC-003) Paste each drift test red-then-green:
      Dockerfile, seccomp, AppArmor, reference compose.

## Phase 4: User Story 4 — The systemd verbs refuse by name

- [ ] T015 [US4] (spec US4-S1, FR-015) Stub the session predicate absent;
      assert `worker install`, `deploy`, `migrate` each refuse naming the
      missing session, the container as likely cause, the supervisor as
      replacement. Red first.
- [ ] T016 [US4] (spec US4-S2, FR-015) Gate `_install` (`factory/cli/nouns/worker.py:29`),
      `_migrate` (`:41`), `_deploy` (`:48`) on
      `_systemd_user_session_available` (`factory/cli/install.py:815-833`) —
      that predicate, moved if needed, never a second one (trap 12).

### Verification for this story

- [ ] T020 [US4] (spec US4-S1, SC-004) Paste the three refusals and the
      unchanged existing `worker` tests passing.
