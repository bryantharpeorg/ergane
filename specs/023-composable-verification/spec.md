---
state: ready
# Drafted 2026-08-10 from an operator conversation: the factory's durability,
# attribution and landing discipline are the product, but what happens *inside*
# a node's loop — which gates, in what order, whether a judge scores it, how
# many retries before a human is paged — should be each target repo's declared
# choice rather than the interpreter's hardcoded one. "Team" enters this system
# as "target repo": factory.yaml is already per-repo, already committed, already
# parsed by the worker's own installed parser. No new tenancy concept is needed
# or wanted.
#
# Numbered 023: 011–014 stay reserved for audit-triage epics, 015 doctor, 016
# delta, 017 peer channel, 018 agent home isolation, 019 operator CLI, 020
# landing attribution, 021 roadmap operability, 022 validate calibration.
depends_on_landed: [002-verification-gating, 005-workgraph-interpreter, 020-landing-attribution]
---

# Feature Specification: Composable Verification

**Feature Branch**: `023-composable-verification`

**Created**: 2026-08-10

**Status**: Draft. The mechanism this spec composes already exists as data in
three places that nothing connects: the ladder is a pure function over a
`VerificationConfig` whose five caps default in code and are set by nobody; the
gate list is already an ordered, operator-declared command map; and the 002
contract explicitly reserved arbitrary gate names for `version: 2`. This spec
is the `version: 2` that contract promised, plus the plumbing that lets a
committed manifest reach the running loop.

**Input**: One principle and two blocks.

**The principle.** The factory's fixed machinery — durable execution, per-node
attribution, worktree isolation, salvage, merge-queue landing — is the
platform, and no manifest may weaken it. What a target repo *may* declare is
the composition of its own verification loop: which named gates run, in what
order the verification steps execute, whether an LLM judge scores the diff,
and how tall the retry ladder stands before a human is paged. Teams author
composition, never code: every declarable step resolves to an activity the
worker already registers, every knob is typed and bounded, and every violation
is refused by name at parse time — `CONFIG_ERROR`, never pass-by-default.

