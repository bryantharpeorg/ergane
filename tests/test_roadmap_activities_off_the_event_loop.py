"""The roadmap's git-reading activities must not block the worker event loop.

Regression for the 2026-08-26 incident. `drift_for_spec` and `derive_spec` are
`async def` activities that shell git: `landed_facts` resolves the default head
through `subprocess.run(..., timeout=GIT_TIMEOUT_S)`, and `GIT_TIMEOUT_S` is
300 seconds. Both called it directly on the event loop.

One slow `git fetch` then held the loop for 5m12s. Everything else in the worker
stopped, including the heartbeat of an in-flight agent attempt — whose timeout
is 120 seconds — so Temporal killed a node that was working correctly, with 138
insertions already on disk. The roadmap schedule ticks every 300s, so the
exposure repeated every five minutes until the schedule was paused by hand.

These tests assert the *property*, not the implementation: while the activity is
inside its blocking git read, another coroutine still gets scheduled. A ticker
that never advances is the bug. Restore the direct call in either activity and
the matching test fails with `ticks == 0`.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from factory.activities import roadmap_activities as ra

#: How long the faked git read blocks for. Comfortably longer than the ticker's
#: interval so a non-blocked loop racks up an unambiguous number of ticks, and
#: short enough that the suite does not notice.
BLOCK_S = 0.30
TICK_S = 0.01

#: A blocked loop yields zero ticks. A free one yields ~30. Anything at or above
#: this is only reachable if the git read moved off the loop.
MIN_TICKS = 5


async def _count_ticks_while(coro: Any) -> tuple[Any, int]:
    """Run `coro`, counting how many times a rival coroutine gets scheduled."""
    ticks = 0
    stop = False

    async def ticker() -> None:
        nonlocal ticks
        while not stop:
            await asyncio.sleep(TICK_S)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        result = await coro
    finally:
        stop = True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return result, ticks


@pytest.mark.asyncio
async def test_drift_for_spec_does_not_block_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The activity that killed 109/us3 must leave the loop free."""

    def slow_landed_facts(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        time.sleep(BLOCK_S)  # stands in for subprocess.run on a slow fetch
        return {}

    monkeypatch.setattr(
        "factory.workgraph.landed.landed_facts", slow_landed_facts, raising=True
    )
    monkeypatch.setattr(ra, "landing_branch", lambda _p: "ergane-buildout")
    monkeypatch.setattr(ra, "_drift_runner", None)

    request = ra.DriftInput(target_repo="/nonexistent", spec_dir="specs/x", spec_text="")
    drifted, ticks = await _count_ticks_while(ra.drift_for_spec(request))

    assert drifted is False
    assert ticks >= MIN_TICKS, (
        f"event loop was starved: only {ticks} ticks during a {BLOCK_S}s git read. "
        "drift_for_spec is shelling git on the loop again."
    )


@pytest.mark.asyncio
async def test_derive_spec_does_not_block_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sibling on the same path. It was never the one that bit, which is
    exactly why it is worth pinning: nothing else would have caught it."""
    sentinel = object()

    def slow_derive(request: Any) -> Any:
        time.sleep(BLOCK_S)
        return sentinel

    monkeypatch.setattr(ra, "_derive_from_git", slow_derive, raising=True)
    monkeypatch.setattr(ra, "_derive_runner", None)

    request = ra.DeriveInput(
        target_repo="/nonexistent",
        epic_id="109-x",
        feature="x",
        specs_root="specs",
        spec_text="",
    )
    graph, ticks = await _count_ticks_while(ra.derive_spec(request))

    assert graph is sentinel
    assert ticks >= MIN_TICKS, (
        f"event loop was starved: only {ticks} ticks during a {BLOCK_S}s derive. "
        "derive_spec is shelling git on the loop again."
    )


def test_blocking_halves_are_plain_functions() -> None:
    """The split must stay a split.

    If either helper is made `async`, `asyncio.to_thread` would hand back a
    coroutine instead of running it on a thread, and the activity would be
    blocking again while still looking correct.
    """
    assert not asyncio.iscoroutinefunction(ra._drift_from_git)
    assert not asyncio.iscoroutinefunction(ra._derive_from_git)
