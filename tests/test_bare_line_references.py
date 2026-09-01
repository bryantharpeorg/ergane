"""US3: bare `:NN` line references are resolved or refused.

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
    spec_body_extra: str = "",
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
        f"{spec_body_extra}"
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


def _ladder_tree(tmp_path: Path) -> Path:
    """A supplied target repo with a 105-line file so `:94` resolves."""
    repo = tmp_path / "target_repo"
    code_dir = repo / "factory" / "verify"
    code_dir.mkdir(parents=True)
    lines = [f"line {i}" for i in range(1, 106)]
    (code_dir / "ladder.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return repo


# --- T019 [P] [US3] S1: a bare `:NN` resolves against the most recent path -------


def test_bare_line_reference_resolves_against_last_path(run, tmp_path):
    target_repo = _ladder_tree(tmp_path)
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan=(
            "# Plan\n\n"
            "- Cite `factory/verify/ladder.py:68-105` first.\n"
            "- Then bare `:94` should resolve to the same file.\n"
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
    assert "anchor_resolution" in result.json["checked"]


# --- T020 [P] [US3] S2: a bare `:NN` with no preceding path is unanchorable ----


def test_bare_line_reference_with_no_path_is_unanchorable(run, tmp_path):
    target_repo = _target_tree(tmp_path)
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan=(
            "# Plan\n\n"
            "## A section with no prior path\n\n"
            "- This bare `:2` has no filename to resolve against.\n"
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
    assert match["severity"] == "refusal"


# --- T021 [P] [US3] S3: a resolved bare `:NN` on a blank line is reported -------


def test_bare_line_reference_resolving_to_blank_line_is_reported(run, tmp_path):
    target_repo = _target_tree(tmp_path)
    module_path = target_repo / "src" / "module.py"
    module_path.write_text("line one\n\nline three\n", encoding="utf-8")
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan=(
            "# Plan\n\n"
            "- `src/module.py:1` sets the path.\n"
            "- `:2` resolves to that file but line 2 is blank.\n"
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
    assert "src/module.py" in match["message"]
    assert "blank" in match["message"]
    assert match["severity"] == "refusal"


# --- T022 [P] [US3] S4: control — no bare refs, US1 behaviour unchanged --------


def test_document_with_no_bare_references_reports_nothing(run, tmp_path):
    target_repo = _target_tree(tmp_path)
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan=(
            "# Plan\n\n"
            "- `src/module.py:1` is a normal citation.\n"
        ),
        tasks=(
            "# Tasks\n\n"
            "## Phase 1: User Story 1 - Do a thing\n\n"
            "- [ ] T001 [US1-S1] first\n"
        ),
    )

    result = run("spec", "validate", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    assert "anchor resolution" in result.stdout
    assert "anchor_resolution" not in result.stderr
