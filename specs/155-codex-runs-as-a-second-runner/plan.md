# Implementation Plan: Codex runs as a second runner

Every `file:line` below was read from the working tree at `8e8b3a1` on
2026-09-06 and verified to resolve. Re-read before editing — anchors move, and
the symbol-anchor tier is a prose convention, not a validator.

**Premise**: spec 154 (`an-agent-names-its-cli-and-its-route-separately`) has
landed. It gave the registry a `route:` field, made `load_personas` refuse an
agent with no registered adapter, made the dispatch path
(`factory/activities/agent_activities.py:521`) select the adapter the persona
names, and hoisted the agent-agnostic attempt policy into one shared
implementation. This spec adds no orchestration — it adds a class, a registry
entry, and a generated `config.toml`, which is exactly what D-018 promised a
second agent costs.

## What already exists, and where

**The seam this lands behind.** After 154:
- `_ADAPTERS` (`factory/workgraph/adapter.py:1512`) is the registry; adding
  `CodexAdapter.name: CodexAdapter` is the whole registration (FR-001).
- The dispatch path selects by persona `agent` (154 US3), so a persona with
  `agent: codex` reaches this adapter with no constant left to sever.
- The shared attempt policy (154 US4) is inherited, not copied.

**The gateway route is proven.** P1 ran 2026-09-06: `POST $LITELLM_PROXY_URL/v1/responses`
with `{"model":"ollama-cloud/glm-5.3-flash","input":"reply with the word ok"}`
returned HTTP 200 with `"text":"ok"` and real usage. The proxy's OpenAPI
declares `/v1/responses`, `/v1/chat/completions`, `/v1/messages`, `/v1/models`.
Every ladder alias resolves to an OpenAI-shaped upstream
(`ollama-cloud/glm-5.3-flash` → `openai/glm-5.3-flash` @ `https://ollama.com/v1`).
The gateway route is the default; `wire_api = "responses"` is the assumption.

**The Claude adapter as the reference shape** (read these, do not copy them):
- `ClaudeCodeAdapter` (`factory/workgraph/adapter.py:993`), `run_attempt` at :1022, per-CLI
  `argv()` at the launch section (:1195 region).
- Provider env / gateway: `factory/workgraph/adapter.py:947` (ANTHROPIC_BASE_URL /
  ANTHROPIC_AUTH_TOKEN), gateway-vs-subscription branch `factory/workgraph/adapter.py:1112`
  (`context.agent != "subscription"`).
- Home seeding `_seed_node_home` (`factory/workgraph/adapter.py:896`): writes the minimum the CLI
  needs non-interactively; for subscription personas copies the operator
  credential (`factory/workgraph/adapter.py:905` region onward).
- Credential discovery `discover_subscription_credential` (`factory/workgraph/adapter.py:840`)
  three-path order: `$XDG_CONFIG_HOME/claude/.credentials.json`,
  `~/.config/claude/.credentials.json`, `~/.claude/.credentials.json`
  (`factory/workgraph/adapter.py:848-852`).
- Prompt delivery `_feed_prompt` (`factory/workgraph/adapter.py:1584`): write prompt, close the
  pipe — the close ends the agent's read. Codex `codex exec -` fits this
  unchanged.
- Refusal markers: `SUBSCRIPTION_REFUSAL_MARKER = "Not logged in · Please run
  /login"` (`factory/workgraph/adapter.py:193`, measured 2026-08-19 on STDOUT with exit 1) and
  `SESSION_ID_REFUSAL_MARKER = "is already in use."` (`factory/workgraph/adapter.py:203`) — two
  literals on plain text. The `## OPERATOR QUESTION` scan
  (`factory/verify/question.py:85`) also reads plain text. This is why v1 does
  not pass `--json`.
- Turn-happened probe: the `$HOME/.claude/projects/<munged>/<id>.jsonl` session
  transcript, used to separate `AGENT_ERROR` from `PRE_AGENT_FAILURE`
  (`session_transcript`, `factory/workgraph/adapter.py:1518` region).

## What to build, in order

Four stories. US1 (gateway route) and US2 (refusal classification) are both P1
and land together; US2's measured refusal text is a prerequisite for trusting
any Codex run's outcome, so do not land US1 in a state where a refusal could
pass silently. US3 (subscription route) is P2. US4 (toolchain/image presence)
is P3 and conditional on the operator's sandbox-boundary decision.

