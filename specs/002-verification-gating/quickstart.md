# Quickstart: Verification Gating

Validation guide proving the component works end-to-end. Prerequisites: component 1
implemented and green (constitution I), `uv sync` done. Contracts referenced here:
[activities.md](contracts/activities.md), [factory-yaml.md](contracts/factory-yaml.md),
[judge.md](contracts/judge.md), [verification-flow.md](contracts/verification-flow.md),
[verification-store.sql](contracts/verification-store.sql).

## 1. Full suite (no external services)

```bash
uv run pytest -q
```

Expected: green. Everything runs against fakes — the parser fixture corpus
(`tests/fixtures/openspec/`, every grammar production per SC-001), fake proxy
(`httpx.MockTransport` serving `/chat/completions`), fake `telegram.Bot`,
`tmp_path` git worktrees and SQLite files, and Temporal's time-skipping environment
for the reference flow (the 1h escalation timeout resolves instantly).

Key behaviors to spot-check in the output:

- `test_criteria.py` — grammar coverage incl. fence masking, RENAMED mapping,
  SHALL/MUST and zero-scenario validation errors naming the requirement.
- `test_ladder.py` — 3-attempt default, judge-retry cap inside the total,
  debugger-once, escalate; all pure, no Temporal.
- `test_judge.py` — strict per-scenario criterion, stricter-interpretation
  cross-check, malformed-response-consumes-a-retry, truncation flagging.
- `test_verification_flow.py` — SC-002 guard (no PASS with a failing gate or empty
  write-scope diff), verbatim feedback in retry prompts (SC-004), timeout →
  default kill with escalation row EXPIRED (SC-005).

## 2. Gate runner against a real repo skeleton

```bash
uv run pytest -q tests/test_gates.py -k demo
```

Runs the declared gates from `tests/fixtures/target_repo/factory.yaml` in a
temporary worktree: one passing config, one failing gate (non-zero exit → FAIL with
output tail), one hanging gate (short timeout → TIMEOUT), one missing manifest
(→ single CONFIG_ERROR result, verdict FAIL — never pass-by-default).

## 3. Live judge smoke (optional, env-gated)

```bash
LITELLM_PROXY_URL=... LITELLM_MASTER_KEY=... uv run pytest -q -m live_proxy tests/test_live_judge.py
```

Auto-skips when env is unset. Mints a real judge attempt key via component 1,
scores a tiny fixture diff against one scenario through the deployed proxy on the
judge persona's alias, tears down, and asserts (a) a structured verdict parsed, and
(b) the judge spend landed in the usage ledger attributed persona=`judge`
(constitution V).

## 4. Live Telegram smoke (optional, env-gated)

```bash
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... uv run pytest -q -m live_telegram tests/test_live_notify.py
```

Auto-skips when env is unset. Sends one real escalation message with inline
buttons, asserts `delivered=true` and a pending row in `escalations`; pressing a
button while `python -m factory.notify.service` runs resolves the row and edits
the message (manual step documented in the test's docstring).

## 5. Inspect the evidence store

```bash
sqlite3 .factory/verification.db '.schema verification_results'
sqlite3 .factory/verification.db \
  "SELECT epic_id, node_id, attempt, form, verdict, judge_unavailable, criteria_drift
   FROM verification_results ORDER BY epic_id, node_id, attempt;"
```

Expected: schema matches [verification-store.sql](contracts/verification-store.sql)
exactly (`schema_version` = 1, WAL on); rows carry full JSON evidence bundles. The
canonical rollup queries at the bottom of the DDL file should all run as-is —
that query surface is what escalation summaries (and a future operations UI)
consume.
