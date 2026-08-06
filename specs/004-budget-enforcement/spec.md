# Feature Specification: Budget Enforcement (DEFERRED)

**Feature Branch**: `004-budget-enforcement`

**Created**: 2026-07-24

**Status**: **Deferred** — designed during the 2026-07-24 interview (D-013…D-016), then
parked by D-021: the operator wants spend *tracked*, not *enforced*, for now. This spec
preserves the settled enforcement design so it can be picked up without re-litigating.
It layers on top of `001-usage-tracking` (which owns keys, polling, and the ledger) and
is unscheduled — it does not participate in the build order until reactivated.

**Input**: Per-node budget caps on the LiteLLM virtual keys minted by component 1,
breach policy (soft-warn / hard-kill / escalate), salvage-always, and the Telegram
escalation flow with bump/reroute/kill choices.

## Design (settled 2026-07-24, preserved verbatim in intent)

### Caps

- Component 1's per-node key gains `max_budget` at issuance: the node's explicit
  override when present, else the persona's budget default from the registry (defaults
  captured at interview: implementer $5, debugger $3, architect $2, researcher $1,
  judge $0.50; verifier keyless).
- All budgets denominated in USD uniformly; local models require synthetic
  `input_cost_per_token` / `output_cost_per_token` registered in the proxy or their
  spend is $0 and caps never trip (operator setup step; optional under tracking-only,
  mandatory here).
- Node budgets never reset mid-node (no `budget_duration`); TTL remains expiry only.

### Breach detection

- The proxy enforces the hard floor itself: past `max_budget`, requests fail with
  HTTP 400 carrying an `ExceededTokenBudget`-style detail.
- Termination classification (component 1's enum) gains **BUDGET_BREACH**, detected
  from output markers (`ExceededTokenBudget`, `budget_exceeded`, `ExceededBudget`)
  and/or an exhausted usage snapshot, with precedence: clean exit → COMPLETED;
  timeout → TIMEOUT; breach evidence → BUDGET_BREACH; kill → KILLED; else AGENT_ERROR.
  (Breach beats KILLED so self-inflicted stops aren't misfiled.)

### Policy (per persona)

- **Soft-warn** (all personas): at ≥80% of budget, exactly one warning per node via
  the notifier; node continues. Reuses component 1's heartbeat polling — no proxy-side
  alerting config.
- **Hard stop**: on breach, SIGTERM with 30s grace then SIGKILL, and **salvage
  always** — worktree committed to the node branch before any cleanup (no work lost).
- **`hard-kill` personas** (verifier, judge, researcher): node fails, downstream stays
  locked, notification only.
- **`escalate` personas** (implementer, debugger, architect): Telegram inline buttons
  **[Bump +50% & resume] [Reroute cheaper] [Kill]**, each mapped to an orchestration
  signal; bump raises `max_budget` on the same key (`/key/update`) and resumes in the
  same worktree; 1 hour of silence → kill (already salvaged).

### Registry additions

- `personas.yaml` regains `budget_usd` and `breach_policy` attributes per persona
  (escalate: implementer/debugger/architect; hard-kill: verifier/judge/researcher).

## Open questions (carried from the interrupted clarify session)

Recorded here so reactivation starts from them rather than rediscovering:

1. **Reroute-cheaper semantics**: restart same persona on its fallback model (fresh
   key, same worktree)? Or operator picks a model at escalation time? (Leaning:
   fallback model, same worktree.)
2. **Key-issuance failure at dispatch** (proxy unreachable): bounded retry then fail
   node + escalate? Fail fast? (Leaning: platform retry with backoff, then fail node.)
3. **TTL default** for the key backstop. (Leaning: 24h.)
4. **Bump after TTL expiry**: bump fails on an expired key — re-present escalation
   with kill/reroute only.

## Reactivation checklist

- [ ] Operator confirms budgets should be enforced (supersede D-021 with a new
      decision entry).
- [ ] Synthetic pricing registered for all local models in the proxy `model_list`.
- [ ] Constitution: restore enforcement language to Principle V; slot this spec into
      the build order.
- [ ] Resolve the open questions above via `/speckit-clarify` on this spec.
- [ ] `001-usage-tracking` implemented (this spec extends its key lifecycle, polling,
      classification, and ledger).
- [ ] Notifier (Telegram inline buttons → signals, built in component 2) available for
      the escalation flow.
