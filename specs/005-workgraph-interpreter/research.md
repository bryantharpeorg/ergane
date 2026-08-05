# Research: Minimal WorkGraph Interpreter

Phase 0 output. Every NEEDS CLARIFICATION from the Technical Context and the one
question the spec deferred to planning is resolved here. R-numbers are referenced
from plan.md, data-model.md, and the contracts.

## R1 · Pause durability across worker restarts

**Decision**: Durable by construction — no persistence code. `pause_epic` is a
Temporal signal; the paused flag is ordinary workflow state.

**Rationale**: A signal is a workflow *history event*. When a worker restarts,
Temporal replays the history against the same deterministic workflow code, the
signal handler runs again, and the flag is rebuilt exactly as it was — that is the
entire durability model of the interpreter, and pause gets it for free. The only
thing that could break it is nondeterministic workflow code, which constitution IV
already forbids for its own reasons. The spec's presumption ("durable by
construction") is confirmed; the open question closes with no design impact.

**Alternatives considered**: Persisting a pause row in a factory store (a second
source of truth that can disagree with workflow state — exactly the class of bug
Temporal exists to remove); a `paused` search attribute (observability sugar, not
durability; Temporal Web UI already shows pending signals and workflow state).

## R2 · Running the agent subprocess inside an activity

**Decision**: `run_agent_attempt` is one async activity: spawn via
`asyncio.create_subprocess_exec(..., start_new_session=True)`, heartbeat every ~30s
while waiting, enforce the node's wall-clock deadline in-activity (SIGTERM to the
process group, grace period, then SIGKILL), classify the outcome into component 1's
`Termination` enum, archive the transcript, return an `AdapterResult`.

**Rationale**: `start_new_session=True` puts the agent and every child it spawns
(`git`, `uv`, test runners) in one process group, so termination is
`os.killpg` — no orphaned grandchildren holding the worktree. The deadline is
enforced *inside* the activity rather than via Temporal's `start_to_close_timeout`
because a Temporal timeout kills the activity, not the subprocess, and forfeits the
classification + salvage the spec requires (US2-S3): `start_to_close_timeout` is
set to the node timeout plus a fixed margin as a backstop only. Heartbeating makes
the activity cancellable (kill path) and lets a worker crash be detected in ~minutes
rather than at the deadline. On `asyncio.CancelledError` (workflow kill), the
activity terminates the group, archives the transcript, then re-raises — cancel
semantics identical to timeout except for the classification (KILLED vs TIMEOUT).
The gate runner's TERM→KILL pattern (002's `gates.py`) is precedent.

**Alternatives considered**: Temporal-timeout-driven termination (loses
classification and transcript, charges infrastructure semantics to the agent);
a supervisor daemon outside Temporal (a second lifecycle manager to keep
consistent — the activity already is one); threads + `subprocess.run` (blocks a
worker thread for hours; async wait is free).

## R3 · Where usage polling lives

**Decision**: In the workflow. While `run_agent_attempt` is pending, the workflow
loops a ~30s timer and calls component 1's `poll_usage` activity, retaining the
latest `UsageSnapshot` as the eventual `TeardownInput.last_snapshot`.

**Rationale**: D-018 caps adapter outputs at termination class + transcript path —
no usage numbers — so the snapshot cannot ride back through the adapter. 001
designed `poll_usage` as a single cheap `/key/info` read "per beat" precisely for a
caller-side loop, and workflow-side polling keeps the fallback snapshot in workflow
state where teardown (also workflow-initiated) needs it. History cost is trivial at
bootstrap scale (~120 activity events per hour-long attempt against a 50K event
budget).

**Alternatives considered**: Polling inside the adapter activity (violates D-018's
output contract, entangles the adapter with the proxy client); no polling (loses
the teardown fallback 001 built — an unreadable proxy at teardown would record
`NULL` spend where a number existed 30s ago).

## R4 · Orphaned agent processes after a worker restart

**Decision**: A pgid file per node attempt under `.factory/run/<epic>/<node>.pid`,
written after spawn, removed on clean exit. On every `run_agent_attempt` start, if
the file exists and the process group is alive, kill it (TERM→KILL) before
launching — then overwrite the file.

