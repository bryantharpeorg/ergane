# Plan: 029-salvage-landing-grammar

Scaffolded from the following ledger findings:

- `targets/salvage-only-pr-lands-invisible` — critical: When an agent commits nothing itself, the salvage commit is the PR's only commit, and GitHub's COMMIT_OR_PR_TITLE squash rule uses that single commit's message as the merge subject -- so the merge lands as 'salvage(<epic>/<node>): completed attempt N' instead of the landing grammar. The story is in the tree but invisible to landed_facts, and a delta derivation would re-dispatch work that already landed.

Refine the approach before the spec is readied.
