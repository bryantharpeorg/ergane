# Tasks: a stranger runs the factory in one command

**Spec**: `specs/109-a-stranger-runs-the-factory-in-one-command/spec.md`
**Plan**: `specs/109-a-stranger-runs-the-factory-in-one-command/plan.md` — read
its **Traps** section before writing anything. T1, T2 and T8 each describe
something that looks like a bug and is not; each will cost an attempt if
discovered rather than read.

`[P]` marks a task that may run in parallel with its siblings — different file,
no ordering dependency. Every task cites the spec scenario and the FR numbers it
discharges, so the judge can check it against criteria provable from the diff.

Tests are written **first and must fail** before the implementation task in the
same phase.

---

## Phase 1: User Story 1 — The gateway has a bundled half

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001) Interview test: the install interview asks
  `gateway mode (external|managed)` and accepts both answers. Model the test on
  whatever covers `_ask_temporal` (`factory/cli/install.py:1764`) so the two
  questions are exercised the same way. Red now — the question does not exist.

- [ ] T002 [P] [US1] (spec US1-S2, FR-002, FR-006) Regression guard, in two
  halves. First: with `mode = "external"`, the written config is byte-identical
  to what today's interview produces for the same answers. Second: assert
  `verify.py:415`'s invariant survives — `gateway` is still the only mode a
  parsed `llm` config can carry. This story adds a mode to the **gateway**, not a
  third `llm.mode`. See plan FR-006.

- [ ] T003 [P] [US1] (spec US1-S3, FR-003, FR-004) Non-interactive test: an
  answers file selecting `managed` is accepted by `_install_from_file`
  (`install.py:1221`) and the written config records the bundled address and that
  the project owns the lifecycle. Also assert the new key appears in
  `docs/ergane-install-answer.example.toml`, which is the documented shape a
  reader copies.

- [ ] T004 [P] [US1] (spec US1-S4, FR-005) Probe-parity test: the
  key-management capability probe (`verify.py:453-511`) runs for **both** modes
  — mint, model-constrain, read spend logs, revoke. Write it so it fails if a
  managed gateway takes any shortcut through verification. This is the test that
  stops "it is ours, so it is fine" from becoming code.

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-002, FR-003) Add the gateway mode question and its
  config field, turning T001–T003 green. Mirror `_ask_temporal`'s shape.
  **Plan trap T4: do not copy its systemd guard** (`install.py:1775-1781`) — that
  refusal exists because the native tier supervises Temporal through systemd, and
  the gateway's managed mode is a compose service with no host dependency.
  Copying it would refuse the demo on exactly the machines it is for.

- [ ] T006 [US1] (FR-004) Extend `_install_from_file` and
  `docs/ergane-install-answer.example.toml` with the new key. Turns T003 green.

### Verification for this story

- [ ] T007 [US1] (spec US1-S1, spec US1-S4, SC-001) Paste the interview
  transcript for **both** modes, and the full LLM verification suite passing —
  with before-and-after counts, so FR-002's "unmodified" is checkable rather than
  asserted.

---

## Phase 2: User Story 2 — The demo project exists and is one file

### Tests for this story (write FIRST, must fail)

- [ ] T008 [US2] (spec US2-S1, FR-007) Drift test over
  `container/compose.demo.yaml`: exactly three services — engine, gateway,
  Postgres — and the engine's image reference derives from the same version
  source `container/compose.reference.yaml:10` uses. Red now; the file does not
  exist.

- [ ] T009 [P] [US2] (spec US2-S2, FR-008) The inverse-invariant test. Assert
  every volume is a **named volume** and **no** mount pair is same-path.
  **The failure message must carry the reason** — that `_check_paths`
  (`container_project.py:318-329`) demands same-path for the *operational*
  project because a host CLI shares git worktrees with the container, and the
  demo has no host side. Read plan trap T1 first: you are deliberately writing
  what the generator would refuse, and a future reader who has seen
  `container_project.py:326` will otherwise "fix" it.

- [ ] T010 [P] [US2] (spec US2-S3, FR-009) Mandatory-variable count test.
  **Enumerate** the variables the file requires without a default and assert the
  count is exactly one, rather than checking that one known name is present. Plan
  trap T5: the first form catches the second variable somebody adds later; the
  second form does not.

- [ ] T011 [P] [US2] (spec US2-S4, FR-010) Registry test: the bundled demo
  registry's aliases carry **no** `example/` prefix
  (`factory/config.py:57 EXAMPLE_ALIAS_PREFIXES`), and the shipped refusal at
  `verify.py:441` is untouched. **Plan trap T2**: assert the refusal still exists
  and still fires for an all-`example/` registry. The demo satisfies that check;
  it does not disable it.

- [ ] T012 [P] [US2] (spec US2-S5, FR-011) Header test: the file opens with a
  comment stating it is a demonstration with volume-local state, that it does not
  land, and that `ergane install --engine=container` generates the operational
  project instead. Model the assertion on how 108/FR-010 pins the credential
  comment in `test-release.yml`.

### Implementation for this story

