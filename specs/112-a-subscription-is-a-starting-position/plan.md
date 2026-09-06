# Implementation Plan: a subscription is a starting position

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**Spec 125 landed the token's environment half on 2026-09-01 and you must not
re-implement it.** `CLAUDE_CODE_OAUTH_TOKEN` is a named constant at
`factory/workgraph/adapter.py:114`, it is set into the child environment inside
the subscription branch of `factory/workgraph/adapter.py:947` — `attempt_env`,
and it is listed in the bwrap `--setenv` allowlist at
`factory/workgraph/adapter.py:603` — `BwrapBackend._build_argv` so it survives
`--clearenv`. The subscription branch reads:

```python
    else:
        # US1: subscription-routed personas authenticate with the operator's
        # longest-lived credential. Carry the token only in the subscription
        # branch; adding it to PASSTHROUGH_ENV would hand it to gateway personas
        # too (trap 1).
        oauth_token = source.get(CLAUDE_CODE_OAUTH_TOKEN)
        if oauth_token:
            env[CLAUDE_CODE_OAUTH_TOKEN] = oauth_token
```

**The gap US1 closes is one `if`, and it is the one 125 did not reach.** The
dispatch path in
`factory/workgraph/adapter.py:1022` — `ClaudeCodeAdapter.run_attempt` does
this, in this order:

```python
        credential_path: Path | None = None
        if context.agent == SUBSCRIPTION_AGENT:
            credential_path = discover_subscription_credential()
            if credential_path is None:
                operator_home = _operator_home()
                raise AdapterError(
                    "subscription credential not found: no .claude/.credentials.json "
                    f"under {operator_home / '.claude'} or XDG_CONFIG_HOME. "
                    "Run `claude auth login` on the worker host."
                )
```

`factory/workgraph/adapter.py:1073` — `ClaudeCodeAdapter.run_attempt` is that
`if`, and it consults no environment variable. Ten lines further down, the
EXPIRED-file branch does:

```python
            if (
                expires_at is not None
                and expires_at <= datetime.now(timezone.utc)
                and not os.environ.get(CLAUDE_CODE_OAUTH_TOKEN)
            ):
```

`factory/workgraph/adapter.py:1088` — `ClaudeCodeAdapter.run_attempt` is that
third conjunct. 125 guarded the expired case on the token and left the absent
case unguarded.
`factory/workgraph/adapter.py:1113` — `ClaudeCodeAdapter.run_attempt` is where
the environment that would have carried the token is finally assembled — after
both refusals.

**The seeding copy is four lines and takes a path, not a decision.**
`factory/workgraph/adapter.py:896` — `_seed_node_home` ends:

```python
    (home / ".gitconfig").write_text(config, encoding="utf-8")
    if credential_path is not None:
        target = home / ".claude" / ".credentials.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(credential_path, target)
        target.chmod(0o600)
```

Its docstring records the hazard as unmeasured: "if rotation-on-use is the
provider's behaviour, a copy still prevents concurrent nodes from invalidating
each other, but the operator's own host login may be invalidated when the first
node refreshes." FR-002 removes the copy in exactly the case where nothing
needs it, and
`factory/workgraph/adapter.py:1101` — `ClaudeCodeAdapter.run_attempt` is the
single call site.

**The remedy strings already exist in the other operator surface, twice as
good.** `factory/workgraph/credential_status.py:44` — `_credential_runway`
closes with:

```python
    return CredentialStatus(
        source=None,
        expires_at=None,
        remedies=(
            "run `claude auth login` on the worker host",
            f"set {CLAUDE_CODE_OAUTH_TOKEN} to a long-lived token from `claude setup-token`",
        ),
    )
```

The adapter's refusal names only the first. FR-005 hoists that tuple to a module
constant and asserts every refusal that names both routes contains every element
of it.

**The constant goes in the adapter, and the import direction is why.**
`factory/workgraph/credential_status.py:25` is
`from factory.workgraph.adapter import (` — six names,
`CLAUDE_CODE_OAUTH_TOKEN` among them.
`grep -n credential_status factory/workgraph/adapter.py` returns nothing: the
edge runs one way only, and it runs from the operator-status module to the
dispatch adapter. There is a third surface with its own hand-written copy of
the same two remedies, the expired-copy refusal at
`factory/workgraph/adapter.py:1096` — `ClaudeCodeAdapter.run_attempt`:

```python
                        "Remedies: run `claude auth login` on the worker host, or "
                        f"set {CLAUDE_CODE_OAUTH_TOKEN} to a long-lived token from "
                        "`claude setup-token`."
```

FR-005 covers all three. Rendering that sentence from the constant produces the
same bytes it produces today, which is why `tests/test_us2_credential_expiry.py`
passing unmodified is the proof that nothing landed moved.

