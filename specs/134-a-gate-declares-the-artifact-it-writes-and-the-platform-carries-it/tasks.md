# Tasks: a gate declares the artifact it writes and the platform carries it

Read `plan.md` before starting. Nine of its traps decide whether this spec is
worth anything, and most of them name a mistake a green suite will not catch:

**Trap 1** — `expected_artifacts` has exactly the right name, is the first thing
you will find, and is the anti-rubber-stamp check for read-scope nodes. Its one
production caller passes `[]` literally. Extending it produces a spec that appears
to land and changes nothing.

**Trap 2** — `VerificationConfig` is the retry ladder, not the parsed manifest.
The class carrying `gates`, `timeouts` and `writes` is `FactoryConfig`. A previous
draft of this plan told an implementer to use the wrong one and validate stayed
green, because both names resolve.

**Trap 3** — `writes:` is a boolean per gate, not a list of paths. Do not flip
`writes_declared`, and do not write the branch as "…and not artifact_paths":
either excuses every path the gate wrote and retires 084's watch for every
artifact-emitting gate. Subtract this gate's declared paths, below the
`snapshot_error` branch. US2-S6 is the reproduction that catches both. The third
wrong move is quieter: that subtraction is string equality against git's own
spelling, so a path accepted verbatim as `./coverage.xml` collects perfectly and
still demotes its gate. Normalise at load time (T010, US1-S8); do not loosen the
comparison at T020.

**Trap 4** — the worktree watch never sees a git-ignored path. Write US2's
fixture over an **unignored** path or the story's headline test is green before you
start, and read US3's artifacts **from disk**, never from `worktree_writes`.

**Trap 6 and trap 7** — the bytes may not travel on a `GateResult`: it is a
Temporal activity return value and an SBOM is megabytes. The record carries a
reference, and the destination is resolved **in the activity**, never in the
workflow, which may read neither the environment nor the filesystem.

**Trap 8** — the destination crosses four frames. A parameter added only to
`_run_watched` compiles, unit-tests green and collects nothing in production.

**Trap 15** — the runtime root is routinely **inside** the target clone: on this
host `ERGANE_ROOT` is `$HOME/code/ergane/.factory` and the node worktrees live
under it, git-ignored. Assert the destination is outside the **node worktree** and
nothing more; a containment check against the target repository would refuse every
gate run here, and `RunGatesInput` carries no target-repository path anyway.

**Trap 9** — the collector must not write inside the worktree it is watching: the
closing snapshot is handed forward as the next gate's opening one, so a byte
written there demotes an innocent gate.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

The 2026-09-10 release refinement in plan.md supersedes earlier path-only safety
and epic/node/attempt-only storage assumptions. Preserve the existing story IDs;
use T053 through T060 in their phases below. Do not dispatch a stale workgraph.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A manifest declares the artifacts its gates write

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, plan trap 2) Given a v2 manifest
      declaring a top-level `artifacts:` list **beside** `gates:`, each entry
      naming a declared gate, a repo-relative path and a type from
      `sbom`/`coverage`/`scan`/`opaque`, assert it parses and the `FactoryConfig` —
      not `VerificationConfig` — carries the entries in declaration order.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Given an entry naming a type outside
      that set, assert refusal with the entry and the permitted types named.
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) Given an entry naming a gate the
      manifest does not declare, assert refusal naming the entry and the declared
      gates, the way `_read_writes` (`factory/verify/factory_yaml.py:443` —
      `_read_writes`) already refuses one.
- [ ] T004 [P] [US1] (spec US1-S4, FR-012) Given an entry whose path is absolute,
      and one whose relative path escapes the repository root, assert each is
      refused with the path named at load time — the same discipline `_read_caches`
      (`factory/verify/factory_yaml.py:761` — `_read_caches`) applies to a declared
      bind.
