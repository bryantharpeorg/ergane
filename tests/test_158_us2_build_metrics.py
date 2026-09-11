"""US2: build metrics preserve dispatch identity and unknown quantities.

The helpers here build temporary stores only.  They deliberately do not look
at ``.factory`` or ``.ergane`` in this checkout: those are operator runtime
roots, not test fixtures.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterator

from factory.usage.ledger import connect as connect_ledger, upsert_record
from factory.usage.models import Termination, UsageRecord
from factory.verify.models import VerificationForm, VerificationResult
from factory.verify.store import connect as connect_verification


REWORK = Path(".agents/skills/build-metrics/scripts/rework.py")


def _stores(runtime_root: Path):
    verification = connect_verification(runtime_root / "verification.db")
    ledger = connect_ledger(runtime_root / "ledger.db")
    return verification, ledger


def _ledger_record(*, key_alias: str) -> UsageRecord:
    return UsageRecord(
        epic_id="158-operator-skills",
        node_id="us1",
        attempt=1,
        persona="implementer",
        spec_ref="158/US1",
        key_alias=key_alias,
        prompt_tokens=100,
        completion_tokens=10,
        cache_read_tokens=0,
        cache_write_tokens=0,
        request_count=1,
        spend_usd=0.10,
        final_usage_confirmed=True,
        termination=Termination.COMPLETED,
        issued_at="2026-09-10T10:00:00Z",
        torn_down_at="2026-09-10T10:03:00Z",
    )


def _without_runtime_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("ERGANE_ROOT", raising=False)
    monkeypatch.delenv("FACTORY_ROOT", raising=False)


def _verification_fields(
    *,
    dispatch: str,
    attempt: int = 1,
    verdict: str = "PASS",
    model_alias: str = "codex-primary",
    route: str = "subscription",
) -> dict[str, str | int]:
    return {
        "epic_id": "158-operator-skills",
        "node_id": "us1",
        "attempt": attempt,
        "form": "PHASE",
        "gate_results": "[]",
        "output_check": "{}",
        "judge_verdict": "null",
        "judge_unavailable": 0,
        "verdict": verdict.upper(),
        "criteria_drift": 0,
        "criteria_sha256": "a" * 64,
        "spec_ref": "158/US1",
        "started_at": "2026-09-10T10:00:00Z",
        "finished_at": "2026-09-10T10:03:00Z",
        "dispatch": dispatch,
        "persona": "implementer",
        "model_alias": model_alias,
        "route": route,
    }


def _run_rework(repo: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(REWORK), str(repo)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[1],
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_two_dispatches_sharing_old_key_fields_stay_separate(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _without_runtime_env(monkeypatch)
    runtime = tmp_path / ".ergane"
    runtime.mkdir()
    store, ledger = _stores(runtime)
    fields = _verification_fields(dispatch="first")
    columns = ", ".join(fields)
    marks = ", ".join(f":{column}" for column in fields)
    store.execute(f"INSERT INTO verification_results ({columns}) VALUES ({marks})", fields)
    fields = _verification_fields(
        dispatch="second",
        model_alias="glm-5.3",
        route="ollama-cloud",
        verdict="FAIL",
    )
    columns = ", ".join(fields)
    marks = ", ".join(f":{column}" for column in fields)
    store.execute(f"INSERT INTO verification_results ({columns}) VALUES ({marks})", fields)
    store.commit()
    upsert_record(ledger, _ledger_record(key_alias="first-dispatch"))
    upsert_record(ledger, _ledger_record(key_alias="second-dispatch"))
    ledger.close()
    output = _run_rework(tmp_path)

    assert output.count("dispatch first") == 1
    assert output.count("dispatch second") == 1
    assert "codex-primary" in output and "subscription" in output
    assert "glm-5.3" in output and "ollama-cloud" in output
from pytest import MonkeyPatch