**The mode enum and the text it needs are eleven lines apart.**
`factory/controlplane/config.py:35` is `KNOWN_LL_MODES = ("gateway", "direct")`
and its comment above still claims `direct` "is recognized as a token but
refused" — false since 055, and operator commit `c5890b2` corrected the same
false claim in `docs/onramp.html` on 2026-08-28.
`factory/controlplane/config.py:350` is the twelve-line
`DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT`, and
`factory/controlplane/config.py:134` — `ControlPlaneConfig.LLMDirect` is the
three-field frozen dataclass FR-006 mirrors. The discriminated union it hangs
off is `factory/controlplane/config.py:147` — `ControlPlaneConfig.LLM`, whose
`gateway` and `direct` fields both default to `None`.
`factory/controlplane/config.py:363` — `_read_llm` is the whole parse, and its
`direct` branch begins at `factory/controlplane/config.py:374` — `_read_llm`.

**The probe's registry seam already exists and already skips subscription
personas.** `factory/controlplane/verify.py:149` — `_load_personas_for_probe`
is the injectable loader, and
`factory/controlplane/verify.py:400` — `gather_gateway_aliases` filters on the
persona property:

```python
    for name, persona in registry.items():
        # US2 FR-016: subscription personas resolve models the CLI accepts,
        # not aliases the gateway serves, so they must not be counted here.
        if not getattr(persona, "routes_through_gateway", True):
            continue
```

That property is `factory/config.py:203` — `Persona.routes_through_gateway`,
which returns `self.agent not in (DETERMINISTIC_AGENT, SUBSCRIPTION_AGENT)`.
FR-007 needs the complement of that filter and can compute it from the same
registry the same seam returns.

**The declared-absent precedent is two probes down the same file.**
`factory/controlplane/verify.py:934` — `EscalationProbe.gather` returns, for
`adapter == "none"`, a snapshot whose detail is at
`factory/controlplane/verify.py:940` — `EscalationProbe.gather`: "escalations
will be dropped: escalation.adapter is `none`; a node that would have asked a
question fails instead of waiting".
`factory/controlplane/verify.py:984` — `EscalationProbe.evaluate` then returns
`passed=True` with that detail unmodified. Pass, and say what it costs, in one
breath. FR-008 is that shape.

**The assertion FR-010 deletes, and the comment that is wrong.**
`factory/controlplane/verify.py:428` — `LLMProbe.gather` opens:

```python
        # `gateway` is the only mode a parsed config can carry (048-US2).
        gateway = config.llm.gateway
        assert gateway is not None
```

`factory/controlplane/verify.py:431` — `LLMProbe.gather` is the assertion.
Confirmed live at 602a92c by constructing a direct-mode `ControlPlaneConfig`
and awaiting `LLMProbe().gather(config)`: `AssertionError` raised, no finding
produced. The three preserved-failure branches FR-009 protects are
`factory/controlplane/verify.py:437` — `LLMProbe.gather` (no master key),
`factory/controlplane/verify.py:447` — `LLMProbe.gather` (no dispatchable
aliases) and `factory/controlplane/verify.py:455` — `LLMProbe.gather` (the
`example/` placeholders). The verdict itself is
`factory/controlplane/verify.py:665` — `LLMProbe.evaluate`:

```python
    def evaluate(self, snapshot: LLMSnapshot) -> Finding:
        # An empty result set means no aliases were probed (no credential, or an
        # unconfigured example registry).  That is a failure, not a vacuous pass.
        passed = bool(snapshot.results) and all(r.completed for r in snapshot.results)
```

`factory/controlplane/verify.py:70` — `LLMSnapshot` carries four fields —
`aliases`, `persona_by_alias`, `results`, `detail` — and none of them says
which mode was declared. Both precedents solve that in `evaluate` on a snapshot
field: `factory/controlplane/verify.py:915` — `TelemetryProbe.evaluate`
branches on `snapshot.mode == "none"` and
`factory/controlplane/verify.py:984` — `EscalationProbe.evaluate` on
`snapshot.adapter == "none"`. FR-008 needs the same field and the same branch.

**The interview's LLM question, and where `direct` states its cost.**
`factory/cli/install.py:1545` — `_ask_llm` asks the mode through
`factory/cli/install.py:1910` — `_ask`, then branches on the answer.
`factory/cli/install.py:1600` — `_ask_llm` holds `elif mode == "direct":`, and
`factory/cli/install.py:1602` — `_ask_llm` holds
`print(DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT)` — a name imported at
`factory/cli/install.py:52`, not copied. The mode itself is applied by
`factory/cli/install.py:2035` — `_apply_llm_mode`, which seeds `_GATEWAY_SEED`
or `_DIRECT_SEED` (`factory/cli/install.py:266`) per mode and otherwise keeps
the raw answer so the parser refuses it by name. The offered choices come from
`factory/cli/install.py:2149` — `_offered_llm_mode`, whose no-usable-scan
branch is `factory/cli/install.py:2168` — `_offered_llm_mode`.