- [ ] T005 [P] [US1] (spec US1-S5, FR-003) **The control.** Given a manifest
      declaring no artifacts, assert the parsed configuration is equal, in every
      field that existed before this story, to what the same manifest parsed to
      before it, and that its artifact field is empty. Assert it field by field:
      the new field is defaulted, so whole-object equality against a pre-story
      configuration cannot be written honestly.
- [ ] T006 [P] [US1] (spec US1-S6, FR-003) **The control.** Given a v1 manifest
      declaring `artifacts:`, assert it is refused as an unknown top-level key by
      `_reject_unknown_keys` (`factory/verify/factory_yaml.py:281` —
      `_reject_unknown_keys`).
- [ ] T007 [P] [US1] (spec US1-S7, FR-013, plan trap 5) Given a parsed
      configuration carrying artifact declarations, assert the parser's own CLI
      renders it as one JSON document whose entries carry path and type as
      strings. A `Path` or a plain `Enum` raises inside `json.dumps` at
      `factory/verify/factory_yaml.py:1239` — `_main`, and the caller cannot tell
      that from a crashed parser.
- [ ] T052 [P] [US1] (spec US1-S8, FR-012, plan trap 3) Given an entry whose path
      is spelled `./coverage.xml` and another spelled `reports/../coverage.xml`,
      assert each parses and each carried path is `coverage.xml` — the spelling
      `git diff-tree --name-only` prints and therefore the only spelling US2's
      subtraction can match. A reader that records the operator's spelling verbatim
      passes every other scenario in this phase and makes US2's exemption miss by a
      prefix. (Its id sits above this phase's block because it was added in a later
      refinement pass; task ids are labels, and renumbering the file would break the
      ids already cited elsewhere in the trio — T034 in plan.md § Sizing, T041 in
      spec.md's provenance.)

### Implementation for this story

- [ ] T008 [US1] (FR-001, FR-003) Add `artifacts` — that literal spelling, which
      FR-001 fixes because every target repository's manifest will carry it
      forever — to `_V2_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:144`), as
      a **sibling** top-level key and not a richer gate value: `_read_gates`
      (`factory/verify/factory_yaml.py:340` — `_read_gates`) requires each gate's
      value to be a non-empty string, and changing that grammar would touch every
      manifest in existence. Spec 128 is adding `boundary_only_gates` to the same
      tuple; expect a one-line conflict there if both epics run at once.
- [ ] T009 [US1] (FR-001, FR-002, FR-012) Add `ArtifactType` as a `StrEnum` over
      `sbom`/`coverage`/`scan`/`opaque` and the declaration record beside
      `CacheDeclaration` (`factory/verify/models.py:241` — `CacheDeclaration`),
      path as `str`, and the field on `FactoryConfig`
      (`factory/verify/models.py:291` — `FactoryConfig`), defaulted empty so a
      manifest that declares nothing is unchanged. **This story owns the four type
      names.** They live here, as a `StrEnum` for the reason `GateStatus`
      (`factory/verify/models.py:73` — `GateStatus`) is one — it survives
      `dataclasses.asdict` plus `json.dumps` where a plain `Enum` raises (trap 5) —
      and US3 reuses this enum on `GateArtifact` rather than spelling the set a
      second time.
- [ ] T010 [US1] (FR-001, FR-002, FR-012) Write the reader modelled on
      `_read_caches` (`factory/verify/factory_yaml.py:761` — `_read_caches`):
      entry-is-a-mapping, unknown-key-inside-an-entry, empty-list and path-bound
      refusals, each naming the entry. **Invert that model's bound and keep yours
      lexical**: `_read_caches` refuses a *relative* path, expands it, calls
      `.resolve()` and requires the result under `Path.home()`, a filesystem touch
      its docstring calls a deliberate departure. FR-012 is the mirror image —
      refuse an absolute path, and refuse any path whose normalised segments leave
      the repository root, with no filesystem call, because this parser runs
      wherever the candidate CLI is invoked and a resolved comparison would judge
      the escape against the reading process's own directory. **Then store what you
      accepted in one spelling**: the path that goes on the record is the normalised
      worktree-root-relative form — posix separators, no `.` and no `..` segment —
      because the only thing that ever compares it is T020's subtraction, a string
      equality against `git diff-tree --name-only` output, and `./coverage.xml`
      never equals `coverage.xml` (plan trap 3). You already computed the normalised
      segments to decide the escape; keep them rather than throwing them away and
      recording the operator's spelling.

