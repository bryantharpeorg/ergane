# Implementation Plan: each Codex attempt owns its evidence

## Current seams and source contract

- `factory/workgraph/adapter.py:1873` — `CodexAdapter` currently launches ordinary output and discovers rollouts in a persistent node home.
- `factory/workgraph/adapter.py:2066` — `CodexAdapter._turn_happened` accepts any rollout found by `factory/workgraph/adapter.py:2143` — `_codex_rollouts`.
- `factory/workgraph/adapter.py:1165` — `SharedAttemptPolicy` owns launch, monitoring, archival, and neutral result construction; keep per-CLI decoding behind this seam.
- `factory/workgraph/adapter.py:300` — `AgentInvocation`, `factory/workgraph/adapter.py:357` — `HostAgentBackend`, and `factory/workgraph/adapter.py:388` — `BwrapBackend` currently expose one combined `log` and route stderr into stdout; Codex JSONL cannot use that contract unchanged.
- `factory/activities/agent_activities.py:598` — `_classify_auth_failure` scans combined output substrings and reconstructs the result at line 629.
- `factory/workgraph/models.py` defines `AdapterResult`, the compatibility boundary for workflow consumers.
- `factory/activities/usage_activities.py:581` — `_record_for` currently writes subscription unknowns honestly.
- Official source: https://learn.chatgpt.com/docs/non-interactive-mode . With `--json`, stdout is JSONL; documented events include thread/turn/item/error types, item subtypes, and turn usage. Plain mode reserves stdout for the final message.

### Measured CLI contract, not an invented error schema

[The installed-CLI qualification](../../docs/codex-jsonl-contract-qualification-2026-09-10.md)
records Codex0.154.0 against a credential-free synthetic peer in an isolated
network namespace. Use its measured shapes for offline fixtures. A401 or
missing provider key still emits thread/turn starts without model-authored
activity; an invalid provider configuration exits before any JSONL. Protocol
startup and Ergane's `agent_took_a_turn` are distinct facts.

The first US1 candidate, PR 529 at
`729272cac2462ae4dd0535acf918f74be61bf807`, passed its factory gate and judge
but failed two exact-head qualification probes on 2026-09-12. An otherwise
valid stream containing `{"type":"item.completed","item":"bad"}` completed
with no diagnostic, and `{"input_tokens":true,"output_tokens":2}` published
`True` as the input-token count. Those are retry requirements, not merely review
notes: the decoder must validate the body of every known event and must interpret
JSON types rather than Python's `bool`-is-an-`int` inheritance.

The measured top-level error and matching `turn.failed.error` contain a
`message`, not a separate numeric HTTP status. Normalize only recognized fatal
message forms inside current typed error evidence; do not invent a required
status field or search arbitrary text for401. A400 response can wrap a quoted
401 inside its non-authentication error body. Preserve it as an ordinary
failure. Diagnostic `item.completed`/`item.type=error` also occurs before the
request and is not a fatal-auth event. A matching error/failed pair describes
one failure, not two terminals, refusals, or spent attempts. Normal item events
need not repeat the initial thread identifier; conflicting explicit identities
remain invalid. Retain raw events locally, not in committed evidence.

## Proposed interfaces

Add `factory/workgraph/codex_events.py` with a streaming decoder that accepts raw
bytes/lines and returns `CodexExecutionEvidence`. It is pure except for a caller-
owned bounded raw spool. Evidence contains thread id, whether a current turn
started, terminal outcome, ordered agent messages, final message, fatal events,
usage, completeness, and decoder diagnostics. It exposes no generic dicts to
workflow code.

The Codex CLI runs with `--json`. An adapter-selected invocation output policy
creates mode-`0600` `codex-events.jsonl` for stdout and `codex-stderr.log` for
diagnostics inside the current attempt archive before launch; both production
backends honor the two sinks. Claude selects its existing combined-log policy.
Declared size/retention values govern the raw files, and reaching either marks
evidence incomplete rather than silently dropping provenance. The invocation's
start marker and decoder, not modification times in the persistent home,
establish ownership. Rollout files may remain secondary raw artifacts when their
current thread id is proven; they are never the turn predicate.

