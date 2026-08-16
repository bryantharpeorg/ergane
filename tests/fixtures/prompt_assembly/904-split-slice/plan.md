# Plan: The agent sandbox (reconstructed)

Two stories, one seam. The detector reads the target repository's tracked-file
state at attempt start and again at teardown; the boundary substitutes the
launch so the same attempt runs with the worktree as its only writable path.

This file exists because prompt assembly reads the whole trio: a plan is carried
into every node's prompt intact, so a fixture missing one would be exercising
the missing-file path by accident rather than the slice-coverage path on purpose.