### Verification for this story

- [ ] T011 [US1] Paste, as committed evidence, the four refusals (bad type,
      undeclared gate, absolute path, escaping path), the successful parse of a
      correct declaration, and the parser CLI's JSON for that same manifest.

## Phase 2: User Story 2 — A declared artifact reaches the runner and the gate's write exemption

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-004, plan trap 4) Given a gate declaring an
      artifact at a path the fixture repository does **not** git-ignore, and the
      gate exits 0 having written exactly that path, assert its status is `PASS`
      and the path is still listed in `worktree_writes`. Assert the fixture's
      `.gitignore` does not cover the path, in the test, or the assertion is green
      before the implementation exists.
- [ ] T013 [P] [US2] (spec US2-S2, FR-005) **The control.** Given a gate that
      exits 0 having written a path declared neither as an artifact nor through
      `writes:`, assert `DIRTIED_WORKTREE` exactly as today. 084's watch is
      correct and this story teaches it, not weakens it.
- [ ] T014 [P] [US2] (spec US2-S3, FR-005) **The control.** Given a gate that
      declares an artifact and does not write it, assert its status is whatever its
      exit code and deadline made it, unchanged.
- [ ] T015 [P] [US2] (spec US2-S4, FR-014, plan trap 5) Given a candidate
      acceptance document carrying artifact declarations, assert
      `_interpret_candidate` (`factory/verify/gates.py:1045` —
      `_interpret_candidate`) lifts them onto `_AcceptedConfig`
      (`factory/verify/gates.py:205` — `_AcceptedConfig`) and that the runner
      receives them on that route, not only on the in-process fallback.
- [ ] T016 [P] [US2] (spec US2-S5, FR-005) **The control.** Given a gate whose
      written paths were all declared artifacts but whose worktree snapshot git
      refused to read, assert `DIRTIED_WORKTREE` — the exemption sits below the
      `snapshot_error` branch, not above it.
- [ ] T017 [P] [US2] (spec US2-S6, FR-004, FR-005, plan trap 3) **The control that
      pins the exemption to a path.** Given one gate that exits 0 having written
      both the path it declared as an artifact and one unignored path it declared
      nowhere, assert its status is `DIRTIED_WORKTREE` and that both paths appear
      in `worktree_writes`. A blanket implementation — `writes_declared` flipped,
      or the branch written as "…and not artifact_paths" — passes every other
      scenario in this story and fails only this one.

### Implementation for this story

- [ ] T018 [US2] (FR-014) Carry the declarations through the JSON route: the field
      on `_AcceptedConfig` (`factory/verify/gates.py:205` — `_AcceptedConfig`), the
      lift in `_interpret_candidate` (`factory/verify/gates.py:1045` —
      `_interpret_candidate`), and the view parameter on `_run_gate_list`
      (`factory/verify/gates.py:1416` — `_run_gate_list`).
- [ ] T019 [US2] (FR-014) Carry the same declarations on the in-process route from
      `_run_gate_list_from_config` (`factory/verify/gates.py:1467` —
      `_run_gate_list_from_config`), and down into `_run_watched`
      (`factory/verify/gates.py:1511` — `_run_watched`) as an argument, the way
      `writes_declared` is decided by the runners and passed down.
