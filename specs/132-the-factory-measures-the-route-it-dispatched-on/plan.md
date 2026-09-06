# Implementation Plan: the factory measures the route it dispatched on

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The check to strengthen.** `factory/workgraph/preflight.py:857` —
`check_aliases` makes exactly two awaited reads, each with its own failure arm,
and closes the client in a `finally`:

```python
    findings: list[PreflightFinding] = []
    try:
        try:
            served = await client.list_model_ids()
        except LiteLLMError as exc:
            findings.append(
                PreflightFinding(
                    check="model-aliases-served",
                    passed=False,
                    transport=True,
```

`served` is then compared against the graph's aliases and the unserved ones
become one finding; `list_key_aliases()` at
`factory/workgraph/preflight.py:914` — `check_aliases` is the first-attempt
collision read, with a transport arm of its own producing a
`check="first-attempt-key-aliases"` finding. **Count the arms before writing a
test against a dead proxy: there are two, and the function's own docstring at
`factory/workgraph/preflight.py:860` — `check_aliases` says the independence is
deliberate** — "a proxy that answers one endpoint but not the other gets a
finding for the one it refused ... so the operator is told which is which". A
wholly unreachable proxy therefore returns **two** transport findings today, and
FR-007 asks for exactly those two and no third. The finding type has exactly four
fields — `factory/workgraph/preflight.py:131` — `PreflightFinding` is
`check` / `passed` / `detail` / `transport` — and no severity of any kind.

**What "informational" means here, exactly.** 126-US1 (`d5119a8`) introduced it
without adding a field: a `passed=True` finding is informational, and the two
dispatch surfaces drop it. `factory/cli/nouns/build.py:363` — `_run_preflight`:

```python
    # Informational findings (`passed=True`) are reported by the module but must not
    # stop dispatch (126 US1 FR-005: an unreachable remote is not a refusal).
    return [f for f in findings if not isinstance(f, PreflightFinding) or not f.passed]
```

`factory/activities/roadmap_activities.py:662` — `preflight_spec` calls
`check_aliases` on that line and carries the same comment-and-filter three lines
below it, at `factory/activities/roadmap_activities.py:665-667` — diff the two
surfaces from those two places, not from the call. `factory/workgraph/cli.py:141`
— `_run_preflight` does **not** filter: it returns every finding, and
`factory/workgraph/cli.py:654` — `_start_epic` prints and refuses on any
non-empty list.

**The parity test that already exists, and what it covers.**
`tests/test_predispatch_landing_preflight.py:460` —
`test_both_dispatch_surfaces_return_the_same_findings` drives the roadmap
activity and `ergane build start` against one fake proxy and asserts their lists
are equal. The third surface is outside it, and the two it does cover are equal
only because they run the same three checks and drop the same informational
findings. FR-005 extends that test; it does not ask for a three-way equality that
no diff could produce.

**The gateway filter that scopes the ask.** `factory/workgraph/preflight.py:835`
— `aliases_to_check` builds the alias set and skips any persona where
`not persona.routes_through_gateway`. That property is
`factory/config.py:203` — `routes_through_gateway`, and its body at
`factory/config.py:208` — `routes_through_gateway` is
`return self.agent not in (DETERMINISTIC_AGENT, SUBSCRIPTION_AGENT)`: it excludes
**deterministic** personas as well as subscription ones, so it is not
`agent != "subscription"`. Both kinds contribute no alias, so FR-004 is a
property the existing code already has — do not lose it, and do not describe it
as a subscription-only filter in a finding's wording.

**The completion capability three call sites assume and no client implements.**

```python
                if hasattr(client, "chat_completion"):
                    response_data = await client.chat_completion(request)
```

That is `factory/controlplane/verify.py:557` — `_probe_one_alias`, a nested
closure inside `factory/controlplane/verify.py:428` — `gather` over `client`,
`base_url`, `api_key` and `timeout`; with a real client the `hasattr` is false
and it falls through to a raw `httpx` POST. The other two call it unguarded:
`factory/cli/install.py:375` — `_async_probe_one_token` (which catches the
`AttributeError` and reports it as a failed completion) and
`factory/controlplane/canary/probe.py:261` — `judge_canary` (which does not).
`factory/usage/litellm_client.py:108` — `LiteLLMClient` defines no such method;
every request it makes goes through `factory/usage/litellm_client.py:409` —
`_call`, which raises `LiteLLMError` on any status ≥ 400 with the proxy's own
message already scrubbed and bounded by `factory/usage/litellm_client.py:445` —
`_proxy_message` — the exact shape FR-002 needs.

**The two lifetimes that make the flip expensive, and only one of them is this
spec's to fix.** `factory/controlplane/verify.py:477` — `gather` builds the
client, and the key-management probe's `finally` closes it at
`factory/controlplane/verify.py:535` — `gather`:

```python
            try:
                await client.aclose()
            except Exception:
                pass
```

`_probe_one_alias` is not defined until `factory/controlplane/verify.py:548` and
not called until `factory/controlplane/verify.py:594` — `gather`, both after that
`finally` has run. Between them sits an early return:
`factory/controlplane/verify.py:539` — `gather` leaves the function whenever the
key-management probe failed, so a fix that simply moves the `aclose()` below the
loop leaks the client on that path. `LiteLLMClient` holds one persistent
`httpx.AsyncClient` built at `factory/usage/litellm_client.py:128` — `__init__`
and closed by `factory/usage/litellm_client.py:196` — `aclose`. That is FR-010's
whole subject.

