# Tasks: one operator contract serves both clients

Write each story test first. Do not change a spec state, dispatch, configure a
client, or grant trust while implementing these stories.

## Phase 1: User Story 1 — One canonical orientation has two verified entry points

- [ ] [US1-S1] Add failing canonical-content and compatibility tests in `tests/test_operator_instructions.py`, covering the node guard, authority map, action boundary, tracked file type, and byte-equivalent resolved content.
- [ ] [US1-S2] Add failing discovery-artifact parser tests and a redacted six-context fixture under `tests/fixtures/operator-instructions/`; prove root, nested, and worktree observations for Codex and Claude without credentials or absolute home paths.
- [ ] [US1-S3] Add failing semantic tests that reject action-granting language in an observation-only section.
- [ ] [US1] Move the maintained orientation into `AGENTS.md`, implement the verified `CLAUDE.md` compatibility entry point, and update `tests/test_claude_md.py` to consume the canonical source without weakening its command/path/status guards.
- [ ] [US1] Run the focused tests and commit their concise transcript as the story's diff-visible qualification evidence.

## Phase 2: User Story 2 — The operator workflow names Ergane's authorities and degraded capabilities

- [ ] [US2-S1] Add failing lifecycle/authority contract tests for `docs/agents/workflow.md` in `tests/test_agent_workflow_docs.py`.
- [ ] [US2-S2] Add a table-driven failing test for every shared-intent and absent-binding row required in `docs/agents/capabilities.md`.
- [ ] [US2-S3] Add a failing local-authority test that refuses Beads, generic issue publication, mandatory push, or checkout cleanup as Ergane defaults.
- [ ] [US2] Write `docs/agents/workflow.md` and `docs/agents/capabilities.md`, linking the canonical vocabulary and immutable decision process.
- [ ] [US2] Prove the document tests pass without opening a runtime store or contacting Temporal, GitHub, memory, or a notification service.

## Verification

- [ ] Run all focused instruction/workflow tests, then the declared repository gate; confirm the deferred governance proposal is not applied.
- [ ] Run `git diff --check` and confirm no runtime store, registry, credential, service, or spec state changed.
