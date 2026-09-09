"""One canonical orientation has two verified entry points (157 US1).

`AGENTS.md` is the canonical repository orientation; `CLAUDE.md` is a
compatibility entry point to those exact bytes, not a copied policy. This file
holds the content contracts the story's acceptance scenarios name:

- the canonical file begins with the dispatched-node guard (FR-001),
- the compatibility entry point is a tracked symlink resolving to the
  canonical file's exact bytes (FR-002),
- the authority map, the live-state table and the active-manifest rule are
  present (FR-003, FR-004),
- the orientation separates observation from authorized action (FR-005 —
  the semantic half of that lives in the ``Observation`` section tests
  below, driven off the shared extractor so a reworded page that drops the
  distinction fails the same way a reworded README fails its concept guard).

The tests read the tracked objects — the symlink's *type* is asserted, not
assumed, because a compatibility entry point that silently became a copy is
exactly the second policy channel this story exists to prevent.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tests.page_holds_true import REPO_ROOT

AGENTS_MD = REPO_ROOT / "AGENTS.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


# --- the tracked file types (US1-S1, FR-001/FR-002) ---------------------------


def test_the_canonical_orientation_exists_and_is_tracked() -> None:
    """`AGENTS.md` is a committed regular file, not runtime state."""
    assert AGENTS_MD.exists(), "AGENTS.md is the canonical orientation; it is missing"
    assert stat.S_ISREG(AGENTS_MD.lstat().st_mode), (
        "AGENTS.md must be the canonical file itself, not a link to something else"
    )


def test_the_compatibility_entry_point_is_tracked_as_a_symlink() -> None:
    """`CLAUDE.md` must be a symlink, or it is a copied policy (FR-002).

    A copied policy drifts the day after it lands and nothing but this
    assertion notices, so the file's type is part of the contract. If a
    supported installation shape cannot preserve the symlink, this test is
    the one that gets amended — with the loader the exception names — and
    never by accepting a second copy of the text.
    """
    assert stat.S_ISLNK(CLAUDE_MD.lstat().st_mode), (
        "CLAUDE.md is a regular file, which makes it a second copy of the policy. "
        "Make it a symlink to AGENTS.md (measured to resolve on both installed "
        "clients, including inside a git worktree), or amend this contract with "
        "the smallest explicit loader if an installation shape cannot carry the "
        "symlink"
    )


def test_the_compatibility_entry_point_resolves_into_the_repository() -> None:
    """The symlink's target stays inside the tree, so a worktree is self-contained."""
    target = CLAUDE_MD.resolve()
    assert target == AGENTS_MD.resolve(), (
        f"CLAUDE.md points at {target}, not at the canonical AGENTS.md — the "
        "entry point must resolve into this repository"
    )


def test_the_compatibility_entry_point_serves_the_canonical_bytes() -> None:
    """Reading through the entry point yields the canonical file's exact bytes."""
    canonical = AGENTS_MD.read_bytes()
    through_entry_point = CLAUDE_MD.read_bytes()
    assert through_entry_point == canonical, (
        "the compatibility entry point no longer serves AGENTS.md byte-for-byte; "
        "the symlink or its target was replaced"
    )


# --- the canonical content (US1-S1, FR-001/FR-003/FR-004/FR-005) ---------------

TEXT = CLAUDE_MD.read_text(encoding="utf-8") if CLAUDE_MD.exists() else ""
LINES = TEXT.splitlines()


def test_it_begins_with_the_dispatched_node_guard() -> None:
    """FR-001: the first prose sentence of the file is the node guard.

    The guard is the whole point of the file's shape — an implementer node
    reads this page on an ancestor path before its brief reaches it, so the
    guard has to be the first thing the page says, not a section it may
    scroll past. Asserted against the first non-heading, non-blank body
    text, so moving the title or adding an HTML comment does not dodge it.
    """
    for line in LINES:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert "not your brief" in stripped, (
            f"AGENTS.md opens with {stripped!r} — the dispatched-node guard "
            "must be the first prose the page carries"
        )
        return
    pytest.fail("AGENTS.md carries no prose at all")


