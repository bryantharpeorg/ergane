# Implementation Plan: a probe tests the endpoint the attempt will use

**Spec**: `specs/080-a-probe-tests-the-endpoint-the-attempt-will-use/spec.md`

## What already exists, and where

**Every line number below was verified on 2026-08-21 by printing that exact line
individually** (`sed -n '<n>p' <file>`). Check each one anyway.

**The split, which is the whole defect:**

- `factory/controlplane/verify.py:160` — `def _llm_client_factory(config: ControlPlaneConfig.LLM) -> LiteLLMClient:`
- `:161` — its docstring's first line, *"Build the real LiteLLM admin client from
  the environment."* The behaviour is documented; it is the asymmetry with the
  other half that is wrong.
- `:166` — `assert config.gateway is not None`
- `:167` — `return LiteLLMClient.from_env()`  ← **the environment-first half**
- `:315` — `base_url = gateway.base_url`  ← **the declaration half**
- `:452-453` — the completion fallback's `httpx.AsyncClient(base_url=base_url.rstrip("/"), ...)`
- `:436` — `detail=key_probe_detail or f"LLM gateway key-management probe failed at {base_url}"`
  — a failure message naming an address the failing call never used.
- `:469`, `:474`, `:529`, `:533` — four more messages interpolating the same
  `base_url`. All of them are US2's subject.

**The precedent to copy, and it is in the same file:**

- `factory/controlplane/verify.py:170` — `async def _temporal_client_factory(config: ControlPlaneConfig.Temporal) -> Any:`
- `:171` — *"Build the real Temporalio client, under the one precedence (048-US4)."*
- `:173-179` — the docstring recording what this looked like before it was fixed:
  it read `config.address or os.environ.get("TEMPORAL_ADDRESS", ...)`, the
  fallback never fired, and the probe dialled the declared address while the
  worker connected elsewhere. **That is this defect, one subsystem over, already
  solved.**
- `:184` — `target = temporal_target_for(config, source=_DECLARED_SOURCE)`
- `:185` — `return await Client.connect(target.address, namespace=target.namespace)`

**The resolver the gateway half should read:**

- `factory/controlplane/resolve.py:137` — `def resolve_llm_gateway(`
- `:150-156` — the declaration read
- `:158` — `endpoint = _resolve_endpoint(env, declared, label)`
- `:159` — `credential = _resolve_credential(env, declared, label)`
- `:160-165` — `GatewayResolution`, which **already carries `base_url_source` and
  `master_key_source`**. US2's data exists; nothing renders it.
- `:111-116` — `Endpoint`, with its own `source` field.
- `:124-135` — `GatewayResolution`'s definition and its `credential` property.
- `:252` — `temporal_target_for`, and its docstring at `:258-264` explaining why
  `resolve_temporal_target` is written in terms of it: *"one function decides
  both."* FR-002 is asking for that shape.

**The constructor being called today:**

- `factory/usage/litellm_client.py:135` — `@classmethod`
- `:136` — `def from_env(`
- `:142` — *"Build a client from what the host declared, environment first."*
- `:144-145` — the note that `from_env` has **five production callers** and is
  deliberately not renamed. **Do not change `from_env`.** Change which
  constructor the probe uses, or give it a sibling that takes a resolution.

## Traps

**1. Do not "fix" this by reading the declaration everywhere.** US1-S2 is the
control. The precedence is environment first and it is deliberate — an operator
exporting `LITELLM_PROXY_URL` is overriding on purpose. The defect is that two
halves disagree, not that either one is wrong on its own.

**2. Do not change `from_env`.** Five production callers
(`factory/usage/litellm_client.py:144-145`). Changing its precedence to fix the
probe would change what the ledger, the key minter and the usage poller do, none
of which are in this spec.

**3. Two variables from one source is not FR-002.** It satisfies today's
scenarios and comes apart at the next edit. `temporal_target_for` is the shape:
one function that both readings are *written in terms of*. US1-S4 is the test
that tells the difference.

**4. `GatewayResolution` already carries the sources.** US2 is mostly rendering,
not plumbing. If you find yourself adding a field to carry "where did this come
from", read `factory/controlplane/resolve.py:124-135` again first.

**5. You are adding print statements next to a credential.** US2-S4 and SC-006.
`GatewayResolution` carries `master_key_env` — the *name* of the variable, which
is safe — and the client holds the key itself, which is not. Assert the absence;
do not assume it.

**6. Do not touch the five-step key sequence.** `factory/controlplane/verify.py:361-423`.
Mint, confirm, check model constraint, check spend log, revoke: that is 061-US1,
it landed, and it was verified live by control and mutation on 2026-08-20. Your
diff changes which client performs it, not what it performs.

**7. The control that matters most is the boring one.** US1-S3: on every real
install the environment and the declaration agree, and the probe must behave
exactly as it does today. If that test needs changing to pass, the change is
wrong.

**8. The judge sees the diff and the criteria, nothing else** (Constitution
Principle VIII). SC-001 needs the *before* run as well as the after — the
demonstration that today's tree reports success on a mint-incapable declared
gateway is what makes the fix legible.

**9. One test file per story.**
- US1 → `tests/test_probe_mints_where_the_attempt_runs.py`
- US2 → `tests/test_probe_names_the_endpoint_it_used.py`
Both stories edit `factory/controlplane/verify.py`; the `depends_on_merged` edge
is what keeps them from racing.

## Sizing

**US1 is small** — one constructor call and the seam that makes both halves read
one resolution. Its risk is entirely trap 3: the two-line version passes the
tests and is wrong.

**US2 is small** and is mostly rendering data that
`factory/controlplane/resolve.py:160-165` already computes. Six message sites
interpolate `base_url` today; changing them is mechanical, and the only care
needed is trap 5.

**Neither story should need a second attempt.**

## Verification the operator will run, independent of the gate

- **Point the config at a gateway that cannot mint, export a real one, and run
  `ergane install --verify`.** That is the whole spec in one command, and today
  it reports success.
- **Run it with the two in agreement** and confirm nothing about the output
  changed except the new source line.
- **Read the report with a master key exported** and confirm the key is not in
  it.
</content>
