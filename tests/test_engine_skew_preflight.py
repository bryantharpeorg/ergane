"""105-US3: the skew refusal reaches both dispatch sites (T020, T021).

`ergane build start` and the older `factory.workgraph.cli.start_command` both
run `_run_preflight`, and both must refuse before any epic dispatches when the
running engine's version differs from the CLI's.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

import factory.cli.nouns as nouns
import factory.cli.nouns.build as build_module
import factory.workgraph.cli as workgraph_cli
from factory.cli.main import main as ergane_main
from factory.mergequeue.models import Finding
from factory.supervision.engine_identity import (
    EngineIdentity,
    identity_path,
    image_reference,
    write_identity,
)
from factory.workgraph.models import WorkNode


def _invoke(*argv: str) -> tuple[int, str, str]:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = StringIO(), StringIO()
    code = 0
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = ergane_main(list(argv))
        except SystemExit as exit_request:
            code = exit_request.code
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return (0 if code is None else int(code), buf_out.getvalue(), buf_err.getvalue())


def _minimal_graph(tmp_path: Path) -> Path:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "epic_id": "105-skew-test",
                "feature": "105-the-cli-and-the-image-share-one-version",
                "specs_root": str(tmp_path / "specs"),
                "target_repo": str(tmp_path / "target"),
                "nodes": [
                    {
                        "id": "us3",
                        "story_key": "US3",
                        "persona": "implementer",
                        "spec_ref": "105-the-cli-and-the-image-share-one-version/spec.md",
                        "requirement_keys": ["US3"],
                        "depends_on": [],
                        "depends_on_merged": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return graph_path


def _write_identity(state_home: Path, version: str) -> Path:
    return write_identity(
        state_home,
        EngineIdentity(
            version=version,
            started_at="2026-08-25T12:00:00+00:00",
            image_reference=image_reference(version),
            image_digest=None,
        ),
    )


@pytest.fixture
def isolated_state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point state resolution at a temporary directory."""
    state = tmp_path / "state"
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    return state


class _FakeLiteLLMClient:
    """Proxy that answers every preflight alias read without being asked."""

    async def list_model_ids(self) -> set[str]:
        return {"ollama-cloud/kimi-k2.7-code"}

    async def list_key_aliases(self) -> set[str]:
        return set()

    async def aclose(self) -> None:
        pass


class _FakePreflight:
    """Records whether the engine skew check was included in preflight findings."""

    def __init__(self, *, include_skew: bool = True) -> None:
        self.include_skew = include_skew

    async def __call__(self, graph: Any) -> list[Any]:
        from factory.workgraph.preflight import PreflightFinding

        findings: list[Any] = []
        if self.include_skew:
            identity = _write_identity(isolated_state_home, "0.3.0")
            sentence = (
                f"engine is running ergane 0.3.0; this CLI is 0.4.0 — they must match. "
                f"Upgrade with `ergane engine upgrade`, or pull the pinned image directly: "
                f"docker pull {image_reference('0.4.0')}. "
                f"If that engine is gone, this record is stale — remove {identity}."
            )
            findings.append(
                PreflightFinding(check="engine", passed=False, detail=sentence, transport=False)
            )
        return findings


# --- T020: build.py site -----------------------------------------------------


def test_build_noun_run_preflight_refuses_on_engine_skew(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_home: Path,
) -> None:
    """T020 / US3-S1 / FR-013: `build.py` `_run_preflight` yields an engine finding."""
    graph_path = _minimal_graph(tmp_path)
    identity = _write_identity(isolated_state_home, "0.3.0")

    from factory.supervision import engine_identity as identity_module

    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.4.0")

    async def fake_aliases(graph: Any, registry: Any, client: Any) -> list[Any]:
        return []

    monkeypatch.setattr(build_module, "check_aliases", fake_aliases)
    monkeypatch.setattr(build_module, "landing_readiness_preflight", lambda graph, root: [])
    monkeypatch.setattr(build_module, "prompt_assembly_preflight", lambda graph, feature_dir: [])

    # Patch the preflight client so proxy checks do not run.
    monkeypatch.setattr(build_module, "_open_preflight_client", _FakeLiteLLMClient)

    from factory.workgraph.cli import load_workgraph

    graph = load_workgraph(str(graph_path))
    findings = asyncio.run(build_module._run_preflight(graph))

    engine_findings = [f for f in findings if getattr(f, "check", None) == "engine"]
    assert len(engine_findings) == 1
    finding = engine_findings[0]
    assert finding.passed is False
    assert finding.transport is False
    assert "engine is running ergane 0.3.0" in finding.detail
    assert "this CLI is 0.4.0" in finding.detail
    assert str(identity) in finding.detail


def test_build_start_prints_engine_skew_and_exits_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_home: Path,
) -> None:
    """T020: `_start_epic` prints the engine finding and returns EXIT_USER."""
    graph_path = _minimal_graph(tmp_path)
    identity = _write_identity(isolated_state_home, "0.3.0")

    from factory.supervision import engine_identity as identity_module

    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.4.0")

    async def fake_run_preflight(graph: Any) -> list[Any]:
        from factory.workgraph.preflight import PreflightFinding

        return [
            PreflightFinding(
                check="engine",
                passed=False,
                detail=(
                    f"engine is running ergane 0.3.0; this CLI is 0.4.0 — they must match. "
                    f"Upgrade with `ergane engine upgrade`, or pull the pinned image directly: "
                    f"docker pull {image_reference('0.4.0')}. "
                    f"If that engine is gone, this record is stale — remove {identity}."
                ),
                transport=False,
            )
        ]

    monkeypatch.setattr(build_module, "_run_preflight", fake_run_preflight)

    class _FakeClient:
        pass

    async def fake_connect() -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr(build_module, "_connect", fake_connect)

    from factory.workgraph.cli import load_workgraph

    graph = load_workgraph(str(graph_path))
    code = asyncio.run(build_module._start_epic(graph, "http://proxy.test/v1", 1))

    assert code == 1


# --- T021: workgraph/cli.py site --------------------------------------------


def test_workgraph_cli_run_preflight_refuses_on_engine_skew(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_home: Path,
) -> None:
    """T021 / US3-S1 / FR-013: the second `_run_preflight` site refuses identically."""
    graph_path = _minimal_graph(tmp_path)
    identity = _write_identity(isolated_state_home, "0.3.0")

    from factory.supervision import engine_identity as identity_module

    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.4.0")

    monkeypatch.setattr(workgraph_cli, "_open_preflight_client", _FakeLiteLLMClient)

    async def fake_aliases(graph: Any, registry: Any, client: Any) -> list[Any]:
        return []

    monkeypatch.setattr(workgraph_cli, "check_aliases", fake_aliases)

    from factory.workgraph.cli import load_workgraph

    graph = load_workgraph(str(graph_path))
    findings = asyncio.run(workgraph_cli._run_preflight(graph))

    engine_findings = [f for f in findings if getattr(f, "check", None) == "engine"]
    assert len(engine_findings) == 1
    finding = engine_findings[0]
    assert finding.passed is False
    assert finding.transport is False
    assert "engine is running ergane 0.3.0" in finding.detail
    assert "this CLI is 0.4.0" in finding.detail
    assert str(identity) in finding.detail
