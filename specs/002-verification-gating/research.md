# Phase 0 Research: Verification Gating

All unknowns from Technical Context resolved. Sources: the Spec Kit template grammar
recorded in `docs/architecture.md` §2 (D-023; fence-masked header-scan technique
inherited from the earlier Fission-AI/OpenSpec research); component 1 research
(`specs/001-usage-tracking/research.md`) for LiteLLM key/proxy mechanics and SQLite
patterns; Telegram Bot API documented limits; Temporal Python SDK testing facilities
validated in this repo's 001 plan.

## R1. Criteria input: parse Spec Kit feature-spec markdown in-factory (D-023)

**Decision**: Implement the mechanical parser in-factory over the feature spec
markdown (`specs/<feature>/spec.md`), per the Spec Kit template grammar in
architecture §2: user-story headers with priorities, numbered acceptance-scenario
items with bold Given/When/Then/And steps, and `FR-###` functional-requirement
bullets.

**Rationale**: The grammar is small and template-driven. An in-factory parser is
pure Python (testable against a fixture corpus, SC-001), imposes no extra toolchain
on worker hosts, and keeps parsing deterministic and versioned with the factory.
Spec Kit ships templates and shell scripts only — there is no upstream parser or
JSON emitter to shell out to — so the in-factory parser is the sole mechanical
path. Ergane's own `specs/` corpus provides real-world fixtures (D-024): the
factory's parser is proven against the very specs that describe it.

**Alternatives considered**: reusing Spec Kit tooling — rejected: no such parser
exists upstream. Retaining the OpenSpec delta grammar alongside — rejected: two
grammars means two parsers and two fixture corpora for no consumer; D-023 makes
Spec Kit the single input format.

## R2. `factory.yaml` schema (owned by this component)

**Decision**: Committed at the target repo root. Schema v1:

```yaml
version: 1                      # required, integer, must be 1
runtime: python:3.11-bookworm   # required, container image ref (reserved, see R3)
gates:                          # required, at least one of the three keys
  test: "uv run pytest -q"      # string, run via bash -c in the worktree
  lint: "uv run ruff check ."
  typecheck: "uv run mypy ."
timeouts:                       # optional, seconds per gate
  test: 600                     # default 600 for any gate not listed
```

Validation: unknown top-level keys rejected; empty/non-string commands rejected;
missing file or invalid schema → verification fails with a `CONFIG_ERROR` gate
result (never "pass by default", per spec edge case). Gate names are fixed
(`test`/`lint`/`typecheck`) in v1 — arbitrary extra gates are a later extension.

**Rationale**: D-009 wants deterministic declaration over auto-detection; fixed
names keep merge-queue required-check mapping (component 3) trivial.

**Alternatives considered**: free-form gate list — rejected for v1 (complicates
component 3's required-check correspondence); TOML — rejected (`pyyaml` already
approved, YAML matches `personas.yaml` house style).

## R3. Gate execution model: subprocess in worktree now, container executor later

**Decision**: v1 gate runner executes each command as `bash -c <command>` with
`cwd=<worktree>`, a per-gate timeout (R2), captured stdout+stderr (last 32 KiB
retained as evidence), and a scrubbed environment (minimal PATH/HOME; never
`LITELLM_MASTER_KEY` or `TELEGRAM_BOT_TOKEN`). Exit 0 = pass; non-zero = fail;
timeout = TIMEOUT. The runner sits behind a narrow `GateExecutor` seam;
`factory.yaml`'s `runtime` image is validated and recorded but container-isolated
execution ships with the agent-adapter/sandbox work (the component that owns node
sandboxing), not here.

**Rationale**: The verifier runs repo-declared commands in the node's already
sandboxed worktree — the sandbox boundary belongs to the node lifecycle owner, not
the gate runner. The seam keeps a `ContainerExecutor` a drop-in later without
touching verdict logic. Env scrubbing keeps SC-004-style credential hygiene inside
gate subprocesses too.

**Alternatives considered**: `docker run` per gate now — rejected: adds a Docker
dependency and image-management scope 002 doesn't need to prove verification
correctness; `shlex.split` + no shell — rejected: repo gate commands legitimately
use shell features (`&&`, env vars), and `factory.yaml` is operator-committed
config, the same trust level as CI config.

## R4. Judge invocation: one bounded chat completion via the proxy, not an agent

**Decision**: The judge is a direct LLM call, not a headless-agent launch:
`POST {proxy}/chat/completions` (OpenAI-compatible, works for every backend the
proxy fronts), `Authorization: Bearer <judge attempt key>` minted via component 1's
`issue_attempt_key` (persona `judge`, same epic/node, its own attempt counter),
`model` = the judge persona's registry alias, `temperature 0`, `max_tokens` capped
(16000 — a reasoning model's thinking is billed to the same output budget as its
verdict). Torn down via `teardown_attempt` so judge spend lands in the usage ledger
attributed to the node's spec ref.

