# Ergane Constitution

Ergane is an agentic software factory: it turns Spec Kit feature specs into merged,
verified code by dispatching headless coding agents through an orchestrated DAG, with
attributed per-node spend, mechanical acceptance-criteria verification, and
merge-queue discipline. The full decision log lives in `docs/decisions.md`
(D-001…D-037); this constitution distills the non-negotiables that every spec, plan,
and implementation must honor.

## Core Principles

### I. Strict Build Order, Vertical Slices (NON-NEGOTIABLE)

Components are built in this order: (1) per-node usage tracking, (2) verification
gating, (3) minimal WorkGraph interpreter (spec 005), (4) merge queue (spec 003) —
the last built by the factory itself dispatching its own spec, with the human
operator as merge queue until it lands (D-024). Budget enforcement (spec 004) is
deferred and unscheduled — it re-enters the order only by explicit operator decision.
Each component ships as a small vertical slice with tests **before** work on the next
begins. No component starts while its predecessor lacks passing tests.

### II. Test-First

Every component gets tests before we move on; test-first development is the default for
all implementation work. A feature without tests is not done.

A test asserts on what the run under test did, never on ambient host state. Scanning a
shared location — `/tmp`, a home directory, a global registry — and asserting on
everything found there makes the suite a function of the machine it runs on: it fails
for reasons no diff explains, and it passes only while nothing else on the host happens
to collide. Where a test must prove a run left no residue, it captures the state before
the run and asserts on the **difference**. Renaming whatever collided is not a fix; the
next thing to occupy that namespace will collide again. A test that cannot pass on a
host doing unrelated work is not measuring the code.

### III. Ask Before Adding Dependencies

No new dependency — package, service, or tool — is added without explicit operator
approval first. Approved to date: `uv`, `temporalio`, `httpx`, `pyyaml`, `pytest`
(+`pytest-asyncio`), and `python-telegram-bot` (approved 2026-07-24 for the notifier).

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

### VIII. Acceptance Criteria Are Provable From the Diff (NON-NEGOTIABLE)

The judge is given the story's diff and the criteria snapshot — never the base tree, the
commit message, a terminal, or the running system. Every acceptance criterion must
therefore be decidable from the diff alone. A criterion that names a commit message, a
mutation that is reverted before commit, a `--durations` reading, a CI observation, or
the state of code the diff does not touch is unprovable by construction: correct,
complete work will fail it, and no number of attempts can change that.

Where a story genuinely needs runtime evidence — a measured duration, a mutation
observed red, a suite total — that evidence is committed as an artifact the diff
contains, with tool output pasted rather than described. The obligation sits with the
spec author: a criterion that cannot be met is a defect in the spec, not in the agent
that failed it.

**That evidence is spent from a bounded budget, and the bound is 64 KiB.** The
deterministic check refuses any story diff exceeding `DIFF_INPUT_LIMIT`
(`factory/verify/diffbounds.py`) before the judge ever runs, so a diff of correct,
tested code is discarded for its size alone — gates green, judge never called, the
whole attempt spent. Pasted evidence is charged to that same budget as the code: on
2026-08-22 both stories of epic 079 lost their first attempt this way at 83,384 and
74,490 bytes, and for one of them 29% of the refused diff was the artifacts this
principle requires. A story is therefore sized for its evidence and its code
together, and one whose evidence cannot fit beside its implementation is split
before dispatch, not discovered oversized after a build. The obligation sits with
the spec author here too: the ceiling binds the diff an agent produces, so a story
scoped past it is a defect in the spec (D-050).

### IX. A Governing Value Is Declared, Never Ambient

When code needs a value that decides where work goes — which branch a landing targets,
which repository owns a directory, which root a path resolves against, which model a
node runs — it reads that value from the declaration that owns it (`factory.yaml`, the
persona registry, the compiled workgraph, the node's own record). It never infers it
from whatever the process happens to be sitting in: a checked-out `HEAD`, a current
working directory, an inherited environment variable, or a default that is merely
present.

Ambient state is the most expensive kind of wrong answer this factory produces, because
it is *plausible*. It is correct on the machine where the code was written, correct in
every test that runs in a clean checkout, and wrong only in the configuration nobody
tried — so it survives review, survives the suite, and fails later, far from its cause,
wearing an error message that names something else. Three times in eight days a landing
PR was opened against whatever branch a clone had checked out rather than the branch
`factory.yaml` declares: `attest/023-042-landed` and `operator/apache-2-license` on
2026-08-17, `spec-routing-plan` on 2026-08-24. Each one killed a node that had passed
every gate and its judge — one of them cascading to two more — and each announced itself
as an unrelated `gh` error about blank SHAs (D-051).

Where the declaration is genuinely absent, the code **refuses and names the declaration
it wanted**. It does not fall back to ambient state and proceed. A refusal at the seam
where the value is read costs one clear error message; a fallback costs a full build,
and spends it before it tells anyone.

## Environment Constraints

- **Intent layer**: Spec Kit feature specs (`specs/<feature>/spec.md`) are the system
  of record for runtime intent (D-023); acceptance criteria are parsed mechanically
  from the template grammar (no LLM parsing). A later extension may add a
  `workgraph.json` artifact for explicit DAG declarations.
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
- **Targets**: the factory's first self-hosted target is this repository — epic 003
  is dispatched by the factory against Ergane itself, human-merged until 003 lands
  (D-024, superseding the earlier never-self-target constraint). Each target repo
  declares runtime, gates and loop composition in a committed `factory.yaml`.

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

**Version**: 2.7.0 | **Ratified**: 2026-07-24 | **Last Amended**: 2026-09-07 (2.7.0 —
D-054: Principle II narrowed; a test asserts on the difference a run made, never on
ambient host state, and where it must prove a run left no residue it captures the
matching state before the run and asserts on the set difference. 2.6.0 —
D-051: Principle IX added; a value that governs where work goes is read from the
declaration that owns it, never inferred from a checked-out branch, a working directory
or an inherited environment, and an absent declaration is refused rather than defaulted.
2.5.0 —
D-050: Principle VIII amended; the evidence it mandates is charged to a bounded 64 KiB
diff budget, and a story is sized for evidence and code together or split before
dispatch. 2.4.0 —
D-046: loop composition is declared data; environment-constraints wording amended to
say each target repo declares runtime, gates and loop composition in a committed
`factory.yaml`. 2.3.0 — D-037: Principle VIII added; acceptance criteria must be
provable from the diff alone, because the judge sees nothing else. 2.2.0 —
D-023/D-024: intent layer is Spec Kit feature specs; build order gains minimal 005
before 003; 003 is built by the factory against this repository, superseding the
never-self-target constraint; preamble updated to spend attribution. 2.1.0:
`python-telegram-bot` added to the approved-dependency roster, D-022. 2.0.0 — D-021:
Principle V redefined from budget enforcement to spend attribution; Principle I build
order updated — budget enforcement deferred to spec 004)