**Rationale**: If the worker host dies mid-attempt, Temporal retries the activity,
but the old agent may still be running against the same worktree — two agents in
one worktree is corruption, and the spec's edge case ("the adapter detects and
reaps the orphaned agent process before relaunching") demands exactly this check.
The pid file is keyed by node, not attempt, because the worktree is the resource
being protected and there is exactly one per node (FR-013). Stale-pid collision
with an unrelated process is guarded by checking the process group still exists
via `os.killpg(pgid, 0)` and accepting the small race as strictly better than the
alternative (never reaping).

**Alternatives considered**: Scanning the process table for the agent binary
(matches unrelated operator sessions on a shared host); Temporal activity
`session`/worker-affinity features (heavier machinery than one file, and the
worktree is host-local anyway); doing nothing (the documented edge case).

## R5 · Worktree lifecycle mechanics

**Decision**: `factory/workgraph/worktree.py` wraps four operations against the
graph's `target_repo` clone: **ensure** (`git worktree add
.factory/worktrees/<epic>/<node> -b factory/<epic>/<node> <default-branch>` at
first dispatch; a directory that already exists is reused as-is), **salvage**
(`git add -A && git commit` on the node branch when the tree is dirty; clean tree →
no commit, message `salvage(<epic>/<node>): <termination> attempt <n>`), **remove**
(`git worktree remove --force` after terminal salvage; the branch always survives),
and **base ref capture** (the target repo's default-branch commit at first
dispatch, recorded in workflow state so retries never rebase mid-node).

**Rationale**: One worktree per node reused across attempts is clarified in the
spec (FR-013), and 002's same-worktree retry semantics (debugger included) require
the reuse. Salvage-before-remove is constitution VI verbatim; committing only a
dirty tree keeps SC-004 honest ("a salvage commit on the node branch" — an
empty commit would fabricate work; the branch itself is the record when the agent
produced nothing... except SC-004 requires a commit on every terminal attempt, so
salvage commits with `--allow-empty` when the tree is clean, making the attempt's
termination observable from the ref alone). Branch naming `factory/<epic>/<node>`
is clarified in the spec and machine-attributable by ref alone.

**Alternatives considered**: Worktree per attempt (violates FR-013 and discards
in-progress state the debugger needs); clone per node instead of worktree (slow,
disk-hungry, and loses the shared-object-store benefit); rebasing the worktree onto
a moving default branch between attempts (moves the goalposts mid-node — the same
reasoning as 002's criteria snapshot).

## R6 · Claude Code as the first adapter

**Decision**: `ClaudeCodeAdapter` launches `claude -p --dangerously-skip-permissions
--model <persona alias> --session-id <uuid4>` with the prompt on stdin, cwd = the
node worktree, and a scrubbed environment carrying exactly:
`ANTHROPIC_BASE_URL=<proxy url>`, `ANTHROPIC_AUTH_TOKEN=<virtual key>`, plus a
minimal passthrough (`PATH`, `HOME`, `LANG`, `TERM`). stdout/stderr stream to
`.factory/transcripts/<epic>/<node>/attempt-<n>/stdout.log`; after exit, the
adapter archives the session transcript from
`~/.claude/projects/<munged-worktree-path>/<session-id>.jsonl` into the same
attempt directory. Exit classification: exit 0 → COMPLETED, non-zero → AGENT_ERROR,
deadline → TIMEOUT, cancellation → KILLED.

**Rationale**: Prompt on stdin avoids ARG_MAX on multi-hundred-KB prompts. A
generated `--session-id` is what makes the transcript *discoverable* — Claude Code
names the transcript file after the session id under a per-cwd directory — and is
the D-018 "session id" input. The env allowlist is the master-key discipline
inverted: instead of scrubbing known secrets, pass only what is needed, so
`LITELLM_MASTER_KEY`/`TELEGRAM_BOT_TOKEN` can never leak by omission (US2-S1:
"never the master key or bot token"). The model alias travels as a CLI flag from
the persona registry — code names no model. `--dangerously-skip-permissions` is the
proven ralph-run configuration on this host; sandboxing beyond worktree isolation
is a post-bootstrap concern (architecture §10 notes containers as the target).

**Alternatives considered**: `--output-format stream-json` parsing (semantic
inspection of agent output — D-018 forbids the adapter knowing more than process
outcome; the raw log is archived either way); passing the key via
`ANTHROPIC_API_KEY` (Claude Code treats console keys and auth tokens differently —
`ANTHROPIC_AUTH_TOKEN` is the bearer-token path the LiteLLM proxy expects; verify
against the deployed proxy in the Tier 1 smoke); prompt as argv (ARG_MAX).

## R7 · Deriving the WorkGraph from the spec

**Decision**: `derive.py` is a pure function: spec text in → `WorkGraph` out.
Mechanics: fence-masked header scan (the technique 002's criteria parser and
D-023's grammar already use) finds the `## Work Graph` section; the first fenced
YAML block inside it is `yaml.safe_load`ed into per-story declarations
(`depends_on`: story ids, `implements`: FR keys, optional `timeout`: seconds).
Cross-validation reuses `factory.verify.criteria.load_criteria` on the same text
with no key filter: every story in the spec must have a declaration and vice versa;
every `implements` key must be an FR the spec declares; every `depends_on` id must
be a declared story; the resulting graph must be acyclic. One node per story:
`id` = lowercased story key (`us1`), `requirement_keys` = the story key + its
`implements` FRs, `spec_ref` = `<feature>:<story key>`. Any violation raises a
derivation error naming the offending story; nothing is emitted (SC-006).