**Rationale**: The judge's job is one scoring pass over (criteria, diff) — a full
agent adapter (worktree, session, termination classes) is machinery without
benefit. Direct calls make "max 2 judge retries" trivially enforceable, and
component 1's key lifecycle gives attribution for free (constitution V).

**Alternatives considered**: launching the `claude-code` adapter with the
code-review skill — rejected for v1: an order of magnitude more moving parts, and
D-012's "backing skill" for the judge informs the rubric content, not the
transport; reusing `factory/usage/litellm_client.py` — rejected: that client is the
master-key *admin* client; the judge call authenticates with the virtual key and
lives in `factory/verify/judge.py` on plain `httpx`.

## R5. Judge verdict format: strict JSON, malformed = judge retry

**Decision**: The judge must return a single JSON object (extracted from a fenced
block or raw body): `{"verdict": "pass|retry|fail", "scenarios": [{"scenario":
"<desc>", "pass": bool, "reasoning": "..."}], "feedback": "..."}`. Parsing is
strict (schema-validated, every dispatched scenario must appear; unknown scenarios
rejected). PASS requires every scenario `pass: true` — the overall `verdict` field
is cross-checked against the per-scenario results and the *stricter* interpretation
wins. Malformed/unparseable/incomplete responses count as one judge retry (spec
edge case); after retries exhaust, the judgment is `fail` with the parse failure as
feedback.

**Rationale**: FR-003's strict per-scenario criterion needs per-scenario structure;
cross-checking verdict vs. scenarios prevents a holistic "pass" sneaking past a
failing scenario. Counting malformed output as a retry keeps judge spend bounded
(SC-003) without ever converting garbage into a pass (SC-002).

## R6. Judge input bounds: 60 KiB diff cap, proportional per-file truncation

**Decision**: Diff input capped at 60 KiB. Over cap: truncate per file
proportionally, keeping each file's head and tail hunks, inserting an explicit
`[... N lines truncated ...]` marker; file list + stat summary always included in
full. The prompt states that truncation occurred. Criteria text is never truncated.

**Rationale**: ~15k tokens of diff fits comfortably in any cheap-tier judge model's
context alongside criteria and instructions; explicit markers stop the judge from
treating truncation as missing implementation. Criteria are the ground truth and
must arrive verbatim.

**Alternatives considered**: fail verification on oversized diffs — rejected
(punishes legitimate large nodes); embedding-based hunk selection — rejected
(nondeterministic input assembly violates the determinism ethos).

## R7. Anti-rubber-stamp mechanics: git-status-based, artifact check for read scopes

**Decision**: "Empty diff" = `git status --porcelain` empty AND `git diff HEAD`
empty in the node worktree (untracked files count as work). Write-scoped personas
(`worktree`, `docs`): empty diff → FAIL regardless of gates/judge (FR-004).
Read-scoped personas and verifier nodes: exempt from the diff check, but the node's
declared artifact — an `expected_artifacts: [<repo-relative path>, ...]` list
carried on the node — must exist and be non-empty; verifier nodes' artifact is the
recorded `VerificationResult` itself. No diff and no artifact → FAIL.

**Rationale**: Porcelain + diff-vs-HEAD catches both modified and new files
without depending on the agent having committed. Artifact paths as node data keep
the check mechanical and keep personas.yaml's shape unchanged (component 1 owns
that file's schema this cycle).

## R8. Criteria snapshot & drift: parse at dispatch, hash, re-hash at verify

**Decision**: A `snapshot_criteria` activity runs at node dispatch: parses the
feature spec for the node's spec ref, returns a `CriteriaSet` (with
`source_sha256` of the raw file bytes) into workflow state; every verification of
that node evaluates against this snapshot (FR-010). At verify time the activity
re-reads the file, recomputes the hash, and sets `criteria_drift = true` on the
result when they differ (missing file at verify time is also drift). Drift never
changes the verdict — it is flagged evidence.

**Rationale**: CriteriaSets are small (KBs) — safe in Temporal payloads; hashing
raw bytes is the cheapest reliable drift signal and avoids semantic-diff rabbit
holes. Verifying against dispatch-time criteria keeps the attempt's goalposts
fixed, per clarification.

## R9. Retry ladder: pure decision function + reference workflow pattern