def test_it_names_every_document_authority() -> None:
    """FR-003: the authority map is present, with each document and its role."""
    paragraphs = TEXT.split("\n\n")
    for document, role in (
        (".specify/memory/constitution.md", "normative"),
        ("docs/architecture.md", "descriptive"),
        ("docs/decisions.md", "immutable"),
        ("CONTEXT.md", "vocabulary"),
    ):
        assert document in TEXT, f"AGENTS.md no longer names {document}"
        # Role and document in one paragraph: the map, not a bare list of files.
        assert any(
            document in paragraph and role in paragraph.lower()
            for paragraph in paragraphs
        ), f"AGENTS.md names {document} but not in the same paragraph as its role {role!r}"


def test_it_names_the_document_authority_map_by_heading() -> None:
    """The authority map is a section a reader can find, not prose in passing."""
    headings = [line.strip() for line in LINES if line.startswith("#")]
    assert any("Which document binds" in heading for heading in headings), (
        f"AGENTS.md has no authority-map heading; its headings are {headings}"
    )


def test_it_names_the_live_state_commands() -> None:
    """The orientation points at read surfaces rather than copying their answers."""
    for command in (
        "ergane spec list",
        "ergane spec landed",
        "ergane build status",
        "ergane findings list",
        "ergane usage --by",
    ):
        assert command in TEXT, f"AGENTS.md no longer names `{command}` as a live source"


def test_it_names_the_active_manifest_and_the_legacy_one() -> None:
    """FR-004: `ergane.yaml` is the manifest; `factory.yaml` is compatibility context."""
    assert "ergane.yaml" in TEXT, "AGENTS.md does not name ergane.yaml as the active manifest"
    assert "factory.yaml" in TEXT, (
        "AGENTS.md does not mention factory.yaml at all — the legacy name is "
        "compatibility context (code still accepts it), and silence reads as "
        "'that name is wrong' rather than 'that name is retired'"
    )


def test_the_manifest_it_applies_to_is_ergane_yaml() -> None:
    """FR-004, the strong half: the page binds the manifest to the active name.

    Prose alone is weak against drift, so the page must say the active
    manifest in the same breath as the standards path it names — the pair a
    dispatched node is actually told to read.
    """
    paragraphs = TEXT.split("\n\n")
    assert any(
        "ergane.yaml" in paragraph and "standards" in paragraph.lower()
        for paragraph in paragraphs
    ), "AGENTS.md never states in one place that ergane.yaml names the standards path"


def test_it_carries_an_observation_versus_action_boundary() -> None:
    """FR-005: the page says which requests are read-only and which are not."""
    headings = [line.strip() for line in LINES if line.startswith("#")]
    assert any("Observation" in heading for heading in headings), (
        f"AGENTS.md has no observation boundary heading; its headings are {headings}"
    )
    # The two halves of the boundary, stated where the section is.
    section = _observation_section()
    assert "observation" in section.lower()
    assert "declared intent" in section.lower(), (
        "the observation section states the read-only half but not the "
        "authorized half — every action requires its own declared intent"
    )


def _observation_section() -> str:
    """The text from the observation heading to the next heading of any depth."""
    section: list[str] = []
    inside = False
    for line in LINES:
        if line.startswith("#"):
            if inside:
                break
            inside = "Observation" in line
            if inside:
                section.append(line)
            continue
        if inside:
            section.append(line)
    return "\n".join(section)


# --- the guard is not vacuous (a control for the first-prose assertion) --------


def test_the_guard_check_fires_on_a_page_that_loses_it() -> None:
    """A copy of the orientation with the guard removed fails the first-prose check.

    A test that only asserts a sentence is present would pass forever on a
    page nobody edits; this is the mutation that keeps it measuring.
    """
    from tests.test_operator_instructions import _first_prose_line  # noqa: PLC0415

    mutated = TEXT.replace("not your brief", "a brief for implementers")
    with pytest.raises(AssertionError):
        _first_prose_line(mutated.splitlines())


def _first_prose_line(lines: list[str]) -> str:
    """The first non-heading, non-empty line of a page."""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert "not your brief" in stripped, (
            f"the page opens with {stripped!r} — the dispatched-node guard "
            "must be the first prose the page carries"
        )
        return stripped
    pytest.fail("the page carries no prose at all")