# Tasks: 037-operator-dial-tests

The implementer works its slice test-first and commits once per task.

## Implementation

- [ ] T001 Read `factory/config.py:88` (`load_personas` path seam) and the
      current test at `tests/test_agent_activities.py:494` before editing.
      No code yet; the commit is allowed to be empty.
- [ ] T002 US1-S2 first, failing first: a copy of the shipped registry with
      `implementer.context_window: 262144` added, module run against it — red
      against today's pinned assertion, and the rework that follows makes it
      green.
- [ ] T003 Rework the pinned test: omitted-→-None on fixture registries
      (US1-S3, two personas), declared-→-verbatim kept (US1-S4), live-file
      literal pin removed.
- [ ] T004 Full gate (`uv run pytest -q`) green against the shipped registry
      untouched (US1-S1). Confirm the diff contains no path under `factory/`
      and does not touch `personas.yaml`.

## Verification

- [ ] Final gate command passes green; diff is tests-only.