That function reads `KNOWN_LL_MODES` a third time, and the read is not a second
place to edit. `factory/cli/install.py:2197` — `_offered_llm_mode` is
`mode = existing_mode if existing_mode in KNOWN_LL_MODES else "direct"`, the
inference-only **re-run** branch. Once FR-006 widens the tuple, a re-run over
an existing `none` config with an inference-only scan offers `llm mode (none)`
for free — correct behaviour, arrived at without a line of US3. Do not add
`none` to that branch by hand; T024 confines the new offer to
`factory/cli/install.py:2168` — `_offered_llm_mode` for the reason trap 15
gives.

**The persona interview is coupled to the gateway in its first two lines.**
`factory/cli/install.py:567` — `_interview_personas` begins:

```python
    base_url = document["llm"]["base_url"]
    master_key_env = document["llm"]["master_key_env"]
```

`factory/cli/install.py:578` — `_interview_personas` is the first of those. It
then fetches aliases from that gateway, ranks them, and walks
`_GATEWAY_PERSONA_ORDER` three times — the primary pass at
`factory/cli/install.py:599` — `_interview_personas`, the fallback pass at
`factory/cli/install.py:640` — `_interview_personas`, and the write-up loop at
`factory/cli/install.py:683` — `_interview_personas`, which does
`updates[name] = {"model": chosen_primary[name], ...}` and therefore raises
`KeyError` for any name the gateway passes never filled. The subscription
branch that already does the right thing sits between them at
`factory/cli/install.py:670` — `_interview_personas`, keyed on
`persona.routes_through_gateway` off the registry's own membership.

The constant has FOUR live readers, not three.
`factory/cli/install.py:596` — `_interview_personas` seeds a dict from it:

```python
    tried_aliases: dict[str, set[str]] = {name: set() for name in _GATEWAY_PERSONA_ORDER}
```

whose keys are then indexed unguarded at
`factory/cli/install.py:616` — `_interview_personas` and
`factory/cli/install.py:653` — `_interview_personas`
(`if chosen in tried_aliases[name]`). Count them before writing US4: 596, 599,
640, 683.

There is a fifth read of the constant and it is not a call site.
`factory/cli/install.py:516` — `_ask_persona_alias` builds a synthetic persona
dict for the proposal ranker over it, but
`grep -rn _ask_persona_alias factory/ tests/ scripts/` returns exactly one line
— its own definition at
`factory/cli/install.py:498` — `_ask_persona_alias`. Nothing in `factory/`,
`tests/` or `scripts/` calls it, it is handed no registry, and no input can
make it raise. US4 may leave it exactly as it is.

**The constant itself, and the call site of the whole thing.**
`factory/cli/install.py:471` is `_GATEWAY_PERSONA_ORDER`, six names.
`factory/cli/install.py:943` — `install_command` is where `_interview_personas`
is called, after `_write_config` at
`factory/cli/install.py:937` — `install_command` has already written the config
— so a `KeyError` there leaves a written `config.toml` and an unwritten
registry.

**The registry a fresh host starts from is six gateway personas, and that is
why US3 needs FR-017.**
`factory/cli/install.py:1118` — `_seed_personas_registry` writes
`factory/config.py:60` — `shipped_registry_text` verbatim, which is
`personas.example.yaml`: architect, implementer, judge, closer, debugger and
researcher each declare `agent: claude-code` (`personas.example.yaml:26` is the
first of them), `verifier` declares `agent: none` and `opus-closer` declares
`agent: subscription`.
`factory/config.py:203` — `Persona.routes_through_gateway` is therefore True
for six of the eight, and `factory/cli/install.py:954` — `install_command` runs
`verify_controlplane` on what the interview just wrote. The writer that would
change them, `factory/cli/install.py:409` — `_update_persona_lines`, touches
`model` and `fallback` lines only:

```python
            for field in ("model", "fallback"):
                if field not in fields:
                    continue
                if stripped.startswith(f"{field}:"):
```

Its `_scalar` helper already renders `None` as the literal `null`, so writing
`fallback: null` on a converted persona needs no new machinery — only `agent`
does.

**Subscription accounting is already correct and is not in scope.**
`factory/activities/usage_activities.py:517` — `_is_subscription_lease` keys on
an empty virtual key and the row is written with NULL counts. Nothing here
changes it.

## Traps

