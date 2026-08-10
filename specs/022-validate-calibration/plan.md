# Plan: 022 — `spec validate` calibration

One file, one decision, one story. The whole change lives in
`factory/cli/nouns/spec.py` and the tests that pin its exit codes.

## Reuse inventory

Verified against `a10ab55` on 2026-08-09 at 11:10 PM CT — the tree as 019 left
it. Re-verify at preflight; 019 moved nineteen anchors in a single evening and
this file is one it created.

| What | Where | Why it matters |
| --- | --- | --- |
| `_ValidateFinding` | `factory/cli/nouns/spec.py:216-219` | Two attributes, `layer` and `message`. This is where severity goes. |
| `_validate_command` | `factory/cli/nouns/spec.py:222` | The whole verb, ~66 lines. Reads top to bottom. |
| The four check calls | `spec.py:234`, `:250-257`, `:260` | frontmatter, work-graph + persona, scenario coverage, in that order. |
| The `checked` list | `spec.py:262-267` | Four layer names, emitted in the JSON report. Unchanged by this work. |
| The report dict | `spec.py:268-275` | `{spec_dir, checked, findings[{layer, message}]}`. FR-007 adds one key per finding here and nowhere else. |
| The human print | `spec.py:279-286` | Findings to **stderr**, one per line, prefixed `ergane spec validate: [layer]`. The success line is on stdout. |
| **The exit rule** | `spec.py:288` | `return EXIT_USER if findings else EXIT_OK`. This single line is FR-002. |
| `_check_scenario_coverage` | `spec.py:378-414` | Produces both findings this spec separates: missing file at `:396-403`, uncovered ids at `:408-414`. |
| `_SCENARIO_ID_RE` | `spec.py:45` | `re.compile(r"US\d+-S\d+")`. Unchanged. |
| `EXIT_OK` / `EXIT_USER` | `factory/cli/errors.py:23-24` | 0 and 1. Do not add a new exit code; FR-002 is about which findings reach 1. |
| Existing tests | `tests/test_ergane_spec.py:442-525` | Three tests under a `T011a: scenario coverage` banner. Two of them assert the contract this spec changes. |

## Approach

1. Give `_ValidateFinding` a third attribute with a default that preserves
   today's behaviour for every existing construction site. There are eight, at
   `spec.py:247`, `:257` (via `_check_personas`), `:298`, `:300`, `:307`,
   `:314`, `:321`, `:398` and `:410`. A defaulted parameter means only the one
   advisory site changes.
2. Change `spec.py:288` to consider severity rather than emptiness.
3. Mark the human line so an advisory reads differently from a refusal
   (FR-006). The prefix already carries the layer; extend that, do not invent a
   second output stream.
4. Add the severity to the per-finding dict at `spec.py:271-274`.
5. Update the two landed tests that assert the old contract, and add the new
   ones.

## Traps

Named hazards. Each one has already cost something, here or nearby.

1. **Do not demote the whole layer.** `_check_scenario_coverage` emits two
   findings under the name `scenario_coverage`, and only one of them is an
   advisory. A missing `tasks.md` (`spec.py:396-403`) is a spec nobody can
   implement, and `test_validate_reports_missing_tasks_file`
   (`tests/test_ergane_spec.py:500-525`) asserts exit 1 on it. If that test
   goes green after your change without you having thought about it, you
   demoted a real check. Severity belongs on the **finding**, not on the layer.

2. **Two landed tests encode the old contract, and one of them must flip.**
   `test_validate_reports_uncovered_scenario_ids` at
   `tests/test_ergane_spec.py:445` asserts `result.code == 1`; under FR-002 it
   becomes 0 while keeping its `"US1-S2" in output` assertion. Change it in the
   same commit as the code. This is the exact shape that made 020's T012 an
   operator task: a landed test asserting the behaviour you are replacing is
   part of your diff, not evidence that you broke something.

3. **`test_validate_scenario_coverage_passes_when_all_referenced` must stay
   green for the same reason it is green today**, not because everything now
   exits 0. It is at `tests/test_ergane_spec.py:473` and it asserts 0 with all
   scenarios referenced. After this change it would also pass if you deleted
   the check entirely. Add the assertion that distinguishes them: with a
   deliberate gap, the ids still appear in the output.

4. **`--json` is a dump, not a re-assembly.** The discipline is stated in 019's
   own plan and holds here. Add `severity` to each finding dict. Do not add a
   top-level `passed`, do not group findings by severity, do not reorder them,
   and do not change `checked` — a consumer parsing today's document must keep
   working.

5. **Stdout stays clean.** Findings go to stderr (`spec.py:281`), the success
   line to stdout (`spec.py:283-286`). An advisory is still a finding and still
   belongs on stderr — the exit code is what changed, not the stream. Do not
   move advisories to stdout because they are "not errors".

6. **The success line is now reachable with findings present.** Today
   `spec.py:279-286` is an if/elif: findings print, or the success line prints.
   Under FR-002 a spec can exit 0 *with* findings. Decide what the operator
   sees in that case and make it unambiguous — a command that prints uncovered
   scenarios and then says everything passes is worse than either alone.

7. **You are editing the CLI the operator is running.** Not the interpreter —
   the worker imports `factory.cli` but does not dispatch through it, so this
   is safe in a way 010 is not. But `ergane spec validate` is how the operator
   checks specs, so a broken verb here is discovered at the next dispatch and
   not before.

8. **Line numbers rot.** Every anchor above was verified at `a10ab55` on the
   night 019 landed. If a citation does not match what you find, trust the tree
   and say so in your notes rather than editing by line number.

## Verification

The gate is `uv run pytest -q`, declared in `factory.yaml`. Beyond it, the
proof this spec exists for is a corpus run rather than a fixture:

```
for d in specs/*/; do ergane spec validate "$d" >/dev/null 2>&1; echo "$? $d"; done
```

Before: seventeen `1`s. After: `0` for every spec whose only findings are
uncovered scenarios, and the ids still printed on stderr for each.

## Out of scope

- Narrowing the rule to identifiers named in a scenario but absent from
  `tasks.md`. Better check, different spec.
- Editing any `tasks.md` in the corpus.
- A `--strict` flag restoring exit 1. Nobody has asked for it; adding a knob to
  undo the fix is how a calibration becomes a configuration surface.
