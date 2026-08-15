# Plan: 044-prompt-assembly-preflight

Refined against the tree at `ca122ad` on 2026-08-15. Every line anchor below was
checked by hand against that commit; re-check them if the tree moves before
dispatch.

Driving finding: `interpreter/prompt-assembly-fails-only-at-dispatch` (critical,
2026-08-15). The incident it records: one roadmap tick killed all four
043-runtime-root-integrity nodes with `tasks.md declares no phase naming user
story US1`, and the same morning 011-agent-sandbox was found carrying a
tests-only-slice defect that assembly alone would not catch (US3 exists because
of it).

## What already exists, and where

| Thing | Location | Note |
| --- | --- | --- |
| `build_attempt_prompt` | `factory/workgraph/prompt.py:282` | The whole check. Raises `PromptAssemblyError` per its docstring (`:313-315`). Pure: texts in, prompt out. |
| Dispatch-time call sites | `factory/workgraph/workflow.py:1212`, `:2387` | Inside the **workflow**, not an activity. Today this is the first and only time the grammar runs. |
| `_task_slice` | `factory/workgraph/prompt.py:457` | The failure that killed 043. |
| `_names_story` | `factory/workgraph/prompt.py:399` | The heading grammar: `\bUser Story\s+<n>(?!\d)`, searched anywhere in the heading text. |
| `_first_section` | `factory/workgraph/prompt.py:410` | Returns the **first** matching section, to the next same-or-shallower heading, fence-masked. Both properties matter — see traps 2 and 3. |
| `_requirement_sections` | `factory/workgraph/prompt.py:349` | The spec.md half of assembly; US1 scenario 2. |
| `ergane spec validate` layers | `factory/cli/nouns/spec.py:222-288` | Four layers today; `checked` list at `:262-267`. The graph is already derived at `:239` — reuse it, do not derive twice. |
| `_ValidateFinding` | `factory/cli/nouns/spec.py:216` | The finding shape the new layers emit. |
| Preflight core | `factory/workgraph/preflight.py:110` (`check_aliases`) | The precedent US2 follows: pure library function, called by CLI and roadmap alike. `PreflightFinding` (check/passed/detail) is the shape; `model-aliases-served` at `:133`, `:156` is the naming pattern — this spec adds `prompt-assembly`. |
| Roadmap preflight activity | `factory/activities/roadmap_activities.py:353` | Where the roadmap calls `check_aliases` before an epic starts. The assembly check runs beside it. |
| CLI preflight callers | `factory/cli/nouns/build.py:165`, `factory/workgraph/cli.py:128` | The other two `check_aliases` call sites; decide per call site whether assembly joins them (build's preflight should). |

## Reference: the hand validator this spec productionizes

The operator's throwaway script, verbatim, minus imports — it proved all sixteen
nodes of four graphs assemble in under a second, offline. US1's core loop is
this with real `WorkNode`s from the already-derived graph instead of
`SimpleNamespace`, and findings instead of prints:

```python
for raw in graph["nodes"]:
    node = SimpleNamespace(**raw)
    try:
        slice_ = prompt._task_slice(node, tasks_text)
        reqs = prompt._requirement_sections(node, spec_text)
    except prompt.PromptAssemblyError as exc:
        print(f"FAIL {name}: {exc}")
```

Call `build_attempt_prompt` itself rather than the two internals: it is public,
it covers both, and FR-001 says "the same functions the dispatch path uses."

## Route choices left to the implementer

**Where the shared implementation lives.** Prefer
`factory/workgraph/preflight.py`, beside `check_aliases` — the roadmap activity
and the CLI already import from there, and the module's docstring describes
exactly this pattern (pure core, two callers). A new module is acceptable if
preflight.py's async/client-carrying signature makes a pure sync function feel
out of place; say which you chose and why in the commit message.

**What US3 counts as a story reference.** The spec names two forms: a `[US<n>]`
tag and a `spec US<n>-` citation. Both appear in this repo's tasks files (011
uses tags, 043 uses citations). Match both; if you find a third form in the
corpus, name it in the commit message rather than silently widening the regex.

## Traps

**Trap 1 — the workflow cannot read files.** The dispatch-time call at
`workflow.py:1212` receives its texts from activities; workflow code reading
the filesystem is non-deterministic and is the exact defect class that killed
the roadmap on 2026-08-13 (`roadmap/success-path-reads-environ-inside-the-workflow`).
US2's check must run **inside the preflight activity**, never in workflow code.

**Trap 2 — fence-masking is part of the grammar.** `_first_section` masks fenced
blocks (`prompt.py:417-418`): a heading quoted inside a code fence neither opens
nor closes a section. Any line-scanning the slice-coverage lint does must use
the same `mask_fences` the assembler uses, or a tasks.md that quotes a heading
in an example will lint differently than it dispatches. This is FR-004's point.

**Trap 3 — `_first_section` returns the first match and only the first.** Two
phases naming the same story hide the second phase silently: assembly succeeds,
the second phase's tasks reach nobody. US1 alone will not catch that; US3's
orphan-task report is what surfaces it (the hidden tasks fall in no slice while
referencing a story — scenario 2's shape). Do not "fix" `_first_section`; the
first-match rule is dispatch behavior, and this spec checks against dispatch
behavior rather than changing it.

**Trap 4 — a missing plan.md must be a finding, not a crash.** Validate today
reads spec.md only (`spec.py:224-228`); the assembly layer also needs plan.md
and tasks.md. US1 scenario 4: surface an unreadable file as a
`prompt_assembly` finding naming the path. An uncaught `OSError` here turns a
refinement tool into a stack trace.

**Trap 5 — the layer must not lie about what it checked.** The preflight
honesty rule (`factory/workgraph/cli.py:97-100`): state what was checked, not
more. If derivation failed in layer two, there is no graph and assembly cannot
run — the report must then omit `prompt_assembly` from `checked` (or state it
was skipped and why), never claim a pass it did not compute.

**Trap 6 — `## Verification` sections are a convention, not a defect.** 043 and
011 both end with a `## Verification` phase naming no story. Task ids there
reach no agent today, deliberately in 043's case (`Final gate command passes
green` carries no id). FR-006 makes ids there *information*, exit code
unchanged. If your lint fails the in-tree corpus, your lint is miscalibrated —
scenario 3 pins this.

**Trap 7 — the judge sees the diff and the criteria, nothing else.** Every
"proven by a committed test" clause means the test is in the diff. Fixtures
reconstructing the 043 and 011 defects must be committed fixture files, not
references to history.

**Trap 8 — dispatch reads live, so validate-then-edit is still a hole.** US2 is
not redundant with US1: the preflight is the only check that reads what
dispatch is about to read (FR-007). Do not implement US2 as "run validate in a
subprocess"; run the shared pure function on the same texts the dispatch
activities load.

## Verification the operator will run, independent of the gate

- Recreate the 043 heading defect in a scratch spec dir; `ergane spec validate`
  it and read the finding.
- Flip that scratch spec to ready under a test roadmap and watch it park with
  `prompt-assembly` rather than dispatch.
- Run validate over every trio in `specs/` and confirm the in-tree corpus is
  clean (or that every finding it raises is real).
