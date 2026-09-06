# Implementation Plan: a probe tests the endpoint the attempt will use

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The privileged half, in five lines.** `factory/controlplane/verify.py:168` —
`_llm_client_factory` is the whole of it, and it is the seam the existing suite
already patches:

```python
def _llm_client_factory(config: ControlPlaneConfig.LLM) -> LiteLLMClient:
    """Build the real LiteLLM admin client from the environment.

    `gateway` is the only mode that reaches here: the parser refuses every other
    value before a probe is constructed (048-US2, D-048).
    """
    assert config.gateway is not None
    return LiteLLMClient.from_env()
```

`config` is handed in and then ignored — `factory/controlplane/verify.py:174`
asserts on it and `factory/controlplane/verify.py:175` throws it away. That line
is the defect in one statement.

**The ordinary half, in three lines, applying no precedence at all.** They open
`LLMProbe.gather` at `factory/controlplane/verify.py:428` — `gather`, and
`factory/controlplane/verify.py:432-434` are:

```python
        base_url = gateway.base_url
        api_key_env = gateway.master_key_env
        api_key = os.environ.get(api_key_env)
```

`base_url` then travels to every message and to the completion request. The
declared credential *variable name* travels with it, which is why FR-001 names
the credential and not only the URL: a diff that unifies the URL and leaves
`api_key_env` bound at `factory/controlplane/verify.py:433` still authenticates
to one server with another server's key.

**Where the admin half actually gets its answer.**
`factory/usage/litellm_client.py:136` — `from_env` has resolved through the
published precedence since 048-US1 landed on 2026-08-16;
`factory/usage/litellm_client.py:170-174` is the call:

```python
        try:
            resolution = resolve_llm_gateway()
            master_key = resolution.credential.read()
        except ControlPlaneResolutionError as error:
            raise LiteLLMError(str(error)) from None
```

Note the empty argument list. That is the second divergence FR-007 closes:
`factory/controlplane/resolve.py:391` — `_declared_config` falls back at
`factory/controlplane/resolve.py:412` to `resolve_config_path()`, so the admin
half reads the *default* file whatever file
`factory/controlplane/verify.py:1198` — `verify_controlplane_async` was handed.
Latent, not live: see trap 12's second half.

**What a probe is handed, which is less than you think.** The shared protocol is
`factory/controlplane/verify.py:57` — `Probe`, and its gather signature is one
line, `factory/controlplane/verify.py:62` — `gather`:

```python
    async def gather(self, config: ControlPlaneConfig) -> Any: ...
```

`factory/controlplane/config.py:114` — `ControlPlaneConfig` is six fields —
`factory/controlplane/config.py:117-122` — and none of them is a path.
`factory/controlplane/config.py:230` — `load_controlplane_config` does compute
one, at `factory/controlplane/config.py:238` (`label = str(path)`), and keeps it
only for its own error messages. By the time a probe runs, the path is gone.
Trap 12 is what follows from that.

That file did move under this spec, and the neighbour survey in the
frontmatter missed it: `e4b111b` (109-US1, 2026-08-26) added `gateway_mode` at
`factory/controlplane/config.py:130` to the `LLMGateway` dataclass the new
sibling takes as its `declared` parameter. It changes no instruction here, and
the load-bearing half of that is where `gateway_mode` is
*not* read: it reaches neither `factory/controlplane/resolve.py` nor
`factory/controlplane/verify.py`. Where it is read is `factory/controlplane/config.py`
itself (parsed at `factory/controlplane/config.py:389-403`, ordered at
`factory/controlplane/config.py:600`, re-emitted at
`factory/controlplane/config.py:632-633`) and, across a dozen lines,
`factory/cli/install.py`'s interview and apply paths — first at
`factory/cli/install.py:162`, not only there. A dataclass that has gained a field
once can gain another, so re-read it before you construct one.

Three more commits landed on `tests/conftest.py` after this spec was drafted and
the frontmatter survey missed those too: `b5bffad` (114-US3, 2026-08-28),
`625de8c` (104-US1, 2026-08-24) and `0371f1b` (088-US4, 2026-08-24). All three
are pure additions, none of them scrubs the LiteLLM pair, and all three of trap
5's anchors into that file were re-read at `602a92c` and still say what the trap
claims — `tests/conftest.py:525` — `_isolated_test_store` is still the autouse
fixture, `tests/conftest.py:563-564` still deletes only the Telegram pair, and
`tests/conftest.py:621` — `litellm_env` is still opt-in. The survey reads as
complete; these three are what completes it.

