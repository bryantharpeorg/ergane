# Attempt report — 095 US3, *an exhausted ladder names the rung that ended it*

Two tasks are answered here: T027 (FR-010's two untouched things) and T028 (the
operator's dead-credential demonstration). Everything below is pasted tool
output, not description.

## T027 — FR-010: what this epic did not change

FR-010 names two things every story of this epic must leave alone: the veto that
decides whether the rewrite dial may stop a granted retry, and `next_action`'s
precedence order. Checked across the **whole epic** — US1, US2 and US3 together —
because FR-010 binds every story and only the epic-wide diff can say whether one
of them moved it.

`8c6e8f7` is the commit before US1 landed; `03774cc` is the branch base for this
story (US2 landed); `HEAD` is this story's work.

**The veto is byte-identical across the epic** — same line count, same byte
count, same checksum before US1 and after US3:

```console
$ for R in 8c6e8f7 HEAD; do
    git show $R:factory/verify/ladder.py \
      | sed -n '/^def _judge_vetoes_a_retry/,/^def _judge_rewrites_spent/p' | wc -lc
    git show $R:factory/verify/ladder.py \
      | sed -n '/^def _judge_vetoes_a_retry/,/^def _judge_rewrites_spent/p' | md5sum
  done
     25    1236
c6137adbe85d54591fbd6d1a2e893e00  -
     25    1236
c6137adbe85d54591fbd6d1a2e893e00  -
```

**No changed line in the epic's whole ladder diff so much as spells the veto or
any of the three actions that produce work** — the arms a reordering would have
to touch:

```console
$ git diff 8c6e8f7 HEAD -- factory/verify/ladder.py \
    | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' \
    | grep -cE '_judge_vetoes_a_retry|NextAction\.(RETRY|PROMOTE|DEBUGGER)'
0
```

**The precedence order is the same four steps, in the same order.** The one
statement the epic added inside `next_action` is US2's own FR-006 — a new
*bound*, escalating through the same escalate path — and it sits above the four
rather than among them:

```console
$ for R in 8c6e8f7 HEAD; do echo "--- $R"; git show $R:factory/verify/ladder.py \
    | sed -n '/^def next_action/,/^def _ends_the_node/p' | grep -E 'return NextAction'; done
--- 8c6e8f7
        return NextAction.KILLED
        return NextAction.PASSED
        return NextAction.RETRY
        return NextAction.PROMOTE
        return NextAction.DEBUGGER
    return NextAction.ESCALATE
--- HEAD
        return NextAction.KILLED
        return NextAction.PASSED
        return NextAction.ESCALATE
        return NextAction.RETRY
        return NextAction.PROMOTE
        return NextAction.DEBUGGER
    return NextAction.ESCALATE
```

The third line of the `HEAD` listing is the added one: US2's pre-agent bound,
escalating before the grant because the grant's own allowance never sees a
pre-agent failure. `RETRY`, `PROMOTE`, `DEBUGGER`, `ESCALATE` follow it in the
order they have always been in.

**This story changed nothing in `next_action` at all** — byte-identical between
the branch base and `HEAD`, which is what "US3 renders, it does not recompute"
(plan trap 5) has to mean at the level of the file:

```console
$ for R in 03774cc HEAD; do echo -n "$R  "; git show $R:factory/verify/ladder.py \
    | sed -n '/^def next_action/,/^    return NextAction.ESCALATE$/p' | md5sum; done
03774cc  7f084fc3b41d9b22618b06c3f7c6b215  -
HEAD  7f084fc3b41d9b22618b06c3f7c6b215  -
```

## T028 — the dead-credential demonstration

### What was run, and the one substitution

The plan asks for `ergane build start` against a persona routed to a
**deliberately invalidated subscription session**, then `ergane build status`
within a minute. **That form was not run, and it was not mine to run.** It needs
the operator's own agent session on the worker host broken on purpose, and this
factory's worker is shared: invalidating that credential would have failed every
other node in flight, not only a node of mine. It also needs a worker running
*this* branch, and the worker imports factory code live from the landing branch —
CLAUDE.md's "never modify factory code while an attempt is in flight" cuts both
ways, and a dispatch from inside a node worktree would have been served by code
without any of this story in it.

So the demonstration was run against the **real interpreter** instead: one real
`EpicWorkflow`, one node, four attempts in which the agent process never
produced a token, driven through the real ladder, the real escalation child, the
real message composer and the real `render_status`. The one substitution is the
agent activity — the suite's fake reports the termination but carries no
`detail`, so it is wrapped to return the measured 73-byte line verbatim:
`Failed to authenticate: OAuth session expired and could not be refreshed`. The
gates are left failing, because a worktree no agent prepared genuinely fails them
(plan trap 3) and hiding that would be demonstrating a different thing.

The driver lives outside the worktree and is not in the diff; the output is its.

### The operator's page

```console
$ uv run ergane build status demo-loans
epic demo-loans  RUNNING  execution RUNNING
ladder dials
  max_attempts       3
  max_judge_retries  2
  debugger_cycles    1
landing dials
  --merge-method             squash  default
  --landing-poll-interval-s      60  default
  --stall-after-s              7200  default
  --max-recovery-cycles           1  default
  --max-free-rebases              3  default
us1  VERIFYING  attempt 4  factory/demo-loans/us1  persona implementer  model implementer-alias  base 999999999999  landing head unavailable
  no agent turn ran: the process exited before producing a single token, so nothing was attempted of the story and the gates for this attempt ran against a worktree no agent prepared — their results describe the environment, not the work. the process's last words: "Failed to authenticate: OAuth session expired and could not be refreshed" authentication: the worker host's agent session was refused. remedy: re-authenticate on the worker host (`claude login` for a subscription-routed persona, or reissue the node's proxy key), then re-dispatch.
```

### The escalation

The four attempt blocks of the history are identical in shape; the second and
third are cut here and marked. Nothing else is elided.

```console
⚠️ Verification escalation
epic: demo-loans
node: us1

Attempt 1 — FAIL
  gate test: FAIL (exit 1, 9.0s)
── test output ──
E   AssertionError: attempt-one recorded no loan against the member

[attempts 2 and 3 cut — same shape]

Attempt 4 — FAIL
  gate test: FAIL (exit 1, 9.0s)
── test output ──
E   AssertionError: attempt-four debugger left the ledger unwritten

ladder exhausted: max_pre_agent_failures = 4 — 4 consecutive attempts ended before the agent produced a token, so no rung of the ladder ever ran. Re-authenticate on the worker host; another attempt buys nothing until that is done

What each button does:
RETRY (🔁 Retry the node) — node: one more attempt, on the tree this one left behind. epic: unchanged — it keeps dispatching.
KILL (🛑 Kill the node) — node: ends KILLED, its branch preserved. epic: keeps dispatching, but every node waiting on this one is locked out and ends KILLED with it, undispatched.
PAUSE_EPIC (⏸️ Pause the epic) — node: ends parked, not killed — nothing waiting on it is locked out. epic: stops dispatching until you resume it; the undispatched nodes keep their place and run then.
KILL_EPIC (💥 End the whole epic) — node: ends KILLED, its branch preserved. epic: ends with it — nothing else dispatches, and any other node's open page is cancelled unanswered.

No answer by 2026-08-31T15:17:43Z applies the default: PAUSE_EPIC the node.
```

```console
--- the ladder's accounting ---
attempts recorded: 4
history: [(1, 'implementer', True), (2, 'implementer', True), (3, 'implementer', True), (4, 'implementer', True)]
```

### Against the plan's three conditions

- **The status names authentication.** Line 2 of the node's block: the reason,
  the process's own last words, and `remedy: re-authenticate on the worker host`
  — on screen, with no transcript opened (US1's FR-002, still holding).
- **The attempt count has not run past the new bound.** Four attempts, all four
  flagged pre-agent, under `max_pre_agent_failures = 4`; `max_attempts` is 3 and
  none of it was spent, which is US2's exclusion visible from outside.
- **The escalation names the remedy, and does not offer KILL as its default.**
  `applies the default: PAUSE_EPIC the node` — a dead credential is fixed by
  re-authenticating, not by killing the node (US2's FR-007).

**Before this spec the same run showed four attempts, a typecheck failure naming
a missing binary, and nothing about a credential anywhere.** All three lines the
page now carries are new: the note is US1's, the accounting is US2's, and the
`ladder exhausted:` line is this story's.

### The other two bounds

The demonstration exercises the pre-agent bound, because that is the incident the
spec was written from. The other two sentences, from the same function, on the
histories US3-S1 and US3-S2 name (`tests/test_095_the_ladder_names_its_bound.py`
asserts them through a real escalation; this is the text itself):

```console
judge rewrites spent, three attempts left:
  ladder exhausted: max_judge_retries = 2 — the judge has asked for more rewrites than this dial allows, and 3 of max_attempts = 6 are unspent. Raising max_attempts alone will not lengthen this fight
deterministic attempts spent:
  ladder exhausted: max_attempts = 3 — every ordinary attempt is spent: 3 of them were charged to this story
debugger cycles spent:
  ladder exhausted: debugger_cycles = 1 — the debugger rung is the last one the ladder has, and its cycles are spent. It is bounded on its own dial, so granting more attempts does not buy another cycle
```

The first of those is the nine-attempt run the spec opens with: three attempts
unspent, and the dial with the obvious name is not the one that would have bought
them.

## This story's own change, in one line

The ladder now reports which of its bounds produced an `ESCALATE`, in a sentence
composed beside the decision that produced it; the escalation carries that
sentence into its footer where the clip cannot take it, and `ergane build status`
prints the three dials in force beside the landing dials — degraded, never
guessed, when a worker cannot report them.