- [ ] T020 [US2] (FR-004, FR-005, plan trap 3) Exempt this gate's declared
      artifact paths, path by path, inside `_to_result`
      (`factory/verify/gates.py:1583` — `_to_result`), below the `snapshot_error`
      branch at `factory/verify/gates.py:1629` — `_to_result`. Subtract the
      declared paths from the set the demotion tests; leave `worktree_writes` and
      `writes_declared` untouched. Do not set `writes_declared` — it means "the
      manifest named this gate in its `writes:` block" and would excuse every path
      the gate wrote. Compare by plain string equality against the recorded paths,
      which `changes_between` (`factory/verify/worktree_snapshot.py:100` —
      `changes_between`) fills from `git diff-tree -r --name-only -z`: US1 already
      normalised the declaration to that spelling (T010), so a prefix-strip, a
      `resolve()` or any other fuzzy match added here would only start excusing
      paths the manifest never named.

### Verification for this story

- [ ] T021 [US2] Paste, as committed evidence, three gate results with their
      `worktree_writes` tuples shown: one gate emitting a declared artifact at an
      unignored path and passing, one emitting an undeclared path and being
      demoted, and one emitting both and being demoted.

## Phase 3: User Story 3 — The boundary collects what was declared

### Tests for this story (write FIRST, must fail)

- [ ] T022 [P] [US3] (spec US3-S1, FR-006, plan traps 1 and 4) Given an attempt
      whose gate wrote a declared artifact, assert that gate's
      `GateResult.artifacts` carries one `GateArtifact` with the declared path, the
      declared type, present true, the true size in bytes and the stored location,
      and that the stored location holds the bytes the gate wrote. **Do not route
      this through `expected_artifacts`** — that field is the anti-rubber-stamp
      check for read-scope nodes and its one production caller passes `[]` at
      `factory/workgraph/workflow.py:2714` — `_verify`. Use a git-ignored path in
      this fixture, so the test also proves collection reads from disk and not from
      `worktree_writes`.
- [ ] T023 [P] [US3] (spec US3-S2, FR-007, plan trap 11) Given a declared artifact
      the gate did not write, assert the record carries a `GateArtifact` marked
      absent rather than omitting it. Omission makes "the gate did not emit it"
      indistinguishable from "nobody declared it".
- [ ] T024 [P] [US3] (spec US3-S3, FR-008, plan trap 10) Given a declared artifact
      of type `opaque`, assert its record carries the same fields, filled the same
      way, as a `coverage` artifact's does. `opaque` is a type, not a fallback —
      otherwise every new format is a platform change before a consumer can use it.
- [ ] T025 [P] [US3] (spec US3-S4, FR-015, plan trap 12) Given a declared artifact
      larger than the named stored-bytes bound, assert the record says present,
      carries the true size, names no stored location, and that no truncated copy
      exists at the destination. Half an SBOM is a corrupt SBOM, not a smaller one.
- [ ] T026 [P] [US3] (spec US3-S5, FR-016, plan trap 6) Given artifacts of growing
      size, assert the serialised `GateResult` list stays within a fixed size — the
      record carries a reference and never the bytes, because this list is a
      Temporal activity return value (`factory/activities/verify_activities.py:263`
      — `run_gates`).
- [ ] T027 [P] [US3] (spec US3-S6, FR-009) Given a declared `coverage` artifact
      whose bytes are not well-formed XML, assert it is collected and recorded
      exactly as a well-formed one is. The platform carries bytes and a declared
      type and grades neither.
- [ ] T028 [P] [US3] (spec US3-S7, FR-006) **The control.** Given a repository
      declaring no artifacts, assert every `GateResult.artifacts` is empty, that
      nothing is written to the destination, and that each gate's result is equal,
      field by field, to what that gate produced before this story in every field
      that existed then.