**The precedence itself, which this spec does not move.**
`factory/controlplane/resolve.py:334` — `_resolve_endpoint` and
`factory/controlplane/resolve.py:347` — `_resolve_credential` are five lines each
and they are the whole of FR-003:

```python
def _resolve_endpoint(
    env: Mapping[str, str],
    declared: ControlPlaneConfig.LLMGateway | None,
    label: str,
) -> EndpointRef:
    override = env.get(PROXY_URL_ENV)
    if override:
        return EndpointRef(override, PROXY_URL_ENV)
    if declared is not None and declared.base_url:
        return EndpointRef(declared.base_url, label)
    raise ControlPlaneResolutionError(_both_routes("endpoint", PROXY_URL_ENV, label))
```

`factory/controlplane/resolve.py:137` — `resolve_llm_gateway` reads the
declaration at `factory/controlplane/resolve.py:150-156`, calls those two at
`factory/controlplane/resolve.py:158-159`, and assembles the answer at
`factory/controlplane/resolve.py:160-165`.

**The shape FR-002 is asking for, already built for the other subsystem.**
`factory/controlplane/resolve.py:232` — `resolve_temporal_target` ends at
`factory/controlplane/resolve.py:249` with `return temporal_target_for(declared,
source=label, environ=env)`, and `factory/controlplane/resolve.py:252` —
`temporal_target_for` says why in its docstring at
`factory/controlplane/resolve.py:258-265`: *"`resolve_temporal_target` is written
in terms of this, so FR-016 is structural rather than promised — one function
decides both."* The gateway side has **no such sibling**; there is nothing
between `resolve_llm_gateway` and the private helpers. Adding one — a
`llm_gateway_for(declared, *, source, environ=None) -> GatewayResolution` beside
`temporal_target_for`, with `resolve_llm_gateway` rewritten to end in a call to
it — is the whole of US1's production change on the resolver side. Note the
`environ=` parameter: `temporal_target_for` takes one and trap 5 is why the
gateway sibling must too. Note the `source=` parameter as well: it is the label
that reaches `EndpointRef.source`, and it is the whole of what US2 can render.

**The consumer in the same file, which is the model for `_llm_client_factory`.**
`factory/controlplane/verify.py:178` — `_temporal_client_factory` is nine lines,
its docstring at `factory/controlplane/verify.py:181-188` is a written account of
this exact defect one subsystem over, and
`factory/controlplane/verify.py:192-193` is what the fixed gateway half should
look like:

```python
    target = temporal_target_for(config, source=_DECLARED_SOURCE)
    return await Client.connect(target.address, namespace=target.namespace)
```

`_DECLARED_SOURCE` is `"the control-plane config"`, defined at
`factory/controlplane/verify.py:46`. Its comment at
`factory/controlplane/verify.py:44-45` says *"Nothing renders it: findings report
the address, never where it came from."* US2 makes that false, and the comment is
part of US2's diff.

**The data US2 renders already exists and carries its own provenance.**
`factory/controlplane/resolve.py:120` — `GatewayResolution` is four fields, two
of which are the sources:

```python
class GatewayResolution:
    """Where the LLM gateway is, and which variable holds its credential.

    Four fields and no secret: the endpoint, the credential's variable *name*,
    and the source that won for each. FR-003 holds by construction, not care.
    """

    base_url: str
    base_url_source: str
    master_key_env: str
    master_key_source: str
```

`factory/controlplane/resolve.py:110` — `EndpointRef` and
`factory/controlplane/resolve.py:78` — `CredentialRef` each carry a `source`
too, and `CredentialRef`'s docstring states the FR-006 contract outright:
*"Deliberately not the credential."* A `source` is a variable name or a label —
never a path, once the probe is the caller.

**The seven message sites, all inside `LLMProbe.gather` or the static helper
below it.** `factory/controlplane/verify.py:493` (`/key/info` could not confirm),
`factory/controlplane/verify.py:519` (`/spend/logs/v2` did not answer),
`factory/controlplane/verify.py:544` (the key-probe failure detail),
`factory/controlplane/verify.py:577` (completion timeout),
`factory/controlplane/verify.py:582` (completion failed), and — through the
`base_url` parameter of `factory/controlplane/verify.py:625` —
`_classify_key_failure` — `factory/controlplane/verify.py:637` and
`factory/controlplane/verify.py:641`. Every one of them interpolates the single
local `base_url` bound at `factory/controlplane/verify.py:432`, which is why US1
alone makes the *address* right at all seven and US2's work there is the source
clause. The passing text at `factory/controlplane/verify.py:523-526` names no
address at all:

```python
                            key_probe_detail = (
                                f"gateway minted, constrained and revoked a "
                                f"short-TTL verify key; spend logs answered"
                            )
```

and it reaches the snapshot through
`factory/controlplane/verify.py:621`, which is `detail=f"{key_probe_detail};
{detail}"`. That composition is why US1's pinned string moves when US2 lands —
trap 11.

**The rendering surface, which is one string.**
`factory/controlplane/verify.py:662` — `evaluate` puts `snapshot.detail` into a
`Finding`, and `factory/controlplane/verify.py:1230` — `render_findings` prints
`[PASS] llm: <detail>`. There is no other surface: US2 changes strings, not a
report format.

**The tests that already exist here, including the one that runs both halves
for real.** `tests/test_controlplane_llm_probe.py` is 400 lines and
`tests/test_controlplane_verify_us1.py` is 623; both matter for the reason
traps 4, 5 and 13 give, not because they need editing. The third file is the
one to read before writing a line.
`tests/test_controlplane_verify.py:1147` —
`test_verify_llm_gather_against_live_double` does **not** patch
`_llm_client_factory`, so the real `LiteLLMClient.from_env()` runs, and its
docstring at `tests/test_controlplane_verify.py:1153-1156` says so outright:
*"the client has no chat_completion path, so the gather falls back to httpx
against the configured base_url — that is the code path being exercised
here"*. It is the only existing test that drives **both** halves of this probe
for real, and it is on the `httpx` branch trap 2 calls the sole production
path. It is backed by `tests/test_controlplane_verify.py:320` —
`_loopback_llm_listener`, a loopback HTTP double that already answers
`/key/generate`, `/key/info`, `/spend/logs/v2`, `/key/delete` and
`/chat/completions`. It parses request headers for one thing only, at
`tests/test_controlplane_verify.py:343-354`: it reads `Content-Length` and drops
everything else, `Authorization` included. That is precisely why no test in this
suite can currently see the credential half of FR-001 — the existing
`test_verify_llm_gather_against_live_double` runs with a declared
`ERGANE_LLM_MASTER_KEY` of `sk-fake-master` against an environment
`LITELLM_MASTER_KEY` of `sk-dummy` and passes either way — and why T001 extends
the double to record that header beside the base URL. **That double is the
harness T001, T004 and T005 extend rather than replace** — it is exactly the five-endpoint admin double those
tasks would otherwise write from scratch, and the sizing below is priced on
reusing it. It is also the test most likely to falsify this change before the
gate does: it sets `LITELLM_PROXY_URL` and the declared `llm_base_url` to the
same loopback address, so it should stay green under this spec — a prediction
to check, not an assumption. Spec 132's US1 also edits it (trap 9), so expect
it to move under you.

## Traps

**Trap 1 — the asymmetry is "one precedence and no precedence", not "two
precedences", and the plan you may have read before said otherwise.** The
2026-08-21 frontmatter block calls the admin half "ENVIRONMENT-FIRST" and implies
the ordinary half is declaration-first. It is not: it applies no precedence at
all. `factory/usage/litellm_client.py:170-174` shows the admin half going through
`resolve_llm_gateway()`, and `factory/controlplane/verify.py:432-434` shows the
ordinary half reading three dataclass attributes. The wrong move is to go hunting
for a second precedence to delete; there isn't one, and FR-002 is satisfied by
giving the ordinary half the resolution it never had.

**Trap 2 — `factory/controlplane/verify.py:560-566` is not a fallback, it is the
only path production takes.** The guard above it,
`factory/controlplane/verify.py:556`, is `if hasattr(client, "chat_completion")`,
and `factory/usage/litellm_client.py:108` — `LiteLLMClient` defines no such
method — its constructor is at `factory/usage/litellm_client.py:118` —
`__init__`, `from_env` at
`factory/usage/litellm_client.py:136`, and the twenty methods that follow run to
the end of the class; `chat_completion` is not among them. Only the test fakes in
`tests/test_controlplane_llm_probe.py` define it, so every existing test takes
the branch production never takes. The wrong move is to treat the `httpx` block
as dead code and fix only the `chat_completion` call; FR-001 fails on every real
install if you do. (Spec 132 filed this as an unfiled defect on 2026-09-04; do
not fix it here — see trap 9.)