The **second** lifetime is the canary's, and it is a filed defect this spec does
not fix. `factory/controlplane/canary/probe.py:208` — `probe_judge_canary`
closes the client in its own `finally`, and
`factory/controlplane/canary/probe.py:220` — `probe_judge_canary` then calls
`judge_canary(alias, client)` on it, which reaches
`factory/controlplane/canary/probe.py:261` — `judge_canary`'s
`client.chat_completion(request)`. Today that raises `AttributeError` before
httpx checks whether the client is open; after FR-003 it raises
`RuntimeError("Cannot send a request, as the client has been closed.")`. The
ledger already holds it as
`install/the-judge-canary-closes-its-http-client-then-uses-it`, open and
critical, and says in its own notes that the missing method was masking it.

**The tautology FR-009 removes.** `factory/controlplane/verify.py:585` —
`_probe_one_alias` returns `LLMAliasResult(alias=alias, model=alias, ...)`. The
`model` field is declared `str | None` on the dataclass at
`factory/controlplane/verify.py:80` — `LLMAliasResult`, is written there and read
nowhere under `factory/`, so replacing it with the payload's own `model` breaks
no consumer. Write the empty string for "the payload named none", not `None`:
the type allows `None` and it is then indistinguishable from a field nobody set,
which is the distinction US1-S8 exists to keep.

**Where the answered model comes from.** `factory/verify/judge.py:982` —
`_assistant_content` already holds the whole payload:

```python
    choices = payload.get("choices") if isinstance(payload, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
```

and returns only the assistant's text to `factory/verify/judge.py:955` —
`_complete`. The payload's `model` is one `.get` away and is discarded today.

**Four places build a `JudgeVerdict`, not two — and the two easy to miss are the
ones FR-014 turns on.** `factory/verify/judge.py:653` — `parse_verdict` and the
malformed-response arm at `factory/verify/judge.py:826` — `run_judge` both set
`model_alias` from the argument they were handed, and both hold a response body:
they get the payload's `model`, or the empty string. The other two hold no body
at all. `factory/workgraph/workflow.py:2942` — `_score` builds the
`JudgeOutcome.UNAVAILABLE` verdict when the judge activity raised, from an
`ApplicationError` message and nothing else — that is FR-014's sentinel case, and
`factory/verify/models.py:1070` — `compose_result` already separates it
(`judge_unavailable = judge is not None and judge.outcome == JudgeOutcome.UNAVAILABLE`).
`factory/verify/store.py:1261` — `_judge_from_dict` rebuilds one from a stored
row and reads its required keys hard — `model_alias=data["model_alias"]` at
`factory/verify/store.py:1275` — `_judge_from_dict` — so a new field read the
same way raises `KeyError` on every row written before this spec. The precedent
for the read side is four lines below it:
`factory/verify/store.py:1281` — `_judge_from_dict` reads `gates_shown` with
`data.get("gates_shown", False)`, and 116-US3's comment at
`factory/verify/store.py:1254` — `_judge_to_dict` explains why the write side is
longhand.

**The two aliases, and which request each describes.**
`factory/verify/models.py:608` — `JudgeVerdict` carries the **judge's** registry
alias, set from `judge.model_alias` at `factory/workgraph/workflow.py:2928` —
`_score`. `factory/verify/models.py:946` — `VerificationResult` carries the
**implementer rung's**, set from `routing.model_alias` at
`factory/workgraph/workflow.py:2688` — `_verify`, whose comment says the alias is
"only ever the routing's" because an attempt no model ran must not borrow one. On
this floor's registry those are different models — `personas.yaml:271` routes the
implementer at `ollama-cloud/kimi-k2.7-code` and `personas.yaml:324` routes the
judge at `ollama-cloud/glm-5.3` — so they disagree on every attempt.

**Where the answered model goes.** The verification store, not the usage ledger.
`factory/verify/store.py:258` is `model_alias TEXT` inside the `_SCHEMA_DDL`
constant — the requested side, landed by 117-US2 — and `usage_records`
(`factory/usage/ledger.py`) has a `persona` column and no model column at all.
The row model is `factory/verify/models.py:946` — `VerificationResult`. It is
constructed in two places, and FR-012 to FR-014 need both:
`factory/verify/models.py:998` — `compose_result` on the write side, which
already receives the `JudgeVerdict`, so a field carried on the verdict needs no
new argument at its call site (`factory/workgraph/workflow.py:2653` — `_verify`,
which is workflow code); and `factory/verify/store.py:1031` —
`_result_from_row` on the read side, which is where a NULL column must become the
unobserved sentinel.

**How a column is added here.** `factory/verify/store.py:640` — `_migrate` is
"add it if it is missing", keyed off `PRAGMA table_info` rather than off a
version number, and the 117-US2 block above the insertion point states the order
rule in full: `ALTER TABLE ADD COLUMN` appends, the `_RESULT_COLUMNS` tuple
(`factory/verify/store.py:711`) is read positionally by
`factory/verify/store.py:1031` — `_result_from_row`, and a divergent order does
not raise — it hands every field of every row to the wrong attribute. The write
side is `factory/verify/store.py:971` — `_result_values`, and
`factory/verify/store.py:1024` — `_result_values` is the line that turns the
`UNKNOWN_BUILDER` sentinel into the NULL it means. FR-014 copies that treatment.
That is the row's column. The **verdict's** field is a separate, fifth edit in
the same file: `factory/verify/store.py:1238` — `_judge_to_dict` and
`factory/verify/store.py:1261` — `_judge_from_dict` are the evidence JSON codec,
written longhand on purpose so a new field has to be added to both.