**Rationale**: Reusing the criteria parser for cross-validation means the deriver
and the verifier read the same spec the same way — a story the deriver accepts is a
story `snapshot_criteria` will later resolve, by construction. Purity (no
filesystem, no registry) keeps SC-006 unit-testable exactly as FR-011 demands;
persona resolution deliberately does NOT happen at derive time (see R8).
`workgraph.json` is written by the CLI wrapper, not the pure function.

**Alternatives considered**: Deriving from tasks.md checkboxes (tasks are the
implementation slice, not the intent — and 005's clarification settled spec-as-
source); a speckit template fork adding the section (explicitly refused — the
operator stays off the speckit upgrade path; validation, not the template, enforces
the convention); node-per-task granularity (the clarified decision is one node per
user story).

## R8 · Timeout resolution (persona registry)

**Decision**: `factory/config.py` gains an optional `timeout` field: a positive
integer of seconds, forbidden on deterministic personas (`agent: none`), optional
otherwise. `personas.yaml` sets it for every agent-backed persona. Resolution is
persona-first at dispatch: the node's `## Work Graph` `timeout` override wins when
declared, else the persona's registry value; a producing node whose persona lacks a
timeout fails WorkGraph validation at epic start — before anything dispatches.

**Rationale**: The clarification names the registry as the default's home
(constitution VII pattern: operator-editable registry resolves runtime defaults;
code never hardcodes one). Validation at epic start rather than registry-load keeps
the loader lenient — `judge` resolves its timeout needs through 002's own bounds,
not the adapter's — while still failing loudly before any key is issued (FR-002's
"resolvable in the registry" extended to "resolvable with a timeout"). Derive-time
resolution was rejected because it would bake registry values into
`workgraph.json`, making a compiled artifact stale the moment an operator edits the
registry.

**Alternatives considered**: A workflow-config default like
`VerificationConfig.gate_timeout_s` (a hardcoded fallback is exactly what the
clarification excluded); required-on-all-personas (forces a meaningless value onto
`verifier`); per-node required in the YAML (pushes an operational default into
every spec).

## R9 · Two-loop prompt assembly

**Decision**: `prompt.py` is pure: `build_attempt_prompt(...)` takes the story's
spec sections (story body + acceptance scenarios + its `implements` FR bodies,
extracted mechanically), the epic's full plan.md text, the story's tasks.md slice
(the phase section whose heading names the story, extracted by the same
fence-masked header scan), the optional standards directive (R11), and — on
retries — the prior attempts' failure evidence (gate `output_tail`s and judge
feedback, verbatim, per 002 FR-006). The embedded inner-loop contract is the ralph
contract generalized to the slice: work the story's tasks in order, test-first, run
the deterministic gate after each task, commit per task, stop when the slice is
done or blocked — stated as advisory fast feedback, with the outer 002 ladder named
as the authoritative verdict (FR-012).

**Rationale**: The clarification fixes both the context set and the contract
lineage (Sonar's two-nested-loop pattern; ralph's PROMPT.md as the inner template —
63 tasks, zero retries is the evidence base). Purity makes FR-006's "unit-testably"
literal: text in, prompt out, no filesystem. The tasks.md slice is extracted by
header scan rather than parsed structurally because speckit-tasks names story
phases in headings — the same additive-grammar bet as `## Work Graph`, enforced by
the same loud-failure rule (a story with no findable slice fails prompt assembly,
which fails the dispatch before a key is issued).