**Trap 3 — two variables assigned from one source is not FR-002.** It passes
US1-S1 and comes apart at the next edit. The shape required is the one at
`factory/controlplane/resolve.py:249`, where `resolve_temporal_target`'s last
statement *is* a call to `temporal_target_for`. US1-S4 is the test that tells the
difference: it patches one symbol and requires both halves to follow. The wrong
move is `resolution = resolve_llm_gateway(...)` followed by `base_url =
resolution.base_url` in one place and a second, independently written read in the
other.

**Trap 4 — the seam under test is the seam the existing suite fakes, and both
obvious doubles delete the code under test.** The first wrong move is the one
the suite hands you: `tests/test_controlplane_llm_probe.py:172` is
`monkeypatch.setattr(verify_module, "_llm_client_factory", recording_factory)`,
and `tests/test_controlplane_llm_probe.py:324` does it again. A new test that
patches `_llm_client_factory` replaces the exact function FR-001 and FR-007
change, and passes against today's tree. The second wrong move is subtler and
an earlier version of this plan recommended it: swapping
`verify_module.LiteLLMClient` for a **from-scratch fake**.
`factory/usage/litellm_client.py:136` — `from_env` is a classmethod whose last
statement is `cls(base_url=resolution.base_url, master_key=master_key, ...)`,
so it is the *real* `from_env` running `resolve_llm_gateway()` that makes
today's tree reach `factory/controlplane/resolve.py:412`'s
`resolve_config_path()`. A fake carrying its own `from_env` reaches nothing:
US1-S5's "fails if `resolve_config_path` is consulted" then passes *before* the
change as well as after — a criterion a test-only diff satisfies, which is the
`readiness-proves-a-thing-is-declared` class this spec sits next to — and
US1-S1's *before* transcript records addresses the fake invented rather than
addresses production resolved. **So any double for the admin client MUST
subclass `factory/usage/litellm_client.py:108` — `LiteLLMClient`**, overriding
only the request methods, or record construction by wrapping
`factory/usage/litellm_client.py:118` — `__init__`; assert on the `base_url` the
constructed client carries, which `factory/usage/litellm_client.py:126` sets as
`self.base_url = base_url.rstrip("/")`. Handing the real class an `httpx`
transport — what `tests/test_controlplane_verify.py:320` —
`_loopback_llm_listener` effectively does with a real socket — is equally
acceptable and equally strict. Patching `_llm_client_factory`, or substituting a
class that does not inherit `LiteLLMClient`, is forbidden in US1's test file.

**Trap 5 — the resolver reads the ambient environment unless you hand it one,
the gate's own shell exports both LiteLLM variables, and the probe-level tests
cannot hand it a mapping at all.** Both halves of the hazard, endpoint and
credential: `scripts/ergane-env.sh:72-73` emits `LITELLM_PROXY_URL` (defaulting
to a loopback address on port 4000) and `LITELLM_MASTER_KEY` unconditionally into the
shell the gate runs in, and `tests/conftest.py:525` — `_isolated_test_store`,
the session-autouse fixture whose whole job is that "the operator's exports
cannot reach a test", deletes only the two Telegram variables
(`tests/conftest.py:563-564`). Nothing scrubs the LiteLLM pair;
`tests/conftest.py:621` — `litellm_env` sets them but is opt-in. So after T009
every existing probe test resolves `base_url` to that loopback default and
`api_key_env` to `LITELLM_MASTER_KEY` instead of the declared values —
`tests/test_controlplane_llm_probe.py:204` declares `ERGANE_LLM_MASTER_KEY`, and
`factory/controlplane/resolve.py:347` — `_resolve_credential` prefers
`LITELLM_MASTER_KEY` whenever it is set.

**The traced conclusion, so you meet a green suite as a prediction rather than
as luck**: no existing test asserts a declared base_url inside a detail string;
none drives the "not set" branch at `factory/controlplane/verify.py:437`; every
fake in `tests/test_controlplane_llm_probe.py` defines `chat_completion`, so the
`httpx` block that consumes `base_url` is skipped there; and
`tests/test_controlplane_verify.py:320` — `_loopback_llm_listener` ignores the
`Authorization` header. A dispatched node is safe either way —
`factory/verify/gates.py:119` is an eleven-name allowlist carrying neither
variable — so this is an operator-local annoyance, not a node failure. If a test
does go red on it, that is the reason, and it is not this spec's defect.

