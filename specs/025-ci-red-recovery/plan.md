# Plan: 025-ci-red-recovery

Scaffolded from the following ledger findings:

- `interpreter/ci-failure-never-reaches-an-agent` — critical: A red required check is treated as a stale base: the interpreter syncs and re-enqueues without routing the CI log to any agent, so the recovery cycle re-runs identical code and the node is KILLED with its dependents
- `ci/flaky-concurrency-test-is-a-random-epic-killer` — critical: test_kill_with_n_in_flight_salvages_every_one_before_terminating asserts a timing coincidence -- that a sampled in-flight set was observed at size 3 -- so under CI load it fails on a diff that never touched it. Because it is inside the single required check, a flake spends a node's only recovery cycle, and two flakes in a row kill the node and every dependent.

Refine the approach before the spec is readied.
