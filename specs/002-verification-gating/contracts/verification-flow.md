# Contract: Reference Verification Flow (in-workflow pattern)

002 ships activities + pure decision functions. The production loop belongs to the
WorkGraph interpreter component; this contract is the pattern it must follow, and a
test-only reference workflow (`tests/test_verification_flow.py`) proves the pattern
under Temporal's time-skipping environment. This mirrors how component 1 documents
its activity call pattern without owning the interpreter.

## Node attempt lifecycle (verification as a phase)

```text
dispatch:
  criteria = snapshot_criteria(...)              # once per node (FR-010)
  history = []

attempt loop (attempt = 1, 2, ...):
  # agent runs here (component 1 key lifecycle around the agent activity)
  gates   = run_gates(worktree, factory_yaml)
  output  = check_output(worktree, persona.write_scope, node.expected_artifacts)
  judge   = None
  if all gates PASS and output.passed and criteria.has_scenarios:
      for judge_attempt in 1 .. (1 + config.max_judge_retries):
          key = issue_attempt_key(persona=judge, ...)          # component 1
          judge = run_judge(criteria, diff, key, judge_attempt,
                            prior_feedback=judge.feedback if retrying)
          teardown_attempt(key, ...)                           # component 1
          break unless judge.outcome == RETRY (or malformed-retry)
  result = compose VerificationResult (verdict truth table, data-model.md)
  record_verification(result)
  history.append(AttemptRecord(...))

  action = next_action(history, config)          # PURE — factory/verify/ladder.py
  match action:
    PASSED   -> unlock downstream edges (FR-005); done
    RETRY    -> build retry prompt with gate output_tails + judge.feedback
                VERBATIM (FR-006, SC-004); next attempt (new component-1 key)
    DEBUGGER -> one debugger-persona cycle (fresh key, SAME worktree), then verify
                again; its attempt joins history
    ESCALATE -> escalation sequence below
```

## Explicit verifier nodes (`VerificationForm.NODE`)

Same `run_gates` / `run_judge` / `record_verification` activities and the same
verdict model; criteria may span multiple upstream requirements (fan-in). Exempt
from the diff check; its declared artifact is the recorded `VerificationResult`
(FR-004). Downstream edges gate on its PASS like any node.

## Escalation sequence (FR-008, R11, R12)

```text
esc = send_escalation(workflow_id, epic, node, history_summary,
                      choices=[RETRY, KILL, PAUSE_EPIC])
if not esc.delivered:
    apply default (KILL) immediately            # fail-safe, notifier down/unset
else:
    try:
        choice = wait for signal escalation_resolved(esc.escalation_id, ...)
                 with timeout = 1h
    except timeout:
        expire_escalation(esc.escalation_id)
        choice = KILL                            # default (FR-008)

match choice:
  RETRY      -> grant one more attempt (history noted; ladder allows exactly one
                post-escalation retry per escalation)
  KILL       -> node FAILED/KILLED; downstream stays locked; branch/worktree
                preserved — salvage is performed by the node-lifecycle owner
                (adapter/interpreter; spec 004 mechanics), never by 002
  PAUSE_EPIC -> interpreter suspends releasing new nodes in this epic until a
                resume signal; this node parks as FAILED-pending-operator
```

## Signals

| signal | payload | sender |
|---|---|---|
| `escalation_resolved` | `{escalation_id, choice}` | notify bridge service (`factory/notify/service.py`) |

The workflow validates `escalation_id` matches the pending escalation (stale or
duplicate signals are ignored — the store enforces at-most-one resolution on the
sender side too).

## Invariants the interpreter must honor

1. Never unlock a downstream edge on anything but `OverallVerdict.PASS` (FR-005).
2. Never invoke the judge unless every deterministic gate passed (FR-003).
3. Always `record_verification` before acting on a result — the evidence store is
   written even when the node is about to be killed (SC-005 history).
4. Retry prompts carry prior failure evidence verbatim, not summarized (FR-006).
5. Criteria come from the dispatch snapshot; drift is flagged, never re-snapshotted
   mid-node (FR-010).
6. Judge/debugger work always runs inside component 1's key lifecycle
   (constitution V).