**Where a credential and an address already arrive as data.** `/model/info` is
an authenticated read, and the module that writes the attempt row holds nothing
to authenticate with: `factory/activities/verify_activities.py:467` —
`RecordVerificationInput` carries a `VerificationResult` and an optional spec
path, full stop. The judge's own dispatch does carry both —
`factory/activities/verify_activities.py:420` — `RunJudgeInput` has `virtual_key`
and `proxy_url`, and `factory/activities/verify_activities.py:430` — `run_judge`
hands them to the library, where `factory/verify/judge.py:942` — `_complete`
opens `httpx.AsyncClient(base_url=proxy_url, headers={"Authorization": f"Bearer
{virtual_key}"})`. That is the seam FR-015 uses. The shape of the read itself is
`factory/discovery/llm_enrichment.py:137` — `_fetch_litellm_model_info`, whose
signature is `(client: httpx.AsyncClient, base_url: str)` and which returns the
body verbatim; its caller looks the alias up as a top-level key at
`factory/discovery/llm_enrichment.py:228` — `_records_from_litellm` and reads
only capability fields out of it, never `litellm_params`. The other independent
source, unused here, is the spend log:
`factory/usage/litellm_client.py:284` — `fetch_spend_log_rows` drains
`/spend/logs/v2`, whose rows carry a model per request.

**The ledger writer US3 reuses.** `factory/doctor/store.py:137` — `report`
upserts a finding and appends an occurrence. There is already one runtime writer
following that path: `factory/workgraph/detector.py:636` — `_persist_finding`
writes an out-of-band batch file first and then writes to
`factory_root / "doctor.db"` inside a `try` that swallows `OSError` and
`sqlite3.Error`, because the runtime root may be gone.

**The shared proxy fake.** `tests/conftest.py:119` — `FakeLiteLLM` serves
`/key/generate`, `/key/info`, `/key/delete`, `/spend/logs/v2`, `/v1/models` and
`/key/list`; anything else is `tests/conftest.py:262` — `_handle` returning
`404 unknown route`. Measured at 602a92c: seventeen test modules import it, and
four of them name a preflight entry point directly —
`tests/test_023_us2_dispatch_pin.py`, `tests/test_engine_skew_preflight.py`,
`tests/test_predispatch_landing_preflight.py` and
`tests/test_roadmap_prompt_assembly.py`. Every other test that drives
`ergane build start` or the roadmap activity against this fake reaches the same
function without naming it, so treat "every existing preflight test" as the blast
radius rather than the four.

**The doctor's own real-transport test.** `tests/test_controlplane_verify.py:1147`
— `test_verify_llm_gather_against_live_double` is the one place the LLM probe
runs against a real `LiteLLMClient` built by `from_env`, over a loopback HTTP
listener, and it asserts `finding.passed is True`. Its docstring says, in as many
words, "the client has no chat_completion path, so the gather falls back to httpx
— that is the code path being exercised here". FR-003 makes that sentence false
and that assertion red. This file is US1's, and the test is FR-010's second
regression.

## Traps

**Trap 1 — THE US3 COMPARISON HAS A NO-OP SHAPE THAT MAKES A WRONG FIX LOOK
RIGHT, AND A FALSE-POSITIVE SHAPE THAT LOOKS LIKE IT WORKING.** The finding's own
notes say LiteLLM returns the deployment it routed *under*, so "compare the
response's `model` to the requested alias" agrees with itself essentially always
— the `/v1/models` blind spot reimplemented one layer down. That is why FR-015
compares against the declaration instead. But the declaration lives in a
different namespace: `/model/info`'s `litellm_params.model` is
`hosted_vllm/qwen3-coder-30b` where the alias is `judge-primary`, so a raw
comparison of the two **disagrees on every healthy alias** and would file a
warning-severity finding on every attempt, into the ledger the operator reads.
FR-016 is the rule that survives both shapes: report only when the answered model
matches *neither* the declared upstream (provider prefix aside) *nor* the alias
itself. An alias echoed back is silence, not a defect. The wrong moves are a
fixture built on the proxy's own echo (passes, never fires) and a raw string
comparison against `litellm_params.model` (fires always, on healthy floors).

**Trap 2 — THE PREMISE IS UNESTABLISHED, AND US3 IS WORTH NOTHING UNTIL IT IS
MEASURED.** Nobody in this repository has written down what this gateway's
completion payload puts in `model` for a mapped alias, or what
`/model/info` returns for the same alias.
`factory/discovery/llm_enrichment.py:228` — `_records_from_litellm` looks the
alias up as a top-level key of the payload and reads capability flags out of the
result; it never reads `litellm_params`, and its own comment says proxies
disagree about the payload's shape. Reuse here means reading the payload
correctly, not calling the existing function and trusting its shape. Take the two
reads first — one judge-shaped completion against a live alias, one
`GET /model/info` for the same alias — and paste both as committed evidence
before the comparison is built on them (FR-015, FR-017; operator step 5). If the
completion payload only ever echoes the alias, FR-016's rule makes this check
silent on this floor by construction, and the pasted payload is the only thing
that tells the operator which of the two regimes they are in.

**Trap 3 — REUSE MEANS IMPLEMENTING THE SEAM, NOT LIFTING THE CLOSURE — AND THE
SEAM REDDENS ONE LIVE DIAGNOSTIC AND UNMASKS A SECOND DEFECT IT DOES NOT FIX.**
The "existing probe" at `factory/controlplane/verify.py:548` — `_probe_one_alias`
is a nested function closed over four locals of
`factory/controlplane/verify.py:428` — `gather`; lifting it drags a key-minting
method with it. The cheap, whole move is the method three call sites already
assume — `chat_completion` on `factory/usage/litellm_client.py:108` —
`LiteLLMClient`, implemented once through `factory/usage/litellm_client.py:409` —
`_call` (FR-003). Be exact about what that buys and what it costs, because the
draft of this trap was wrong about it:

