"""The merge-queue component (epic 003): verified work lands through GitHub's queue.

US1 — the landing path. When a node's ladder ends PASSED, its branch is salvaged
and pushed, opened as a ready PR against the target repo's default branch,
enqueued with `gh pr merge --auto`, polled until GitHub's queue yields a verdict,
and that verdict classified into the interpreter's vocabulary (FR-001, 002, 003,
004, 009). All serialization of landings is GitHub's own merge queue; this
component never sequences merges itself, only asks for them and reads what
happened (D-011: polling-only reconciliation).

The `gh` CLI is the one subprocess boundary: it runs against the target clone
with the same scrubbed environment the worktree operations use (constitution V),
and its failures come back as data — `GH_AUTH`, `GH_NOT_FOUND`, `GH_REFUSED`,
`GH_UNAVAILABLE` — never as crashes an interpreter has to read prose from.

Determinism core (constitution IV): classification is a pure function of a
polled `PrSnapshot`, the `Landing` record, the `LandingConfig`, and the clock.
No LLM sits in any merge decision, and the judge that scored the node is never a
required check here — 002's judge already ran; its verdict lives in the branch
history and the PR body, not in a merge gate.
"""
