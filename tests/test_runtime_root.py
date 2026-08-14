"""Tests for the runtime root resolution and migration (US2).

The factory's runtime state lives under `.ergane/` by default.  Existing
managed repos may still have `.factory/`; the resolver must honor that legacy
name and tell the operator to migrate.  The migration itself is an operator
command so it can refuse to run while an epic is in flight.

Every test here uses tmp roots.  030's store guard refuses to open a real store
path under pytest, but that guard is a backstop, not the safety net these
tests rely on.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import warnings
from pathlib import Path
from typing import Callable

import pytest

import factory.workgraph.worktree as worktree_module
from factory.activities.agent_activities import (
    FACTORY_ROOT_ENV,
    factory_root,
)
from factory.workgraph.worktree import (
    DEFAULT_FACTORY_ROOT,
    DEFAULT_RUNTIME_ROOT,
    LEGACY_FACTORY_ROOT,
    RuntimeRootChoice,
    resolve_factory_root,
)

#: The migration command the resolver names when it finds the legacy root.
MIGRATION_COMMAND = "ergane repo migrate-runtime-root"


def _unset_factory_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure the resolver reads the default, not an env override."""
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)


@pytest.fixture(autouse=True)
def _reset_resolver_sentinel() -> None:
    """Each test sees the deprecation warning fresh, despite the module-level flag."""
    worktree_module._DEPRECATED_LEGACY_ROOT = None
    yield
    worktree_module._DEPRECATED_LEGACY_ROOT = None


# --- T008: root resolution ----------------------------------------------------


def test_resolve_no_root_creates_ergane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No runtime root -> the resolver creates and returns `.ergane/`."""
    _unset_factory_root(monkeypatch)
    monkeypatch.chdir(tmp_path)
    root, choice = resolve_factory_root()
    assert root.resolve() == tmp_path / DEFAULT_RUNTIME_ROOT
    assert choice is RuntimeRootChoice.NEW
    assert (tmp_path / DEFAULT_RUNTIME_ROOT).is_dir()


def test_resolve_legacy_only_uses_it_and_names_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only `.factory/` exists -> use it and tell the operator how to migrate."""
    _unset_factory_root(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / LEGACY_FACTORY_ROOT).mkdir()
    (tmp_path / LEGACY_FACTORY_ROOT / "verification.db").write_text("legacy", encoding="utf-8")

    with pytest.warns(DeprecationWarning, match=MIGRATION_COMMAND):
        root, choice = resolve_factory_root()

    assert root.resolve() == tmp_path / LEGACY_FACTORY_ROOT
    assert choice is RuntimeRootChoice.LEGACY
    assert (tmp_path / DEFAULT_RUNTIME_ROOT).is_dir() is False
    assert (tmp_path / LEGACY_FACTORY_ROOT / "verification.db").read_text(encoding="utf-8") == "legacy"


def test_resolve_new_wins_when_both_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If both `.ergane/` and `.factory/` exist, `.ergane/` wins."""
    _unset_factory_root(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / DEFAULT_RUNTIME_ROOT).mkdir()
    (tmp_path / DEFAULT_RUNTIME_ROOT / "verification.db").write_text("new", encoding="utf-8")
    (tmp_path / LEGACY_FACTORY_ROOT).mkdir()
    (tmp_path / LEGACY_FACTORY_ROOT / "verification.db").write_text("legacy", encoding="utf-8")

    with pytest.warns(DeprecationWarning, match="ignored"):
        root, choice = resolve_factory_root()

    assert root.resolve() == tmp_path / DEFAULT_RUNTIME_ROOT
    assert choice is RuntimeRootChoice.NEW


def test_factory_root_helper_routes_through_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`factory_root()` from agent_activities returns what `resolve_factory_root` chose."""
    _unset_factory_root(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / LEGACY_FACTORY_ROOT).mkdir()

    with pytest.warns(DeprecationWarning, match=MIGRATION_COMMAND):
        assert factory_root().resolve() == tmp_path / LEGACY_FACTORY_ROOT


# --- T009/T012: migration -----------------------------------------------------


@pytest.fixture
def migration_runner(monkeypatch: pytest.MonkeyPatch) -> Callable[..., tuple[int, str, str]]:
    """Run the migration command in-process and capture stdout/stderr."""
    def run(args: argparse.Namespace, env: dict[str, str] | None = None) -> tuple[int, str, str]:
        import io
        import sys

        saved = {k: os.environ.get(k) for k in (env or {})}
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        from factory.cli.errors import OperatorError

        try:
            old_stdout, old_stderr = sys.stdout, sys.stderr
            buf_out, buf_err = io.StringIO(), io.StringIO()
            try:
                sys.stdout, sys.stderr = buf_out, buf_err
                from factory.cli.repo import migrate_runtime_root_command
                try:
                    code = migrate_runtime_root_command(args)
                except OperatorError as exc:
                    print(f"ergane: {exc}", file=sys.stderr)
                    code = exc.code
                except SystemExit as exc:
                    code = 0 if exc.code is None else int(exc.code)
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
        finally:
            for k, v in saved.items():
                if v is None:
                    monkeypatch.delenv(k, raising=False)
                else:
                    monkeypatch.setenv(k, v)
        return code, buf_out.getvalue(), buf_err.getvalue()

    return run


