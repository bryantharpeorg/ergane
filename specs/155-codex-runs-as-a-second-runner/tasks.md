# Tasks: Codex runs as a second runner

Derived from `plan.md`. Tests precede implementation (constitution). The CLI
probe task (T004) produces the measured facts the refusal and subscription
stories must not assume, and is a hard dependency of Phase 3.

## Phase 1 — Setup and premise check

- [ ] T001 Confirm spec 154 has landed (`ergane spec landed
  specs/154-an-agent-names-its-cli-and-its-route-separately --default-branch
  ergane-buildout` — pass the buildout branch, not the default). This spec
  builds on its seam and must not dispatch against a tree without it.
- [ ] T002 Re-read every `file:line` anchor in `plan.md` against the current
  tree and amend the plan for any that moved.

## Phase 2: User Story 1 — A Codex node runs on the gateway, driving an ollama-cloud alias

### Tests for this story (write FIRST, must fail)

- [ ] T003 [P] [US1] (spec US1-S1, US1-S2, US1-S3, FR-001, FR-002, FR-004)
  Write the failing tests: a persona with `agent: codex` / `route: gateway`
  launches `codex exec -` with the prompt on stdin (US1-S1); spend reads from
  the proxy on the attempt's virtual key (US1-S2); the generated `config.toml`
  carries the gateway provider and key (US1-S3).

### Probe for this story (produces measured facts; floor untouched)

- [ ] T004 [US1] (traps 2, 3, 4) Install the verified artifact
  (`@openai/codex@0.153.4`; `npm i -g @openai/codex@0.153.4` — one `codex` bin
  via `bin/codex.js`, Node >=16, platform binaries via `optionalDependencies`:
  linux/win32/darwin x x64/arm64; npm registry, 2026-09-06) to a scratch prefix;
  run `codex exec` with no credential and record refusal text/stream/exit;
  record where `codex login` writes `auth.json` and whether it rotates; capture
  `thread.started` for session identity. Write the results into this plan as
  measured traps replacing 2, 3, 4.

### Implementation for this story

- [ ] T005 [US1] (FR-001) Implement `CodexAdapter` and register it in
  `_ADAPTERS` (`factory/workgraph/adapter.py:1512`) as `codex`; implement the
  per-CLI surface (argv, prompt delivery, provider env, home seeding,
  credential discovery, turn-happened probe, refusal markers), inheriting the
  shared policy 154 hoisted.
- [ ] T006 [US1] (FR-003, trap 6) Write the generated-`config.toml` seeding and
  add only the needed env names to the standing boundary's env contract
  (`factory/workgraph/adapter.py:596-618` under bwrap today).
- [ ] T007 [US1] (spec US1-S4, FR-007, trap 1) Handle cleartext reasoning CoT:
  the turn probe and output scans match against the message/output channel, not
  reasoning blocks.

### Verification for this story

- [ ] T008 [US1] (US1-S1/S2/S3) Verify: tests pass; full `uv run pytest -q`
  green.

## Phase 3: User Story 2 — A Codex refusal is classified, not read as a silent success

### Tests for this story (write FIRST, must fail)

- [ ] T009 [P] [US2] (spec US2-S1, US2-S2, FR-005) Write the failing tests: a
  Codex auth failure is classified as a refusal from the measured text
  (US2-S1); the committed test replays the measured refusal string both ways
  (US2-S2); reasoning text neither satisfies nor defeats detection (US2-S3).

### Implementation for this story

- [ ] T010 [US2] (FR-005) Add the measured Codex refusal marker wired into the
  same classification path as `SUBSCRIPTION_REFUSAL_MARKER`
  (`factory/workgraph/adapter.py:193`), so a refused run is named a refusal,
  never a silent diffless success.

### Verification for this story

- [ ] T011 [US2] (US2-S2) Verify: the classifier test passes; a refused run is
  never a silent success; full `uv run pytest -q` green.

## Phase 4: User Story 3 — A Codex node runs on a ChatGPT subscription

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US3] (spec US3-S1, US3-S2, US3-S3, FR-006) Write the failing
  tests: a `route: subscription` Codex persona mints no virtual key (US3-S1),
  records a `credential_source` naming the discovered file (US3-S2), and names
  the rotation hazard as inherited and unmeasured (US3-S3).

### Implementation for this story

- [ ] T013 [US3] (FR-006, trap 3) Implement the Codex credential discovery (the
  analogue of `discover_subscription_credential`,
  `factory/workgraph/adapter.py:840`) and the subscription seeding path from
  the measured `auth.json`.

### Verification for this story

- [ ] T014 [US3] (US3-S1/S2) Verify: tests pass; full `uv run pytest -q` green.

## Phase 5: User Story 4 — The toolchain and image carry the Codex binary, confined by the standing boundary

### Tests for this story (write FIRST, must fail)

- [ ] T015 [P] [US4] (spec US4-S1, FR-008) Write the failing check: on a host
  with the toolchain applied, `codex` resolves on the node's PATH.

### Implementation for this story

- [ ] T016 [US4] (FR-008, trap 6) Add `codex` (the `@openai/codex` npm package,
  pin `0.153.4`) to the toolchain
  (`factory/verify/toolchain.py:122` region) and the image (`Dockerfile`);
  launch under the standing boundary with Codex's own read-only default
  disabled when an outer boundary confines the node (US4-S2); record the
  bwrap-nesting question as an OPEN hazard tied to the operator's
  sandbox-boundary decision (US4-S3) — do not harden the bwrap seam beyond what
  the launch requires.

### Verification for this story

- [ ] T017 [US4] (US4-S1/S2) Verify: on a host with the toolchain applied,
  Codex launches and writes its worktree; full `uv run pytest -q` green.

## Verification

- [ ] T018 Dispatch a single-story spec on a Codex persona through the gateway
  and land it; read the landed diff and the ledger row as evidence. A green
  suite and a PASS verdict are evidence, not proof.
- [ ] T019 Confirm the adapter conformance suite sweeps `_ADAPTERS` and would
  notice Codex breaking the seam; full `uv run pytest -q` green.
