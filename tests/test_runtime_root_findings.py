"""US2: the findings ledger is addressed through the runtime-root resolver.

Every test here chdir-s into a fresh tmp layout so `resolve_factory_root()`
cannot create `.ergane/` in the repository under test (plan trap 2).  The
process-global deprecation sentinel is reset by an autouse fixture so warning
assertions stay stable across the suite (plan trap 3).
"""

from __future__ import annotations

import ast
import io
import json
import sys
import warnings
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli import main as main_module
import factory.doctor.cli as doctor_cli
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.store import connect, report
from factory.workgraph.worktree import (
    DEFAULT_RUNTIME_ROOT,
    ERGANE_ROOT_ENV,
    FACTORY_ROOT_ENV,
    LEGACY_FACTORY_ROOT,
    _DEPRECATED_LEGACY_ROOT,
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


@pytest.fixture(autouse=True)
def _chdir_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every US2 test runs inside a throw-away filesystem layout."""
    # The session fixture pins ERGANE_ROOT/FACTORY_ROOT to a shared tmp path so
    # unrelated tests cannot reach the operator's checkout.  US2 tests exercise
    # the resolver's relative-path logic, so we drop the override and let
    # `resolve_factory_root()` read the cwd (which is tmp_path).
    monkeypatch.delenv(ERGANE_ROOT_ENV, raising=False)
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _freeze_utcnow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the doctor's age rendering deterministic."""
    monkeypatch.setattr(doctor_cli, "_utcnow", lambda: "2026-08-10T12:00:00Z")


@pytest.fixture(autouse=True)
def _reset_legacy_warning_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the one-per-process directory deprecation sentinel."""
    monkeypatch.setattr(
        "factory.workgraph.worktree._DEPRECATED_LEGACY_ROOT", None
    )


def _seed_doctor_db(
    path: Path, key: str = "ops/recurred-three-times", occurrences: int = 3
) -> Path:
    """Create a populated ledger at `path` with `key` at the given occurrence count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        first_seen = "2026-08-10T09:00:00Z"
        for i in range(occurrences):
            seen_at = f"2026-08-10T{9 + i:02d}:00:00Z"
            report(
                conn,
                Finding(
                    key=key,
                    category="ops",
                    severity=Severity.WARNING,
                    status=Status.OPEN,
                    summary="a recurring finding",
                    refs=["a:1"],
                    notes=None,
                    source="probe",
                    occurrences=1,
                    first_seen=first_seen,
                    last_seen=seen_at,
                    promoted_spec=None,
                    resolved_at=None,
                    resolution=None,
                ),
                seen_at=seen_at,
            )
    finally:
        conn.close()
    return path


def _line_for_key(stdout: str, key: str) -> str | None:
    for line in stdout.splitlines():
        if line.strip() and key in line:
            return line
    return None


# --- T009: new-root test ------------------------------------------------------


def test_new_root_reads_ergane_doctor_db_and_preserves_recurrence(
    tmp_path: Path, invoke: Callable[..., Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `.ergane/doctor.db` with no `.factory/` is read through the resolver."""
    _seed_doctor_db(tmp_path / DEFAULT_RUNTIME_ROOT / "doctor.db", occurrences=3)

    result = invoke("findings", "list")

    assert result.code == 0, (result.stdout, result.stderr)
    line = _line_for_key(result.stdout, "ops/recurred-three-times")
    assert line is not None
    # occurrences column is right-justified at width 5
    assert "    3" in line


# --- T008 / T013: split-state test --------------------------------------------


def test_split_state_follows_populated_legacy_ledger(
    tmp_path: Path, invoke: Callable[..., Run]
) -> None:
    """`.ergane/` exists but holds no ledger; `.factory/doctor.db` is populated.

    FR-006: the command MUST NOT silently open an empty ledger at the resolved
    root.  It follows the populated legacy ledger, so the recurrence count
    survives.
    """
    (tmp_path / DEFAULT_RUNTIME_ROOT).mkdir()
    _seed_doctor_db(tmp_path / LEGACY_FACTORY_ROOT / "doctor.db", occurrences=3)

    with pytest.warns(DeprecationWarning):
        result = invoke("findings", "list")

    assert result.code == 0
    # The empty new ledger must not have been created.
    assert not (tmp_path / DEFAULT_RUNTIME_ROOT / "doctor.db").exists()
    line = _line_for_key(result.stdout, "ops/recurred-three-times")
    assert line is not None
    assert "    3" in line


# --- T014: legacy-only test ---------------------------------------------------


def test_legacy_only_root_reads_factory_doctor_db_and_warns_once(
    tmp_path: Path, invoke: Callable[..., Run]
) -> None:
    """Only `.factory/doctor.db` exists; the resolver chooses legacy and warns."""
    _seed_doctor_db(tmp_path / LEGACY_FACTORY_ROOT / "doctor.db", occurrences=3)

    with pytest.warns(DeprecationWarning) as warning_record:
        result = invoke("findings", "list")

    assert result.code == 0
    assert len(warning_record) == 1
    assert ".factory is deprecated" in str(warning_record[0].message)
    line = _line_for_key(result.stdout, "ops/recurred-three-times")
    assert line is not None
    assert "    3" in line


# --- T015: explicit --db wins -------------------------------------------------


def test_explicit_db_wins_over_resolver(
    tmp_path: Path, invoke: Callable[..., Run]
) -> None:
    """An explicit `--db` path is used even when the resolved root has data."""
    explicit_db = tmp_path / "explicit" / "doctor.db"
    _seed_doctor_db(explicit_db, key="ops/explicit-store", occurrences=2)
    _seed_doctor_db(
        tmp_path / DEFAULT_RUNTIME_ROOT / "doctor.db",
        key="ops/resolver-store",
        occurrences=5,
    )

    result = invoke("findings", "list", "--db", str(explicit_db))

    assert result.code == 0
    assert "ops/explicit-store" in result.stdout
    assert "    2" in result.stdout
    assert "ops/resolver-store" not in result.stdout


# --- T016: no path defaults built from literal `.factory` ----------------------


def test_doctor_modules_do_not_carry_factory_literal_defaults() -> None:
    """The three doctor modules derive store paths from `resolve_factory_root()`.

    US2-S3 is about *path defaults*, not prose, so this check looks for
    `Path(".factory")` and `Path(".factory") / "..."` path-building expressions
    rather than a raw grep (plan trap 9).
    """
    modules = [
        Path(__file__).resolve().parents[1] / "factory" / "cli" / "doctor.py",
        Path(__file__).resolve().parents[1] / "factory" / "doctor" / "cli.py",
        Path(__file__).resolve().parents[1] / "factory" / "doctor" / "probes.py",
    ]
    for module in modules:
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if _is_path_built_from_factory_literal(node):
                raise AssertionError(
                    f"{module}:{node.lineno} builds a path from the literal '.factory'"
                )


def _is_path_built_from_factory_literal(node: ast.AST) -> bool:
    """True for `Path('.factory')` or `Path('.factory') / '...'`."""
    if isinstance(node, ast.Call):
        return _is_path_call_with_factory(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _is_path_built_from_factory_literal(node.left)
    return False


def _is_path_call_with_factory(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Name) or node.func.id != "Path":
        return False
    if not node.args:
        return False
    first = node.args[0]
    return isinstance(first, ast.Constant) and first.value == ".factory"