@pytest.fixture
def no_epics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the migration's capacity read to report no running epics."""
    import factory.cli.repo as repo_module

    async def empty() -> set[str]:
        return set()

    monkeypatch.setattr(repo_module, "_running_epic_ids", empty)


@pytest.fixture
def yes_args() -> argparse.Namespace:
    """An argparse namespace with --yes set, as the real parser would produce."""
    return argparse.Namespace(yes=True)


def _count_rows(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _seed_legacy_root(legacy: Path) -> tuple[int, int]:
    """Create verification.db and ledger.db under `legacy` and return row counts."""
    legacy.mkdir(parents=True, exist_ok=True)
    verify_db = legacy / "verification.db"
    ledger_db = legacy / "ledger.db"

    # Use the real schemas so opening with the real connect() after the move works.
    from factory.usage import ledger
    from factory.verify import store

    with sqlite3.connect(verify_db) as conn:
        store._bootstrap_schema(conn)
        conn.execute(
            "INSERT INTO verification_results "
            "(epic_id, node_id, attempt, form, verdict, gate_results, output_check, "
            "criteria_sha256, spec_ref, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("epic-legacy", "node-a", 1, "PHASE", "PASS", "[]", "{}",
             "sha", "spec-legacy", "2026-08-13T00:00:00Z", "2026-08-13T00:01:00Z"),
        )
        conn.commit()

    with sqlite3.connect(ledger_db) as conn:
        ledger._bootstrap_schema(conn)
        conn.execute(
            "INSERT INTO usage_records "
            "(epic_id, node_id, attempt, persona, spec_ref, key_alias, "
            "final_usage_confirmed, termination, issued_at, torn_down_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("epic-legacy", "node-a", 1, "impl", "spec-legacy", "epic-legacy:node-a:1:impl",
             0, "completed", "2026-08-13T00:00:00Z", "2026-08-13T00:01:00Z"),
        )
        conn.commit()

    return _count_rows(verify_db, "verification_results"), _count_rows(ledger_db, "usage_records")


def test_migration_moves_rows_intact_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    migration_runner: Callable[..., tuple[int, str, str]],
    no_epics: None,
    yes_args: argparse.Namespace,
) -> None:
    """A populated legacy root migrates with identical row counts (FR-007).

    The migration moves `.factory/` to `.ergane/`.  The verification and usage
    stores must open after the move and return the counts they held before it.
    A second run reports already-migrated and moves nothing (idempotency).

    Pasted evidence (T012) — captured from a real tmp-root run:

        Before migration:
            verification_results: 1
            usage_records: 1
        After migration:
            verification_results: 1
            usage_records: 1

    A second run reports already-migrated and moves nothing (idempotency),
    leaving the counts unchanged.
    """
    _unset_factory_root(monkeypatch)
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / LEGACY_FACTORY_ROOT
    before_verify, before_usage = _seed_legacy_root(legacy)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        code, out, err = migration_runner(yes_args)

    assert code == 0, err
    assert (tmp_path / DEFAULT_RUNTIME_ROOT).is_dir()
    assert (tmp_path / LEGACY_FACTORY_ROOT).exists() is False

    after_verify = _count_rows(tmp_path / DEFAULT_RUNTIME_ROOT / "verification.db", "verification_results")
    after_usage = _count_rows(tmp_path / DEFAULT_RUNTIME_ROOT / "ledger.db", "usage_records")
    assert after_verify == before_verify, f"verification rows changed: {before_verify} -> {after_verify}"
    assert after_usage == before_usage, f"usage rows changed: {before_usage} -> {after_usage}"

    # Idempotency: second run reports already-migrated and leaves files untouched.
    code2, out2, err2 = migration_runner(yes_args)
    assert code2 == 0, err2
    assert "already migrated" in out2.lower()
    assert _count_rows(tmp_path / DEFAULT_RUNTIME_ROOT / "verification.db", "verification_results") == before_verify
    assert _count_rows(tmp_path / DEFAULT_RUNTIME_ROOT / "ledger.db", "usage_records") == before_usage


def test_migration_refuses_when_epic_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    migration_runner: Callable[..., tuple[int, str, str]],
    yes_args: argparse.Namespace,
) -> None:
    """A running epic is refused by name so the store is not moved out from under it."""
    _unset_factory_root(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / LEGACY_FACTORY_ROOT).mkdir()

    # Script the migration's capacity helper to report one open epic.
    import factory.cli.repo as repo_module

    async def scripted_open_epics() -> set[str]:
        return {"epic-040-live"}

    monkeypatch.setattr(repo_module, "_running_epic_ids", scripted_open_epics)

    code, out, err = migration_runner(yes_args)

    assert code == 1
    assert "epic-040-live" in err
    assert (tmp_path / DEFAULT_RUNTIME_ROOT).exists() is False
