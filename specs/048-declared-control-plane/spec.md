---
state: landed
# Attested landed 2026-08-16 by an operator session, after `ergane spec landed
# specs/048-declared-control-plane --default-branch ergane-buildout` observed every
# story in git: US1 1b2c1b6a, US2 f390a449, US3 5b439d42, US4 c00c9981.
# Every story passed the real bwrap boundary gate and an LLM judge on a diff
# that fit whole; US4 judged 5 of 5 at 60,533 bytes with truncated_input=False.
# US4's first full gate failed on
# `test_hanging_agent_is_killed_at_deadline_with_no_survivors`, established as
# unrelated by control -- that test alone passes in bwrap on this branch and on
# the clean tip, the full gate passes on the clean tip, and the re-run passes
# here. Filed as `ci/the-deadline-boundary-test-fails-intermittently-in-the-full-suite`.
#
# US4 also produced the `.pyc` finding this repository now carries as a trap in
# every plan: CPython validates a cached bytecode file on (mtime-seconds, size)
# only, so two same-size mutants written inside one wall-clock second make the
# second run execute the first's bytecode.
# Flipped to ready 2026-08-16 by the operator session after reading all three
# documents. What decided it: every scenario ends "proven by a committed test",
# and the anti-vacuity is designed rather than asserted — US1-S3 binds the config
# path to a file the parser would refuse, so a resolver that opened it could not
# have passed; US1-S2 is the override-wins case and is named in the spec as the
# scenario under which this repository's own worker keeps running unchanged.
# Fifteen traps, of which trap 13 is the one that matters most: verify.py reads
# Temporal config-first and that is the bug, not the pattern to copy.
#
# Two findings this spec owns were corrected during drafting rather than
# inherited. The drafting session disproved three claims in the operator's brief
# and one in the finding's own proof text; the ledger entry has been rewritten.
# The sharpest correction is now the spec's framing: `direct` verifies more
# cleanly than `gateway` does, and `direct` is the mode that cannot dispatch.
# Drafted 2026-08-16 by an operator session, from one open critical finding:
# `install/the-config-install-writes-reaches-nothing-that-builds`, filed the
# same morning (13:53Z) by walking install → init → build as an end user
# against a built wheel, ahead of a real install on a second host.
#
# The finding's sibling from the same walkthrough —
# `install/the-wheel-ships-no-persona-registry-so-an-installed-ergane-cannot-dispatch`
# — was fixed in `b63388c` (#103) and is NOT in this spec's scope; the ledger
# entry is stale, not the tree. Between the two of them they were the whole of
# "Ergane installs but does not work when installed"; this is the half that
# remains.
#
# US4 (Temporal) was added on the operator's direction after drafting: the goal
# is proving Ergane runs on a second machine, and one subsystem whose
# declaration reaches nothing means that machine still needs a hand-set
# variable. A spec named `declared-control-plane` that joins the LLM
# declaration and leaves Temporal's dangling does not earn the name.
#
# Every acceptance scenario here is decidable from the story's diff alone
# (D-037 / constitution principle VIII): there is no scenario of the form "on a
# second machine it works", because a diff cannot show a second machine. Each
# is instead a committed test driving a fixture config against a fixture
# environment — which is what "a second machine" means to a resolver.
depends_on_landed: [033-ergane-install]
---

# Feature Specification: 048-declared-control-plane

## Context

`ergane install` interviews an operator for five subsystems, writes
`~/.config/ergane/config.toml`, and verifies what it wrote. Nothing on the
dispatch path reads that file. `grep` for `load_controlplane_config` or
`ControlPlaneConfig` across `factory/workgraph/` and `factory/activities/`
returns nothing at all.

What the build reads instead is two environment variables:
`factory/usage/litellm_client.py:56-57` names them `LITELLM_PROXY_URL` and
`LITELLM_MASTER_KEY`, `from_env` (`:146`, `:149`, `:154`) reads both straight
from `os.environ`, `factory/cli/nouns/build.py:371` refuses to start an epic
without the first, and `factory/activities/roadmap_activities.py:357` reads the
second by name. Meanwhile the interview's default for the credential's variable
is `ERGANE_LLM_MASTER_KEY` (`factory/cli/install.py:65`). Two naming schemes,
no connection between them.

So the first-install experience is: complete the interview, run
`ergane build start`, and be told

```
LITELLM_PROXY_URL is not set; the agent's virtual key is only honored at the
proxy, so no epic can be started without it
```

