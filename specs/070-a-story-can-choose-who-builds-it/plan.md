# Implementation Plan: a story can choose who builds it

**Spec**: `specs/070-a-story-can-choose-who-builds-it/spec.md`

## What already exists, and where

**Every line below was verified on 2026-08-19 by reading that exact line
number**, not by reading `grep -A` context and counting. That distinction is not
pedantry: the three specs drafted immediately before this one carried anchors off
by one to three lines throughout, and a review caught 68 attempt-costing defects
in them. Check each against the tree anyway.

**US1 — pinning:**

- `factory/workgraph/derive.py:79` — `_OPTIONAL_KEYS = ("timeout", "depends_on_merged")`.
  The list a new optional key joins.
- `factory/workgraph/derive.py:186` — `persona=IMPLEMENTER,`. **The hardcode.
  This line is the defect.**
- `factory/workgraph/derive.py:193` — `timeout_override_s=declaration.timeout,`.
  **This is the pattern to copy**: an optional Work Graph key becoming a
  per-node override field.
- `factory/workgraph/models.py:173` — `timeout_override_s: int | None = None`, the
  field on `WorkNode`.
- `factory/workgraph/models.py:355-363` — `resolve_timeout_s(node, persona)`,
  "persona-first with a per-story override (R8)". The resolution shape.
- `factory/workgraph/models.py:164` — `persona: str` on the declaration/node.
- `factory/workgraph/models.py:228` — `persona: str` on the resolved node.
- `validate_workgraph` in `factory/workgraph/models.py` (immediately after
  `resolve_timeout_s`) — already refuses "every node's persona resolvable in the
  given registry *with* a resolvable timeout". **US1-S3 and US1-S4 must reach
  this existing refusal, not add a second one.**
- `factory/workgraph/models.py:199` — the snapshot discipline US1-S6 asserts: an
  operator editing `personas.yaml` mid-epic changes the next epic, never the one
  in flight.

**US2, US3, US4 — the subscription runner (split 2026-08-19; US2 routing, US3 credential, US4 accounting):**

- `factory/config.py:143` — `DETERMINISTIC_AGENT = "none"`. **The sentinel to
  mirror.** A second sentinel on the same field is the established pattern.
- `factory/config.py:145` — `_REQUIRED_FIELDS = ("agent", "model", "write_scope", "needs_worktree")`.
- `factory/config.py:177` — `agent: str` on `Persona`.
- `factory/config.py:191` — `def is_llm(self) -> bool:`, today `agent != DETERMINISTIC_AGENT`.
  **This binary must become a three-way** — deterministic (no LLM, no key),
  gateway (LLM, key), subscription (LLM, no key). Its only two consumers are
  `factory/workgraph/preflight.py:552` and `factory/controlplane/verify.py:331`;
  read both before changing the property, because "does this persona spend
  tokens" and "does this persona need a virtual key" stop being the same question.
- `factory/config.py:245` — `agent = entry["agent"]`, the parse site.
- `factory/workgraph/adapter.py:774` — `"ANTHROPIC_BASE_URL": context.proxy_url,`
- `factory/workgraph/adapter.py:775` — `"ANTHROPIC_AUTH_TOKEN": context.virtual_key,`
  **These two lines are the whole of gateway billing.** A subscription node omits
  them.
- `factory/workgraph/adapter.py:90` — `PASSTHROUGH_ENV = ("PATH", "LANG", "TERM")`.
  Nothing else crosses from the worker's environment. A credential must arrive
  through the seeded HOME, not by widening this tuple.
- `factory/workgraph/adapter.py:719` — `return Path(factory_root) / "homes" / epic_id / node_id`.
  The per-node HOME.
- `factory/workgraph/adapter.py:740` — `(home / ".gitconfig").write_text(config, encoding="utf-8")`.
  **The seeding site.** The credential goes in beside this, conditionally.
- `factory/verify/toolchain.py` — discover-don't-declare, and the `ToolchainError`
  precedent US3-S3 wants: a named refusal before the fork.

**US5 — the promotion rung:**

- `factory/verify/models.py:114` — `class NextAction(StrEnum)`; members PASSED,
  RETRY, DEBUGGER, ESCALATE, KILLED.
