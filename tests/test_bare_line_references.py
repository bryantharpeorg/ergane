"""US3: bare `:NN` citations are resolved against their section's last path.

Every fixture is a supplied tmp tree, never this repository, because the anchors
in `factory/` move — that is the whole premise of 072.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as exit_request:
        return 0 if exit_request.code is None else int(exit_request.code)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        code = _invoke(list(argv))
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def _write_spec(
    spec_dir: Path,
    *,
    state: str = "ready",
    plan: str = "# Plan\n\n",
    tasks: str = "# Tasks\n\n",
) -> None:
    """Write a minimal Spec Kit trio."""
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_text = (
        "---\n"
        f"state: {state}\n"
        "---\n"
        "# Feature\n\n"
        "## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST do a thing.\n\n"
        "### User Story 1 - Do a thing (Priority: P1)\n\n"
        "As the operator, I want this.\n\n"
        "**Acceptance Scenarios**:\n"
        "1. **Given** a thing, **When** I act, **Then** it works.\n\n"
        "## Work Graph\n\n"
        "```yaml\n"
        "US1:\n"
        "  depends_on: []\n"
        "  implements: [FR-001]\n"
        "```\n"
    )
    (spec_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (spec_dir / "plan.md").write_text(plan, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks, encoding="utf-8")


def _target_tree(tmp_path: Path) -> Path:
    """A supplied target repo with one file of three real lines."""
    repo = tmp_path / "target_repo"
    code_dir = repo / "src"
    code_dir.mkdir(parents=True)
    (code_dir / "module.py").write_text("line one\nline two\nline three\n", encoding="utf-8")
    return repo


def test_bare_reference_resolves_against_most_recent_path(run, tmp_path):
    """US3-S1 / T019: `:NN` carries the last cited path forward in the same section."""
    target_repo = _target_tree(tmp_path)
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan=(
            "# Plan\n\n"
            "- `src/module.py:1-3` sets the file.\n"
            "- Later, `:2` refers back to it.\n"
        ),
        tasks=(
            "# Tasks\n\n"
            "## Phase 1: User Story 1 - Do a thing\n\n"
            "- [ ] T001 [US1-S1] first\n"
        ),
    )

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    assert not any(f["layer"] == "anchor_resolution" for f in result.json["findings"])


def test_bare_reference_without_preceding_path_is_unanchorable(run, tmp_path):
    """US3-S2 / T020: a bare `:NN` with no path in its section is reported, not skipped."""
    target_repo = _target_tree(tmp_path)
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan=(
            "# Plan\n\n"
            "## Section without a path\n\n"
            "- `:2` has no file to resolve against.\n"
        ),
        tasks=(
            "# Tasks\n\n"
            "## Phase 1: User Story 1 - Do a thing\n\n"
            "- [ ] T001 [US1-S1] first\n"
        ),
    )

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 1
    findings = result.json["findings"]
    match = next(f for f in findings if f["layer"] == "anchor_resolution")
    assert "plan.md" in match["message"]
    assert "`:2`" in match["message"]
    assert "unanchorable" in match["message"]


def test_bare_reference_resolving_to_blank_line_is_reported(run, tmp_path):
    """US3-S3 / T021: a resolved bare `:NN` on a blank line is reported exactly as US1 would."""
    target_repo = _target_tree(tmp_path)
    module_path = target_repo / "src" / "module.py"
    module_path.write_text("line one\n\nline three\n", encoding="utf-8")
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan=(
            "# Plan\n\n"
            "- `src/module.py:1-3` sets the file.\n"
            "- `:2` lands on a blank line.\n"
        ),
        tasks=(
            "# Tasks\n\n"
            "## Phase 1: User Story 1 - Do a thing\n\n"
            "- [ ] T001 [US1-S1] first\n"
        ),
    )

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 1
    findings = result.json["findings"]
    match = next(f for f in findings if f["layer"] == "anchor_resolution")
    assert "plan.md" in match["message"]
    # The finding names the resolved citation, so the bare ` :2` text may not
    # appear verbatim; the cited path and line, plus the blank-line failure
    # kind, are what US1 would report.
    assert "line 2 is blank" in match["message"]
    assert "src/module.py" in match["message"]


def test_document_with_no_bare_references_is_unchanged(run, tmp_path):
    """US3-S4 / T022: the control — no bare refs means silence and US1 behaviour unchanged."""
    target_repo = _target_tree(tmp_path)
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan="# Plan\n\n- see `src/module.py:1` and `src/module.py:3`.\n",
        tasks=(
            "# Tasks\n\n"
            "## Phase 1: User Story 1 - Do a thing\n\n"
            "- [ ] T001 [US1-S1] first\n"
        ),
    )

    result = run("spec", "validate", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    assert "anchor resolution" in result.stdout
    assert "unanchorable" not in result.stderr

    json_result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))
    assert not any(f["layer"] == "anchor_resolution" for f in json_result.json["findings"])
    assert "anchor_resolution" in json_result.json["checked"]
