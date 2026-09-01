# Implementation Plan: a credential outlives the night

Every file:line below was read from `ergane-buildout` at `30246c7` on 2026-08-31
after the worker rotation, and each was verified to resolve to the symbol named. Do
not trust an anchor that has moved; re-read before editing.

## What already exists, and where

**The environment is constructed, not filtered.** `attempt_env`
(`factory/workgraph/adapter.py:908`) builds the child environment from nothing: it
sets `HOME` unconditionally, adds `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`
only when `routes_through_gateway`, adds `CLAUDE_CODE_MAX_CONTEXT_TOKENS` when a
window is declared, and then merges the passthrough at `:941`:

```python
env.update({name: source[name] for name in PASSTHROUGH_ENV if source.get(name)})
```

Its docstring states the reason in full, and it is constitution V: "an allowlist, so
`LITELLM_MASTER_KEY` and `TELEGRAM_BOT_TOKEN` are absent by omission rather than by
redaction". That reasoning is correct and this spec does not weaken it.

**The passthrough has three members**, `PASSTHROUGH_ENV` (`:102`):

```python
PASSTHROUGH_ENV: tuple[str, ...] = ("PATH", "LANG", "TERM")
```

**The sandbox sets its own names, separately.** In the bwrap argument vector
(`:580-600`), after `--clearenv`, the code loops `PASSTHROUGH_ENV` and then an
explicit tuple: `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`,
`CLAUDE_CODE_MAX_CONTEXT_TOKENS`, `ATTEMPT_ARCHIVE`, and six git identity variables.
This is a *second* mechanism, not a rendering of the first.

**The subscription branch already refuses a missing credential.** At `:1026-1034`:

```python
if context.agent == SUBSCRIPTION_AGENT:
    credential_path = discover_subscription_credential()
    if credential_path is None:
        raise AdapterError(
            "subscription credential not found: no .claude/.credentials.json ..."
            "Run `claude auth login` on the worker host."
        )
_seed_node_home(home, credential_path)
```

US2 extends this refusal; it does not build a new one.

**The credential search is a host fact.** `discover_subscription_credential`
(`:823`) searches `$XDG_CONFIG_HOME/claude/.credentials.json`, then
`~/.config/claude/.credentials.json`, then `~/.claude/.credentials.json`, and returns
`None` when none exist. It takes an optional `operator_home` so tests drive discovery
without touching the host.

**The seed writes two files.** `_seed_node_home` (`:859`) writes `.gitconfig` and,
when a credential path is given, copies it to `~/.claude/.credentials.json` inside the
node home at `0600` (`:892`).

**095's pre-agent machinery is landed and live in the worker.**
`Termination.PRE_AGENT_FAILURE`, `PRE_AGENT_WINDOW_S = 60.0` (`:122`), the
classification at `:1494-1499`, and on the ladder side `pre_agent_failures_spent`
(`factory/verify/ladder.py:393`), `pre_agent_bound_spent` (`:228`, `:311`) and the
`max_pre_agent_failures` dial. US2's refusal is a *stronger* case than a pre-agent
failure — it happens before the fork — and it should reuse this shape rather than
inventing a parallel one.

**The routing predicate is a string comparison in two places.** `:1046` reads
`routes_through_gateway = context.agent != "subscription"` with a bare literal, while
`:1026` uses the imported `SUBSCRIPTION_AGENT` constant (`factory/config.py:149`).
They agree today. An implementer touching this region should not leave them
disagreeing.

## Traps

**Trap 1 — Do not add a name to `PASSTHROUGH_ENV`.** It is the obvious edit and it is
wrong. `PASSTHROUGH_ENV` is merged for *every* attempt including gateway-routed ones,
so adding the token there hands an inference credential to personas that authenticate
with a virtual key, widening a deliberately narrow allowlist to solve a
subscription-only problem. FR-012 forbids it and US1-S3 tests for it. The correct
shape is a conditional construction in the subscription branch, beside the existing
`if routes_through_gateway:` block.

**Trap 2 — Two mechanisms, both required.** The environment dict (`:941`) and the
bwrap `--setenv` list (`:584-600`) are independent. A name added to only the dict is
discarded by `--clearenv`; a name added to only the argv is not in the environment the
adapter records. This has bitten before in the gate boundary, where the comment at
`:472-474` notes `--clearenv` must precede every `--setenv` "bwrap keeps what is set
after it, and clears what came before". US1-S2 is the test that catches half a fix.