- `factory/verify/ladder.py:60` — `DEBUGGER_PERSONA = "debugger"`. **The pattern:
  a rung is a persona constant plus a counter that partitions history.**
- `factory/verify/ladder.py:63-97` — `next_action`. Read the real line numbers
  yourself; the three specs before this one cited them wrongly.
- `factory/verify/ladder.py:111-119` — `_attempts_spent`, counting records whose
  persona is not the debugger. **A third rung breaks this partition unless it is
  taught about the new persona.**
- `factory/verify/ladder.py:122-124` — `_debugger_cycles_spent`.
- `factory/verify/factory_yaml.py:121` — `_LADDER_KEYS`, where `max_attempts`,
  `max_judge_retries`, `debugger_cycles` and `escalation_timeout_s` become
  operator-settable. FR-011's dial belongs here.
- `personas.yaml:143` — the `closer` persona. Note its alias 401s today; US5 must
  work with **any** configured promotion persona and must not hardcode `closer`.

## Traps

**1. Do not touch the `implementer` persona.** A diff that edits `implementer` in
`personas.yaml` — its model, its fallback, anything — has exceeded scope, whatever
else it got right.

*Rationale updated 2026-08-19 ~20:20 CT.* This trap used to say "the operator
declined Anthropic API billing and kimi stays the builder". **That is no longer
true** — the operator has since pointed `implementer` at `anthropic/claude-opus-5`
so that every *not-yet-started* epic defaults to it. The trap itself stands, and
now stands harder: the registry is the operator's live dial, it was just moved by
hand, and a story that edits it is fighting the operator rather than building.
Read `personas.yaml` for what it currently says instead of assuming either
wiring.

**2. Do not hardcode `closer`, or any persona name, in code.** Constitution
Principle VII: code never names a model, and `personas.yaml` is the only place an
alias may appear. The promotion target is configuration. `DEBUGGER_PERSONA` at
`ladder.py:60` is a persona *role* constant, which is the precedent — a role name
in code is fine, a model alias never is.

**3. `is_llm` stops being a yes/no question and its two callers must be read.**
`factory/workgraph/preflight.py:552` and `factory/controlplane/verify.py:331` both
ask `is_llm` today and both mean something slightly different by it. One is asking
"should I check this persona's model resolves"; the other is a preflight gate.
A subscription persona spends tokens (so it is an LLM) and needs no key (so the
key-minting path must not treat it as one). Splitting the property without
reading both callers will silently change a preflight.

*Made concrete 2026-08-19, and it is a dispatch-blocker rather than a nuance.*
This trap and trap 17 are two ends of one problem. Once `--model` carries a name
the CLI accepts, that name is **by construction** not one the proxy serves — and
`aliases_to_check` (`preflight.py:544-556`) hands every `is_llm` persona's model
to `check_aliases`, which refuses anything absent from `list_model_ids()`
(`preflight.py:594-614`) with the words *"Nothing was dispatched."* Measured: the
proxy serves 16 aliases, all namespaced; `opus`, `claude-opus-5` and `sonnet` are
all absent and always will be. So a subscription persona declaring the model its
own CLI needs would **park the entire epic at preflight**, with a message
blaming the registry rather than this split. The correct split is therefore not
"spends tokens" vs "needs a key" alone — the alias gate wants a third reading,
**"routes through the gateway"**, and both callers must take that one. US2-S6 and
T053 are the test; note that T014 passes either way, which is exactly why T053
has to exist separately.

**4. The credential must not arrive through `PASSTHROUGH_ENV`.** `adapter.py:90`
is an allowlist of three variables and it is deliberate — widening it re-opens the
whole class 018 closed. The credential belongs in the seeded HOME
(`adapter.py:740`), conditionally, and US3-S2's control test is what proves it
stays out of gateway nodes.

**5. Discover the credential, do not declare its path.** `factory/verify/toolchain.py`
exists because literal paths encoded "one machine on one afternoon". Where Claude
Code keeps its subscription credential is a host fact. Find it, refuse by name if
absent (US3-S3), and never write an operator's home path into code.

**6. A key minted and unused is worse than no key.** FR-006. If the subscription
path still mints a virtual key "just in case", there is a live credential with no
purpose and a spend row that will read zero — which is precisely what FR-009
exists to prevent being confused with free.

