# 127-US4 — the landing escalation names its exhausted dial

T027. The two operator messages the story's acceptance scenarios ask to be read,
pasted from the tests that assert them (`tests/test_127_us4_landing_escalation_names_its_bound.py`,
run with `uv run pytest -q -s -p no:randomly` in this worktree on 2026-09-07).
Timestamps are the test run's own; the sentences are the shipped renderer's.

## US4-S1 — recovery cycles spent: the bound is named

The shipped default (`max_recovery_cycles = 1`): one landing rejected, the
automatic recovery cycle spent on it, its re-enqueue rejected again — the
scheduler pages with the budget gone. The bound sentence names the dial and its
configured value, in the shape `ExhaustedBound.describe` produces and the
verification path has printed since 095:

```
⚠️ Verification escalation
epic: demo-loans
node: us1

CHECKS_FAILED at 2026-09-07T02:58:11Z (failing checks: lint)
CHECKS_FAILED at 2026-09-07T02:58:11Z (failing checks: lint)
Recovery cycles: 1

ladder exhausted: max_recovery_cycles = 1 — the landing's recovery allowance is spent: the recovery cycle ran and the queue rejected it again. Another cycle buys another rejection of the same tree — grant one only to see it fail again

What each button does:
KILL (🛑 Kill the node) — node: ends KILLED, its branch preserved. epic: keeps dispatching, but every node waiting on this one is locked out and ends KILLED with it, undispatched.
PAUSE_EPIC (⏸️ Pause the epic) — node: ends parked, not killed — nothing waiting on it is locked out. epic: stops dispatching until you resume it; the undispatched nodes keep their place and run then.
KILL_EPIC (💥 End the whole epic) — node: ends KILLED, its branch preserved. epic: ends with it — nothing else dispatches, and any other node's open page is cancelled unanswered.

No answer by 2026-09-07T03:58:11Z applies the default: KILL the node.
```

The same page raised from the story's other exhaustion caller — `_run_recovery`'s
failed cycle rather than the scheduler's spent REJECTED pickup — carries the
identical sentence; that caller is pinned separately in the test module
(`test_the_failed_recovery_exhaustion_names_the_bound_too`).

## US4-S2 — a cycle remaining: no bound is named

The same rejection under `max_recovery_cycles = 2`: the automatic recovery spent
one cycle and the page goes out with a second still grantable. No bound line
appears — the RETRY button below is real, and a page naming
`max_recovery_cycles` as exhausted beside it would contradict the offer it makes:

```
⚠️ Verification escalation
epic: demo-loans
node: us1

CHECKS_FAILED at 2026-09-07T02:58:14Z (failing checks: lint)
Recovery cycles: 1

What each button does:
RETRY (🔁 Retry the node) — node: one more attempt, on the tree this one left behind. epic: unchanged — it keeps dispatching.
KILL (🛑 Kill the node) — node: ends KILLED, its branch preserved. epic: keeps dispatching, but every node waiting on this one is locked out and ends KILLED with it, undispatched.
PAUSE_EPIC (⏸️ Pause the epic) — node: ends parked, not killed — nothing waiting on it is locked out. epic: stops dispatching until you resume it; the undispatched nodes keep their place and run then.
KILL_EPIC (💥 End the whole epic) — node: ends KILLED, its branch preserved. epic: ends with it — nothing else dispatches, and any other node's open page is cancelled unanswered.

No answer by 2026-09-07T03:58:14Z applies the default: KILL the node.
```

The futile re-enqueue page — the story's third `_escalate_landing` caller,
which is not an exhaustion and offers RETRY unconditionally — is likewise
pinned naming no bound (`test_the_futile_reenqueue_page_names_no_bound`), and
the verification escalation's golden message is pinned byte-identical
(`test_a_verification_escalation_message_is_byte_identical`), so this story
altered no page 095 built.