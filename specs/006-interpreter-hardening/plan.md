# Implementation Plan: Interpreter Hardening

**Branch**: `006-interpreter-hardening` | **Date**: 2026-08-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-interpreter-hardening/spec.md`

## Summary

Five defects the 003 crossover exposed by running the interpreter against a real epic
for the first time. The largest is a cost: the attempt loop uses
`workflow.wait_condition(..., timeout=poll_interval_s)` as a heartbeat and fires a
`poll_usage` activity on every timeout, producing **11 history events per 30 seconds** —
measured, not estimated — to maintain a value whose only consumer is a teardown
fallback on the proxy-unreachable path. This epic moves that observation onto the agent
activity's heartbeat, where Temporal stores details in mutable state rather than on the
event log, making an attempt's history cost independent of its duration (FR-001). The
other four are operator-facing: an epic naming a model alias the proxy does not serve
burns attempts instead of refusing at `start` (FR-004); an epic killed mid-attempt
cannot restart because its deterministic key alias is orphaned (FR-007); a five-second
heartbeat bound discards multi-hour attempts on any Temporal blip (FR-008); and
`factory-epic status` reports the epic's internal state while never reporting Temporal's
execution status, so it printed `RUNNING` for a workflow already `FAILED` (FR-010).

This plan is deliberately self-contained: the prompt assembler ships spec/plan/tasks
only, so every contract an implementer node needs is inlined below rather than split
into files that would never reach it.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: `temporalio`, `httpx`, `pyyaml` — all roster items, all already
in use. **This feature adds no dependency.** If a task believes it needs one, that is an
operator-approval conversation (constitution III), not a quiet `uv add`.

**Storage**: No new store. The usage snapshot moves from workflow state maintained by
polling to workflow state derived from the activity's result and its heartbeat details.
The ledger's schema is unchanged.

**Key API facts, verified against the installed SDK** — the design depends on these and
they were checked, not assumed:

- `temporalio.exceptions.TimeoutError.last_heartbeat_details` (`exceptions.py:247`)
  exposes the final heartbeat payload **to the workflow** when an activity times out.
- `temporalio.activity.Info.heartbeat_details` (`activity.py:111`) exposes it to the
  activity itself on retry.
- Heartbeat details are recorded on mutable state, **not** the workflow event log. This
  is the entire basis of FR-002; a task that verifies nothing else must verify this.
- `factory/activities/agent_activities.py:376` already passes `heartbeat=activity.heartbeat`
  into the adapter's monitor, so the adapter needs a details-carrying callable, not a
  new mechanism.

**Testing**: `pytest`, `WorkflowEnvironment.start_time_skipping()`, `ActivityEnvironment`.
Every behaviour here is provable without a live proxy or a live Temporal server.

**Project Type**: single Python package (`factory/`).

**Performance Goals**: SC-001 — a simulated four-hour attempt contributes a history event
count within a small constant of a one-minute attempt. Today: ~5,300 vs ~15.

**Constraints**: No behaviour change that any existing test asserts (SC-006). This epic
changes what things *cost* and what the operator is *told*, not what the factory decides.

## Constitution Check

- **I (test-first)**: every task pairs a failing test with its implementation, tests first.
- **III (no unapproved dependencies)**: none added; see Technical Context.
- **V (credentials)**: FR-011. The preflight in US2 reads the proxy's model list and key
  list, both of which require the master key — which the **CLI already holds** to start an
  epic. No new path gains it, and no key value may appear in a preflight message: report
  the *alias*, never the token.
- **VI (salvage)**: untouched. Nothing here alters the terminal paths.
- **VII (persona routing)**: untouched. Preflight validates aliases; it does not choose them.

## Project Structure

### Documentation (this feature)

```
specs/006-interpreter-hardening/
├── spec.md      # what and why, plus the decided heartbeat trade
├── plan.md      # this file
└── tasks.md     # dependency-ordered tasks
```

### Source Code (repository root)

```
factory/
├── workgraph/
│   ├── workflow.py     # US1: attempt loop; US4: timeout constants
│   ├── cli.py          # US2: preflight; US5: execution status
│   └── adapter.py      # US1: heartbeat carries the snapshot
├── activities/
│   ├── agent_activities.py   # US1: poll inside the attempt, heartbeat details
│   └── usage_activities.py   # US1: teardown input; US3: orphan recovery
└── usage/
    └── litellm_client.py     # US2/US3: model list, key list, key delete
