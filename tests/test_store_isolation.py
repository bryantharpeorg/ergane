"""US1: the test suite owns its stores, and no shell export can reach them.

This file is the contract between the operator's environment and the suite:
a session-scoped fixture in `conftest.py` redirects every state-locating env
variable into pytest's session tmp base before any test body runs, and the
proof here asserts that redirection is unconditional and comprehensive.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities import notify_activities
from factory.activities.agent_activities import FACTORY_ROOT_ENV, factory_root
from factory.activities.notify_activities import (
    TELEGRAM_BOT_TOKEN_ENV,
    TELEGRAM_CHAT_ID_ENV,
    RecordRoadmapFailureInput,
    SendEscalationInput,
    record_roadmap_failure,
    send_escalation,
)
from factory.activities.usage_activities import LEDGER_PATH_ENV, _ledger_path
from factory.activities.verify_activities import (
    VERIFICATION_DB_PATH_ENV,
    _store_path as verify_store_path,
)
from factory.verify import store
from factory.verify.models import EscalationChoice


#: Modern acknowledgment variable that deliberately opens the real-store door for
#: the live smoke.  Named in `factory/verify/store.py` and mirrored here so
#: tests that need to set it do not hardcode a string.
EVIDENCE_STORE_ALLOW_REAL_ENV = "ERGANE_EVIDENCE_STORE_ALLOW_REAL"

#: Match the shape `test_roadmap_failure_notifications.py` uses for a roadmap id.
ROADMAP_ID = "roadmap-specs"

#: Same text the leaking harness historically placed in the live store.
FAILURE_TEXT = "max_concurrent_nodes must be a positive integer, got -1"

#: Distinctive fake credentials that must never reach a real network.
FAKE_BOT_TOKEN = "1234567890:poisoned-token-do-not-page"
FAKE_CHAT_ID = "-100poisonedchat"


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


def _is_under(path: Path, base: Path) -> bool:
    """Resolved containment, tolerating pytest's numbered basetemp naming."""
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


# In-suite invariant: the session fixture has redirected the state env variables
# into pytest's session tmp base, removed the Telegram credentials from env, and
# production resolvers all resolve under that base.


