# Tasks: The suite may hold the resolver to the registry, never the registry to a value

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and must
fail before its implementation task runs.

## Format: `[ID] [Story] Description`

---

## Phase 1: User Story 1 — Un-pin the dial (Priority: P1)

- [ ] T001 [US1] Read `factory/config.py:88` (`load_personas` path seam) and
      the current test at `tests/test_agent_activities.py:494` before
      editing. No code yet; the commit is allowed to be empty.
- [ ] T002 [US1] US1-S2 first, failing first: a copy of the shipped registry
      with `implementer.context_window: 262144` added, module run against
      it — red against today's pinned assertion, and the rework that
      follows makes it green.
- [ ] T003 [US1] Rework the pinned test: omitted-→-None on fixture
      registries (US1-S3, two personas), declared-→-verbatim kept (US1-S4),
      live-file literal pin removed.
- [ ] T004 [US1] Full gate (`uv run pytest -q`) green against the shipped
      registry untouched (US1-S1). Confirm the diff contains no path under
      `factory/` and does not touch `personas.yaml`.

---

## Verification

- [ ] Final gate command passes green; diff is tests-only.
