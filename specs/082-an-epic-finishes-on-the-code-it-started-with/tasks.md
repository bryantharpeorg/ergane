# Tasks: an epic finishes on the code it started with

**Spec**: `specs/082-an-epic-finishes-on-the-code-it-started-with/spec.md`
**Plan**: `specs/082-an-epic-finishes-on-the-code-it-started-with/plan.md`

Read the plan's traps before the first task. Trap 1 (**a versioned worker
serves only its version — land US1 dark**), trap 5 (**probe the roadmap's
migration mechanics, don't guess them**), trap 10 (**the predecessor sweep
already exists — reuse the adapter's R4, never rebuild it**) and trap 14
(**pasted evidence is charged to the 64 KiB diff budget — paste minimal
proving lines**) are the four that decide whether an attempt lands.

## Phase 1: User Story 1 — The worker declares which code it is

### Probes for this story (run FIRST, commit the transcripts as evidence)

- [ ] T001 [US1] (spec US1-S4; plan trap 5, FR-002) On the dev server, with a toy workflow:
      prove whether a PINNED workflow's continue-as-new inherits its version
      or re-routes to current. The roadmap's `versioning_behavior` is chosen
      by this transcript, not by preference.
- [ ] T002 [US1] (plan trap 6, FR-007 groundwork) On the dev server: prove
      what happens to an open *unversioned* workflow when a versioned worker
      becomes current — served, stalled, or auto-upgraded. Commit the
      transcript; US4's refusal encodes this answer.

### Tests for this story (write next, must fail)

- [ ] T003 [P] [US1] (spec US1-S2, FR-001) **The control.** In
      `tests/test_worker_versioning.py`: with no versioning environment,
      `build_worker` constructs exactly today's worker — no
      `deployment_config` — and the existing `tests/test_worker.py` suite
      passes untouched (plan trap 13).
- [ ] T004 [P] [US1] (spec US1-S1, FR-001; plan trap 13) With the environment
      gate set, the booted worker registers deployment `ergane-worker` with
      the captured revision as build id, read back via the SDK from a real
      dev server. **Probe first whether the time-skipping test server
      supports the deployment API**; if not, use `start_local()` or the
      session dev server behind the bare-RuntimeError live guard — never a
      marker.
- [ ] T005 [P] [US1] (spec US1-S5, FR-001; plan trap 11) With versioning
      engaged and `_worker_revision()` returning `None`, boot refuses by
      name.
- [ ] T006 [US1] (spec US1-S3/S4, FR-001/FR-002) Pinned behavior declared on
      epic/escalation/question defns; the roadmap carries whichever behavior
      T001's transcript proved out — asserted structurally (decorator
      arguments), with the routing itself carried by US2's live evidence.

### Implementation for this story

- [ ] T007 [US1] (FR-001) `factory/worker.py:233-252` — build
      `deployment_config` from the environment gate; validate the gate's
      build id against `_WORKER_REVISION` (`:230`) when both exist.
- [ ] T008 [US1] (FR-001/FR-002) Add `versioning_behavior` to the four defns
      (`factory/workgraph/workflow.py:562`,
      `factory/roadmap/workflow.py:506`,
      `factory/escalation/workflow.py:212`,
      `factory/escalation/question.py:86`).

### Verification for this story

- [ ] T009 [US1] (SC-groundwork) Paste: dev-server worker boot with the gate
      set, `temporal worker deployment describe --deployment-name
      ergane-worker` showing the version; then the control boot without the
      gate, `deployment list` unchanged.

## Phase 2: User Story 2 — A deploy puts new code on the floor without touching the old

**Depends on US1 having merged** (`depends_on_merged`).

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S4, FR-004) Refusals by name, each its own
      case: not a git checkout; unresolvable revision; dirty tree with no
      explicit revision; Temporal unreachable. Nothing touched before the
      refusal.
- [ ] T011 [P] [US2] (spec US2-S3, FR-003) Idempotence: deploying the
      already-current revision converges without error or duplicate units.
- [ ] T012 [P] [US2] (spec US2-S5, FR-003; plan trap 7) Registration-wait
      timeout reports degraded and leaves the unit running; a re-run
      converges.
- [ ] T013 [P] [US2] (spec US2-S6, FR-010) The report names every version
      and its state (current / draining / drained).
- [ ] T014 [US2] (plan traps 2, 4) The generated instance runs from the
      deployment checkout with the deployment's interpreter, the deployments
      root is inside `InstallLayout.roots`, and the env-command indirection
      survives in the instance's wrapper path.

### Implementation for this story

- [ ] T015 [US2] (FR-003) `factory/supervision/deploy.py`: revision
      resolution, `git worktree add --detach` under
      `supervision_home()/deployments/<build-id>`, `uv sync --frozen`,
      instance start, bounded `describe-version` poll, `set-current-version`,
      report. Take the deploy lock (spec edge case) first.
