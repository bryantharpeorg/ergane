# Ergane Constitution

Ergane is an agentic software factory: it turns OpenSpec change proposals into merged,
verified code by dispatching headless coding agents through an orchestrated DAG, with
hard per-node budgets, mechanical acceptance-criteria verification, and merge-queue
discipline. The full decision log lives in `docs/decisions.md` (D-001…D-021); this
constitution distills the non-negotiables that every spec, plan, and implementation
must honor.

## Core Principles

### I. Strict Build Order, Vertical Slices (NON-NEGOTIABLE)

Components are built in this order: (1) per-node usage tracking, (2) verification
gating, (3) merge queue. Budget enforcement (spec 004) is deferred and unscheduled —
it re-enters the order only by explicit operator decision. Each component ships as a
small vertical slice with tests **before** work on the next begins. No component
starts while its predecessor lacks passing tests.

### II. Test-First

Every component gets tests before we move on; test-first development is the default for
all implementation work. A feature without tests is not done.

### III. Ask Before Adding Dependencies

No new dependency — package, service, or tool — is added without explicit operator
approval first. Approved to date: `uv`, `temporalio`, `httpx`, `pyyaml`, `pytest`
(+`pytest-asyncio`). `python-telegram-bot` is pre-flagged for the notifier but not yet
approved.

### IV. Determinism at the Core, LLMs at the Edges

Orchestration decisions (routing, retries, unlocking edges, merge policy) are plain,
deterministic code operating on graph data — never LLM calls. Workflow code makes pure
decisions; all side effects live in activities (plan-then-apply). LLM judgment is
bounded, opt-in, and confined to designated nodes (agent work, judge scoring).

### V. Spend Is Attributed, Never Anonymous

Every LLM-consuming node runs on its own model-constrained, TTL'd virtual key, issued
at dispatch and revoked at teardown — the attribution primitive that ties every token
(input, output, cache read/write) and dollar to a node, persona, epic, and piece of
work without agent cooperation. Every teardown writes a ledger row; recorded usage is
never fabricated (unknown is flagged, not zeroed). Budget *enforcement* (caps, breach
policy) is deferred per D-021. The proxy master key lives only in the worker host
environment and never enters orchestration state, payloads, or logs.

### VI. No Work Is Ever Lost

Agent output is salvaged on every termination path — breach, kill, timeout, failure —
by committing the worktree to the node's branch before cleanup. Escalations that expire
default to kill, but only after salvage.

### VII. Personas Over Model Tiers

Nodes are routed by persona (architect, implementer, verifier, judge, debugger,
researcher). A persona resolves to agent, model + fallback, skills, write scope, budget
default, and breach policy via an operator-editable registry. Code never hardcodes a
model name.

## Environment Constraints

- **Intent layer**: vanilla OpenSpec is the system of record for runtime intent;
  acceptance criteria are parsed mechanically from its stock grammar (no LLM parsing).
  A later fork adds a `workgraph.json` artifact requiring tasks + design.
- **Orchestration**: self-hosted Temporal; one generic WorkGraph interpreter workflow
  per epic reading a JSON DAG; no codegen'd workflows.
- **Model access**: exclusively through the already-deployed LiteLLM proxy (vLLM/DGX
  Spark, Ollama Cloud, Anthropic) via per-node virtual keys.
- **Agents**: headless coding agents behind a narrow, swappable adapter (Claude Code
  first; pi.dev/OpenCode later). Adapter outputs are process outcome + termination
  class only; diffs are read from the worktree, usage from the ledger. One isolated git
  worktree per node; sandboxed containers.
- **Merge**: GitHub is the source-control and merge system; target repos are public;
  landing goes through GitHub's native merge queue. Merge-queue required checks are
  deterministic only — the LLM judge runs in the inner loop, pre-CI, never in CI.
- **Escalation**: Telegram with inline-button approvals bridged to orchestration
  signals; Temporal Web UI is the operational dashboard for now.
- **Targets**: the factory never operates on its own repository; first E2E target is a
  separate trivial public sample repo. Each target repo declares runtime and
  test/lint/typecheck commands in a committed `factory.yaml`.

## Development Workflow

- Specs live under `specs/###-component-name/` (Spec Kit); the factory's own
  development follows spec → plan → tasks → implement.
- Decisions are recorded in `docs/decisions.md` as immutable numbered entries;
  supersede, don't edit. Architecture overview lives in `docs/architecture.md`.
- Every merge to the factory repo requires green tests.

## Governance

This constitution supersedes ad-hoc practice. Amendments require a new decision-log
entry (D-0xx) recording rationale, and a version bump below. Any spec, plan, or PR that
conflicts with a principle must either conform or carry an explicit, approved
amendment. Complexity beyond what a principle allows must be justified in writing in
the relevant spec's Assumptions section.

**Version**: 2.0.0 | **Ratified**: 2026-07-24 | **Last Amended**: 2026-07-24 (D-021:
Principle V redefined from budget enforcement to spend attribution; Principle I build
order updated — budget enforcement deferred to spec 004)
