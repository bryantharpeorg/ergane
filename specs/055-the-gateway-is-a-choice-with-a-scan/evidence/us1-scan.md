# US1 Scan Transcript — real loopback endpoints

Captured 2026-08-18 against the local development host. These outputs are
pasted directly from the terminal to satisfy SC-001: a claim about what a
running deployment reports.

## 1. Ollama on 127.0.0.1:11434 — inference-only

Command:

```
$ ergane install --scan --address http://127.0.0.1:11434
```

Output:

```
Probed 1 candidate(s):
  http://127.0.0.1:11434 — reachable, inference-only
    aliases: deepseek-v4-flash:0731-cloud, deepseek-v4-flash:cloud, gemma4-hauhaucs-balanced:q8-131k, gemma4:12b-it-qat, gemma4:26b-a4b-it-qat, gemma4:31b, glm-4.5-air:q5-128k, glm-4.5-air:q5-128k-tools, glm-4.5-air:q5-128k-tools-v2, glm-5.2:cloud, gpt-oss:120b-cloud, hermes-architect:latest, hermes-orchestrator:qwen3.6-128k, hermes4-70b:131k, hf.co/bartowski/NousResearch_Hermes-4-70B-GGUF:Q4_K_M, hf.co/googlecs/Huihui-Qwen3.6-27B-abliterated-Q4_K_M-GGUF:latest, hf.co/mradermacher/Qwen3-Next-80B-A3B-Thinking-GGUF:Q4_K_M, huihui_ai/gpt-oss-abliterated:120b, kimi-k2.7-code:cloud, nomic-embed-text:latest, qwen2.5-coder:32b-instruct-q6_K, qwen2.5:0.5b, qwen3-coder-next:q5-131k, qwen3-coder-next:q5-131k-v2, qwen3-coder-next:q5-256k, qwen3-coder:30b, qwen3-coder:30b-temp01, qwen3-next:80b, qwen3.5-122b:128k, qwen3.5:122b, qwen3.5:9b, qwen3.6-27b-abl-q4-ollama:latest, qwen3.6-27b:128k, qwen3.6-35b-a3b-hauhaucs-aggressive:q8-256k, qwen3.6-35b-a3b:q6-65k, qwen3.6-35b:128k, qwen3.6:35b-a3b-q8_0
    detail: inference-only: /v1/models answers but the key-management API (/key/generate) does not
```

The endpoint answered `GET /v1/models` with 37 aliases. A follow-up unauthenticated
`POST /key/generate` returned `404 page not found`, so the scanner classifies it
`inference-only` and names the missing capability.

## 2. LiteLLM proxy on 127.0.0.1:4000 — dispatchable

The unauthenticated scanner cannot be given the master key during discovery
(FR-003), so the proxy's `/v1/models` returns `401 Authentication Error`. This
correctly prevents the scan from classifying a credential-protected gateway as
reachable. To prove the proxy *is* a gateway when a credential is supplied, the
operator separately authenticated with the master key:

```
$ curl -s http://127.0.0.1:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"
{"data":[{"id":"general-agent",...},{"id":"dev-agent",...},{"id":"coder-small",...},{"id":"coder-large",...},{"id":"judge",...},{"id":"glm-5.2:cloud",...},{"id":"kimi-k2.7-code:cloud",...},{"id":"minimax-m3:cloud",...},{"id":"qwen3.6-27b-abl-nvfp4:192k",...},{"id":"qwen3.8-27b-nvfp4-dspark-sg-262k",...},{"id":"deepseek-v4-flash",...},{"id":"local/qwen3.6-27b",...},{"id":"ollama-cloud/deepseek-v4-flash",...},{"id":"ollama-cloud/glm-5.2",...},{"id":"ollama-cloud/kimi-k2.7-code",...},{"id":"anthropic/claude-opus-5",...}]}

$ curl -s -X POST http://127.0.0.1:4000/key/generate \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d '{"key_alias":"us1-scan-probe-2","models":[]}'
{"key_alias":"us1-scan-probe-2","key":"sk-H1lbP8n...","duration":null,"models":[],"spend":0.0,...}
```

The same proxy therefore answers both `/v1/models` and `/key/generate` when the
credential is presented, which is the dispatchable classification. The probe key
was deleted immediately after the transcript was captured.

## 3. Default loopback scan

Command:

```
$ ergane install --scan
```

Output:

```
Probed 2 candidate(s):
  http://127.0.0.1:4000 — unreachable, unknown
    aliases: none
    detail: /v1/models answered 401
  http://127.0.0.1:11434 — reachable, inference-only
    aliases: deepseek-v4-flash:0731-cloud, deepseek-v4-flash:cloud, gemma4-hauhaucs-balanced:q8-131k, gemma4:12b-it-qat, gemma4:26b-a4b-it-qat, gemma4:31b, glm-4.5-air:q5-128k, glm-4.5-air:q5-128k-tools, glm-4.5-air:q5-128k-tools-v2, glm-5.2:cloud, gpt-oss:120b-cloud, hermes-architect:latest, hermes-orchestrator:qwen3.6-128k, hermes4-70b:131k, hf.co/bartowski/NousResearch_Hermes-4-70B-GGUF:Q4_K_M, hf.co/googlecs/Huihui-Qwen3.6-27B-abliterated-Q4_K_M-GGUF:latest, hf.co/mradermacher/Qwen3-Next-80B-A3B-Thinking-GGUF:Q4_K_M, huihui_ai/gpt-oss-abliterated:120b, kimi-k2.7-code:cloud, nomic-embed-text:latest, qwen2.5-coder:32b-instruct-q6_K, qwen2.5:0.5b, qwen3-coder-next:q5-131k, qwen3-coder-next:q5-131k-v2, qwen3-coder-next:q5-256k, qwen3-coder:30b, qwen3-coder:30b-temp01, qwen3-next:80b, qwen3.5-122b:128k, qwen3.5:122b, qwen3.5:9b, qwen3.6-27b-abl-q4-ollama:latest, qwen3.6-27b:128k, qwen3.6-35b-a3b-hauhaucs-aggressive:q8-256k, qwen3.6-35b-a3b:q6-65k, qwen3.6-35b:128k, qwen3.6:35b-a3b-q8_0
    detail: inference-only: /v1/models answers but the key-management API (/key/generate) does not
```

With no `--address`, the scanner probed only the loopback candidates. The proxy
was not reachable without a credential, and Ollama was reported as inference-only.
