"""Tests for the live agent reading in `ergane build status`.

These tests build the `describe()` answer the CLI receives rather than driving a
Temporal worker, because the fact under test exists only in the server's
pending-activity list: a worker accepted the activity or it did not.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterable
import json

import pytest
from google.protobuf.timestamp_pb2 import Timestamp
from temporalio.api.enums.v1.workflow_pb2 import PendingActivityState

from factory.cli.nouns import build
import factory.cli.nouns as nouns
from factory.cli.nouns.build import render_status
from factory.usage.models import UsageSnapshot

NODE = "us2"
CAPTURED_AT = "2026-08-05T09:31:00Z"
SNAPSHOT = UsageSnapshot(spend_usd=6.25, captured_at=CAPTURED_AT)


class _FakeActivity:
    """The fields the reading needs, without fabricating presence for scalars."""

    def __init__(
        self,
        *,
        state: str,
        attempt: int,
        heartbeat_time: Timestamp | None,
        heartbeat_payloads: Iterable[Any] = (),
    ) -> None:
        self.activity_id = NODE
        self.activity_type = SimpleNamespace(name="run_agent_attempt")
        self.state = state
        self.attempt = attempt
        self.heartbeat_details = (
            SimpleNamespace(payloads=list(heartbeat_payloads))
            if heartbeat_payloads is not None
            else None
        )
        self.last_heartbeat_time = heartbeat_time

    def HasField(self, field: str) -> bool:
        if field in {"activity_type", "heartbeat_details", "last_heartbeat_time"}:
            return getattr(self, field) is not None
        raise ValueError(f"proto3 scalar field {field!r} has no HasField presence")


class _FakeConverter:
    async def decode(self, payloads: list[Any], types: Any) -> list[Any]:
        assert types == [UsageSnapshot | None]
        return list(payloads)


class _FakeClient:
    data_converter = _FakeConverter()


class _FakeStatusClient:
    data_converter = _FakeConverter()

    def get_workflow_handle(self, workflow_id: str) -> Any:
        assert workflow_id == "epic-us2"
        return _FakeStatusHandle()


class _FakeHandle:
    def __init__(self, activities: list[Any]) -> None:
        self._activities = activities

    async def describe(self) -> Any:
        return SimpleNamespace(
            raw_description=SimpleNamespace(pending_activities=self._activities)
        )


class _FakeStatusHandle:
    async def query(self, name: str) -> Any:
        assert name == "epic_status"
        return _document()

    async def describe(self) -> Any:
        started = _FakeActivity(
            state=PendingActivityState.PENDING_ACTIVITY_STATE_STARTED,
            attempt=1,
            heartbeat_payloads=[SNAPSHOT],
            heartbeat_time=_heartbeat_time(),
        )
        scheduled = _FakeActivity(
            state=PendingActivityState.PENDING_ACTIVITY_STATE_SCHEDULED,
            attempt=2,
            heartbeat_payloads=None,
            heartbeat_time=_heartbeat_time(),
        )
        return SimpleNamespace(
            status=SimpleNamespace(name="RUNNING"),
            raw_description=SimpleNamespace(
                pending_activities=[started, scheduled]
            ),
        )


def _heartbeat_time() -> Timestamp:
    timestamp = Timestamp()
    timestamp.FromDatetime(
        datetime(2026, 8, 5, 9, 30, 0, tzinfo=timezone.utc)
    )
    return timestamp


def _document() -> dict[str, Any]:
    return {
        "epic_state": "RUNNING",
        "nodes": {
            NODE: {
                "state": "RUNNING",
                "attempt": 6,
                "branch": "landing/us2",
            }
        },
    }


def _live(state: str) -> dict[str, Any]:
    return {
        NODE: {
            "state": state,
            "activity_attempt": 2,
            "last_heartbeat_at": "2026-08-05T09:30:00+00:00",
        }
    }


@pytest.mark.asyncio
async def test_a_pending_agent_attempt_without_a_payload_is_still_visible() -> None:
    """US2-S1/FR-007: no payload leaves the activity, not its liveness fields."""
    activity = _FakeActivity(
        state=PendingActivityState.PENDING_ACTIVITY_STATE_SCHEDULED,
        attempt=2,
        heartbeat_payloads=None,
        heartbeat_time=_heartbeat_time(),
    )

    live = await build._live_spend(_FakeClient(), _FakeHandle([activity]), _document())

    assert live[NODE] == {
        "state": "SCHEDULED",
        "activity_attempt": 2,
        "last_heartbeat_at": "2026-08-05T09:30:00+00:00",
    }
    assert isinstance(live[NODE]["state"], str)
    assert isinstance(live[NODE]["activity_attempt"], int)
    assert isinstance(live[NODE]["last_heartbeat_at"], str)


def test_a_pending_activity_state_changes_the_node_line() -> None:
    """US2-S2/FR-009: the state is named, not merely the reason the lines differ."""
    scheduled = render_status(
        "epic-us2", _document(), "RUNNING", live_spend=_live("SCHEDULED")
    ).splitlines()[-1]
    started = render_status(
        "epic-us2", _document(), "RUNNING", live_spend=_live("STARTED")
    ).splitlines()[-1]

    assert scheduled != started
    assert "SCHEDULED" in scheduled


def test_a_live_figure_is_printed_with_the_time_it_was_measured() -> None:
    """US2-S3/FR-010: retained spend is dated, not mistaken for a fresh read."""
    figure = _live("STARTED")[NODE]
    figure["spend_usd"] = SNAPSHOT.spend_usd
    figure["captured_at"] = CAPTURED_AT

    line = render_status(
        "epic-us2", _document(), "RUNNING", live_spend={NODE: figure}
    ).splitlines()[-1]

    assert f"${SNAPSHOT.spend_usd:.2f}" in line
    assert CAPTURED_AT in line


async def test_json_live_spend_stays_additive_and_loadable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """US2-S4/FR-011: existing keys survive and every field is JSON scalar."""
    async def open_client() -> Any:
        return _FakeStatusClient()

    monkeypatch.setattr(nouns, "_open_client", open_client)

    await build._query_status("epic-us2", as_json=True)
    document = json.loads(capsys.readouterr().out)

    live = document["live_spend"]
    assert set(live) == {NODE}
    for figure in live.values():
        if "spend_usd" in figure:
            assert set(figure) >= {"spend_usd", "captured_at"}
            assert isinstance(figure["spend_usd"], float)
            assert isinstance(figure["captured_at"], str)
        assert isinstance(figure["state"], str)
        assert isinstance(figure["activity_attempt"], int)
        assert isinstance(figure["last_heartbeat_at"], str)


def test_a_node_without_a_pending_activity_keeps_its_old_line() -> None:
    """US2-S5/FR-012: no pending activity adds no state token or padding."""
    unchanged = render_status("epic-us2", _document(), "RUNNING")
    empty_live = render_status("epic-us2", _document(), "RUNNING", live_spend={})

    assert empty_live == unchanged
    assert empty_live.splitlines()[-1] == f"{NODE}  RUNNING  attempt 6  landing/us2"
