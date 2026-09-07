# 133-US1 attempt report: a typed report exists, and today's output is captured

## What changed

Three commits, tests first:

- `tests/test_133_us1_typed_report_and_golden_captures.py` plus the two
  fixture trios and the shared fixture target repository (T001–T006, T009) —
  committed observed-red. T001–T005 assert the `factory.spec` exports, the
  four channels as separate members, the information-only pass verdict, the
  `_ValidateFinding` constructor shape, and the CLI module binding rather than
  defining the type. T006 compares both trios' three streams against six
  golden artifacts with the repository root normalised on both sides. T009's
  fixtures: `tests/fixtures/spec_validate/{clean-specs/001-clean-trio,
  defective-specs/002-defective-trio,target-repo}` — each trio alone in its
  parent (the frontmatter layer reads `spec_dir.parent` as the specs root,
  plan trap 13), the target repo committing an `ergane.yaml` that declares one
  gate, `smoke` (plan trap 20).
- `factory/spec/` (T007) — `SpecFinding`, a frozen dataclass with
  `_ValidateFinding`'s attribute names and keyword-only `severity="refusal"`
  default (plan trap 7), and `SpecValidation` with all four channels and a
  verdict that reads refusals alone (FR-001, FR-002, US1-S3). Nothing here
  imports from the CLI module (plan trap 17).
- `factory/cli/nouns/spec.py` (T008) — the class at 483 is deleted and the
  import bound under the same local name: `from factory.spec import
  SpecFinding as _ValidateFinding`. Not one construction site changes.
- `tests/golden/spec_validate/` (T010) — six artifacts, captured through the
  same CLI entry point the test drives, before any layer body moved, root
  normalised to `<REPO_ROOT>` on every stream. Six files, 6,370 bytes.

## The red runs

T001–T005 and T006 against the tree as received, no `factory/spec/`, no
goldens:

```
$ uv run python -m pytest tests/test_133_us1_typed_report_and_golden_captures.py -q --no-header
E       ModuleNotFoundError: No module named 'factory.spec'
E       ModuleNotFoundError: No module named 'factory.spec'
E       ModuleNotFoundError: No module named 'factory.spec'
E       ModuleNotFoundError: No module named 'factory.spec'
E       assert 'class _ValidateFinding' not in <module source>
E       FileNotFoundError: .../tests/golden/spec_validate/clean/stdout.txt
E       FileNotFoundError: .../tests/golden/spec_validate/defective/stdout.txt
FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_factory_spec_exports_the_typed_report_and_finding
FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_report_holds_all_four_channels_as_separate_members
FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_information_only_report_verdicts_as_a_pass
FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_finding_type_keeps_the_validate_finding_constructor_shape
FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_cli_module_no_longer_defines_the_finding_type_but_binds_the_import
FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_trio_matches_its_three_golden_artifacts[trio_dir0-clean]
FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_trio_matches_its_three_golden_artifacts[trio_dir1-defective]
FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_clean_trio_prints_the_all_pass_sentence_and_the_defective_one_refuses
8 failed, 1 passed in 0.26s
```

The one that passed red is T009's layout control, and it had to: the fixture
layout is committed in the same commit as the tests, and the comparison tests
are red only on the artifacts not yet taken. A layout control that failed red
would mean the fixtures were mislaid before the goldens existed.

## T011 — the pasted evidence

**A constructed report, all four channels, and its verdict** (FR-001, FR-002):

```
$ uv run python (constructed in-process)
=== T011: one constructed report, all four channels (FR-001, FR-002) ===

refusals    : [('evidence', 'refusal', 'US1-S1: "the page renders correctly in the browser." asserts…')]
advisories  : [('scenario_coverage', 'advisory', 'acceptance scenarios with no task reference: US1-S1')]
information : [('sentinel', 'tasks.md:5: - [ ] T001 draw the page. ERGANE-TODO:…'), ('fixes', 'verified 2 finding key(s)…')]
skipped     : [{'layer': 'anchor_resolution', 'reason': 'none of the cited paths exist under target repository <fixture-repo>'}, {'layer': 'slice_coverage', 'reason': 'the work graph did not compile, so there are no nodes to assemble a prompt for'}]

verdict     : fail

=== T011/US1-S3: the information-only control ===
verdict     : pass — notes and a skip ride their own channels; the verdict reads refusals alone

=== T011/US1-S4: the constructor shape ===
SpecFinding('workgraph', 'the work graph did not compile')          -> severity: refusal
SpecFinding('slice_contention', '…', severity='advisory')           -> severity: advisory

=== T011/US1-S1: the exports ===
factory.spec.SpecValidation : factory.spec.report.SpecValidation
factory.spec.SpecFinding    : factory.spec.report.SpecFinding
SpecFinding fields          : [('layer', '<required>'), ('message', '<required>'), ('severity', 'refusal')]
```

