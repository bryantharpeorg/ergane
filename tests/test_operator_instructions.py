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

import json
import re
import stat
from pathlib import Path

import pytest

from tests.page_holds_true import REPO_ROOT

AGENTS_MD = REPO_ROOT / "AGENTS.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "operator-instructions"


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


# --- the six-context discovery evidence (US1-S2, FR-009) ----------------------

SHAPES = ("root", "nested", "worktree")
CLIENTS = ("codex", "claude")


def _record(client: str, shape: str) -> dict:
    path = FIXTURES / f"{client}-{shape}.json"
    assert path.exists(), f"the discovery record {path.name} is missing"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("client", CLIENTS)
@pytest.mark.parametrize("shape", SHAPES)
def test_every_client_shape_recorded(client: str, shape: str) -> None:
    record = _record(client, shape)
    assert record["client"] == client
    assert record["session_shape"] == shape
    assert record["redaction"], "the record must state how it was redacted"


def test_the_records_carry_no_credentials_or_absolute_host_paths() -> None:
    forbidden = (
        "sk-", "sk_", "Bearer ", "ghp_", "github_pat_",
        str(Path.home()), "/home/admin", "/root/", "LITELLM_MASTER_KEY",
    )
    for path in sorted(FIXTURES.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, (
                f"{path.name} carries {needle!r} — the six-context evidence must "
                "stay redacted (no credentials, no absolute home paths)"
            )


@pytest.mark.parametrize("client", CLIENTS)
@pytest.mark.parametrize("shape", SHAPES)
def test_every_observation_names_the_canonical_instructions_exactly_once(
    client: str, shape: str
) -> None:
    record = _record(client, shape)
    observation = record["observation"]
    assert observation["canonical_named"] == "AGENTS.md"
    expected = 0 if client == "codex" and shape == "worktree" else 1
    assert observation["canonical_occurrences"] == expected
    loaded = observation["instruction_files_loaded"]
    if expected:
        assert any("AGENTS.md" in name for name in loaded)
        assert observation["resolved_bytes_equal_canonical"]


@pytest.mark.parametrize("client", CLIENTS)
@pytest.mark.parametrize("shape", SHAPES)
def test_every_record_carries_the_dispatched_node_facts(
    client: str, shape: str
) -> None:
    facts = _record(client, shape)["dispatched_node_facts"]
    line = facts["assembled_prompt_standards_line"]
    assert ".specify/memory/constitution.md" in line
    assert facts["precedence"].startswith("declared standards outrank")


def test_the_six_records_agree_on_the_canonical_file() -> None:
    named = {
        _record(client, shape)["observation"]["canonical_named"]
        for client in CLIENTS
        for shape in SHAPES
    }
    assert named == {"AGENTS.md"}


def test_the_fixture_readme_names_all_six_records() -> None:
    readme = (FIXTURES / "README.md").read_text(encoding="utf-8")
    for client in CLIENTS:
        for shape in SHAPES:
            assert f"{client}-{shape}" in readme


def test_the_parser_actually_reads_the_records() -> None:
    with pytest.raises(AssertionError):
        _record("codex", "shape-that-was-never-recorded")


_RECIPE_OPENINGS = re.compile(
    r"^\s*(?:[-*]\s+)?(?:To\s+)?"
    r"(run|execute|fetch|pull|merge|push|commit|dispatch|start|apply|answer|"
    r"press|approve|install|restart|publish|land|revoke|mint|kill|mark|write|"
    r"set|edit|update|move|create|add|remove|delete|answer it|re-read)\b",
    re.IGNORECASE,
)
_ACTIONS = (
    "fetch", "merge", "dispatch", "attest", "escalation", "findings",
    "commit", "push", "service", "restart",
)


def _observation_sentences(section: str) -> list[str]:
    body = "\n".join(line for line in section.splitlines() if not line.startswith("#"))
    flat = re.sub(r"\s+", " ", body)
    return [item.strip() for item in re.split(r"(?<=[.!?:])\s+", flat) if item.strip()]


def _granted_actions(section: str) -> list[str]:
    return [
        sentence for sentence in _observation_sentences(section)
        if _RECIPE_OPENINGS.match(sentence)
    ]


def test_the_observation_section_grants_no_action() -> None:
    section = _observation_section()
    assert section, "the observation section is empty — it moved or was renamed"
    granted = _granted_actions(section)
    assert not granted, (
        "the observation section contains imperative recipes:\n"
        + "\n".join(f"  {sentence}" for sentence in granted)
    )


def test_the_observation_section_names_the_forbidden_actions() -> None:
    section = _observation_section().lower()
    named = [action for action in _ACTIONS if action in section]
    assert len(named) >= len(_ACTIONS) - 2


def test_the_observation_section_requires_declared_intent_for_actions() -> None:
    assert "declared intent" in _observation_section().lower()


def test_the_observation_section_keeps_the_read_only_half() -> None:
    section = _observation_section().lower()
    assert "read-only" in section or "no mutation" in section or "does not" in section


_GRANT_MUTATIONS = (
    ("merge", "To land a story, merge the PR once the queue is green."),
    ("fetch", "- Fetch origin first so the landed list is current."),
    ("dispatch", "Run `ergane build start` to dispatch the epic."),
    ("attest", "Mark the spec's frontmatter landed to attest it."),
    ("escalation", "Answer the escalation by pressing the approve button."),
    ("findings", "Apply the finding with `ergane findings apply`."),
    ("commit", "Commit the result before reporting."),
    ("push", "Push the branch so CI runs."),
    ("service", "Restart the worker to pick up the change."),
)


@pytest.mark.parametrize(
    "action,recipe", _GRANT_MUTATIONS, ids=[action for action, _ in _GRANT_MUTATIONS]
)
def test_a_granted_action_is_rejected(action: str, recipe: str) -> None:
    assert _granted_actions(_observation_section() + "\n\n" + recipe), (
        f"the {action} mutation was not detected — the imperative sweep is too narrow"
    )


def test_naming_an_action_without_recipe_passes() -> None:
    shipped = _observation_section()
    assert not _granted_actions(shipped)
    assert "merge" in shipped.lower() or "merge" in TEXT.lower()
