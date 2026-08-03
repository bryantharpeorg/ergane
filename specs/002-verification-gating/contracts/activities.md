# Activity Contracts: Verification Gating

All activities live in `factory/activities/verify_activities.py` and
`factory/activities/notify_activities.py`. Credentials (`TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, and — for judge key issuance via component 1 —
`LITELLM_MASTER_KEY`) are read from the worker environment **inside activities
only** and never appear in inputs, results, logs, or error strings. Inputs/outputs
are the dataclasses of [data-model.md](../data-model.md).

Judge/debugger attribution keys are NOT minted here — the caller uses component 1's
`issue_attempt_key` / `teardown_attempt` around the judge call, per
[verification-flow.md](verification-flow.md).

## `snapshot_criteria`

| | |
|---|---|
| **Input** | `{openspec_root, change_name, capability, requirement_keys: [str], spec_ref}` |
| **Output** | `CriteriaSet` (with `source_sha256`, `snapshotted_at`) |
| **Errors** | `CRITERIA_PARSE_FAILED` (application error; validation message names the offending requirement — spec US1); `CRITERIA_FILE_MISSING` |
| **Idempotency** | Pure read + parse; safe to retry. Called once at node dispatch; the returned snapshot is workflow state for the node's lifetime (FR-010). |

## `run_gates`

| | |
|---|---|
| **Input** | `{worktree_path, factory_yaml_path, timeout_overrides?}` |
| **Output** | `list[GateResult]` — one per declared gate, in declaration order |
| **Errors** | None raised for gate failures — failures are data. Missing/malformed `factory.yaml` returns a single `CONFIG_ERROR` gate result (never pass-by-default). |
| **Semantics** | Each gate: `bash -c <command>`, `cwd=worktree`, scrubbed env (minimal PATH/HOME; no factory credentials), per-gate timeout (declared or 600s default), last 32 KiB of combined output retained. Heartbeats between gates. |
| **Idempotency** | Re-running re-executes commands (side effects are the target repo's own test suite); safe under Temporal retry. |

## `check_output`

| | |
|---|---|
| **Input** | `{worktree_path, write_scope, expected_artifacts: [str]}` |
| **Output** | `OutputCheck` |
| **Errors** | `WORKTREE_MISSING` (application error) — a vanished worktree is an infrastructure failure, not a FAIL verdict |
| **Semantics** | `git status --porcelain` + `git diff HEAD` decide `has_diff` (untracked files count); read scopes/verifier nodes check artifact existence + non-emptiness instead (R7). |
| **Idempotency** | Read-only; safe to retry. |

## `run_judge`

| | |
|---|---|
| **Input** | `{criteria: CriteriaSet, diff_text, virtual_key, proxy_url, model_alias, judge_attempt, prior_feedback?}` |
| **Output** | `JudgeVerdict` |
| **Errors** | `JUDGE_UNAVAILABLE` (application error) after in-activity HTTP retries exhaust — caller maps to gates-only fallback + notification (spec edge case). Malformed responses are NOT errors: they consume a judge attempt and, once `judge_attempt` exceeds the cap, come back as `outcome=FAIL` with the parse failure as feedback (R5). |
| **Semantics** | One `POST {proxy_url}/chat/completions`, Bearer = the judge's per-attempt virtual key (minted by the caller via component 1), `temperature 0`, `max_tokens 2000`, diff truncated per R6 with `truncated_input` flagged. Strict JSON verdict schema per [judge.md](judge.md); per-scenario coverage enforced; stricter-interpretation cross-check applied. |
| **Idempotency** | Each invocation is one judge attempt; the caller controls `judge_attempt` numbering and the ≤ 1+2 bound (SC-003). |

## `record_verification`

| | |
|---|---|
| **Input** | `VerificationResult` |
| **Output** | `{row_id}` |
| **Errors** | `ATTRIBUTION_INCOMPLETE` (application error) — empty epic/node/attempt rejected, never written |
| **Semantics** | Upserts by `(epic_id, node_id, attempt, form)` into `.factory/verification.db` (WAL; DDL per [verification-store.sql](verification-store.sql)). Also recomputes the criteria-source hash to set `criteria_drift` if the caller hasn't. |
| **Idempotency** | Upsert — re-run records once. |

## `send_escalation`

| | |
|---|---|
| **Input** | `{workflow_id, epic_id, node_id, history_summary, choices: [EscalationChoice]}` |
| **Output** | `{escalation_id, delivered: bool, expires_at}` |
| **Errors** | None for delivery failure — `delivered=false` is data (caller applies the fail-safe default immediately, R11). Store-write failure is an application error. |
| **Semantics** | Inserts the `EscalationRecord` FIRST (so a crash between insert and send leaves an expirable row, never an untracked message), then sends one Telegram message with inline buttons, `callback_data = "esc:<id>:<choice>"` (≤64 bytes by construction). Message contains the full failure history (SC-005). |
| **Idempotency** | Retry after a sent-but-unrecorded-ack crash may duplicate the message; both copies carry the same escalation id and the store accepts exactly one resolution (safe). |

## `expire_escalation`

| | |
|---|---|
| **Input** | `{escalation_id}` |
| **Output** | `{final_state}` |
| **Semantics** | Marks the row `EXPIRED` iff still pending (terminal states immutable); best-effort edits the Telegram message to show expiry. Called by the workflow on the 1h timeout path (R12). |
| **Idempotency** | State machine enforces at-most-one terminal transition. |

## Bridge service (not an activity)

`python -m factory.notify.service` — long-polling `CallbackQueryHandler`: parses
`esc:<id>:<choice>`, loads the row, validates choice ∈ `choices` and state =
pending, signals `escalation_resolved(escalation_id, choice)` on `workflow_id` via
the Temporal client, marks resolved, answers the callback, edits the message.
Unknown/expired/resolved ids → callback answered with a notice, no signal. The
service holds no state outside the store; restarts are harmless.
