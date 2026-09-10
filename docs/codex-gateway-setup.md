# Codex CLI with an Ollama Cloud gateway

This is the gateway-backed setup: Codex supplies the coding-agent CLI, while
your database-backed LiteLLM gateway supplies inference and per-attempt usage
attribution. Ollama Cloud credentials stay on the gateway. Start with the
[operator setup guide](getting-started.md) for the engine, target and forge.

## Keep the three choices separate

| Choice | Where it is configured | What it controls |
| --- | --- | --- |
| Operator session | Your Codex CLI configuration and login | The model answering in your operator pane |
| Builder attempt | Ergane's resolved persona registry and frozen epic configuration | Agent runner, model, credential route and bounded retries |
| Independent judge | The judge persona and verification configuration | Acceptance review; changing the builder does not select a new judge |

Using Codex for a builder does not require using OpenAI inference. A Codex
gateway attempt uses its leased gateway key, not your ChatGPT login. Keep the
judge on its deliberately selected route and model when changing builders.

## Prepare the worker and gateway

Install `codex` where the worker's toolchain discovery can find it. Check the
actual version and installation layout, not only your interactive shell's
`PATH`. The runtime must also have `bwrap`, Git, uv, Node.js and the target's
declared build tools. A successful version command is a prerequisite check,
not proof that an agent can edit, test and commit inside the sandbox.

The gateway must serve the selected builder and judge aliases, support leased
keys and usage queries, and handle Codex's Responses requests and tool calls.
A model-list response alone does not prove those capabilities. Ergane generates
the builder's provider configuration in its own per-node Codex home, appending
`/v1` to the declared gateway base URL. Declare the proxy root, not a URL that
already ends in `/v1`, for this path.

The generated config names `CODEX_GATEWAY_KEY` as an environment key; do not
put its value in the registry or copy a gateway master key into a node's home.
Do not manually repair generated homes or share your operator's writable Codex
home with builders. The gateway path needs no factory ChatGPT login.

## Select Codex in the persona registry

Find the registry Ergane actually resolved; see the
[registry precedence explanation](getting-started.md#the-difference-that-will-bite-you).
In the builder entries used by your ladder, set `agent: codex` and
`route: gateway`. Keep their existing timeout, write scope and fallback policy
unless you deliberately intend to change those too.

This is one illustrative entry, not a replacement for the whole registry:

```yaml
implementer:
  agent: codex
  route: gateway
  model: ollama-cloud/glm-5.3-flash
  fallback: null
  skills: []
  write_scope: worktree
  needs_worktree: true
  timeout: 7200
```

The model string is an operator-defined gateway alias, not a built-in Ergane
model or a promise that another gateway serves it. Use your own served alias
and retain the other required personas. A non-null fallback must also be
served and usable through the same route; changing only a model does not
switch authentication. Promotion to another persona follows the configured
ladder, not an operator's current Codex model selection.

For the Ollama gateway configuration used by this repository, hosted web-search
tool requests are disabled in the project's `.codex/config.toml`:

```toml
web_search = "disabled"
```

Carry that compatible tool setting into your target as a deliberate, reviewed
configuration change when its gateway cannot serve the hosted search tool.
Do not disable the outer sandbox to solve a provider/tool incompatibility.
Project configuration and hooks remain subject to the client's normal trust
requirements; a written file is not proof that a client loaded it.

## Optionally use the gateway in your operator pane

Your operator session can keep its existing provider and login. If you also
want that session to use the gateway, give it a separate operator-scoped gateway
key, not a builder's short-lived key or the gateway master key. Add a custom
provider to your user-level Codex configuration, merging it with existing
settings rather than replacing the file:

```toml
[model_providers.ergane_gateway]
name = "Ergane gateway"
base_url = "https://gateway.example.com/v1"
env_key = "ERGANE_OPERATOR_GATEWAY_KEY"
wire_api = "responses"
```

Replace the example endpoint, make the named variable available through your
normal secret-management method, and select that provider and a served model
for the desired session. For example, from your target repository:

```bash
codex -c 'model_provider="ergane_gateway"' -c 'web_search="disabled"' --model ollama-cloud/glm-5.3-flash
```

Replace the example model alias too if your gateway uses a different one.
This starts an inference session and can incur usage; it is not a dry run.
Do not commit the key. Unlike Ergane's gateway-root
setting above, this Codex provider URL includes the API prefix.

Provider configuration belongs at user scope; do not put a second provider
definition into the target's project-local config and assume it overrides
Ergane's generated builder provider. OpenAI documents custom provider URLs,
environment-key authentication and configuration scope in the
[Codex configuration guide](https://learn.chatgpt.com/docs/config-file/config-advanced).
Keep your normal operator approval mode; the factory's noninteractive flags
belong inside its declared confinement, not in an unsandboxed operator command.

## Prove the configured path

Run the setup verification, then the supervised first-epic procedure in the
[setup guide](getting-started.md#dispatching-your-first-epic). Inspect the
actual attempt record, not only the registry file: the frozen dispatch must
name Codex, the gateway route and the intended model. Confirm real tool use,
an edited diff, gate results, independent judge results, archived evidence and
gateway usage. A halt-after-pass trial intentionally does not prove landing.
When normal landing is authorized, also require the native merge-group check
and the actual merged commit.

If a build cannot start, distinguish a missing CLI or sandbox tool, an
unsupported installation layout, a missing model alias, a provider/tool
refusal and a credential failure. Read the named refusal and current attempt
archive before changing configuration. Do not restart the worker or switch
the route solely because an observation timed out.

Subscription-backed Codex escalation is a separate credential-lifecycle and
deployment qualification. This gateway procedure does not establish it, and
its model/example must not be reused as a subscription configuration.