def test_invariant_session_fixture_redirects_state_env(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    base = tmp_path_factory.getbasetemp()

    factory_root_path = Path(os.environ[FACTORY_ROOT_ENV])
    assert factory_root_path.is_absolute(), "FACTORY_ROOT must be absolute (FR-002)"
    assert _is_under(factory_root_path, base), (
        f"FACTORY_ROOT {factory_root_path} is not under {base}"
    )

    db_path = Path(os.environ[VERIFICATION_DB_PATH_ENV])
    assert _is_under(db_path, base), (
        f"FACTORY_VERIFICATION_DB_PATH {db_path} is not under {base}"
    )

    ledger_path = Path(os.environ[LEDGER_PATH_ENV])
    assert _is_under(ledger_path, base), (
        f"FACTORY_LEDGER_PATH {ledger_path} is not under {base}"
    )

    assert TELEGRAM_BOT_TOKEN_ENV not in os.environ
    assert TELEGRAM_CHAT_ID_ENV not in os.environ

    assert _is_under(verify_store_path(), base)
    assert _is_under(notify_activities._store_path(), base)
    assert _is_under(factory_root(), base)
    assert _is_under(_ledger_path(), base)



# Subprocess proof: a child pytest run that inherited poisoned shell exports for
# the three path variables and the two Telegram credentials still resolves
# everything under pytest's session tmp base and has no credential in env.


def test_poisoned_shell_isolation(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    # Poison paths under a root that cannot exist; safe even if the proof fails.
    poison_root = Path("/nonexistent-030-proof/factory-root")
    poison_db = Path("/nonexistent-030-proof/verification.db")
    poison_ledger = Path("/nonexistent-030-proof/ledger.db")

    env = os.environ.copy()
    env[FACTORY_ROOT_ENV] = str(poison_root)
    env[VERIFICATION_DB_PATH_ENV] = str(poison_db)
    env[LEDGER_PATH_ENV] = str(poison_ledger)
    env[TELEGRAM_BOT_TOKEN_ENV] = FAKE_BOT_TOKEN
    env[TELEGRAM_CHAT_ID_ENV] = FAKE_CHAT_ID

    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_store_isolation.py", "-k", "invariant", "-q"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    assert not poison_root.exists(), "poison FACTORY_ROOT was created"
    assert not poison_db.exists(), "poison FACTORY_VERIFICATION_DB_PATH was created"
    assert not poison_ledger.exists(), "poison FACTORY_LEDGER_PATH was created"
    assert not poison_db.parent.exists(), (
        "poison directory should not have been created"
    )


# Leaking-writer containment: exercise the real activities the roadmap harnesses
# register, with no env manipulation of our own, and assert every write lands in
# the session's tmp store and the cwd-relative default was not created.


async def test_leaking_writers_are_contained(
    env: ActivityEnvironment,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    base = tmp_path_factory.getbasetemp()

    sent = await env.run(
        send_escalation,
        SendEscalationInput(
            workflow_id="wf-030",
            epic_id=ROADMAP_ID,
            node_id="node-030",
            history_summary="isolation proof",
            choices=[EscalationChoice.KILL],
            timeout_s=3600,
        ),
    )
    assert sent.delivered is False, "no credential should be visible to the activity"

    count_result = await env.run(
        record_roadmap_failure,
        RecordRoadmapFailureInput(
            db_path=os.environ[VERIFICATION_DB_PATH_ENV],
            roadmap_id=ROADMAP_ID,
            failure_text=FAILURE_TEXT,
        ),
    )
    assert count_result.count == 1

    db_path = Path(os.environ[VERIFICATION_DB_PATH_ENV])
    assert _is_under(db_path, base)
    assert db_path.exists(), "session store was not created"

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT consecutive_count, last_failure_text FROM roadmap_failures WHERE roadmap_id = ?",
            (ROADMAP_ID,),
        ).fetchone()
        assert row is not None, "roadmap_failures row missing from session store"
        assert row[0] == 1, row
        assert row[1] == FAILURE_TEXT, row

        escalation = conn.execute(
            "SELECT delivered FROM escalations WHERE epic_id = ?",
            (ROADMAP_ID,),
        ).fetchone()
        assert escalation is not None, "escalation row missing from session store"
        assert escalation[0] == 0, escalation
    finally:
        conn.close()

    default_db = Path(".factory/verification.db")
    assert not default_db.exists(), (
        f"cwd-relative default store {default_db} was created"
    )


# US2: the store refuses to be constructed outside tmp during a test, unless the
# operator has explicitly acknowledged the risk.


#: The finding key the guard names in its error message.
ISOLATION_FINDING_KEY = "hardening/test-suite-writes-to-the-live-evidence-store"


def test_us2_refuses_fabricated_non_tmp_path():
    """Guard refuses a fabricated absolute path outside tmp; no disk trace left.

    The path is under a nonexistent root so that even a red run (guard not yet
    written) fails with an ordinary OSError rather than creating a real store.
    """
    poison = Path("/nonexistent-030-proof-us2/live-evidence.db")

    with pytest.raises(RuntimeError) as exc_info:
        store.connect(poison)

    message = str(exc_info.value)
    assert ISOLATION_FINDING_KEY in message, message
    assert str(poison) in message, message

    assert not poison.exists(), "refused path was created"
    assert not poison.parent.exists(), "refused path's parent was created"


def test_us2_acknowledgment_allows_real_store(tmp_path: Path, monkeypatch):
    """Guard against over-reach: explicit acknowledgment keeps the smoke door open.

    A writable path outside the tmp tree but inside this checkout's repo root is
    used, and removed in a finally block, so a red run never leaves a real store
    behind.
    """
    repo_root = Path(__file__).resolve().parent.parent
    scratch = repo_root / ".scratch-us2-ack"
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / "ack.db"

    monkeypatch.setenv(EVIDENCE_STORE_ALLOW_REAL_ENV, "1")

    try:
        conn = store.connect(path)
        try:
            # The store opened; schema bootstrap ran.
            version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
            assert version == store.SCHEMA_VERSION
        finally:
            conn.close()

        assert path.exists(), "acknowledged store was not created"
    finally:
        # No real store may outlive this test.
        if path.exists():
            path.unlink()
        if scratch.exists():
            scratch.rmdir()


def test_us2_tmp_path_connects_normally(tmp_path: Path):
    """Guard against over-reach: paths under tmp connect exactly as today."""
    path = tmp_path / "isolated.db"

    conn = store.connect(path)
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == store.SCHEMA_VERSION
    finally:
        conn.close()

    assert path.exists(), "tmp store was not created"


def test_us2_sentinel_absent_is_byte_identical(tmp_path: Path, monkeypatch):
    """Guard against over-reach: with PYTEST_CURRENT_TEST absent behavior is unchanged.

    This is the production proof FR-010 demands: the worker, the notify service
    and the CLI never meet the guard.
    """
    path = tmp_path / "production-shape.db"
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    conn = store.connect(path)
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == store.SCHEMA_VERSION
    finally:
        conn.close()

    assert path.exists(), "production-shape store was not created"
