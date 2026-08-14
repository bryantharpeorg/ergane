"""US3: the operator-facing environment variables are `ERGANE_*`.

The factory's state paths and the evidence-store guard are controlled by
environment variables.  This story adds `ERGANE_*` names, keeps the old
`FACTORY_*` names working, and reports a conflict once when both are set.

Evidence rule for every scenario: as US1.
"""

from __future__ import annotations

import os
import re
import subprocess
import warnings
from pathlib import Path
from typing import Any

import pytest

from factory.activities import notify_activities
from factory.activities.agent_activities import factory_root
from factory.activities.usage_activities import _ledger_path
from factory.activities.verify_activities import _store_path as verify_store_path
from factory.verify.store import EVIDENCE_STORE_ALLOW_REAL_ENV


def _repo_root() -> Path:
    """Repo root, reached from any worktree copy of this test file."""
    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return Path(toplevel)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parents[2]


REPO_ROOT = _repo_root()


def test_ergane_root_honored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ERGANE_ROOT", str(tmp_path / "ergane-root"))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    assert factory_root() == Path(tmp_path / "ergane-root")


def test_ergane_verification_db_path_honored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "ERGANE_VERIFICATION_DB_PATH", str(tmp_path / "ergane-verify.db")
    )
    monkeypatch.delenv("FACTORY_VERIFICATION_DB_PATH", raising=False)
    assert verify_store_path() == Path(tmp_path / "ergane-verify.db")


def test_ergane_ledger_path_honored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ERGANE_LEDGER_PATH", str(tmp_path / "ergane-ledger.db"))
    monkeypatch.delenv("FACTORY_LEDGER_PATH", raising=False)
    assert _ledger_path() == Path(tmp_path / "ergane-ledger.db")


def test_legacy_factory_root_honored_with_deprecation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """US3-S2: only the old name is set -> honored and one deprecation reported."""
    monkeypatch.setenv("FACTORY_ROOT", str(tmp_path / "legacy-root"))
    monkeypatch.delenv("ERGANE_ROOT", raising=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = factory_root()
    assert result == Path(tmp_path / "legacy-root")
    assert any("FACTORY_ROOT" in str(w.message) for w in caught)
    assert len([w for w in caught if "FACTORY_ROOT" in str(w.message)]) == 1


def test_legacy_factory_verification_db_path_honored_with_deprecation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "FACTORY_VERIFICATION_DB_PATH", str(tmp_path / "legacy-verify.db")
    )
    monkeypatch.delenv("ERGANE_VERIFICATION_DB_PATH", raising=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = verify_store_path()
    assert result == Path(tmp_path / "legacy-verify.db")
    assert any("FACTORY_VERIFICATION_DB_PATH" in str(w.message) for w in caught)
    assert len([w for w in caught if "FACTORY_VERIFICATION_DB_PATH" in str(w.message)]) == 1


def test_legacy_factory_ledger_path_honored_with_deprecation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FACTORY_LEDGER_PATH", str(tmp_path / "legacy-ledger.db"))
    monkeypatch.delenv("ERGANE_LEDGER_PATH", raising=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _ledger_path()
    assert result == Path(tmp_path / "legacy-ledger.db")
    assert any("FACTORY_LEDGER_PATH" in str(w.message) for w in caught)
    assert len([w for w in caught if "FACTORY_LEDGER_PATH" in str(w.message)]) == 1


def test_conflict_new_name_wins_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """US3-S3: both names set to different values -> ERGANE_* wins, both named."""
    new_path = tmp_path / "new-root"
    old_path = tmp_path / "old-root"
    monkeypatch.setenv("ERGANE_ROOT", str(new_path))
    monkeypatch.setenv("FACTORY_ROOT", str(old_path))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = factory_root()
    assert result == Path(new_path)
    messages = " ".join(str(w.message) for w in caught)
    assert "ERGANE_ROOT" in messages
    assert "FACTORY_ROOT" in messages


def test_conflict_new_name_wins_verification_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    new_path = tmp_path / "new-verify.db"
    old_path = tmp_path / "old-verify.db"
    monkeypatch.setenv("ERGANE_VERIFICATION_DB_PATH", str(new_path))
    monkeypatch.setenv("FACTORY_VERIFICATION_DB_PATH", str(old_path))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = verify_store_path()
    assert result == Path(new_path)
    messages = " ".join(str(w.message) for w in caught)
    assert "ERGANE_VERIFICATION_DB_PATH" in messages
    assert "FACTORY_VERIFICATION_DB_PATH" in messages


def test_conflict_new_name_wins_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    new_path = tmp_path / "new-ledger.db"
    old_path = tmp_path / "old-ledger.db"
    monkeypatch.setenv("ERGANE_LEDGER_PATH", str(new_path))
    monkeypatch.setenv("FACTORY_LEDGER_PATH", str(old_path))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _ledger_path()
    assert result == Path(new_path)
    messages = " ".join(str(w.message) for w in caught)
    assert "ERGANE_LEDGER_PATH" in messages
    assert "FACTORY_LEDGER_PATH" in messages


def test_deprecation_emitted_once_per_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """US3-S2 / trap 7: a resolver called repeatedly must warn only once per process."""
    monkeypatch.setenv("FACTORY_ROOT", str(tmp_path / "legacy-root"))
    monkeypatch.delenv("ERGANE_ROOT", raising=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for _ in range(5):
            factory_root()
    deprecation_warnings = [w for w in caught if "FACTORY_ROOT" in str(w.message)]
    assert len(deprecation_warnings) == 1, (
        f"expected one deprecation, got {len(deprecation_warnings)}"
    )


def test_env_script_exports_ergane_names() -> None:
    """US3-S4: scripts/ergane-env.sh emits the new variable names."""
    script = REPO_ROOT / "scripts" / "ergane-env.sh"
    assert script.exists(), "scripts/ergane-env.sh must exist"
    text = script.read_text(encoding="utf-8")
    assert "export ERGANE_ROOT=" in text, "script must export ERGANE_ROOT"
    assert "export FACTORY_ROOT=" not in text, "script must stop exporting FACTORY_ROOT"


def test_conftest_fixture_sets_both_old_and_new_names(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """US3-S4 / trap 5: the session fixture sets both ERGANE_* and FACTORY_*."""
    conftest = REPO_ROOT / "tests" / "conftest.py"
    text = conftest.read_text(encoding="utf-8")
    for new, old in [
        ("ERGANE_ROOT", "FACTORY_ROOT"),
        ("ERGANE_VERIFICATION_DB_PATH", "FACTORY_VERIFICATION_DB_PATH"),
        ("ERGANE_LEDGER_PATH", "FACTORY_LEDGER_PATH"),
    ]:
        assert re.search(rf"patch\.setenv\s*\(\s*['\"]{re.escape(new)}['\"]", text), (
            f"conftest must set {new}"
        )
        assert re.search(rf"patch\.setenv\s*\(\s*['\"]{re.escape(old)}['\"]", text), (
            f"conftest must keep setting {old} for partially migrated trees"
        )