tests/
├── test_interpreter.py       # US1, US4
├── test_epic_cli.py          # US2, US5
├── test_adapter.py           # US1 heartbeat details
└── test_usage_activities.py  # US3 orphan recovery
```

## Data Model (inline)

**`UsageSnapshot`** — unchanged shape, new provenance. Today it is produced by a
`poll_usage` activity the workflow schedules; here it is produced inside the agent
activity and delivered two ways.

**`AdapterResult`** gains an optional `last_snapshot: UsageSnapshot | None`. On the
normal path the attempt's final observation rides home in the activity's return value,
which the workflow already awaits — zero extra events.

**Heartbeat payload** — a single serialisable `UsageSnapshot` (or `None` before the
first successful read). It must round-trip through Temporal's data converter; a task
must assert that, because a payload that fails to serialise degrades the heartbeat into
a liveness-only beat silently.

**`TeardownInput.last_snapshot`** — unchanged field, unchanged meaning, new source. Its
docstring must be corrected: it no longer describes "the newest heartbeat read" produced
by polling, and leaving that sentence in place would be a lie the next reader inherits.

**`PreflightFinding`** — `check: str`, `passed: bool`, `detail: str`. Deliberately the
same shape as 003's onboarding `Finding`; **reuse that type if 003 has landed it**, and
only define a local one if it genuinely is not importable. Two near-identical finding
types in one codebase is the defect this note exists to prevent.

**`EpicStatus`** — unchanged. US5 adds execution status at the **CLI** layer, not to the
query payload: the workflow cannot know its own Temporal execution status, and inventing
a field it would have to guess at is worse than reporting what the client already knows.

## Approach by story

### US1 — the attempt's history cost stops growing (FR-001, 002, 003)

The loop at `workflow.py:819-829` becomes a plain `await agent`, plus the kill check it
already performs. The timer and the per-interval `poll_usage` activity both disappear.

Observation moves inside `run_agent_attempt`. The activity already runs a monitor loop
beating once a second (`adapter.py`, `DEFAULT_HEARTBEAT_INTERVAL_S`); it gains a much
slower usage read — every `poll_interval_s`, unchanged in *frequency of proxy reads*,
which is not the cost being removed. Each beat carries the newest snapshot as heartbeat
details. The proxy round trip must never block or fail the beat: a failed read leaves the
previous snapshot in place and the beat still fires, because liveness and spend are now
sharing one channel and spend must never be able to kill liveness.

Delivery to teardown, all three paths:

1. **Normal completion** — the snapshot is a field on the returned `AdapterResult`.
2. **Timeout** — the workflow reads `TimeoutError.last_heartbeat_details` off the
   `ActivityError` it already catches.
3. **Kill** — **decided by the operator 2026-08-06, superseding this plan's earlier
   text, after attempt 1 verified the concern and stopped on it**: do NOT rely on
   reading heartbeat details off a cancelled activity's error — that mechanism is
   unverified for the cancel path in the installed SDK. Instead the adapter catches
   the cancellation and **returns** a KILLED `AdapterResult` carrying the final
   snapshot — the same channel as normal completion. `_cancel` awaits that result
   and hands its snapshot to teardown instead of swallowing an error; the attempt's
   termination class still reads KILLED, and the kill-path test asserts a non-NULL
   spend delivered via the returned result. Verify the exact catch-and-return
   mechanics against the installed SDK as part of T005(c), as was done for the
   normal and timeout paths.

`poll_usage` stays a registered activity — 001 owns it and the judge path has no poller —
but the workflow no longer schedules it per interval.

**S4's mechanism — mid-attempt visibility moves to the CLI (decided by the
operator 2026-08-07, after attempt 2's RETRY on exactly this)**: deleting the
poll deletes the only thing that updated `record.last_snapshot` mid-attempt, so
US1-S4 needs a replacement, and the replacement must not reintroduce history
events. Do NOT try to read heartbeat details from inside the workflow —
`workflow.info()` has no pending-activity accessor in the installed SDK
(verified 2026-08-07; attempt 2's judge feedback suggested
`workflow.info().pending_activity_info()`, which does not exist). The mechanism
is the US5 pattern one step further: `status_command` already holds a client and
a workflow handle, and `describe()`'s
`raw_description.pending_activities[*].heartbeat_details` carries the newest
`UsageSnapshot` payload the adapter publishes on every beat (field verified
against the installed SDK; the CLI's client decodes it with its data converter —
T004 already proves the payload round-trips). The CLI merges it into both
renderings beside the epic's internal state; the query payload stays a dump
(US5's sibling-key discipline). Zero history events, zero workflow change.

**The trap**: `_teardown` is reached from several call sites (`workflow.py:717`, `:746`)
that each pass `record.last_snapshot`. If any path stops populating that field, teardown
silently records NULL and the ledger quietly loses a dollar figure — a regression no
existing test would catch, because today's tests assert on a polled value. A task must
assert a non-NULL spend on **each** of the three paths independently.

### US2 — an epic that cannot succeed never starts (FR-004, 005, 006)

`start_command` gains a preflight before it starts the workflow, in the same spirit as
the structural re-validation already there: "a graph that fails them never becomes a
workflow that has to be killed."

Two checks, both read-only:

- **Model aliases**: `GET /v1/models`, compare against every `model` and `fallback` the
  resolved registry names. Report each unserved alias *with the persona naming it* —
  "`anthropic/claude-opus-5` (implementer, architect, debugger, researcher)" is
  actionable; a bare alias is not. A proxy that does not answer is a **distinct** finding
  naming the address tried (FR-005), never silently a pass.
- **Key aliases**: `GET /key/list`, compare against the aliases the epic's first attempts
  will mint (`<epic>:<node>:1:<persona>`). Any hit is reported with its remedy.

**The honesty constraint (spec Edge Cases)**: the CLI resolves personas from *its* working
directory; the worker resolves from its own `personas.yaml` (R8, deliberate). Preflight
therefore reduces a class of failure and cannot eliminate it, and its output must not
claim otherwise. Word findings as facts about what was checked.

Exit codes follow the existing contract: `1` for something the operator must fix, `2` for
a service that is not answering.

### US3 — a killed epic restarts without hand-cleaning credentials (FR-007)

Issuance gains recovery on alias collision, in `issue_attempt_key`. The distinction that
makes it safe: an alias belonging to a **dead** epic may be reclaimed; one belonging to a
**live** epic must not be touched. Nothing in the alias itself says which.

The workflow-id is the discriminator. `epic-<epic_id>` is the epic's identity, and
Temporal knows whether that workflow is open. An orphan is an alias whose epic's workflow
is closed. If that determination cannot be made — Temporal unreachable — issuance must
**refuse**, not guess: deleting a live epic's key mid-attempt would break a running node
to fix a stopped one.

Reclaim is delete-then-reissue, and the dead run's ledger row is already written and
immutable, so its spend stays attributable (FR-011 / acceptance 2). A task must assert
that the reclaimed alias's historical spend is still queryable afterwards.

### US4 — transient infrastructure does not discard hours (FR-008, 009)

`_AGENT_HEARTBEAT_TIMEOUT = timedelta(seconds=5 * HEARTBEAT_INTERVAL_S)` becomes a
function of the attempt's own timeout, floored so a short attempt keeps a sane bound.
The existing comment derives 5 beats from "the slack a healthy attempt on a busy worker
needs" — that reasoning was about a *busy worker*, never about a Temporal outage, and the
replacement's comment must say what it is actually protecting against.

Liveness detection must survive: a genuinely dead agent is still detected, just later
(acceptance 2). The bound loosens; it does not vanish.

Issuance retry (`_RETRIES`) gains a budget measured against a real proxy restart rather
than seconds. Note `_CREDENTIAL_REJECTED = {401, 403}` is correct and must stay — a
rejected credential is a misconfiguration, and retrying it for minutes only delays the
diagnosis.

### US5 — the operator surface reports what is true (FR-010, 011)

`status_command` already holds a client and a workflow handle. `describe()` yields the
execution status; report it alongside the epic's internal state, in both renderings.

`--json` is documented as "a dump, never a re-assembly" — the query payload is printed as
it arrived so that `EpicStatus` is stated in exactly one place. Adding execution status
therefore means adding a **sibling** key, not merging into the query's document: the
existing payload must remain byte-identical under its own key so no consumer breaks.

FR-011's sweep belongs here as the epic's last task: assert no credential value reaches
any preflight finding, status output, or error path.

## Complexity Tracking

| Risk | Why it is real | Mitigation |
|---|---|---|
| Teardown silently records NULL | Three delivery paths, one shared field; no current test asserts non-NULL per path | Per-path assertions before US1's implementation task |
| Heartbeat payload fails to serialise | Would silently degrade to liveness-only | Explicit round-trip test through the data converter |
| Orphan recovery deletes a live key | Two epics, one alias, no local disambiguator | Workflow-open check; refuse when undeterminable |
| Preflight overclaims | CLI registry ≠ worker registry by design (R8) | Wording constraint stated in US2; asserted in tests |
| US1 and US4 both edit the attempt loop | Merge conflict between sibling nodes | `us4 depends_on us1` in the Work Graph |