**Trap 1 — most of the old US1 has landed; building it again is the expensive
mistake.** Spec 125 (`ed9aa51`, `8d71de4`, `01bb717`, 2026-09-01) put the token
into `attempt_env`, into the bwrap allowlist, into an expired-copy refusal and
into a whole new operator module. Operator commit `c5890b2` corrected
`claude login` to `claude auth login` at
`factory/workgraph/adapter.py:1078` — `ClaudeCodeAdapter.run_attempt` on
2026-08-28. Read `factory/workgraph/credential_status.py` and
`tests/test_us2_credential_expiry.py` before writing a line of US1. The only
production change FR-001 needs is the token guard on the ABSENT-file branch at
`factory/workgraph/adapter.py:1073` — `ClaudeCodeAdapter.run_attempt`; the
tempting move is to rewrite `discover_subscription_credential` to return a
token-or-path union, which would touch every one of 125's landed tests for no
requirement here.

**Trap 2 — the credential decision must be made before the home is seeded, and
there is already a second derivation of it downstream.**
`factory/workgraph/adapter.py:1101` — `ClaudeCodeAdapter.run_attempt` seeds the
home; `factory/workgraph/adapter.py:1122` — `ClaudeCodeAdapter.run_attempt`
derives `credential_source` from `env.get(CLAUDE_CODE_OAUTH_TOKEN)` seventeen
lines later. FR-002 needs the same answer earlier. Compute the token's presence
once and let both readers use it; deriving it twice from two different sources
is how the recorded `credential_source` starts disagreeing with what was
actually written to disk, which is 125's own trap 10 reopened.

**Trap 3 — do not widen `PASSTHROUGH_ENV`.** FR-003.
`factory/workgraph/adapter.py:104` is `("PATH", "LANG", "TERM")` and 125's
FR-012 requires every story to leave it that way. The token belongs in the
subscription branch of `attempt_env` — where it already is — and adding it to
the global allowlist would hand it to gateway personas, which is a credential
leak dressed as a simplification.

**Trap 4 — FR-007 cannot live in the parser, and the old plan said it could.**
`factory/controlplane/config.py:363` — `_read_llm` takes `(document, source)`.
It has no registry, no path to one, and no business acquiring one: it is a pure
document parse and every other subsystem's cross-checks live in the probes. The
registry is reachable only through
`factory/controlplane/verify.py:149` — `_load_personas_for_probe`, which is the
injectable seam the tests already use. Put the cross-check in `LLMProbe.gather`
and return a failing snapshot; a failing `llm` finding is already the strongest
refusal the verify surface has.

**Trap 5 — do not collapse "declared absent" into "not configured".** The
comment at `factory/controlplane/verify.py:663` — `LLMProbe.evaluate` is right
about the case it was written for, and the `example/` check at
`factory/controlplane/verify.py:455` — `LLMProbe.gather` is the same instinct.
FR-008 adds a branch **gated on the declaration being `none`**. The wrong move,
and it will look like a simplification, is to make an empty alias set pass
whenever it is empty; that turns a misconfigured gateway install green. US2-S5
exists to fail that diff.

**Trap 6 — the surrender text is the deliverable and two thirds of it are
security.** FR-006. The gateway delivers the agent's credential so a sandboxed
agent never holds the operator's real one, and makes persona-to-model routing
enforceable because the minted key's model list derives from the registry. Only
spend attribution is bookkeeping. A `none` text that says "you lose spend
tracking" is wrong by two thirds and is the specific failure this trap exists
to prevent. Write it beside `factory/controlplane/config.py:350` and import it;
a second copy in `factory/cli/install.py` is how the two drift. Do **not**
mirror the existing pin and call it done:
`tests/test_controlplane_direct_mode.py:448` — `test_surrendered_properties_source_is_single_module_constant`
asserts only that each expected phrase appears in the constant and that the
text has exactly three `-` bullets — it never counts definitions, and a test
that mirrors it is weaker than US2-S1's "defined exactly once in
`factory/controlplane/config.py`". Read that module as text and assert the
`none` text's opening line occurs once in it.

**Trap 7 — `none` must not become a way to run gateway personas without a
gateway.** FR-007 is the load-bearing half of US2. Without it, `none` is a
config error that surfaces as an authentication failure at first token, with a
green verify behind it — precisely the class of defect the whole `--verify`
surface exists to catch.

**Trap 8 — `_apply_llm_mode` will silently carry the old mode's fields into a
`none` document.** `factory/cli/install.py:2035` — `_apply_llm_mode` seeds
`_GATEWAY_SEED` or `_DIRECT_SEED` per mode and otherwise does
`document["llm"] = {**current, "mode": mode}`. Fall through that `else` with
`none` and the document keeps a `base_url` and a `master_key_env` from whatever
was there before — which will parse, because FR-006 only says those are not
*required*. Then `factory/cli/install.py:578` — `_interview_personas` finds a
`base_url`, takes the gateway path, and interviews against an endpoint the
operator just declared absent. Add a seed for `none` that carries nothing but
the mode.

