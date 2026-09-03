"""057/US2: the constitution fits the repo it is written into.

These tests are written before the implementation that will satisfy them, so they
are expected to fail on a clean tree. They assert against the composed output
and against fixture repositories so the judge can verify them from the diff alone
(constitution VIII / D-037).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

import factory.cli.init as init_module
import factory.stack_packs as stack_packs_module
from factory.cli.errors import EXIT_OK

from tests.test_057_us1_constitution_seeded import run_init
from tests.test_ergane_init import ScriptedPrompter, _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams, conforming_gh
from tests.fake_schedules import FakeScheduleServer


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> FakeScheduleServer:
    """Bind every outward seam; return the fake schedule server for inspection."""
    control_plane = FakeScheduleServer()
    bind_offline_seams(monkeypatch, conforming_gh(), schedules=control_plane)
    return control_plane


#: Minimal answers with a Python stack's default gate string.
#: Order follows `_TOP_LEVEL_KEYS`, then the US4 template-source question, then
#: the US2 detected-stack question, then the slug.
PYTHON_STACK_ANSWERS: list[str] = [
    "1",  # version
    "bwrap",  # runtime
    'test: "uv run pytest -q"',  # gates
    "",  # timeouts (empty -> omitted)
    "",  # standards (empty -> omitted, default will be used)
    "main",  # landing_branch
    "",  # roadmap (empty -> omitted)
    "",  # forge (empty -> omitted)
    "",  # writes (empty -> omitted)
    "",  # caches (empty -> omitted)
    "",  # diff_refusal_bytes (empty -> omitted)
    "",  # template source (empty -> shipped default)
    "",  # detected stack: accept default
    "myapp",  # slug
]


def test_python_fixture_produces_python_stack_layer_and_states_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US2-S1/FR-007/FR-008: a repo whose markers identify a pack gets that pack's
    stack layer, and the detected stack is stated to the operator before use."""
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "pyproject.toml": "[project]\nname = 'app'\nversion = '0.1.0'\n",
        },
    )

    result = run_init(repo, monkeypatch, answers=list(PYTHON_STACK_ANSWERS), offline_server=offline)

    assert result.code == EXIT_OK, result.stderr
    assert "detected" in result.stdout.lower(), "init did not state the detected stack"
    assert "python" in result.stdout.lower(), "init did not name the Python stack"
    constitution = repo / ".specify" / "memory" / "constitution.md"
    assert constitution.exists()
    text = constitution.read_text(encoding="utf-8")
    assert "Python" in text or "pytest" in text or "uv" in text, (
        "Python stack layer not written into constitution"
    )


