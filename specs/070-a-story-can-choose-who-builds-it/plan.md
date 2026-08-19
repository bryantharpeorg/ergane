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

**US2 — the subscription runner:**

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
  precedent US2-S5 wants: a named refusal before the fork.

**US3 — the promotion rung:**

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
- `personas.yaml:143` — the `closer` persona. Note its alias 401s today; US3 must
  work with **any** configured promotion persona and must not hardcode `closer`.

## Traps

**1. Do not touch the `implementer` persona.** The operator declined Anthropic API
billing and kimi stays the builder. A diff that edits `implementer` in
`personas.yaml` — its model, its fallback, anything — has exceeded scope, whatever
else it got right.

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

**4. The credential must not arrive through `PASSTHROUGH_ENV`.** `adapter.py:90`
is an allowlist of three variables and it is deliberate — widening it re-opens the
whole class 018 closed. The credential belongs in the seeded HOME
(`adapter.py:740`), conditionally, and US2-S4's control test is what proves it
stays out of gateway nodes.

**5. Discover the credential, do not declare its path.** `factory/verify/toolchain.py`
exists because literal paths encoded "one machine on one afternoon". Where Claude
Code keeps its subscription credential is a host fact. Find it, refuse by name if
absent (US2-S5), and never write an operator's home path into code.

**6. A key minted and unused is worse than no key.** FR-006. If the subscription
path still mints a virtual key "just in case", there is a live credential with no
purpose and a spend row that will read zero — which is precisely what FR-009
exists to prevent being confused with free.

**7. Zero is not the same as unknown.** FR-009 and US2-S6. A ledger row recording
`$0` for a subscription attempt is indistinguishable from a free call, and
`ergane usage` will report it as one. The record must say the data does not exist.
This project already reports tokens rather than dollars as the effort signal; a
flat-rate row that says so is honest, a zero is not.

**8. The third rung must not corrupt the first two counts.** US3-S5.
`_attempts_spent` (`ladder.py:111-119`) counts every record whose persona is not
the debugger — so a promoted attempt is counted as an ordinary attempt today, by
default, silently. Decide deliberately whether it should be, and test both
counters either way.

**9. The ladder's caps expire together at defaults.** Filed 2026-08-19 as
`verify/the-ladders-two-caps-expire-together-at-defaults-so-a-control-test-cannot-see-either`,
and proved by mutation: at `max_attempts=3` / `max_judge_retries=2`, a test of cap
behaviour written at default config **passes whether the cap exists or is deleted
outright**. Any US3 test that intends to observe a budget must raise
`max_attempts` above the cap it is testing, or it is structurally unable to fail.
`factory/verify/ladder.py:17-19` documents this.

**10. Every existing ladder test must pass unchanged.** US3-S3, SC-006. A ladder
with no promotion persona configured behaves exactly as today. This is the
cheapest possible regression check and the one a reviewer will run first.

**11. Determinism.** `next_action` is pure and called from workflow code; keep it
pure. Credential discovery is a filesystem read and belongs in an activity, never
in the workflow.

**12. One test file per story, named here.**
- US1 → `tests/test_story_persona_pinning.py`
- US2 → `tests/test_subscription_runner.py`
- US3 → `tests/test_promotion_rung.py`
If you need a file assigned to another story, the edge declaration is wrong — say
so rather than editing across the line. The three specs before this one declared
stories independent that shared files, in all three cases.

**13. The judge sees the diff and the criteria, nothing else.** SC-001 through
SC-006 require committed output. Redact the credential in SC-002 and say you did.

## Sizing

**US1 is small and well-patterned** — an optional key, a field, a resolution, and
reaching an existing validation. `derive.py:193` is the worked example. Perhaps
twenty lines plus tests.

**US2 is the largest and the least certain.** Its floor is the environment change
(two lines omitted) and the conditional seed. Its ceiling is unknown, because
whether the Claude Code CLI accepts a seeded credential inside a bwrap sandbox
with `--clearenv` and a synthetic HOME has not been established here. **Establish
that first**, by hand, before writing production code — if it does not work, the
story is a different shape and the operator needs to know within the hour rather
than at the end of the attempt.

**US3 is medium** and its risk is entirely traps 8 and 9 — a new rung that quietly
changes two existing counters, tested by an assertion that cannot fail.

## Verification the operator will run, independent of the gate

- **Prove US1 by control.** One pinned story, siblings unpinned, in one real
  graph. Both halves asserted.
- **Prove US2 by running a real node on the subscription**, and prove the control
  in the same epic: a gateway node that still gets its key and its variables and
  no credential.
- **Prove US2's honesty by reading the ledger.** A row that says zero has failed
  even if the node succeeded.
- **Prove US3 by mutation, at a raised `max_attempts`.** At defaults the test
  cannot fail — see trap 9.
- **Prove nothing regressed** by running the existing ladder suite with no
  promotion persona configured.
