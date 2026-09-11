"""US2: build metrics preserve dispatch identity and unknown quantities.

The helpers here build temporary stores only.  They deliberately do not look
at ``.factory`` or ``.ergane`` in this checkout: those are operator runtime
roots, not test fixtures.
"""

from __future__ import annotations

import subprocess
import sys
import sqlite3
import importlib.util
from pathlib import Path
from typing import Any, Iterator

import pytest

from factory.usage.ledger import connect as connect_ledger, upsert_record
from factory.usage.models import Termination, UsageRecord
from factory.verify.models import VerificationForm, VerificationResult
from factory.verify.store import connect as connect_verification


REWORK = Path(".agents/skills/build-metrics/scripts/rework.py")
LOC = Path(".agents/skills/build-metrics/scripts/loc.py")
REPO_ROOT = Path(__file__).parents[1]


def _old_verification_store(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE verification_results (
            id INTEGER PRIMARY KEY,
            epic_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            form TEXT NOT NULL,
            verdict TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            dispatch TEXT NOT NULL
        )
        """
    )
    return conn


def _old_ledger_store(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE usage_records (
            id INTEGER PRIMARY KEY,
            epic_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            persona TEXT NOT NULL,
            spec_ref TEXT NOT NULL,
            key_alias TEXT NOT NULL UNIQUE,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            cache_read_tokens INTEGER,
            cache_write_tokens INTEGER,
            request_count INTEGER,
            spend_usd REAL,
            final_usage_confirmed INTEGER NOT NULL,
            termination TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            torn_down_at TEXT NOT NULL
        )
        """
    )
    return conn


def _stores(runtime_root: Path):
    verification = connect_verification(runtime_root / "verification.db")
    ledger = connect_ledger(runtime_root / "ledger.db")
    return verification, ledger


def _ledger_record(*, key_alias: str, **overrides: Any) -> UsageRecord:
    fields: dict[str, Any] = {
        "epic_id": "158-operator-skills",
        "node_id": "us1",
        "attempt": 1,
        "persona": "implementer",
        "spec_ref": "158/US1",
        "key_alias": key_alias,
        "prompt_tokens": 100,
        "completion_tokens": 10,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "request_count": 1,
        "spend_usd": 0.10,
        "final_usage_confirmed": True,
        "termination": Termination.COMPLETED,
        "issued_at": "2026-09-10T10:00:00Z",
        "torn_down_at": "2026-09-10T10:03:00Z",
    }
    fields.update(overrides)
    return UsageRecord(**fields)


def _insert_old_verification(conn: sqlite3.Connection, dispatch: str = "<unknown>") -> None:
    conn.execute(
        "INSERT INTO verification_results (epic_id, node_id, attempt, form, verdict, "
        "finished_at, dispatch) VALUES (?, ?, 1, 'PHASE', 'PASS', "
        "'2026-09-10T10:03:00Z', ?)",
        ("158-operator-skills", "us1", dispatch),
    )
    conn.commit()


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


