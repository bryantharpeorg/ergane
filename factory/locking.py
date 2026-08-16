"""One exclusive-file-lock helper for every operator command that writes state.

033 FR-007 locks the control-plane config while `ergane install` runs; 034 FR-008
locks the repo registry. Both are the same problem — one writer at a time on one
path — so both get one implementation, here, rather than two conventions one
epic apart (033 plan, trap 5).

The lock is `flock(2)` on a sibling `<target>.lock` file, not on the target
itself. Locking the target would mean creating it before the operator has
answered a single question, and an aborted interview would leave an empty
`config.toml` behind — which every consumer would then read as a *malformed*
config rather than an absent one, losing FR-013's "run `ergane install`"
remedy. The sidecar keeps the target's absence meaningful.

`flock` is held by the open file description, so two `open()` calls contend even
inside one process, and the kernel releases the lock if the holder dies —
including by `SIGKILL`, which is what makes a crashed install recoverable
without an operator deleting a stale file by hand.
"""

from __future__ import annotations

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

#: How often a waiter retries while the lock is held.
DEFAULT_POLL_S = 0.05


class LockUnavailable(Exception):
    """Another process holds the lock and did not release it in time."""

    def __init__(self, target: str | Path, timeout_s: float) -> None:
        self.target = Path(target)
        self.timeout_s = timeout_s
        super().__init__(
            f"another process holds the lock on {self.target} "
            f"(waited {timeout_s:g}s)"
        )


def lock_path_for(target: str | Path) -> Path:
    """Return the lock file guarding ``target``."""
    path = Path(target)
    return path.with_name(path.name + ".lock")


@contextmanager
def exclusive_lock(
    target: str | Path,
    *,
    timeout_s: float = 30.0,
    poll_s: float = DEFAULT_POLL_S,
) -> Iterator[Path]:
    """Hold an exclusive lock on ``target`` for the duration of the block.

    Waits up to ``timeout_s`` for a lock another process holds, then raises
    `LockUnavailable`. ``timeout_s=0`` tries exactly once. The lock is released
    on every exit path, including an exception, and by the kernel if the process
    dies.
    """
    lock_file = lock_path_for(target)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + max(0.0, timeout_s)
    try:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LockUnavailable(target, timeout_s) from None
                time.sleep(min(poll_s, remaining))
        try:
            yield lock_file
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        os.close(handle)
