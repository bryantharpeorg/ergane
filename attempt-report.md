# Attempt 1 — US1: The live manifest is checked for validity, not for content

## What changed

Three committed files and one edited one:

- `tests/test_121_manifest_is_not_a_fixture.py` (new) — the story's six
  scenario tests (T001–T006), written first and committed failing where the
  pins still stood.
- `tests/fixtures/target_repo/manifests/v1-sample.yaml` (new, T007) — the v1
  sample whose committed bytes are now the frozen thing, named for the one
  condition it demonstrates as its eleven neighbours are.
- `tests/fixtures/target_repo/docs/v1-sample-standards.md` (new, T007) — the
  document the sample's `standards:` path resolves to.
- `tests/test_factory_yaml.py` (edited) — T008 and T009:
  `test_v1_identity_against_erganes_own_manifest` repointed onto the sample and
  renamed for what it does (`test_v1_identity_against_the_committed_sample`),
  its whole-`FactoryConfig` comparison untouched (FR-007); the `assert
  config.version == 1` removed from `test_erganes_own_manifest_loads`, with the
  load kept (trap 1) and the `gates` / `standards` / `landing_branch`
  assertions untouched (trap 6).

## How the scenarios are covered

- **US1-S1** — two tests drive a copy of the operator's manifest with a legal
  v2 `ladder:` block appended and version 2: it parses, the declared dials come
  back (`max_attempts: 2`, `promotion_persona: opus-closer`,
  `promotion_cycles: 1`), and the copy is valid end to end.
- **US1-S2** — a source-reading guard refuses any `version` comparison in a
  test that loads `REPO_ROOT / MANIFEST_NAME`, located structurally so a new
  or renamed live-manifest test is covered by having been written.
- **US1-S3** — the control, in two halves: the production seam
  (`prepare_worktree` → `_require_standards`) refuses a dispatch whose declared
  standards document is absent, naming the file and the manifest, and a
  source-reading guard requires the live load in
  `test_erganes_declared_standards_document_exists` to survive (trap 1).
- **US1-S4** — three guards: the sample is v1 (v2 keys absent from its parsed
  document, defaults read back as v1's); v1 semantics are frozen field for
  field against it here as well as in the sibling module; and the sibling
  module's identity test reads the sample rather than the operator's file,
  still whole-config (FR-007).
- **US1-S5** — the FR-011 invariant, held by
  `_worktree_manifest_is_untouched` in this module: a node worktree whose
  manifest differs from the landing branch's copy at its branch point is
  refused, naming `ergane.yaml` — proven dirty and (the D-051-relevant shape)
  committed, with the untouched worktree as the control and the invariant
  applied to this repository's own checkout so a node editing `ergane.yaml`
  here reds its own gate. A linked worktree is compared; the landing branch's
  own checkout has no node and is vacuously satisfied. FR-011 is not weakened:
  the operator's file is still not free for a node to edit, and this
  repository still cannot have its manifest pinned — only the *enforcement
  shape* moved from frozen literals to a validity property.
- **US1-S6** — the anti-recurrence guard: every `assert` line in every
  live-manifest test is classified, and only three shapes survive — documented
  operator facts (`ergane-buildout`, the standards path, the declared gate
  command), truthiness/shape checks (including the standards control's
  `is_file()` on a manifest-derived path), and `is None` / `is not None`.
  `FactoryConfig(`-shaped and any `*Config(`-constructed comparisons are
  refused by shape before any literal lookup. Proven by mutation in both
  directions: reintroducing `assert config.version == 1` fails both S2 and S6
  naming the line; reintroducing `assert config.ladder is VerificationConfig()`
  fails S6.

## The demonstration (T011), both runs

Before, on this branch, with `ergane.yaml` untouched:

```
$ uv run pytest -q tests/test_factory_yaml.py tests/test_forge_manifest.py
186 passed in 0.91s
```

After declaring the ladder (the plan's step 2 script: `version: 2` plus
`ladder: {max_attempts: 2, promotion_cycles: 1, promotion_persona:
opus-closer}`):

```
$ uv run pytest -q tests/test_factory_yaml.py tests/test_forge_manifest.py
186 passed in 0.33s
```

And the parsed ladder is what was declared (plan step 4):

```
$ python3 -c "...print(l.max_attempts, l.promotion_persona, l.promotion_cycles)"
2 opus-closer 1
```

`ergane.yaml` was restored (`git checkout ergane.yaml`) — the file is as it
was found, and the diff contains no change to it.

The red run the plan predicted was reproduced on the pre-121 tree (commit
`aef5257`, the tree the plan's anchors were read at) with the same manifest
change, so the pair is honest evidence and not a suite that was already
green:

```
$ uv run pytest -q tests/test_factory_yaml.py::test_erganes_own_manifest_loads \
    tests/test_factory_yaml.py::test_v1_identity_against_erganes_own_manifest
E       AssertionError: assert 2 == 1
E       AssertionError: assert FactoryConfig(...)... == FactoryConfig(...)
E       Differing attributes: ['version', 'ladder']
2 failed in 0.22s
```

## The one surprise the full gate caught

The scoped runs (my module, the sibling module, the forge suite) were green
before the sample's standards document had even been placed at
`docs/STANDARDS.md` — but the full `uv run pytest -q` was not: two
pre-existing tests (`test_agent_activities`' loud-failure test and the
workgraph failure sweep) use `docs/STANDARDS.md` as the path the fixture repo
*does not* commit — the absent half of R11's existence check. Shipping the
sample's document there silenced both refusals; the failure presented as
`DID NOT RAISE ApplicationError` in tests this story never touched. The
sample's document moved to `docs/v1-sample-standards.md`, which resolves for
the identity comparison and collides with nothing. Bisected to the T007
commit with scratch worktrees and fixed in d893e91; nothing outside the
fixture and my own module was edited to fix it.

## Gate result

`uv run pytest -q` — **5169 passed, 58 skipped, 0 failed** (6m).

Scoped runs on the final tree:
`tests/test_121_manifest_is_not_a_fixture.py` 14 passed;
`tests/test_factory_yaml.py` + `tests/test_forge_manifest.py` 186 passed with
the ladder declared and 186 passed with the operator's file untouched
(evidence pair above).

## Traps, accounted

1. Live-manifest load kept — `test_erganes_declared_standards_document_exists`
   untouched; its survival asserted in source by
   `test_the_live_manifest_load_survives`.
2. Both sites moved — the version assertion and the `ladder` pin are each
   gone, and US1-S1's ladder-parses test is the proof.
3. Coverage preserved — the identity test exists and still compares the whole
   `FactoryConfig`, against the sample.
4. The sample is v1 — `test_the_v1_sample_is_a_v1_manifest` refuses `ladder:`
   and `verify:` in its parsed document and pins its read-back defaults.
5. The sample joined both corpus globs (forge: 13 files, sweep: 13) and both
   suites pass; the sample carries no judge-reaching command (084/FR-009).
6. Gates/standards/landing_branch assertions untouched — asserted by the S6
   allow-list rather than deleted.
7. S6 is written and mutation-proven, not skipped as over-engineering.

## Not done, and not in scope

`ergane.yaml` is unchanged; the manifest schema is unchanged; `personas.yaml`
is untouched (the registry half of the finding is a separate surface). No
production code was modified — the FR-011 check in US1-S5 lives in the test
module's helper, called against this repository's own checkout by a committed
test, which is where the plan put the story.