- It **repairs** `factory/cli/install.py:375` — `_async_probe_one_token`, whose
  `finally` closes the client *after* the completion, so a defined method simply
  starts working there.
- It **does not repair** `factory/controlplane/canary/probe.py:261` —
  `judge_canary`. Its caller closed the client at
  `factory/controlplane/canary/probe.py:208` — `probe_judge_canary` before
  calling it at `factory/controlplane/canary/probe.py:220` —
  `probe_judge_canary`, so the `AttributeError` becomes
  `RuntimeError("Cannot send a request, as the client has been closed.")` and
  `ergane install`'s persona step at `factory/cli/install.py:624` stays broken.
  That is the open critical
  `install/the-judge-canary-closes-its-http-client-then-uses-it`, whose notes name
  the structural fix (let `run_probes` own the lifetime with `async with`). It is
  **out of scope here**. Do not widen into it, and do not write a comment or a
  finding claiming the canary now works.
- It **breaks the doctor** unless FR-010 lands with it. The moment the method is
  defined, the `hasattr` at `factory/controlplane/verify.py:557` —
  `_probe_one_alias` flips true and the probe calls it on the client that
  `factory/controlplane/verify.py:535` — `gather` already closed: httpx raises
  `RuntimeError`, which is not an `httpx.HTTPError`, so `_call`'s handler misses
  it and the bare `except Exception` inside `_probe_one_alias` records
  `completed=False`. Every alias of `ergane doctor`'s LLM probe
  (`factory/controlplane/verify.py:1187`, the `REGISTRY` list) and of
  `factory/supervision/demo_driver.py:320` — `_default_llm_preflight` would then
  report failing against a healthy gateway. The suite sees this:
  `tests/test_controlplane_verify.py:1147` —
  `test_verify_llm_gather_against_live_double` goes red.

What else changes, so no test is written for a distinction that does not exist
and no key is quietly re-minted for one that does. The **credential** is the same
gateway master key on both paths — `factory/controlplane/verify.py:434` —
`gather` reads `os.environ.get(gateway.master_key_env)` and
`factory/controlplane/verify.py:168` — `_llm_client_factory` builds the client
with `LiteLLMClient.from_env()`. The **address** is not necessarily the same: the
raw fallback posts to the `base_url` the config handed `gather`, while
`from_env()` resolves the environment first, which is the open key
`verify/probe-mints-against-the-resolved-env-gateway-not-the-declared-one`
(demonstrated live 2026-08-20). Retiring the fallback puts mint and completion on
one address and so removes that key's *internal* disagreement, without deciding
which address is right — say that in the diff rather than claiming the key is
closed. The **timeout** changes (`config.llm.timeout_s` at
`factory/controlplane/verify.py:435` — `gather` versus `DEFAULT_TIMEOUT_SECONDS`,
`30.0`, at `factory/usage/litellm_client.py:55`) and the **error wording**
changes, because `_call` raises `LiteLLMError` for everything and the
`except httpx.TimeoutException` arm's "timed out after Ns" sentence stops firing.
That wording change is an improvement worth noting: the bare
`response.raise_for_status()` at `factory/controlplane/verify.py:566` —
`_probe_one_alias` is what
`verify/the-gateway-probe-discards-the-upstream-error-body-so-a-failed-alias-names-no-cause`
is about, and `factory/usage/litellm_client.py:445` — `_proxy_message` carries
the upstream's own message instead. Neither key is declared in `fixes:`; both are
named here so the next triage reads them rather than re-mints them.

FR-010 is the fix for the part that *is* in scope: keep a live client for the
probe loop and still close it on **both** exits — the early return at
`factory/controlplane/verify.py:539` — `gather` and the normal one. Building a
second client for the probe loop, closed in its own `finally`, is the move that
cannot leak; "move the `aclose()` below the loop" is the move that can.

**Trap 4 — THE SHARED FAKE ANSWERS 404 TO A COMPLETION, AND EVERY EXISTING
PREFLIGHT TEST DRIVES IT.** `tests/conftest.py:262` — `_handle` has no
`/chat/completions` route, so the moment the probe lands inside
`factory/workgraph/preflight.py:857` — `check_aliases`, every existing preflight
test starts seeing a new failing finding for every alias its graph names. Four
test modules name a preflight entry point through this fake and seventeen import
it; the ones that drive `ergane build start` or the roadmap activity reach the
same code without naming it, so size for "every existing preflight test", not for
four. The fix is part of this story, not collateral: teach
`tests/conftest.py:119` — `FakeLiteLLM` the route, defaulting to *serving* every
alias it advertises, with an explicit lever for the dead-upstream case. A fake
whose default is "refuses" turns FR-001 into a repository-wide test rewrite.

**Trap 5 — ONE OUTAGE, ONE FINDING — AND TODAY A DEAD PROXY IS ALREADY TWO.** The
probe runs only over the aliases the `/v1/models` read confirmed served (FR-006,
FR-007). Two ways to get this wrong, both expensive: probing an alias the proxy
does not advertise doubles the finding an operator already has, and probing after
the model-list read has *failed* turns a transport refusal into an extra,
differently-worded one for the same dead proxy. Read the baseline before writing
the test: `factory/workgraph/preflight.py:857` — `check_aliases` returns **two**
transport findings against a proxy that refuses everything, one per independent
read, and its docstring calls that deliberate. A test asserting "exactly one
finding" is red for a reason the diff cannot cause, and the cheapest way to make
it green is to suppress the key-list arm — deleting a behaviour this spec never
asked to change. Assert the two, unchanged, plus no third.
`factory/workgraph/preflight.py:131` — `PreflightFinding` has no severity field;
do not invent one, and do not reach for `passed=True` to express "this was not
really a failure" — that value means informational and is dropped by two of the
three surfaces (`factory/cli/nouns/build.py:363` — `_run_preflight`).