**The two blocks.** Schema v2 of `factory.yaml` adds `ladder:` (the caps
`VerificationConfig` already models: attempts, judge rewrites, debugger
cycles, escalation deadline) and `verify:` (the ordered step list the
interpreter's `_verify` currently hardcodes as gates → diff check → judge).
It also lifts v1's fixed gate names — the merge-queue onboarding check that
motivated fixing them (`gate_check:<gate>` / `unknown_check:<name>`) is
already name-generic, so the 1:1 correspondence survives any spelling.

**What makes this worth a version bump rather than five knobs.** A verdict is
only meaningful relative to the pipeline that produced it. Once loops vary by
repo, a bare PASS stops being self-describing — so the resolved loop
configuration must ride into the verification row and the PR's evidence, and
"verified" becomes "verified, by this declared definition." That is an
auditability gain, not a cost: today the definition is implicit in whatever
the interpreter hardcoded on the day the epic ran.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The manifest can declare the loop (Priority: P1)

As a target-repo owner, I commit a `factory.yaml` with `version: 2` that names
my own gates in my own order, declares my retry ladder's height, and states
whether and where a judge scores my diffs — and a manifest that declares any
of it badly is refused with the exact rule named, before anything runs.

This story is the parser and only the parser: `parse_factory_config` learns
`version: 2` with a `ladder:` block, a `verify:` list, and arbitrary gate
names, while `version: 1` continues to parse to byte-identical semantics.
Every new rule refuses loudly in the existing `FactoryConfigError` grammar —
stable rule slug, offending value `repr`-rendered, source file named.

**Why this priority**: every other story consumes the parsed shape. Nothing
downstream exists until the manifest can say it.

**Independent Test**: a v2 manifest exercising every new key parses to a typed
config; each violation — unknown step, duplicated step, judge before gates,
missing diff check, boolean where an integer belongs, a cap beyond its
ceiling — raises `FactoryConfigError` with its own named rule; the entire
existing v1 suite passes unmodified.

**Acceptance Scenarios**:

1. **Given** a `version: 2` manifest declaring gates `unit` and `contract`, a
   `verify:` order of `[diff_check, gates, judge]`, and a `ladder:` of
   `max_attempts: 2`, **When** it is parsed, **Then** the returned config
   carries exactly those gates in that order, that step order, and that cap,
   with every undeclared ladder field at today's default.
2. **Given** a `version: 1` manifest from any repo the factory builds today,
   **When** it is parsed, **Then** the result is semantically identical to
   what today's parser returns — same gates, same defaults, same rejections —
   and no existing test changes to stay green.
3. **Given** a v2 manifest whose `verify:` omits `diff_check`, or omits
   `gates`, or places `judge` before `gates` or before `diff_check`, **When**
   it is parsed, **Then** it is refused with a named rule stating the floor:
   the diff check is not optional, and a judge only ever scores work that is
   already green.
4. **Given** a v2 manifest with `ladder: {max_attempts: true}` or
   `{debugger_cycles: "1"}`, **When** it is parsed, **Then** it is refused
   naming the field and the `repr` of the value — `isinstance(True, int)` is
   `True` in Python, and the version check at `_read_version` already models
   the type-identity guard this must reuse.
5. **Given** a v2 manifest declaring a cap beyond its platform ceiling (an
   attempt budget above 10, an escalation deadline above 24 hours), **When**
   it is parsed, **Then** it is refused with the ceiling named — a manifest
   must not be able to declare unbounded spend or an escalation that never
   expires.
6. **Given** a v1 manifest that declares `ladder:` or `verify:`, **When** it
   is parsed, **Then** it is refused as an unknown key exactly as today —
   the new vocabulary exists only behind the version bump.

---

### User Story 2 - The declared ladder reaches the running epic (Priority: P1)

As the factory operator, an epic dispatched against a repo whose manifest
declares `max_attempts: 2` escalates after two failed attempts, and nothing an
agent writes into its own worktree can buy it a third.

Today `VerificationConfig` rides `EpicInput.config` and defaults at every
construction site: `ergane build start` builds `EpicInput` without one, and
the roadmap's `_dispatch` passes whatever its own input carried at roadmap
start. This story reads the *operator clone's committed manifest* at dispatch,
builds the config from it, and pins it into the epic's input — where Temporal
records it in history and it becomes immutable for the run, which is exactly
the existing rule: manifest edits reach only the next epic.

The pin is also the tamper boundary, and the asymmetry with gates is
deliberate and must be preserved. Gate *commands* are read from the node
worktree's manifest by design — a tampered command is caught by the
merge-group CI re-running the real required checks. The *loop* has no such
backstop: nothing downstream re-checks how many attempts a node granted
itself. So loop configuration is read once, at dispatch, from the operator's
clone, and a node worktree that rewrites its own `ladder:` changes nothing.

**Why this priority**: a parsed shape nothing consumes is documentation. This
story is the difference between the two.

**Independent Test**: an epic dispatched against a v2 manifest carries the
declared caps in its `EpicInput`; a scheduled epic dispatched by the roadmap
carries the same; a node worktree that edits its manifest's `ladder:`
mid-attempt still escalates on the pinned budget; the escalation row's
advertised deadline equals the configured one.

**Acceptance Scenarios**:

1. **Given** a target repo whose manifest declares `max_attempts: 2`, **When**
   the operator runs `ergane build start`, **Then** the started epic's input
   carries a config with `max_attempts=2`, and a node that fails twice
   proceeds to the debugger rung rather than a third ordinary attempt.
2. **Given** a target repo with a v1 manifest or no `ladder:` block, **When**
   an epic is dispatched, **Then** the epic runs under today's defaults
   exactly — absent means today, on every field, always.
3. **Given** a roadmap dispatching a spec, **When** `_dispatch` starts the
   child epic, **Then** the child's config was read from the manifest at that
   dispatch — not frozen at roadmap start — so a manifest edit reaches the
   next scheduled epic even under a roadmap that idles for a week.
4. **Given** a node whose agent rewrites the worktree's `factory.yaml` to
   declare `max_attempts: 99`, **When** its attempt fails, **Then** the ladder
   decides on the pinned dispatch-time config and the rewrite has no effect on
   any loop decision.
5. **Given** a manifest declaring `escalation_timeout_s: 7200`, **When** a
   node escalates, **Then** the workflow waits 7200 seconds *and* the stored
   escalation row advertises an `expires_at` 7200 seconds after send — the
   timer and the evidence must not disagree about when the deadline is.
6. **Given** a target repo whose committed manifest is malformed, **When** the
   operator runs `ergane build start`, **Then** the dispatch is refused at
   preflight with the parse error named — an epic that would `CONFIG_ERROR`
   at its first node's first gate must not start.

---

### User Story 3 - The verify list drives the loop (Priority: P1)

As a target-repo owner, the order I declared is the order that runs: a repo
that puts `diff_check` before `gates` fails a no-op diff in under a second
instead of after a full test run, and a repo that declares no `judge` step
runs gates-and-diff-check verification with no LLM in the loop at all.

`_verify` currently hardcodes gates → output check → judge-if-it-can-matter.
The hardcoded order is not even cheapest-first — the output check costs a
subsecond git read while gates cost up to two hours, so 002's own
cheapest-first invariant argues for letting a repo reorder them. The judge's
guard survives composition: where `judge` appears in the declared order, it
still runs only when `judge_required` says a scoring can matter, and it still
reads both the gate results and the output check regardless of the order the
two ran in — which is why the parser (US1) already refused any order that
places `judge` ahead of either.

**Why this priority**: this is half of what was asked for, and the half that
makes the composition visible in behaviour rather than in a parsed dataclass.

**Independent Test**: under a declared `[diff_check, gates, judge]` order the
output check executes before any gate command; under a declared judge-less
list the judge activity is never invoked and the verdict composes with no
judge evidence; under a v1 manifest the executed sequence is byte-for-byte
today's.

**Acceptance Scenarios**:

1. **Given** a repo declaring `verify: [diff_check, gates, judge]`, **When** a
   node's attempt produces an empty diff, **Then** the attempt's verification
   fails on the output check before any gate command has run.
2. **Given** a repo declaring `verify: [gates, diff_check]`, **When** a node's
   attempt passes both steps, **Then** the verdict is a PASS composed with no
   judge verdict and no judge key was ever minted — and the recorded result
   distinguishes "judge excluded by the declared loop" from "judge skipped
   because it could not matter."
3. **Given** a v1 manifest or a v2 manifest with no `verify:` key, **When** a
   node verifies, **Then** the executed order is today's — gates, output
   check, then judge only if it can still matter.
4. **Given** any declared order containing `judge`, **When** the prior steps
   leave nothing for a judge to usefully score, **Then** `judge_required`
   still short-circuits it exactly as today — composition changes where the
   judge sits, never the guard that decides whether scoring is worth a
   completion.
5. **Given** a declared order, **When** verification runs, **Then** every
   step's result reaches `compose_result` with the same truth-table semantics
   as today — reordering affects cost and sequence, never the verdict a given
   set of step results composes to.

---

### User Story 4 - The verdict names its definition of verified (Priority: P2)

As the factory operator, every verification row and every PR the factory
opens states which loop produced its verdict — so that two repos' PASSes,
granted under different declared loops, are never mistaken for the same claim.

Once the loop varies by repo, provenance must say which loop ran. The
resolved configuration — schema version, gate names, declared order, ladder
caps, judge included or not — is digested and recorded with each verification
result, and the PR body's evidence section names it alongside the gate
results it already carries.

**Why this priority**: real, and the reason the composition is safe to offer
at all — but nothing about it blocks US1–US3, and until two repos actually
declare different loops the digest describes a population of one.

**Independent Test**: a verification row records the resolved loop digest and
summary; the PR body renders it; two epics run under different declared loops
record different digests; a v1 repo's rows record the default loop
explicitly rather than nothing.

**Acceptance Scenarios**:

1. **Given** a node verified under any loop, **When** its result is recorded,
   **Then** the row carries a stable digest of the resolved loop
   configuration and a human-readable summary of it.
2. **Given** a PASS landing as a PR, **When** the PR body is assembled,
   **Then** its evidence names the loop that granted the verdict — declared
   order, ladder caps, judge presence — in one line an operator can read.
3. **Given** a v1 repo, **When** its nodes verify, **Then** the recorded loop
   is the explicit default — "unconfigured" is a described state, never an
   absent field.
4. **Given** the same declared loop across two attempts, **When** both are
   recorded, **Then** their digests are equal — the digest identifies the
   loop, not the attempt.

### Edge Cases

- A v2 manifest that declares `verify:` but no `judge` step *and* a `ladder:`
  with `max_judge_retries` — the knob is coherent (a judge could be added
  back) but currently idle; parse it, keep it, and let the summary in US4
  show a judge-less loop so nobody wonders why rewrites never happen.
- A manifest edited between an epic's dispatch and a node's retry: the retry
  runs under the pinned config, because the pin is per-epic, not per-attempt.
  Only the next epic sees the edit.
- The roadmap dispatching against a repo whose manifest went malformed since
  the last pass: the dispatch must fail loudly for *that spec* and park it,
  not kill the roadmap — a broken manifest is a spec-level blocker, not a
  scheduler defect.
- Two gates declared with the same name is impossible (YAML mapping), but a
  gate named `judge`, `diff_check`, or `gates` must be refused — step names
  and gate names share a sentence in the manifest, and a gate literally named
  `judge` would make every error message about it unreadable.
- `escalation_timeout_s` interacts with the operator-channel contract: the
  expiry default (kill, after salvage) is constitution VI and stays invariant;
  only the deadline's length is the repo's to declare, within its ceiling.
- A `verify:` list of `[gates]` alone is refused (diff check is the floor),
  but `[diff_check, gates]` is legal — the minimum loop is "it did work, and
  the work is green."

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `parse_factory_config` MUST accept `version: 2` manifests
  carrying optional `ladder:` and `verify:` blocks and arbitrary non-empty
  gate names, and MUST continue to parse `version: 1` manifests to semantics
  identical to today's, with `ladder:` and `verify:` refused as unknown keys
  under v1.
- **FR-002**: The `ladder:` block MUST accept exactly the fields
  `max_attempts`, `max_judge_retries`, `debugger_cycles`, and
  `escalation_timeout_s`, each type-identity-checked as a non-boolean integer
  within platform ceilings (`max_attempts` 1–10, `max_judge_retries` 0–10,
  `debugger_cycles` 0–3, `escalation_timeout_s` 60–86400). Unknown ladder
  keys and out-of-range values MUST be refused with a named rule. Absent
  fields MUST default to today's `VerificationConfig` values.
- **FR-003**: The `verify:` list MUST be a non-empty, duplicate-free ordered
  list drawn from exactly `gates`, `diff_check`, `judge`, in which `gates`
  and `diff_check` are mandatory and `judge` is optional but MUST follow both
  when present. Absent `verify:`, a v2 manifest MUST default to today's
  order. Violations MUST be refused with a named rule.
- **FR-004**: In v2, gate names MUST be arbitrary non-empty strings other
  than the reserved step names (`gates`, `diff_check`, `judge`, `config`),
  and the merge-queue onboarding correspondence (`gate_check:<gate>` /
  `unknown_check:<name>`) MUST hold for the declared names unchanged.
- **FR-005**: `ergane build start` MUST read and parse the target repo's
  committed manifest at dispatch, build the epic's `VerificationConfig` and
  declared order from it, and pin both into `EpicInput` before the workflow
  starts. A manifest that fails to parse MUST refuse the dispatch at
  preflight with the parse error named.
- **FR-006**: The roadmap's `_dispatch` MUST obtain the same dispatch-time
  read for each child epic, through an activity, so that a manifest edit
  reaches the next scheduled epic regardless of how long the roadmap has been
  running. A malformed manifest at dispatch time MUST park that spec with the
  error recorded and MUST NOT fail the roadmap run.
- **FR-007**: Loop configuration MUST be immutable for a running epic and
  MUST be sourced only from the operator clone's committed manifest at
  dispatch. Content of any node worktree's manifest MUST have no effect on
  ladder decisions, verify order, or escalation deadlines — while gate
  *commands* continue to be read from the worktree manifest exactly as today.
- **FR-008**: The interpreter MUST execute verification steps in the declared
  order, MUST NOT invoke the judge (nor mint a judge key) when the declared
  loop excludes it, and MUST preserve `judge_required`'s short-circuit and
  `compose_result`'s verdict semantics for every legal order. The recorded
  result MUST distinguish a judge excluded by the loop from a judge skipped
  by `judge_required`.
- **FR-009**: A node's escalation MUST wait the configured deadline and the
  stored escalation row MUST advertise an `expires_at` computed from that
  same value — asserted under a non-default configuration, because under the
  default the two sources are indistinguishable.
- **FR-010**: Every verification result MUST record a stable digest and
  human-readable summary of the resolved loop configuration, with the
  unconfigured default recorded explicitly, and the PR body's evidence MUST
  name it.
- **FR-011**: Ergane's own committed `factory.yaml` MUST remain `version: 1`
  and byte-unmodified in every one of this spec's story diffs. The worker's
  installed parser must learn v2 before any manifest anywhere declares it;
  flipping this repository's manifest is a separate operator act after this
  spec lands and the worker restarts.

### Key Entities

- **Loop configuration** — the composable half of a node's verification: the
  ladder caps plus the declared step order plus the gate map. Pinned per
  epic at dispatch; the platform floor is everything it cannot say.
- **Platform floor** — what no manifest may weaken: attribution, salvage,
  worktree isolation, the diff check's presence, judge-only-behind-green,
  expiry-defaults-to-kill, merge-group landing. The floor is enforced at
  parse time by refusal, never at run time by silent correction.
- **Verify step** — one named member of the declared order, resolving to an
  activity the worker already registers. v2's registry is exactly `gates`,
  `diff_check`, `judge`; growing it is worker code, not manifest vocabulary.
- **Loop digest** — the stable identifier of a resolved loop configuration,
  recorded with every verdict so that PASS is a claim relative to a named
  definition of verified.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every v1 repo the factory builds today dispatches, verifies and
  lands with zero behavioural change — the full existing suite passes with no
  test modified.
- **SC-002**: A repo declaring `verify: [diff_check, gates, judge]` fails a
  no-op-diff attempt before any gate command runs, spending seconds where
  today's order spends a full gate run.
- **SC-003**: A node whose worktree rewrites its own manifest's `ladder:`
  escalates on the dispatch-pinned budget — demonstrated by a test in which
  the rewrite would have granted extra attempts if read.
- **SC-004**: An epic against a `max_attempts: 2` manifest pages the operator
  after exactly two ordinary attempts plus the debugger rung, and the
  escalation row's advertised deadline equals the manifest's declared one.
- **SC-005**: A judge-less declared loop completes verification with no judge
  key minted — visible as the absence of a judge ledger row for the attempt.
- **SC-006**: Every verification row written after this spec lands names its
  loop digest, and the row for a v1 repo names the explicit default.

## Work Graph

A chain, for the same honest reason as 021: US2, US3 and US4 all edit the
interpreter's `_verify` neighbourhood in `factory/workgraph/workflow.py`, and
US2 additionally shares `factory/cli/nouns/build.py` and the roadmap dispatch
path. US1 is upstream of everything because every consumer imports the parsed
shape from `factory/verify/factory_yaml.py` and `factory/verify/models.py`.
Concurrent worktrees on one module is the collision this repository has paid
for twice already.

Every edge is a **merge** edge: each story consumes the previous story's
types and plumbing from its base, and a pass edge would let a node build
against a tree without them.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-009, FR-011]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-010]
```

## Assumptions

- **`VerificationConfig` is the ladder's existing vocabulary and this spec
  adds no second one.** Manifest field names match the dataclass fields
  exactly — `max_attempts`, `max_judge_retries`, `debugger_cycles`,
  `escalation_timeout_s` — one concept, one word. `gate_timeout_s` stays out
  of `ladder:` because per-gate `timeouts:` already exists in the manifest
  and two homes for one knob is a defect.
- **Expiry semantics are floor, not knob.** Constitution VI: escalations that
  expire default to kill, after salvage. A repo declares how long the
  operator has, never what silence means.
- **Persona routing stays in the registry.** The manifest says *whether* a
  judge scores; personas.yaml says *what* a judge is (constitution VII). A
  manifest that could name models would be a second persona registry.
- **The constitution's environment-constraints wording will need one line
  amended.** "Each target repo declares runtime and test/lint/typecheck
  commands" becomes "declares runtime, gates and loop composition" — an
  amendment plus decision-log entry claimed at landing time, per governance.
  The decision-log number is deliberately unassigned here.
- **The step registry grows through worker code only.** A future `security`
  or `panel_judge` step is a registered activity plus one parser constant —
  a spec of its own, arriving with the constitution's dependency and
  review discipline. This spec's registry is closed at three on purpose.
- **`landing_branch` (020) is the precedent for every part of this.**
  Declared, never auto-detected; parsed by the worker's installed parser so a
  node cannot self-modify it; learned by the parser before any manifest
  declares it. This spec extends that pattern rather than inventing one.