Authentication and question classifiers accept typed evidence. Plain neutral
fields are derived once from the current final agent message. Usage normalization
produces an optional corroboration record; the existing LiteLLM aggregation stays
authoritative for gateway attempts.

## Story slices

### US1 — Pure decoder

Implement official-shape fixtures before CLI integration. Preserve unknown lines
and partial known evidence. Bound orchestration fields separately from the raw
host archive.

### US2 — Launch and archive integration

Switch Codex invocation to JSONL and allocate separate stdout-event/stderr-
diagnostic spools before process launch. Extend both production backends through
an adapter-selected output policy and preserve Claude's combined behavior.
Archive exactly the current stream on all termination paths. Populate the neutral
result without exposing raw events to existing consumers, git, workflows, or
public evidence.

### US3 — Typed classification

Move auth and question decisions onto evidence types and current final messages.
Replace manual result reconstruction with a field-preserving helper or immutable
replacement operation so adding a new field cannot be silently dropped.

### US4 — Usage corroboration

Map documented usage fields with explicit provenance/completeness. Extend storage
only as required to distinguish CLI evidence from gateway attribution. Do not
derive dollar value from subscription tokens.

## Traps

1. **A rollout directory belongs to a node, not an attempt.** Its existence is not current identity.
2. **An error event is not an agent message.** Error-only runs took no model-authored turn for Ergane's purposes.
3. **Unknown events are forward compatibility, not success.** Archive and mark incomplete.
4. **Combined stdout/stderr destroys event classes.** Parse JSONL before rendering diagnostics.
5. **Quoted markers are ordinary text.** Only the typed source and final-message position grant meaning.
6. **Result reconstruction drops fields.** Preserve all existing neutral-result fields and future additions automatically; do not require future 159 owner/generation fields before gateway evidence can be implemented.
7. **Cancellation may end mid-line.** Keep raw bytes and mark the decoder incomplete.
8. **A retry of archival is not a second attempt.** Paths and records remain idempotent.
9. **Gateway tokens have an attribution owner already.** JSONL is corroboration, not an amount to add.
10. **Subscription dollars are unavailable.** Do not calculate implied plan cost.
11. **Raw evidence can contain secrets.** Keep it mode `0600` and host-local; never copy it to git, workflows, or public qualification artifacts; redact orchestration fields and fixtures.
12. **Claude is the conformance control.** No Claude event parser or question behavior changes.
13. **Final-message output is a compatibility value.** Existing question and transcript consumers must never receive raw JSONL.
14. **Stderr is not JSONL.** Both production backends currently combine it with stdout, so the invocation seam must change before decoding.
15. **Protocol startup is not model activity.** A current thread/turn start can precede a local missing-key failure with zero HTTP requests; retain identity without setting `agent_took_a_turn`.
16. **A typed error can quote another error.** A non-authentication fatal body containing401 remains non-authentication; recognizing the event family is necessary but not sufficient.
17. **A known envelope does not validate its body.** `item.started` and `item.completed` with a non-object `item` are malformed current events, not no-ops; retain them raw, emit a stable diagnostic, and mark evidence incomplete/invalid.
18. **JSON booleans are not token counts.** Python accepts `isinstance(True, int)`, so usage validation must require an actual non-negative JSON integer (`type(value) is int` or an equivalent strict check) before publishing any count. Wrong-shaped, negative, or fractional counts remain unknown and make completeness false with a stable reason.

## Verification

Use fake processes and official-shape fixtures for all implementation stories.
Exercise persistent homes, malformed streams, cancellation, and result-field
round trips. Run 154/155 adapter and question tests as regressions, the usage
suite, then the declared full gate. Sweep committed fixtures and rendered errors
for credential patterns.
