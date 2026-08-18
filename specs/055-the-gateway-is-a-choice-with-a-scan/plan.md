# Implementation Plan: the gateway is a choice, and install can find one

**Spec**: `specs/055-the-gateway-is-a-choice-with-a-scan/spec.md`

## What already exists, and where

Checked against the tree on 2026-08-17. Check again before relying on one — a
plan citing a function that has since moved sends the implementer hunting for it.

| Thing | Where | Why it matters here |
| --- | --- | --- |
| The one proxy seam | `factory/usage/litellm_client.py` — module docstring states the invariant | Every proxy call in the factory goes through this file. US2's direct path must not open a second one |
| The standard probe | `list_model_ids()` :356, `GET /v1/models` :367 | US1's discovery call already exists; reuse the shape |
| The proprietary calls | `/key/generate` :222, plus `/key/info`, `/key/delete`, `/key/list`, `/spend/logs/v2` | US1's second probe distinguishes a gateway from an inference endpoint |
| Mode-discriminated config | `factory/controlplane/config.py`: `LLM` dataclass ~:127 with `gateway: LLMGateway \| None` | US2 extends an existing discriminated union rather than inventing one |
| The token that already exists | `KNOWN_LL_MODES = ("gateway", "direct")` :35 | `"direct"` is deliberately recognized so the refusal can name it. Do not widen this tuple |
| The refusal being replaced | `RULE_LLM_DIRECT_NOT_SUPPORTED` :60, raised ~:340 | US2 replaces a refusal with a mode. The refusal's own text is the list of what direct gives up |
| Credential delivery | `factory/workgraph/adapter.py:774` `ANTHROPIC_BASE_URL`, `:775` `ANTHROPIC_AUTH_TOKEN` | The only place the agent's credential is set. Direct mode changes the value, not the mechanism |
| The mint that opens every attempt | `factory/workgraph/workflow.py:35`, call sites `:1197`, `:1809`, `:2437` | US2 routes through `issue_attempt_key`, never around it |
| Why attribution may degrade | `factory/activities/usage_activities.py` — "a poll is a read with no consequence", "issuance failure is not an attempt" | The distinction the whole spec rests on |
| The registry's claim | `personas.yaml` header — the key's `models` list makes the binding "enforceable, not advisory" | US2 makes that sentence conditional. FR-011 |
| The interview | `factory/cli/install.py` | US3's file, and US3's alone |
| Probe contract and registry | `factory/controlplane/verify.py`: `REGISTRY` :567, sweep :585 | 054 is rewriting this. Rebase onto it, do not fight it |

## Traps

**1. Do not send a credential to something you just discovered.** US1 probes
addresses nobody has confirmed yet. Any local process can bind a loopback port,
so a scan that presents the master key to whatever answers has handed that key
away. Probe unauthenticated, classify from the unauthenticated response, and
present a credential only to an address the operator has confirmed. FR-003 and
SC-002 exist to make this checkable rather than intended.

**2. A probe that opens a real socket is the 042/US3 test again.** The boundary
gate runs under bwrap with `--clearenv`, no D-Bus, a tmpfs `/tmp` and `USER`
unset; a CI runner has a full environment. A test that opens a real socket, or
that depends on what is listening on the host, passes in one and fails in the
other **deterministically** — and the agent meeting it will call it flaky,
because in its own sandbox it genuinely is green. On 2026-08-17 that pattern
burned four attempts on 042/US3; attempt 4 ran 3491 tests green and declared a
deterministic runner-side failure a flaky runtime condition. US1 is a story about
probing the network. Build the seam first, simulate through it everywhere, and
treat any test whose answer differs between your machine and the gate as already
broken.

**3. Route through `issue_attempt_key`, never around it.** The temptation in US2
is to branch before the activity and hand the static key straight to the adapter.
That also skips the ledger row, and the row is the record that the attempt
happened at all — `workflow.py:35` calls this activity the thing that opens every
attempt. Direct mode changes what the activity *returns*, not whether it runs.

**4. The degradations must be visible, not silent.** This repository has a
sentence for the failure mode, from 052: the command "would stop dying and start
lying." An empty `ergane usage` table and an inapplicable question look identical
and mean opposite things (FR-009). Same for the persona binding: if it is no
longer enforced, `personas.yaml` must stop claiming it is (FR-011). A file that
describes a guarantee the code stopped making is worse than one describing none.

**5. Enumerate the surrendered properties once.** SC-003. The interview, the
config error and the documentation all need the same three sentences, and three
copies drift. One source, three renderings, one test that they agree.

**6. Redaction is not optional for the direct credential.** `litellm_client.py`'s
docstring sets the standard: the master key "lives only in this client's request
headers, and is redacted out of anything a caller can observe — a failed call
raises `LiteLLMError` carrying an HTTP status and a scrubbed proxy message, never
the credential that authenticated it." Direct mode's key meets the same bar
(FR-010). A provider key in a traceback is a secret in a log.

**7. Loopback by default is a security property, not a default value.** FR-004.
An installer that sweeps a subnet unasked is doing network reconnaissance on the
operator's behalf. Candidates outside loopback must be named.

**8. Three stories, and only US3 may touch `factory/cli/install.py`.** US1 adds a
discovery module and a read-only flag; US2 works in config, dispatch and the
registry. If US1 or US2 finds itself editing the interview, the slice is wrong —
stop and say so rather than widening.

**9. Rebase onto 054, do not fight it.** 054's US2 and US3 are adding a host
probe to `factory/controlplane/verify.py` and changing `LLMProbe` to sweep the
whole registry. This spec is held until that lands. Read what landed before
writing; the probe contract may have moved.

**10. The judge sees the diff and the criteria, nothing else.** No base tree, no
terminal. SC-001 is a claim about a running deployment, so its transcript must be
committed as pasted output *inside the diff*. 053/US1 shipped attempt 1 without
its transcript and spent attempt 2 adding it.

## Sizing

US1 is a module plus a flag plus tests — small, and entirely simulated. US2 is
the largest: a config branch, a dispatch-path branch, a `usage` branch, a
registry header change, and the one-source-three-renderings structure SC-003
asks for. US3 is interview wiring over two landed stories. If US2 feels like it
is growing past one story, the likely cause is doing US3's interview work inside
it; that is trap 8, not a sizing problem.

## Verification the operator will run, independent of the gate

- **Run the scan against something real.** Start an Ollama endpoint on loopback
  and confirm the scan finds it, classifies it inference-only, and names the
  missing key-management capability. Then point it at the LiteLLM proxy and
  confirm the classification flips. Two classifications from one command is the
  claim; a test asserting it is not the same as watching it.
- **Prove FR-003 by observation, not by assertion.** Watch the probe traffic
  during a scan and confirm no authorization header leaves. This is the one
  requirement where a passing test and a leaking implementation can coexist if
  the test checks the wrong layer.
- **Prove SC-001 end to end.** On a host with a provider key and no proxy,
  declare `direct` and dispatch one attempt. That is the whole point of the
  spec, and it is the only check that catches a mode which parses but cannot
  build.
- **Prove FR-009 by control.** Run `ergane usage` in each mode. Gateway returns
  rows; direct says attribution is unavailable. If both return an empty table,
  the story failed even with a green suite.
