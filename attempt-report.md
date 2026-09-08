# 133-US9 attempt report: the verb renders the composition, and its output is unchanged

## What changed

Five commits, tests first (69ce7e7 red, then the implementations):

- `tests/test_133_us9_the_verb_renders_the_composition.py` (T035–T038, T052,
  T053) — ten tests committed observed-red: goldens on both streams over both
  trios with exit codes pinned; `--json` byte for byte, `judge_evidence`
  absent-not-null asserted against the goldens and against the serialiser; the
  CLI module's five finding constructions absent from source and AST; the
  demonstration stage on the library form printing the verb's rendering; the
  control on the controls (T052); the import-backs retired (T053).
- `factory/spec/composition.py` (T040) — `serialise_report` beside
  `validate_spec`: the `--json` document from the typed report in the verb's
  key order, `judge_evidence` appended only when returned, absent rather than
  null otherwise (trap 21). No `dataclasses.asdict()`.
- `factory/cli/nouns/spec.py` (T040) — `_validate_command` reduced from the
  261-line composition to a renderer: argv in, `SpecReadError` translated at
  the boundary that owns it, `_render_validation` printing every line on the
  stream it printed on before (trap 19), `fail` mapped to `EXIT_USER`.
  Import-backs retired with the call sites (FR-015); `_scan_sentinels_in_trio`
  stays for `_derive_command`'s sentinel gate.
- `factory/cli/install.py` (T041) — `_demonstrate_validate` replaces the argv
  round-trip: the stage validates through `validate_spec` and prints through
  `_render_validation` (trap 14 — the streaming was the point, the argv was
  not). `_spec_validate_argv` deleted; `test_110` T003 follows the seam.
- `tests/test_089_validate_checks_fixes.py`,
  `tests/test_102_unprovable_criteria.py` (T054) — both corpus-control helpers
  rebind `factory.spec.composition`'s layer. Neither helper deleted, neither
  assertion weakened. `tests/test_133_us{1,2,5,6,7,8}_*.py` re-pointed to the
  modules the retirement leaves as the definition sites.

## The red runs

`uv run pytest tests/test_133_us9_the_verb_renders_the_composition.py -q
--no-header`, tree as received:

```
FAILED ...::test_the_renderer_serialises_the_typed_report_and_leaves_judge_evidence_absent
FAILED ...::test_the_cli_module_constructs_no_finding_of_its_own
FAILED ...::test_the_demonstration_obtains_its_verdict_through_the_library_form
FAILED ...::test_the_re_pointed_controls_still_disable_something
FAILED ...::test_the_cli_module_imports_no_relocated_layer_function
FAILED ...::test_no_test_reaches_a_relocated_layer_through_the_cli_module
6 failed, 4 passed in 0.38s
```

The four that passed red are the output guards (T035/T036): the pre-change
verb already produces US1's goldens, so those assert output *unchanged* rather
than detect a defect.

**T052's red ran deeper than trap 23 predicted.** `main()` re-executes every
noun module on every call (`factory/cli/main.py:74`,
`spec.loader.exec_module`), so a rebinding on `factory.cli.nouns.spec` is lost
before the very `main()` call it wraps — the fresh module's globals are rebuilt
from `factory.spec`'s cached objects. Verified by instrumenting the stub to
raise: it never fires. The two corpus controls had been passing vacuously since
they landed, through US5, US6 and US8 alike. The live seam is
`factory.spec.composition`, which the re-executed module re-imports cached;
T054 re-points both helpers there and T052 proves the re-point took.

## T042 evidence

**Plan step 4 sweep.** All 147 corpus specs, both faces, captured outside the
tree before the first edit and again after T040/T041/T054 — 294 runs. The
captures differ only where corpus specs' own `path:NN` anchors cite the two
files this story edits, which the anchor-resolution layer recomputes against
moved lines. Filtering those recomputations out: exit codes equal, and
`checked`, `skipped`, `information` and non-anchor findings equal per run —

```
$ diff <(before) <(after)
sweep problems: 0
```

**Demonstration stage, before and after T041** (same throwaway repository,
temp-dir normalised; `diff` of the two captures is empty):

```
exit=0
<REPO>/specs/001-demo/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage, anchor resolution, symbol anchors all pass
<REPO>/specs/001-demo/spec.md: what the judge will be shown for each node
  the diff — the node's own worktree diff and nothing else: not the tree it changed, not a terminal, not the running system. Abridged for the judge above 65536 bytes, and refused unjudged above 65536 (`diff_refusal_bytes` in <REPO>/ergane.yaml).
  the criteria — each node is shown its own story's scenarios, snapshotted at dispatch:
    US1 (Demonstration) — US1-S1
  the gates — the results of the gates <REPO>/ergane.yaml declares: test
  every Then-clause names evidence one of those three can produce.
--- stderr --- (empty, before and after)
```

**The re-pointed controls, on a spec each layer refuses** (T052's letter):

```
=== fixes control (spec declares fixes: absent/key; store holds present/key only)
enabled  : exit=1 findings=['fixes']
disabled : exit=0 findings=[]
different: True

=== evidence control (Then-clause asserts a browser outcome; this repo's ergane.yaml declares gate test)
enabled  : exit=1 findings=['evidence']
disabled : exit=0 findings=[]
different: True
```

Before the re-point the same instrument showed `different: False` for both —
T052's red run.

## The assembled diff, measured

`git diff 4c2f093..HEAD | wc -c` = **62,754 at the prose-trim commit**, and it
exceeds the 52,400-byte ceiling the story sets, which I am reporting rather
than shipping silently. The plan priced US9 at ~48 KB; the overage is the five
sibling re-points (~14.3 KB) and the corpus-control re-point, forced by FR-015's
retirement and priced into other stories' notes but only *possible* once T040
landed. Prose was cut twice; what remains is assertions and the strings they
assert on. Evidence here is pasted at minimum size.