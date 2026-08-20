"""What resetting one node means on a forge (069-US3, FR-010/FR-011).

`ergane build reset` archives a terminated epic's local survivors so it can be
relaunched. Until this story it stopped there, and the forge kept the rest: the
proposal the dead attempt offered, and the head it pushed. A rebuilt node
branches from the base again, so its first push is not a descendant of what the
remote holds and the push is refused — non-fast-forward, during a recovery, with
the remedy written down nowhere.

Two rules shape everything here.

**The factory owns `factory/<epic>/<node>` and nothing else** (US3-S4). Every
forge call this module issues is addressed by one head, and `NODE_HEAD` is what
says a head is that shape. A cleanup verb that closed a pull request an operator
opened by hand would be a far worse defect than the one being fixed, so the
namespace is checked at the one place all of it is addressed from rather than
trusted to each caller — a node id that arrived carrying a slash is refused here
instead of reaching a namespace nobody meant.

**Undone is reported, never raised** (US3-S5, FR-011). A forge that cannot be
reached must not abort the reset: the local half is what the operator is
recovering with, and a verb that fails whole leaves them in exactly the state it
exists to clear. Each half is attempted separately, so a forge that answers the
first call and drops the second reports one done and one not.

This module decides; it does not spawn anything. The forge behind it is resolved
by the caller, which is why the tests can put a repository model, a real git
origin, or a recorded `gh` transcript behind the same three calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from factory.mergequeue.forge import Forge, ForgeError

#: The one head shape a reset owns: `factory/<epic>/<node>`, exactly three parts.
#: Spelled as a pattern rather than derived from `branch_name` on purpose — this
#: is the *guard*, and a guard that re-uses the thing it guards against would
#: accept whatever that produced.
NODE_HEAD = re.compile(r"^factory/[^/]+/[^/]+$")


@dataclass(frozen=True)
class ForgeReset:
    """What one node's forge cleanup came to: what was done, and what was not.

    Both halves are carried because both are true at once — a forge that closed
    the proposal and then stopped answering has done half the work, and an
    operator told only about the failure would re-close a closed proposal while
    the head they actually need gone stays.
    """

    done: tuple[str, ...] = ()
    not_done: tuple[str, ...] = ()


def archive_prefix(head: str) -> str:
    """Where `head`'s tip is kept once the head is gone.

    `archive/factory/<epic>/<node>`, so a retired head reads on the forge exactly
    as `worktree.py`'s archived branch reads locally; the forge appends the tip's
    own short sha, which is what makes the write idempotent (the ref names its
    own content).
    """
    return f"archive/{head}"


def reset_note(epic_id: str, node_id: str) -> str:
    """The comment a closed proposal carries, naming the reset that closed it.

    An operator who finds a pull request shut with no comment cannot tell a
    factory verb from somebody's mistake, so this names the command, the epic and
    the node, and says the work is not lost.
    """
    return (
        f"Closed by `ergane build reset` for epic {epic_id}, node {node_id}. "
        f"The epic was terminated and reset so it can be rebuilt; this node's "
        f"branch was archived and its head removed from this repository, which "
        f"is what lets the rebuilt node push. No commit was deleted — the tip "
        f"is kept under archive/factory/{epic_id}/{node_id}/."
    )


def reset_node_on_forge(forge: Forge, *, head: str, note: str) -> ForgeReset:
    """Close the open proposal for `head` and retire `head`, reporting both.

    Raises `ValueError` for a head outside `factory/<epic>/<node>`: that is a
    caller bug, not a forge failure, and it is the one thing here that must stop
    rather than degrade — a reset reaching outside its namespace is the defect
    trap 8 names, and reporting it as "not done" would let it be retried against
    something the factory does not own.

    Every *forge* failure is data. The two halves are independent calls so that
    losing one does not hide the other.
    """
    if not NODE_HEAD.match(head):
        raise ValueError(
            f"refusing to reset {head!r} on the forge: a reset acts only on "
            "heads named factory/<epic>/<node>, and nothing else (FR-010)"
        )

    done: list[str] = []
    not_done: list[str] = []

    try:
        proposal = forge.find_proposal(head)
        if proposal is None:
            done.append(f"no open pull request for {head}")
        else:
            forge.close_proposal(proposal.number, note=note)
            done.append(f"closed pull request #{proposal.number}")
    except ForgeError as error:
        not_done.append(
            f"the open pull request for {head} is still open "
            f"(close it by hand): {error}"
        )

    try:
        retired = forge.retire_head(head, archive_prefix=archive_prefix(head))
        done.append(retired or f"no {head} on the forge")
    except ForgeError as error:
        not_done.append(
            f"{head} is still on the forge and a rebuilt node cannot push over "
            f"it (delete the branch by hand): {error}"
        )

    return ForgeReset(tuple(done), tuple(not_done))