**7. Zero is not the same as unknown.** FR-009 and US4-S1. A ledger row recording
`$0` for a subscription attempt is indistinguishable from a free call, and
`ergane usage` will report it as one. The record must say the data does not exist.
This project already reports tokens rather than dollars as the effort signal; a
flat-rate row that says so is honest, a zero is not.

**8. The third rung must not corrupt the first two counts.** US5-S5.
`_attempts_spent` (`ladder.py:111-119`) counts every record whose persona is not
the debugger — so a promoted attempt is counted as an ordinary attempt today, by
default, silently. Decide deliberately whether it should be, and test both
counters either way.

**9. The ladder's caps expire together at defaults.** Filed 2026-08-19 as
`verify/the-ladders-two-caps-expire-together-at-defaults-so-a-control-test-cannot-see-either`,
and proved by mutation: at `max_attempts=3` / `max_judge_retries=2`, a test of cap
behaviour written at default config **passes whether the cap exists or is deleted
outright**. Any US5 test that intends to observe a budget must raise
`max_attempts` above the cap it is testing, or it is structurally unable to fail.
`factory/verify/ladder.py:17-19` documents this.

**10. Every existing ladder test must pass unchanged.** US5-S3, SC-006. A ladder
with no promotion persona configured behaves exactly as today. This is the
cheapest possible regression check and the one a reviewer will run first.

**11. Determinism.** `next_action` is pure and called from workflow code; keep it
pure. Credential discovery is a filesystem read and belongs in an activity, never
in the workflow.

**12. One test file per story, named here.**
- US1 → `tests/test_story_persona_pinning.py`
- US2 → `tests/test_subscription_routing.py`
- US3 → `tests/test_subscription_credential.py`
- US4 → `tests/test_subscription_accounting.py`
- US5 → `tests/test_promotion_rung.py`
If you need a file assigned to another story, the edge declaration is wrong — say
so rather than editing across the line. The three specs before this one declared
stories independent that shared files, in all three cases.

**13. The judge sees the diff and the criteria, nothing else.** SC-001 through
SC-007 require committed output. Redact the credential in SC-002 and say you did.

**14. US2 and US3 both edit `factory/workgraph/adapter.py`, and the edge that
keeps them apart is `depends_on_merged`, not `depends_on`.** US2 removes two
lines from the constructed environment (`:774-775`); US3 adds a conditional write
beside the `.gitconfig` seed (`:740`). Different functions, one file.

*Corrected 2026-08-19.* This trap originally declared `depends_on: [US2]` and
claimed that edge was "doing double duty — logical order *and* contention". **It
was not, and could not.** `validate_workgraph` says it plainly in its own refusal
text: *"an edge gates on either verification or merge, never both (FR-009)"*
(`factory/workgraph/models.py:413-419`). `depends_on` gates on US2 **passing**,
so US3 would have started from a base that did not yet contain US2's
`adapter.py` change while US2 sat in the merge queue — which is the exact
contention the trap claimed to prevent. The declaration now reads
`depends_on_merged: [US2]`, matching what 071's us2 does for the same reason.

Do not "simplify" it back to `depends_on`. If you are US3 and the file does not
look as this plan describes, US2 has landed: re-read it rather than assuming.

**15. Do not re-run the feasibility spike.** It is answered, with its control,
in Sizing below. Re-establishing it costs an attempt and a live subscription call
to learn something already written down. If your reading of the tree contradicts
what is recorded there, say so explicitly rather than quietly redoing it.

**16. Decide, on purpose, whether `persona:` is fingerprint-bearing — and say so
in the diff.** `fingerprint()` (`factory/workgraph/landed.py:319`) hashes four
components, and one of them is `declaration` — the story's **raw declaration YAML
text** from `## Work Graph` (`_story_parts`, `:349`). So adding a `persona:` key
to a story that has already landed changes that text, changes the digest, and
`delta` then **re-opens the landed story** (`factory/workgraph/delta.py:9`).
Default behaviour, no code change required, and it is the exact mechanism behind
`interpreter/editing-implements-on-a-landed-story-reopens-it-into-an-unwinnable-loop`.