def test_operator_answer_overrides_detected_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US2-S2/FR-008: an operator answer in the interview overrides detection."""
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "pyproject.toml": "[project]\nname = 'app'\nversion = '0.1.0'\n",
        },
    )

    # Provide an override answer when asked about the stack.
    # The prompt text is "detected stack"; any non-empty answer is the override.
    answers = [
        "1",  # version
        "bwrap",  # runtime
        'test: "uv run pytest -q"',  # gates
        "",  # timeouts
        "",  # standards
        "main",  # landing_branch
        "",  # roadmap
        "",  # forge
        "",  # writes
        "",  # caches
        "",  # diff_refusal_bytes
        "",  # template source (empty -> shipped default)
        "agnostic",  # detected stack: override with agnostic fallback
        "myapp",  # slug
    ]
    bind_offline_seams(monkeypatch, conforming_gh(), schedules=offline)
    prompter = ScriptedPrompter(answers)
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)

    result = _invoke(["init", str(repo)], monkeypatch)

    assert result.code == EXIT_OK, result.stderr
    # The override path leaves evidence in the transcript.
    assert "using operator-chosen stack" in result.stdout.lower(), (
        "init did not report applying the operator's stack choice"
    )


def test_unmatched_fixture_produces_language_agnostic_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US2-S3/FR-009: a repo matching no shipped pack gets the language-agnostic layer
    with a clear list of what the user must complete."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})

    # Unmatched repos do not ask the detected-stack question, so use the 13-entry
    # minimal answer list from the US1 test.
    from tests.test_057_us1_constitution_seeded import MINIMAL_ANSWERS as UNMATCHED_ANSWERS

    result = run_init(
        repo, monkeypatch, answers=list(UNMATCHED_ANSWERS), offline_server=offline
    )

    assert result.code == EXIT_OK, result.stderr
    constitution = repo / ".specify" / "memory" / "constitution.md"
    assert constitution.exists()
    text = constitution.read_text(encoding="utf-8")
    assert "stack" in text.lower() or "toolchain" in text.lower(), (
        "language-agnostic stack layer not written"
    )
    assert "complete" in text.lower() or "fill" in text.lower() or "add" in text.lower(), (
        "agnostic layer does not name what the user must complete"
    )


def test_shipped_packs_use_only_own_toolchain_commands(
    tmp_path: Path,
) -> None:
    """US2-S4/SC-003: every shipped pack names only commands valid for its own
    toolchain, and no pack names a tool belonging to another pack.

    This test is mechanical: it inspects the pack data resolved by the factory
    and cross-checks commands against tool markers. Reading the pack files is
    not evidence (plan trap 8).
    """
    packs = stack_packs_module.resolve_stack_packs()
    assert packs, "no stack packs resolved"

    # Build a map of pack name -> set of executable/tool names named by commands.
    # The exact extraction shape depends on the pack data schema; this assertion
    # will be tightened once the schema is implemented.
    for pack in packs:
        assert pack.name, "pack has no name"
        for cmd in pack.commands.values():
            assert isinstance(cmd, str), f"{pack.name} command is not a string"
            assert cmd, f"{pack.name} has an empty command"

    # Cross-pack check: collect toolchain identifiers and assert no command
    # contains a tool identifier from a different pack. A pack's own toolchain
    # name is allowed; foreign toolchain names are forbidden.
    tool_markers: dict[str, set[str]] = {}
    for pack in packs:
        markers: set[str] = {pack.toolchain.lower()}
        for cmd_name in pack.commands:
            markers.add(cmd_name.lower())
        tool_markers[pack.name] = markers

    for pack in packs:
        own_markers = tool_markers[pack.name]
        for other_name, other_markers in tool_markers.items():
            if other_name == pack.name:
                continue
            for cmd in pack.commands.values():
                lowered = cmd.lower()
                for marker in other_markers:
                    assert marker not in lowered, (
                        f"{pack.name} command {cmd!r} names tool from {other_name}"
                    )


def test_two_markers_produce_question_not_pick(
    tmp_path: Path,
) -> None:
    """Edge case: two stack markers in one repository produce a question, not a pick."""
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "pyproject.toml": "[project]\nname = 'app'\nversion = '0.1.0'\n",
            "package.json": '{"name": "app", "version": "0.1.0"}\n',
        },
    )

    # For this test to exercise ambiguity, add a second shipped pack that also
    # matches package.json so detection sees more than one match.
    extra_dir = tmp_path / "extra_packs"
    extra_dir.mkdir()
    node_pack = {
        "name": "node",
        "label": "Node.js",
        "markers": ["package.json"],
        "toolchain": "Node.js (npm)",
        "commands": {"test": "npm test", "lint": "npm run lint"},
        "dependency_policy": "Ask before adding dependencies.",
    }
    (extra_dir / "node.yaml").write_text(
        yaml.safe_dump(node_pack, sort_keys=False), encoding="utf-8"
    )

    detected = stack_packs_module.detect_stack(repo, extra_directories=[extra_dir])

    assert detected is None, (
        "two markers produced a single pick instead of a question"
    )


def test_adding_a_pack_changes_only_data_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S5/FR-010/SC-004: adding a pack changes no code outside the pack data.

    The selector reads from data and branches on what it finds, so adding a new
    pack requires only a new data file. This test lists the resolved packs, adds
    a synthetic one in a temporary location, and asserts the selector sees it
    without a new code branch.
    """
    packs = stack_packs_module.resolve_stack_packs()
    names_before = {p.name for p in packs}

    # Create a synthetic pack file and add it to the resolution path through the
    # test seam. The implementation must provide a way to point the resolver at
    # additional directories; this test documents that seam.
    extra_dir = tmp_path / "extra_packs"
    extra_dir.mkdir()
    synthetic = {
        "name": "synthetic-test-stack",
        "label": "Synthetic",
        "markers": ["synthetic.marker"],
        "toolchain": "synthetic",
        "commands": {"test": "synthetic-test"},
        "dependency_policy": "Ask before adding dependencies.",
    }
    (extra_dir / "synthetic.yaml").write_text(
        yaml.safe_dump(synthetic, sort_keys=False), encoding="utf-8"
    )

    with_packs = stack_packs_module.resolve_stack_packs(extra_directories=[extra_dir])
    names_after = {p.name for p in with_packs}

    assert "synthetic-test-stack" in names_after, "synthetic pack was not picked up"
    assert names_before <= names_after, "adding a pack dropped an existing pack"
