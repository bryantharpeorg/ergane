# Implementation Plan: a subscription is a starting position

Drafted 2026-08-27 against ergane-buildout at 3e5c940. Every anchor below was
read from that commit. The six measurements in spec.md's frontmatter are inputs
to this plan, not open questions.

## Requirements, numbered here

- **FR-001** — `discover_subscription_credential`
  (`factory/workgraph/adapter.py:797-830`) gains an environment route. When
  `CLAUDE_CODE_OAUTH_TOKEN` is set and non-empty, it resolves to that token;
  otherwise it searches today's three file paths in today's order. The function's
  return type widens from `Path | None` to a small result carrying either a token
  or a path — callers must be able to tell which, because the two are seeded
  differently.
- **FR-002** — When the credential is a token, `_seed_node_home`
  (`adapter.py:833-867`) writes **no** credentials file into the per-node HOME.
  The token reaches the child through its environment instead. This is the whole
  point: the file copy is what carries the rotation hazard the docstring records
  at `:846-850`, and a token has no file to rotate out from under anybody.
- **FR-003** — The subscription route's existing invariant is unchanged under
  either credential form: the adapter hands the child neither
  `ANTHROPIC_BASE_URL` nor `ANTHROPIC_AUTH_TOKEN` (070-US2 FR-006). A token is a
  third thing, not a re-introduction of the gateway's two.
- **FR-004** — The token takes precedence over a file when both exist, and the
  order is asserted rather than emergent.
- **FR-005** — The refusal raised when no credential is found
  (`adapter.py:1002-1008`) names both supply routes: `claude auth login`, which
  writes the file, and `claude setup-token` with `CLAUDE_CODE_OAUTH_TOKEN`, which
  produces the token. The current text says `claude login`, which is not a
  subcommand in Claude Code 2.1.223 — `claude login --help` falls through to
  top-level help exactly as an unknown word does, while `claude auth login
  --help` resolves. (An operator session corrected this string on 2026-08-27; if
  that landed first, this FR is a no-op and the test still pins it.)
- **FR-006** — `KNOWN_LL_MODES` (`factory/controlplane/config.py:35`) gains
  `"none"`. A `none`-mode config requires no `base_url` and no `master_key_env`,
  and carries a surrendered-properties text in the shape
  `DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT` uses (`:350-360`), naming three
  things in this order: the credential is the operator's own and reaches every
  attempt unexpiring and unconstrained; the registry's persona-to-model bindings
  are advisory rather than enforced, because there is no key whose model list
  derives from them; and spend attribution is unavailable. The first two are
  security properties and the text says so.
- **FR-007** — A `none` declaration is refused when any persona in the resolved
  registry has `routes_through_gateway` True (`config.py:203-208`). The refusal
  names the offending personas. This is the one combination that must be
  unreachable: a registry that dispatches through a gateway the config says does
  not exist fails at the first attempt, with nothing in verify to have warned.