— naming a variable the interview never mentioned, about an endpoint the
operator just declared. Nothing in the install output warns that its answers
will not be used.

The config file is not unused. `factory/registry.py:223` reads it for a repo's
memory scopes, `factory/notify/adapter.py:255` reads it to choose the
escalation transport, and `factory/cli/init.py:649` runs its verifier. It is a
file the *dispatch path* ignores, which is a narrower and more fixable problem
than a file nobody wants.

### The inversion, stated plainly

The obvious story about this defect — "install declares, the build ignores,
they drifted" — is not what the tree shows. What the tree shows is that the two
were never joined at all, and the evidence is that **the one LLM mode that
verifies cleanly is the one mode that cannot dispatch.**

The interview offers `llm.mode = "direct"` — per-persona
`base_url`/`model`/`api_key_env` (`KNOWN_LL_MODES` at
`factory/controlplane/config.py:31`, seeded at `factory/cli/install.py:501-502`,
probed at `factory/controlplane/verify.py:182`). Its probe performs a real HTTP
round trip against the declared endpoint using only declared values
(`verify.py:218-232`, called at `:250`) and reports PASS on a host with no
`LITELLM_*` variable set at all.

`gateway` mode — the mode that *can* dispatch — cannot do that.
`LLMProbe.gather` resolves the credential correctly through the declared name
(`api_key_env = gateway.master_key_env` at `verify.py:206-207`) and then builds
its client through `LiteLLMClient.from_env()` at `verify.py:110`, which reads
the legacy variables. So the gateway check fails on a freshly-installed host
until the operator also exports `LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY`.
The repository's own test says so out loud —
`tests/test_controlplane_verify.py:927-933` sets **three** variables to verify
one endpoint, with the comment `# LiteLLMClient.from_env() is called first and
requires these env vars.`

Both halves of that collision live inside one function. A subsystem that had
drifted would verify its declaration and fail at use; this one verifies a
declaration it cannot use and fails to verify the declaration it can. That is
not drift. That is a seam nobody owned: 033 owns the declaration, the 001/005
dispatch path owns the consumption, and no story ever owned the join.

Meanwhile `issue_attempt_key` (`factory/activities/usage_activities.py:181`)
mints a LiteLLM **virtual key** through `open_client()` (`:158-164`, `:197`),
which is `LiteLLMClient.from_env()`. There is no other route to an attempt's
credential. `direct` is a choice a user can make, that passes verification more
cleanly than the supported mode does, and that cannot run a single attempt.

Temporal is the same shape one subsystem over: the interview writes
`temporal.address` and `temporal.namespace` (`factory/cli/install.py:294-309`),
and every operational connect reads `os.environ` instead — ten sites, listed in
the plan. Its verify probe, uniquely, reads the config *first* and falls back
to the environment (`verify.py:118-119`, `:308-309`), which is the opposite
precedence from everything else and lets the probe check a different server
than the worker connects to.

One principle covers all of it: **what an operator declares is what the factory
builds against, and a declaration the factory cannot honour is refused where it
is made rather than discovered at the first attempt.**

---

### User Story 1 - The build resolves its endpoint and credential from what was declared (Priority: P1)

The config already stores the right shapes. `ControlPlaneConfig.LLMGateway`
(`factory/controlplane/config.py:119-125`) carries `base_url` and
`master_key_env` — the **name** of the environment variable holding the key,
never the key, which is the correct shape under principle V and is enforced by
`_reject_secret_shape` (`config.py:799`). The gateway verify probe already
resolves the credential exactly this way at `verify.py:206-207`. Nothing on the
dispatch path does the same.

One resolver, consulted everywhere the endpoint or the credential is needed.
The environment stays authoritative when it speaks: `LITELLM_PROXY_URL` and
`LITELLM_MASTER_KEY` become **overrides**, so a host already exporting them —
including this development host and its running worker — resolves exactly as it
does today, and a change that required re-provisioning this machine to keep
working would be a failed change. That direction is deliberate rather than
incidental, and it is recorded as such: the day `ergane install` is the normal
path, inverting the precedence is a migration with its own story, not a
refactor.

**Why this priority**: It is the whole of the finding's first consequence, and
it is the single largest obstacle to Ergane running on a host other than the one
it was developed on. Every other story here either depends on it or is
pointless without it.

**Independent Test**: Drive resolution against a fixture config declaring a
gateway and a fixture environment holding only the declared variable, and
confirm both values resolve; then set the overrides and confirm they win and
the file is not consulted.

