# spec-validate golden captures (133-US1)

Six artifacts — each of two fixture trios' **stdout**, **stderr** and
`--json` document — committed before any layer body moves (FR-014). Every
later story of epic 133 re-runs
`tests/test_133_us1_typed_report_and_golden_captures.py::test_the_trio_matches_its_three_golden_artifacts`
and must match these bytes exactly; that is what makes "the move changed
nothing" provable rather than asserted.

| Path | Trio | Stream | What it freezes |
| --- | --- | --- | --- |
| `clean/stdout.txt` | `001-clean-trio` | stdout | The all-pass sentence naming every layer that ran, and the judge-evidence report. |
| `clean/stderr.txt` | `001-clean-trio` | stderr | One skipped-layer line (`anchor_resolution`) and one information note (the sentinel), plus the trailing sentinel count. |
| `clean/json.txt` | `001-clean-trio` | `--json` | The whole document: `checked` order, the `skipped` reason, empty `findings`, and `judge_evidence` present. |
| `defective/stdout.txt` | `002-defective-trio` | stdout | The judge-evidence report and **no** all-pass sentence — a run carrying a refusal never prints one. |
| `defective/stderr.txt` | `002-defective-trio` | stderr | One `— advisory:` line (scenario_coverage), one `— refusal:` line (evidence, the string US6-S4 compares against), the skipped-layer line and the sentinel note. |
| `defective/json.txt` | `002-defective-trio` | `--json` | The document carrying both findings with their severities, and `all_provable: false`. |

Three of the four rendered channels print to **stderr**; only the all-pass
sentence, the judge-evidence report and the `--json` document reach stdout
(plan trap 19). That split is why each trio has three artifacts and not one:
a stdout-only capture would freeze none of the four prefixes the relocation is
forbidden to change.

**The repository root is normalised** to `<REPO_ROOT>` in every artifact, on
every stream — the fixes layer's information note embeds an absolute store
path, the evidence report the absolute manifest path, and the skipped-layer
reasons the `--target-repo` string (plan trap 11). A verbatim capture would go
red on every other checkout, the merge-group build included.

**Re-taking these**: only when a fixture trio under
`tests/fixtures/spec_validate/` changes, in the same commit as the trio, and
only from a tree where the validate verb still produces today's output —
never to make a failing comparison green. The taker is
`tests/_us1_outputs/take_spec_validate_goldens.py`.

    uv run python tests/_us1_outputs/take_spec_validate_goldens.py