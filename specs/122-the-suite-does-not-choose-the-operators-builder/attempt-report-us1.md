# 122-US1 attempt report: the registry test asserts loading, not vendor

The plan asks for a pair of runs, because "a suite that was already green proves
no fix and one green only afterwards proves no regression was avoided". Both are
below, measured in this worktree.

The plan's operator demonstration swaps `personas.yaml` to `agent: subscription`
before running. **That swap was deliberately not made here** — the same plan says
an attempt editing `personas.yaml` has gone outside the spec, and the story is
independent of which model the operator names. So the swap is made *in process*
instead: `tests/test_122_registry_is_not_pinned.py` writes a subscription
registry under its own `tmp_path` and points both seams that name the shipped
file at it, then runs the surviving shipped-registry check against it. That is
the same refusal the operator hit, reproduced without touching their file, and it
is what the red run below is.

## Before — the pin in force (T001–T004 written, T005 not yet applied)

```
$ uv run pytest -q tests/test_122_registry_is_not_pinned.py
E       AssertionError: a subscription implementer was refused: assert '/' in 'claude-opus-5'
E       assert AssertionError("assert '/' in 'claude-opus-5'\n +  where 'claude-opus-5' = Persona(name='implementer', agent='subscrip...nt',), write_scope=<WriteScope.WORKTREE: 'worktree'>, needs_worktree=True, timeout_s=3600, context_window=None).model") is None

>       assert offences == [], offences
E       AssertionError: ["test_us2_shipped_registry.py:344 in test_repo_root_registry_still_resolves_real_wiring_in_checkout: assert '/' in registry['implementer'].model — names ['/'] while reading ['model'] off the operator's registry"]

FAILED tests/test_122_registry_is_not_pinned.py::test_a_subscription_implementer_passes_the_shipped_registry_check
FAILED tests/test_122_registry_is_not_pinned.py::test_no_assertion_about_the_shipped_registry_constrains_a_vendor_or_route
2 failed, 3 passed in 2.83s
```

The control (a gateway-routed implementer) and the resolve check (an implementer
that names no model) are the three that already passed: the pin's removal had to
widen what the check accepts, not swap one accepted shape for another.

## After — T005 applied

```
$ uv run pytest -q tests/test_122_registry_is_not_pinned.py tests/test_us2_shipped_registry.py
............                                                             [100%]
12 passed in 3.78s
```

## The whole gate, on the declared command

```
$ uv run pytest -q
5216 passed, 58 skipped, 8 warnings in 370.34s (0:06:10)
```

## The anti-recurrence guard, proven by mutation

US1-S4 is worth nothing unless it fails when the defect returns, so a seventh
recurrence was written into a *different* module — `tests/test_config.py`, which
reads the shipped registry the other way (`load_personas(SHIPPED_REGISTRY)`) —
and then reverted:

```
$ # added to test_llm_personas_resolve_a_model:
$ #     assert persona.model.startswith("ollama-cloud/")
$ uv run pytest -q tests/test_122_registry_is_not_pinned.py::test_no_assertion_about_the_shipped_registry_constrains_a_vendor_or_route
E       AssertionError: ["test_config.py:108 in test_llm_personas_resolve_a_model: assert persona.model.startswith('ollama-cloud/') — names ['ollama-cloud/'] while reading ['model'] off the operator's registry"]
1 failed in 2.92s
```

The guard names the file, the line, the literal and the field, and it reaches
past the one file this story edits — which is the point, since the last three
recurrences of this defect class each appeared in a different module.

## What this story does not settle

The two remaining pins are US2's (`tests/test_usage_activities.py`) and US3's
(the 089 fixes-layer tests). Until all three land, the operator's own
`personas.yaml` swap still reddens the suite through those files, not through
this one.