**Alternatives considered**: Full tasks.md in every prompt (blows context on
multi-story epics and invites cross-slice work — the slice *is* the scope fence);
regenerating a per-story tasks file at derive time (a second compiled artifact to
drift; the slice extraction is one function); agent-discovers-context ("read the
spec yourself" — non-reproducible prompts, unattributable failures).

## R10 · Scheduling and replay determinism

**Decision**: Sequential: the workflow picks the first ready node in graph
declaration order (all `depends_on` PASSED, epic not paused), runs it to a terminal
state, then re-evaluates. Kill terminates the in-flight attempt (activity cancel →
R2 semantics), salvages, tears down, and marks every non-terminal node KILLED.
Pause lets the in-flight node finish its full ladder; it blocks only new *node*
dispatches (the clarified reading of "in-flight attempts run to completion" that
keeps a node's worktree/key lifecycle atomic).

**Rationale**: Parallel node execution is explicitly deferred by the spec, and
sequential + declaration-order is the strongest determinism guarantee available:
SC-001's "deterministically across replays" follows from ordering being a pure
function of graph data and recorded history, with no `asyncio.gather` races to
version. Declaration order (not node-id sort) because the deriver emits stories in
spec order — the spec author's order is the tiebreak, visibly.

**Alternatives considered**: Ready-set parallelism with a concurrency cap (the
deferred feature — the loop's seam is designed so the ready-set picker can widen
later without restructuring); priority-field scheduling (P1/P2 already shaped the
story DAG at authoring time; a second ordering input would let the two disagree).

## R11 · `factory.yaml` `standards` key

**Decision**: 002's loader (`factory/verify/factory_yaml.py`) accepts an optional
top-level `standards`: a non-empty string path, relative to the repo root, recorded
on `FactoryConfig`. Schema stays v1 (additive, optional). Existence is checked at
dispatch, in `prepare_worktree` — a declared standards file missing from the
worktree fails the dispatch loudly (config error, no agent attempt). When present,
prompt assembly (R9) includes a read-and-obey directive naming the path. Ergane's
own `factory.yaml` declares `standards: .specify/memory/constitution.md`.

**Rationale**: The clarification puts the key in factory.yaml (adapter-agnostic by
construction — no reliance on CLAUDE.md auto-loading) and the spec's Assumptions
assign ownership to 002's loader. Shape-only validation at parse keeps the parser
pure; the existence check lands in the one activity already touching the worktree
before the agent does. The directive references the path rather than inlining the
document because the agent can read it in-worktree — inlining would double a large
constitution into every prompt.

**Alternatives considered**: Schema v2 (a version bump for one optional key forces
every target repo to migrate for nothing); a persona-registry field (standards are
a property of the *target repo*, not of who works on it); inlining the document
into the prompt (context cost, and drifts from the committed file the gates see).

## R12 · CLI and workflow identity

**Decision**: Console script `factory-epic` (`factory/workgraph/cli.py`):
`derive <spec-dir>` (pure — parse, validate, write `workgraph.json` next to the
spec or print the specific errors and write nothing, exit non-zero), `start
<workgraph.json>` (validate, connect via `TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE` —
the bridge service's exact env contract — start `EpicWorkflow` on task queue
`workgraph` with workflow id `epic-<epic_id>`, print the id), `status <epic-id>`
(query `epic_status`, print per-node states; `--json` for machines). Duplicate
start of a running epic is refused by Temporal's workflow-id uniqueness — reported
as the operator-facing message, not a stack trace.

**Rationale**: FR-009 caps the surface at start + status ("anything richer is out
of scope — Temporal Web UI covers it"); derive rides along per FR-011/US3-S4.
Reusing the bridge's env names means one deployment story for everything that talks
to Temporal. `epic-<epic_id>` as workflow id makes the id predictable for `status`,
for the bridge's `workflow_id` round-trip, and for the operator's Web UI search —
and makes accidental double-starts collide by construction.

**Alternatives considered**: Subcommands on the existing `factory-usage` CLI (that
CLI is read-only by contract; mixing a workflow-starting verb into it breaks its
"safe to run anywhere" property); a `pause`/`resume`/`kill` CLI verb set (signals
are already sendable via `temporal workflow signal` and the Telegram buttons —
minimal means minimal; the workflow contract documents the signal names as the
supported surface).
