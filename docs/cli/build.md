# `ergane build`

> start, watch and signal an epic

Verbs over one object: the epic. Everything is keyed by the **epic id**,
which is the spec directory's name — `072-a-stale-anchor-fails-validate-not-the-attempt`,
not a UUID and not a workflow run id.

```
ergane build ship                        <spec-dir> --target-repo PATH [dials] [--yes]
ergane build start                       <graph> [dials]
ergane build status                      <epic-id> [--json]
ergane build attempts                    <epic-id>
ergane build answer                      <epic-id> [<question-id> <text>]
ergane build resolve                     <epic-id> [<escalation-id> <choice>]
ergane build pause                       <epic-id>
ergane build resume                      <epic-id>
ergane build kill                        <epic-id> [--yes]
ergane build reset                       <epic-id> [--specs-root DIR]
ergane build salvage                     <graph>
ergane build credential-status           [--json]
ergane build complete-node-externally    <epic-id> <node-id> <branch> --provenance TEXT
ergane build external-completion-count   [--json]
```

---

## Starting

### `ergane build ship`

Validate, derive, show the compiled graph, pause, then dispatch. This is the
verb to reach for; `start` is the one to reach for when you already have the
artifact.

| argument | default | meaning |
| --- | --- | --- |
| `<spec_dir>` | — | the feature directory holding `spec.md` |
| `--target-repo` | **required** | worker-host path to the repository the epic builds in |
| `--specs-root` | `specs` | where the worker finds feature specs |
| `-o`, `--output` | `<spec-dir>/workgraph.json` | write the artifact here instead |
| `--delta` | | derive only the work that remains against the landed baseline |
| `--json` | | emit validate/derive output as JSON instead of human prose |
| `--yes` | | skip the interactive confirmation |

Plus every dial listed under `start` below.

### `ergane build start`

Dispatch a graph that is already compiled.

| argument | default | meaning |
| --- | --- | --- |
| `<graph>` | — | path to a compiled `workgraph.json` |

### The dials, shared by `ship`, `start` and [`roadmap start`](roadmap.md)

| flag | default | meaning |
| --- | --- | --- |
| `--max-concurrent-nodes` | `1` | how many ready nodes the scheduler may have in flight at once |
| `--promotion-persona` | the target repo's manifest, else no promotion rung | persona a node is promoted to once its ordinary attempts are spent |
| `--merge-method` | `squash` | how a passing node's pull request lands (`merge`, `rebase`, `squash`) |
| `--landing-poll-interval-s` | `60` | how often a landing in the queue is polled |
| `--stall-after-s` | `7200` | how long a landing may sit queued and unanswered before it classifies as stalled |
| `--max-recovery-cycles` | `1` | how many times a rejected landing may be recovered before the node escalates |
| `--max-free-rebases` | `3` | how many times a landing rejected for a moved base may be rebased and requeued for free |
| `--halt-after-pass` | | stop a passing node at `PASSED` and do not attempt to land — a supervised execution trial, not a dry run |

**`--max-concurrent-nodes` is not a free speedup.** It caps concurrent *agents*,
and raising it interacts with every isolation layer beneath it. Before running
unattended above 1, check `ergane findings list` for open defects in that area
and lower `--stall-after-s` so a wedged landing surfaces in the same session
that caused it.

**`--halt-after-pass` stops before landing, not before execution.** Agents,
gates and the judge still run and can incur model usage. Clone and preflight
operations can still contact GitHub; passing nodes are not enqueued for merge.

---

## Watching

### `ergane build status <epic-id>`

The epic's node table: state, attempt number, branch, PR number, landing state,
terminal reason, provenance, recovery cycles.

Per-node status includes the current `persona` and `model_alias` when available.
Use the epic's frozen workflow input and recorded dispatch for its runner and
credential-route provenance; do not infer either from your operator client's
model or a registry edited after dispatch. Legacy records can lack fields, so
missing provenance is unknown, not a value to invent.