The shape to build: the sibling takes `environ=` exactly as
`factory/controlplane/resolve.py:252` — `temporal_target_for` does, so the
resolver is unit-testable directly and a later caller can inject; the probe's own
call sites pass none and fall through to `os.environ`, exactly as
`factory/controlplane/verify.py:192` does today for Temporal. **Do not read this
as "every test hands in a mapping": no probe-level test can.**
`factory/controlplane/verify.py:62` — `gather` takes only `config` and trap 12
forbids widening it; `factory/usage/litellm_client.py:136` — `from_env` takes
only `transport` and `timeout` and FR-008 forbids widening that. T001 through
T006 therefore inject with `monkeypatch.delenv("LITELLM_PROXY_URL",
raising=False)` and `monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)`
followed by `monkeypatch.setenv` — which is what
`tests/test_controlplane_llm_probe.py:204` already does. The wrong move is a
test written around a mapping parameter that does not exist, or a plumbing
change to invent one.

**Trap 6 — do not call `credential.read()` before the graceful branch.**
`factory/controlplane/resolve.py:91` — `read` raises
`ControlPlaneResolutionError` when the variable is unset, and
`factory/controlplane/verify.py:1198` — `verify_controlplane_async` catches any
exception a probe raises and reports `probe failed unexpectedly: <type>: <msg>`.
That would replace `factory/controlplane/verify.py:437-443`'s helpful *"X is not
set; no credential to complete a round trip"* with a stack-trace-flavoured line,
on the single most common first-run condition. Resolve the *names* early; read the
value no earlier than today does, at `factory/controlplane/verify.py:434`.

**Trap 7 — the five-step key sequence is not yours.**
`factory/controlplane/verify.py:467-537`: mint, confirm, check the model
constraint, check the spend log, revoke — 061-US1, landed, verified live by
control and mutation on 2026-08-20. Your diff changes which client performs it
and which address the messages inside it name. It does not change what it
performs, and it does not move the `finally` at
`factory/controlplane/verify.py:528-537` that guarantees a key is never leaked.

**Trap 8 — there are seven message sites and the older enumeration listed five.**
`factory/controlplane/verify.py:493` and `factory/controlplane/verify.py:519`
were missing from it. They interpolate the same `base_url` as the rest, so a diff
built to the short list ships two messages whose source clause is missing and
satisfies FR-005 only by accident. Fixing the caller at
`factory/controlplane/verify.py:486` covers the two inside
`factory/controlplane/verify.py:625` — `_classify_key_failure`, because that
function takes the address as a parameter — and if the source must travel with
the address, that helper's signature is where it travels.

**Trap 9 — spec 132 is being refined against the same method, and what it owns
is wider than two lines.** 132's FR-003 does **not** edit
`factory/controlplane/verify.py:556`: it requires the completion be issued
through one method on `factory/usage/litellm_client.py:108` — `LiteLLMClient`,
i.e. it *defines* `chat_completion` there. The consequence for you is that the
`hasattr` guard becomes permanently true, which retires trap 2's claim that the
`httpx` block is the only path production takes — without making one line of
your diff wrong, because both branches read the same `base_url`. Its FR-009
replaces the `model=alias` tautology inside the `LLMAliasResult` construction at
`factory/controlplane/verify.py:585-591` (the tautology itself is
`factory/controlplane/verify.py:587`). Its FR-010 is the one that will collide:
it restructures the admin client's lifetime around the `finally` at
`factory/controlplane/verify.py:528-537` — specifically the `await
client.aclose()` at `factory/controlplane/verify.py:535`, which today runs
before `factory/controlplane/verify.py:548` — `_probe_one_alias` is ever
called — and trap 7 tells you to leave that `finally` exactly as it is. 132 also
names `tests/test_controlplane_verify.py:1147` —
`test_verify_llm_gather_against_live_double` as a file its US1 must edit. So:
change the address and the source inside `factory/controlplane/verify.py:577`
and `factory/controlplane/verify.py:582`; leave the `hasattr` guard, the
`LLMAliasResult` construction and the whole `finally` block untouched. Whichever
spec lands second meets a conflict in this method; the answer is a rebase, and
the wrong move is a tidy-up commit that takes both. 132's own provenance says the
two specs are "adjacent, different, and not to be folded in".