@pytest.fixture
def loc_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "ergane_build_metrics_loc", REPO_ROOT / LOC
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fake_cloc(tmp_path: Path) -> Path:
    executable = tmp_path / "cloc"
    executable.write_text(
        "#!/bin/sh\n"
        'out=""\n'
        'for value do\n'
        '  case "$value" in --out=*) out="${value#--out=}" ;; esac\n'
        "done\n"
        'cat > "$out" <<\'CSV\'\n'
        "filename,language,blank,comment,code\n"
        "./example.py,Python,1,2,10\n"
        "CSV\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def test_declared_local_loc_tool_does_not_download(
    tmp_path: Path, loc_module: Any, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def deny_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access was attempted")

    monkeypatch.setattr("socket.socket", deny_network)
    tool = _fake_cloc(tmp_path)
    loc_module.main(str(tmp_path), tool=str(tool))

    output = capsys.readouterr().out
    assert "BY LANGUAGE" in output
    assert "Python" in output


def test_loc_scratch_outputs_are_run_unique(
    tmp_path: Path, loc_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs: list[Path] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        path = Path(command[-1].removeprefix("--out="))
        outputs.append(path)
        path.write_text(
            "filename,language,blank,comment,code\n./example.py,Python,1,2,10\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    tool = _fake_cloc(tmp_path)
    monkeypatch.setattr(loc_module.subprocess, "run", fake_run)
    loc_module.main(str(tmp_path), tool=str(tool))
    loc_module.main(str(tmp_path), tool=str(tool))

    assert outputs[0] != outputs[1]
    assert all(path.parent.is_relative_to(tmp_path) for path in outputs)


def test_loc_reports_unavailable_without_local_tool(
    tmp_path: Path, loc_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loc_module.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="LOC tool unavailable"):
        loc_module.main(str(tmp_path))


def test_loc_source_has_no_remote_executable_boundary() -> None:
    source = (REPO_ROOT / LOC).read_text(encoding="utf-8")
    assert "urllib" not in source
    assert "https://raw.githubusercontent.com" not in source
    assert "CLOC_URL" not in source
    assert "master" not in source


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


@pytest.mark.parametrize(
    "scenario",
    ["empty", "legacy-dimensions", "unknown-usage"],
)
def test_missing_and_unmeasured_quantities_are_not_zero(
    tmp_path: Path, scenario: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _without_runtime_env(monkeypatch)
    runtime = tmp_path / ".ergane"
    runtime.mkdir()
    if scenario == "legacy-dimensions":
        store = _old_verification_store(runtime / "verification.db")
        _insert_old_verification(store)
        ledger = _old_ledger_store(runtime / "ledger.db")
        ledger.execute(
            "INSERT INTO usage_records (epic_id, node_id, attempt, persona, spec_ref, "
            "key_alias, prompt_tokens, completion_tokens, final_usage_confirmed, "
            "termination, issued_at, torn_down_at) "
            "VALUES ('158-operator-skills', 'us1', 1, 'implementer', '158/US1', "
            "'legacy-row', 1000, 100, 1, 'completed', '2026-09-10T10:00:00Z', "
            "'2026-09-10T10:03:00Z')"
        )
        ledger.commit()
    elif scenario == "unknown-usage":
        store, ledger = _stores(runtime)
        fields = _verification_fields(dispatch="<unknown>")
        columns = ", ".join(fields)
        marks = ", ".join(f":{column}" for column in fields)
        store.execute(f"INSERT INTO verification_results ({columns}) VALUES ({marks})", fields)
        store.execute(
            "UPDATE verification_results SET persona = NULL, model_alias = NULL, route = NULL"
        )
        store.commit()
        upsert_record(
            ledger,
            _ledger_record(
                key_alias="subscription-complete",
                usage_source="subscription",
                usage_status="complete",
                cost_basis="unknown",
                cache_read_tokens=None,
                cache_write_tokens=None,
                request_count=None,
                spend_usd=None,
            ),
        )
        upsert_record(
            ledger,
            _ledger_record(
                key_alias="subscription-unknown",
                usage_source="subscription",
                usage_status="unknown",
                cost_basis="unknown",
                prompt_tokens=None,
                completion_tokens=None,
                cache_read_tokens=None,
                cache_write_tokens=None,
                request_count=None,
                spend_usd=None,
            ),
        )
        upsert_record(
            ledger,
            _ledger_record(
                key_alias="gateway-partial",
                usage_source="gateway",
                usage_status="partial",
                cost_basis="proxy_estimate",
                prompt_tokens=50,
                completion_tokens=None,
                cache_read_tokens=None,
                cache_write_tokens=None,
                request_count=1,
                spend_usd=0.25,
            ),
        )
        upsert_record(
            ledger,
            _ledger_record(
                key_alias="legacy-row",
                prompt_tokens=500,
                completion_tokens=None,
                request_count=None,
                usage_source="legacy",
                usage_status="legacy",
                cost_basis="unknown",
                spend_usd=0.30,
            ),
        )
    else:
        store, ledger = _stores(runtime)
        store.close()
        ledger.close()

    output = _run_rework(tmp_path)
    if scenario != "empty":
        store.close()
        ledger.close()

    if scenario == "empty":
        assert "verification rows 0" in output
        assert "usage rows 0" in output
    if scenario == "legacy-dimensions":
        assert "runner unknown" in output
        assert "route=unknown" in output
        assert "model=unknown" in output
        assert "prompt tokens measured 1000" in output
        assert "completion tokens measured 100" in output
    if scenario == "unknown-usage":
        assert "prompt tokens measured 650" in output
        assert "completion tokens measured 10" in output
        assert "requests measured 1" in output
        normalized = " ".join(output.split())
        assert "usage sources gateway legacy subscription" in normalized
        assert "usage statuses complete legacy partial unknown" in normalized
        assert "cost bases proxy_estimate unknown" in normalized
from pytest import MonkeyPatch