The workflow start payload also owns a roadmap-dispatched epic's actual graph;
an on-disk `workgraph.json` is not rewritten by the roadmap and can disagree.

### `ergane build attempts <epic-id>`

Read-only, and needs no Temporal server. It reports stored verifications by node,
attempt and dispatch, including the verdict and the diff check's recorded size
decision: abridged, whole, or not recorded.

The human `judge input` token describes that diff check. Gate evidence also
uses space in the final judge prompt, so a `whole` token alone does not prove
that the judge received the entire diff. Where recorded, the `--json` output's
`judge.truncated_input` and `judge.gates_shown` fields describe the actual prompt.
A missing judge or missing historical measurement is unknown evidence.

If the verification store does not exist, the current command prints a human
absence message even with `--json`. An existing empty store produces an empty
JSON attempt list. Consumers must distinguish those cases; neither establishes
a completed or fully observed attempt.

### `ergane build salvage <graph>`

Read-only, and needs no Temporal server — which is the point. For every node of
a compiled graph it reports the branch and tip, every per-attempt salvage ref
(`refs/salvage/<epic>/<node>/attempt-<n>-<sha12>`), and whether the branch exists
off this machine.

A terminated epic's workflow is usually gone. The work usually is not. Reach for
this before concluding anything was lost.

### `ergane build credential-status`

Reports the current Claude subscription credential source and its locally
recorded expiry when available. It does not print a credential value or contact
the provider to prove authentication. It does not inspect Codex's subscription
credential; selecting a Codex builder does not change this command's scope.

---

## Answering

### `ergane build answer <epic-id> [<question-id> <text>]`

With no question id, list the epic's pending questions. With one, answer it; the
text is carried into the next attempt verbatim.

Questions from agents are yours to answer — that is the whole point of the
operator channel, and an unanswered question dead-waits its window and then
pages you anyway.

For a question that arrived over some other transport and quoted a correlation
id, use [`ergane answer`](answer.md) instead.

### `ergane build resolve <epic-id> [<escalation-id> <choice>]`

With no escalation id, list the epic's pending escalations. With one, record the
choice.

An escalation is a **fixed choice**, not free text — that is the difference from
`answer`. See [escalations.md](escalations.md) for what the offered choices mean
and why silence is a legitimate answer.

---

## Steering

| verb | effect |
| --- | --- |
| `pause <epic-id>` | stop dispatching new nodes; nodes in flight finish |
| `resume <epic-id>` | resume dispatch |
| `kill <epic-id>` | terminate the epic; `--yes` skips the confirmation |
| `reset <epic-id>` | re-dispatch from the compiled graph |

**A kill skips the sweep.** Node branches, worktrees and sidecar state outlive
the workflow, and a later relaunch will collide with them unless they are cleared
by hand. `build salvage` is how you find what survived.

`reset` is keyed by the epic id like every other verb that acts on a started
epic, and resolves the graph from `<specs-root>/<epic-id>/workgraph.json` rather
than reading it off the workflow — it cannot be read off the workflow, because
`describe()` exposes no input and start sets no memo. A path to a compiled graph
is still accepted.

---

## The operator escape hatch

### `ergane build complete-node-externally <epic-id> <node-id> <branch> --provenance TEXT`

Signal that a human finished a stuck node by hand. The branch becomes the node's
result and the provenance string is recorded in the verification store.

`--provenance` is required and should say who and how —
`operator:manual-2026-08-17`.

### `ergane build external-completion-count [--json]`

The durable count of accepted external completions: the total and the per-spec
breakdown. **The target is zero.** A store that has never recorded a use answers
`0` explicitly rather than as an empty table, so the number is always readable
as a measurement rather than as missing data.

## See also

- [`ergane spec`](spec.md) — validate and derive, which `ship` runs for you
- [`ergane status`](status.md) — every epic at once, rather than one
- [`ergane roadmap`](roadmap.md) — dispatch without a `build start` at all
