# Data Model: Verification Gating

Frozen dataclasses in `factory/verify/models.py` unless noted. All values are
JSON-serializable (they travel through Temporal payloads and into the SQLite
evidence store). Enums are string-valued.

## Enums

| Enum | Values | Notes |
|---|---|---|
| `RequirementKind` | `STORY` \| `FUNCTIONAL` | user story (`US<n>`, carries scenarios) vs functional requirement (`FR-###`, declarative) — D-023 |
| `GateStatus` | `PASS` \| `FAIL` \| `TIMEOUT` \| `CONFIG_ERROR` | `CONFIG_ERROR` = missing/malformed `factory.yaml` (never pass-by-default) |
| `JudgeOutcome` | `PASS` \| `RETRY` \| `FAIL` \| `UNAVAILABLE` | `UNAVAILABLE` = model/backend down after retries (spec edge case) |
| `OverallVerdict` | `PASS` \| `FAIL` | the only two values that exist for edge unlocking (FR-005) |
| `VerificationForm` | `PHASE` \| `NODE` | built-in attempt phase vs explicit verifier node (FR-002) |
| `NextAction` | `PASSED` \| `RETRY` \| `DEBUGGER` \| `ESCALATE` \| `KILLED` | output of the pure ladder function |
| `EscalationChoice` | `RETRY` \| `KILL` \| `PAUSE_EPIC` | maps 1:1 to inline buttons (FR-008) |

## Criteria entities (parser output — pure, snapshot-able)

### `Scenario`

| field | type | rules |
|---|---|---|
| `scenario_id` | str | `US<n>-S<k>` — story key + 1-based position in its `**Acceptance Scenarios**:` list; the identity the judge must echo |
| `steps` | list[str] | the bold **Given/When/Then/And** segments of the numbered item, captured verbatim in order |
| `raw_text` | str | the full numbered list item, verbatim (fence-masked scan) |

### `Requirement`

| field | type | rules |
|---|---|---|
| `key` | str | `US<n>` (story) or `FR-###` (functional) — the identity key; duplicates → error |
| `kind` | RequirementKind | STORY from `### User Story <n> - <title> (Priority: P<m>)`; FUNCTIONAL from `- **FR-###**:` bullets |
| `title` | str \| None | story title text; None for FUNCTIONAL |
| `priority` | str \| None | `P<m>` from the story header; None for FUNCTIONAL |
| `body` | str | story narrative, or the FR bullet text — FUNCTIONAL bodies MUST contain `SHALL` or `MUST` (validation error otherwise, naming the requirement) |
| `scenarios` | list[Scenario] | MUST be non-empty for STORY (validation error otherwise); always empty for FUNCTIONAL |

### `CriteriaSet`

