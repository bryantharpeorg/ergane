# Data Model: Minimal WorkGraph Interpreter

All types live in `factory/workgraph/models.py` as frozen dataclasses / `StrEnum`s
(the 002 discipline: plain enough for Temporal's default JSON converter, `StrEnum`
so deserialization round-trips). This component adds **no store** — its durable
state is the workflow history plus the stores 001/002 already own; everything here
is either a compiled artifact (`workgraph.json`), a payload, or workflow memory.

## WorkGraphDeclaration (derivation intermediate, pure)

The parsed `## Work Graph` YAML before cross-validation — one entry per user story.

| field | type | notes |
|---|---|---|
| `story_id` | str | e.g. `US1`; must match a story the criteria parser finds |
| `depends_on` | list[str] | story ids; empty = root node |
| `implements` | list[str] | `FR-###` keys this story delivers |
| `timeout` | int \| None | per-story override, seconds, positive (R8) |

Never serialized beyond the deriver; exists so validation errors can name the
declaration (SC-006) before a `WorkNode` exists.

## WorkGraph

The compiled artifact (`workgraph.json`) and the workflow's input. Pure data,
validated at derive time and re-validated at epic start (FR-002 — the file may
have been edited by hand between the two, which re-validation makes irrelevant).

| field | type | notes |
|---|---|---|
| `epic_id` | str | e.g. `003-merge-queue`; names branches, keys, transcripts |
| `feature` | str | spec directory name under `specs_root` (D-023) |
| `specs_root` | str | target repo's specs directory, worktree-relative resolution at snapshot |
| `target_repo` | str | worker-host path to the target repo clone (bootstrap topology) |
| `nodes` | list[WorkNode] | **declaration order = scheduling order** (R10) |

**Validation (FR-002, raised with the offending node named):** every `id` unique;
every `depends_on` references a declared node; graph acyclic; every `persona`
resolvable in the registry *and* carrying a resolvable timeout (R8); `epic_id`,
`feature`, `target_repo` non-blank.

## WorkNode

One user story, compiled (FR-011: one node per story, never hand-authored).

| field | type | notes |
|---|---|---|
| `id` | str | lowercased story key, e.g. `us1`; names the branch and worktree |
| `story_key` | str | `US1` — the criteria-parser key |
| `persona` | str | registry name; bootstrap epics use `implementer` |
| `spec_ref` | str | `<feature>:<story_key>` — component 1's attribution string |
| `requirement_keys` | list[str] | `[story_key, *implements]` — what `snapshot_criteria` filters to |
| `depends_on` | list[str] | node ids (lowercased story ids) |
| `timeout_override_s` | int \| None | wins over the persona default when set (FR-010) |

## ResolvedNode (epic-start registry snapshot)

Output of the `resolve_graph` activity: the persona registry read once, at epic
start, per node — the same snapshot discipline as 002's criteria (an operator
editing `personas.yaml` mid-epic changes the *next* epic).

| field | type | notes |
|---|---|---|
| `node` | WorkNode | as validated |
| `model_alias` | str | persona's alias — the only place a model name enters the epic |
| `models` | list[str] | `[model, fallback?]` — the issued key's constraint list |
| `write_scope` | str | drives 002's `check_output` |
| `timeout_s` | int | override if set, else persona registry value (R8) |

## NodeState (enum) and NodeRecord (workflow memory, queryable)

```
PENDING → KEY_ISSUED → RUNNING → VERIFYING → PASSED
                                          ↘ FAILED   (ladder: → RETRY/DEBUGGER → KEY_ISSUED again,
                                                      or → ESCALATE → RETRY/park/KILLED)
any non-terminal ────────────────────────→ KILLED    (kill_epic, escalation KILL/EXPIRED, deps never met)
```

Terminal states: `PASSED`, `FAILED` (parked by PAUSE_EPIC resolution), `KILLED`.
`RETRY`/`DEBUGGER`/`ESCALATE` are ladder *actions* (002's `NextAction`), not
states — they route back into `KEY_ISSUED` or forward to a terminal state.

`NodeRecord` (per node, in workflow state, surfaced by the `epic_status` query):

| field | type | notes |
|---|---|---|
| `node_id` | str | |
| `state` | NodeState | |
| `attempt` | int | current/last attempt number, 0 before first dispatch |
| `history` | list[AttemptRecord] | 002's type — the ladder's input, verbatim |
| `escalations` | list[str] | resolutions received, the ladder's `escalations` arg |
| `branch` | str | `factory/<epic_id>/<node_id>` (FR-013) |
| `base_ref` | str \| None | target default-branch commit captured at first dispatch (R5) |
| `last_snapshot` | UsageSnapshot \| None | latest poll (R3), teardown fallback |

## EpicState (enum)

`RUNNING → PAUSED ⇄ RUNNING`, `RUNNING|PAUSED → KILLED`, `RUNNING → COMPLETED`
(all nodes terminal). `COMPLETED` does not imply all-PASSED — the workflow result
carries the per-node outcome map; SC-005's success reading is "every node PASSED".

## AttemptContext

Everything one attempt needs, assembled **pure** in the workflow from prior
activity results, consumed by `run_agent_attempt` (FR-005 inputs exactly).

| field | type | notes |
|---|---|---|
| `epic_id` / `node_id` / `attempt` | str/str/int | attribution triple (001's identity) |
| `prompt` | str | R9 assembly, retry evidence included from attempt 2 on |
| `worktree_path` | str | the node's one worktree (FR-013) |
| `proxy_url` | str | LiteLLM base URL |
| `virtual_key` | str | from the attempt's `KeyLease` — the only credential in the payload |
| `model_alias` | str | persona registry alias |
| `session_id` | str | uuid4, generated via workflow-deterministic API (`workflow.uuid4()`) |
| `timeout_s` | int | resolved per R8 |

## AdapterResult

D-018's narrow output — nothing else crosses back (FR-005: no diff, no usage).

| field | type | notes |
|---|---|---|
| `termination` | Termination | component 1's enum: COMPLETED / AGENT_ERROR / TIMEOUT / KILLED |
| `transcript_path` | str | archived attempt directory under `.factory/transcripts/` (FR-007) |

## Amendments to existing types

- **`factory.config.Persona`** gains `timeout_s: int | None` — optional, positive,
  forbidden when `agent == "none"` (R8). `personas.yaml` sets it on every
  agent-backed persona.
- **`factory.verify.models.FactoryConfig`** gains `standards: str | None` —
  optional non-empty path, schema stays v1 (R11). Existence checked in
  `prepare_worktree`, not at parse.

## Reused without modification

`KeyLease`, `UsageSnapshot`, `Termination`, `IssueKeyInput`, `TeardownInput` (001);
`CriteriaSet`, `VerificationResult`, `AttemptRecord`, `VerificationConfig`,
`NextAction`, `EscalationChoice`, all verify/notify activity input types (002).
The interpreter adds no fields to any of them.
