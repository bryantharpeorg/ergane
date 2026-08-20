"""Why the queue rejected a landing — one pure decision over structural facts.

`classify` answers *what* the queue said; this answers *whose fault it was*, and
it is a separate question because the two have different consequences. A
rejection the node caused is what an attempt budget exists to bound. A rejection
caused by a sibling landing first is the world moving, and charging a node for
that exhausts a node that never had a defect — the failure 069 exists to fix.

Pure, for the same reason `classify` is (constitution IV): `(outcome, two base
shas)` in, a `RejectionCause` out. No filesystem, no `gh`, no clock. It reads no
retry count and no message text, and it *cannot* — neither is a parameter
(FR-005). That is deliberate:

- **A retry count is not a cause.** "This has failed twice, so it must be the
  node" is a guess that gets a defect-free node killed on its second unlucky
  sibling, and it gets a genuinely broken node a free ride on its first.
- **A message is not a cause either.** The forge's rejection wording is prose it
  may reword between releases, and a classifier keyed on it looks like it works
  right up until the day it silently classifies everything as one thing. The
  facts here are already structural, and they were already in the record before
  this module existed.

The two facts, and what each is:

- **`QueueOutcome.CONFLICT`** is the forge's own observation that *the target
  has moved under this proposal and it no longer applies as it stands*
  (`PrSnapshot.in_conflict`, `models.py`) — the factory's vocabulary for it,
  already translated at the boundary from whatever the forge spells it. There is
  no reading of that fact under which the node's tree is what changed.
- **A base that advanced under an enqueued tree.** `Landing.enqueued_base` is
  the target head the tree was built and offered against; the base the forge
  reports at the poll is the target head now. Different heads mean something
  landed in between, and the checks that failed ran against a world the node was
  never shown. Equal heads mean the tree was tested against exactly the base it
  was built on — and then a failing required check is about the tree.

Those two are distinct causes rather than two spellings of one: a conflict is
observed by the forge and needs no base comparison, and a base that advanced is
computed from two shas and needs no conflict. Either alone is enough.

An **unknown** base — `None` on either side — is not "it did not move". It is a
pre-069 landing replaying, or a forge that reports no base, and it is classified
`NODE_CODE` so that the node is charged exactly as it was before this module
existed. The free path is opt-in on a fact actually observed, never on the
absence of one.
"""

from __future__ import annotations

from factory.mergequeue.models import QueueOutcome, RejectionCause


def rejection_cause(
    outcome: QueueOutcome,
    *,
    enqueued_base: str | None,
    observed_base: str | None,
) -> RejectionCause:
    """Whose fault one queue rejection was: the world's, or the node's.

    `outcome` is what `classify` made of the poll. `enqueued_base` is the target
    head the rejected tree was offered against (`Landing.enqueued_base`);
    `observed_base` is the target head the forge reported at the poll
    (`PrSnapshot.base_sha`). Compared by value, not by identity: both are shas
    that have crossed a payload boundary.
    """
    if outcome == QueueOutcome.CONFLICT:
        # The forge saw the target move under the proposal. No comparison is
        # needed and none would add anything — this *is* the base moving.
        return RejectionCause.BASE_MOVED
    if outcome == QueueOutcome.CHECKS_FAILED and base_moved(
        enqueued_base, observed_base
    ):
        return RejectionCause.BASE_MOVED
    return RejectionCause.NODE_CODE


def base_moved(enqueued_base: str | None, observed_base: str | None) -> bool:
    """Whether the target advanced under a tree between offer and observation.

    Two shas that are both known and differ. Either one unknown answers False:
    an absent reading is not evidence of stillness, and the caller charges the
    node when it cannot tell.
    """
    if enqueued_base is None or observed_base is None:
        return False
    return enqueued_base != observed_base