- [ ] T029 [P] [US3] (spec US3-S8, FR-018, plan trap 9) **The control.** Given two
      gates where the first declares and writes an artifact that is collected,
      assert the second gate's status and `worktree_writes` are exactly what they
      are when nothing is declared. `_run_watched` hands its closing snapshot
      (`factory/verify/gates.py:1553` — `_run_watched`) forward as the next gate's
      opening one (`factory/verify/gates.py:1566` — `_run_watched`), so a copy made
      inside the worktree demotes an innocent gate.
- [ ] T030 [P] [US3] (spec US3-S9, FR-011, plan trap 13) **The control.** Given an
      attempt with collected artifacts, assert the prompt `_gate_blocks`
      (`factory/verify/judge.py:409` — `_gate_blocks`) assembles is byte-identical
      to the one it assembles for the same attempt with no artifacts declared.
      Assert against that function by name: it is where 116 put gate results into
      the prompt and where an implementer "finishing the job" would add a line, and
      admitting an artifact there is a constitutional change that belongs in its
      own spec with its own decision entry.

- [ ] T053 [US3] (US3-S10, FR-020) Before the collector change, add failing real-file tests for escaping/substituted symlinks, hardlink aliases, FIFO/special files, bounded reads and explicit refusal without gate-verdict change.
- [ ] T054 [US3] (US3-S11, FR-022) Add failing before/after capture tests distinguishing unchanged preexisting report, newly produced bytes and mutation during collection; no stale-as-fresh or inconsistent snapshot claim.

### Implementation for this story

- [ ] T031 [US3] (FR-006, FR-008) Add the `GateArtifact` record and `artifacts:
      tuple[GateArtifact, ...] = ()` on `GateResult`
      (`factory/verify/models.py:374` — `GateResult`), defaulted so every caller and
      every stored row written before this story reads back unchanged. Type the
      record's type field with the `ArtifactType` `StrEnum` US1 defined — do not
      mint a second spelling of the four names, or the refusal message US1 emits
      and the record US3 writes can drift apart.
- [ ] T055 [US3] (FR-020, FR-022) Implement handle-based safe collection and freshness/status metadata in `factory/verify/gates.py` and `factory/verify/models.py`; keep output references bounded and never execute/interpret report bytes. T053/T054 run before this implementation.
- [ ] T032 [US3] (FR-006, FR-018, plan trap 8) Thread the destination across all
      four frames, defaulted empty and meaning "collect nothing" — `run_gates`
      (`factory/verify/gates.py:1225` — `run_gates`), `_run_gate_list`
      (`factory/verify/gates.py:1416` — `_run_gate_list`),
      `_run_gate_list_from_config` (`factory/verify/gates.py:1467` —
      `_run_gate_list_from_config`) and `_run_watched`
      (`factory/verify/gates.py:1511` — `_run_watched`). A parameter added to
      `_run_watched` alone compiles and never arrives; US5 is the story that
      supplies a value.
- [ ] T033 [US3] (FR-006, FR-007, FR-009, FR-015, FR-018) Collect in `_run_watched`
      (`factory/verify/gates.py:1511` — `_run_watched`): for each declaration on
      the gate that just ran, read the declared path from the worktree on disk,
      record present/absent and the true size, copy the bytes to the destination
      when they are within the bound, and never parse them. Refuse to write
      anywhere inside `invocation.cwd`: the snapshot taken at
      `factory/verify/gates.py:1553` — `_run_watched` is already the next gate's
      baseline.

### Verification for this story

- [ ] T034 [US3] Paste, as committed evidence, one attempt's records showing a
      collected coverage artifact and a declared-but-absent one — one record of
      each, not one per type — and the directory listing of the destination.

## Phase 4: User Story 5 — The bytes land in one absolute place the activity resolves

### Tests for this story (write FIRST, must fail)

