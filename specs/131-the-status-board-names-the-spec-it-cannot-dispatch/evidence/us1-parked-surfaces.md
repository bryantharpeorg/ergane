# 131-US1 evidence — both parked surfaces name the refusal

The fixture is the story's required pair: one `onboarding` park and one
`derive` park with the empty-delta detail. The same recorded fields drive all
three surfaces; only the blocks required by T009 are printed here.

```text
ergane status specs
schedule: schedule-roadmap-specs (unknown)
schedule: none found
run: roadmap-specs
next tick: 2026-09-04T12:00:00+00:00
dispatch: running
running: -
parked: 2
  077-onboarding — check: onboarding
    the target repository refused onboarding
  078-empty-delta — check: derive
    delta is empty: all stories are satisfied
```

```text
ergane status specs --json (roadmap.parked)
{
  "parked": [
    {
      "spec_dir": "077-onboarding",
      "check": "onboarding",
      "detail": "the target repository refused onboarding"
    },
    {
      "spec_dir": "078-empty-delta",
      "check": "derive",
      "detail": "delta is empty: all stories are satisfied"
    }
  ]
}
```

```text
ergane roadmap status specs (parked block)
dispatch: running
concurrency: 1 epic(s), 1 node(s)
running: -
parked: 2
  077-onboarding — check: onboarding
    the target repository refused onboarding
  078-empty-delta — check: derive
    delta is empty: all stories are satisfied
```

The no-parked control keeps `parked: 0` on the human block and emits
`roadmap.parked: []` in JSON. The declared gate was green after the fixture
and implementation:

```text
$ uv run pytest -q
5987 passed, 58 skipped, 15 warnings in 600.77s (0:10:00)
```