**Acceptance Scenarios**:

1. **Given** a fixture config declaring `llm.base_url` and
   `llm.master_key_env = "DECLARED_KEY_VAR"`, and a fixture environment where
   `DECLARED_KEY_VAR` is set but neither `LITELLM_PROXY_URL` nor
   `LITELLM_MASTER_KEY` is, **When** the gateway is resolved, **Then** the
   resolved endpoint is the declared `base_url`, the resolved credential
   variable is `DECLARED_KEY_VAR`, and each carries the config path as its
   source — proven by a committed test.

2. **Given** the same fixture config and a fixture environment where
   `LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY` are both set to values
   different from the declared ones, **When** the gateway is resolved, **Then**
   the environment's values win and each source names the environment variable
   it came from — proven by a committed test. This is the scenario under which
   this repository's own worker keeps running unchanged.

3. **Given** `LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY` set, and the config
   path bound to a file the parser would refuse (malformed TOML), **When** the
   gateway is resolved, **Then** resolution succeeds from the environment and
   raises nothing — proven by a committed test whose fixture file is
   unparseable, so a resolver that opened it could not have passed.

4. **Given** a fixture environment with neither override set and the config
   path bound to a file that does not exist, **When** an epic start resolves
   its endpoint, **Then** it refuses naming both routes — the environment
   variable and the config path — and the message contains no credential value
   — proven by a committed test asserting on the refusal text.

5. **Given** a fixture environment with neither override set and the config
   path bound to a file the parser refuses, **When** resolution runs, **Then**
   the refusal carries the parser's own reason and names the file, rather than
   reporting that an environment variable is not set — proven by a committed
   test.

6. **Given** a fixture config declaring `master_key_env = "DECLARED_KEY_VAR"`
   with `DECLARED_KEY_VAR` unset and no override set, **When** the credential
   is resolved, **Then** the error names `DECLARED_KEY_VAR` and the config path
   and nothing else — proven by a committed test, preserving the discipline
   `from_env` already keeps at `factory/usage/litellm_client.py:148-150`.

7. **Given** a fixture environment whose declared credential variable holds a
   planted sentinel value, **When** the resolution object is produced and its
   `repr` taken, **Then** the sentinel appears nowhere in it — proven by a
   committed test, because the resolution carries a variable *name* and never a
   value.

8. **Given** a fixture environment exporting both overrides, **When** an epic
   is started, **Then** the `EpicInput` it builds is byte-identical to the one
   built today from the same inputs — proven by a committed test comparing
   against the current construction.

9. **Given** the diff, **When** `docs/decisions.md` is read, **Then** it
   carries a new numbered entry recording that the environment overrides the
   declaration, why that direction was chosen (a change requiring this host to
   be re-provisioned to keep working is a failed change), and that inverting it
   once install is the normal path is a migration with its own story — proven
   by the diff containing the entry.

---

### User Story 2 - A declaration the dispatch path cannot honour is refused where it is made (Priority: P1)

`direct` mode cannot reach dispatch, and making it reach dispatch is not a
story. Every LLM-consuming node runs on its own model-constrained, TTL'd
virtual key issued at dispatch and revoked at teardown — that is principle V,
and it is the primitive that ties every token to a node without agent
cooperation. A per-persona provider endpoint has no such primitive: there is
nothing to mint, nothing to revoke, and nothing to attribute. Honouring
`direct` therefore means building a second attribution mechanism, which is an
epic and a constitutional amendment, not a story in a bugfix spec.

So the mode is refused where it is declared. The tree already has the shape for
exactly this: `temporal.mode = "managed"` is a recognized token that the parser
refuses until 042 lands, with its own rule slug
(`RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED`, `config.py:54`, raised at `:437-443`).
`direct` gets the same treatment — recognized by name so the refusal can be
specific rather than "unknown mode", and refused with a message that says *why*
dispatch cannot honour it and what to do instead: put a LiteLLM-shaped gateway
in front of the provider, which is what `gateway` mode already is.

The user who wanted `direct` is not silently deprived of it. They are told, at
the moment they ask for it, that the mode is recognized, that per-attempt
attribution is the reason it cannot be served, and what the supported route is.
That is strictly better than a green verification they cannot build against.

**Why this priority**: Refusing at install costs one message. Discovering it at
the first attempt costs a dispatched epic, a minted-key failure and an
operator's afternoon — and today it does not even fail loudly, because the
probe passes.