**Trap 10 — the judge sees the diff and the criteria, nothing else**
(Constitution Principle VIII, D-037). US1-S1 needs the *before* transcript as
well as the after: the recording that today's tree mints at B and completes at A
is what makes the fix legible to a reader holding only the diff. Paste tool
output; do not describe it, and do not revert a change to demonstrate it, because
a revert erases its own evidence.

**Trap 11 — US1's pinned detail string is US2's to update, and nobody warns you
twice.** US1-S3 pins the snapshot detail character-for-character in
`tests/test_080_us1_probe_mints_where_the_attempt_runs.py`. The passing half of
that string is the text at `factory/controlplane/verify.py:523-526`, composed
into the snapshot at `factory/controlplane/verify.py:621` — and FR-004 requires
US2 to put an address and a source into exactly that text. So US1's test goes red
the moment US2 lands, on the `depends_on_merged` edge that guarantees US2 sees
it. This is expected and it is US2's task, not a sign US2 is wrong: update the
pin, show the old and the new string in the same diff, and assert nothing else in
that test moved. The wrong moves are both available and both bad — weakening
FR-004's rendering to keep US1's test green, or deleting the pin instead of
updating it.

**Trap 12 — the probe cannot know which file it came from, and the two ways to
get one are each forbidden.** FR-004 and FR-009 say "the source the resolution
carries" and mean it literally.
`factory/controlplane/verify.py:57` — `Probe` hands `gather` a parsed
`factory/controlplane/config.py:114` — `ControlPlaneConfig` with no path field;
`factory/controlplane/config.py:230` — `load_controlplane_config` computes the
label at `factory/controlplane/config.py:238` and keeps it for its own errors.
The two tempting escapes: **plumbing the path** means changing the shared
protocol at `factory/controlplane/verify.py:62` — `gather`, the loop at
`factory/controlplane/verify.py:1204`, all eight probes in
`factory/controlplane/verify.py:1183-1192` and 43 `.gather(` call sites across 15
test files — against a story this plan sizes at one production file; **calling
`resolve_config_path()`** re-opens the default file and breaks FR-007, which is
the defect it was meant to describe. Render `GatewayResolution.base_url_source`:
it is `PROXY_URL_ENV` when the variable won, and the `source=` label the probe
passed when the declaration won. That label is `_DECLARED_SOURCE` at
`factory/controlplane/verify.py:46` unless US1 chooses a better word, and its
comment at `factory/controlplane/verify.py:44-45` — *"Nothing renders it"* —
stops being true the moment US2 lands.

**Trap 13 — gather the probe, not the registry.** US1-S5 is about one probe, and
`factory/controlplane/verify.py:1198` — `verify_controlplane_async` runs all
eight in `factory/controlplane/verify.py:1183-1192`, including the host probe,
the forge capability probe and Temporal. The existing suite treats that as a
hazard: `tests/test_controlplane_host_probe.py:277-306` is a meta-test asserting
that every `verify_controlplane_async` call in that module patches
`_host_seam_factory`. It parses only its own file, so a new test file escapes the
assertion but not the consequence — a slow, flaky test failing on something this
spec does not touch. Do what the existing LLM tests do at
`tests/test_controlplane_llm_probe.py:207-208`: construct `LLMProbe()` and await
`gather` on a config parsed from the non-default file, with `resolve_config_path`
patched to raise. Copy that *shape* and not that file's fixture: the autouse
fixture at `tests/test_controlplane_llm_probe.py:172` patches
`_llm_client_factory` away for every test in it, which trap 4 forbids here — a
`gather` driven that way never reaches `resolve_config_path` on today's tree
either, and US1-S5 goes green on a diff that changed no production line.

**Trap 14 — one test file per story, plus the shared double US1 may extend and
the pin US2 inherits.**
- US1 → `tests/test_080_us1_probe_mints_where_the_attempt_runs.py`, and
  `tests/test_controlplane_verify.py:320` — `_loopback_llm_listener`, extended to
  record the base URL **and the `Authorization` header** of every request it is
  handed rather than replaced by a second double. The header half is not optional:
  US1-S1 asserts on it, and the listener discards it today at
  `tests/test_controlplane_verify.py:343-354`.
- US2 → `tests/test_080_us2_probe_names_the_endpoint_it_used.py`, **and** the
  pinned string inside US1's file, for the reason trap 11 gives.

Both stories edit `factory/controlplane/verify.py`; the `depends_on_merged` edge
is what keeps them from racing.

