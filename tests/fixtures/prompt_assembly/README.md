# Prompt-assembly fixtures (044 US1)

Three committed spec trios, each reproducing one state the new `prompt_assembly`
validate layer must recognise. They are committed rather than built in a test
body because the defects they carry are incidents, and an incident described in
a test is a claim about history nobody reading the diff can check.

| Trio | What it reproduces |
| --- | --- |
| `901-heading-defect` | The 2026-08-15 kill: `tasks.md` phase headings name each story's *title* and never the literal story key, so no node finds a task slice. Every other validate layer passes it. |
| `902-stale-graph` | A compiled `workgraph.json` that outlived the spec it was compiled from: the artifact still carries a `us2` node, `spec.md` no longer declares that story. This is the graph `ergane build start` loads and dispatches. |
| `903-well-formed` | The control: the same shape, correct, which the layer must report clean. |

Each trio is a whole trio — `spec.md`, `plan.md`, `tasks.md` — because prompt
assembly reads all three, and a fixture missing one would test the missing-file
path by accident. The missing-file case (US1 scenario 4) is built by copying
`903-well-formed` and deleting a document, so the deletion is visible in the
test that needs it.

Every trio's frontmatter is valid and its `## Work Graph` compiles: the point of
`901-heading-defect` is that the four pre-existing validate layers see nothing
wrong with it (SC-004).
