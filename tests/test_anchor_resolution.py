"""US1: anchor resolution checks for `ergane spec validate`.

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
    frontmatter_extra: str = "",
    spec_body_extra: str = "",
    plan: str = "# Plan\n\n",
    tasks: str = "# Tasks\n\n",
) -> None:
    """Write a minimal Spec Kit trio."""
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_text = (
        "---\n"
        f"state: {state}\n"
        f"{frontmatter_extra}"
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


# --- S1-S3: the three broken-anchor shapes -----------------------------------


def test_validate_reports_citation_past_end_of_file(run, tmp_path):
    target_repo = _target_tree(tmp_path)
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan="# Plan\n\n- see `src/module.py:10` for context.\n",
    )

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 1
    findings = result.json["findings"]
    assert any(f["layer"] == "anchor_resolution" for f in findings)
    match = next(f for f in findings if f["layer"] == "anchor_resolution")
    assert "plan.md" in match["message"]
    assert "src/module.py:10" in match["message"]
    assert "past end of file" in match["message"]
    assert match["severity"] == "refusal"


def test_validate_reports_citation_on_blank_line(run, tmp_path):
    target_repo = _target_tree(tmp_path)
    # Make line 2 blank.
    module_path = target_repo / "src" / "module.py"
    module_path.write_text("line one\n\nline three\n", encoding="utf-8")
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan="# Plan\n\n- see `src/module.py:2` for context.\n",
    )

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 1
    findings = result.json["findings"]
    match = next(f for f in findings if f["layer"] == "anchor_resolution")
    assert "plan.md" in match["message"]
    assert "src/module.py:2" in match["message"]
    assert "blank" in match["message"]
    assert match["severity"] == "refusal"


def test_validate_reports_citation_to_absent_file(run, tmp_path):
    target_repo = _target_tree(tmp_path)
    # Add a second cited file that exists so the layer does not treat the repo
    # as unreadable when it encounters the missing one.
    (target_repo / "src" / "other.py").write_text("line one\n", encoding="utf-8")
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        plan="# Plan\n\n- see `src/missing.py:1` and `src/other.py:1`.\n",
    )

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 1
    findings = result.json["findings"]
    match = next(f for f in findings if f["layer"] == "anchor_resolution")
    assert "plan.md" in match["message"]
    assert "src/missing.py:1" in match["message"]
    assert "absent" in match["message"]
    assert match["severity"] == "refusal"


# --- S4-S5: what must not be reported ----------------------------------------


def test_validate_skips_citation_inside_fenced_block(run, tmp_path):
    target_repo = _target_tree(tmp_path)
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        state="landed",
        plan=(
            "# Plan\n\n"
            "```text\n"
            "This would be broken: `src/module.py:99`.\n"
            "```\n"
            "- and `src/module.py:1` is fine.\n"
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


def test_validate_skips_citation_inside_spec_frontmatter(run, tmp_path):
    target_repo = _target_tree(tmp_path)
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        state="landed",
        frontmatter_extra=(
            "# A held spec records its own broken anchor: `src/module.py:99`.\n"
        ),
        plan="# Plan\n\n- `src/module.py:1` is fine.\n",
        tasks=(
            "# Tasks\n\n"
            "## Phase 1: User Story 1 - Do a thing\n\n"
            "- [ ] T001 [US1-S1] first\n"
        ),
    )

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    assert not any(f["layer"] == "anchor_resolution" for f in result.json["findings"])


# --- S6: the control ----------------------------------------------------------


def test_validate_reports_nothing_when_anchors_resolve(run, tmp_path):
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

    json_result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))
    assert not any(f["layer"] == "anchor_resolution" for f in json_result.json["findings"])
    assert "anchor_resolution" in json_result.json["checked"]

    # Prove the control can fail: break one anchor and watch it report.
    plan_path = spec_dir / "plan.md"
    plan_path.write_text(plan_path.read_text(encoding="utf-8").replace("src/module.py:3", "src/module.py:99"), encoding="utf-8")
    rerun = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))
    assert rerun.code == 1
    assert any(f["layer"] == "anchor_resolution" for f in rerun.json["findings"])


# --- S7: missing target repo ------------------------------------------------


def test_validate_skips_anchor_layer_when_target_repo_missing(run, tmp_path):
    missing_repo = tmp_path / "does-not-exist"
    spec_dir = tmp_path / "001-demo"
    _write_spec(
        spec_dir,
        state="landed",
        plan="# Plan\n\n- see `src/module.py:1`.\n",
        tasks=(
            "# Tasks\n\n"
            "## Phase 1: User Story 1 - Do a thing\n\n"
            "- [ ] T001 [US1-S1] first\n"
        ),
    )

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(missing_repo))

    assert result.code == 0
    assert not any(f["layer"] == "anchor_resolution" for f in result.json["findings"])
    skipped = result.json["skipped"]
    assert any(
        entry["layer"] == "anchor_resolution" and str(missing_repo) in entry["reason"]
        for entry in skipped
    )