**Trap 6 — A PROBE THAT STALLS IS A WORSE OUTAGE THAN THE LADDER IT PROTECTS, AND
THE SEAM HAS NO TIMEOUT ARGUMENT TO PASS.** `DEFAULT_TIMEOUT_SECONDS` is `30.0`
(`factory/usage/litellm_client.py:55`), and a graph naming six gateway-routed
aliases probed in sequence against a hung gateway stalls a dispatch for three
minutes — and on the roadmap surface that is not merely a stalled tick, it is a
timeout with a retry behind it. `preflight_spec` runs as an activity at
`factory/roadmap/workflow.py:1241` — `_dispatch` under the options at
`factory/roadmap/workflow.py:1248` — `_dispatch`, and those options are the
module's `_FAST` at `factory/roadmap/workflow.py:459`: a
`start_to_close_timeout` of **two minutes**, with a retry policy of three
attempts. Six aliases at 30 s sequential is three minutes, so the worked example
above does not merely stall the tick — it exceeds that ceiling, the activity
times out, and Temporal re-runs the whole preflight, re-probing every alias, up
to three times. That is the sharpest reason FR-008 is not optional: issue the
completions concurrently over the served aliases, and keep the concurrent worst
case inside two minutes rather than inside the operator's patience. Choosing the
probe's timeout deliberately is not free either: `factory/usage/litellm_client.py:409`
— `_call` takes no timeout, and the client's is fixed at construction
(`factory/usage/litellm_client.py:128` — `__init__`), so a per-probe timeout
means giving `chat_completion` — or `_call` — an optional one that reaches
`self._client.request`. That edit lands in `factory/usage/litellm_client.py`,
which is US1's file, and it is the same task as FR-003's method.

**Trap 7 — DO NOT MINT A PROBE KEY.** The doctor's probe mints a short-TTL key
because it is *testing* key minting. A preflight that minted one would create a
key alias while standing next to `factory/workgraph/preflight.py:914` —
`check_aliases`, the check that refuses a dispatch when a live key already holds
an alias the epic will mint; a revocation that failed would leave the floor
refusing itself on the next tick. Probe on the client the preflight already holds
and mint nothing.

**Trap 8 — SCOPE THE ASK HONESTLY OR THE SPEC OVERPROMISES.** A completion probe
covers only gateway-routed aliases, because `factory/workgraph/preflight.py:835`
— `aliases_to_check` filters on `factory/config.py:208` —
`routes_through_gateway`, which drops deterministic *and* subscription personas.
Neither has an alias to probe. Do not let a finding's wording imply the preflight
now proves every rung will work; it proves the gateway-routed ones will (FR-004).

**Trap 9 — THIS WIDENS 006's CONTRACT AND MUST SAY SO.**
`specs/006-interpreter-hardening/spec.md:113` states the preflight is "a read of
`/v1/models` and a key listing", and calls it the "cheapest possible fix for the
most operator time lost". That was a deliberate scoping decision, not an
oversight. A story that quietly makes the preflight do more without naming the
supersession leaves the next reader with two specs that disagree about what the
preflight is.

**Trap 10 — DO NOT FOLD THIS INTO 080.**
`specs/080-a-probe-tests-the-endpoint-the-attempt-will-use` is `state: draft` and
is about `install --verify` minting a key against `LiteLLMClient.from_env()` while
completing against the declared `gateway.base_url`. Adjacent, different, and
merging them would produce one spec that changes two subsystems for two reasons.

**Trap 11 — THE ANSWERED MODEL MUST RIDE OUT OF AN ACTIVITY, NEVER BE READ IN THE
WORKFLOW.** `factory/verify/models.py:998` — `compose_result` is called from
`factory/workgraph/workflow.py:2653` — `_verify`, which is workflow code: it may
not make a network call and may not read a response. The value has to travel on
the `JudgeVerdict` the judge activity already returns (FR-011), which is also why
`compose_result` needs no new argument at that call site. An implementer who
"just reads the model where the row is built" writes a non-deterministic
workflow. The same rule binds US3's declared upstream, for the same reason.

**Trap 12 — THE STORE READS ITS COLUMNS POSITIONALLY, AND THE VERDICT'S CODEC IS
A FIFTH EDIT.** `factory/verify/store.py:640` — `_migrate` and the 117-US2
comment above it spell the rule out: the new column goes **last** in the fresh
DDL and last in the migration, so a migrated store and a fresh one have the same
column order. The `_RESULT_COLUMNS` tuple (`factory/verify/store.py:711`) is
zipped positionally in `factory/verify/store.py:1031` — `_result_from_row`; a
divergent order does not raise, it silently hands every field of every row to the
wrong attribute (FR-012, FR-014). That is four sides: the DDL, `_migrate`,
`factory/verify/store.py:971` — `_result_values` and `_result_from_row`. The
fifth is the verdict's own JSON round trip, in the same file and easy to forget
because it is not a column: `factory/verify/store.py:1238` — `_judge_to_dict`
must write the new field and `factory/verify/store.py:1261` — `_judge_from_dict`
must read it. Read it with a default. `_judge_from_dict` reads its required keys
hard — `model_alias=data["model_alias"]` at `factory/verify/store.py:1275` —
`_judge_from_dict` — so a hard read raises `KeyError` on every verdict stored
before this spec, and no new test catches it because new tests round-trip through
the new writer. The precedent is `factory/verify/store.py:1281` —
`_judge_from_dict`'s `data.get("gates_shown", False)`, added by 116-US3 for
exactly this.

