"""US5 of 131: the roadmap's landed read is bounded and paid for once."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from factory.activities import roadmap_activities as ra
from factory.worker import ACTIVITIES


BLOCK_S = 0.30
TICK_S = 0.01
MIN_TICKS = 5


def _activity_is_registered(activities: list[object], target: object) -> bool:
    """Return whether the worker's registration set names this activity."""
    return any(activity is target for activity in activities)


@pytest.mark.asyncio
async def test_landed_for_spec_does_not_block_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The landed read leaves the worker loop free while git is blocked."""
    ticks = 0
    stop = False

    def slow_landed_from_git(_request: Any) -> None:
        time.sleep(BLOCK_S)

    async def ticker() -> None:
        nonlocal ticks
        while not stop:
            await asyncio.sleep(TICK_S)
            ticks += 1

    monkeypatch.setattr(ra, "_landed_runner", None)
    monkeypatch.setattr(ra, "_landed_from_git", slow_landed_from_git)
    request = ra.LandedInput(target_repo="/nonexistent", spec_dir="specs/x", spec_text="")
    ticker_task = asyncio.create_task(ticker())
    try:
        result = await ra.landed_for_spec(request)
    finally:
        stop = True
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass

    assert result is None
    assert ticks >= MIN_TICKS


@pytest.mark.asyncio
async def test_landed_for_spec_test_detects_an_on_loop_git_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scripted on-loop read starves the same ticker the activity control uses."""
    ticks = 0
    stop = False

    def slow_landed_runner(_request: Any) -> None:
        time.sleep(BLOCK_S)

    async def ticker() -> None:
        nonlocal ticks
        while not stop:
            await asyncio.sleep(TICK_S)
            ticks += 1

    monkeypatch.setattr(ra, "_landed_runner", slow_landed_runner)
    request = ra.LandedInput(target_repo="/nonexistent", spec_dir="specs/x", spec_text="")
    ticker_task = asyncio.create_task(ticker())
    try:
        result = await ra.landed_for_spec(request)
    finally:
        stop = True
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass

    assert result is None
    assert ticks < MIN_TICKS


def test_landed_for_spec_is_registered_on_the_worker() -> None:
    """A workflow call to an unregistered activity is a timeout, not an import error."""
    assert _activity_is_registered(ACTIVITIES, ra.landed_for_spec)


def test_registration_test_detects_a_missing_activity() -> None:
    """The registration control notices the exact one-line omission it guards."""
    faulted = [activity for activity in ACTIVITIES if activity is not ra.landed_for_spec]
    assert not _activity_is_registered(faulted, ra.landed_for_spec)