**Trap 15 — the seventh message site renders on no input, and the driver an
earlier version of T016 named for it does not exist.**
`factory/controlplane/verify.py:544` is
`detail=key_probe_detail or f"LLM gateway key-management probe failed at {base_url}"`.
The `or` never fires. `key_probe_detail` starts at `None`
(`factory/controlplane/verify.py:474`) and `key_probe_passed` at `False`
(`factory/controlplane/verify.py:475`), and every path that reaches
`factory/controlplane/verify.py:539`'s `if not key_probe_passed` has already
assigned a non-empty string: `issue_key` raising assigns at
`factory/controlplane/verify.py:486` from
`factory/controlplane/verify.py:625` — `_classify_key_failure`, whose two returns
(`factory/controlplane/verify.py:635-639` and
`factory/controlplane/verify.py:640-643`) are both non-empty f-strings;
`get_key_info` raising assigns at `factory/controlplane/verify.py:491-494`; an
unconstrained key assigns at `factory/controlplane/verify.py:500-504`; a spend-log
failure assigns at `factory/controlplane/verify.py:517-521`; and the one path that
leaves the detail unwritten is the success path, which sets `key_probe_passed`
true at `factory/controlplane/verify.py:527`. So T020 edits that site's source
clause like the other six and the diff is what proves it — US2-S2 asks for six
driven branches, not seven.

The wrong move is to go looking for the driver anyway, and an earlier T016 named
one that is not a driver at all: *"an unconstrained key with no detail"* reaches
`factory/controlplane/verify.py:500-504`, which does set a detail, names no
gateway address, and is therefore outside FR-005's seven sites entirely. If you
want the defensive branch exercised regardless, exactly one mechanism reaches it
— neutralise the helper, `monkeypatch.setattr(verify_module.LLMProbe,
"_classify_key_failure", staticmethod(lambda exc, base_url: ""))`, then make
`issue_key` raise — and it is optional; no scenario requires it and no scenario
is weakened by its absence.

**Trap 16 — the sibling is one function with two bindings, and the shape T007 and
T008 point at is what makes it two.** `factory/controlplane/verify.py:32` is
`from factory.controlplane.resolve import temporal_target_for` — a module-scope
*name binding* in `verify.py` — while `factory/controlplane/resolve.py:249` calls
that function as a module global of `resolve.py`. Copy that shape for the gateway
sibling and one function answers to two names. A single `monkeypatch.setattr`
then moves half of what US1-S4 asserts: patching verify's binding moves both probe
halves and leaves `factory/controlplane/resolve.py:137` — `resolve_llm_gateway`
answering the declaration, while patching resolve's binding moves
`resolve_llm_gateway` and not the probe. So US1-S4 and T004 say "by name in every
module that binds it": two `setattr` lines naming one function, which is one
symbol replaced, not two.

The alternative shape is equally acceptable and needs only one patch: import the
module rather than the name — `from factory.controlplane import resolve`, then
`resolve.llm_gateway_for(declared, source=_DECLARED_SOURCE)` — which leaves
`verify.py` holding no binding of its own. The wrong moves are the two that hide
the hazard instead of meeting it: weakening US1-S4 to whichever single patch you
tried first, and moving the import inside `_llm_client_factory` to dodge the
second binding. A function-scope import is what
`factory/usage/litellm_client.py:162-168` does and it says why in its own comment
— an import cycle `factory.controlplane.resolve` would otherwise close — and no
such cycle exists in this direction, so there is no reason to reach for it here.

## Sizing

**US1 touches two production files, a third that must not move, and one new
test file.**
`factory/controlplane/resolve.py` gains the `llm_gateway_for` sibling and loses
three lines from the body of `factory/controlplane/resolve.py:137` —
`resolve_llm_gateway`, which becomes a call to it.
`factory/controlplane/verify.py` changes
`factory/controlplane/verify.py:168` — `_llm_client_factory` to build a client
from a resolution instead of calling `from_env`, and changes
`factory/controlplane/verify.py:432-434` to read the same resolution.
The third file, `factory/usage/litellm_client.py`, **should not move at all**:
`factory/usage/litellm_client.py:118` — `__init__` already accepts `base_url`
and `master_key` directly (`factory/usage/litellm_client.py:118-133`), FR-008
forbids changing `from_env`, and T010 says so. Count it as a file the diff is
expected not to contain. Six scenarios, six short tests, plus two pasted
transcripts — priced on **reusing**
`tests/test_controlplane_verify.py:320` — `_loopback_llm_listener` rather than
writing a five-endpoint admin double, which is the difference between a story
that fits and one that does not. US1 therefore also touches
`tests/test_controlplane_verify.py` to extend that double, recording the base URL
**and the `Authorization` header** of every request it is handed — a few lines
inside the header loop at `tests/test_controlplane_verify.py:343-354`, which today
keeps `Content-Length` and nothing else; it must not weaken
`tests/test_controlplane_verify.py:1147` —
`test_verify_llm_gather_against_live_double`. Well inside the 64 KiB refusal
(`factory/verify/diffbounds.py`, D-050).