| field | type | rules |
|---|---|---|
| `feature` | str | spec directory name (e.g. `002-verification-gating`) |
| `spec_ref` | str | opaque work-attribution key (matches the node's, component 1) |
| `requirements` | list[Requirement] | filtered to the node's requested requirement key(s) |
| `source_path` | str | the `specs/<feature>/spec.md` path parsed |
| `source_sha256` | str | hash of raw file bytes at snapshot time (drift detection, R8) |
| `snapshotted_at` | str (ISO-8601 UTC) | dispatch time |

**Validation rules** (Spec Kit template semantics, spec US1 / D-023): user story with
zero acceptance scenarios → error naming it; FUNCTIONAL requirement without
SHALL/MUST → error naming it; scenario item with no bold keyword steps → error;
duplicate requirement keys → error; requested requirement key absent from the spec →
error naming the missing key; headers and FR-like bullets inside fenced code blocks
ignored.

## Gate entities

### `FactoryConfig` (from `factory.yaml`, schema v1 — see contracts/factory-yaml.md)

| field | type | rules |
|---|---|---|
| `version` | int | must be `1` |
| `runtime` | str | container image ref; recorded, execution-reserved (R3) |
| `gates` | dict[str, str] | keys ⊆ {`test`,`lint`,`typecheck`}, ≥1 entry, non-empty commands |
| `timeouts` | dict[str, int] | per-gate seconds; default 600 |

### `GateResult`

| field | type | rules |
|---|---|---|
| `name` | str | `test` \| `lint` \| `typecheck` (or `config` for CONFIG_ERROR) |
| `command` | str | as declared |
| `status` | GateStatus | exit 0 → PASS; non-zero → FAIL; deadline → TIMEOUT |
| `exit_code` | int \| None | None on TIMEOUT/CONFIG_ERROR |
| `duration_s` | float | wall time |
| `output_tail` | str | last ≤32 KiB combined stdout+stderr (retry evidence) |

## Diff/artifact entities

### `OutputCheck`

| field | type | rules |
|---|---|---|
| `write_scope` | str | persona's scope: `worktree` \| `docs` \| `read` |
| `has_diff` | bool | `git status --porcelain` or `git diff HEAD` non-empty (untracked counts) |
| `expected_artifacts` | list[str] | node-declared repo-relative paths (read scopes; may be empty for write scopes) |
| `artifacts_present` | bool \| None | all expected artifacts exist non-empty; None when not applicable |
| `passed` | bool | write scope: `has_diff`; read scope/verifier: `artifacts_present`; never both-absent (FR-004) |

## Judge entities

### `JudgeScenarioFinding`

| field | type | rules |
|---|---|---|
| `scenario` | str | must match a dispatched `scenario_id` exactly |
| `passed` | bool | strict per-scenario criterion (FR-003) |
| `reasoning` | str | judge's stated reasoning |

### `JudgeVerdict`

| field | type | rules |
|---|---|---|
| `outcome` | JudgeOutcome | cross-checked: any finding `passed=false` forces RETRY/FAIL — stricter interpretation wins (R5) |
| `findings` | list[JudgeScenarioFinding] | must cover every dispatched scenario |
| `feedback` | str | verbatim payload for the retry prompt; failing scenarios cited by name |
| `judge_attempt` | int | 1-based; ≤ 1 + judge_retry cap |
| `truncated_input` | bool | diff truncation flag (R6) |
| `model_alias` | str | persona registry alias used (never a hardcoded model) |

## Composition

### `VerificationResult`

| field | type | rules |
|---|---|---|
| `epic_id` / `node_id` / `attempt` | str / str / int | attribution dimensions (match component 1) |
| `form` | VerificationForm | phase or explicit verifier node |
| `gate_results` | list[GateResult] | all declared gates run and recorded (FR-002); judge skipped unless all PASS |
| `output_check` | OutputCheck | anti-rubber-stamp result |
| `judge` | JudgeVerdict \| None | None when gates failed (cheapest-first) or node has no scenarios |
| `verdict` | OverallVerdict | PASS iff gates all PASS ∧ output_check.passed ∧ judge outcome ∈ {PASS, UNAVAILABLE} |
| `judge_unavailable` | bool | True → verdict fell back to gates-only + operator notification (spec edge case) |
| `criteria_drift` | bool | dispatch-snapshot hash ≠ verify-time hash (FR-010); flags, never changes verdict |
| `started_at` / `finished_at` | str (ISO-8601 UTC) | |

**Verdict truth table** (SC-002 guard): any gate FAIL/TIMEOUT/CONFIG_ERROR → FAIL;
`output_check.passed = false` → FAIL; judge FAIL/RETRY → FAIL (RETRY distinguishes
ladder handling, not the verdict); all gates PASS + output ok + judge PASS → PASS;
all gates PASS + output ok + judge UNAVAILABLE → PASS with `judge_unavailable=true`
and notification.

## Ladder entities (pure)

### `VerificationConfig`

| field | type | default |
|---|---|---|
| `max_attempts` | int | 3 (initial + 2 retries, any failure mix) |
| `max_judge_retries` | int | 2 (within max_attempts) |
| `debugger_cycles` | int | 1 |
| `gate_timeout_s` | int | 600 (overridable per gate via factory.yaml) |
| `escalation_timeout_s` | int | 3600 |

### `AttemptRecord` / ladder input

`history: list[AttemptRecord]` where each record carries `attempt`, `persona`,
`verdict`, `judge_outcome | None`. Pure function
`next_action(history, config) -> NextAction`:

- last verdict PASS → `PASSED`
- attempts < max_attempts → `RETRY` (judge-RETRY outcomes also bounded by
  `max_judge_retries` — exhausted judge retries consume attempts as failures)
- attempts exhausted, no debugger cycle used → `DEBUGGER`
- debugger cycle used and failed → `ESCALATE`
- escalation resolved KILL or timed out → `KILLED`

## Escalation entities

### `EscalationRecord` (store row, R11)

| field | type | rules |
|---|---|---|
| `escalation_id` | str | 12-hex token; key of `callback_data` (`esc:<id>:<choice>`, ≤64 bytes) |
| `workflow_id` / `epic_id` / `node_id` | str | signal routing + attribution |
| `choices` | list[EscalationChoice] | rendered as inline buttons |
| `history_summary` | str | full failure history text included in the message (SC-005) |
| `sent_at` / `expires_at` | str (ISO-8601 UTC) | expires = sent + 1h |
| `delivered` | bool | False → workflow skips wait, applies default kill (R11) |
| `resolution` | EscalationChoice \| `EXPIRED` \| None | None while pending |
| `resolved_at` | str \| None | |

**State transitions**: `pending → resolved(choice)` (bridge signal, exactly once —
later button presses answered "already resolved", no signal) or `pending → expired`
(workflow timeout path). Terminal states are immutable.

## Storage

`.factory/verification.db` — tables `verification_results` and `escalations`,
DDL in [contracts/verification-store.sql](contracts/verification-store.sql):
WAL mode, `busy_timeout=5000`, `schema_version = 1`, one connection per activity
invocation, single-INSERT transactions (the 001 ledger pattern). Nested structures
(gate results, findings) stored as JSON text columns with generated columns for
the hot query keys.