This is not hypothetical. Field-reported 2026-08-19 from a consumer install:
re-partitioning `implements` across landed stories produced *"us1 reopened:
fingerprint changed from c569195841... to 9b203a65cf..."*, and the reopened node
branched from a base that **already contained its own work**. Its entire possible
diff was a one-line docstring fix, unjudgeable against eight requirements, so it
burned the ladder to exhaustion while the real story sat landed and green.

The consequence lands on the operator's stated plan, which is to pin *existing*
specs to a different persona — several of which have landed stories. Pinning one
would silently reopen it.

So US1 must not leave this to accident. Either:

- **exclude `persona` from the declaration component** of the fingerprint, so a
  routing change never reopens landed work — and add the test that proves a
  landed story with a newly-added `persona:` key stays landed; or
- **keep it fingerprint-bearing** because who built the code is part of what the
  story means — and then `validate` must **warn by name** when an edit changes a
  landed story's fingerprint, rather than discovering it at dispatch.

Pick one, implement it, and state which in the diff. An implementation that
simply adds the key and never mentions the fingerprint has made this choice by
omission, and it is the expensive one.

**17. The registry's `model` is a *proxy* alias, and `--model` does not take
one.** `argv()` (`adapter.py:931`) passes `context.model_alias` verbatim at
`:938`. That value comes from the persona registry's `model` field
(`factory/config.py:178`), which holds LiteLLM aliases like
`ollama-cloud/kimi-k2.7-code` — names the *proxy* resolves. Remove the proxy, as
US2 does, and there is nothing left to resolve them.

Measured 2026-08-19 against the signed-in CLI, cleared environment, no
`ANTHROPIC_*`:

    --model anthropic/claude-opus-5   exit 1   "There's an issue with the selected
                                                model (anthropic/claude-opus-5). It
                                                may not exist or you may not have
                                                access to it."
    --model opus                      exit 0   "OK"

This is the trap because the failure looks like nothing it is. A node that
authenticates perfectly then exits 1 on its model name, and the message names
neither authentication nor the gateway — so the natural diagnosis is that US3's
credential work is broken, which it would not be. Fix it in US2, where it is
testable over the constructed argv with no credential at all.

**18. An attempt routinely outlives its own access token, and a copied
credential throws the refresh away.** Measured 2026-08-19: `.credentials.json`
carries `expiresAt` and `refreshTokenExpiresAt`; the access token had **5.8
hours** of life. `implementer`'s timeout is **14400s — four hours**
(`personas.yaml:80`). So a long attempt crossing its own expiry is the ordinary
case, not an edge, and the CLI will refresh itself mid-flight.

Where that refreshed token lands is decided by how US3 places the credential. A
plain copy into `.factory/homes/<epic>/<node>` puts it in a directory discarded
at teardown: every attempt re-refreshes from the same stored token. Whether that
is harmless or destructive depends on a fact **nobody has measured** — whether
the provider rotates the refresh token on use. If it does, concurrent nodes
invalidate each other and the operator's own login on this host, which is a
failure that reaches well outside the factory.

Do not resolve this by assuming the benign case. Either establish the rotation
behaviour and say how, or state plainly that it is unestablished and choose the
placement that is safe under both readings. US3-S6 and SC-009 are where the
choice is recorded.

## Sizing

**US1 is small and well-patterned** — an optional key, a field, a resolution, and
reaching an existing validation. `derive.py:193` is the worked example. Perhaps
twenty lines plus tests.

**THE FEASIBILITY QUESTION IS ANSWERED. Do not spend an attempt re-establishing
it.** An earlier draft of this plan said the ceiling of the subscription story
was unknown because nobody had checked whether the Claude Code CLI would
authenticate from a seeded credential inside a bwrap sandbox with `--clearenv`
and a synthetic HOME. **It does.** Run by an operator session on 2026-08-19,
against a sandbox built to mirror `adapter.py` — `--clearenv`, `--ro-bind /usr`,
`--proc`/`--dev`/`--tmpfs`, `/etc/resolv.conf` and `/etc/ssl` from
`_resolver_binds`, the agent binary bound at its link path, `--unshare-pid
--die-with-parent`, and `--setenv` for HOME, PATH, LANG and TERM only:

    $ bwrap --clearenv … --setenv HOME <synthetic> … claude -p "Reply with exactly: SPIKE-OK"
    SPIKE-OK
    EXIT=0

