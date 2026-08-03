# Implementation Plan: Verification Gating

**Branch**: `002-verification-gating` | **Date**: 2026-08-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-verification-gating/spec.md`

## Summary

Make the factory's output trustworthy before any PR exists: a mechanical OpenSpec
criteria parser (pure Python over the stock delta grammar), a two-tier verifier —
deterministic gates from the target repo's committed `factory.yaml` first, a bounded
LLM judge (one chat completion on its own component-1 attribution key, strict
per-scenario verdict) second — plus the anti-rubber-stamp diff/artifact check, a pure
retry-ladder decision function (3 attempts → debugger → escalate, configurable), a
factory-owned SQLite verification-evidence store, and the Telegram notifier
(send-only activity + long-polling callback bridge → Temporal signals). Downstream
edges unlock only on PASS. The production loop that drives the ladder is delivered as
a documented in-workflow reference pattern; the WorkGraph interpreter component owns
running it.

## Technical Context

**Language/Version**: Python 3.11+ (D-003)

**Primary Dependencies**: `temporalio` (activity/signal surface), `httpx` (judge
chat-completion call), `pyyaml` (`factory.yaml`, persona registry),
`python-telegram-bot` (notifier, approved D-022) — all on the approved roster
(constitution III). Stdlib: `sqlite3` (evidence store), `subprocess` (gate runner),
`hashlib` (criteria drift), `json`, `argparse` not needed here. **No new
dependencies.**

**Storage**: SQLite verification-evidence store `.factory/verification.db` (WAL,
versioned schema, same single-designated-host topology as the 001 ledger); criteria
snapshots travel as small JSON-able values in workflow state. Upstream inputs: delta
spec files in the target OpenSpec workspace, `factory.yaml` in the target repo,
node worktree via `git`.

**Testing**: `pytest` + `pytest-asyncio`; parser fixture corpus under
`tests/fixtures/openspec/` covering every grammar production (SC-001);
`httpx.MockTransport` fake of the proxy's `/chat/completions` for the judge;
`temporalio.testing.ActivityEnvironment` for activities and
`WorkflowEnvironment.start_time_skipping()` for the reference retry/escalation
workflow (1h timeout without waiting an hour); fake `telegram.Bot` for message
construction and bridge handler tests; `tmp_path` git worktrees and SQLite files.

**Target Platform**: Linux worker host(s) alongside the Temporal dev server
(namespace `factory`), same host that owns `.factory/` per the 001 topology
assumption.

**Project Type**: Library package (`factory/verify/`, `factory/notify/`) + Temporal
activity surface + one runnable service module (callback bridge). No UI (the
evidence store is deliberately query-friendly for a future operations UI).

**Performance Goals**: Modest — gates bounded by per-gate timeout (default 600s);
judge ≤ 3 calls per verification cycle (1 + 2 retries, SC-003) with capped input
(60 KiB diff) and output (2000 tokens); notifier traffic is single-operator scale.

**Constraints**: No LLM anywhere in parsing or orchestration decisions
(constitution IV); judge never a CI/merge-queue check (FR-009, D-008); strict
per-scenario pass criterion (FR-003); verify against dispatch-time criteria snapshot
(FR-010); never "pass by default" on config errors; `TELEGRAM_BOT_TOKEN` and
`LITELLM_MASTER_KEY` live in worker env, read inside activities only, never in
payloads/logs (001 FR-009 discipline extended to the bot token); gate subprocesses
run with a scrubbed environment.

**Scale/Scope**: Single operator, tens of concurrent nodes, low-thousands of
verification rows per epic — SQLite comfortably sufficient.

## Constitution Check

*GATE: evaluated against constitution v2.1.0 before Phase 0; re-checked after Phase 1.*

| Principle | Status | Evidence |
|---|---|---|
| I. Build order, vertical slices | PASS | Component 2 planned after component 1's plan/tasks are approved. **Implementation must not start until 001's tests are green** (001 is specced+tasked but not yet implemented) — recorded as an explicit tasks.md prerequisite. |
| II. Test-first | PASS | Every deliverable has a test strategy (fixture corpus, fake proxy, fake bot, ActivityEnvironment, time-skipping workflow env); tasks will order tests first. |
| III. Ask before dependencies | PASS | Roster-only: `python-telegram-bot` was approved 2026-07-24 (D-022). Zero new dependency requests. |
| IV. Determinism core, LLMs edges | PASS | Parser, gate verdicts, diff check, retry ladder, drift detection: pure functions. The judge is the designated bounded LLM edge (≤3 calls, strict schema, never decides routing — its verdict is *input* to the pure ladder). All side effects (subprocess, HTTP, SQLite, Telegram) in activities. |
| V. Spend attributed, never anonymous | PASS | Judge and debugger work runs on per-attempt keys minted/torn down by component 1's activities; no unattributed LLM call exists in this component. |
| VI. No work lost | PASS (dependency noted) | 002 never deletes branches/worktrees and persists all evidence. Worktree salvage on kill is owned by the node-lifecycle owner (adapter/interpreter; mechanics preserved in spec 004) — the spec's "worktree salvaged per component 1" phrasing is a known dangling reference; this plan emits kill decisions only and does not claim salvage. |
| VII. Personas over model tiers | PASS | Judge/debugger resolved via `personas.yaml` registry; no model names in code; verifier gates are keyless/deterministic. |

**Post-Phase-1 re-check**: PASS — no design element introduced a violation;
Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-verification-gating/
├── plan.md                    # This file
├── research.md                # Phase 0 output (R1–R12)
├── data-model.md              # Phase 1 output
├── quickstart.md              # Phase 1 output
├── contracts/
│   ├── activities.md          # Temporal activity contracts (inputs/outputs/idempotency)
│   ├── factory-yaml.md        # factory.yaml schema v1 (owned by this component)
│   ├── judge.md               # judge prompt assembly + verdict JSON schema + bounds
│   ├── verification-flow.md   # reference in-workflow loop: ladder, signals, timeout
│   └── verification-store.sql # SQLite DDL (evidence store + escalations)
└── tasks.md                   # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
factory/
├── verify/
│   ├── __init__.py
│   ├── models.py              # CriteriaSet, GateResult, JudgeVerdict, VerificationResult, enums
│   ├── criteria.py            # pure: mechanical OpenSpec delta parser (fence masking, grammar)
│   ├── factory_yaml.py        # pure: factory.yaml load/validate (schema v1, R2)
│   ├── gates.py               # gate runner: bash -c in worktree, timeout, scrubbed env (R3)
│   ├── diffcheck.py           # pure decision + git-reading runner: empty-diff/artifact (R7)
│   ├── judge.py               # prompt assembly (pure) + proxy chat-completion call (R4–R6)
│   ├── ladder.py              # pure: next_action(history, config) retry-ladder decisions (R9)
│   └── store.py               # SQLite evidence store: schema, insert, escalation rows (R10)
├── notify/
│   ├── __init__.py
│   ├── messages.py            # pure: escalation text + inline keyboard construction (R11)
│   └── service.py             # runnable callback bridge: long-poll → store → Temporal signal
└── activities/
    ├── verify_activities.py   # snapshot_criteria / run_gates / check_output / run_judge / record_verification
    └── notify_activities.py   # send_escalation / expire_escalation

tests/
├── fixtures/openspec/         # delta-spec corpus: every grammar production + edge cases
├── fixtures/target_repo/      # tiny repo skeleton with factory.yaml variants
├── test_criteria.py           # parser vs corpus; validation errors; fence masking; renames
├── test_factory_yaml.py       # schema v1 acceptance/rejection; CONFIG_ERROR mapping
├── test_gates.py              # exit codes, timeout→TIMEOUT, output tail, env scrubbing
├── test_diffcheck.py          # write-scope empty-diff FAIL; read-scope artifact rules
├── test_judge.py              # prompt bounds/truncation; strict JSON parse; malformed=retry; verdict cross-check
├── test_ladder.py             # attempt caps, judge-retry cap inside total, debugger-once, escalate
├── test_verify_store.py       # DDL, WAL, inserts, escalation lifecycle, queryability
├── test_verify_activities.py  # ActivityEnvironment: snapshot+drift, record, judge-unavailable fallback
├── test_notify.py             # message/keyboard shape; callback_data ≤64B; bridge handler vs fake Bot
└── test_verification_flow.py  # time-skipping reference workflow: full ladder + 1h-timeout default kill
```

**Structure Decision**: single `factory` package per D-004 — `verify/` is the
subpackage D-004 reserved for this component; the notifier gets its own `notify/`
subpackage because component 3 reuses it for merge-queue escalations. The WorkGraph
interpreter is NOT in scope; the production retry loop ships only as the documented
pattern in `contracts/verification-flow.md` plus a test-only reference workflow
(mirroring how 001 exposes activities without owning the interpreter).

## Complexity Tracking

No constitution violations; table intentionally empty.