**Independent Test**: Parse a config declaring `direct` and read the refusal;
run the interview's mode question and confirm `direct` is neither offered nor
accepted; run verification against a `direct` config and confirm no check
reports PASS.

**Acceptance Scenarios**:

1. **Given** a config document declaring `llm.mode = "direct"`, **When**
   `parse_controlplane_config` runs, **Then** it raises with a stable rule slug
   whose message names dispatch's virtual-key requirement as the reason and
   names `gateway` as the supported route — proven by a committed test
   asserting on the slug and the message.

2. **Given** the diff, **When** `factory/cli/install.py` is read, **Then** the
   llm mode question no longer offers `direct` and no seed constructs a
   `direct` block — proven by a committed test that answers `direct` to the
   mode question and asserts the interview re-asks carrying the parser's
   refusal, exactly as it does for any other value the parser rejects.

3. **Given** a config file on disk declaring `llm.mode = "direct"` — an
   operator who installed before this change — **When** `ergane install` is
   re-run, **Then** it fails closed naming the file and the reason rather than
   silently rewriting it, through the existing `_starting_document` path
   (`factory/cli/install.py:171-180`) — proven by a committed test.

4. **Given** a config file declaring `llm.mode = "direct"`, **When**
   `ergane install --verify` runs, **Then** it reports the parser's refusal and
   no check reports PASS — proven by a committed test, because a mode that
   verifies green and cannot dispatch is the defect itself.

5. **Given** the diff, **When** `factory/controlplane/config.py`,
   `factory/cli/install.py` and `factory/controlplane/verify.py` are read,
   **Then** none of them contains a code path that constructs, renders or
   probes a `direct` LLM block — proven by a committed test that parses each
   module's AST rather than grepping it.

6. **Given** the diff, **When** `docs/decisions.md` is read, **Then** it
   carries a new numbered entry recording the removal: the alternative
   considered (make `direct` reach dispatch), why it was rejected (a second
   per-attempt attribution primitive, which is an epic and touches principle V),
   what a user who wanted `direct` is told, and the
   `temporal.mode = "managed"` precedent it follows — proven by the diff
   containing the entry.

---

### User Story 3 - The operator can see which source won for each value (Priority: P2)

`ergane env` (`factory/cli/env.py:51-62`) reports which variables are set. After
US1 that is no longer the whole question: two sources can supply the same value,
and "`LITELLM_PROXY_URL` is not set" stops meaning "the build cannot start". The
report an operator needs on a strange host is *which source won*, per value.

That report arrives as a new `--sources` mode rather than as a change to what
the command prints by default. The default listing is something an operator may
already be reading on an unfamiliar machine, and rewriting a diagnostic's
default output inside the spec whose whole point is that diagnostics were lying
is the wrong trade.

One exception, deliberately narrow: `_ENTRIES` describes
`LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY` as `required` (`env.py:33-34`).
US1 makes that false — they are overrides — and a report that calls an override
required sends an operator to export a variable they do not need. Correcting a
word that has become untrue is not the same act as restructuring the output,
and leaving it would be this spec shipping its own defect.

**Why this priority**: US1 is correct without it and US3 is useless before it.
It is what makes US1 checkable by a human on a machine that is not this one,
which is the point of the whole spec.

**Independent Test**: Run the command in both modes against each combination of
fixture config and fixture environment, and read which source it names.

**Acceptance Scenarios**:

1. **Given** a fixture config declaring a gateway and a fixture environment
   where only the declared credential variable is set, **When**
   `ergane env --sources` runs, **Then** its output names the config path as
   the source of the endpoint and names the declared variable as the source of
   the credential — proven by a committed test asserting on captured output.

2. **Given** the same fixture config and a fixture environment where both
   overrides are set, **When** `ergane env --sources` runs, **Then** its output
   names the environment variable as the winning source for both values —
   proven by a committed test.

3. **Given** a fixture environment whose declared credential variable holds a
   planted sentinel value, **When** `ergane env --sources` runs, **Then** the
   sentinel appears nowhere in the captured output — proven by a committed
   test.

4. **Given** a fixture environment with neither override set and no config file,
   **When** `ergane env --sources` runs, **Then** it reports both values as
   unresolved, names both ways each could be satisfied, and still exits zero —
   a report is not a gate — proven by a committed test asserting on output and
   exit code.