- [ ] T016 [US2] (FR-003) The template-instance plumbing in
      `factory/supervision/units.py` that T014 asserts (shared with US4's
      generation swap — coordinate, don't duplicate).
- [ ] T017 [US2] (FR-003/FR-004) The `deploy` verb in
      `factory/cli/nouns/worker.py`, thin like `install` (`:23-32`).

### Verification for this story

- [ ] T018 [US2] (spec US2-S1, US2-S2; SC-001, SC-005) **The story's whole point, live.** With an
      attempt in flight on version A: deploy B; paste the attempt finishing
      on A (no KILLED, no `temporal activity fail`), the next epic's 053
      revision query reporting B, and the deploy report.

## Phase 3: User Story 3 — A drained version leaves the host

**Depends on US2 having merged** (`depends_on_merged`).

### Tests for this story (write FIRST, must fail)

- [ ] T019 [P] [US3] (spec US3-S2, FR-005) **The control.** The pure reap
      decision never selects the current version, idle or not.
- [ ] T020 [P] [US3] (spec US3-S3, FR-005) Nor a version with any open
      pinned workflow — and the check re-runs at action time, not sweep
      start (spec edge case).
- [ ] T021 [P] [US3] (FR-005; plan trap 3) Reaping removes the checkout via
      `git worktree remove` (with `prune` on failure), never bare deletion.

### Implementation for this story

- [ ] T022 [US3] (FR-005) The pure decision function beside deploy; the
      sweep wired into the probe's cycle (`factory/supervision/probe.py` —
      find its loop and report path) and the tail of `worker deploy`.

### Verification for this story

- [ ] T023 [US3] (spec US3-S1; SC-003) Paste: a drained non-current version, then within
      one sweep interval — unit inactive, checkout gone, `describe-version`
      unknowing.

## Phase 4: User Story 4 — The unversioned unit retires

**Depends on US2 having merged** (`depends_on_merged`).

### Tests for this story (write FIRST, must fail)

- [ ] T024 [P] [US4] (spec US4-S1, FR-006) `install()`'s generated set
      contains `ergane-worker@.service` and not `ergane-worker.service`
      (`factory/supervision/units.py:259-268`).
- [ ] T025 [P] [US4] (spec US4-S3, FR-006) `uninstall()` removes the legacy
      unit only when its text matches what install once wrote — the existing
      provenance rule (`:483`, `:528`), extended, not forked.
- [ ] T026 [P] [US4] (spec US4-S2, FR-007) The migration refusal: legacy
      removal refused by name while any epic T002's transcript classifies as
      strandable remains open.

### Implementation for this story

- [ ] T027 [US4] (FR-006/FR-007) The generation swap
      (`_worker_text` → template at `:327`), the uninstall extension, the
      refusal.

### Verification for this story

- [ ] T028 [US4] (SC-004) Paste: post-migration
      `systemctl --user list-units 'ergane-worker*'` showing instances only,
      and the unit directory without the legacy file.

## Phase 5: User Story 5 — A dead worker is noticed in beats, not hours

**Independent of Phases 2–4; may run in parallel after US1.**

### Tests for this story (write FIRST, must fail)

- [ ] T029 [P] [US5] (spec US5-S1, US5-S2, FR-008) The derivation: a 4-hour
      deadline yields the cap (120s); a 60-second deadline yields today's
      five-beat floor; the function is monotone between them. Name both
      constants (`factory/workgraph/workflow.py:401`, the new cap).
- [ ] T030 [US5] (spec US5-S4, FR-009; plan trap 10) **Verify, don't build**:
      the predecessor sweep already exists (adapter R4 — `pid_file` at
      `factory/workgraph/adapter.py:732`, `_reap` at `:1320`, tested in
      `tests/test_adapter.py`). Confirm the existing suite covers: recorded
      live group terminated before the next attempt; no record → nothing
      touched (**the control**); record in the sidecar, absent from
      `read_worktree_diff`. Add a test ONLY for a proven gap, extending the
      existing file.

### Implementation for this story

- [ ] T031 [US5] (FR-008; plan trap 9) The cap in
      `_agent_heartbeat_timeout` (`factory/workgraph/workflow.py:429-434`),
      the comment at `:411-425` rewritten to argue the cap,
      `start_to_close_timeout` and `_AGENT_RETRIES` untouched.
- [ ] T032 [US5] — **STRUCK at the 2026-08-22 refinement.** The
      record-then-sweep it asked for is landed code (adapter R4, see T030);
      building it again would fork the pid-file contract. No work here.

### Verification for this story

- [ ] T033 [US5] (spec US5-S3; SC-002) **Live, with timestamps.** SIGKILL the worker unit
      mid-attempt; paste the kill time and the replacement attempt's
      schedule time, ≤3 minutes apart, against the 2026-08-19 ~2h baseline.