- [ ] T035 [P] [US5] (spec US5-S1, FR-017, plan traps 7 and 15) Given a
      `RunGatesInput` (`factory/activities/verify_activities.py:217` —
      `RunGatesInput`) carrying an epic id, a node id and an attempt, assert the
      destination the activity hands the runner is an absolute path under the root
      `resolve_factory_root` (`factory/workgraph/worktree.py:191` —
      `resolve_factory_root`) returns, scoped to that epic, node and attempt, and
      outside the node worktree. Pin it to the resolver by running the same request
      under a second resolved root and asserting the destination moves with it.
      **Do not assert it falls outside the target clone**: on this host the root is
      `$HOME/code/ergane/.factory`, git-ignored, with the node worktrees under it,
      so that assertion is green only on a tmp root (trap 15).
- [ ] T036 [P] [US5] (spec US5-S2, FR-017, plan trap 7) Assert the input `_verify`
      (`factory/workgraph/workflow.py:2700` — `_verify`) **constructs** carries the
      epic id, the node id and the attempt, and sets no filesystem path but the
      worktree — assert over that instance, not over `RunGatesInput`'s field list,
      which also declares `factory_yaml_path` and which this call site leaves at
      its default.
      Workflow code may read neither the environment nor the filesystem
      (constitution IV, `factory/workgraph/worktree.py:264` — `PreparedWorktree`),
      so a path composed there is either worktree-relative and lost, or a fifth
      runtime-root resolver.
- [ ] T037 [P] [US5] (spec US5-S3, FR-017) **The control.** Given an environment in
      which the engine's runtime-root resolver answers with a relative path — its
      default, `DEFAULT_RUNTIME_ROOT` at `factory/workgraph/worktree.py:93` —
      assert the destination the activity composes and the location it records are
      absolute. A relative root resolves against whichever directory the worker
      happens to be in, which is the class four ledger findings and spec 129 are
      about.
- [ ] T038 [P] [US5] (spec US5-S4, FR-019) Given an attempt whose gate results
      carry collected artifacts, assert the written row reads back with each
      artifact's path, type, presence, size and stored location, through
      `_gate_to_dict` (`factory/verify/store.py:1091` — `_gate_to_dict`) and
      `_gate_from_dict` (`factory/verify/store.py:1105` — `_gate_from_dict`).
- [ ] T039 [P] [US5] (spec US5-S5, FR-019) **The control.** Given a stored row
      whose gate results carry no artifact key at all — the shape every row written
      before this spec has — assert it decodes to a `GateResult` equal in every
      field that existed before this story with the artifact field empty, and that
      no schema statement changed: `gate_results` is a JSON column
      (`factory/verify/store.py:216`).
- [ ] T040 [P] [US5] (spec US5-S6, FR-019) **The control.** Given an attempt in a
      repository declaring no artifacts, assert the row it stores decodes to a
      result equal, in every field that existed before this story, to what the same
      attempt stored before it.

- [ ] T056 [US5] (US5-S7, FR-021) Before identity persistence changes, add failing real-store tests for two dispatches/captures sharing ordinals, identical redelivery and conflicting bytes; old artifact-free rows remain readable.

### Implementation for this story

- [ ] T041 [US5] (FR-017) Add the epic id, node id and attempt to `RunGatesInput`
      (`factory/activities/verify_activities.py:217` — `RunGatesInput`), defaulted
      so every existing caller is unchanged, and compose the destination inside the
      `run_gates` activity (`factory/activities/verify_activities.py:263` —
      `run_gates`) beside `_store_path`
      (`factory/activities/verify_activities.py:634` — `_store_path`): resolve the
      root through `resolve_factory_root` (`factory/workgraph/worktree.py:191` —
      `resolve_factory_root`) the way `factory_root`
      (`factory/activities/agent_activities.py:179` — `factory_root`) does, make it
      absolute, and scope it by epic, node and attempt. Take the *site* from
      `_store_path` and the *resolver* from `factory_root`, and do not copy
      `_store_path`'s own resolution: it calls `resolve_env_path`
      (`factory/env.py:47` — `resolve_env_path`) with the hardcoded legacy default
      `.factory/verification.db` (`factory/activities/verify_activities.py:128`)
      and never reaches `resolve_factory_root` — copying it is the fifth resolver
      trap 7 forbids. Never inside the node
      worktree — and add no check that it falls outside the target clone: the root
      is git-ignored and routinely sits inside that clone, `RunGatesInput` carries
      no target-repository path to compare against, and a guard invented from one
      would refuse every gate run on this host (plan trap 15).