- **FR-008** — `LLMProbe` gains a declared-absent branch. When the config
  declares `none` **and** `gather_gateway_aliases` (`verify.py:386-402`) is
  empty, the finding is PASS and its detail names the surrender, in the manner
  `escalation` already names its own ("escalations will be dropped… a node that
  would have asked a question fails instead of waiting"). PASS-and-say-what-it-
  costs is the house form; a silent skip is not.
- **FR-009** — Every other path through `LLMProbe.evaluate`
  (`verify.py:648-656`) keeps today's verdict. An empty alias set under a
  `gateway` declaration still FAILS; the `example/` placeholder registry still
  FAILS (`:441-451`); a missing master key still FAILS (`:423-429`). The comment
  at `:649-650` — "That is a failure, not a vacuous pass" — remains true for
  every case it was written about.
- **FR-010** — `LLMProbe.gather` no longer asserts `config.llm.gateway is not
  None` (`verify.py:415-417`). A `direct` config produces a finding describing
  what direct mode cannot verify; a `none` config takes the FR-008 branch. The
  stale comment claiming gateway is the only parseable mode goes with the
  assertion.
- **FR-011** — `ergane install`'s LLM question offers the no-gateway answer, and
  prints the FR-006 surrender text **before** accepting it, in the same order the
  `direct` branch already uses (`factory/cli/install.py:1596-1602`).
- **FR-012** — The interview's per-persona questions are driven by the resolved
  registry's own membership rather than by `_GATEWAY_PERSONA_ORDER`
  (`install.py:471-478`). A registry with more or fewer than the shipped six is
  interviewed correctly; a gateway install's transcript for the shipped six is
  unchanged.
- **FR-013** — Choosing the gateway leaves the interview byte-for-byte today's,
  proven by the existing install suite passing unmodified.

## What already exists, and where

| Piece | Where | State |
| --- | --- | --- |
| The subscription sentinel | `SUBSCRIPTION_AGENT`, `factory/config.py:145-149` | Real, used, and two personas in this repo's `personas.yaml` declare it |
| Routing predicates | `routes_through_gateway` `config.py:203-208`; `needs_virtual_key` `:210-216` | Already exclude subscription and deterministic personas — no change needed |
| Credential discovery | `discover_subscription_credential`, `adapter.py:797-830` | Three file paths, no env route; `environ` param resolves XDG only |
| Per-node HOME seeding | `_seed_node_home`, `adapter.py:833-867` | Copies the credential at 0600; docstring records the rotation hazard as unmeasured |
| Dispatch-time refusal | `adapter.py:996-1008` | Named refusal before the sandbox forks — the right shape, wrong remedy string |
| Alias derivation | `gather_gateway_aliases`, `verify.py:386-402` | Already skips non-gateway personas; returns `{}` for an all-subscription registry |
| The surrender-text precedent | `DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT`, `config.py:350-360`, printed at `install.py:1602` | The exact shape FR-006 and FR-011 copy |
| The declared-absent precedent | memory / telemetry / escalation probes, verify output on the 2026-08-27 demo run | `[PASS] escalation: escalations will be dropped…` is the model for FR-008 |
| Subscription accounting | `_is_subscription_lease`, `usage_activities.py:517-535` | A subscription attempt already has no proxy spend to read; unchanged |
| The gateway's three jobs | spec 055, and `docs/decisions.md` on the declared choice | Dropping the gateway surrenders two security properties, not one bookkeeping feature |

## Technical approach, story by story

### US1 — a token is a credential the factory can take

Widen the discovery result. A frozen two-field result (`token: str | None`,
`path: Path | None`) is enough, and it makes the seeding decision a branch on
data rather than on a `None` check that cannot distinguish "no credential" from
"a credential that is not a file". `_seed_node_home` takes the result instead of
a path: token → nothing written, env carries it; path → today's copy at 0600.
The adapter's environment assembly gains one variable on the token branch.

### US2 — no gateway is a declaration, not a failure

Three edits, each small and each in a file that already has the shape for it.
`config.py` gains a `"none"` member of `KNOWN_LL_MODES`, an `LLMNone` block
mirroring `LLMDirect`, and a surrender text beside the existing one. The registry
cross-check (FR-007) belongs with the other control-plane refusals rather than
inside the probe, because it is a property of the declaration and should fail at
parse or verify time, not at dispatch. `verify.py` loses its assertion, gains the
declared-absent branch, and keeps every other verdict.

### US3 — the interview can produce that position

One new answer in the LLM question, wired to the same disclosure-then-accept
ordering `direct` uses. `_GATEWAY_PERSONA_ORDER` becomes a derivation over the
resolved registry, filtered to gateway personas — the constant's *order* is worth
keeping as a sort key for a stable transcript, but its *membership* stops being
the source of truth.

## Traps

**T1 — this is a security surrender, and the text is the deliverable.** The
temptation is to write `none` as "no gateway configured" and move on. Recalled
and load-bearing: the gateway delivers the agent's credential so a sandboxed
agent never holds the operator's real one, and makes persona-to-model routing
enforceable because the minted key's model list derives from the registry. Only
spend attribution is bookkeeping. A surrender text that says "you lose spend
tracking" is wrong by two thirds and is the failure mode this trap exists to
prevent. Spec 055 already settled that this must be a declared choice; FR-006 is
that ruling applied to a third mode.

**T2 — `none` must not become a way to run gateway personas without a gateway.**
FR-007 is the load-bearing half of this story. Without it, `none` is a footgun
that turns a config error into a dispatch-time failure with nothing in verify to
have caught it — which is precisely the class of defect the whole `--verify`
surface exists for.

**T3 — do not collapse "declared absent" into "not configured".** The comment at
`verify.py:649-650` is right about the case it was written for: an empty alias
set from an unconfigured registry is a failure, and the `example/` placeholder
check (`:441-451`) is the same instinct. FR-008 adds a branch **gated on the
declaration**; it must not widen to "empty aliases always pass". A test that
proves the unconfigured case still fails is not optional (spec US2-S5).

**T4 — the token must not resurrect `ANTHROPIC_AUTH_TOKEN`.** The subscription
route's defining property is that the child runs on the CLI's own credential
rather than on a gateway-issued one, and 070-US2 FR-006 states it as an absence
of two variables. Adding a third variable is correct; setting either of the two
old ones because it is convenient is a silent return to gateway semantics with
no gateway behind it.

**T5 — precedence between token and file must be stated, not emergent.** Both
will exist on the floor host, where a credentials file has sat since before this
spec and a token may be exported for a container. If the order falls out of
whichever check happens to come first in the function body, two operators get two
behaviours and neither can predict theirs. FR-004 and its test are the fix.

**T6 — `claude login` is not a command.** The current refusal
(`adapter.py:1007`) tells operators to run it. Measured on Claude Code 2.1.223:
`claude login --help` falls through to top-level help identically to a nonsense
subcommand, while `claude auth login --help` resolves. The first error a
subscription operator ever sees currently hands them a remedy that silently does
nothing.

**T7 — do not touch spend attribution for gateway attempts.** A subscription
attempt already has no per-key spend and `usage_activities.py:517-535` already
handles that. Nothing in this spec changes what a gateway-routed attempt records,
and a diff that edits the ledger's gateway path is out of scope.

**T8 — `_GATEWAY_PERSONA_ORDER` has two jobs and only one is wrong.** It supplies
membership (wrong — the registry knows) and a stable order for the transcript
(fine). Deleting it outright makes the interview's question order depend on dict
iteration, which is a reproducibility regression in a transcript operators read
and diff. Keep it as a sort key.

## Work Graph

```yaml
US1:
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
  depends_on: []
US2:
  implements: [FR-006, FR-007, FR-008, FR-009, FR-010]
  depends_on: []
US3:
  implements: [FR-011, FR-012, FR-013]
  depends_on: []
  depends_on_merged: [US2]
```

Chain depth 2. US1 runs alongside from round one — it owns `adapter.py` and
touches neither the config schema nor the installer.

## Sizing

Three stories. US2 is the largest and the one whose blast radius is widest: it
edits the control-plane schema, which every config in existence is parsed by.
US1 is one function's return type and one seeding branch. US3 is one interview
answer and one derivation.

**US2 is the one at risk.** Its unit of value is "a third declared position
exists and verify understands it" — not "the control-plane config is
refactored". `LLMDirect` is the template; mirror it and stop. Every existing
config must parse unchanged, and the existing control-plane suite passing
unmodified is the cheapest proof of that.

## File contention

| story | owns |
| --- | --- |
| US1 | `factory/workgraph/adapter.py`, its tests (new file) |
| US2 | `factory/controlplane/config.py`, `factory/controlplane/verify.py`, its tests (new file) |
| US3 | `factory/cli/install.py`, its tests (new file) |

No two stories share a file. US3 is sequential on US2 by semantics — the answer
it writes must be a mode the parser accepts — not by contention.

## Dispatch hazards, for the operator running this epic

- **Re-derive the workgraph at dispatch** with `--target-repo "$PWD"` from the
  operator checkout; the committed artifact carries compile-time absolute paths.
- **US1 edits `adapter.py`, which is the module every dispatched attempt runs
  through.** Never modify it while an attempt is in flight; the worker imports it
  live. Check `ergane status` reads `epics: none running` before dispatch.
- **This floor runs on the subscription route.** Two personas in `personas.yaml`
  declare `agent: subscription`, and the credential file at
  `~/.claude/.credentials.json` is the one US1 is changing the handling of. A
  regression here does not fail a test — it stops the floor. The existing
  subscription suites (`tests/test_subscription_credential.py`,
  `test_subscription_routing.py`, `test_subscription_accounting.py`,
  `test_rung_resolves_its_own_model.py`, 29 tests) passing is a gate, not a
  formality.
- **Do not run `scripts/gate-commit` while an attempt is in flight.**

## Verification the operator will run, independent of the gate

Every test in this spec runs against scratch homes and parsed configs, because
the thing it is for is a machine that this machine is not: one with a
subscription and no gateway.

After it lands: on such a machine — or on this one with the gateway config set
aside — run `claude setup-token`, export `CLAUDE_CODE_OAUTH_TOKEN`, run
`ergane install` and choose the no-gateway answer, read the surrender text before
confirming, run `ergane install --verify` and read a green `llm` line, then
dispatch one real story and watch it reach PASSED. The evidence is the green
verify line and the passing story, in that order; the first without the second
proves only that a declaration parses.
