"""US1 renders `ergane roadmap status` parked findings verbatim."""

from __future__ import annotations

from dataclasses import asdict

from factory.cli import roadmap as roadmap_cli
from factory.roadmap.workflow import ParkedFinding, RoadmapStatus


def _status() -> RoadmapStatus:
    return RoadmapStatus(
        specs=[],
        running=[],
        parked=[
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
        ],
    )


def test_render_status_names_each_parked_finding_under_the_count() -> None:
    lines = roadmap_cli._render_status(_status()).splitlines()
    parked_index = lines.index("parked: 2")

    assert lines[parked_index + 1 :] == [
        "  077-onboarding — check: onboarding",
        "    the target repository refused onboarding",
        "  078-empty-delta — check: derive",
        "    delta is empty: all stories are satisfied",
    ]


def test_status_json_payload_still_contains_the_query_answer_verbatim() -> None:
    payload = asdict(_status())

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
