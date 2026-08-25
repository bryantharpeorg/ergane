# US4 `ergane build ship` transcript paste (T040)

All runs below are seam captures where the sandbox cannot reach a real Temporal
server: `start_command` is rebound to a stub that prints and returns without
dispatching.  The validate and derive stages are the real CLI handlers.

## 1. Full `ship` run through the pause, dispatch stubbed (US4-S1)

```text
ship: validating /tmp/ship-demo/workgraph.json
/tmp/ship-demo/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage all pass
ship: deriving /tmp/ship-demo/workgraph.json
/tmp/ship-demo/workgraph.json
ship: compiled graph 'ship-demo' has 3 node(s)
dispatch order: us1 us2 us3
  us1  persona implementer  model ollama-cloud/kimi-k2.7-code
  us2  persona implementer  model ollama-cloud/kimi-k2.7-code
  us3  persona implementer  model ollama-cloud/kimi-k2.7-code
[STUB] start_command called; dispatch avoided
EXIT=0
```

Seams rebound: `start_command` stubbed; `load_personas` pointed at a fixture
registry containing `implementer: ollama-cloud/kimi-k2.7-code`.

## 2. Declined confirmation, no dispatch (US4-S1)

```text
ship: validating /tmp/ship-demo/workgraph.json
/tmp/ship-demo/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage all pass
ship: deriving /tmp/ship-demo/workgraph.json
/tmp/ship-demo/workgraph.json
ship: compiled graph 'ship-demo' has 3 node(s)
dispatch order: us1 us2 us3
  us1  persona implementer  model ollama-cloud/kimi-k2.7-code
  us2  persona implementer  model ollama-cloud/kimi-k2.7-code
  us3  persona implementer  model ollama-cloud/kimi-k2.7-code
Dispatch epic 'ship-demo'? [y/N] ergane: ship cancelled
EXIT=1
```

Input seam: stdin fed `n`.  No Temporal connection attempted.

## 3. Validate failure stops ship at stage one (US4-S2)

```text
ship: validating /tmp/ship-bad/workgraph.json
ergane spec validate — refusal: [frontmatter] ship-bad: [unknown_state] 'state' must be one of 'deferred', 'draft', 'landed', 'ready', got 'invalid' — only the system may say 'building'; the author's vocabulary is the four intent states
ergane spec validate — refusal: [workgraph] the `## Work Graph` section does not compile (1 declaration rejected):
  - [section_missing] the spec must declare exactly one `## Work Graph` section; found no
ergane spec validate — layer 'prompt_assembly' not checked: the work graph did not compile, so there are no nodes to assemble a prompt for
ergane spec validate — layer 'slice_coverage' not checked: the work graph did not compile, so there are no nodes to assemble a prompt for
ergane spec validate — layer 'slice_contention' not checked: the work graph did not compile, so there are no stories to compare slices for
EXIT=1
```

No derive stage ran and no dispatch was attempted.

## 4. Constituent verb suites remain green (US4-S3)

```text
$ uv run pytest -q tests/test_ergane_spec.py tests/test_ergane_build.py tests/test_graph_paths_are_absolute.py tests/test_build_verbs_take_an_epic_id.py
tests/test_ergane_spec.py ..............................
tests/test_ergane_build.py ...............................................
tests/test_graph_paths_are_absolute.py .......
tests/test_build_verbs_take_an_epic_id.py .......
97 passed, 1 warning in 6.55s
```

`tests/test_graph_paths_are_absolute.py:132` still imports `_derive_command` by
its private name; the new public wrappers `validate_spec_command` and
`derive_spec_command` were added without moving the private symbols.
