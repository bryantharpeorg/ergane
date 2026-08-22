# US5 T033 / SC-002 — a SIGKILLed worker's node is rescheduled in ~2 minutes

Run 2026-08-22 against this host's live Temporal (Server 1.31.2, namespace
`default`) by the script committed beside this file:

```
uv run python specs/082-an-epic-finishes-on-the-code-it-started-with/evidence/us5_dead_worker_evidence.py
```

Output, verbatim:

```
attempt deadline                     14400s (4h)
heartbeat timeout, before this story 7200s
heartbeat timeout, shipped derivation 120s (cap 120s)

last heartbeat the server received   2026-08-22T22:05:56.902Z  (attempt 1)
SIGKILL delivered to the worker      2026-08-22T22:05:56.992Z  (exit -9)
replacement attempt scheduled        2026-08-22T22:07:58.811Z  (attempt 2)

kill -> replacement scheduled        121.8s
2026-08-19 baseline (half of 4h)     7200s
within the 3-minute bound            True
```

**121.8 seconds, against a 2026-08-19 baseline of ~2 hours.** The two timestamps
that decide it are the server's own: `last_heartbeat_time` on the pending
activity for the kill point, and `scheduled_time` on attempt 2 for the
replacement. Neither is this script's clock. The interval is the heartbeat
timeout (120s) plus the 1.8s the last beat was already stale by — the worker was
running the production beat cadence (`factory.worker._heartbeat_cadence_limits`,
5s), so staleness is bounded by that and not by the attempt's deadline.

The attempt was configured exactly as the real one is: a four-hour
`start_to_close_timeout`, `maximum_attempts=2`, and a `heartbeat_timeout` taken
from the shipped `_agent_heartbeat_timeout` rather than typed into the probe —
which is why the same run prints what that call returned before this story
(7200s) beside what it returns now.

## What was killed, and what was not

The worker killed is a subprocess the script starts, **not**
`ergane-worker.service`. This node is itself an attempt running on that unit:
SIGKILLing it would have timed out the activity running this agent, rescheduled
this node, and reaped the process writing these words — the story would have
destroyed its own evidence. The mechanism is unchanged by the substitution. An
uncleanly killed worker stops heartbeating; the server notices when the timeout
elapses; the number this story moved is the only thing that decides when. The
kill is a process-*group* `SIGKILL` to a session-leading subprocess (`exit -9`),
so nothing shut down politely and nothing drained.

A replacement worker was started right after the kill — systemd's
`Restart=on-failure` is what does that in production. It cannot make the server
declare attempt 1 dead any sooner, because only the heartbeat timeout does that,
so the 121.8s above is the timeout's interval and not the restart's.

Namespace `default` rather than `factory`, following 079's US2 evidence: the
`factory` namespace holds the epic that dispatched this node, and probe runs
must not appear where an operator reads for real.

## The false positive this makes routine (US5-S4)

A tighter bound means the server will sometimes declare a live agent dead. That
path is already load-bearing and already landed: the retry dispatches into the
same worktree, and the adapter reaps the recorded predecessor process group
before launching (`factory/workgraph/adapter.py` — `pid_file`, `_reap`). The
suite proves it end to end, including the control that a node with no recorded
predecessor kills nothing and the placement of the record outside the diffed
tree (`tests/test_adapter.py`).
