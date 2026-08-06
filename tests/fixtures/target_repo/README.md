# calc

A deliberately tiny target repo: one module, one manifest, one set of gates.

It exists to be *verified*, not to be useful — the factory's gate runner needs a
repo whose gates it can run and whose worktree it can diff, and the smallest
honest one is a single function plus the scripts that check it.

This file is tracked and boring on purpose: diff-check tests modify it to prove
`has_diff` notices a change to a tracked file.