**Trap 9 — the disclosure ordering the old spec asked for does not exist in the
tree.** `direct` prints its text at `factory/cli/install.py:1602` — `_ask_llm`
*after* `_ask` has already accepted the mode answer, not before. `none` has no
follow-up question to print ahead of at all. Do not restructure `_ask_llm` to
invent a pre-acceptance disclosure; FR-011 asks only that the text is printed
on the `none` branch, from the shared constant, before `_ask_llm` returns —
which is strictly before anything is written, since
`factory/cli/install.py:937` — `install_command` writes the config only after
`_interview` returns.

**Trap 10 — a `none` interview must not reach the gateway at all, and a test
that merely asserts "no crash" will not prove it.** FR-012. The gateway path
does network work: `_fetch_aliases_from_gateway`, `_enrich_aliases`, and a probe
per alias. Inject the alias-fetch and probe seams as callables that raise if
called, and assert the interview completes — that is what makes "no gateway was
contacted" provable from the diff rather than from a stopwatch.

**Trap 11 — `_GATEWAY_PERSONA_ORDER` has two jobs and only one is wrong.** It
supplies membership (wrong —
`factory/cli/install.py:670` — `_interview_personas` already shows the registry
knows) and a stable order for a transcript operators read and diff (fine).
Deleting it makes question order depend on dict iteration, which is a
reproducibility regression. FR-015 keeps it as the sort key: known names first
in its order, unknown names after in registry order. **Four** live readers must
move together — `factory/cli/install.py:596` — `_interview_personas`,
`factory/cli/install.py:599` — `_interview_personas`,
`factory/cli/install.py:640` — `_interview_personas` and
`factory/cli/install.py:683` — `_interview_personas`. The one that is easy to
miss is 596: it is the dict comprehension that seeds `tried_aliases`, and its
keys are indexed unguarded at
`factory/cli/install.py:616` — `_interview_personas` and
`factory/cli/install.py:653` — `_interview_personas`. Move the two loops and
the write-up onto a registry-derived list and leave 596 alone and US4-S2's
seven-persona registry raises `KeyError` on the two unknown names at 616 — the
trap's own failure, reproduced by the fix. Three of four leaves the `KeyError`
exactly where it is; move all four and it is gone.

The constant is read in a fifth place and that read is not one of the four.
`factory/cli/install.py:516` — `_ask_persona_alias` reads it, and
`grep -rn _ask_persona_alias factory/ tests/ scripts/` returns only the
function's own definition at
`factory/cli/install.py:498` — `_ask_persona_alias`: it is unreferenced, it
receives no registry, and it cannot raise the `KeyError` this trap exists to
prevent. Leave it alone. Two earlier passes of this trio counted it as a fifth
call site and told the implementer that four of five was not enough; both were
wrong, and the wrong move they invite is to change a dead function's signature
so that a count comes out right.

**Trap 12 — this floor dispatches on the code US1 edits.** Two personas in this
repository's `personas.yaml` declare `agent: subscription`, and every
subscription-routed attempt runs through
`factory/workgraph/adapter.py:1022` — `ClaudeCodeAdapter.run_attempt`. A
regression here does not fail a test, it stops the floor. Six existing suites
are a gate on US1, not a formality: `tests/test_subscription_credential.py`,
`tests/test_subscription_routing.py`, `tests/test_subscription_accounting.py`,
`tests/test_us2_credential_expiry.py`, and spec 125's own two on this exact
code — `tests/test_us1_long_lived_token.py` and
`tests/test_125_us3_credential_runway.py`. The last two are the ones an
implementer will not think to run.
`tests/test_us1_long_lived_token.py:341` — `test_token_wins_and_record_states_source`
is the landed pin for the token-and-file case FR-002 changes: it asserts the
recorded `credential_source` and the child environment and does **not** assert
that the seeded copy exists, which is why FR-002 leaves it green — verify that
by reading it rather than by assuming it.
`tests/test_us1_long_lived_token.py:299` — `test_no_token_subscription_still_seeds_copied_credential`
is FR-004's pin on the other half and must stay green unmodified. And
`tests/test_subscription_credential.py:236` — `test_missing_subscription_credential_refused_before_fork`
is the test that pins today's absent-file refusal and will need to state its
new precondition rather than be deleted. Three more tests in that same module
assert the seeded copy EXISTS —
`tests/test_subscription_credential.py:173` — `test_subscription_home_carries_credential`,
`tests/test_subscription_credential.py:291` — `test_moved_credential_is_still_seeded`
and
`tests/test_subscription_credential.py:358` — `test_credential_placement_is_a_distinct_copy`
— and `grep -n CLAUDE_CODE_OAUTH_TOKEN tests/test_subscription_credential.py`
returns nothing, so each of the three inherits its precondition from whatever
the host happens to export. After FR-002 they are green on a host with no token
and red on a host with one — which is precisely the host operator step 1 below
describes. They pass on this floor today because nothing here exports the token
into a test process and the gate boundary omits it
(`tests/test_us1_long_lived_token.py:378` — `test_gate_boundary_omits_oauth_token`),
which is a fact about this host rather than a property of the suite. T005 makes
that precondition explicit instead of inherited; do not discover it on a
laptop.

