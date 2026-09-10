"""US1 renders each parked finding beside the bare parked count."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from factory.cli import status as status_cli
from factory.roadmap.discovery import (
    RoadmapLocation,
    RoadmapOwner,
)
from factory.roadmap.workflow import ParkedFinding
from factory.cli.roadmap import _render_status as render_roadmap_status
from factory.roadmap.workflow import RoadmapStatus


OWNER = RoadmapOwner.RUN
RUN_ID = "roadmap-specs"
SCHEDULE_ID = "schedule-roadmap-specs"
NEXT_TICK = "2026-09-04T12:00:00+00:00"
SPECS_ROOT = "specs"

PARKED = (
    ParkedFinding(
        spec_dir="077-onboarding",
        check="onboarding",
        detail="the target repository refused onboarding",
    ),
    ParkedFinding(
        spec_dir="078-empty-delta",
        check="derive",
        detail="delta is empty: all stories are satisfied",
    ),
)


def _location() -> RoadmapLocation:
    return RoadmapLocation(
        root_name="specs",
        bare_workflow_id=RUN_ID,
        run_prefix=f"{RUN_ID}-",
        owner=OWNER,
        workflow_id=RUN_ID,
        schedule_id=SCHEDULE_ID,
        schedule_paused=False,
        next_action_at=NEXT_TICK,
        looked_for=(f"workflow id {RUN_ID}",),
        skipped_overlap_count=0,
    )


class _StubClient:
    def __init__(self, document: Any) -> None:
        self._document = document

    def get_workflow_handle(self, _workflow_id: str) -> Any:
        return SimpleNamespace(query=self._query)

    async def _query(self, _name: str) -> Any:
        return self._document


def _disposition(monkeypatch: pytest.MonkeyPatch) -> status_cli.RoadmapDisposition:
    async def _resolved(_client: Any, _specs_root: Path) -> RoadmapLocation:
        return _location()

    monkeypatch.setattr(status_cli, "resolve_roadmap", _resolved)
    document = {
        "parked": [asdict(finding) for finding in PARKED],
    }
    return asyncio.run(
        status_cli._disposition(_StubClient(document), Path(SPECS_ROOT))
    )


def _floor(
    disposition: status_cli.RoadmapDisposition,
) -> status_cli.FloorStatus:
    return status_cli.FloorStatus(
        specs_root=SPECS_ROOT,
        roadmap=disposition,
        epics=[],
        queue=[],
        drafts=[],
        pace=[],
        readiness_basis=status_cli.ReadinessBasis(observed=False, detail="attestation"),
        notes=[],
        degraded=False,
    )


def test_status_specs_human_names_each_parked_finding_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposition = _disposition(monkeypatch)
    lines = status_cli._roadmap_lines(_floor(disposition))

    assert lines[lines.index("parked: 2") + 1 :] == [
        "  077-onboarding — check: onboarding",
        "    the target repository refused onboarding",
        "  078-empty-delta — check: derive",
        "    delta is empty: all stories are satisfied",
    ]


def test_status_specs_json_carries_parked_fields_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposition = _disposition(monkeypatch)
    payload = asdict(disposition)

    assert payload["parked"] == [
        {
            "spec_dir": "077-onboarding",
            "check": "onboarding",
            "detail": "the target repository refused onboarding",
        },
        {
            "spec_dir": "078-empty-delta",
            "check": "derive",
            "detail": "delta is empty: all stories are satisfied",
        },
    ]


def test_distinct_park_checks_and_details_stay_distinct_on_both_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_surface = "\n".join(
        status_cli._roadmap_lines(_floor(_disposition(monkeypatch)))
    )
    roadmap_surface = render_roadmap_status(
        RoadmapStatus(specs=[], running=[], parked=list(PARKED))
    )

    for surface in (status_surface, roadmap_surface):
        assert "077-onboarding — check: onboarding" in surface
        assert "078-empty-delta — check: derive" in surface
        assert "the target repository refused onboarding" in surface
        assert "delta is empty: all stories are satisfied" in surface


def test_zero_parked_human_block_is_unchanged_and_json_field_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _resolved(_client: Any, _specs_root: Path) -> RoadmapLocation:
        return _location()

    monkeypatch.setattr(status_cli, "resolve_roadmap", _resolved)
    document = {"parked": []}
    disposition = asyncio.run(
        status_cli._disposition(_StubClient(document), Path(SPECS_ROOT))
    )

    assert disposition.parked == []
    assert status_cli._roadmap_lines(_floor(disposition)) == [
        "schedule: schedule-roadmap-specs (unknown)",
        "schedule: none found",
        "run: roadmap-specs",
        "next tick: 2026-09-04T12:00:00+00:00",
        "dispatch: running",
        "running: -",
        "parked: 0",
    ]
    assert asdict(disposition)["parked"] == []
