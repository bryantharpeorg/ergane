# Contract: `factory-epic` CLI

Owned by `factory/workgraph/cli.py`, console script `factory-epic` (pyproject).
FR-009, FR-011, US3. Minimal by requirement: derive, start, status — the Temporal
Web UI covers everything richer.

## Environment

| var | default | used by |
|---|---|---|
| `TEMPORAL_ADDRESS` | `localhost:7233` | start, status |
| `TEMPORAL_NAMESPACE` | `factory` | start, status |

Same names and defaults as the notify bridge — one deployment story. `derive`
touches neither.

## `factory-epic derive <spec-dir> --target-repo <path> [--specs-root specs] [-o <file>]`

Pure pipeline: read `<spec-dir>/spec.md` → `derive` (workgraph-schema.md) → write
`workgraph.json` into `<spec-dir>` (or `-o`). On any validation failure: print
**every** collected error (each naming its story/rule), write **nothing**, exit 1
(US3-S4, SC-006). Exit 0 with the artifact path printed on success. Starts no
workflow.

## `factory-epic start <workgraph.json>`

Read + re-validate the graph (structural rules only — persona/timeout resolution
happens in `resolve_graph` on the worker, which owns `personas.yaml`). Start
`EpicWorkflow` with workflow id `epic-<epic_id>` on task queue `workgraph`,
namespace per env. Print the workflow id to stdout (US3-S1). An
already-running id → Temporal's already-started error is reported as
`epic '<epic_id>' is already running (workflow id epic-<epic_id>)`, exit 1.
Invalid graph → errors printed, exit 1, no workflow started.

## `factory-epic status <epic-id> [--json]`

Query `epic_status` on `epic-<epic-id>`. Human output: epic state line, then one
line per node (`<node_id>  <state>  attempt <n>  <branch>`), declaration order.
`--json`: the query result verbatim. Unknown workflow → clear message, exit 1.

## Exit codes

`0` success · `1` validation/user error (message on stderr) · `2` transport
(Temporal unreachable — the message names the address tried).

## Test surface

`test_epic_cli.py`: derive against the fixture corpus (artifact exactness, error
listing, nothing-written-on-failure); start/status against the time-skipping
environment (id convention, duplicate-start message, status shape both formats).
