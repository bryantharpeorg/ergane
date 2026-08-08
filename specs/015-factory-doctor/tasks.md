# Tasks: Factory Doctor

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution I): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written
in any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm 009 has landed on the target's default branch
      (this spec's frontmatter edge), then re-verify plan.md's reuse
      inventory against that tree — store discipline line numbers
      (`factory/verify/store.py`), the `/key/list` paging in
      `factory/usage/litellm_client.py`, `worktree_path`'s layout, the
      roadmap grammar's `_KNOWN_KEYS`, and the criteria parser's story/FR
      regexes. The inventory was drafted 2026-08-07 against `ergane-buildout`
      at aa220ea+; landings may have moved lines or shapes. Correct the plan
      before deriving, not the nodes after.

---

## Phase 2: User Story 1 — Findings are durable records with recurrence (Priority: P1) 🎯 MVP

**Goal**: the findings grammar, the `.factory/doctor.db` store under the
evidence-store discipline, and `report`/`list`/`resolve` with recurrence and
regression semantics.

**Independent Test**: report, re-report, batch-ingest, resolve, and
re-report-after-resolve against a scratch store; identity, counts,
transitions, all-or-nothing refusal, deterministic listing.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green; `factory/verify/store.py`, `factory/workgraph/derive.py`,
      `factory/roadmap/models.py` exist and plan.md's inventory claims hold —
      constitution I gate; STOP and report blocked if not satisfied.
- [ ] T003 [P] [US1] Write store-contract cases FIRST: `connect` bootstraps a
      scratch db whose structure matches `contracts/doctor-store.sql`
      structure-for-structure (the `tests/test_verify_store.py` pattern); WAL
      journal mode and busy timeout are set; severity/status CHECK
      constraints refuse unknown values — must fail.
- [ ] T004 [P] [US1] Write recurrence cases FIRST: first report inserts open
      with occurrences 1 and an event; same-key report recurs (count +1,
      last_seen advances, latest summary/refs kept, second event, never a
      second row); report on a resolved key transitions to `regressed`
      preserving occurrences, resolution history, and appending a
      `regressed` event; the report transition is one transaction under two
      concurrent connections (plan.md § US1 trap) — must fail.
- [ ] T005 [P] [US1] Write batch-grammar cases FIRST against a fixture corpus
      (one directory per fixture, the `tests/fixtures/README.md` convention),
      `seed-findings.json` among them. The envelope is per FR-004: required
      top-level `source` applied to every entry, optional ignored `comment`,
      required `findings` list; entries carry no `source` of their own, so the
      file's provenance is the row's. Assert the seed corpus parses to 27
      findings, each taking `source: "audit-2026-08-07"` from the envelope; and
      that a malformed entry (missing field, unknown severity, key duplicated
      within the batch) or a missing top-level `source` refuses the whole batch
      with staged findings naming every offender at once, store unchanged — must
      fail.
- [ ] T006 [US1] Write CLI cases FIRST driving `main(argv)`: `report` via
      flags and via `--batch`; `list` deterministic (severity rank,
      occurrences desc, key) showing key, severity, status, occurrences, age;
      `resolve --reason` records resolution and a resolved event; regressed
      findings render distinctly; exit codes 0/1/2 per the existing contract
      — must fail.

### Implementation for User Story 1

- [ ] T007 [US1] Implement `factory/doctor/models.py` (StrEnum severity/
      status, frozen `Finding`/`FindingEvent`, pure batch parser with staged
      rejections) until T005's parsing cases pass.
- [ ] T008 [US1] Implement `factory/doctor/store.py` (connect/bootstrap with
      `_SCHEMA_DDL` verbatim from the contract, single-transaction report
      state machine, list/resolve reads) until T003 and T004 pass.
- [ ] T009 [US1] Implement `factory/doctor/cli.py` (`report`, `list`,
      `resolve`) and register `factory-doctor` in `pyproject.toml`
      `[project.scripts]` until T006 passes.

---

## Phase 3: User Story 2 — Probes catch known incident classes (Priority: P2)

**Goal**: a probe registry the `check` driver iterates; four initial probes,
each an observed incident class; skip-vs-finding semantics and the 0/1/2 exit
contract.

**Independent Test**: scripted snapshots reproducing each incident class file
the expected findings; clean snapshots file nothing; re-runs recur; exit
codes for clean, new-critical, and skipped runs.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T010 [P] [US2] Write probe-evaluation cases FIRST, one per initial
      probe, pure snapshot in / findings out: orphaned key (alias names a
      closed epic → finding with stable key naming the alias; open epic →
      silence), stale worker (process older than newest `factory/` commit →
      finding naming both timestamps), stale worktrees (closed epics' paths
      named), store integrity (failed check → `critical`); every emitted key
      is identical across two evaluations of the same snapshot — must fail.
- [ ] T011 [P] [US2] Write check-driver cases FIRST: registry iteration
      (a probe appended to the registry runs without driver changes); a
      gather raising service-not-answering marks that probe skipped with the
      service named while other probes still run; findings file through the
      US1 store with source = probe name; exit 0 clean / 1 new critical /
      2 any skip, and the both-critical-and-skip combination exits 2
      (plan.md § US2 trap) — must fail.
- [ ] T012 [P] [US2] Write the read-only case FIRST (FR-011): no probe or
      driver path invokes key deletion, worktree removal, or any process
      signal — assert the doctor module never imports or calls the mutating
      surfaces (the grep-backed 001 pattern applied to the module) — must
      fail.

### Implementation for User Story 2

- [ ] T013 [US2] Implement `factory/doctor/probes.py` (Probe protocol,
      snapshot dataclasses, four evaluations, thin gathers composing
      `litellm_client` `/key/list`, the CLI describe path for closed-ness,
      `worktree_path` layout, `git log -1 --format=%ct -- factory/`, and
      `PRAGMA quick_check`) until T010 and T012 pass.
- [ ] T014 [US2] Implement the `check` subcommand in `factory/doctor/cli.py`
      (registry drive, skip classification, new-finding accounting, exit
      codes) until T011 passes.

---

## Phase 4: User Story 3 — Accepted findings become work (Priority: P2)

**Goal**: `promote` scaffolds a deriver-clean draft spec from findings and
records the association; landed specs resolve their findings on the next
doctor run.

**Independent Test**: promote seeded findings into a scratch specs root;
scaffold structure, derive-clean, `promoted` transitions, refusals, and
landed-state auto-resolution.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T015 [P] [US3] Write scaffold cases FIRST, pure findings-in/text-out:
      frontmatter is exactly `state: draft`; one `### User Story N - ...
      (Priority: P2)` per finding with summary/refs/notes folded verbatim and
      scenario stubs matching the criteria parser's Given/When/Then shapes;
      one obligation-bearing `- **FR-NNN**:` bullet per finding; a
      `## Work Graph` block covering every story; `parse_spec` accepts the
      scaffold and `derive_workgraph` compiles it with zero rejections
      (plan.md § US3 trap: generate against the parser, test against both) —
      must fail.
- [ ] T016 [P] [US3] Write promote/loop cases FIRST: promote writes the
      scaffold, verifies it via `derive_workgraph` (supplying the four
      identity keywords the signature requires — `epic_id`, `feature`,
      `specs_root`, `target_repo`), and marks findings `promoted` with the
      spec dir in one transaction; an existing target directory refuses before
      any write; **a scaffold that fails derivation leaves nothing behind, and
      re-promoting the same slug afterwards is not blocked** (write-to-temp
      then rename, or remove on failure); an already-promoted finding refuses
      naming its spec while a `regressed` finding promotes again; a promoted
      finding whose spec frontmatter reads `state: landed` resolves on the next
      doctor invocation recording the spec. Attested frontmatter only — no
      Temporal query for observed-landed (FR-009) — must fail.
- [ ] T017 [P] [US3] Write the credential sweep FIRST (FR-010): no key value
      can reach findings, events, snapshots, scaffold text, or CLI output —
      the grep-backed 001 pattern across the doctor module — must fail.

### Implementation for User Story 3

- [ ] T018 [US3] Implement `factory/doctor/scaffold.py` until T015 passes.
- [ ] T019 [US3] Implement `promote` and the loop-closure sweep in
      `factory/doctor/cli.py` + store transitions until T016 and T017 pass.
- [ ] T020 [US3] Final sweep + docs: extend `docs/architecture.md`'s module
      table with `factory/doctor/`; claim the decision-log number in
      `docs/decisions.md` for spec § Decision (detection is durable,
      remediation is work); confirm no new dependency (constitution III) and
      the credential grep is wired into the suite.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything — including re-verifying the
  reuse inventory this plan leans on.
- Phase 2 (US1) has no dependency and is the MVP: the audit corpus gets its
  durable home the day it lands.
- Phase 3 (US2) imports US1's store and grammar — merged, not passed.
- Phase 4 (US3) imports the same and shares the CLI wiring file with US2 —
  merged, sequential (spec § Work Graph).

## Implementation Strategy

US1 alone is worth landing if anything must be cut — the seed corpus ingests
and `list` replaces the chat artifact as the audit's home. US2 makes the
ledger self-feeding; US3 closes the loop into the roadmap. Nothing modifies
the interpreter, the roadmap workflow, or the worker: the doctor is CLI verbs
over its own store, which is what keeps it buildable by the factory it
examines — and keeps every probe honest about FR-011: the doctor diagnoses;
epics operate.
