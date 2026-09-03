"""057/US1: the content of the seeded constitution is generic and well-worded.

These tests assert against the composed output rather than a fixture copy, so
rewording the floor cannot silently drop the rationale (plan evidence
discipline). They are written first and must fail until the composer and floor
data exist.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

import factory.cli.init as init_module


#: Pattern that identifies a principle heading and an immediately following
#: one-line "why" paragraph. We expect each principle to carry its own rationale.
PRINCIPLE_HEADING = re.compile(r"^## .+$", re.MULTILINE)
#: Pattern for the consequence phrasing "if this is removed" / "removing this".
CONSEQUENCE_PHRASE = re.compile(
    r"what removing this costs|if (?:you remove|this is removed|it is removed|removing this|removing it)",
    re.IGNORECASE,
)


def composed_text(tmp_path: Path) -> str:
    """Return the composed constitution text using the real shipped floor."""
    from factory.constitution import shipped_floor_text
    from factory.stack_packs import agnostic_layer

    floor_text = shipped_floor_text()
    source = "shipped-default"
    return init_module.compose_constitution(
        floor_text, source, project_name="app", stack_layer=agnostic_layer()
    )


def test_composed_output_contains_floor_and_governance(
    tmp_path: Path,
) -> None:
    """US1-S4/FR-004: the document contains the default floor and a governance section."""
    text = composed_text(tmp_path)
    assert "## " in text, "no principles present"
    assert "governance" in text.lower(), "no governance section"


def test_composed_output_contains_no_ergane_specific_content(
    tmp_path: Path,
) -> None:
    """US1-S4/FR-005/FR-006: no spec numbers, decision ids, rosters, or product principles."""
    text = composed_text(tmp_path)
    assert "D-" not in text, "decision id present"
    assert not re.search(r"spec\s+\d{3}", text, re.IGNORECASE), "spec number present"
    assert not re.search(
        r"\b(temporalio|python-telegram-bot|pytest|httpx|pyyaml|uv)\b",
        text,
        re.IGNORECASE,
    ), "dependency roster present"
    for forbidden in (
        "Spend Is Attributed",
        "Personas Over Model Tiers",
        "Determinism at the Core",
    ):
        assert forbidden not in text, f"product-specific principle {forbidden!r} present"


def test_every_principle_carries_a_one_line_why(tmp_path: Path) -> None:
    """US1-S6/FR-016/SC-006: every principle heading carries a bold one-line rationale."""
    text = composed_text(tmp_path)
    headings = list(PRINCIPLE_HEADING.finditer(text))
    assert headings, "no principle headings found"

    missing_why = 0
    for match in headings:
        rest = text[match.end() :]
        # The rationale is the first bold paragraph after the heading. The block
        # starts with an empty line after the heading, so split on the first
        # blank paragraph and look inside.
        next_block = rest.split("\n\n", 1)[0].strip()
        if not next_block:
            # If the heading is at the end of the floor, read the remainder.
            next_block = rest.strip()
        if "**Why this is here:**" not in next_block:
            missing_why += 1

    assert missing_why == 0, f"{missing_why} principle(s) carry no one-line why"


def test_mechanical_principles_are_phrased_as_consequences(
    tmp_path: Path,
) -> None:
    """US1-S7/FR-017: the two mechanical principles state what removing them costs."""
    text = composed_text(tmp_path)
    # The two mechanical principles concern provable criteria and vertical slices.
    mechanical_principles: list[str] = []
    for heading_match in PRINCIPLE_HEADING.finditer(text):
        heading = heading_match.group(0)
        if "diff" in heading.lower() or "criteria" in heading.lower() or "slice" in heading.lower():
            # Capture the whole principle block until the next heading or the
            # end of the floor section, whichever comes first.
            next_heading = PRINCIPLE_HEADING.search(text, heading_match.end())
            block_end = (
                next_heading.start()
                if next_heading is not None
                else text.find("\n---\n", heading_match.end())
            )
            block = text[heading_match.end() : block_end if block_end != -1 else None]
            mechanical_principles.append(block)

    assert len(mechanical_principles) >= 2, "expected at least two mechanical principles"
    for block in mechanical_principles:
        assert CONSEQUENCE_PHRASE.search(block), (
            "mechanical principle does not state what removing it costs:\n" + block
        )


def test_document_says_it_is_the_repositories_to_edit(
    tmp_path: Path,
) -> None:
    """US1-S7/FR-017: the seeded document says plainly that the repo owns it."""
    text = composed_text(tmp_path)
    assert re.search(r"\byour\s+repository|this\s+repository|repository['’]?s\s+own|edit\s+this", text, re.IGNORECASE), (
        "document does not say it is the repository's to edit"
    )