- [ ] T057 [US5] (FR-021) Extend activity identity and gate JSON codecs with dispatch, immutable capture identity, digest/status/freshness; publish atomically outside the node worktree and preserve previous captures. Use deterministic workflow identity, never an ambient timestamp guess.
- [ ] T042 [US5] (FR-017) Pass the attempt's identity — and no path — from `_verify`
      (`factory/workgraph/workflow.py:2700` — `_verify`), which holds
      `request.graph.epic_id`, `node.id` and `attempt` already. Resolve nothing
      here and import nothing that reads the filesystem.
- [ ] T043 [US5] (FR-019) Extend `_gate_to_dict` (`factory/verify/store.py:1091` —
      `_gate_to_dict`) and `_gate_from_dict` (`factory/verify/store.py:1105` —
      `_gate_from_dict`), defaulting an absent key to the empty tuple the way
      `worktree_writes` already does. No schema migration: `gate_results` is a JSON
      column (`factory/verify/store.py:216`).

### Verification for this story

- [ ] T044 [US5] Paste, as committed evidence, the absolute destination one
      attempt's bytes were written to, the listing of that directory, and the same
      listing after the node worktree has been removed — "readable per attempt
      afterwards" is half of what the declared ledger keys asked for.

## Phase 5: User Story 4 — An exported reader returns them per attempt

### Tests for this story (write FIRST, must fail)

- [ ] T045 [P] [US4] (spec US4-S1, FR-010) Given an attempt whose stored row
      carries collected artifacts, assert the exported reader returns each with its
      declared path, declared type, producing gate name, presence and stored
      location, over a connection from `connect_readonly`
      (`factory/verify/store.py:401` — `connect_readonly`).
- [ ] T046 [P] [US4] (spec US4-S2, FR-010) Given two attempts of the same node
      whose artifacts differ, assert each call returns its own attempt's set and
      neither returns the other's.
- [ ] T047 [P] [US4] (spec US4-S3, FR-010) **The control.** Given an attempt whose
      row carries no artifacts, assert an empty tuple rather than a raise.

- [ ] T058 [US4] (US4-S4, FR-023) Before extending the reader, add failing read-only tests for explicit dispatch/capture selection, returned digest/status/freshness and refused ambiguous old-style requests.

### Implementation for this story

- [ ] T048 [US4] (FR-010) Add the exported reader beside `node_history`
      (`factory/verify/store.py:873` — `node_history`) and `attempt_timings`
      (`factory/verify/store.py:944` — `attempt_timings`), attributing each
      artifact to the `GateResult` it came off. "A reader must exist or nothing can
      display it" is PR-3's central argument and this is it.
- [ ] T059 [US4] (FR-023) Extend the same exported reader rather than adding a second artifact API; retain unambiguous legacy calls and empty-result controls.

### Verification for this story

- [ ] T049 [US4] Paste the reader's output for two attempts of one node, as
      committed evidence that artifacts are attempt-scoped.

## Verification

- [ ] T060 Operator pre-dispatch: derive the refined five-node graph into a new isolated output, inspect FR-020 through FR-023 coverage, and reassess US3's code+tests+evidence size against64KiB; do not overwrite the user's stale untracked graph.
- [ ] T050 The full gate command passes green.
- [ ] T051 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. **Step 1's "without changing anything else in
      that repository" is the falsifiable test of the whole spec**: a consumer has
      already built the producer half at standard stable paths on the explicit
      expectation that a platform collector could take it unchanged. If it cannot,
      this spec solved a different problem.