**The `from_env` call sites FR-008 protects, counted rather than remembered.**
Six, in five modules: `factory/activities/usage_activities.py:169`,
`factory/cli/nouns/__init__.py:34`, `factory/controlplane/canary/probe.py:31`,
`factory/controlplane/canary/probe.py:156`, `factory/doctor/probes.py:267` and
`factory/workgraph/cli.py:125`. The seventh call site is
`factory/controlplane/verify.py:175`, which is the one US1 changes. `from_env`'s
own docstring at `factory/usage/litellm_client.py:144-147` says "five production
callers" — that number is stale and is not the count to work from.

**US2 touches one production file and two test files.**
`factory/controlplane/verify.py`, at the seven message sites, the passing text at
`factory/controlplane/verify.py:523-526` and the `_DECLARED_SOURCE` comment at
`factory/controlplane/verify.py:44-45`; its own
`tests/test_080_us2_probe_names_the_endpoint_it_used.py`; and the pinned string
in `tests/test_080_us1_probe_mints_where_the_attempt_runs.py` (trap 11). Four
scenarios, four tests plus the pin update, three pasted reports. Still smaller
than US1.

**The two stories share `factory/controlplane/verify.py` and nothing else, and
they do not split at a line number.** An earlier draft of this section said US1
works above `factory/controlplane/verify.py:477` and US2 below it. That is false
and worth stating: the variable US1 rebinds at
`factory/controlplane/verify.py:432` is read at all seven message sites below it,
which is exactly why FR-005's address half arrives already satisfied and its
source half does not. The split is by *kind* — US1 changes which client and which
address; US2 changes what the strings say — and the `depends_on_merged` edge, not
a line boundary, is what keeps them apart. There is no story pair here that
shares no production file.

## Verification the operator will run, independent of the gate

1. **Declare a gateway at one address, export `LITELLM_PROXY_URL` naming another,
   and run `ergane install --verify` with both servers logging.** Read the two
   access logs: after this spec only one of them has entries. Today the mint lands
   on the exported one and the completion on the declared one.
2. **Run it with the two in agreement** and diff the printed report against the
   run recorded before the change. After US1 nothing may differ at all; after US2
   nothing may differ except the new address and source clause.
3. **Falsify FR-007 by direct call, because no route reaches it with a path.**
   `ergane install` has no `--config`, and there are six callers of
   `verify_controlplane` in the tree, none of which hands it a non-default path:
   three pass no argument at all — `factory/cli/nouns/install.py:40`,
   `factory/cli/init.py:174` and `factory/supervision/engine_upgrade.py:106` —
   and the three inside `factory/cli/install.py`
   (`factory/cli/install.py:954`, `factory/cli/install.py:1185`,
   `factory/cli/install.py:1279`) all pass the `path = resolve_config_path()`
   bound once at `factory/cli/install.py:901`. So write a
   third config at `/tmp/other.toml` declaring a third address, leave the default
   file declaring its own, and run
   `python -c "import asyncio; from factory.controlplane.verify import
   verify_controlplane_async, render_findings;
   print(render_findings(asyncio.run(verify_controlplane_async('/tmp/other.toml'))[0]))"`.
   The llm line must name `/tmp/other.toml`'s gateway. Today the admin half reads
   the file at `resolve_config_path()` instead. This is the latent row of the
   truth table: it proves FR-007, and it is not evidence of a symptom any install
   can currently show.
4. **Export the master key with a recognisable value and read the whole report**,
   confirming the value appears nowhere and the variable's name appears.
5. **Re-derive `workgraph.json` before dispatch** and confirm
   `us1.requirement_keys` ends in FR-008 and `us2.requirement_keys` in FR-009. The
   file on disk beside this plan was compiled before FR-007, FR-008 and FR-009
   existed, and `ergane build start` reads a compiled graph off disk.
