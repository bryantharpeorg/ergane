# `ergane answer`

> answer an operator question by its correlation id

```
ergane answer <correlation-id> <text> [--as WHO]
```

| argument | default | meaning |
| --- | --- | --- |
| `<correlation_id>` | — | the id the delivery quoted |
| `<text>` | — | the answer, carried into the next attempt **verbatim** |
| `--as` | `unknown` | who is answering, spelled as `escalation.authorized_responders` spells them |

## When to use this rather than `build answer`

Use `ergane answer` when the question reached you **over a transport** — a chat
message, a notification — and that delivery quoted a correlation id. You do not
need to know which epic it came from; the id resolves it.

Use [`ergane build answer <epic-id>`](build.md) when you are already looking at
an epic and want to see its pending questions listed.

Use [`ergane build resolve`](build.md) for an **escalation**, which is a fixed
choice rather than free text. Answering an escalation with prose does not
resolve it.

## `--as`

Only needed where `escalation.authorized_responders` is configured. Spell the
identity exactly as that list spells it; an unrecognised responder is not a
partial match.

## The text is carried verbatim

Whatever you type reaches the next attempt as-is. It is not summarised,
reformatted or interpreted on the way. Write it as an instruction to the agent
that will read it, including whatever context the agent lacks — it can see its
own worktree and its brief, and not your terminal.

An unanswered question dead-waits its window and then pages you anyway, so
answering is cheaper than ignoring.

## See also

- [`ergane build answer`](build.md) — list and answer one epic's questions
- [`ergane escalations list`](escalations.md) — the fixed-choice channel