**The six artifact heads, showing the normalised root** (FR-014, plan trap 11):

```
=== head: tests/golden/spec_validate/clean/stdout.txt ===
<REPO_ROOT>/tests/fixtures/spec_validate/clean-specs/001-clean-trio/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage, symbol anchors all pass
<REPO_ROOT>/tests/fixtures/spec_validate/clean-specs/001-clean-trio/spec.md: what the judge will be shown for each node
  the diff — the node's own worktree diff and nothing else: not the tree it changed, not a terminal, not the running system. Abridged for the judge above 65536 bytes, and refused unjudged above 65536 (`diff_refusal_bytes` in <REPO_ROOT>/tests/fixtures/spec_validate/target-repo/ergane.yaml).

=== head: tests/golden/spec_validate/clean/stderr.txt ===
ergane spec validate — layer 'anchor_resolution' not checked: none of the cited paths exist under target repository <REPO_ROOT>/tests/fixtures/spec_validate/target-repo
ergane spec validate — noted, not a refusal: [sentinel] tasks.md:5: - [ ] T001 [US1-S1] Leave this trio byte-stable. ERGANE-TODO: the golden — not ready to derive
1 ERGANE-TODO sentinel remain; ergane spec derive will refuse until they are resolved.

=== head: tests/golden/spec_validate/clean/json.txt ===
{
  "spec_dir": "<REPO_ROOT>/tests/fixtures/spec_validate/clean-specs/001-clean-trio",
  "checked": [

=== head: tests/golden/spec_validate/defective/stdout.txt ===
<REPO_ROOT>/tests/fixtures/spec_validate/defective-specs/002-defective-trio/spec.md: what the judge will be shown for each node
  the diff — the node's own worktree diff and nothing else: not the tree it changed, not a terminal, not the running system. Abridged for the judge above 65536 bytes, and refused unjudged above 65536 (`diff_refusal_bytes` in <REPO_ROOT>/tests/fixtures/spec_validate/target-repo/ergane.yaml).
  the criteria — each node is shown its own story's scenarios, snapshotted at dispatch:

=== head: tests/golden/spec_validate/defective/stderr.txt ===
ergane spec validate — advisory: [scenario_coverage] acceptance scenarios with no task reference: US1-S1
ergane spec validate — refusal: [evidence] US1-S1: "the page renders correctly in the browser." asserts an outcome only a running system shows ("in the browser", "renders correctly"); the judge is shown the diff and the results of the gates this repository declares (smoke), and the clause names neither — no declared gate, and nothing the diff itself carries. To make it provable: name a declared gate (smoke) whose result will reach the judge with the diff, or restate the clause as something the diff carries — e.g. "… — proven by a committed test"
ergane spec validate — layer 'anchor_resolution' not checked: none of the cited paths exist under target repository <REPO_ROOT>/tests/fixtures/spec_validate/target-repo

=== head: tests/golden/spec_validate/defective/json.txt ===
{
  "spec_dir": "<REPO_ROOT>/tests/fixtures/spec_validate/defective-specs/002-defective-trio",
  "checked": [
```

**The clean trio's all-pass sentence, the line the story exists to freeze**:

```
<REPO_ROOT>/tests/fixtures/spec_validate/clean-specs/001-clean-trio/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage, symbol anchors all pass
```

**The defective trio's refusal and advisory lines** (the prefixes US3 rewrites;
both print to stderr and to no other stream — plan trap 19):

```
ergane spec validate — refusal: [evidence] US1-S1: "the page renders correctly in the browser." asserts an outcome only a running system shows ("in the browser", "renders correctly"); the judge is shown the diff and the results of the gates this repository declares (smoke), and the clause names neither — no declared gate, and nothing the diff itself carries. To make it provable: name a declared gate (smoke) whose result will reach the judge with the diff, or restate the clause as something the diff carries — e.g. "… — proven by a committed test"
ergane spec validate — advisory: [scenario_coverage] acceptance scenarios with no task reference: US1-S1
```

## Green gates on the declared command

```
$ uv run pytest -q
5768 passed, 58 skipped, 11 warnings in 504.14s (0:08:24)
```

The suite total matches the pre-existing baseline exactly (the pre-story run
also carried 58 skips); the eleven warnings are the pre-existing
deprecation/Temporal noise, two of which this run's summary reports. The
terminal summary's `[FAIL]` lines are the live-tier probes that did not run in
this sandbox (no Temporal server on :8233, no `ERGANE_LLM_MASTER_KEY`) —
the report the conftest describes as "describes and never decides".

## What was not done, on purpose

No layer body moved: the twelve layers run from the same lines they ran
before, and the `--json` document, the `checked` order and every rendered
prefix are byte-identical to what they were — the six artifacts are the proof,
taken before anything after this story moves.