The synthetic HOME contained exactly two files: `.gitconfig` and
`.claude/.credentials.json`. **No `~/.claude.json`, no onboarding state, no
cache, no extra environment variable.** The environment inside the namespace was
verified to be `HOME`, `LANG`, `PATH`, `PWD`, `TERM` and nothing else — no
`ANTHROPIC_BASE_URL`, no `ANTHROPIC_AUTH_TOKEN`.

**And the control, because one green run proves less than it looks.** The same
sandbox with the credential removed and nothing else changed:

    Not logged in · Please run /login
    TRUE EXIT = 1

So the credential is what authenticated it — not an ambient fallback, not a
cached session, not the operator's own login leaking through `--clearenv`.

Three facts from that control that are cheaper to read here than to rediscover:
1. **The failure exit code is 1**, so exit status is a usable signal.
2. **The refusal is printed on STDOUT, not stderr.** A caller watching stderr
   sees an empty error stream and a process that "ran". That is US3-S5's whole
   point and FR-013 exists because of it.
3. `.claude/.credentials.json` is `chmod 600` and 509 bytes on this host, holding
   a `claudeAiOauth` object with `accessToken`, `refreshToken`, `expiresAt`,
   `refreshTokenExpiresAt`, `scopes`, `subscriptionType`, `rateLimitTier`. The
   presence of `expiresAt` and `refreshTokenExpiresAt` is why FR-013 is about a
   credential that is present and *stale*, not only one that is absent.

**US2 (declaration and routing) is medium, and it grew twice on 2026-08-19 — read
this before assuming it is the small one.** It was "two lines omitted from the
environment" when it was split out. It is now five implementation edits: the
sentinel (`config.py`), the `is_llm` split (`config.py`), the omitted gateway
variables (`adapter.py:774-775`), the `--model` translation (`adapter.py:938`,
trap 17) and the alias-gate exclusion (`preflight.py` + `controlplane/verify.py`,
trap 3). Both additions were found by *running* the CLI, not by reading the tree.

They are cohesive — every one of them is the same idea, "a subscription persona
is a different kind of thing from a gateway persona" — and none is individually
large. But the story was already split once for being oversized, so if it fails,
suspect size first: the natural second split is FR-014 (`--model`, which touches
`argv()` alone and needs no credential) into a story of its own, leaving US2 as
the declaration and the `is_llm` split with its two callers.

No credential is involved in any of it, which is why it remains a story of its
own and why it stays testable on any host.

**US3 (the credential) is small-to-medium and its risk is entirely the controls**
— traps 4 and 5, and the negative test that keeps gateway nodes credential-free.
Trap 18 adds a decision rather than much code: where the credential is *placed*
determines what happens to a token refreshed mid-attempt, and one of the two
readings reaches outside the factory to the operator's own login.

**US4 (accounting and bound) is small** and is mostly a decision: what an
unbounded default means. Make it deliberately.

**US5 is medium** and its risk is entirely traps 8 and 9 — a new rung that quietly
changes two existing counters, tested by an assertion that cannot fail.

## Verification the operator will run, independent of the gate

- **Prove US1 by control.** One pinned story, siblings unpinned, in one real
  graph. Both halves asserted.
- **Prove US2 by reading the constructed environment**, and prove the control in
  the same epic: a gateway node that still gets its key and both variables.
- **Prove US3 by running a real node on the subscription**, and prove its control
  the same way: a gateway node in that epic with no credential in its home. The
  sandbox is already known to work (Sizing); what US3 adds is doing it
  conditionally and refusing when it cannot.
- **Prove US3's failure path by taking the credential away.** The measured
  behaviour is exit 1 with the message on stdout — if your handling watches
  stderr it will read that as success.
- **Prove US4's honesty by reading the ledger.** A row that says zero has failed
  even if the node succeeded.
- **Prove US5 by mutation, at a raised `max_attempts`.** At defaults the test
  cannot fail — see trap 9.
- **Prove nothing regressed** by running the existing ladder suite with no
  promotion persona configured.