**Trap 3 — This is not an API key, and the distinction is a standing operator rule.**
The value is a subscription OAuth token, `sk-ant-oat01-` prefixed, scope
`user:inference`, minted by `claude setup-token`. The operator's standing instruction
is that an Anthropic API key is never the route; `agent: subscription` personas are.
No story may introduce `ANTHROPIC_API_KEY`, and no story may make a subscription
persona route through the gateway to reach a credential. FR-012.

**Trap 4 — Never put a real token in a test, a fixture, a spec, or a commit.** The
operator's standing rule is that secrets do not go in git, not even encrypted. Tests
use a synthetic value. The live token on this host is at
`/home/admin/.config/ergane-oauth-token.env` at `0600` and is deliberately outside
the repository; nothing in this spec should reference that path as a constant, because
it is an operator-local fact and this factory is portable by design.

**Trap 5 — The gate boundary must not inherit the credential.** The gate is a separate
boundary in `factory/verify/gates.py` with its own tmpfs `HOME`. It runs deterministic
commands and has no use for an inference credential. US1-S6 tests its absence. Bounding
the blast radius is the point of an allowlist, and a fix that leaks the token one
boundary further has made the sandbox worse while making the factory work.

**Trap 6 — Two credential shapes, and only one has an expiry.** The copied credential
carries `expiresAt` and `refreshTokenExpiresAt` as timestamps in its JSON. The
long-lived token is an opaque environment string with no local expiry to read. A check
that assumes either shape breaks the other. US2-S3 and US2-S4 are the two controls.

**Trap 7 — Refuse only on positive evidence of death.** An unreadable, absent or
unparseable expiry is not evidence that a credential is dead. A check that refuses on
absence converts a working factory into a stopped one, which is a worse failure than
the one being fixed — the same argument `_read_standards` makes about optional keys in
`factory/verify/factory_yaml.py`. FR-008 and US2-S4.

**Trap 8 — No network call in the check.** A pre-dispatch probe that dials the API
adds latency to every dispatch and introduces a second thing that can fail, at the
exact moment the factory is least able to tolerate it. Read the local expiry. FR-009
and US2-S7.

**Trap 9 — The judge sees the diff and the criteria, nothing else.** Constitution
Principle VIII / D-037. Every acceptance scenario above says "proven by a committed
test" because that is the only evidence that reaches the verdict. If a story produces
runtime evidence — a live dispatch that authenticated with the token — it must be
pasted into the attempt report as output, not described.

**Trap 10 — The precedence must be stated, not implied.** When both sources are
present the token wins (FR-005), and the record must say which was chosen. Two
credentials with an unstated precedence is a coin toss that the operator cannot debug
at 3 AM, which is exactly when this code runs.

## Sizing

Three stories, chained on file ownership. US1 is small — a conditional in
`attempt_env`, a name in the sandbox argv tuple, and the tests that pin both halves
plus the two controls. US2 is a pre-fork check beside an existing refusal, plus its
record shape. US3 is an operator surface over what US2 already knows.

US1 is the whole fix for the reported defect. US2 and US3 are what stop the next
credential problem costing a story and a night respectively.

## Verification the operator will run, independent of the gate

The gate and the judge see the diff. The operator will additionally, after US1 lands
and the worker is rotated:

1. Confirm the worker environment carries the token and the operator credential does
   not need to be fresh.
2. Dispatch one epic and let it run **past** the copied credential's `expiresAt`.
   Today that is the falsifiable claim: a run that crosses the old eight-hour boundary
   without a 73-byte authentication failure is the proof, and a run that dies at it
   means the token is not the whole story.
3. Confirm by reading a node's recorded environment that no credential value was
   written to any log, transcript or attempt report.

Step 2 is the measurement this spec exists to make possible, and it cannot be run
until US1 is landed **and** the worker has been rotated — the worker imports factory
code live from the operator checkout, so a landed fix that has not been rotated in is
not running. That mistake has already been made on this repository: spec 095's fix was
landed and unproven for a full day because the worker was twenty commits stale.
