"""US3: the spec HTML view consumes one typed validation report."""

from __future__ import annotations

import importlib.util
import sys
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
