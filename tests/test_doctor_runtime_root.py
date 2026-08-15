"""US2: the findings ledger is resolved through the runtime-root resolver.

Every test runs inside a pytest tmp directory with the ERGANE_ROOT/FACTORY_ROOT
environment overrides removed, so resolve_factory_root() reads the cwd-relative
directories the same way an operator-run command does.  A per-test fixture resets
the process-global deprecation sentinels so warning assertions are deterministic.
"""

from __future__ import annotations

import ast
import json
import warnings
from pathlib import Path
from typing import Generator

import pytest

from factory.cli.main import main
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.store import connect, report, resolved_doctor_db_path

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runtime_root_isolation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Chdir into tmp, drop env overrides, and reset deprecation sentinels."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ERGANE_ROOT", raising=False)
    monkeypatch.delenv("FACTORY_ROOT", raising=False)

    import factory.env as _env
    import factory.workgraph.worktree as _worktree

    monkeypatch.setattr(_worktree, "_DEPRECATED_LEGACY_ROOT", None)
    monkeypatch.setattr(_env, "_WARNED", set())
    return tmp_path


def _make_populated_doctor_db(
    path: Path, *, key: str = "test/key", occurrences: int = 3
) -> None:
    """Create a doctor.db at ``path`` with ``key`` at the requested recurrence."""
    conn = connect(path)
    for _ in range(occurrences):
        report(
            conn,
            Finding(
                key=key,
                category="test",
                severity=Severity.CRITICAL,
                status=Status.OPEN,
                summary="test finding",
                refs=["file:1"],
                notes=None,
                source="test",
                occurrences=1,
                first_seen="",
                last_seen="",
                promoted_spec=None,
                resolved_at=None,
                resolution=None,
            ),
            seen_at="2026-08-15T00:00:00Z",
        )
    conn.close()


class TestResolvedDoctorDbPath:
    """The helper itself follows the data when the resolved root holds none."""

    def test_new_root_with_populated_db(
        self, runtime_root_isolation: Path, capsys: pytest.CaptureFixture
    ) -> None:
        (runtime_root_isolation / ".ergane").mkdir()
        new_db = runtime_root_isolation / ".ergane" / "doctor.db"
        _make_populated_doctor_db(new_db, occurrences=3)

        result = main(["findings", "list", "--json"])

        assert result == 0
        out = json.loads(capsys.readouterr().out)
        assert len(out) == 1
        assert out[0]["key"] == "test/key"
        assert out[0]["occurrences"] == 3

    def test_legacy_only_repo_reads_and_warns(
        self, runtime_root_isolation: Path, capsys: pytest.CaptureFixture
    ) -> None:
        (runtime_root_isolation / ".factory").mkdir()
        legacy_db = runtime_root_isolation / ".factory" / "doctor.db"
        _make_populated_doctor_db(legacy_db, occurrences=3)

        with pytest.warns(DeprecationWarning, match=r"\.factory is deprecated"):
            result = main(["findings", "list", "--json"])

        assert result == 0
        out = json.loads(capsys.readouterr().out)
        assert len(out) == 1
        assert out[0]["occurrences"] == 3

    def test_split_state_follows_populated_legacy_ledger(
        self, runtime_root_isolation: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """FR-006: .ergane/ exists but is empty; .factory/doctor.db is populated.

        The command must not silently open an empty ledger at the resolved root.
        It follows the populated legacy ledger, preserving recurrence counts.
        """
        (runtime_root_isolation / ".ergane").mkdir()
        (runtime_root_isolation / ".factory").mkdir()
        legacy_db = runtime_root_isolation / ".factory" / "doctor.db"
        _make_populated_doctor_db(legacy_db, occurrences=3)
        assert not (runtime_root_isolation / ".ergane" / "doctor.db").exists()

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = main(["findings", "list", "--json"])

        assert result == 0
        out = json.loads(capsys.readouterr().out)
        assert len(out) == 1
        assert out[0]["occurrences"] == 3
        # The empty resolved ledger must not have been created by the read.
        assert not (runtime_root_isolation / ".ergane" / "doctor.db").exists()


class TestExplicitDbWins:
    """An explicit --db argument beats the resolver."""

    def test_db_flag_wins_over_resolver(
        self, runtime_root_isolation: Path, capsys: pytest.CaptureFixture
    ) -> None:
        (runtime_root_isolation / ".ergane").mkdir()
        default_db = runtime_root_isolation / ".ergane" / "doctor.db"
        _make_populated_doctor_db(default_db, key="default/key", occurrences=1)

        custom_db = runtime_root_isolation / "custom.db"
        _make_populated_doctor_db(custom_db, key="custom/key", occurrences=5)

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = main(["findings", "list", "--db", str(custom_db), "--json"])

        assert result == 0
        out = json.loads(capsys.readouterr().out)
        assert len(out) == 1
        assert out[0]["key"] == "custom/key"
        assert out[0]["occurrences"] == 5


class TestNoLiteralFactoryPathDefaults:
    """The three doctor modules must not build path defaults from literal .factory."""

    @pytest.mark.parametrize(
        "module_path",
        [
            REPO_ROOT / "factory" / "cli" / "doctor.py",
            REPO_ROOT / "factory" / "doctor" / "cli.py",
            REPO_ROOT / "factory" / "doctor" / "probes.py",
        ],
    )
    def test_no_path_default_built_from_literal_factory(
        self, module_path: Path
    ) -> None:
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        bad: list[ast.AST] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "Path":
                    if (
                        node.args
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value == ".factory"
                    ):
                        bad.append(node)
        assert not bad, (
            f"{module_path.relative_to(REPO_ROOT)} still builds paths from "
            f"literal '.factory': {[ast.dump(n) for n in bad]}"
        )