**Trap 13 — THE IMPLEMENTER ROUTE SEES NO RESPONSE BODY, AND NEITHER DOES AN
UNAVAILABLE JUDGE.** The CLI adapter never surfaces one, so US2 cannot cover
implementer attempts through it. Record what is observable and mark the rest
unobserved (FR-013, FR-014) rather than defaulting the answered field to the
alias, which would manufacture agreement — the exact shape of the tautology FR-009
is deleting. Two values, not one adjective: the empty string means "a body
answered and named no model", the sentinel stored as NULL means "no body was ever
held". Collapsing them makes a proxy that answers badly indistinguishable from a
route this factory cannot see. **The second value has two producers, and the one
that will be missed is the judge outage.** `factory/workgraph/workflow.py:2942` —
`_score` builds a `JudgeOutcome.UNAVAILABLE` verdict out of an error message,
holding no payload; a field defaulted to `""` on `JudgeVerdict` therefore records
"a body answered and named no model" on every judge outage — a false fact, on a
path this floor takes for real. Default the field to the sentinel and let the two
body-holding sites (`factory/verify/judge.py:653` — `parse_verdict` and
`factory/verify/judge.py:826` — `run_judge`) set the empty string when the
payload named none. `factory/verify/models.py:1070` — `compose_result` already
distinguishes the case, so there is no new predicate to invent.

**Trap 14 — DO NOT SEND A CREDENTIAL TO A DISCOVERED ADDRESS.** Spec 055's rule,
unchanged. The probe goes to the configured gateway. If an implementer finds
themselves resolving an upstream address from a scan result and authenticating to
it, the design has gone wrong.

**Trap 15 — THE MODULE THAT WRITES THE ROW HAS NO CREDENTIAL, NO ADDRESS, AND IS
FORBIDDEN FROM ACQUIRING ONE.** US3's comparison rides
`factory/activities/verify_activities.py:493` — `record_verification`, and the
obvious implementation — read `/model/info` there — cannot be written.
`factory/activities/verify_activities.py:467` — `RecordVerificationInput` carries
a result and an optional path and nothing else; the module docstring at
`factory/activities/verify_activities.py:54-57` states that `LITELLM_MASTER_KEY`
"sits in the same worker environment and has no path into these calls (FR-009)";
and `tests/test_verification_sweep.py:790` —
`test_this_component_never_names_the_master_key` is parametrised over
`COMPONENT_MODULES`, which includes this module (`tests/test_verification_sweep.py:138`),
so the file may not even spell the variable. An implementer who invents a
credential seam here breaks a constitution-V invariant and reddens a committed
sweep. **Take the read where the credential already arrives as data instead**:
`factory/activities/verify_activities.py:430` — `run_judge` holds
`factory/activities/verify_activities.py:420` — `RunJudgeInput`'s `virtual_key`
and `proxy_url` — the same pair `factory/verify/judge.py:942` — `_complete`
authenticates the completion with — so the declared upstream can be read there,
once, and ride out on the verdict beside the answered model. `record_verification`
then compares two strings it is already holding and makes no network call at all,
which is what makes FR-017's "must not delay the recording" buildable rather than
aspirational. Bound the read anyway — one attempt, no retry, a timeout no longer
than the judge's — and make it best-effort in the shape
`factory/workgraph/detector.py:636` — `_persist_finding` already uses: a
`/model/info` read that fails, or a `doctor.db` that is gone, leaves the verdict
returned and the row written.

**Trap 16 — THE ROW CARRIES TWO ALIASES AND THEY ARE DIFFERENT REQUESTS.** The
answered model comes out of the *judge's* completion. The attempt row's
`model_alias` describes the *implementer's* dispatch:
`factory/workgraph/workflow.py:2688` — `_verify` sets it from
`routing.model_alias`, and `factory/verify/models.py:946` —
`VerificationResult`'s docstring says all three builder fields are "carried in
from the resolution that dispatched the attempt and never re-derived at write
time". The judge's own alias is a separate field,
`factory/verify/models.py:608` — `JudgeVerdict`'s `model_alias`. Two wrong moves,
both cheap to make: comparing the answered model against the row's `model_alias`
files a mis-route finding on **every** attempt on this floor, because
`personas.yaml:271` and `personas.yaml:324` name different models; and setting
the row's `model_alias` from the judge to make the pair agree destroys 117-US2's
dispatch attribution, which is the only thing that can answer "which model built
this story" thirty days later. FR-012 forbids the second and FR-015 forbids the
first; US3-S5 is the control that proves neither was made.

**Trap 17 — A FAKE WHOSE `aclose()` IS A NO-OP CANNOT PROVE FR-010.** Every
double in this tree closes by doing nothing —
`tests/test_controlplane_llm_probe.py:81` — `_AliasRecordingLLMClient` and
`tests/test_controlplane_llm_probe.py:302` — `_RefusingForOneAliasLLMClient` both
have `async def aclose(self) -> None: pass`, and both define `chat_completion`.
Drive US1-S9 through one of those and the assertion "a served alias completes"
is green today, before any diff, and stays green after a diff that leaves the
`aclose()` at `factory/controlplane/verify.py:535` — `gather` exactly where it
is. The double has to model httpx's contract: `aclose()` marks it closed and a
later request raises `RuntimeError("Cannot send a request, as the client has been
closed.")` — deliberately **not** an `httpx.HTTPError`, because
`factory/usage/litellm_client.py:409` — `_call` catches only that and production
would let the `RuntimeError` through. Then the test is red until the lifetime is
fixed, and `tests/test_controlplane_verify.py:1147` —
`test_verify_llm_gather_against_live_double` is the second, real-transport proof
beside it.

