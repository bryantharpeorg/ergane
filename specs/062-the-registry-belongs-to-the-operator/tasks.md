# Tasks: the registry belongs to the operator

**Spec**: `specs/062-the-registry-belongs-to-the-operator/spec.md`
**Plan**: `specs/062-the-registry-belongs-to-the-operator/plan.md`

Read the plan's **Traps** before the first task. Trap 4 must be resolved before
anything is dispatched: this spec can break the factory that is building it.

Tests are written before the implementation and must fail for the stated reason
before anything is made to pass.

Edges: US1 → US2 (both edit `factory/config.py`). US3 is independent.

## Phase 1: User Story 1 — The registry resolves from the operator's own config directory

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) Assert `$ERGANE_PERSONAS_PATH` wins when set and readable.
- [ ] T002 [P] [US1] (spec US1-S2) Assert `~/.config/ergane/personas.yaml` wins over package
      data when no env override is set.
- [ ] T003 [P] [US1] (spec US1-S3) Assert package data resolves when neither is present, with
      no repository above the package — the 054 trap-4 case (trap 2).
- [ ] T004 [P] [US1] (spec US1-S4) Assert `XDG_CONFIG_HOME` is honoured rather than
      `~/.config` being hardcoded, mirroring
      `factory/controlplane/config.py:202`.
- [ ] T005 [P] [US1] (spec US1-S5) Assert an environment override changes what each of the
      five call sites resolves: `factory/activities/roadmap_activities.py:334`,
      `factory/cli/nouns/spec.py:408`, `factory/workgraph/cli.py:100`,
      `factory/activities/agent_activities.py:260` and `:331` (trap 3).
- [ ] T006 [P] [US1] (spec US1-S6) Assert a present-but-unreadable or unparseable override
      **fails naming the path and fault** and does not fall back to package data
      (trap 1).
- [ ] T007 [P] [US1] (spec Edge Cases) Assert an override pointing at a directory is named as
      a distinct fault from an override pointing at nothing.

### Implementation for this story

- [ ] T008 [US1] (FR-001, FR-004) Extend `_resolve_default_registry_path()`
      (`factory/config.py:44`) into a precedence chain: env override, then
      XDG/HOME-relative, then the existing `importlib.resources` branch
      unchanged. Add the relative-path constant beside `REGISTRY_FILENAME`,
      mirroring `DEFAULT_CONFIG_REL` (`factory/controlplane/config.py:53`).
- [ ] T009 [US1] (FR-002) Route every call site through the resolver. Prefer making bare
      `load_personas()` resolve internally over asking five callers to remember
      (trap 3).
- [ ] T010 [US1] (FR-003) Fail loudly on a present-but-broken override.

## Phase 2: User Story 2 — The shipped registry is an example, and install seeds the operator's copy

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1) Assert the packaged registry contains none of the
      `ollama-cloud/`, `local/` or `anthropic/` alias prefixes, no operator name,
      and no dated homelab rationale.
- [ ] T012 [P] [US2] (spec US2-S2) Assert the packaged registry documents the persona shape
      and states that its aliases are placeholders.
- [ ] T013 [P] [US2] (spec US2-S3) Assert `ergane install` writes
      `~/.config/ergane/personas.yaml` when absent, and reports the path.
- [ ] T014 [P] [US2] (spec US2-S4) Assert a re-run does **not** overwrite an existing operator
      registry.
- [ ] T015 [P] [US2] (spec US2-S5) Assert `--verify` against an unedited placeholder registry
      reports one condition naming the registry, not one fault per alias
      (trap 6).
- [ ] T016 [P] [US2] (spec US2-S6) Assert this repository's own registry still resolves for
      this repository (trap 4).
- [ ] T017 [P] [US2] (spec Edge Cases) Assert an unwritable `XDG_CONFIG_HOME` is reported
      rather than causing a write inside the package.

### Implementation for this story

- [ ] T018 [US2] (FR-005, FR-006) Rewrite the packaged registry as a neutral, documented
      example. Keep this repository's real wiring wherever T016 requires it to
      live, and check `pyproject.toml`'s force-include still points at the
      correct source file.
- [ ] T019 [US2] (FR-007) Seed `~/.config/ergane/personas.yaml` from `ergane install`
      when absent; never overwrite; report the path either way.
- [ ] T020 [US2] (FR-008) Rewrite the `--verify` failure so an unconfigured registry is
      one actionable condition.

## Phase 3: User Story 3 — `skills` either works or says it does not

### Tests for this story (write FIRST, must fail)

- [ ] T021 [P] [US3] (spec US3-S1) Either assert declared skills appear in the constructed
      adapter invocation, or assert the field is documented as reserved and the
      three `skills=()` sites are explained. Pick one; do not leave the field
      dead (trap 7).
- [ ] T022 [P] [US3] (spec US3-S2) Assert the registry documentation states both scope facts:
      home-scoped skills invisible (factory-owned HOME,
      `factory/workgraph/adapter.py:339`), project-scoped committed skills
      visible (worktrees carry committed files). **Verify both against the
      adapter before writing them as fact** (trap 8).
- [ ] T023 [P] [US3] (spec US3-S3) Assert the chosen behaviour would fail if it silently
      reverted.

### Implementation for this story

- [ ] T024 [US3] (FR-009) Wire `skills` into the adapter invocation, or mark it reserved
      and unused at `factory/config.py:212` and at the three construction sites.
- [ ] T025 [US3] (FR-010) Document the visible skill scopes in the registry header.

## Verification

- [ ] T026 (SC-001) On a fresh host: `uv tool install ergane-cli`, `ergane install`,
      edit `~/.config/ergane/personas.yaml`, `uv tool upgrade ergane-cli`,
      confirm the edits survive. **Paste the transcript into the diff** (trap 9).
- [ ] T027 (SC-002) Open the packaged registry as a stranger would and confirm it can
      be filled in without reading source.
- [ ] T028 (SC-003) Run `ergane install --verify` against an unedited registry and
      confirm one actionable condition, not five alias faults.
- [ ] T029 (SC-004) Dispatch an epic in this repository after the change and confirm it
      resolves this repository's registry (trap 4).