**Trap 13 — do not touch spend attribution.**
`factory/activities/usage_activities.py:517` — `_is_subscription_lease` already
records a subscription attempt as carrying no gateway spend data. A diff that
edits the ledger's gateway path is out of scope for every story here.

**Trap 14 — the shared remedy constant lives in the adapter; the other direction
does not import, it crashes.** FR-005.
`factory/workgraph/credential_status.py:25` already imports six names from
`factory/workgraph/adapter.py`, and the adapter imports nothing back. Hoisting
the tuple to `credential_status.py` — where the strings sit today, and therefore
the reading the words "hoist from" invite — makes the adapter import it, which
re-enters a half-initialised adapter whose token constant at
`factory/workgraph/adapter.py:114` is not yet bound. That is an `ImportError` on
every entry point, in the module trap 12 says stops the floor rather than failing
a test. The escape hatch an implementer reaches for next — a lazy import inside
the function — is worse: it inverts the layering silently, so the dispatch
adapter starts depending on the operator-status surface. Define the constant in
`factory/workgraph/adapter.py` beside the token constant and let
`credential_status.py` import it the way it already imports the other six names.

**Trap 15 — the mode question's text is a public string and two landed tests
pin it literally.** FR-011, FR-013. `factory/cli/install.py:1545` — `_ask_llm`
renders the question as `f"llm mode ({offered.choices})"`, and the
no-usable-scan branch at `factory/cli/install.py:2168` — `_offered_llm_mode`
returns `choices=mode`, i.e. the bare string `gateway`. Adding `none` there
makes the prompt `llm mode (gateway|none)`, and `defaults_for` matches on the
whole prompt string, so
`tests/test_install_mode_routing.py:292` — `test_empty_scan_falls_back_to_todays_question`
(`assert prompter.defaults_for("llm mode (gateway)") == ["gateway"]`, driven
through exactly that branch by an empty scan result) and
`tests/test_ergane_install_walkthrough.py:635` — `test_the_real_terminal_prompter_drives_the_interview`
(`assert "llm mode (gateway) [gateway]" in result.stdout`, with
`_scan_endpoints` stubbed to nothing at
`tests/test_ergane_install_walkthrough.py:619` — `test_the_real_terminal_prompter_drives_the_interview`)
both go red. This tree already records the same collision from 048 at
`tests/test_direct_mode_refused.py:236`. Restate both assertions to the new
string, the way T005 restates the subscription refusal's; deleting them removes
a pin nobody replaced.

The confinement to that one branch is itself load-bearing, and nothing else in
this plan says so. Three further live assertions pin the *other* two branches'
strings —
`tests/test_install_mode_routing.py:186` — `test_dispatchable_scan_offers_gateway_with_address_defaulted`,
`tests/test_install_mode_routing.py:218` — `test_inference_only_scan_offers_direct_and_names_missing_capability`
and
`tests/test_install_mode_routing.py:321` — `test_operator_declared_address_overrides_scan_result`
— and they survive only because the new choice is added at
`factory/cli/install.py:2168` — `_offered_llm_mode` and nowhere else. An
implementer who helpfully offers `none` from every branch turns three more
landed tests red beyond the two T023 was told to amend.

**Trap 16 — the `none` interview must skip the write-up loop too, not only the
gateway passes.** FR-012. `factory/cli/install.py:683` — `_interview_personas`
iterates the six-name constant and does
`updates[name] = {"model": chosen_primary[name], ...}`. In `none` mode no
gateway pass ran, so `chosen_primary` is empty and that loop raises `KeyError`
on the first name — the same exception class US3-S3 says it is removing, one
screen further down from the one it is thinking about. The no-gateway path
writes `subscription_updates` alone. (US4 later makes that loop iterate a
derived list, which would be empty here; US3 lands first and cannot lean on
it.)

