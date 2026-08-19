# Tasks: the on-ramp stops leaking and guessing

**Spec**: `specs/064-the-on-ramp-stops-leaking-and-guessing/spec.md`
**Plan**: `specs/064-the-on-ramp-stops-leaking-and-guessing/plan.md`

Read the plan's **Traps** before the first task. Trap 2 is the one that decides
whether US1's tests prove anything at all.

Tests are written before the implementation and must fail for the stated reason
before anything is made to pass.

No edges. All three stories touch different modules and may run in parallel.

## Phase 1: User Story 1 — The bot token never reaches the journal

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) With logging at INFO and a stub transport, send a Telegram
      message using a **distinctive fake token**; assert the send occurred, and
      assert no captured log record contains the token. All three assertions or
      the test proves nothing (trap 2).
- [ ] T002 [P] [US1] (spec US1-S2) Assert the request is still observable in redacted form —
      a redacted URL or a line naming the operation (trap 1).
- [ ] T003 [P] [US1] (spec US1-S3) Assert both the worker and the operator-bridge entry
      points carry the protection.
- [ ] T004 [P] [US1] (spec US1-S4) Assert the protection holds when the adapter is constructed
      directly, without the caller configuring logging.
- [ ] T005 [P] [US1] (spec US1-S5) Assert `factory/notify/webhook.py` gets the same protection
      for a secret-bearing URL (trap 3).
- [ ] T006 [P] [US1] (spec Edge Cases) Assert a raised httpx exception does not render the
      token in its traceback (trap 4).

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-002, FR-004) Attach a redacting event hook to the httpx
      client used by the escalation adapters, covering both telegram and webhook.
      Prefer the hook over a logger level so the request line survives redacted
      (trap 1).
- [ ] T008 [US1] (FR-003) Apply it where the client is constructed rather than at each
      call site, so a future adapter inherits it.
- [ ] T009 [US1] (FR-001) Cover exception rendering as well as log records.
- [ ] T010 [US1] Add a comment at the hook naming `factory/supervision/units.py:425`
      as the design commitment it upholds, so the next reader sees why it exists
      rather than deleting it as noise.

## Phase 2: User Story 2 — Init names the repository it resolved and asks before enrolling a parent

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1) From a non-repository directory beneath a repository:
      assert init states the resolved root, requires confirmation, and writes no
      manifest when confirmation is declined.
- [ ] T012 [P] [US2] (spec US2-S2) From the repository root: assert **no** confirmation is
      required (trap 5).
- [ ] T013 [P] [US2] (spec US2-S3) From a subdirectory of the repository: assert the resolved
      root is stated and confirmation is required.
- [ ] T014 [P] [US2] (spec US2-S4) Under `--non-interactive` with a differing resolved root:
      assert a refusal, not an assumption (trap 7).
- [ ] T015 [P] [US2] (spec US2-S5) Assert `--check` reports the resolved root as a finding,
      not only in a header line.
- [ ] T016 [P] [US2] (spec Edge Cases) Assert a legitimate worktree invocation does not fire a
      spurious confirmation (trap 6), and that a bare `git init` repository with
      no commits still behaves as 051 established.

### Implementation for this story

- [ ] T017 [US2] (FR-005, FR-006) In `factory/cli/init.py`, compare the invocation
      directory against the resolved root from `resolve_repo_root` (:165) and
      require confirmation only when they differ for the walk-up reason —
      distinguishing that from the worktree case documented at :172.
- [ ] T018 [US2] (FR-007) Refuse under `--non-interactive` when they differ.
- [ ] T019 [US2] (FR-008) Emit the resolved root as a `--check` finding at the call site
      (`factory/cli/init.py:478`).

## Phase 3: User Story 3 — `revoke_key` is defined once

### Tests for this story (write FIRST, must fail)

- [ ] T020 [P] [US3] (spec US3-S1) Assert `LiteLLMClient` defines `revoke_key` exactly once.
- [ ] T021 [P] [US3] (spec US3-S2) Assert delegation by **observation**: patch
      `revoke_key_by_tokens` and assert `revoke_key`'s behaviour changes. Do not
      grep the source (trap 8).
- [ ] T022 [P] [US3] (spec US3-S3) Assert no class member in
      `factory/usage/litellm_client.py` is redefined — a guard against the class,
      not the instance.

### Implementation for this story

- [ ] T023 [US3] (FR-009) Delete the second `revoke_key`
      (`factory/usage/litellm_client.py:339`), keeping the delegating definition
      at :246.
- [ ] T024 [US3] (FR-010) Add the redefined-member guard.

## Verification

- [ ] T025 (SC-001) Trigger a live escalation, then confirm from the journal both that
      the send occurred **and** that no token substring appears. **Paste both
      into the diff** — an empty grep alone is not evidence (traps 2, 10).
- [ ] T026 (SC-004) Confirm the operator still receives escalation messages after the
      change.
- [ ] T027 (SC-002) `mkdir` a non-repository directory beneath a repository, run
      `ergane init` there, confirm the prompt, decline, and confirm nothing was
      written.
- [ ] T028 (SC-003) `grep -c "async def revoke_key" factory/usage/litellm_client.py`
      returns 1.
