"""057/US3: a seeded floor's age is visible.

The seeded constitution records which installed floor produced it, and
`ergane init --check` reports whether that recorded version is current, behind,
or unknown. The report is advisory: it never blocks readiness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import factory.cli.init as init_module
from factory.constitution import DEFAULT_FLOOR_VERSION as FLOOR_VERSION, shipped_floor_text
from factory.stack_packs import agnostic_layer
from factory.mergequeue.forge import LandingPolicy, RepositoryDescription
from factory.mergequeue.models import Finding, Severity
from factory.mergequeue.onboard import InitFacts, evaluate_repo

from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init import ScriptedPrompter, _git, _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams, conforming_gh

REPO = "acme/widgets"
DEFAULT_BRANCH = "main"

#: Minimal interactive answers that let init use defaults for every optional key.
MINIMAL_ANSWERS: list[str] = [
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
    "myapp",  # slug
]


# --- pure helpers ------------------------------------------------------------


def _reading(**over: object) -> RepositoryDescription:
    base = dict(address=REPO, default_branch=DEFAULT_BRANCH)
    return RepositoryDescription(**{**base, **over})  # type: ignore[arg-type]


def _policy(**over: object) -> LandingPolicy:
    base = dict(
        branch=DEFAULT_BRANCH,
        gates_on_named_checks=True,
        required_checks=("test",),
        lands_without_a_human=True,
        landing_title_from_proposal=True,
        landing_title_source="proposal-title",
    )
    return LandingPolicy(**{**base, **over})  # type: ignore[arg-type]


def _init_facts(**overrides: object) -> InitFacts:
    facts: dict[str, Any] = dict(
        repo_root="/repos/widgets",
        runtime_root=".ergane",
        runtime_root_is_legacy=False,
        runtime_root_ignored=True,
        gitignore="/repos/widgets/.gitignore",
        registry_path="/state/ergane/repos.json",
        registry_slug="widgets",
        registry_error=None,
        landing_branch="main",
        landing_branch_exists=True,
        standards_path="docs/STANDARDS.md",
        standards_exists=True,
        standards_recorded_version=FLOOR_VERSION,
        installed_floor_version=FLOOR_VERSION,
        control_plane=(Finding("temporal", True, "namespace `factory` exists"),),
        control_plane_error=None,
        schedule_id="ergane-roadmap-widgets",
        schedule_present=True,
        schedule_paused=False,
        schedule_drift=(),
        schedule_error=None,
    )
    facts.update(overrides)
    return InitFacts(**facts)  # type: ignore[arg-type]


def _judge(**overrides: object) -> Any:
    return evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=("test",),
        init_facts=_init_facts(**overrides),
    )


def _floor_finding(profile: Any) -> Finding:
    for finding in profile.findings:
        if finding.check == "standards_floor":
            return finding
    raise AssertionError(
        f"no standards_floor finding; got {[f.check for f in profile.findings]}"
    )


# --- T024 [US3] (spec US3-S1, FR-011) ----------------------------------------


def test_composed_output_records_floor_version() -> None:
    """The seeded document records the floor version it came from."""
    text = init_module.compose_constitution(
        shipped_floor_text(),
        "shipped-default",
        project_name="app",
        stack_layer=agnostic_layer(),
    )
    assert f"floor version {FLOOR_VERSION}" in text


def test_floor_version_is_machine_readable_and_human_visible() -> None:
    """The marker is a predictable pattern a parser can read and a human can see."""
    text = init_module.compose_constitution(
        shipped_floor_text(),
        "shipped-default",
        project_name="app",
        stack_layer=agnostic_layer(),
    )
    assert f"(floor version {FLOOR_VERSION})" in text
    assert "Governance" in text


# --- T025 [US3] (spec US3-S2, FR-012, SC-005) --------------------------------


def test_document_at_older_floor_is_reported_behind_naming_both_versions() -> None:
    """A document recorded at floor N, checked against installed N+1, is behind."""
    profile = _judge(
        standards_recorded_version="0.9.0",
        installed_floor_version="1.0.0",
    )
    finding = _floor_finding(profile)
    assert finding.passed is False
    assert finding.severity == Severity.WARNING
    assert "0.9.0" in finding.detail
    assert "1.0.0" in finding.detail
    assert "0.9.0" in finding.detail
    assert "1.0.0" in finding.detail
    assert "installed" in finding.detail.lower() or "newer" in finding.detail.lower()


def test_check_reports_behind_and_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed a repo, bump the installed floor, and `--check` reports behind without writing."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    offline = FakeScheduleServer()
    bind_offline_seams(monkeypatch, conforming_gh(), schedules=offline)
    prompter = ScriptedPrompter(list(MINIMAL_ANSWERS))
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)

    result = _invoke(["init", str(repo)], monkeypatch)
    assert result.code == 0, result.stderr

    constitution = repo / ".specify" / "memory" / "constitution.md"
    assert constitution.exists()
    before = constitution.read_bytes()

    # Bump the installed floor version to simulate a newer Ergane release.
    monkeypatch.setattr(init_module, "FLOOR_VERSION", "99.0.0")
    monkeypatch.setattr("factory.mergequeue.onboard.DEFAULT_FLOOR_VERSION", "99.0.0")

    check_result = _invoke(["init", "--check", str(repo)], monkeypatch)
    after = constitution.read_bytes()

    assert "standards_floor" in check_result.stdout
    assert "99.0.0" in check_result.stdout
    assert "[WARN] standards_floor" in check_result.stdout
    assert before == after, "--check modified the standards document"


# --- T026 [P] [US3] (spec US3-S3, FR-014) ------------------------------------


def test_handwritten_document_with_no_recorded_version_is_reported_unknown() -> None:
    """A standards document with no recorded floor version is reported unknown."""
    profile = _judge(standards_recorded_version=None)
    finding = _floor_finding(profile)
    assert finding.passed is False
    assert finding.severity == Severity.WARNING
    assert "unknown" in finding.detail.lower()


# --- T027 [P] [US3] (spec US3-S4) -------------------------------------------


def test_document_at_installed_floor_is_reported_current() -> None:
    """A document at the installed floor version is reported current."""
    profile = _judge()
    finding = _floor_finding(profile)
    assert finding.passed is True
    assert FLOOR_VERSION in finding.detail


# --- T027a [P] [US3] (spec US3-S5, FR-019) -----------------------------------


def test_repository_reported_behind_is_still_ready() -> None:
    """An out-of-date floor is advisory; readiness stays true."""
    profile = _judge(
        standards_recorded_version="0.9.0",
        installed_floor_version="1.0.0",
    )
    assert profile.passed is True


def test_behind_report_is_not_phrased_as_noncompliance() -> None:
    """The advisory wording never describes the repository as non-compliant."""
    profile = _judge(
        standards_recorded_version="0.9.0",
        installed_floor_version="1.0.0",
    )
    finding = _floor_finding(profile)
    detail = finding.detail.lower()
    for word in (
        "non-compliant",
        "noncompliant",
        "refuse",
        "blocking",
        "fails",
        "not ready",
    ):
        assert word not in detail, f"detail reads as non-compliance: {finding.detail!r}"
