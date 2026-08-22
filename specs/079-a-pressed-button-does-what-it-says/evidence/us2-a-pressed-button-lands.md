# US2 — a pressed button lands, or the operator is told why

Evidence for SC-004 (T020) and SC-005 (T021). Regenerate with:

```
uv run python specs/079-a-pressed-button-does-what-it-says/evidence/us2_press_evidence.py
```

The generator is committed beside this file (`us2_press_evidence.py`); everything
below is its stdout, pasted rather than described (constitution VIII).

## What SC-005 could and could not be on this host, stated plainly

The spec asks for a press on a **real escalation** on the **live bridge**. Two
facts about this worktree, neither of them worked around:

1. **There is no live escalation to press.** `find / -name verification.db`
   outside pytest's temp base returns nothing: this host has no installed
   evidence store, so `ergane escalations list` has nothing to list. Trap 12
   says to say so and paste the closest constructed equivalent, which is what
   follows.
2. **A live escalation must not be pressed by a node anyway.** `CLAUDE.md`'s
   standing rule is "never press an escalation button on the operator's behalf",
   and the one workflow running in the `factory` namespace right now is
   `epic-079-a-pressed-button-does-what-it-says` — the epic that dispatched this
   node. Nothing here touches it. The evidence workflow below runs in the
   `default` namespace, on its own task queue, under its own generated id.

So the press below is real in every part the host can supply and stood in for in
exactly one:

| Part | Real? |
| --- | --- |
| Temporal server | **yes** — `127.0.0.1:7233`, the live one on this host |
| The workflow receiving the signal | **yes** — started, signalled, and it returned the signal it heard as its own result |
| The signal | **yes** — `escalation_resolved(escalation_id, choice)`, same name and arity as the interpreter's |
| The escalations store | **yes** — a real SQLite store through `factory/verify/store.py`, DDL and guarded UPDATE included |
| `CallbackBridge` | **yes** — the shipped class, unpatched |
| The Telegram Bot API | **no** — `scripts/ergane-env.sh` needs `sops`, which is not on this worktree's PATH, so there is no `TELEGRAM_BOT_TOKEN` here and no bridge process polling. The callback query is an object with the two methods the bridge calls (`answer`, `edit_message_text`); what it recorded is printed verbatim below. |

The one thing the substitution costs is proof that Telegram delivers the toast.
It costs nothing on the two facts the story is about: the signal reached a real
workflow, and the real store's real row moved.

## Output

```text
==============================================================================
T020 / SC-004 — the press path, walked from the code
==============================================================================
CallbackBridge.handle's call graph (follow `self.<method>(...)` transitively):

  _answer                0 return(s) at lines []
  _answer_settled        3 return(s) at lines [902, 911, 920]
  _edit                  0 return(s) at lines []
  _handle_press          8 return(s) at lines [560, 578, 589, 600, 607, 613, 627, 637]
  _record                1 return(s) at lines [985]
  _refuse_unauthorized   2 return(s) at lines [789, 797]
  _signal                2 return(s) at lines [879, 880]
  handle                 3 return(s) at lines [509, 517, 535]

  19 returns in total.

Every branch driven, and what it produced:

branch                          outcome           signal  row       told  recorded
----------------------------------------------------------------------------------
live_escalation                 RESOLVED          sent    RETRY     yes   yes
not_a_callback                  MALFORMED         —       pending   n/a   yes
payload_from_elsewhere          MALFORMED         —       pending   yes   yes
unauthorized_sender             UNAUTHORIZED      —       pending   yes   yes
row_is_gone                     UNKNOWN           —       pending   yes   yes
choice_never_offered            INVALID_CHOICE    —       pending   yes   yes
stale_already_resolved          ALREADY_RESOLVED  —       KILL      yes   yes
stale_expired                   EXPIRED           —       EXPIRED   yes   yes
orchestrator_unreachable        SIGNAL_FAILED     —       pending   yes   yes
stale_race_to_expiry            EXPIRED           sent    EXPIRED   yes   yes
row_vanishes_mid_signal         UNKNOWN           sent    gone      yes   yes
row_this_build_cannot_read      BRIDGE_ERROR      —       pending   yes   yes
store_fails_after_the_signal    BRIDGE_ERROR      sent    pending   yes   yes
telegram_refuses_the_toast      RESOLVED          sent    RETRY     yes   yes

returns reached by the table above: 19/19   unreached: none

Every row is one of {signal sent + row resolved} or {a named refusal}, and every row is recorded (FR-006, FR-007).

==============================================================================
T021 / SC-005 — one press, against this host's Temporal and a real store
==============================================================================
temporal      : 127.0.0.1:7233, namespace 'default'
workflow      : us2-evidence-b3ee8ff0 (EvidenceEscalationWaiter)
escalation    : dc593059e21f
store         : /tmp/tmp4c2cjul4/.factory/verification.db

row before the press:
  escalation_id='dc593059e21f' | workflow_id='us2-evidence-b3ee8ff0' | choices='["RETRY", "KILL"]' | resolution=None | resolved_at=None | resolved_via=None

press:
  callback_data = 'esc:dc593059e21f:RETRY'

outcome       : RESOLVED

signal, as the workflow itself returned it:
  escalation_resolved('dc593059e21f', 'RETRY')

row after the press:
  escalation_id='dc593059e21f' | workflow_id='us2-evidence-b3ee8ff0' | choices='["RETRY", "KILL"]' | resolution='RETRY' | resolved_at='2026-08-22T03:26:41Z' | resolved_via='BUTTON'

what the operator was told:
  toast: RETRY recorded.
  message now reads: ✅ Escalation resolved …

what the journal recorded (FR-007):
  escalation dc593059e21f: press RESOLVED — RETRY signalled to us2-evidence-b3ee8ff0 and recorded

The workflow completed on the signal, so the decision reached it: the `heard` list above is the workflow's own return value, not a recorder's.
```

## Reading the SC-004 table

- **`signal` + `row`** are FR-006: every row is either `sent` with the row
  carrying the choice, or a refusal that sent nothing and moved nothing. No row
  is blank in both columns — that combination is what happened at 03:16Z.
- **`told`** is the named refusal reaching the operator. `n/a` appears once, for
  the update that carries no callback query at all: there is no query to answer,
  which is exactly why the next column has no exceptions.
- **`recorded`** is FR-007: the journal line naming the escalation. It reads
  `yes` for all fourteen branches.
- **`returns reached: 19/19`** is the enumeration itself. The 19 came from
  walking `CallbackBridge.handle`'s call graph in the AST, not from a list
  anyone wrote. Drop one branch from the registry and the count drops with it —
  `tests/test_pressed_button_reaches_the_store.py::test_every_return_in_the_press_path_is_taken_by_a_branch`
  is the guard, and removing `row_vanishes_mid_signal` while building this made
  it fail with `['_answer_settled:902']`.

The two rows that did not exist before this story are
`row_this_build_cannot_read` and `store_fails_after_the_signal`. Both used to
leave `handle` as an exception — no signal, no row change, no line naming the
escalation — and both are now `BRIDGE_ERROR` with a notice and a record. They
are told apart because the operator's next move is opposite: the first says
press again, the second says do not.

## Suite

```
$ uv run pytest -q
4177 passed, 52 skipped, 7 warnings in 326.02s (0:05:26)
```

```
$ uv run pytest tests/test_pressed_button_reaches_the_store.py -q
39 passed in 0.14s
```
