# 155-US2 evidence — the Codex refusal, measured

FR-005 says the marker comes from the probe, not from assumption (trap 2).
US1's T004 probe measured it first (2026-09-08, recorded in plan.md trap 2);
this node re-measured every shape itself against the real CLI before wiring
the marker, so the committed classifier rests on a measurement this attempt
reproduced, not on a claim it inherited. Transcript below, pasted rather than
described (constitution VIII / D-037: the judge sees this diff and nothing
else).

CLI: `@openai/codex@0.153.4`, fetched as
`registry.npmjs.org/@openai/codex/-/codex-0.153.4.tgz` plus the
`codex-0.153.4-linux-arm64.tgz` platform artifact (this host is aarch64);
binary `package/vendor/aarch64-unknown-linux-musl/bin/codex`, which prints
`codex-cli 0.153.4`. Scratch lives under `/tmp/codex-probe`, outside the
worktree.

## Shape 1 — no credential at all (route to api.openai.com)

`codex exec --skip-git-repo-check --cd <dir> -` with the prompt on stdin, no
`auth.json`, default `CODEX_HOME`. Exit code captured before any pipe:

    EXIT=1
    === STDOUT (0 bytes) ===            <- stdout carries nothing
    === STDERR fatal lines ===
    2026-09-08T03:33:20.520517Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://api.openai.com/v1/responses
    ERROR: Reconnecting... 2/5        (…repeats 5/5…)
    warning: Falling back from WebSockets to HTTPS transport. unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: wss://api.openai.com/v1/responses, cf-ray: a37ae44efeca5d06-DFW
    ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses, cf-ray: a37ae47add1a45fa-DFW, request id: req_e4cfc40ee7cb4428a347456e386c2e51

A rollout file was still written:
`$CODEX_HOME/sessions/2026/09/08/rollout-2026-09-08T03-33-20-01a07f13-d155-7a53-81c5-5d2ba73e7519.jsonl`
— its existence is not evidence a turn ran (plan trap 2).

## Shape 2 — gateway mode, `env_key` variable unset

Generated `config.toml` declaring the gateway provider with
`env_key = "CODEX_GATEWAY_KEY"`, launched with that variable absent:

    EXIT=1
    === STDOUT bytes: 0 ===
    ERROR: Missing environment variable: `CODEX_GATEWAY_KEY`.

The adapter's launch path always mints the key into the env before the child
starts, so this shape is prevented by construction in production — it is
recorded here because it is a refusal the marker does NOT match, and the
story's guarantee (a refusal is named) rests on the shapes the launch path can
actually produce.

## Shape 3 — gateway mode, invalid key (401 through the LiteLLM proxy)

Same `config.toml`, `CODEX_GATEWAY_KEY=sk-invalid-garbage`, proxy
`http://localhost:4000/v1` (the deployed LiteLLM answered 401 unauthenticated
— the wrong-credential shape, exactly what a minted-but-dead key produces):

    EXIT=1
    === STDOUT bytes: 0 ===
    ERROR: unexpected status 401 Unauthorized: Authentication Error, Invalid proxy server token passed. Received API Key = sk-...bage, Key Hash (Token) =a7e00522…, Unable to find token in cache or `LiteLLM_VerificationTokenTable`, url: http://localhost:4000/v1/responses

## What the measurement fixed

- Exit 1 on every refusal; **stdout is empty on every refusal**; the fatal
  lines are on stderr — the inverse of Claude Code (stdout, also exit 1),
  which is why the marker scans the combined `stdout.log` and not a stream
  chosen by name (070's lesson, inverted for this CLI).
- The stable substring across shapes 1 and 3 — openai.com and gateway-mode
  401s — is `unexpected status 401 Unauthorized`:
  `CODEX_REFUSAL_MARKER` (factory/workgraph/adapter.py). Route-independent, so
  the activity's classifier carries no route gate.
- A refused run still writes its rollout file under the per-node
  `$CODEX_HOME/sessions` tree, so the turn probe answers "a turn happened" on
  a refused run too — the marker, not the rollout, is what names the refusal.