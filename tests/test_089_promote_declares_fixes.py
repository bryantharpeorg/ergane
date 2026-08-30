"""US1 of 089: `ergane findings promote` declares the keys it was built from.

Every test builds its own store and specs root under ``tmp_path`` (trap 7),
and `_own_findings_store` holds the verbs to it.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

import factory.doctor.cli as _doctor_cli
from factory.cli import main as main_module
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.store import connect, report
from factory.doctor.triage import _declaration


@pytest.fixture(autouse=True)
def _own_findings_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Put both findings-store candidates under this test's own `tmp_path`.

    `findings promote` is told its store with `--db`, but `spec validate` is
    not: it resolves one, and that resolution has two candidates.  When the
    runtime root holds no ledger, `_resolve_store_path` falls back to the legacy
    runtime root *relative to the working directory* — the operator's real
    ledger on the machine that does the building, which then decided whether a
    promoted spec's own `fixes:` keys were known (122-US3, trap 6).

    Pointing the root at `tmp_path` is what makes the store this module already
    seeds there the one the verbs read.
    """
    monkeypatch.setenv("ERGANE_ROOT", str(tmp_path))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    monkeypatch.setattr(
        _doctor_cli, "LEGACY_FACTORY_ROOT", tmp_path / "legacy-runtime-root"
    )


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: list[str]) -> Run:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


@pytest.fixture
def invoke() -> Callable[..., Run]:
    def _caller(*argv: str) -> Run:
        return _invoke(list(argv))
    return _caller


def _seed_store(db_path: Path, keys: list[str]) -> None:
    """Write open findings for the given keys into a fresh store."""
    conn = connect(db_path)
    try:
        for key in keys:
            category, _, slug = key.partition("/")
            report(
                conn,
                Finding(
                    key=key,
                    category=category,
                    severity=Severity.INFO,
                    status=Status.OPEN,
                    summary=f"Summary for {key}",
                    refs=["factory/foo.py:1"],
                    notes=None,
                    source="test",
                    occurrences=1,
                    first_seen="2026-08-29T00:00:00Z",
                    last_seen="2026-08-29T00:00:00Z",
                    promoted_spec=None,
                    resolved_at=None,
                    resolution=None,
                ),
                seen_at="2026-08-29T00:00:00Z",
            )
    finally:
        conn.close()


@pytest.fixture
def promoted_dir(tmp_path: Path) -> Path:
    """A specs root containing one promoted spec built from a/one and b/two."""
    db_path = tmp_path / "doctor.db"
    specs_root = tmp_path / "specs"
    _seed_store(db_path, ["a/one", "b/two"])

    result = _invoke(
        [
            "findings",
            "promote",
            "--db",
            str(db_path),
            "--slug",
            "s",
            "--keys",
            "a/one",
            "b/two",
            "--specs-root",
            str(specs_root),
            "--target-repo",
            ".",
        ]
    )
    assert result.code == 0, result.stderr
    return specs_root / "s"


def test_frontmatter_declares_fixes_in_order(promoted_dir: Path) -> None:
    """T001 / US1-S1: frontmatter carries state: draft and the ordered fixes: list."""
    spec_text = (promoted_dir / "spec.md").read_text(encoding="utf-8")
    assert spec_text.startswith("---\n")
    parts = spec_text.split("---\n", 2)
    frontmatter = parts[1]

    lines = frontmatter.splitlines()
    assert lines[0] == "state: draft"
    fixes_idx = lines.index("fixes:")
    assert lines[fixes_idx + 1] == "  - a/one"
    assert lines[fixes_idx + 2] == "  - b/two"
    # No extra entries.
    assert not any(line.startswith("  - ") and line not in {"  - a/one", "  - b/two"} for line in lines)


def test_frontmatter_parses_through_declaration(promoted_dir: Path) -> None:
    """T002 / US1-S2: _declaration returns both keys, not []."""
    spec_text = (promoted_dir / "spec.md").read_text(encoding="utf-8")
    parts = spec_text.split("---\n", 2)
    state, fixes = _declaration(parts[1])
    assert state == "draft"
    assert fixes == ["a/one", "b/two"]


def test_prose_still_names_key_everywhere(invoke: Callable[..., Run], tmp_path: Path) -> None:
    """T003 / US1-S3: the promoted key remains in all four prose positions."""
    db_path = tmp_path / "doctor.db"
    specs_root = tmp_path / "specs"
    _seed_store(db_path, ["a/one"])

    result = invoke(
        "findings",
        "promote",
        "--db",
        str(db_path),
        "--slug",
        "s",
        "--keys",
        "a/one",
        "--specs-root",
        str(specs_root),
        "--target-repo",
        ".",
    )
    assert result.code == 0, result.stderr

    spec_text = (specs_root / "s" / "spec.md").read_text(encoding="utf-8")
    plan_text = (specs_root / "s" / "plan.md").read_text(encoding="utf-8")
    tasks_text = (specs_root / "s" / "tasks.md").read_text(encoding="utf-8")

    # Given clause in the acceptance scenario.
    assert "**Given** the finding `a/one`" in spec_text
    # Functional requirement bullet.
    assert "- **FR-001**: The factory MUST address `a/one`" in spec_text
    # Addressed-findings bullet in plan.md.
    assert "- `a/one`" in plan_text
    # Task bullet in tasks.md.
    assert "`a/one`" in tasks_text


def test_validate_verdict_unchanged(invoke: Callable[..., Run], tmp_path: Path) -> None:
    """T004 / US1-S4: validate returns the same verdict as for a promote-generated trio."""
    db_path = tmp_path / "doctor.db"
    specs_root = tmp_path / "specs"
    _seed_store(db_path, ["a/one"])

    result = invoke(
        "findings",
        "promote",
        "--db",
        str(db_path),
        "--slug",
        "s",
        "--keys",
        "a/one",
        "--specs-root",
        str(specs_root),
        "--target-repo",
        ".",
    )
    assert result.code == 0, result.stderr

    result = invoke("spec", "validate", "--json", str(specs_root / "s"))
    # US1 adds a frontmatter declaration; this test records the verdict a promote-
    # generated trio already produced, so we can prove the declaration changed
    # nothing.  Promote-generated trios have no task-phase headings, so
    # prompt_assembly refuses and scenario_coverage advises; a new frontmatter
    # finding would be evidence US1 broke validation.
    assert result.code == 1, result.stderr
    findings = result.json.get("findings", [])
    assert not any(finding.get("layer") == "frontmatter" for finding in findings)
    assert {f["layer"]: f["severity"] for f in findings} == {
        "scenario_coverage": "advisory",
        "prompt_assembly": "refusal",
    }


def test_slot_scaffold_has_no_fixes_key(tmp_path: Path) -> None:
    """T005 / trap 1: the slot form of scaffold_spec emits state: draft only."""
    from factory.doctor.scaffold import scaffold_spec

    spec_text, _plan, _tasks = scaffold_spec(
        slug="slot-demo", title="A slot feature", anchor="factory/foo.py:1"
    )
    assert spec_text.startswith("---\n")
    parts = spec_text.split("---\n", 2)
    frontmatter = parts[1]
    assert frontmatter.strip() == "state: draft"
    assert "fixes:" not in frontmatter
