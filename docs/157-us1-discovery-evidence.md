# 157 US1 qualification

## Factory-attempt gate evidence (retained historical run)

These two outputs were committed by the factory's US1 attempt. They are not
new full-suite runs performed by the operator evidence-refresh branch.

```text
uv run pytest tests/test_operator_instructions.py tests/test_claude_md.py -q
============================== 68 passed in 1.05s ==============================
```

### Repository gate

```text
uv run pytest -q
========== 6079 passed, 58 skipped, 15 warnings in 606.31s (0:10:06) ===========
```

## Independent current-byte qualification — 2026-09-10

The six JSON records now describe fresh independent observations of canonical
SHA-256 `0986f4602ccc91f3bb3eba6b2ff4282cc114eb6f814e0df974cc91a8afbd154f`.
The source anchor is c3d21e7ee27fde207614509efeb94a60717134e5. Its full Git
tree is identical to PR head5cd4391429269037c3cb46f336e5ed8ffe1b3704. The
native landing0d909c5fd96a5ee966243ecf4c896cce90d26174 leaves the canonical
guide, Claude symlink and focused instruction tests unchanged. Actual Git diffs
returned no differences for those comparisons.

### Codex rendered inputs

`codex-cli 0.154.0` rendered its prompt input in fresh temporary homes. The
evidence is the model-visible input, not a model response. Host paths are
redacted below as `<REPO>`, `<PARENT>` and `<WORKTREE>`.

```text
root:     # AGENTS.md instructions for <REPO>\n\n<INSTRUCTIONS>\n# Ergane ...
nested:   # AGENTS.md instructions for <PARENT>\n\n<INSTRUCTIONS>\n# Ergane ...
worktree: # AGENTS.md instructions for <WORKTREE>\n\n<INSTRUCTIONS>\n# Ergane ...
```

Each input contained the whole decoded canonical guide exactly once, ignoring
only leading/trailing whitespace; the byte digest above is checked separately.
One operator guard and the precedence guard were present. The installed CLI ran
with an empty native profile, read-only source and no network or inference.
The nested context was repeated after correcting an operator probe mount that
had hidden its parent checkout; no candidate guide or client settings changed.

Codex reads project instructions when a run starts and discovers them along the
project-root-to-working-directory chain. This is why the qualification uses
fresh root, nested and worktree contexts rather than a filename-presence check.
[Official instruction-discovery guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

### Claude actual request captures

Installed Claude Code2.1.261 sent its real request to a loopback-only synthetic
HTTP peer inside an isolated network namespace. The peer captured the input
before returning a fixed acknowledgment; it ran no model. Each child had an
empty temporary profile, read-only source, no tools and strict empty MCP
configuration. Neither the live gateway nor an operator account was used.

Root, nested and isolated-worktree contexts each exited0 with one full
canonical occurrence, one operator guard and the precedence guard present.
Each positive context passed again in a new process/profile. The requested
model alias is only a request label here, not observed serving-model evidence.
No synthetic usage field is treated as a measurement. Only counts/digests are
retained; raw requests, credentials, absolute host paths and output are omitted.

The empty-directory control exited0 with one captured request but zero
canonical/guard occurrences and no precedence guard, twice. Its request-input
digests were:

```text
first:  3c06c292a25d9bc98a81ef5c83ca1c87e051693cce06b249ddafce164b7ab4b8
repeat: 3ed0f7e6451dc41d8b31e77e0bf6d7d51b56d69ea410bbd3acdccf87fe778548
```

Positive first/repeated request digests are retained in the three Claude JSON
records. Every actual capture reported `real_inference_requests: 0` and passed.
This demonstrates installed-client instruction loading, not model obedience,
real-account qualification, tool enforcement or a successful gateway model call.

### Historical evidence correction

The old Claude observations were dated September9 and derived from archived
candidate909568392ddb with canonical digest646c1242e5be3bc1e52e4e5de72c0de11a18359f5ade62674934d17c27b161a4.
The factory candidate had retained those observations while replacing their hash
with today's different canonical digest. Static fixture checks alone accepted
that relabeling; they were not evidence of a new session. This refresh replaces
them with the actual new observations above and keeps the historical distinction
explicit. A digest assertion still does not authenticate who ran a probe.

### Evidence-refresh focused verification

Actual operator command on this isolated branch, with no live-tier environment:

```text
python -m pytest tests/test_operator_instructions.py tests/test_claude_md.py -q -o addopts=''
68 passed in 0.33s
```

The live tiers did not run. This check covers the guide, compatibility symlink,
real CLI command/path references and fixture contracts, not a second full gate
or new model inference. Production code, AGENTS.md bytes and live node worktrees
were not edited by this evidence correction.
