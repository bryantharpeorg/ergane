# Contract: EpicWorkflow (the interpreter)

Owned by `factory/workgraph/workflow.py`. FR-001, FR-003, FR-004, FR-008, FR-012;
US1, US3. One generic workflow — namespace `factory`, task queue `workgraph`,
workflow id `epic-<epic_id>` — whose logic is fixed and whose behavior comes
entirely from WorkGraph data (D-002). All side effects in activities; workflow
code makes pure decisions (constitution IV). This contract *composes*
`specs/002-verification-gating/contracts/verification-flow.md`; its six
invariants are inherited unchanged.

## Main loop (sequential, R10)

```text
validate graph via resolve_graph                    # FR-002; reject → workflow fails, nothing dispatched
loop:
  if kill_requested: break to kill sequence
  if paused: await resume/kill signal
  node = first node in declaration order with state PENDING
         and all depends_on PASSED                  # FR-003, SC-002
  if node is None:
    if any node non-terminal: mark those whose deps can never pass KILLED? — no:
      a node whose dependency reached FAILED/KILLED is marked KILLED (never
      dispatched, "dependent nodes never dispatch", US1-S3) at the moment the
      dependency went terminal; so None ⇒ all terminal → epic COMPLETED
  else: run node lifecycle below
```

## Node lifecycle (composes 002's reference flow)

```text
criteria = snapshot_criteria(...)                   # once per node (002 FR-010)
worktree = prepare_worktree(...)                    # once per node (FR-013)
attempt loop:
  attempt += 1
  prompt  = build_attempt_prompt(...)               # pure, R9; retry evidence from attempt 2
  lease   = issue_attempt_key(models=resolved.models, ...)   # state KEY_ISSUED (FR-004)
  state RUNNING:
    run_agent_attempt(AttemptContext) ∥ poll loop   # adapter.md; ~30s timer → poll_usage,
                                                    # retain last_snapshot (R3)
  state VERIFYING:
    gates/output/judge per verification-flow.md     # judge on its own 001 key lifecycle
    result = compose_result(...); record_verification(result)
  teardown_attempt(lease, termination, last_snapshot)        # FR-004 bracket closes
  history.append(AttemptRecord(...))
  action = next_action(history, config, escalations=...)     # PURE (002 ladder)
  PASSED   → salvage, remove_worktree, node PASSED; unlock dependents
  RETRY    → next attempt (same worktree, evidence verbatim)
  DEBUGGER → one debugger-persona attempt (same worktree, fresh key), then verify again
  ESCALATE → escalation sequence per verification-flow.md;
             RETRY grants one attempt; KILL/EXPIRED → salvage, remove, node KILLED;
             PAUSE_EPIC → salvage, remove, node FAILED (parked) + epic paused
```

Adapter termination feeds `teardown_attempt` and the evidence trail; it never
shortcuts verification — even a TIMEOUT/AGENT_ERROR attempt runs the gates (the
worktree may hold salvageable partial work, and FR-012 forbids trusting any agent
signal in either direction). A node PASSES **only** through 002's ladder.

## Signals (FR-008)

| signal | payload | sender | semantics |
|---|---|---|---|
| `pause_epic` | — | operator / Telegram PAUSE_EPIC | no new node dispatch; in-flight node completes its ladder (R10) |
| `resume_epic` | — | operator | clears paused; loop continues |
| `kill_epic` | — | operator | cancel in-flight attempt (adapter KILLED path), salvage, teardown, every non-terminal node KILLED, epic KILLED (US3-S3) |
| `escalation_resolved` | `{escalation_id, choice}` | notify bridge (`factory.notify.service.SIGNAL_NAME`) | routed to the owning node's pending escalation; stale/unknown ids ignored (002 contract) |

Kill is the one path that interrupts an attempt: cancellation propagates to
`run_agent_attempt`, whose KILLED path still archives the transcript; the workflow
then salvages and tears down before terminating (US3-S3's ordering).

## Query

`epic_status → {epic_state, nodes: {node_id: {state, attempt, branch}}}` — the
CLI's read surface (FR-009). Queries are read-only over workflow state; no
activity runs.

## Replay determinism (US1-S4, SC-001)

- All side effects in activities; replay re-dispatches nothing (Temporal replays
  recorded results). No key is double-issued *by workflow logic*: issuance happens
  exactly once per attempt number; an activity-level retry after an unrecorded
  completion is bounded by the key TTL backstop (001 R5) and lands on the same
  `key_alias`, upserting one ledger row.
- Randomness only via `workflow.uuid4()` (session ids); time only via workflow
  timers; the poll loop is timer-driven, not wall-clock reads.
- Pause durability is replay itself (R1) — no store involvement.
- Scheduling order is a pure function of graph declaration order and node states.

## Success-criteria mapping

| SC | where asserted |
|---|---|
| SC-001 | `test_interpreter.py`: scripted 3-node graph (chain + leaf), exact transition/unlock/attempt script, replay test |
| SC-002 | same suite: dependency gating holds on failure and kill paths |
| SC-003 | scripted activities record every issue/teardown + verification pair; asserted per attempt |
| SC-004 | terminal paths assert salvage commit + archived transcript per attempt |
| SC-005 | live Tier 1 rehearsal (`test_live_epic.py`) + the 003 crossover itself |
