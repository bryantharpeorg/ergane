# Implementation Plan: away mode has one owner and an explicit policy

## Current seams and official contract

- The `Turning it on and off` and `The mechanism` sections in `.claude/skills/away-mode/SKILL.md` store lifecycle in one session and hardcode `ScheduleWakeup`, `TaskStop`, and `PushNotification` tool names.
- Spec 158 makes `floor-status` and escalation inspection read-only; ticks consume those surfaces before actions.
- Existing typed CLI acts include build/roadmap signals, attestation, answers, and findings commands. Away mode wraps them with explicit policy; it does not call workflow internals or implement dispatch selection.
- Official scheduled-task source: https://learn.chatgpt.com/docs/automations . The desktop app can run project-scoped local tasks; Codex CLI and the IDE extension do not provide the Scheduled management interface. Local tasks require the machine and app to remain running.

## Proposed interfaces

Add a small operator-side package such as `factory/operator/away.py` and a noun
surface `ergane away start|status|tick|stop`. The store lives under the resolved
operator state location, separate from Temporal and evidence stores. Models:
`AwayPolicy`, `AwayOwner`, `AwayObservation`, `ActionIntent`, `ActionResult`,
`NotificationIntent`, and `AwayRunState`.

Start persists explicit scope. Tick claims a short transaction, reads facts,
releases observation state, journals one proposed action at a time, then calls an
injected typed executor. Stop writes durable state before asking an injected
binding to cancel. Bindings are documented/fixture-tested in the canonical away
skill; the core package contains no client tool-name switch.

## Story slices

### US1 — Policy and owner

Implement closed allow/prohibit sets, target identity, deadline validation, and
one-owner concurrency. State includes a monotonic journal sequence and redacted
binding metadata. Taking over is a separate future operator verb, not implicit
start behavior.

### US2 — Observation and generic action journal

Use typed read surfaces and one injected fake-action seam. Persist intent before
action and reconcile by idempotency key. This story proves ordering, replay, and
deny behavior without absorbing five action adapters or notification policy.

### US5 — Typed actions and notifications

Map each allowed kind to an existing typed operator command, exact current
evidence, idempotency identity, and forbidden states. A builder-question answer
is available only for an exact fact in current authoritative spec/decision
evidence; ambiguity or a choice abstains. Add notification intents/deduplication
on top of the generic journal and keep unchanged ticks quiet.

### US3 — Client bindings

Rewrite the canonical skill around capability detection. Codex desktop renders
one project task prompt; CLI/IDE report unavailable and show `ergane away tick`.
Claude renders its available wakeup/notification binding. Fixtures prove only
`definition rendered`; separately authorized live evidence advances through
`binding created` and `verified fired/notified`. Production Python never imports
a fabricated scheduler API, and activation stays held without the final state.

### US4 — Stop and recovery

Make terminal state durable before cancellation. Recover in-doubt action and
notification intents after any crash. Two simultaneous ticks contend only for a
short transaction; the persisted owner outlives it. A failed binding cancellation
is an observable cleanup error, not permission to act again.

## Traps

1. **A file lock is not durable ownership.** Owner state must remain after the transaction closes.
2. **Explicit enablement is the authority.** Installing the skill does not enable away mode.
3. **Allowlist, never inferred intent.** Omitted actions are denied even if the old skill performed them.
4. **Escalations belong to the operator.** Away mode may prepare evidence but never press a choice.
5. **Held means held.** No state flip or dependency override while unattended.
6. **Live factory code is imported.** Never edit it to unblock a running attempt.
7. **Temporal owns scheduling.** Away mode requests existing operations; it does not choose roadmap children.
8. **Intent precedes side effect.** The inverse loses the idempotency record at the crash boundary.
9. **Quiet is a requirement.** A heartbeat record does not imply a notification.
10. **Stop precedes cancellation.** Timer cancellation can fail; durable state must still deny future work.
11. **Clients expose different tools.** Capability absence is a supported result.
12. **Codex CLI cannot manage Scheduled.** Offer one tick; do not shell a private app API.
13. **Desktop local tasks need the machine and app.** State that prerequisite in the binding.
14. **No unattended memory writes.** Durable continuity lives in the away store and project records.
15. **Two clients can wake together.** Tick claim is short, idempotent, and quiet for the loser.
16. **A definition is not a wakeup.** Fixture rendering, binding creation, and observed firing/notification are separate states.
17. **Grounded is a closed rule.** An answer that requires interpretation, a tradeoff, or an escalation choice abstains.

## Verification

Use a temporary store, fixed clock, fake observers/actions/notifiers/bindings, and
time-skipping where applicable. Test every action and prohibition, every crash
point, simultaneous ticks, unavailable scheduling, and failed cancellation. Run
focused skill/operator tests and the declared full gate. No test may contact a
live scheduler, Temporal, forge, notifier, memory service, or operational store.