- [ ] T013 [US2] (FR-007, FR-008, FR-009, FR-011) Write
  `container/compose.demo.yaml`, turning T008–T010 and T012 green. Three
  services, named volumes throughout, one mandatory environment variable, the
  header comment. **Plan trap T6**: the Postgres password is a baked default for
  a demo database reachable only on the compose network — put a comment on the
  line saying so, or the next audit files it as a leak and the next agent
  "fixes" it into a required variable, breaking FR-009.

- [ ] T014 [US2] (FR-010) Add the bundled answers file and the demo persona
  registry, turning T011 green. Aliases must match what the bundled gateway's
  model config actually serves — a registry naming an alias the gateway does not
  serve fails FR-005's probe three stages later wearing a different error.

### Verification for this story

- [ ] T015 [US2] (spec US2-S4, SC-002) Paste the project coming up and
  `ergane install --verify` passing **inside it**, with the key-management probe
  visible in the output — mint, constrain, spend logs, revoke. A green summary
  line is not enough; the probe's own evidence is what proves the demo gateway is
  held to the same standard as an operator's.

---

## Phase 3: User Story 3 — The epic halts at PASSED

### Tests for this story (write FIRST, must fail)

- [ ] T016 [US3] (spec US3-S1, FR-012) Terminal-state test: in the halting mode,
  a node that passes its gate and judge ends at `PASSED`
  (`factory/workgraph/models.py:114`) and the landing phase never begins.

- [ ] T017 [P] [US3] (spec US3-S1, FR-013) The forge spy. Inject a `Forge`
  double (`factory/mergequeue/forge.py:178`, eight methods) whose **every method
  raises**, and assert the run completes. **Plan trap T7**: a double returning
  sentinel values lets a call through and still passes. The assertion is that the
  run finished, which is only possible if nothing called it.

- [ ] T018 [P] [US3] (spec US3-S2, FR-014) Output test: the run states that
  landing was **not attempted** and what would be required to land. Assert the
  wording distinguishes it from a failed landing — a reader who has only ever
  seen runs that land will assume failure otherwise.

- [ ] T019 [P] [US3] (spec US3-S3, spec US3-S4, FR-015, FR-016) Two guards. With
  the mode **off**, behaviour runs through `MERGED` as today. With the mode
  **on** and a node failing its gate or judge, failure reports exactly as today.
  The mode changes where success stops, never what failure means.

### Implementation for this story

- [ ] T020 [US3] (FR-012, FR-013, FR-014) Add the halting mode, turning
  T016–T018 green. The seam already exists: `models.py:78` documents
  `… → VERIFYING → PASSED → PR_OPEN → ENQUEUED → MERGED` and `:86-87` records
  that `PR_OPEN`/`ENQUEUED` are the landing phase's states. Make `PASSED`
  terminal in this mode and say so in the output. **Plan trap T8: do not
  implement a forge.** If the work seems to need one, the reading is wrong — the
  operator ruled explicitly that the demo does not land.

### Verification for this story

- [ ] T021 [US3] (spec US3-S1, spec US3-S2, spec US3-S3, SC-003) Paste a
  halting-mode run reaching `PASSED` with the landing statement **quoted
  verbatim**, and the existing workgraph suite passing unmodified with
  before-and-after counts.

---

## Phase 4: User Story 4 — The file has a URL

### Tests for this story (write FIRST, must fail)

- [ ] T022 [US4] (spec US4-S1, FR-017) Ordering test over
  `.github/workflows/release.yml`: a step publishes
  `container/compose.demo.yaml` as a release asset, and it is ordered **after**
  the image job (`:98-99`). A compose file naming an image that does not exist
  yet is failure mode 13 in a new costume.

- [ ] T023 [P] [US4] (spec US4-S2, FR-018) Tag-agreement test: the workflow
  contains a step that reads the published file's engine image tag, compares it
  to the tag being released, and exits non-zero on mismatch. Assert the check is
  **in the workflow**, not a human procedure. The image job already models this
  shape — it reads its own manifest back rather than trusting the push.

- [ ] T024 [P] [US4] (spec US4-S3, FR-019) Regression guard: the preflight
  ordering (`release.yml:21`, `:42-43`), `build-and-publish-image`'s `needs:`
  (`:98-99`), and 108's package linkage and visibility assertions all still hold.

### Implementation for this story

- [ ] T025 [US4] (FR-017, FR-018) Add the publish step and the tag-agreement
  assertion, turning T022–T023 green. Do not reorder or re-parent any existing
  job (FR-019).

### Verification for this story

- [ ] T026 [US4] (spec US4-S3, SC-004) Paste the full
  `tests/test_release_path.py` run with before-and-after counts, showing every
  test 105 and 108 landed still passing. The count may only go up.

---

## What no task here can prove

Every task above is checkable from the diff, which is the constitution's
requirement and the judge's only input. **None of them proves the thing the spec
is for**, which is a stranger's first five minutes.

The operator verification in `plan.md` is the acceptance test, and it runs after
this epic lands, **on a machine that has never had Ergane installed**:

```bash
export UPSTREAM_MODEL_API_KEY=…
curl -fsSL https://github.com/bryantharpeorg/ergane/releases/latest/download/compose.yaml \
  | docker compose -f - up
```

Run it on the x86 rig rather than the factory host. The factory host has a
config, a registry, a state root and a running worker, and any one of them can
make a broken demo look like a working one.
