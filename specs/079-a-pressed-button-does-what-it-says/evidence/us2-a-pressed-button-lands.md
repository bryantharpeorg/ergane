# US2 — a pressed button lands, or the operator is told why

Every block below is pasted stdout, with the command that produced it, run
against this committed tree (constitution VIII).

## T020 / SC-004 — the press path, enumerated from the code

Printed by the test that asserts it, so table and assertion cannot disagree:

```
uv run pytest -s -k every_return tests/test_pressed_button_reaches_the_store.py
```

```text
CallbackBridge.handle's call graph (follow `self.<method>(...)` transitively):

  _answer                0 return(s) at lines []
  _answer_settled        3 return(s) at lines [884, 893, 902]
  _edit                  0 return(s) at lines []
  _handle_press          8 return(s) at lines [548, 566, 577, 588, 595, 601, 615, 625]
  _record                1 return(s) at lines [960]
  _refuse_unauthorized   2 return(s) at lines [775, 783]
  _signal                2 return(s) at lines [865, 866]
  handle                 3 return(s) at lines [499, 507, 524]

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
```

`signal` + `row` are FR-006: every row is either `sent` with the row carrying
the choice, or a refusal that sent nothing and moved nothing — never blank in
both, which is what happened at 03:16Z. `told` is the refusal reaching the
operator; `n/a` appears once, for the update carrying no callback query, which
is why `recorded` (FR-007) has no exceptions. `19/19` comes from walking
`handle`'s call graph in the AST, not from a list anyone wrote (trap 8).

`row_this_build_cannot_read` and `store_fails_after_the_signal` did not exist
before this story. Both used to leave `handle` as an exception — no signal, no
row change, no line naming the escalation — and both are now `BRIDGE_ERROR` with
a notice and a record. They are told apart because the operator's next move is
opposite: the first says press again, the second says do not.

### The enumeration is measured, not asserted

Deleting the `row_vanishes_mid_signal` entry from `BRANCHES` and re-running:

```text
E  AssertionError: these returns in CallbackBridge.handle's call graph are branches
   no scenario reaches, so nobody can say what a press through them does:
   ['_answer_settled:884']
1 failed, 14 passed, 22 deselected
```

The *other* two enumerations passed on that run: `BridgeOutcome.UNKNOWN` was
still produced by `row_is_gone`, so the outcome check saw full coverage while a
distinct branch producing it had gone untested. That is why the return walk is
the primary check.

## T021 / SC-005 — one real press

```
uv run python specs/079-a-pressed-button-does-what-it-says/evidence/us2_press_evidence.py
```

SC-005 asks for a press on a real escalation on the live bridge. This host has
no live escalation — no `verification.db` outside pytest's temp base — and a node
must not press one anyway (`CLAUDE.md`: never press an escalation button on the
operator's behalf; the only workflow in the `factory` namespace is the epic that
dispatched this node, and nothing here touches it). So, per trap 12, the closest
constructed equivalent, real in every part this host can supply: real Temporal
at `127.0.0.1:7233`, a real workflow that receives the signal and returns what it
heard, a real SQLite store through `factory/verify/store.py` including the
guarded UPDATE, and the shipped `CallbackBridge`, unpatched — in the `default`
namespace, on its own task queue and id.

The one substitution is the Bot API: `scripts/ergane-env.sh` needs `sops`, absent
from this worktree's PATH, so the callback query is an object with the two
methods the bridge calls. That costs proof that Telegram delivers the toast, and
nothing on the two facts the story is about: the signal reached a real workflow,
and the real row moved.

```text
==============================================================================
T021 / SC-005 — one press, against this host's Temporal and a real store
==============================================================================
temporal      : 127.0.0.1:7233, namespace 'default'
workflow      : us2-evidence-ce86c855 (EvidenceEscalationWaiter)
escalation    : 4fc53d2bf531
store         : /tmp/tmp8eg4xbtk/.factory/verification.db

row before the press:
  escalation_id='4fc53d2bf531' | workflow_id='us2-evidence-ce86c855' | choices='["RETRY", "KILL"]' | resolution=None | resolved_at=None | resolved_via=None

press:
  callback_data = 'esc:4fc53d2bf531:RETRY'

outcome       : RESOLVED

signal, as the workflow itself returned it:
  escalation_resolved('4fc53d2bf531', 'RETRY')

row after the press:
  escalation_id='4fc53d2bf531' | workflow_id='us2-evidence-ce86c855' | choices='["RETRY", "KILL"]' | resolution='RETRY' | resolved_at='2026-08-22T03:59:46Z' | resolved_via='BUTTON'

what the operator was told:
  toast: RETRY recorded.
  message now reads: ✅ Escalation resolved …

what the journal recorded (FR-007):
  escalation 4fc53d2bf531: press RESOLVED — RETRY signalled to us2-evidence-ce86c855 and recorded

The workflow completed on the signal, so the decision reached it: the `heard` list above is the workflow's own return value, not a recorder's.
```

## Suite

```
$ uv run pytest -q
4177 passed, 52 skipped, 6 warnings in 320.81s (0:05:20)

$ uv run pytest -q tests/test_pressed_button_reaches_the_store.py
39 passed in 0.16s
```