5. **Given** the diff, **When** `factory/cli/env.py` is read, **Then** bare
   `ergane env` renders byte-identically to today for every entry except that
   `LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY` are no longer described as
   `required` — proven by a committed test asserting byte-equality for the
   unchanged entries and asserting on the rendered source text for those two.

---

### User Story 4 - Temporal connects to what was declared (Priority: P2)

The interview asks for `temporal.address` and `temporal.namespace`
(`factory/cli/install.py:294-309`) and writes them. Ten operational sites
connect to Temporal, and every one of them reads `os.environ` instead — the
worker itself at `factory/worker.py:221-222`, the CLI's client seam at
`factory/cli/nouns/__init__.py:51-52`, and eight more listed in the plan. On a
freshly-installed host the operator declares an address and then still has to
export `TEMPORAL_ADDRESS` before anything connects.

The verify probe is worse than silent: it reads the config *first* and falls
back to the environment (`factory/controlplane/verify.py:118-119`, `:308-309`),
which is the opposite precedence from everything else in the tree. Where the
two sources disagree, `ergane install --verify` reports on one server while the
worker connects to another — a green check about a machine nothing runs on.

This is US1's resolver pointed at a second pair of values, with the same
override direction, so that one precedence holds everywhere.

**Why this priority**: The operator's goal is proving Ergane runs on a second
machine. One subsystem whose declaration reaches nothing means that machine
still needs a hand-set variable, and a spec named `declared-control-plane` that
joins the LLM declaration and leaves Temporal's dangling does not earn the name.
It is P2 rather than P1 because an epic that cannot mint a key never gets far
enough to care where Temporal is.

**Independent Test**: Resolve against a fixture config declaring an address and
namespace with no `TEMPORAL_*` variables set, then with them set to different
values, and confirm the precedence and the reported source in both.

**Acceptance Scenarios**:

1. **Given** a fixture config declaring `temporal.address` and
   `temporal.namespace` and a fixture environment with neither `TEMPORAL_ADDRESS`
   nor `TEMPORAL_NAMESPACE` set, **When** the Temporal connection target is
   resolved, **Then** both come from the config and each carries the config path
   as its source — proven by a committed test.

2. **Given** the same fixture config and a fixture environment setting both
   variables to different values, **When** the target is resolved, **Then** the
   environment wins for both and each source names its variable — proven by a
   committed test, the same direction US1 establishes.

3. **Given** a fixture config declaring an address and a fixture environment
   setting `TEMPORAL_ADDRESS` to a different one, **When** the verify probe
   resolves its target, **Then** it probes the same address the operational
   path would use — proven by a committed test, because a probe that checks a
   server nothing connects to is the defect this story exists to close.

4. **Given** neither a config nor an environment variable, **When** the target
   is resolved, **Then** it falls back to `DEFAULT_TEMPORAL_ADDRESS` and
   `DEFAULT_TEMPORAL_NAMESPACE` (`factory/notify/service.py:108`, `:111`)
   exactly as today, and no site carries its own hardcoded literal — proven by
   a committed test plus a committed test reading the diff for literals.

5. **Given** `ergane env --sources`, **When** it runs against a fixture config
   declaring Temporal, **Then** it reports the winning source for the address
   and the namespace alongside the LLM values — proven by a committed test.

---

## Functional Requirements

- **FR-001**: The dispatch path MUST resolve the LLM gateway's endpoint and the
  *name* of the variable holding its credential from the control-plane config
  when the environment does not override them.
- **FR-002**: `LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY` MUST remain
  overrides that win over the config, and when an override is set the config
  file MUST NOT be read for that value.
- **FR-003**: A resolution MUST carry the credential's variable name and never
  its value. No resolved credential may enter a config file, a log line, an
  error message, a workflow input, a status payload, or a test's asserted
  output.
- **FR-004**: Where nothing resolves, the refusal MUST name both routes — the
  environment variable and the config path — so an operator is told the two
  ways to satisfy it rather than one.
- **FR-005**: With no override set, a config the parser refuses MUST surface
  the parser's own refusal naming the file, never be reported as an unset
  environment variable.
- **FR-006**: Every site that builds a workflow input from a proxy endpoint
  MUST obtain it from the one resolver; no second copy of the precedence may
  exist.
- **FR-007**: Resolution MUST happen in a CLI entry point or an activity; no
  workflow-scoped function may read the config file or the process environment
  (constitution IV; guarded by `tests/test_workflow_env_guard.py`).
- **FR-008**: `llm.mode = "direct"` MUST be refused by the parser with a stable
  rule slug whose message names the reason and the supported route.
