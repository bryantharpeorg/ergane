from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (REPO_ROOT / "docs/agents/workflow.md").read_text("utf-8")
CAPABILITIES = (REPO_ROOT / "docs/agents/capabilities.md").read_text("utf-8")

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


CAPABILITY_HEADERS = [
    "job",
    "shared intent",
    "codex cli binding",
    "claude code binding",
    "absent-binding fallback",
]


@pytest.mark.parametrize(
    "job",
    ["ask", "delegate", "recall", "schedule", "notify", "render", "stop", "publish"],
)
def test_capability_rows_separate_intent_from_bindings(job: str) -> None:
    tables = [
        line
        for line in CAPABILITIES.splitlines()
        if line.startswith("| ") and line.endswith(" |")
    ]
    header_index = next(
        (
            index
            for index, line in enumerate(tables)
            if [cell.strip().lower() for cell in line.strip("|").split("|")]
            == CAPABILITY_HEADERS
        ),
        None,
    )
    assert header_index is not None, "capabilities.md must contain the shared binding table"
    rows = {
        cells[0].lower(): [cell.strip() for cell in cells]
        for line in tables[header_index + 2 :]
        if (cells := [cell.strip() for cell in line.strip("|").split("|")])
        and len(cells) == len(CAPABILITY_HEADERS)
        and cells[0]
        and not set(cells[0]) <= {"-"}
    }
    assert job in rows, f"capabilities.md must cover the {job!r} job"
    cells = rows[job]
    assert len(cells) == len(CAPABILITY_HEADERS)
    assert cells[1], f"{job} has no shared intent"
    for binding in cells[2:4]:
        assert binding, f"{job} has an unrepresented binding"
        assert "unavailable" in binding.lower(), (
            f"{job} hides an absent binding instead of reporting it: {binding!r}"
        )
    assert "narrow fallback" in cells[4].lower(), (
        f"{job} must name its narrow supported fallback: {cells[4]!r}"
    )


def test_workflow_names_the_governing_local_authorities() -> None:
    for authority in ("Spec Kit trios", "findings ledger", "immutable decisions"):
        assert authority in WORKFLOW, f"workflow must name the {authority!r} authority"


@pytest.mark.parametrize(
    "forbidden",
    [
        "Beads is not an Ergane default",
        "GitHub issues are not an Ergane default",
        "A mandatory push is not an Ergane default",
        "Checkout cleanup is not an Ergane default",
    ],
)
def test_workflow_refuses_competing_or_destructive_defaults(forbidden: str) -> None:
    assert forbidden in WORKFLOW
