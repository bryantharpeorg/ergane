"""US3: the spec HTML view consumes one typed validation report."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import pytest
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
    assert spec.validation == report
    page = renderer.build(spec, str(FIXTURE_REPO))

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


def test_requested_local_output_writes_only_that_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rendering without publication intent changes one local filesystem path."""
    renderer = load_renderer()
    spec_dir = tmp_path / "001-local-only"
    spec_dir.mkdir()
    for name in ("spec.md", "plan.md", "tasks.md"):
        shutil.copyfile(DEFECTIVE_TRIO / name, spec_dir / name)
    output = tmp_path / "chosen.html"
    before = set(tmp_path.rglob("*"))
    monkeypatch.setattr(
        renderer,
        "landed_facts",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network or git action")),
    )
    returned = renderer.render_local(
        spec_dir,
        FIXTURE_REPO,
        None,
        specs_root=tmp_path / "specs",
        output=output,
    )
    assert returned == output
    after = set(tmp_path.rglob("*"))
    assert after - before == {output}


def test_default_render_writes_one_unique_scratch_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No requested output makes one local scratch path, never a remote publication."""
    renderer = load_renderer()
    spec_dir = tmp_path / "001-local-only"
    spec_dir.mkdir()
    for name in ("spec.md", "plan.md", "tasks.md"):
        shutil.copyfile(DEFECTIVE_TRIO / name, spec_dir / name)
    before = {path.name for path in tmp_path.iterdir()}
    monkeypatch.setattr(
        renderer,
        "landed_facts",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network or git action")),
    )
    returned = renderer.render_local(
        spec_dir,
        FIXTURE_REPO,
        None,
        specs_root=tmp_path / "specs",
        scratch_dir=tmp_path,
    )
    after = {path.name for path in tmp_path.iterdir()}
    assert returned == tmp_path / returned.name
    assert returned.name.startswith("001-local-only-")
    assert returned.suffix == ".html"
    assert after - before == {returned.name}


def test_renderer_uses_the_library_report_instead_of_anchor_validation() -> None:
    """The view owns no anchor parser, and its source binds the public validator."""
    renderer = load_renderer()
    source = SKILL_PATH.read_text(encoding="utf-8")
    assert "from factory.spec import SpecValidation, validate_spec" in source
    assert "resolve_anchors" not in source
    assert "ANCHOR_RE" not in source
    assert not hasattr(renderer, "Anchor")


def test_skill_contract_names_local_path_and_separate_publication() -> None:
    """The skill tells the operator what rendering returns and what it never does."""
    contract = (REPO_ROOT / ".agents" / "skills" / "spec-html" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "returns that local path" in contract
    assert "publication is a separate authorized action" in contract
    assert ".agents/skills/spec-html/render.py" in contract
