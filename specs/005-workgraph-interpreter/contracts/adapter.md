# Contract: Agent Adapter and Worktree Activities

Owned by `factory/workgraph/adapter.py`, `factory/workgraph/worktree.py`,
`factory/activities/agent_activities.py`. D-018, FR-005, FR-007, FR-010, FR-013,
US2. The adapter is the only place the factory touches an agent; everything
semantic is read elsewhere — the diff from the worktree, usage from the ledger.

## The seam

`AgentAdapter` is a small protocol: `launch(context) → handle`, `wait/monitor`,
`terminate(handle)`, `classify(exit) → Termination`, `transcript(handle) → path`.
`ClaudeCodeAdapter` is the first implementation; personas name adapters by the
registry `agent` field (`claude-code`). A second agent is a second class — no
orchestration change (D-018).

## Activities

### `resolve_graph(workgraph) → list[ResolvedNode]`

Reads `personas.yaml` once per epic (registry snapshot, data-model.md). Raises a
non-retryable `GRAPH_INVALID` naming the node for: unresolvable persona, missing
timeout (R8), structural rule violations (re-validation). Read-only, idempotent.

### `prepare_worktree(epic_id, node_id, target_repo, standards) → PreparedWorktree{path, branch, base_ref}`

First call: capture the target repo's default-branch head as `base_ref`, then
`git worktree add .factory/worktrees/<epic>/<node> -b factory/<epic>/<node>
<base_ref>`. Subsequent calls (retries, debugger, activity re-runs): the directory
exists → return it unchanged (idempotent by construction; FR-013's one worktree).
When `factory.yaml` declares `standards`, verify the file exists in the worktree —
missing → non-retryable `STANDARDS_MISSING` (a config error, no agent attempt,
ladder applies as for any dispatch failure).

### `run_agent_attempt(AttemptContext) → AdapterResult`

The one place an agent runs. In order:

1. **Reap** (R4): if `.factory/run/<epic>/<node>.pid` names a live process group,
   TERM→KILL it. Then write this attempt's pgid.
2. **Launch** (R6): `claude -p --dangerously-skip-permissions --model
   <model_alias> --session-id <session_id>`, prompt on **stdin**, cwd =
   `worktree_path`, `start_new_session=True`.
3. **Environment — allowlist, not scrub** (US2-S1). The child env is exactly:

   | var | value |
   |---|---|
   | `ANTHROPIC_BASE_URL` | `proxy_url` from the context |
   | `ANTHROPIC_AUTH_TOKEN` | the attempt's virtual key (the only credential in any payload) |
   | `PATH`, `HOME`, `LANG`, `TERM` | passed through from the worker |

   `LITELLM_MASTER_KEY`, `TELEGRAM_BOT_TOKEN`, and everything else are absent by
   construction — omission, not redaction.
4. **Monitor**: heartbeat ~30s while waiting; enforce `timeout_s` in-activity —
   on deadline, TERM the process group, grace (10s), KILL (US2-S3).
5. **Classify** (US2-S2): exit 0 → `COMPLETED`; non-zero → `AGENT_ERROR`;
   deadline → `TIMEOUT`; cancellation → `KILLED`. Nothing else is inspected — no
   stdout parsing, no self-reported success (FR-012).
6. **Archive** (FR-007), on *every* path including cancellation and crash-retry:
   copy the streamed `stdout.log` and the session transcript
   (`~/.claude/projects/<munged-cwd>/<session_id>.jsonl`) into
   `.factory/transcripts/<epic>/<node>/attempt-<n>/`; return that directory as
   `transcript_path`. Transcripts stay on the worker host, never committed.
7. Remove the pid file; return `AdapterResult{termination, transcript_path}`.

On `asyncio.CancelledError` (workflow kill): steps 5–7 with `KILLED`, then
re-raise so Temporal records the cancellation. Temporal timeouts are a backstop
only: `start_to_close_timeout = timeout_s + margin`, `heartbeat_timeout` ~2min.

**Not in the output** (D-018): no diff, no usage numbers, no parsed verdicts.

### `salvage_worktree(epic_id, node_id, termination, attempt) → str (commit sha)`

`git add -A` + commit on `factory/<epic>/<node>` with message
`salvage(<epic>/<node>): <termination> attempt <n>`; `--allow-empty` when the tree
is clean so every terminal attempt is observable from the ref alone (SC-004,
constitution VI). Idempotent per attempt: a clean tree after a prior salvage
produces an empty marker commit, never an error. Called by the workflow on every
node-terminal path *before* `remove_worktree` and before key teardown completes
the record.

### `remove_worktree(epic_id, node_id) → None`

`git worktree remove --force` after terminal salvage. The branch always survives.
Idempotent: an already-removed worktree is success.

## Test surface (US2 independent test)

`tests/stub_agent.py` — an executable standing in for the agent CLI: records its
argv/env/cwd/stdin to a file, sleeps or exits per a control file, writes a fake
session transcript. Adapter tests assert env exactness (the table above and
nothing else), TERM→KILL timing, classification per exit path, archive layout,
and reaping of a planted live process group.