**Decision**: The ladder (3 total attempts default — initial + 2 retries, any
gate/judge failure mix; judge-initiated retries ≤ 2 inside that; then one
`debugger` cycle; then escalate) is a pure function
`next_action(history, config) -> RETRY | DEBUGGER | ESCALATE | PASSED | KILLED`
over an attempt-history value, with `VerificationConfig` making the caps
configurable per deployment. The loop that *drives* it is documented as a reference
in-workflow pattern in `contracts/verification-flow.md` (and exercised by a
minimal test workflow under Temporal's time-skipping test environment) — the
WorkGraph interpreter component owns running it in production, exactly as
component 1's activities are consumed via a documented call pattern.

**Rationale**: Constitution IV — routing/retry decisions are deterministic code;
making the ladder a pure function over history makes every clarified rule (caps,
mix, debugger-once) unit-testable without Temporal. Keeping the production loop
out of scope respects the build-order boundary: 002 ships verification, not the
interpreter.

## R10. Verification evidence store: factory-owned SQLite, same pattern as 001

**Decision**: Every verification writes one row to `.factory/verification.db`
(WAL, `busy_timeout=5000`, per-invocation connections, versioned schema — the 001
ledger pattern verbatim): node, epic, attempt, verification form (phase|node),
per-gate results (JSON), diff-check outcome, judge verdict + per-scenario findings
(JSON), overall verdict, drift flag, judge-unavailable flag, timestamps.
Escalations get their own table (see R11). DDL is a published contract
(`contracts/verification-store.sql`).

**Rationale**: The spec requires escalations to carry *full failure history*
(SC-005) — a queryable store beats spelunking Temporal event history for it. It
also gives the retry-prompt builder and any future operations UI (dashboard over
ledger + verification evidence, per the 2026-08-03 direction) a stable read
surface, decided now while it is cheap. Storage stays on the designated worker
host alongside the usage ledger — same single-writer topology assumption.

**Alternatives considered**: Temporal history as the only record — rejected
(unqueryable across epics, retention-bound); adding tables to the 001 ledger DB
file — rejected (separate lifecycle/schema_version; cross-DB joins are not needed
— attribution joins happen on epic/node ids in SQL across attached DBs if ever
wanted).

## R11. Notifier: send-only activity + callback bridge service, store-backed ids

**Decision**: Two pieces, both `python-telegram-bot` (approved, D-022):

1. **`send_escalation` activity** — constructs the message (failure history
   summary + inline keyboard) and sends it directly via `telegram.Bot` using
   `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` from worker env (activities-only, like
   the master key). Before sending it inserts an escalation row (id = 12-hex
   token, workflow id, node, choices, `expires_at = now + 1h`) into the store.
   `callback_data` = `esc:<id>:<choice>` (≤ 64-byte Bot API limit by
   construction — never the workflow id itself).
2. **Callback bridge service** (`factory/notify/service.py`, runnable module) —
   long-polling `Application` with a `CallbackQueryHandler`: resolves
   `esc:<id>:<choice>` against the store, validates the choice, signals the
   workflow (`escalation_resolved(escalation_id, choice)`) via a Temporal client,
   marks the row resolved, answers the callback, and edits the message to show
   the outcome. Unknown/expired/already-resolved ids → answered with a notice, no
   signal. No public webhook (D-011).

Failure mode: if the token/chat env is absent or the send fails, the activity
returns `delivered=false`; the workflow then skips the wait and applies the
fail-safe default (kill) immediately — matching architecture §9's "log + fail
safe" interim behavior. If the bridge is down, buttons go unanswered and the 1h
timeout produces the same default.

**Rationale**: Sending must not depend on the bridge process being alive; the
store-backed escalation id survives restarts of either side, keeps callback_data
tiny, and doubles as the SC-005 audit record. Signal-by-workflow-id is the
standard Temporal external-trigger pattern (D-011).

**Alternatives considered**: one always-on bot process that both sends and
receives — rejected: puts an availability dependency in the escalation *send*
path; encoding workflow ids in callback_data — rejected: 64-byte limit makes it
fragile.

## R12. Escalation timeout: workflow-side 1h wait, then default kill

**Decision**: The reference pattern waits on the resolution signal with a 1-hour
timeout (`workflow.wait_condition(..., timeout=timedelta(hours=1))`). On timeout:
an activity marks the escalation expired in the store (and best-effort edits the
Telegram message), then the default applies — kill, per FR-008. Worktree salvage
on kill is performed by the node-lifecycle owner (adapter/interpreter; designed in
spec 004's salvage-always mechanics) — 002 emits the kill decision and preserves
all evidence, and never deletes branches or worktrees itself.

**Rationale**: Timer-in-workflow is durable across worker restarts (Temporal owns
the clock) and independent of the notifier being alive. Scoping salvage out keeps
002 inside its boundary; the plan's Constitution Check records this as a
cross-component dependency, not a gap this spec closes.
