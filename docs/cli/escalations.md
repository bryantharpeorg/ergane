# `ergane escalations`

> what is waiting on you

```
ergane escalations list [--json]
```

Read the escalations a human still has to answer, **sourced from the workflows
holding them open** rather than from the store. That is the important property:
the answer is what is actually blocking right now, not what was written down at
the time.

```
$ ergane escalations list
no open escalations
```

`--json` prints them as a document instead of the human view.

## What an escalation is

A node has exhausted its retry ladder and the workflow has stopped to ask a
human which way to go. It offers a **fixed set of choices** — that is the
difference from an operator *question*, which takes free text and is answered
with [`ergane build answer`](build.md) or [`ergane answer`](answer.md).

Record a choice with:

```bash
ergane build resolve <epic-id> <escalation-id> <choice>
```

## Silence is a legitimate answer

Escalations expire, and expiry is part of the contract rather than a failure of
it. An escalation left unanswered ends the way the workflow says it ends, which
is a decision the operator is entitled to make by doing nothing.

This matters most for anything acting on an operator's behalf: an automated
actor that presses a button because a deadline is approaching has substituted
its judgement for the operator's silence, and the measured record on this
factory is that verified work is lost in the landing path by confident automated
actors far more often than by agents writing bad code.

## Reading the offered choices

The set of choices an escalation offers is itself information — it is the
workflow telling you what it still has budget for. A retry that is *not* offered
is a retry the ladder cannot afford, and choosing to end a node is a different
decision when there was a retry available than when there was not.

Read the real clock before pressing anything with a deadline on it. An
escalation's remaining window is measured from when it opened, not from when you
started looking at it.

## See also

- [`ergane build resolve`](build.md) — record the choice
- [`ergane build answer`](build.md) — the free-text channel, for questions rather than escalations
- [`ergane answer`](answer.md) — answer by correlation id, over any transport