### US1 — Codex on the gateway

1. Register `CodexAdapter` in `_ADAPTERS` under `codex` (FR-001). The class
   implements the per-CLI surface 154 hoisted: `argv`, prompt delivery,
   provider env, home seeding, credential discovery, turn-happened probe,
   refusal markers. The shared policy is inherited.
2. `argv(context)` (FR-004): `codex exec -` plus `--model`, the sandbox flag,
   and `--cd <worktree>`. Prompt on stdin via the existing `_feed_prompt`.
3. Provider env + home (FR-002/FR-003): for `route: gateway`, mint the
   per-attempt virtual key exactly as the Claude route, write a generated
   `config.toml` into the per-node `CODEX_HOME` declaring the gateway as a
   custom provider:
   ```toml
   model_provider = "ergane-gateway"
   [model_providers.ergane-gateway]
   name = "Ergane LiteLLM gateway"
   base_url = "<context.proxy_url>/v1"
   env_key = "CODEX_GATEWAY_KEY"
   wire_api = "responses"
   ```
   Put the virtual key in `CODEX_GATEWAY_KEY`. Every new env name goes on the
   standing boundary's env contract — under bwrap today that is the `--setenv`
   allowlist (`factory/workgraph/adapter.py:596-618`), which `--clearenv` makes the whole of the
   env; add only what is needed (trap 6).
4. Spend (FR-002): read from the proxy on the attempt's virtual key
   (`factory/activities/agent_activities.py:200-227`), same as Claude. Do NOT add `--json` for
   accounting.
5. Reasoning CoT (FR-007): the turn-happened probe and any output scan must
   not misread cleartext chain-of-thought (P1 finding, trap 1). Match markers
   and success against the message/output channel, not reasoning blocks.

### US2 — refusal classification

1. MEASURE FIRST (trap 2): install the CLI to a scratch prefix, run
   `codex exec` with no valid credential, record the exact refusal text, its
   stream, and its exit code. That string becomes the marker. (Also the moment
   to resolve trap 3's auth.json location and trap 4's thread id, both used in
   US3.)
2. Add the Codex refusal marker (FR-005) as the analogue of
   `SUBSCRIPTION_REFUSAL_MARKER`, wired into the same classification path so a
   refused run is named a refusal, never a silent diffless success.
3. The committed test replays the measured string both ways (US2-S2) and
   asserts reasoning text alone neither satisfies nor defeats detection
   (US2-S3 / FR-007).

### US3 — subscription route

1. For `route: subscription` (FR-006): mint no virtual key; seed the node home
   from the discovered Codex credential (the measured `auth.json` path from
   US2's probe step — the Codex analogue of `discover_subscription_credential`,
   `factory/workgraph/adapter.py:840`).
2. Record `credential_source` naming the file (US3-S2), so a subscription run
   is distinguishable from a gateway run in the evidence.
3. Name the token-rotation hazard as inherited and unmeasured (US3-S3), the
   same caveat `factory/workgraph/adapter.py:840-852` carries for Claude.

### US4 — toolchain and image presence (CONDITIONAL)

1. Add `codex` to the toolchain
   (`factory/verify/toolchain.py:122` region, `DEFAULT_AGENT_RUNNER`) and to
   the image (`Dockerfile`), so the binary is on the node's PATH (FR-008).
2. Launch under the standing boundary with Codex's own read-only default
   disabled (`--dangerously-bypass-approvals-and-sandbox`) when the outer
   boundary already confines the node.
3. Record the bwrap-nesting question (P4, deferred) as an OPEN hazard tied to
   the operator's sandbox-boundary decision — neither assumed to work nor
   assumed to fail. Do not harden the bwrap `--setenv`/mount seam beyond what
   the launch requires (trap 6).

## Traps (consolidated — meet them as declared scope, not as failure)

1. Reasoning CoT returns in cleartext (P1 measured; **re-measured by US1's
   probe on 0.153.4**: the reasoning summary text is interleaved into plain
   `codex exec` stderr output, and appears as its own `reasoning` item under
   `--json` — never as the agent message). Never match markers or success
   against reasoning text.
