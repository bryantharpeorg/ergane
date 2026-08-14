# Tasks: Supervised services

Three stories, strictly serial: US2 and US3 both alert through US1, and US3
reuses the unit-generation and probe machinery US2 builds. Work test-first
within a story and commit once per task.

## Format: `[ID] [P?] [Story] Description`

**Read `plan.md` before T001, including its first section.** The design input
for this epic is nine files in a different repository
(`/home/admin/code/homelab/infra/ergane-supervision/`), hand-written after a
host outage. Every trap in the plan is a line from them.

## Phase 1: User Story 1 — An alert can reach the operator when Temporal is dead (Priority: P1) 🎯 MVP

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T001 [US1] Write the no-Temporal case FIRST (spec US1-S1, FR-001): with
      no Temporal server reachable, a degraded report is delivered through the
      configured adapter and recorded in a local log. The test must construct
      **no Temporal client at all** — this epic is the caller 041 FR-002 exists
      for, and it runs when Temporal is gone.

- [ ] T002 [US1] Write the failed-send case FIRST (spec US1-S2, FR-002): an
      adapter that raises is logged and nothing propagates. A supervisor that
      crashes on a failed send has stopped supervising.

- [ ] T003 [US1] Write the fire-and-forget assertion FIRST (spec US1-S3): scan
      the module's source and assert it starts no workflow, creates nothing
      requiring an answer, and imports no Temporal client — assert it, do not
      intend it (plan trap 6's discipline, applied to imports).

- [ ] T004 [US1] Write the message-content case FIRST (spec US1-S4, FR-002): a
      rendered alert names the service, the observed condition and the duration.
      "Degraded" alone sends the operator to a terminal to learn what this code
      already knew.

### Implementation for User Story 1

- [ ] T005 [US1] Implement the out-of-band alert module: render, hand to 041's
      adapter, log locally. Swallow send failures (FR-002); complain loudly and
      exit non-zero when no delivery is possible at all (FR-015, plan trap 6).

- [ ] T006 [US1] Full suite green: `uv run pytest -q`.

## Phase 2: User Story 2 — The worker installs, is contained, and is watched (Priority: P1)

Chains on US1 merged. **Read plan traps 1, 2, 3, 4, 5 and 7 before writing —
each is a verbatim line from the prior art and each was paid for.**

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T007 [US2] Write the generated-unit assertions FIRST (spec US2-S1,
      FR-003, SC-006): units are active and enabled, linger is enabled, and a
      scan of the generated unit **text** finds no path outside the operator's
      own installation. Plan trap 7 is the clearest way this epic fails while
      looking finished.

- [ ] T007a [US2] Write the command-line spelling assertion FIRST (plan trap 9):
      no generated unit's command line contains the substring `python -`. The
      obvious spelling — `uv run python -m factory.worker` — is what an agent's
      `pkill -f "python -"` matched on 2026-08-12, killing the worker that was
      running it. Scan the generated text, and say in the commit that this is
      mitigation and not a fix (`hardening/agent-pkill-kills-the-live-worker`).

- [ ] T008 [US2] Write the whole-tree-stops case FIRST (spec US2-S2, FR-004,
      SC-002): stopping a unit with child processes leaves none behind. Count
      processes before and after and paste both counts. Plan trap 1 quotes why
      `KillMode=control-group` is not a default worth losing.

- [ ] T009 [US2] Write the three reaping conditions FIRST (spec US2-S3, FR-006,
      SC-003): seed an orphan older than the grace period, a fresh orphan, and a
      parented process; assert exactly one is reaped. Plan trap 3 explains each
      condition — in particular that `comm` truncates at 15 characters, so
      matching the full `temporal-test-server` matches nothing, forever,
      silently.

- [ ] T010 [US2] Write the outside-the-slice assertion FIRST (FR-006, plan
      trap 2): every generated unit is in the slice **except** the probe. A
      probe inside the slice is reclaimed alongside the leak it exists to
      report.

- [ ] T011 [US2] Write the dead-unit alert case FIRST (spec US2-S4, FR-007): a
      unit not active produces an alert naming the unit and the outage duration
      through US1's path, while it is still down.

- [ ] T012 [US2] Write the bounded-restart assertion FIRST (spec US2-S5,
      FR-005): the generated unit bounds its restart rate. Flapping during a
      memory storm deepens it.

- [ ] T013 [US2] Write the uninstall cases FIRST (spec US2-S6, FR-008, SC-005):
      exactly the units install created are removed, the config file is
      untouched, and a same-named unit the engine did not write is reported and
      left on disk. Record provenance at install time — do not guess at
      uninstall time.

- [ ] T014 [US2] Write the edge-trigger cases FIRST (spec US2-S7, FR-013): an
      unchanged healthy stack on the interval sends nothing; a status change
      sends once; a heartbeat rides its own much longer interval. The timer
      fires every couple of minutes, and a channel that pages that often is
      muted within a day — plan trap 4.

- [ ] T015 [US2] Write the no-remediation assertion FIRST (spec US2-S8,
      FR-014): the probe restarts and kills nothing except orphaned test
      servers. Assert it against the source — the instinct on reading "the
      worker is down" is to restart it, and plan trap 5 quotes why not.

- [ ] T016 [US2] Write the unescalatable-probe case FIRST (spec US2-S9,
      FR-015): a probe that cannot deliver says so in its own output and exits
      non-zero. Silent inability to escalate is indistinguishable from a healthy
      floor.

### Implementation for User Story 2

- [ ] T017 [US2] Generate the unit text from resolved paths: the slice, the kill
      semantics, the bounded restart. No literal from this plan's quotations
      reaches a generated file (plan trap 7).

- [ ] T018 [US2] Implement `ergane worker install` / `uninstall`, enabling
      linger, recording provenance, and refusing uninstall while an epic is in
      flight (FR-012) via the existing capacity read
      (`factory/activities/roadmap_activities.py:468`).

- [ ] T019 [US2] Implement the probe: unit liveness, TCP reachability, host
      memory headroom, orphan detection and reap, slice memory as a note.
      Edge-triggered with a heartbeat, state under the XDG state home
      (reuse whichever of 033/034 landed that resolver).

- [ ] T020 [US2] Full suite green: `uv run pytest -q`, with the SC-002 and
      SC-003 measurements pasted verbatim into the test files.

## Phase 3: User Story 3 — Managed Temporal is installed supervised or not at all (Priority: P2)

Chains on US2 merged.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T021 [US3] Write the managed-install case FIRST (spec US3-S1, FR-009):
      the Temporal unit and the probe timer are active, linger is enabled, and
      033's parse-time refusal of `managed` no longer fires.

- [ ] T022 [US3] Write the persistence case FIRST (spec US3-S2, SC-004): write
      workflow history, restart the unit, read it back. The prior art's comment
      is the reason this is a criterion — without the persistence flag "every
      reboot silently discards in-flight workflow history" (D-006). Paste the
      before/after verbatim.

- [ ] T023 [US3] Write the alert-while-down case FIRST (spec US3-S3, SC-001):
      the managed process killed, the probe fires, and the alert is delivered
      through US1's out-of-band path *while Temporal is still down*. This is the
      claim the epic exists for; if you cannot measure it in your environment,
      say so plainly rather than asserting it.

- [ ] T024 [US3] Write the external-mode case FIRST (spec US3-S4, FR-010): no
      unit is installed and the verify finding states that the remote server's
      uptime is the operator's contract. A silent pass is how a remote outage
      becomes a mystery.

- [ ] T025 [US3] Write the unsupported-host refusal FIRST (spec US3-S5,
      FR-011): a host without systemd user sessions refuses managed mode at
      walkthrough time naming the constraint — not half-way through unit
      installation.

### Implementation for User Story 3

- [ ] T026 [US3] Generate the Temporal server unit with persistent storage,
      inside the slice, with the same restart bound and probe coverage as US2.

- [ ] T027 [US3] Remove 033's parse-time refusal of `temporal.mode = "managed"`
      (FR-009). That refusal names this epic by number, so landing it is part of
      this story, not a follow-up.

- [ ] T028 [US3] Full suite green: `uv run pytest -q`.

## Verification

- [ ] Final gate command passes green.
- [ ] The generated unit text contains no path outside the operator's installation.
- [ ] No generated unit's command line contains `python -` (plan trap 9).
- [ ] Process counts before and after a unit stop are pasted in the diff.
- [ ] The three reaping conditions are discriminated by test, not by comment.
- [ ] Workflow history survived a managed-unit restart, with evidence.
- [ ] The probe is the one generated unit outside the slice.