**Trap 18 — US3's WHOLE SEAM RESTS ON A CREDENTIAL NOBODY HAS TESTED, AND
FR-017 IS BUILT TO SWALLOW THE FAILURE.** FR-015 reads `/model/info` with the
credential the judge activity already holds — `virtual_key`, which
`factory/workgraph/workflow.py:2926` — `_score` sets from `lease.key`, the
short-TTL per-attempt key `factory/usage/litellm_client.py:206` — `issue_key`
mints scoped to the persona's models (`factory/usage/litellm_client.py:225` —
`issue_key` sends `models`). Nothing in this repository establishes that such a
key can read `litellm_params` at all. The only `/model/info` reader here does the
opposite: `factory/discovery/llm_enrichment.py:52` — `enrich_aliases` takes a
`master_key_env`, reads it at `factory/discovery/llm_enrichment.py:75` —
`enrich_aliases`, and when it is unset returns every alias unclassified with the
detail "no credential to reach gateway metadata"
(`factory/discovery/llm_enrichment.py:83` — `enrich_aliases`). LiteLLM's
`/model/info` is role-sensitive, and a non-admin key can legitimately be served a
payload whose `litellm_params` is absent or whose `api_key`/`api_base` are
masked. **That is the trap, not merely the risk**: FR-017 says a payload "the
reader does not recognise" leaves the verdict returned and the row written —
silence — and every one of US3's five scenarios is driven through doubles, so the
diff satisfies all five, the judge PASSes, and the check never fires once in
production. Two moves stop that, and both are cheap because both happen before
the story is dispatched. First, operator step 6 takes the read with a key of the
kind `run_judge` holds, **not** with the master key sitting in the operator's own
shell, which would confirm the wrong premise; the payload it produces is what
FR-015's normalisation is written against and what the diff commits. Second, if
`litellm_params.model` does not survive that authorization, US3 is not dispatched
as written — the declared second source is the spend log,
`factory/usage/litellm_client.py:284` — `fetch_spend_log_rows`, already drained
per attempt lease at `factory/activities/usage_activities.py:511` —
`_read_final_usage`, whose rows LiteLLM records a model on. Re-cutting FR-015
onto that source is an operator act, not something an implementer improvises
mid-story. Redact `api_key` and `api_base` out of anything pasted either way: a
`/model/info` entry carries upstream credential material, and the standing rule
on this floor is that no secret enters git, encrypted or not.

## Sizing

**US1** — `factory/usage/litellm_client.py` (one method, plus the optional
timeout trap 6 names), `factory/workgraph/preflight.py` (the probe inside
`check_aliases`), `factory/controlplane/verify.py` (FR-009's one line and
FR-010's client lifetime), `tests/conftest.py` (the fake's completion route) and
`tests/test_controlplane_verify.py` (the live-double test whose docstring and
premise FR-003 reverses). Nine scenarios, all driven through doubles. This is the
story to watch for size: the committed evidence is bounded at **three** short
transcripts, a handful of lines each with alias lists elided —
(1) the preflight refusing against a stopped upstream and passing once it is
back, (2) the same preflight against a stopped proxy showing the two transport
findings and no third, and (3) `ergane doctor`'s LLM probe before and after, each
run preceded by the one-line `hasattr(LiteLLMClient, "chat_completion")` print so
the flip and its consequence sit in one block. tasks.md asks for exactly those
three and no more, because the diff limit is measured with evidence included
(D-050). The awkward parts are trap 4 — the shared fake — and traps 3 and 17 —
the closed client — not the logic.

**How much room US1 actually has, and where to spend it.** The deterministic
refusal is 64 KiB (`factory/verify/diffbounds.py`, `DIFF_INPUT_LIMIT`, D-050),
measured on the assembled diff with the pasted evidence inside it. Measured at
602a92c, this repository's tests run about 1.6 KB each in
`tests/test_predispatch_landing_preflight.py` (25.3 KB over sixteen tests) and
about 3.9 KB each in `tests/test_controlplane_verify.py` (55.0 KB over fourteen).
Ten new tests, roughly 11 KB of production edits across four files, the fake's
new route and three short transcripts put US1 at **roughly 45 KB against a 64 KiB
refusal** — real headroom, but the thinnest of the three stories and the only one
where a careless habit spends it. Two rules follow. Put T001–T007 in the existing
`tests/test_predispatch_landing_preflight.py`, beside the parity test
`tests/test_predispatch_landing_preflight.py:460` —
`test_both_dispatch_surfaces_return_the_same_findings` that FR-005 extends
anyway, rather than opening a new module that must carry its own imports,
fixtures and scaffolding before it asserts anything. And keep the three
transcripts to a handful of lines each with alias lists elided, as tasks.md
already bounds them. Do not split this into two PRs to buy room: FR-003, FR-009
and FR-010 have to land together, because defining the method is exactly what
reddens `tests/test_controlplane_verify.py:1147` —
`test_verify_llm_gather_against_live_double`, and a story that leaves that test
red is a story that lands a red trunk.