**Trap 17 — FR-008's PASS has nothing to hang on until the snapshot declares
the mode.** `factory/controlplane/verify.py:665` — `LLMProbe.evaluate` computes
`passed = bool(snapshot.results) and all(...)`, and
`factory/controlplane/verify.py:70` — `LLMSnapshot` carries no mode, adapter or
declaration field. A `none` snapshot has no results, so it fails there no
matter what `gather` wrote into `detail`. The tempting move — make an empty
`results` pass — is the diff trap 5 exists to fail. Add the discriminator to
the snapshot and branch on it in `evaluate`, exactly as
`factory/controlplane/verify.py:915` — `TelemetryProbe.evaluate` and
`factory/controlplane/verify.py:984` — `EscalationProbe.evaluate` already do.

**Trap 18 — a landed test asserts `KNOWN_LL_MODES` by exact equality, and its
own name says the change FR-006 requires is forbidden.** FR-006.
`tests/test_controlplane_direct_mode.py:121` — `test_known_llm_modes_unchanged`
is:

```python
def test_known_llm_modes_unchanged() -> None:
    """The token list does not widen; 'direct' stays recognized."""
    assert KNOWN_LL_MODES == ("gateway", "direct")
```

US2's first production edit turns it red. Both wrong moves are cheap: back the
widening out because the test looks like a prohibition, or delete the pin
because it is in the way. Neither is right — the assertion is a real guard
against a mode list that grows by accident, and the fix is to restate it to
`("gateway", "direct", "none")` and restate the docstring with it, exactly as
trap 15 restates the two prompt-string pins. The rest of the tree was swept and
does not need touching:
`tests/test_controlplane_config.py:395` — `test_unknown_llm_mode_refused`
iterates the tuple and adapts on its own, and
`tests/test_direct_mode_refused.py:148` — `test_direct_stays_a_recognised_token_so_the_refusal_stays_specific`
asserts membership rather than equality. 121 is the only breakage, and T014 is
where it is amended.

**Trap 19 — a fresh install answering `none` fails its own FR-007 until the
interview offers the conversion.** FR-017, FR-007. The registry
`factory/cli/install.py:1118` — `_seed_personas_registry` seeds carries six
personas declaring `agent: claude-code`, so
`factory/config.py:203` — `Persona.routes_through_gateway` is True for all six
and FR-007's cross-check names all six the moment
`factory/cli/install.py:954` — `install_command` verifies. FR-012 alone does
not help: it confirms the model name of personas that ALREADY declare
`agent: subscription`, which over the shipped registry is `opus-closer` and
nothing else. That is the exact clause of the declared ledger row — "the
interview's subscription branch only asks the model name for personas that
ALREADY declare agent: subscription" — and without FR-017 this spec's headline
promise is reachable only by hand-editing `personas.yaml`, which no story and
no operator step names. The wrong move is to make FR-007 lenient about seeded
placeholder personas; that is trap 7 reopened. Write the offer instead, keep
the decline path honest, and note that
`factory/cli/install.py:409` — `_update_persona_lines` must learn one more
field name and must keep writing exactly today's bytes when no `agent` is
supplied, or FR-013's paired gateway fixture fails.

## Sizing

**US1** touches `factory/workgraph/adapter.py` and one new test module. Its
production change is a token check on one `if`, one boolean threaded into
`_seed_node_home`'s call, and one remedy tuple hoisted to a module constant —
under fifty lines. It also amends
`tests/test_subscription_credential.py:236` — `test_missing_subscription_credential_refused_before_fork`
to state that the refusal now requires both credential forms absent.

**US2** touches `factory/controlplane/config.py` and
`factory/controlplane/verify.py` and one new test module: a tuple entry, a
frozen dataclass mirroring `LLMDirect`, a text constant, a `none` branch in
`_read_llm`, and in the probe one deleted assertion, two new `gather` branches,
one new field on `factory/controlplane/verify.py:70` — `LLMSnapshot` (carrying
a default, so the five constructors in that module and the two outside it —
`tests/test_ergane_install_personas.py:103` — `_stub_llm_gather` and
`tests/_us4_outputs/generate_interview_evidence.py:236` — `_stub_llm_gather` —
need no edit) and the one `evaluate` branch that reads it (trap 17). It also
amends one landed assertion in `tests/test_controlplane_direct_mode.py`,
`tests/test_controlplane_direct_mode.py:121` — `test_known_llm_modes_unchanged`
(trap 18). Under a hundred production lines. `LLMDirect` is the template; mirror it and stop — the unit of
value is "a third declared position exists and verify understands it", not "the
control-plane schema is refactored", and every config in existence is parsed by
this file.

