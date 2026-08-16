# Prompt-assembly fixtures (044 US1, US3)

Committed spec trios, each reproducing one state the `prompt_assembly` and
`slice_coverage` validate layers must recognise. They are committed rather than
built in a test body because the defects they carry are incidents, and an
incident described in a test is a claim about history nobody reading the diff
can check.

| Trio | What it reproduces |
| --- | --- |
| `901-heading-defect` | The 2026-08-15 kill: `tasks.md` phase headings name each story's *title* and never the literal story key, so no node finds a task slice. Every other validate layer passes it. |
| `902-stale-graph` | A compiled `workgraph.json` that outlived the spec it was compiled from: the artifact still carries a `us2` node, `spec.md` no longer declares that story. This is the graph `ergane build start` loads and dispatches. |
| `903-well-formed` | The control: the same shape, correct, which both layers must report clean. |
| `904-split-slice` | The 011 near-miss (US3): Tests and Implementation groups both written at phase level, so each story's slice stops at its own implementation heading. **All five earlier layers pass it** — every node assembles, and every prompt is missing half its story. |
| `905-wrong-slice` | The worse half of the same sweep (US3): a story inserted at position two after `tasks.md` was numbered, so `us2` assembles Phase 3 and is handed US3's tasks, `us3` assembles Phase 4 and is handed US4's. Only `us4`, which no heading names, refuses — three quarters of the defect is silent. |
| `906-orphan-tasks` | The two shapes the lint must *not* refuse: a `## Verification` phase whose task ids carry no story key (information, exit code unchanged), and a task line quoted inside a fenced block, deliberately written as the worst case the lint reports. |

Each trio is a whole trio — `spec.md`, `plan.md`, `tasks.md` — because prompt
assembly reads all three, and a fixture missing one would test the missing-file
path by accident. The missing-file case (US1 scenario 4) is built by copying
`903-well-formed` and deleting a document, so the deletion is visible in the
test that needs it.

Every trio's frontmatter is valid and its `## Work Graph` compiles: the point of
`901-heading-defect` is that the four pre-existing validate layers see nothing
wrong with it (SC-004), and the point of `904-split-slice` is that the
`prompt_assembly` layer sees nothing wrong with it either.