**US2** — `factory/verify/judge.py`, `factory/verify/models.py`,
`factory/verify/store.py`. One value carried through four verdict-construction
sites and one appended column with its migration, touching both sides of the row
codec (`factory/verify/store.py:971` — `_result_values` and
`factory/verify/store.py:1031` — `_result_from_row`) and both sides of the
verdict codec (`factory/verify/store.py:1238` — `_judge_to_dict` and
`factory/verify/store.py:1261` — `_judge_from_dict`). The migration test (US2-S4)
is the one that needs a fixture store; keep the pasted evidence to a single row
dump rather than a transcript.

**US3** — `factory/activities/verify_activities.py` (the `/model/info` read in
`run_judge`, and the comparison in `record_verification`), plus the verdict field
it rides out on in `factory/verify/models.py` and its codec in
`factory/verify/store.py` — US2's files, reachable because the
`depends_on_merged` edge orders US3 behind it. It reuses
`factory/doctor/store.py` for the write and reads `/model/info` the way
`factory/discovery/llm_enrichment.py:137` — `_fetch_litellm_model_info` does, on
the judge's own `proxy_url` and `virtual_key`. It needs no double for
`/chat/completions`, so it does not touch `tests/conftest.py`: `/model/info`
already has its own local double at `tests/test_llm_enrichment.py:32`. Small in
code — but **not automatically small in evidence, and that is the one way US3 can
be refused for size**. A LiteLLM `/model/info` payload on this host advertises
nineteen aliases and gives each a full `litellm_params` and `model_info` block;
pasted whole it is tens of KB against the same 64 KiB refusal, and it carries
`api_key`/`api_base` material into git. Bound it the way US1's is bounded: paste
the **single entry for the alias under test**, with `api_key` and `api_base`
redacted, plus the one completion payload — two short blocks, not two dumps.
Traps 1, 2, 15, 16 and 18 are the whole of its difficulty, and 18 is the one that
decides whether it is worth building at all.

**Disjointness.** US1 and US2 share no file at all — US1's five files and US2's
three are distinct, which is what lets them run concurrently. US3 reads what US2
wrote and is ordered behind it by `depends_on_merged`, so its slice may name US2's
files safely; it must not name US1's, and it does not.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. Before anything is built, reproduce the dead seam:
   `python -c "from factory.usage.litellm_client import LiteLLMClient; print(hasattr(LiteLLMClient, 'chat_completion'))"`
   prints `False`, and `ergane install --verify` reports its per-alias completion
   failing with an `AttributeError`. Both must be true afterwards in the other
   direction.
2. Run `ergane doctor` before and after US1 lands. Its LLM probe must report the
   same aliases completing in both runs. This is a *second* proof of FR-010, not
   the only one: `tests/test_controlplane_verify.py:1147` —
   `test_verify_llm_gather_against_live_double` drives the real client over a
   loopback listener and goes red on the closed client, so the suite catches it
   too. Run the command anyway — the suite's listener is not this host's gateway,
   and FR-010's failure mode is "every alias reports failing against a healthy
   proxy", which is the thing an operator sees first.
3. With the local gateway healthy, run a dispatch preflight. It must pass, and the
   time it adds must be one completion rather than one per alias.
4. Stop the upstream behind one alias while leaving the proxy running — the exact
   state observed on this host during triage, where `/v1/models` advertised
   nineteen aliases and every one returned a connection error. Run the preflight
   again. It must refuse and name the alias, the gateway address and the proxy's
   own words.
5. Stop the **proxy** itself. Exactly the two transport findings this preflight
   returns today must come back — the model-list read's and the key-list read's,
   worded as they are today — and no third finding from the probe. Two, not one:
   the reads are independent and each has its own transport arm.
6. **Before US3 is dispatched, not after**, take the two reads trap 2 demands and
   keep both payloads: one judge-shaped completion against a live gateway alias
   (what does the response's `model` say?) and `GET /model/info` for the same
   alias (what does `litellm_params.model` say?). **Make the `/model/info` read
   with a key of the kind `run_judge` actually holds — a per-attempt virtual key,
   minted the way `factory/usage/litellm_client.py:206` — `issue_key` mints one
   and scoped to the judge persona's models — and not with the master key sitting
   in your own shell.** Those are two different authorizations and only one of
   them is the premise FR-015 rests on, so run the same `GET /model/info` twice,
   once under each, and record whether `litellm_params.model` survives the
   virtual-key read. If it does, that entry — the alias under test only, with
   `api_key` and `api_base` redacted — is the payload FR-015's normalisation is
   written against and the one the diff commits. If it does not, **do not dispatch
   US3 as written**: FR-015 has to be re-cut onto the declared second source
   (trap 18 — `factory/usage/litellm_client.py:284` — `fetch_spend_log_rows`) or
   onto a seam that legitimately holds the master key, and that is an operator
   decision rather than an implementer's. A story dispatched without this read is
   a story whose fixtures the implementer will invent and whose check may never
   fire once in production while every one of its tests passes.
7. Point an alias at an upstream serving a different model and complete one
   attempt. The attempt row must carry the answered model beside the judge's
   alias — and its own `model_alias` must still be the implementer rung's — and a
   finding naming all three values must appear in `ergane findings list`.
8. After US1 lands, run `ergane install` far enough to reach its judge-persona
   step and confirm what this spec did **not** fix: the canary now fails with
   `RuntimeError: Cannot send a request, as the client has been closed.` rather
   than with `AttributeError`. That is
   `install/the-judge-canary-closes-its-http-client-then-uses-it` becoming
   visible, on purpose. If it instead reports passing, something widened past
   this spec's scope and the diff should be read again.

Step 4 is the falsifiable test of the preflight half: it is the condition that was
live on this floor while this spec was being written, and that today's preflight
passes cleanly. Step 6 is the falsifiable test of the recording half, and it must
happen before dispatch rather than after.
