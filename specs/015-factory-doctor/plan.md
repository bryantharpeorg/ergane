# Implementation Plan: Factory Doctor

**Branch**: `015-factory-doctor` | **Date**: 2026-08-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/015-factory-doctor/spec.md`

## Summary

A `factory-doctor` console script over a new `factory/doctor/` module: a
findings ledger in `.factory/doctor.db` (identity-keyed, recurrence-counting,
regression-aware), a registry of deterministic probes for the incident classes
the factory has already exhibited, and a `promote` verb that scaffolds a
deriver-clean spec directory from accepted findings — closing the loop from
"this keeps happening" to "the factory is building the fix" with the operator
holding exactly one decision: the `ready` flip.

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so every fact an implementer node needs is inlined, each
verified against the tree the day of drafting — and T001 re-verifies them
against the tree that actually hosts the work.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: `sqlite3` and `json` (stdlib), `yaml` (roster,
`tests/test_final_sweep.py`), `temporalio` only through the existing CLI
connect path. **This feature adds none.**

**Verified reuse inventory** (file:line as of drafting; T001 re-checks):

- **Store discipline**: `factory/verify/store.py` is the template — WAL +
  busy timeout in `connect` (:167), `_bootstrap_schema` (:183), `_SCHEMA_DDL`
  as a verbatim copy of the contract file, held structure-for-structure by
  `tests/test_verify_store.py`. The doctor store copies the shape:
  `contracts/doctor-store.sql` in this directory is the contract;
  `factory/doctor/store.py` is the one writer. Upsert-on-identity mirrors
  `upsert_result` (:235) — at-least-once callers land on one row.
- **Store paths**: `.factory/ledger.db` (`factory/usage/cli.py:45`,
  `factory/activities/usage_activities.py:94`) and `.factory/verification.db`
  (`factory/activities/verify_activities.py:121`) establish the `.factory/`
  convention `doctor.db` joins. Resolution from the working directory, the
  way the ledger does it.
- **Orphaned-key probe**: `factory/usage/litellm_client.py` already pages
  `/key/list` (page size cap noted at :45) and constructs from env
  (`from_env`, :135, `PROXY_URL_ENV`); the probe composes existing client
  calls and adds no new endpoint. Key *values* never enter snapshots —
  aliases and hashed tokens only (`hashed_token`, :66).
- **Closed-epic fact**: `factory/workgraph/cli.py` `_connect()` and
  `workflow_id(epic_id) -> f"epic-{epic_id}"` — the probe describes
  workflows by that id convention to learn closed-ness, read-only, the same
  path `status` uses. Env-before-client ordering in `start_command` is the
  pattern to keep.
- **Stale-worktree probe**: layout is `.factory/worktrees/<epic>/<node>`
  (`factory/workgraph/worktree.py:134-140`, `worktree_path`); epic ids read
  straight off the directory names and closed-ness comes from the same
  describe path above.
- **Stale-worker probe**: newest commit touching `factory/` via
  `git log -1 --format=%ct -- factory/`; worker process start time via
  `/proc/<pid>/stat` or `ps -o lstart=` on the discovered worker pid. Keep
  the gather thin and the comparison pure; if no worker process is found,
  that is its own finding (`ops/no-worker-running`), severity `info` — a
  laptop run is not an incident.
- **Scaffold self-check**: `derive_workgraph` (`factory/workgraph/derive.py`,
  pure) is invoked directly by `promote` on the scaffold text before anything
  reports success — the same function the CLI's `derive` verb wraps, so
  "compiles for promote" and "compiles for dispatch" are one fact. Its
  signature is not text-only: `derive_workgraph(spec_text, *, epic_id, feature,
  specs_root, target_repo)`, so promote must supply the four identity
  keywords — for a scaffold, the slug it just chose and the operator's
  specs-root and target-repo. `parse_spec` (`factory/verify/criteria.py:122`) defines the
  story/FR shapes the scaffold must emit: `### User Story N - Title
  (Priority: PX)` headers (`_STORY_RE`, :74), `**Acceptance Scenarios**:`
  marker (:83), `- **FR-NNN**:` bullets with MUST/SHALL obligation keywords
  (:80, :98).
- **Roadmap grammar for loop closure**: `factory/roadmap/models.py` — the
  pure frontmatter reader and states (`_KNOWN_KEYS = ("state",
  "depends_on_landed")`, :107). US3 reads promoted specs' states through it;
  `landed` (attested) or observed-landed through the roadmap's readiness
  computation resolves the finding. The doctor never writes any state but
  `draft` into a scaffold.
- **CLI shape**: `factory/workgraph/cli.py` (`main`, :188; subparsers, :707)
  and `factory/roadmap/cli.py` (offline-verb precedent: render touches no
  service, stdout carries only the render, exit codes 0/1/2 documented in
  the module docstring). `factory-doctor` registers in `pyproject.toml`
  `[project.scripts]` beside `factory-usage`/`factory-epic`/
  `factory-roadmap` (:13-16).
- **Rejection style**: the deriver's staged `_Rejections` collection
  (`factory/workgraph/derive.py:126`) is the template for batch-ingestion
  refusal — every defect named at once, nothing partially ingested; the
  fixture-corpus pattern (`tests/fixtures/README.md`) is the test template.
- **Seed corpus**: `seed-findings.json` in this directory — 27 findings from
  the 2026-08-07 audit, the batch-ingestion fixture and SC-001's input.

**Storage**: `.factory/doctor.db`, WAL, schema from the contract file. Host-
local evidence, never committed; replication is itself a seed finding
(`hardening/litestream-evidence-stores`), deliberately not solved here.

**Testing**: `pytest`. Probes split gather (thin, impure) from evaluate
(pure: snapshot dataclass in, findings out) so every probe's judgment runs
against scripted snapshots — the fakes-under-real-names ethos without needing
a live proxy or Temporal. CLI tests drive `main(argv)` directly, the way the
existing CLI tests do. No time-skipping environment is needed anywhere: the
doctor has no workflow.

**Project Type**: single Python package; new module directory
`factory/doctor/` (models, store, probes, scaffold, cli), mirroring
`workgraph/`'s layout so `docs/architecture.md`'s module table extends rather
than bends.

## Constitution Check

- **I (test-first)**: every task pairs a failing test with implementation.
- **III (dependencies)**: none added; stdlib + roster only.
- **V (credentials)**: FR-010. Probe snapshots carry aliases and hashed
  tokens only; the sweep asserts findings, events, scaffolds, and CLI output.
- **VI (salvage)**: untouched — the doctor owns no node terminal path.
- **VII (persona routing)**: untouched — the doctor never chooses a model.

## Approach by story

### US1 — grammar, store, report/list/resolve (FR-001..004)

`factory/doctor/models.py`: `Severity` and `Status` as `StrEnum` (the
`workgraph/models.py` spelling), a frozen `Finding` and `FindingEvent`, and a
pure batch parser for the findings JSON grammar with staged
`_Rejections`-style findings (duplicate-key-in-batch, unknown severity,
missing field — each named, all at once). `factory/doctor/store.py`: connect/
bootstrap from the contract DDL; `report` as one transaction implementing the
FR-002 state machine (insert | recur | regress + event append); reads for
`list`. `factory/doctor/cli.py`: `report` (flags or `--batch`), `list`,
`resolve --reason`. Ordering: severity rank, occurrences desc, key — computed
in SQL so the CLI stays a renderer.

Trap: the FR-002 transition must be one transaction. A recur that bumps the
row but loses the event (or vice versa) under a concurrent report is exactly
the corruption the WAL discipline exists to prevent — write the concurrency
test with two connections, not two calls.

### US2 — the probe registry and check (FR-005..007, 011)

`factory/doctor/probes.py`: `Probe` protocol — `name`, `gather() -> Snapshot`
(thin, may touch proxy/Temporal/fs/git), `evaluate(Snapshot) ->
list[FindingReport]` (pure). A module-level registry list the `check` driver
iterates; adding a probe is appending to it. Gather failures classify: a
service not answering marks the probe skipped-with-service-named (drives exit
2); any other exception is a probe bug and propagates. `check` files findings
through US1's store (source = probe name), then computes the exit code from
what was *new* this run: 0 clean, 1 new critical, 2 any skip. The four
initial probes per the inventory above.

Trap: exit-code precedence. A run with both a new critical and a skipped
probe exits 2 — "I could not fully examine you" outranks "and what I did see
is bad" — because 2 is the only code that tells the operator the report is
incomplete. State it in the CLI docstring and test the combination.

### US3 — promote and the closed loop (FR-008..010)

`factory/doctor/scaffold.py`: pure text generation — findings in, the three
files' contents out (spec.md with `state: draft` frontmatter, one story per
finding at P2 with evidence folded verbatim into the narrative and a
scenario stub per ref; one `- **FR-NNN**: ... MUST ...` bullet per finding;
`## Work Graph` block with `depends_on: []`/`implements` per story; plan.md
and tasks.md skeletons pointing back at finding keys). `promote` in the CLI:
refuse-existing-dir, write to a temporary directory, run `derive_workgraph` on
the written spec text, and **rename into place only on a clean compile** — on
rejection the temporary directory is removed and nothing survives, because a
half-written directory would trip the refuse-existing rule and block every
retry of that slug (US3-S6). On success mark findings `promoted` in one
transaction. Loop closure runs as a cheap sweep at the top of every doctor
command: promoted findings' specs read through the roadmap's frontmatter
grammar; `state: landed` → resolve with the spec named. Attested state only —
observed-landed lives in `RoadmapWorkflow`'s in-memory state and would cost a
Temporal query against a possibly-closed workflow on every command (FR-009).

Trap: the scaffold's scenario stubs must satisfy `_STEP_RE` (bold
Given/When/Then) and the story headers `_STORY_RE` exactly — derive's
self-check catches structural misses, but the criteria parser is the stricter
reader and `snapshot_criteria` is the one that runs at dispatch. Generate
against `parse_spec`, test against both.

## Complexity Tracking

None. No new dependency, no new workflow type, no schema migration (version 1
bootstraps), no async surface beyond the existing client calls the probes
compose.
