# 133-US2 attempt report: the anchor and symbol layers leave the CLI module

## What changed

Four commits, tests first:

- `tests/test_133_us2_anchor_layers_leave_the_cli_module.py` (T012, T013,
  T014) — committed observed-red, 10 failed / 1 passed. T012 reads the CLI
  module's *source* for a `def` or an assignment of each of the eleven names
  US2-S1 lists (an attribute check would also pass on the import back) and
  asserts both halves of the definition/binding distinction: nothing defined
  here, everything still bound, because the CLI still composes. T013 compares
  the CLI's binding to `factory.spec`'s object by identity and `__module__`,
  so a re-declaration cannot pass as a move. T014 drives
  `_check_symbol_anchors` and `_check_anchor_resolution` over tmp trees
  asserting the parameter contract and the caller-owned `findings`, `skipped`
  and `checked` appends, and carries one test per `checked` exit of
  `_check_anchor_resolution` (plan trap 5): no documents, no citations, only
  unanchorable bare refs, and the normal end — none merged into one append.
- `factory/spec/anchors.py` (T015) — the anchor family moved byte-for-byte:
  `_check_anchor_resolution` and `_check_symbol_anchors` with
  `_read_citation_files`, `_spec_state`, `_severity_for_state`,
  `_symbol_spans`, `_line_hits_symbol`, and the grammars they alone read —
  `_ANCHOR_RE` and `_BARE_LINE_RE` with their `#:` comments from above the
  span, `_SYMBOL_ANCHOR_RE` and `_DISPATCHABLE_STATES` from inside it (plan
  trap 17). 18,084 bytes of source, proven byte-identical to the spans
  `0c2cb23` held (see the evidence file). The four `checked` appends stay
  four separate exits; no string changed; nothing in `factory/spec/` imports
  from `factory.cli.nouns.spec`.
- `factory/cli/nouns/spec.py` (T016) — the three spans deleted; the eleven
  names import back from `factory.spec` under their old private spellings and
  `_validate_command` calls them exactly as it did. `_check_frontmatter`
  stays for US5. The CLI still composes; US3 ends that.
- `tests/_us2_outputs/t017_golden_comparison.txt` (T017) — the committed
  evidence: the comparison against US1's six golden artifacts, empty on all
  three streams for both trios, plus the story's `git diff --stat` line and
  the byte-identity proof.

## The red run

```
$ uv run pytest tests/test_133_us2_anchor_layers_leave_the_cli_module.py -q --no-header
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_the_cli_module_no_longer_defines_the_anchor_family
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_the_cli_module_calls_the_anchor_checkers_defined_in_factory_spec
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_factory_spec_defines_the_moved_names
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_the_moved_checkers_keep_their_parameters_and_append_into_caller_owned_lists
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_the_signatures_are_unchanged
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_1_no_documents
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_2_no_citations_found
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_3_citations_but_no_paths_cited
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_4_the_normal_end
FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_4_reports_stale_anchors_before_appending
10 failed, 1 passed in 0.18s
```

The one that passed red is T012's binding half — true before the move and
after it, which is what makes the definition/binding distinction real rather
than decorative. T014's driven half is red because `factory.spec.anchors` did
not exist yet; a rewrite would have kept it red.

## T017 — the pasted evidence

The comparison of this story's output against US1's six golden artifacts —
`tests/test_133_us1_typed_report_and_golden_captures.py::test_the_trio_matches_its_three_golden_artifacts`
is the standing guard, and it reads 9 passed here:

```
$ uv run pytest tests/test_133_us1_typed_report_and_golden_captures.py -q --no-header
9 passed in 0.99s
```

The same comparison as a unified diff, both trios, all three streams
(`tests/_us2_outputs/t017_golden_comparison.txt` carries it too):

```
[clean/stdout] diff lines vs US1 golden: 0
[clean/stderr] diff lines vs US1 golden: 0
[clean/json] diff lines vs US1 golden: 0  (stderr empty: True)
[defective/stdout] diff lines vs US1 golden: 0
[defective/stderr] diff lines vs US1 golden: 0
[defective/json] diff lines vs US1 golden: 0  (stderr empty: True)

ALL THREE STREAMS, BOTH TRIOS: EMPTY — the move changed nothing
```

The verb's exit codes, unchanged: clean trio 0, defective trio 1.

**The story's `git diff --stat` line** (T017 asks for it by name; base is
US1's merge, `0c2cb23`):

```
 git diff 0c2cb23..HEAD --stat
 factory/cli/nouns/spec.py                          | 444 +------------------
 factory/spec/__init__.py                           |  43 +-
 factory/spec/anchors.py                            | 473 +++++++++++++++++
 ...t_133_us2_anchor_layers_leave_the_cli_module.py | 382 +++++++++++++++++
 4 files changed, 910 insertions(+), 432 deletions(-)
```

Assembled diff against the base: 60,666 bytes — inside
`DIFF_REFUSAL_THRESHOLD` (65,536, `factory/verify/diffbounds.py:66`) with
4,870 bytes of headroom. The production half alone is 42,781 bytes.

## Byte-identity proof for the moved source

Extraction of the three spans from
`git show 0c2cb23:factory/cli/nouns/spec.py` against the same markers in
`factory/spec/anchors.py`:

```
spanA (symbol family) byte-identical: True 7566
spanB (citation family) byte-identical: True 10275
regex block byte-identical: True 243
TOTAL source bytes moved: 18084 (plan measured 18,098 incl. trailing blanks)
```

## Green gates on the declared command

```
$ uv run pytest -q
5785 passed, 58 skipped, 11 warnings in 505.27s (0:08:25)
```

5,785 against the base run's 5,774: the story's eleven new tests, nothing
else moved. The 58 skips and the warning set match the baseline. The
"9 of 12 checks failed" line a full-suite transcript shows between progress
dots is captured stdout printed by the passing seam-capture test
`tests/test_ergane_install_closing_step.py::test_closing_step_seam_capture_transcript`
(witnessed at the base commit too, `git worktree add` at `0c2cb23`, same
line, same single pass) — install's readiness report describing a
demonstration repository without a Temporal server or an
`ERGANE_LLM_MASTER_KEY`, described and never deciding.

## What was not done, on purpose

`_check_frontmatter` stays in the CLI module (US5's). No refusal string
changed; no parameter changed; the four `checked` appends were not merged;
`factory/spec/` imports nothing from `factory.cli.nouns.spec`. The verb's
stdout, stderr, `--json` document, `checked` order and every rendered prefix
are byte-identical to what they were — the six artifacts are the proof.

---

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