- **FR-009**: The interview MUST NOT offer, seed, render or accept a `direct`
  LLM block.
- **FR-010**: Verification MUST NOT report a passing finding for a mode the
  parser refuses.
- **FR-011**: `ergane env --sources` MUST report, for every value this spec
  resolves, which source supplied it and what the alternative route was.
- **FR-012**: Every test this spec adds that exercises config resolution MUST
  bind the config path explicitly and MUST NOT resolve the operator's real
  `~/.config/ergane/config.toml`.
- **FR-013**: The precedence direction MUST be recorded in `docs/decisions.md`
  as a new numbered entry, as a deliberate and revisitable choice rather than
  an accident of implementation order.
- **FR-014**: The removal of `direct` MUST be recorded in `docs/decisions.md`
  as a new numbered entry naming the alternative considered, why it was
  rejected, what a user who wanted it is told, and the precedent it follows.
- **FR-015**: Temporal's address and namespace MUST resolve from the
  control-plane config when the environment does not override them, through the
  same resolver and the same precedence as FR-001, at every operational connect
  site.
- **FR-016**: Verification MUST resolve Temporal's address and namespace with
  the same precedence as the operational path, so no probe can report on a
  server the worker does not use.
- **FR-017**: Bare `ergane env` MUST render byte-identically to today for every
  entry except the two override variables, which MUST NOT be described as
  required.

## Success Criteria

- **SC-001**: A fixture host exporting `LITELLM_PROXY_URL` and
  `LITELLM_MASTER_KEY`, with no control-plane config, builds an `EpicInput`
  byte-identical to today's — the parity half, and the reason this repository's
  own worker needs no re-provisioning.
- **SC-002**: A fixture host with neither `LITELLM_*` variable set and a config
  declaring a gateway resolves both endpoint and credential, and the client
  built from that resolution issues its request to the declared endpoint
  carrying the value found in the declared variable.
- **SC-003**: `llm.mode = "direct"` cannot be written by the interview, cannot
  be accepted by the parser, and produces no passing verification finding.
- **SC-004**: **Control.** With the config branch of the resolver disabled
  through its seam, the SC-002 fixture refuses exactly as the tree refuses
  today — establishing that the new branch changed the outcome, rather than the
  fixture having resolved for some other reason.
- **SC-005**: A sentinel credential planted in a fixture environment appears in
  no resolver output, no `ergane env` output, no refusal message and no
  workflow input.
- **SC-006**: A fixture config and a fixture environment declaring *different*
  Temporal addresses resolve to one address across the operational path and the
  verify probe — the probe can no longer report on a server nothing connects
  to.

## Out of Scope

- **Making `direct` mode dispatch.** It needs a per-node attribution primitive
  that does not exist, and inventing one touches a NON-NEGOTIABLE principle.
  US2 refuses it, says so, and records why; resurrecting it is a future epic
  with its own decision entry, not a knob.
- **`memory`, `telemetry` and `escalation`.** `memory` and `escalation` are
  already read (`factory/registry.py:223`, `factory/notify/adapter.py:255`) and
  `telemetry` reaches nothing operational by design. Only the LLM endpoint and
  Temporal block a second host, and those are US1 and US4.
- **Packaging.** `install/the-wheel-ships-no-persona-registry…` was the other
  half of the same walkthrough and was fixed in `b63388c` (#103); nothing here
  touches `pyproject.toml` or `factory/config.py`.
- **The PR-body credential sweep.** `factory/activities/merge_activities.py:339-340`
  reads both variables only to hand them to a renderer that deliberately drops
  them (`factory/mergequeue/messages.py:82`). It consumes nothing and decides
  nothing; leave it alone.
- **Removing the duplicated epic-start handler.** `factory/workgraph/cli.py:457`
  is a second copy of `factory/cli/nouns/build.py:371`'s refusal. FR-006 makes
  both call one resolver; consolidating the two handlers is a separate cleanup.
- **`temporal.tls_enabled` and `temporal.api_key_env`.** The config carries
  both (`config.py:152-153`); no connect site honours either. That is a
  Temporal Cloud story, and it needs a credential path US4 does not build.
- **Any change to what a virtual key is or how it is issued.** This spec
  changes where the endpoint and credential come from, never what is done with
  them.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-012, FR-013]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-008, FR-009, FR-010, FR-014]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-011, FR-017]
US4:
  depends_on: []
  depends_on_merged: [US2, US3]
  implements: [FR-015, FR-016]
```
