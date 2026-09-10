# Codex JSONL: measured startup and fatal-error boundaries

Operator qualification,2026-09-10. This is a synthetic protocol measurement,
not inference quality, real-account qualification, or a delivered160 decoder.

Installed executable: `codex-cli 0.154.0`, aarch64 Linux standalone, SHA256
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.
The helper uses only a synthetic HTTP peer and Python standard library.
Private network/PID/mount namespaces expose system binaries, this executable,
an empty temporary profile/workspace, and a caller-owned artifact directory.
No host account home, repository, credential, gateway, or inference endpoint is
mounted or reachable. Captured raw streams stay local, mode0600; the output
directory is0700. They are not part of this document or commit.

The invocation uses `exec --json --ephemeral --skip-git-repo-check --sandbox
read-only --model synthetic/no-inference -`. A temporary provider configuration
selects Responses transport, a loopback URL, a synthetic environment token,
ephemeral credential storage, and zero request/stream retries. No model runs.
Each HTTP case receives exactly one POST at the synthetic Responses endpoint.
Prompts, request bodies, and header values are discarded, not retained.

## Actual outcomes

| Fixture | Requests | Exit | JSONL outcome |
| --- | ---: | ---: | --- |
| HTTP401 credential rejection | 1 | 1 | thread start, diagnostic item, turn start, error, failed turn; no agent message |
| HTTP400 invalid request whose body quotes a historical401 | 1 | 1 | Same event families, but the fatal message is the non-authentication JSON error body |
| HTTP403 forbidden | 1 | 1 | Same families; the fatal message identifies403, not401 |
| Missing provider environment key | 0 | 1 | Same families despite no request; fatal message names the missing variable |
| Invalid transport configuration | 0 | 1 | Empty stdout/JSONL; configuration diagnostic only on stderr |

The three HTTP cases reproduced in three independent runs with fresh profiles.
The missing-key shape was measured twice. The final five-case invocation passed
all checks. An earlier probe wrongly expected missing-key failure to emit no
JSONL: its assertion failed, and the measurement corrected that probe assumption.
It was not a product test failure. Invalid configuration supplies the separate
measured pre-thread case.

## Interpretation for160 fixtures

Observed error events contain a message string; the401 message begins with the
CLI's unexpected-status form, while400 retains a JSON-encoded non-auth error
body. Neither includes an independent top-level numeric HTTP-status field.
The matching failed-turn event repeats the error message. Diagnostic item
errors are a separate item category and can precede the actual request.

Consequently, current typed provenance must be combined with recognition of
known fatal message forms, not arbitrary401 substring matches or invented
fields. Thread/turn starts prove protocol identity, not model-authored work.
The public [non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
supplies the broader event/item and usage examples; it is not an exhaustive
fatal-error schema. Keep unrecognized forms explicit and incomplete where
appropriate, without silently widening authentication refusal classification.

Retained operator helper SHA256:
`8db271cc0495c662ace4dd0c24ae6dcf8fa060f5494c754d6b833a174b1aa0c5`.
This record summarizes measurements; it does not publish raw transcripts or
change authentication ownership, factory routing, or readiness.
