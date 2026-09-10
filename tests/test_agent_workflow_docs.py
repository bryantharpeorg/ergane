from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (REPO_ROOT / "docs/agents/workflow.md").read_text("utf-8")

LIFECYCLE = [
    "source verification",
    "optional memory recall",
    "finding-to-spec ownership",
    "whole-trio refinement",
    "validation",
    "readiness",
    "dispatch",
    "landing",
    "attestation",
]


def _positions(document: str, phrases: list[str]) -> list[int]:
    lowered = document.lower()
    cursor = 0
    positions = []
    for phrase in phrases:
        position = lowered.find(phrase, cursor)
        assert position >= 0, f"workflow must name {phrase!r} after position {cursor}"
        positions.append(position)
        cursor = position + len(phrase)
    return positions


def test_workflow_orders_the_full_lifecycle() -> None:
    positions = _positions(WORKFLOW, LIFECYCLE)
    assert positions == sorted(positions)


@pytest.mark.parametrize(
    ("phase", "authority"),
    [
        ("source verification", "read-only"),
        ("optional memory recall", "optional"),
        ("finding-to-spec ownership", "declared intent"),
        ("whole-trio refinement", "declared intent"),
        ("dispatch", "declared intent"),
        ("landing", "declared intent"),
        ("attestation", "declared intent"),
    ],
)
def test_workflow_states_phase_authority(phase: str, authority: str) -> None:
    marker = f"{phase} — {authority}"
    assert marker.lower() in WORKFLOW.lower()


def test_workflow_links_the_canonical_vocabulary_and_decision_process() -> None:
    assert "[CONTEXT.md](../../CONTEXT.md)" in WORKFLOW
    assert "[docs/decisions.md](../decisions.md)" in WORKFLOW
    assert "immutable" in WORKFLOW.lower()
