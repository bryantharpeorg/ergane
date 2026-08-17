# Implementation Plan: Composable Verification

> **Re-verified 2026-08-16 against `851e0bf`, and most anchors below had
> drifted.** Four were resolved by name and corrected in place:
> `VerificationConfig` is at `factory/verify/models.py:555` with its five caps
> from `:562`; `_verify` is at `factory/workgraph/workflow.py:1628` in a
> 2,557-line file; `_start_epic` is at `factory/cli/nouns/build.py:409`;
> `next_action` (`factory/verify/ladder.py:63`) and `render_pr_body`
> (`factory/mergequeue/messages.py:52`) both held exactly.
>
> The rest were **not** individually re-resolved, and that is deliberate: this
> plan's own **T001 is an operator preflight that re-verifies every `file:line`
> anchor**, and it exists because this spec was drafted on 2026-08-10 against a
> tree that has since taken hundreds of commits. **Do T001 first and do it
> properly.** Trust the code over this table wherever they disagree, and say so
> in your handoff rather than hunting.

**Branch**: `023-composable-verification` | **Date**: 2026-08-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/023-composable-verification/spec.md`

## Summary

The composition this spec offers already exists as disconnected data. The
ladder is a pure function over `VerificationConfig` — five caps that default
in code and are set by no one. The gate map is already an ordered,
operator-declared command list whose order the parser deliberately preserves.
The 002 contract reserved arbitrary gate names for `version: 2` in writing.
And `escalation_timeout_s` is plumbed end-to-end through the workflow and the
escalation row, waiting for something to feed it a non-default value. This
spec connects the manifest to all of it: schema v2 parsing (US1), a
dispatch-time pin into `EpicInput` (US2), a `_verify` that walks the declared
order (US3), and a verdict that names the loop that granted it (US4).

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so every fact an implementer node needs is inlined,
each verified against the tree on 2026-08-10 — and T001 re-verifies them
against the tree that actually hosts the work.

## Technical Context

**Language/Version**: Python 3.11+; the worker host runs 3.13.

**Primary Dependencies**: none added. `pyyaml` and `temporalio` are already
on the roster.

**Verified reuse inventory** (`file:line` as of 2026-08-10; T001 re-checks):

*The parser (US1's whole surface)*

- `factory/verify/factory_yaml.py` — `MANIFEST_NAME` `:55`, `KNOWN_GATES`
  `:59` (the v1 freeze this spec lifts), `_TOP_LEVEL_KEYS` `:61`,
  `_SUPPORTED_VERSION = 1` `:63`, `parse_factory_config` `:85`.
- The type-identity guard to reuse everywhere: `_read_version` `:162` —
  `type(version) is not int`, with the comment explaining why (`version:
  true` would pass a naive `== 1`). The roadmap's bound check
  (`factory/roadmap/workflow.py:546-553`, per 021) is the same idiom.
- Gate-name refusal to relax: `:214-222`. Declaration order preserved on
  purpose: `:232-233` — v2's `verify:` list extends that philosophy to steps.
- `_read_landing_branch` `:293-311` — the pattern for every v2 addition:
  optional, absent-means-today, declared-means-declared, refused by name.
- `config_error_result` `:352` — how a refusal becomes gate data, never an
  exception.
- `FactoryConfig` — `factory/verify/models.py:555` (`VerificationConfig`; the five caps start at `:562`). Frozen dataclass; grows
  `ladder` and `verify_order` fields with defaults equal to today.

*The ladder and its caps*

- `VerificationConfig` — `factory/verify/models.py:440-451`: `max_attempts=3`,
  `max_judge_retries=2`, `debugger_cycles=1`, `gate_timeout_s=600`,
  `escalation_timeout_s=3600`. The manifest's `ladder:` sets four of the
  five; `gate_timeout_s` stays out (per-gate `timeouts:` already exists).
- `next_action` — `factory/verify/ladder.py:63`: pure over
  `(history, config, escalations)`. **US2 changes what `config` contains,
  never this function.**
- Default-derived module constants that must stay untouched:
  `factory/verify/judge.py:64` and `factory/verify/gates.py:58` both
  construct `VerificationConfig()` for defaults. They are defaults, not the
  epic's config; leave them.

*The dispatch pin (US2)*

- `EpicInput` — `factory/workgraph/workflow.py:394-418`; `config` field at
  `:409`, docstring already says "passed in rather than read so an
  operator's retry policy is a property of the epic they started."
  `WorkGraph.target_repo` — `factory/workgraph/models.py:190` — is how the
  CLI knows which repo's manifest to read.
- CLI dispatch: `_start_epic` — `factory/cli/nouns/build.py:409` (`_start_epic`);
  `EpicInput(graph, proxy_url, max_concurrent_nodes)` built at `:320-324`
  with `config` defaulting. `_run_preflight(graph)` at `:303` is where the
  manifest read joins; a `ConfigError` there already becomes `OperatorError`.
- Roadmap dispatch: child `EpicInput` at
  `factory/roadmap/workflow.py:1107-1114`, passing `config=request.config` —
  i.e., frozen at roadmap start today. FR-006 replaces that field's source
  with a per-dispatch activity read.
- Roadmap park discipline: the parked-findings path from 009/021 is the
  home for a malformed manifest at dispatch time — park the spec, never
  fail the run.
- Escalation deadline plumbing, already live: workflow passes
  `config.escalation_timeout_s` at `factory/workgraph/workflow.py:1854`,
  `:1869`, `:2423`, `:2432`; the node-path row computes `expires_at` from
  `request.timeout_s` at `factory/activities/notify_activities.py:369`.
  **The knob works; nothing sets it.** The roadmap-failure path at `:549`
  uses the module constant — correct, out of scope, no manifest exists in
  that context.

*The verify chain (US3)*

- `_verify` — `factory/workgraph/workflow.py:1628` (`_verify`): `run_gates` at
  `:1654`, `check_output` at `:1662`, `judge_required` gate at `:1676`,
  `read_worktree_diff` at `:1677`, `_judge` at `:1684`, `compose_result` at
  `:1688`, `record_verification` at `:1702`.
- `judge_required` — `factory/verify/models.py:555`. It reads gate results
  *and* the output check; the parser's judge-after-both rule (FR-003) is
  what guarantees both exist whenever the judge's turn comes.
- `_judge` mints its own key (`:1749-1766`) — a judge-less declared loop
  must never reach that mint (SC-005).
- The worktree manifest read that stays: `RunGatesInput.factory_yaml_path`
  defaults to the worktree's own manifest
  (`factory/activities/verify_activities.py:212, :220`), and the workflow
  passes only `worktree_path` (`:1656`). Gate commands are
  worktree-declared by design — the merge-group CI re-running the real
  required checks is their tamper backstop. The loop has no such backstop,
  which is the whole reason FR-007 pins it at dispatch.

*Provenance (US4)*

- `record_verification` — `factory/activities/verify_activities.py:459`;
  the store behind it is `factory/verify/store.py` (additive column;
  existing rows read as pre-023, never backfilled).
- PR body assembly: `render_pr_body` — `factory/mergequeue/messages.py:52`.
  The evidence section it already renders is where the loop line joins.

*Onboarding correspondence (FR-004)*

- `factory/mergequeue/onboard.py:51-100` — `gate_check:<gate>` /
  `unknown_check:<name>` computed from `FactoryConfig.gates` keys and the
  queue's required checks, both as opaque strings. Verified name-generic:
  arbitrary gate names flow through unchanged. The v1 rationale for fixed
  names ("map 1:1") is satisfied by *matching* names, not by *those three*
  names.

**Storage**: one additive column set on the verification store (US4). No new
database.

**Testing**: `pytest`; `WorkflowEnvironment.start_time_skipping()` for
interpreter behaviour. Suites that exist and grow here:
`tests/test_factory_yaml.py` (US1), `tests/test_ladder.py` (unchanged —
prove it), `tests/test_verify_activities.py`, `tests/test_worker.py` (its
AST registration check must learn US2's new activity),
`tests/test_interpreter.py` (US3), `tests/test_verify_store.py` (US4).

**Project Type**: single Python package; no new module directory.

## Constitution Check

- **I (build order)**: four slices, each independently landable; US1 alone
  is a working parser change with zero behavioural effect.
- **II (test-first)**: every task pairs a failing test with implementation;
  SC-001's "no existing test modified" is itself asserted by running the
  untouched suite.
- **III (dependencies)**: none added.
- **IV (determinism at the core)**: the declared order is data interpreted
  by the same deterministic `_verify`; the manifest read at roadmap dispatch
  is an activity whose result enters history; no LLM touches routing.
- **V (credentials/attribution)**: a judge-less loop mints no judge key —
  attribution gets *more* honest, not less. No credential surface changes.
- **VI (salvage)**: untouched; expiry-defaults-to-kill is explicitly floor
  (spec § Assumptions).
- **VII (personas)**: the manifest declares judge *presence*, never judge
  identity; personas.yaml remains the only place a model is named.
- **Governance**: the environment-constraints wording amendment
  ("test/lint/typecheck commands" → gates and loop composition) is claimed
  at landing with its decision-log entry, per spec § Assumptions.

## Approach by story

### US1 — the parser (FR-001…FR-004)

`_SUPPORTED_VERSION` becomes a pair; every v2-only key is refused under v1
exactly as today (they are simply not in v1's `_TOP_LEVEL_KEYS`). New
readers follow `_read_landing_branch`'s shape: optional, absent-means-today,
type-identity-checked, refused with a stable rule slug.

`FactoryConfig` grows two fields with defaults equal to current behaviour:
`ladder: VerificationConfig = VerificationConfig()` (reuse the existing
dataclass — one vocabulary, spec § Assumptions) and
`verify_order: tuple[str, ...] = ("gates", "diff_check", "judge")`. The
default tuple *includes* `judge` because today's loop includes it — a v2
manifest excludes the judge by declaring a list without it.

Floor rules are parse rules, all with named slugs: `verify` non-empty,
duplicate-free, drawn from the three step names; `gates` and `diff_check`
mandatory; `judge` after both when present; ladder ints non-boolean and
within ceilings (`max_attempts` 1–10, `max_judge_retries` 0–10,
`debugger_cycles` 0–3, `escalation_timeout_s` 60–86400); gate names in v2
arbitrary but not a reserved step name (`gates`, `diff_check`, `judge`,
`config` — the last because `config` is the synthetic gate name
`config_error_result` already emits).

### US2 — the dispatch pin (FR-005…FR-007, FR-009, FR-011)

Two dispatch sites, one rule: the loop is read from the operator clone's
committed manifest at dispatch and pinned into `EpicInput`.

- **CLI**: `_start_epic` reads `Path(graph.target_repo) / MANIFEST_NAME` via
  `load_factory_config` during preflight, maps a `FactoryConfigError` to the
  existing `OperatorError` path with the rule named, and passes
  `config=parsed.ladder` (plus the order, riding a new `EpicInput` field
  with today's default) into the workflow.
- **Roadmap**: a new activity (suggested name `read_loop_config`) takes
  `target_repo`, returns the parsed ladder + order, and is called by
  `_dispatch` per child, replacing `config=request.config` as the source. A
  parse failure parks that spec with the error recorded, through the
  existing parked-findings discipline — the roadmap run itself never fails
  on one repo's broken manifest. Register the activity in
  `factory/worker.py` and extend `tests/test_worker.py`'s AST check in the
  same diff — an unregistered activity is a silent stall, not an error.

Tamper (FR-007) needs no new enforcement — the workflow already never reads
a manifest for loop decisions; the story's obligation is the *test* proving
a worktree rewrite of `ladder:` changes nothing, so the property survives
future refactors. FR-009 likewise: the plumbing exists; the test asserts
row/timer parity under a non-default deadline, which no current test can
distinguish from the constant.

### US3 — the walked order (FR-008)

`_verify` becomes a loop over `request.verify_order` instead of three
hardcoded awaits. Semantics, decided here so stories do not re-litigate:

- **Fail-fast between steps.** A failing step ends the phase; later steps do
  not run. This is what makes `[diff_check, gates, judge]` worth declaring
  (SC-002) — and it changes evidence shape, so the next point is the one
  that matters.
- **A short-circuited phase can never compose to PASS.** `compose_result`
  today assumes gates always ran; a diff-check-first failure reaches it with
  zero gate results. The truth table must read "step failed, phase FAIL"
  from the failing step's own result — never pass-by-default through an
  empty gate list. This gets its own test before the loop is written.
- **The judge's guard survives composition.** Where `judge` appears, it
  still runs only if `judge_required(gate_results, output, criteria)` says
  scoring can matter — the parser guarantees both inputs exist by then. A
  loop that excludes `judge` skips the guard, the diff read, and the key
  mint entirely (SC-005).
- **Record what ran.** The result carries which steps executed and why the
  judge did not (excluded-by-loop vs skipped-by-guard) — FR-008's
  distinction, and US4's raw material.
- **v1 and default-v2 paths execute today's exact sequence** — same
  activities, same arguments, same order, asserted against the existing
  interpreter suite unmodified.

### US4 — the named verdict (FR-010)

Digest = SHA-256 over a canonical rendering of (schema version, gate names
in declared order, verify order, ladder caps, judge presence). Rides
`VerificationResult` into `record_verification` (additive store column;
pre-023 rows read as absent, never backfilled) and one line in
`render_pr_body`'s evidence section. The unconfigured default digests like
any other loop — "default" is a described state (SC-006), so the digest for
a v1 repo is a constant the tests can name.

## Traps

0. **This repo's own manifest is a landmine in every diff — 020-US1 died
   four times proving it.** The config gate parses the node's `factory.yaml`
   with the *worker's installed parser*. Until this spec lands and the
   worker restarts, that parser rejects `version: 2`, `ladder:` and
   `verify:` as unknown — so a story diff that touches Ergane's committed
   `factory.yaml` in any way is rejected at `CONFIG_ERROR` in 0.0s before
   its own gates run. FR-011 makes this binding: the manifest stays
   byte-identical in every story. Fixture manifests under `tests/` are fine;
   the one at the repo root is not yours. Flipping it to v2 is operator
   work, after landing, after a worker restart.

1. **`isinstance(True, int)` is `True`.** Every ladder integer uses the
   type-identity idiom from `_read_version` (`:162`) — `type(x) is not
   int` — or `ladder: {max_attempts: true}` becomes a budget of 1. The
   repo has now paid for this class three times (version check, roadmap
   bounds, 021 trap 5); do not make it four.

2. **Do not "unify" the two manifest reads.** Gates reading the *worktree*
   manifest (`RunGatesInput.factory_yaml_path` defaulting inside the
   activity) is a design decision with a CI backstop, and 020's
   CONFIG_ERROR protection depends on that read existing. The dispatch pin
   is a *second* read with a different trust model, not a replacement.
   A refactor that routes gate commands through the pinned config removes
   the config-gate tamper check without noticing.

3. **`EpicInput` and `VerificationConfig` cross Temporal's payload
   boundary.** Add fields with defaults only; never rename or retype
   existing ones. A running epic replays its history with old payloads, and
   a field whose default does not reproduce today's behaviour changes the
   past. The `verify_order` default must therefore be today's order
   *including* `judge`.

4. **An empty gate-result list must never read as "no gates failed".**
   `factory_yaml.py`'s own docstring names the failure mode: a verifier that
   finds no gates sees nothing fail and passes a repo it never tested.
   Fail-fast (US3) creates the first code path where `compose_result` can
   legitimately receive zero gate results. Write the
   short-circuit-composes-to-FAIL test before touching `_verify`, and treat
   any green run of it against unmodified `compose_result` as a defect in
   the test (tasks preamble rule).

5. **The new activity is a silent stall until registered.** Worker
   registration is by name; a workflow calling an unregistered activity
   waits forever with no error. `read_loop_config` lands in
   `factory/worker.py`'s ACTIVITIES and in `tests/test_worker.py`'s AST
   check in the same diff as its first caller.

6. **The roadmap must park, not die.** One repo's malformed manifest at
   dispatch time is that spec's blocker. Route it through the existing
   parked-findings path with the parse error recorded; a roadmap run that
   fails on it re-creates 021's silent-scheduler class with a manifest as
   the trigger.

7. **FR-009's test must use a non-default deadline.** Under 3600s the
   config-fed path and the constant-fed path are indistinguishable — a
   parity test at the default proves nothing. Configure 7200, assert both
   the workflow timer and the row's `expires_at` moved together. The
   roadmap-failure escalation (`notify_activities.py:549`) legitimately
   uses the constant; do not "fix" it.

8. **Judge exclusion is not judge unavailability.** `compose_result`
   already has a judge-absent path (`judge_unavailable` — an outage that
   does not block a PASS, flagged in the row). A loop that *excludes* the
   judge is a third state and must not reuse that flag: unavailability is
   an incident, exclusion is a declaration. Conflating them poisons the
   doctor's ledger and US4's summary both.

## Complexity Tracking

| Risk | Why it is real | Mitigation |
|---|---|---|
| v1 behaviour drifts under the refactor | Every current repo is v1; SC-001 is the contract | No existing test modified; v1 parse asserted semantically identical; default `verify_order` replays today's sequence |
| Short-circuit passes by default | First-ever path where compose sees zero gate results | Trap 4's test written first, against unmodified `compose_result` |
| Self-target chicken-and-egg | Worker's parser rejects v2 until restart | Trap 0 / FR-011: root manifest byte-identical in every diff |
| Replay divergence on running epics | New `EpicInput` field crosses payload boundary | Trap 3: additive with today's default; never rename |
| Roadmap killed by one bad manifest | Per-dispatch read adds a failure path to `_dispatch` | Trap 6: park the spec, record the error, run continues |
| Silent stall on the new activity | Registration is by name, failure mode is a hang | Trap 5: register + AST test in the same diff |
| Deadline parity test proves nothing | Default value hides which source fed the row | Trap 7: assert under 7200, not 3600 |
| Two manifest reads confuse future readers | Worktree read (gates) vs pinned read (loop) look redundant | Trap 2 + comments at both sites naming the asymmetry and its backstop |

## Instrument traps carried forward from 2026-08-16

**Purge `__pycache__` between mutants**, or run under `PYTHONDONTWRITEBYTECODE=1`.
CPython validates a cached `.pyc` on `(mtime-in-whole-seconds, size)` only, so
two same-size mutants written inside one wall-clock second make the second run
execute the *first* mutant's bytecode. It fails toward green and reproduces
stably, so nothing catches the eye.

**Quote `passed` and `skipped`, never the warning count** — a warm cache
suppresses compile-time warnings, so the count measures cache state rather than
your diff. Baseline skips are 44; a new skip is a hidden test you must declare.

**Measure exit codes without a pipe.** `cmd | head; echo $?` reports the pipe's
status, not the command's.

**A mutation can be indistinguishable from correct** when every test observes
the two states at a moment they coincide. This spec is unusually exposed: a
declared verify order of `[diff_check, gates, judge]` and the hardcoded order it
replaces produce the same outcome on any input where all three pass. US3-S2's
*reordered* list is the case that can tell them apart — make sure a mutation to
the walk actually dies there, and not merely because some unrelated assertion
noticed.

**The diff ceiling is 61,440 bytes and this epic has four stories touching the
verification core.** Measure through `size_refusal` from
`factory/verify/diffbounds.py`, importing `DIFF_INPUT_LIMIT` rather than quoting
it. If a story does not fit whole, **say where you would split it** — do not trim
checks. Six stories landed on 2026-08-16 on evidence the judge only partly saw,
one at 2.1x, and a seventh refused to fit and was split instead. The refusal was
the right answer.
