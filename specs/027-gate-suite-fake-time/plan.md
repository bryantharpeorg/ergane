# Plan: 027-gate-suite-fake-time

Scaffolded from the following ledger findings:

- `ci/gate-suite-waits-out-real-clocks` — critical: Three tests wait out real 60-second clocks and are ~53% of every gate run: the suite's time-skipping Temporal env skips workflow timers but cannot skip an in-flight activity, and ScriptedWorld's heartbeat_then_block leaves the activity running so real heartbeat timeouts must elapse. The gate pays ~3 idle minutes on every attempt, several times per node.

Refine the approach before the spec is readied.