2. **MEASURED 2026-09-08 on `@openai/codex@0.153.4` (US1's probe task): every
   refusal is on STDERR, not stdout, with exit status 1 — the exact inverse of
   Claude Code, whose refusal is on stdout.** Stdout carries nothing on a
   refused run. The refusal shapes:
   - No credential at all (route to `api.openai.com`): repeated
     `ERROR: unexpected status 401 Unauthorized: Missing bearer or basic
     authentication in header` after websocket/HTTPS retries; stable marker
     `unexpected status 401 Unauthorized` (it also appears in gateway-mode
     401s, so it is route-independent).
   - Gateway mode with `env_key` var unset:
     `ERROR: Missing environment variable: \`CODEX_GATEWAY_KEY\`.` — names the
     configured `env_key`, not a literal.
   - Gateway mode with an invalid key: `unexpected status 401 Unauthorized:
     Authentication Error, Invalid proxy server token passed…` (again the
     stable `unexpected status 401 Unauthorized` substring).
   - Outside a git repo without `--skip-git-repo-check`:
     `Not inside a trusted directory and --skip-git-repo-check was not
     specified.` (exit 1, stderr) — the reason every launch passes
     `--skip-git-repo-check` in addition to `--cd`.
   070's lesson inverts here: the watcher must read stderr (the adapter already
   archives stdout+stderr interleaved into one `stdout.log`, so the combined
   stream is what every scan reads, and the marker is matched on that).
   A refused run still writes a session rollout file under
   `$CODEX_HOME/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl` containing only
   `session_meta` and error events — its existence is NOT evidence a turn ran.
3. **MEASURED 2026-09-08: `codex login` writes `$CODEX_HOME/auth.json`**
   (default `~/.codex/auth.json`), format `{"auth_mode":"apikey",
   "OPENAI_API_KEY":"sk-…"}` for API-key logins (ChatGPT logins add token
   fields). Re-login overwrites the key in place; `codex logout` removes the
   file. A gateway-routed attempt (env_key carries the key) writes **no**
   `auth.json` at all — its credential is the env var, not a file. Rotation on
   use is still UNMEASURED for ChatGPT-mode tokens (no ChatGPT account to probe
   with) — the hazard is inherited from Claude's
   `factory/workgraph/adapter.py:847` docstring, unmeasured, and US3 names it.
4. **MEASURED 2026-09-08: there is no session-id flag on `codex exec`** (full
   `--help` read; nothing accepts a caller-supplied id; `codex exec resume` is
   a resumption flag, not a set-one flag). Identity facts as measured:
   `codex exec` prints `session id: <uuid>` in its stderr banner (a v7-shaped
   UUID codex generates), and under `--json` the first event is
   `{"type":"thread.started","thread_id":"<uuid>"}` carrying the same value.
   The session rollout file is named after it:
   `$CODEX_HOME/sessions/<YYYY>/<MM>/<DD>/rollout-<RFC3339 mangled>-<id>.jsonl`
   — the `<id>` suffix is the adapter's probe target: turn-happened = a rollout
   file whose name carries a codex-generated id exists under the per-node
   `$CODEX_HOME/sessions` tree for this attempt's day. The banner id and the
   filename id agree (probe: banner `01a07e5e-9c24…`, file
   `rollout-2026-09-08T00-15-24-01a07e5e-9c24….jsonl`).
5. `wire_api = "chat"` acceptance unresolved; default to `responses` (P1 proved
   the proxy serves it, and the US1 probe then proved the CLI end-to-end on
   it); probe before relying on `chat`.
6. Do not over-invest in bwrap; the operator is weighing moving away from it.
7. A repeating 429 naming a `cooldown_list` is a dead upstream credential, not
   a rate limit; read up to the first 401.

## Verification

- Re-read every anchor against the tree at implementation time.
- `uv run pytest -q` green — the whole gate (`ergane.yaml`).
- One real dispatch of a single-story spec on a Codex persona through the
  gateway, with the landed diff and the ledger row as evidence. A green suite
  and a PASS verdict are evidence, not proof — run the thing.
- The conformance suite sweeps `_ADAPTERS` and would notice Codex breaking the
  seam.