**US3** touches `factory/cli/install.py` and one new test module: a seed dict,
a `none` branch in `_apply_llm_mode`, a `none` branch in `_ask_llm`, one entry
in the offered choices, an early no-gateway path in `_interview_personas` that
runs the subscription loop and the write and skips both gateway passes and the
write-up loop at `factory/cli/install.py:683` — `_interview_personas`, the
conversion offer FR-017 asks for on that same path, and one more field name in
`factory/cli/install.py:409` — `_update_persona_lines`. It also amends two
landed assertions that pin the old mode-question string (trap 15):
`tests/test_install_mode_routing.py:292` — `test_empty_scan_falls_back_to_todays_question`
and
`tests/test_ergane_install_walkthrough.py:635` — `test_the_real_terminal_prompter_drives_the_interview`.

**US4** touches `factory/cli/install.py` and one new test module: one
derivation function and **four** live call sites moved onto it —
`factory/cli/install.py:596` — `_interview_personas`,
`factory/cli/install.py:599` — `_interview_personas`,
`factory/cli/install.py:640` — `_interview_personas` and
`factory/cli/install.py:683` — `_interview_personas`. Three of four is trap 11's
own failure, reproduced by the fix. The constant's fifth reader,
`factory/cli/install.py:516` — `_ask_persona_alias`, is unreferenced in the
tree and is not a call site of this story: leaving it be is correct.

US1 and US2 name no production file in common with each other or with US3/US4.
US3 and US4 share `factory/cli/install.py`, which is why US4 carries a
`depends_on_merged` edge on US3 rather than running beside it.

All four stories are well inside the 64 KiB deterministic diff bound (D-050).
The pasted evidence each verification task asks for is a directory listing, two
finding lines and two short transcripts — not a session log.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only,
so every runtime observation below is committed as pasted output. Beyond that:

0. **Before any dispatch, at the moment this spec is flipped**: the
   `workgraph.json` beside this plan was compiled when every story's `implements`
   was empty, so its three nodes carry `requirement_keys: ["USn"]` and there is no
   `us4` node at all. The roadmap re-derives from `spec.md` and never reads it,
   but `ergane build start --graph` loads it off disk. Delete it or re-derive it,
   and confirm four nodes carrying FR-001…FR-017 before starting the epic. This
   is an operator action; refinement is not permitted to write that file.

Then, after all four stories land:

1. On this host, with `CLAUDE_CODE_OAUTH_TOKEN` exported and
   `~/.claude/.credentials.json` temporarily moved aside, dispatch one
   subscription-routed story. It must reach the agent rather than refusing, and
   the per-node HOME under `.ergane/` must contain a `.gitconfig` and no
   `.credentials.json`.
2. Move the credentials file back, unset the token, and dispatch again. The copy
   must reappear at mode 0600 and the story must behave exactly as it does today.
3. Move both aside and unset the token. The refusal must name `claude auth
   login` **and** `claude setup-token`.
4. On a machine with a subscription and no LiteLLM anywhere — or on this one with
   the gateway config set aside — run `claude setup-token`, export the token, run
   `ergane install`, answer the LLM mode question with `none`, and read the
   surrender text. The interview must complete and write both files without a
   `KeyError`. It must also offer to convert each of the six seeded
   `agent: claude-code` personas; accept them all and read the written
   `personas.yaml` back — six `agent: subscription` lines, six CLI-side model
   names, six `fallback: null`. Decline one deliberately on a second run: that
   run's registry must keep the persona as it was, which is what step 5's second
   half then names.
5. Run `ergane install --verify` over the all-accepted registry and read a green
   `llm` line whose detail names the surrender. Then run it over the second
   run's registry — the one where a persona was declined and so still declares
   `agent: claude-code` — and it must fail, naming that persona.
6. Point the same verify at a `direct`-mode config. It must report a finding
   rather than raising `AssertionError`.
7. Dispatch one real story from that install and watch it reach PASSED.
8. Before the next `ergane findings triage --apply`, file a successor finding
   for the residue this spec leaves behind:
   `install/subscription-only-operator-cannot-verify-green` stays declared in
   `fixes:` because its summary and three of the four halves in its notes are
   owned outright by these FRs, but its fourth — "credentials are file-copied
   per node with a rotation hazard the code records as unmeasured" — survives
   on the no-token path by design (FR-004 keeps that copy, and
   `factory/workgraph/adapter.py:896` — `_seed_node_home` still carries the
   docstring that records the hazard). Triage closes a row on the strength of a
   landed `fixes:` declaration and cannot tell a whole fix from a half one, so
   the successor row is what keeps the hazard counted. File it against
   `factory/workgraph/adapter.py:929` — `_seed_node_home`, naming the no-token
   path as the surviving one.

Step 7 is the falsifiable test of the whole spec. Until it has been done once,
this spec has made a position declarable and proved nothing about whether it
builds software; a green verify line on its own proves that a declaration
parses, which is the smaller half.
