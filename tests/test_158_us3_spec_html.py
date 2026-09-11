"""US3: the spec HTML view consumes one typed validation report."""

from __future__ import annotations

import importlib.util
import sys
import pytest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = REPO_ROOT / ".agents" / "skills" / "spec-html" / "render.py"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "spec_validate"
FIXTURE_REPO = FIXTURE_ROOT / "target-repo"
DEFECTIVE_TRIO = FIXTURE_ROOT / "defective-specs" / "002-defective-trio"


def load_renderer():
    spec = importlib.util.spec_from_file_location("ergane_spec_html_render", SKILL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_page_renders_the_typed_refusal_advisory_and_skip() -> None:
    """One `validate_spec` run supplies refusal, advisory, and skipped states."""
    from factory.spec import validate_spec

    report = validate_spec(
        DEFECTIVE_TRIO,
        target_repo=str(FIXTURE_REPO),
        specs_root=str(FIXTURE_ROOT / "defective-specs"),
    )
    renderer = load_renderer()
    spec = renderer.load(
        DEFECTIVE_TRIO,
        FIXTURE_REPO,
        None,
        specs_root=FIXTURE_ROOT / "defective-specs",
    )
    page = renderer.build(spec, str(FIXTURE_REPO), validation=report)

    assert f'Validation: {report.verdict}' in page
    for finding in report.findings:
        assert finding.severity in page
        assert finding.layer in page
        assert finding.message in page
    for skipped in report.skipped:
        assert skipped["layer"] in page
        assert skipped["reason"] in page


def test_no_landing_branch_is_unavailable_not_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A lookup that was not requested cannot masquerade as zero landings."""
    renderer = load_renderer()
    monkeypatch.setattr(renderer, "landed_facts", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("lookup attempted")))
    spec = renderer.load(
        DEFECTIVE_TRIO,
        FIXTURE_REPO,
        None,
        specs_root=FIXTURE_ROOT / "defective-specs",
    )
    assert spec.landed == {}
    assert spec.landing_state == "unavailable"
    assert "--landed-branch" in spec.landing_detail
    page = renderer.build(spec, str(FIXTURE_REPO))
    assert "Landing: unavailable" in page
    assert "--landed-branch" in page
    assert "0/1 stories" not in page


def test_empty_landing_result_is_empty_not_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty successful lookup remains its own state."""
    renderer = load_renderer()
    monkeypatch.setattr(renderer, "landed_facts", lambda *args, **kwargs: {})
    spec = renderer.load(
        DEFECTIVE_TRIO,
        FIXTURE_REPO,
        "main",
        specs_root=FIXTURE_ROOT / "defective-specs",
    )
    assert spec.landed == {}
    assert spec.landing_state == "empty"
    page = renderer.build(spec, str(FIXTURE_REPO))
    assert "Landing: empty" in page
    assert "No landing facts returned." in page


def test_landing_error_keeps_the_original_safe_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed lookup is visible with its original safe detail."""
    from factory.workgraph.worktree import WorktreeError

    renderer = load_renderer()

    def fail(*args, **kwargs):
        raise WorktreeError("git log refused: scratch failure")

    monkeypatch.setattr(renderer, "landed_facts", fail)
    spec = renderer.load(
        DEFECTIVE_TRIO,
        FIXTURE_REPO,
        "main",
        specs_root=FIXTURE_ROOT / "defective-specs",
    )
    assert spec.landed == {}
    assert spec.landing_state == "error"
    assert spec.landing_detail == "git log refused: scratch failure"
    page = renderer.build(spec, str(FIXTURE_REPO))
    assert "Landing: error" in page
    assert "git log refused: scratch failure" in page
    assert "0/1 stories" not in page
