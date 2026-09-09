# Tasks: a scaffolded repo arrives with the context its agents need

Write every story's tests first. Do not start a client, grant trust, use a trust
bypass, or modify a real target repository during implementation.

## Phase 1: User Story 1 — The target-context unit is one declared package

- [ ] [US1-S1] Add a failing resolver test for the exact canonical skill, Claude compatibility entry point, Claude settings, Codex hooks, version, bytes, and digests.
- [ ] [US1-S2] Add a failing payload allowlist test rejecting `.py`, executables, credentials, host paths, `AGENTS.md`, and `CLAUDE.md`.
- [ ] [US1-S3] Add failing semantic tests for derivation, supported-tool scope, node exemption, trust state, unreadable behavior, visible escape, and defense-in-depth wording.
- [ ] [US1] Implement the typed package/resource resolver and the client-neutral target-safety context; keep the checker in the installed Python package.

## Phase 2: User Story 2 — Init owns only bytes it previously installed

- [ ] [US2-S1] Add a failing scratch-repository first-install test that asserts every relative path, digest, report row, and exact staging argument.
- [ ] [US2-S2] Add a failing clean-owned upgrade fixture.
- [ ] [US2-S3] Add failing modified-owned and pre-existing-unowned collision fixtures proving byte preservation, ownership disclaimer, and independent sibling updates.
- [ ] [US2-S4] Add a failing effective-ignore fixture that identifies each hidden owned path without changing `.gitignore`.
- [ ] [US2] Install the unit from `factory/cli/init.py:1134` — `init_command` using absent, clean-owned, and collision states and an atomic versioned record.
- [ ] [US2] Build reporting and staging guidance from exact owned paths and `git check-ignore`, never a whole `.claude` or `.codex` directory.

## Phase 3: User Story 3 — Protected paths come from the target manifest and stack pack

- [ ] [US3-S1] Add failing Python-pack tests for existing `src`/`tests`, absent roots, root exclusion, and origin attribution.
- [ ] [US3-S2] Add a failing ordered-token test for `npm --prefix web run build`.
- [ ] [US3-S3] Add a failing no-guess empty-result test.
- [ ] [US3-S4] Add a failing repeat-run transcript/status test for `ergane repo gate-paths`.
- [ ] [US3] Add validated optional source roots at `factory/stack_packs.py:50` — `StackPack` and `factory/stack_packs.py:141` — `_pack_from_data`.
- [ ] [US3] Implement client-neutral derivation from `factory/verify/models.py:291` — `FactoryConfig`, ordered gate tokens, existing roots, and origin metadata.
- [ ] [US3] Add the deterministic read-only listing through `factory/cli/repo.py:105` — `add_repo_parser`.

## Phase 4: User Story 5 — One installed checker normalizes paths and decodes Claude events

- [ ] [US5-S1] Commit exact redacted Claude `Write` and `Edit` fixtures and add failing protected/unprotected decode tests.
- [ ] [US5-S2] Add failing canonicalization tables for absolute in-repository paths, `./`, resolving `..`, repeated separators, spaces/quoting, and existing symlink aliases; ambiguous, unresolved, escaping, and outside-root inputs report not enforced.
- [ ] [US5-S3] Add failing default-root and relocated-root node-exemption tests over home, worktree, and branch shapes.
- [ ] [US5-S4] Add a failing matrix for unreadable manifest, malformed Claude payload, unknown event/tool, unavailable verb, and ordinary parser status.
- [ ] [US5-S5] Add failing visible-escape tests and a child-environment assertion proving the escape is not propagated.
- [ ] [US5] Implement repository-root-relative canonicalization and the Claude fixture decoder in the installed package.
- [ ] [US5] Implement one pure decision boundary returning typed allow, refuse, or not-enforced results with a dedicated refusal distinct from CLI statuses.
- [ ] [US5] Expose the checker through the installed `ergane repo gate-paths` CLI without adding executable repository payloads.

## Phase 5: User Story 6 — A Codex patch decision checks every canonical target

- [ ] [US6-S1] Commit exact redacted Codex `apply_patch` fixtures and add failing tests for every Add, Update, Delete, source, and Move-to destination header.
- [ ] [US6-S2] Add failing cross-client canonicalization tables for every US5 spelling and loud whole-patch not-enforced behavior on ambiguous/unresolved/escaping targets.
- [ ] [US6-S3] Add failing mixed protected/unprotected, source/destination, and target-order tests proving any covered path refuses the whole recognized patch.
- [ ] [US6-S4] Add failing prefix-valid/suffix-invalid and unknown-header controls proving no partial target set is enforced.
- [ ] [US6] Implement complete Codex patch-target parsing and feed all targets through US5's canonicalizer and pure decision boundary.

## Phase 6: User Story 4 — Installation reports trust and proves active enforcement

- [ ] [US4-S1] Add failing report-model tests for `installed`, `preserved collision`, `trust required`, and `verified active enforcement` per client.
- [ ] [US4-S2] Add failing Claude wrapper-composition tests proving only the dedicated refusal blocks and an ordinary parser failure reports not enforced.
- [ ] [US4-S3] Add a failing Codex binding test against the official hook event/response fixture, including redacted `permissionDecisionReason`, and exact definition digest.
- [ ] [US4-S4] Add a failing invocation-boundary test proving init cannot grant trust, start clients, or invoke `--dangerously-bypass-hook-trust` or an equivalent.
- [ ] [US4-S5] Add failing evidence parser tests for client versions, trusted definition hash, one allow, one refusal, target classification, and redaction for both clients.
- [ ] [US4-S6] Add failing negative capability rows for shell, MCP, unsupported tools, disabled hooks, and untrusted definitions.
- [ ] [US4-S7] Add failing transitions that invalidate verified enforcement after client-version, hook-byte/hash, trust, or enabled-state drift.
- [ ] [US4] Install the two bindings collision-safely, translate the typed result into each official response, and report trust without changing it.
- [ ] [US4] After separate operator authorization, qualify fresh supported clients only in disposable repositories and commit the minimal redacted evidence.

## Verification

- [ ] Run all focused package, init, derivation, decoder, checker, wrapper, trust-state, and evidence tests, then the declared repository gate.
- [ ] Inspect payload/evidence for secret or absolute-host leakage and run `git diff --check`.
