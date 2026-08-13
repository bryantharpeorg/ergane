# Plan: 037-operator-dial-tests

Scaffolded from `ci/test-suite-pins-the-operator-dial` (critical); refined
2026-08-13 against the tree at 8bdb425.

## Where the work is

One file: `tests/test_agent_activities.py`. The offending assertion is
`assert item.context_window is None` (~:515) inside
`test_context_window_is_resolved_onto_the_node_and_none_when_omitted`, which
reads `load_personas()` with no argument — the live shipped registry. The same
test's declared-window half already uses a hand-built `Persona` and
`_resolve_node` directly; that half is the pattern to extend, not replace.

## Traps

1. **This story's diff is tests-only by declared scope (FR-004).** The judge
   holds it to that: a diff touching `factory/` or `personas.yaml` fails the
   story, and no production change is needed — `load_personas` already takes
   `path: Path | str | None` (factory/config.py:88), so the fixture seam
   exists. Do not add parameters, flags, or env vars to production code.
2. **Scenario 2's registry copy must be a copy of the *shipped* file with one
   line added** — not a hand-written minimal registry. The point is proving
   the real file plus the dial stays green, so build it in-test from the real
   file's text (`tmp_path`, one YAML edit).
3. **`resolve_graph` reads the shipped registry internally** (that is why the
   original test pinned it). For scenario 3, either resolve through a seam the
   activity exposes for the registry path, or follow the existing pattern:
   drive `_resolve_node` with fixture `Persona` objects for both personas. Do
   not weaken scenario 3 into a single-persona check — the original test used
   two personas to prove per-persona resolution, keep that property.
4. **Do not touch other tests that read the live registry relationally** —
   e.g. `test_a_per_story_timeout_override_wins_over_the_registry` compares
   *against* the registry value without demanding what it is. Relational reads
   are the correct pattern; only the literal pin is the defect.
5. **The failure mode this guards against recurs anywhere a test asserts a
   literal against `load_personas()` output.** Scan the one module being
   touched for other literal pins while in there (timeout, model, fallback);
   fix them the same way *only if they exist in this module* — the scope fence
   is `tests/test_agent_activities.py`, nothing wider.

## Post-landing operator steps (not the implementer's)

- Re-set `implementer.context_window: 262144` in personas.yaml (the parked
  comment names this spec's finding; delete the parking comment, keep the
  provenance line).
- No worker restart needed for a tests-only landing, but the next dispatch
  after the dial is set gets the full window — verify with the attempt's
  stdout.log (the 200k warning disappears).
