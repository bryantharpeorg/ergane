from __future__ import annotations

import dataclasses
import importlib.util
import json
import re
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from factory.env import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
)
from factory.verify.store import connect, upsert_result
from tests.test_117_dispatch_scoped_rows import EPIC, make_result
from tests.test_092_abridged_is_recorded import invoke


ROOT = Path(__file__).resolve().parents[1]
FLOOR_SKILL = ROOT / ".agents/skills/floor-status"
ESCALATION_SKILL = ROOT / ".agents/skills/escalation-triage"
FORBIDDEN_ACTION_RE = re.compile(
    r"\b(?:git\s+(?:fetch|merge|push|checkout|reset)|gh\s+(?:pr\s+merge|run\s+rerun)|"
    r"ergane\s+(?:build\s+ship|build\s+(?:pause|resume|kill|answer|resolve)|"
    r"findings\s+(?:apply|report|resolve|promote|triage\s+--apply)|"
    r"spec\s+ship)|systemctl\s+(?:start|restart|stop|kill|reload))\b"
)
FORBIDDEN_IMPORT_RE = re.compile(
    r"^(?:import|from)\s+(?:subprocess|os|shutil|socket|httpx|requests)\b",
    re.MULTILINE,
)


def load_skill_script(name: str) -> Any:
    path = FLOOR_SKILL / name if name.startswith("floor") else ESCALATION_SKILL / name
    spec = importlib.util.spec_from_file_location(
        f"_test_{path.stem}", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def fixture_dir(tmp_path: Path) -> Path:
    return tmp_path


class DeniedMutations:
    """Any mutation through the configured seams fails the test immediately."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        def denied(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(name)
            raise AssertionError(f"mutation seam called: {name}")

        return denied


def status_fixture() -> dict[str, Any]:
    return {
        "epic_id": "158-operator-skills-report-and-act-by-declared-intent",
        "epic_state": "RUNNING",
        "execution_status": "RUNNING",
        "worker_revision": "60943a0",
        "nodes": {
            "us1": {
                "state": "RUNNING",
                "attempt": 1,
                "branch": "factory/158/us1",
            },
            "us2": {
                "state": "VERIFYING",
                "attempt": 2,
                "branch": "factory/158/us2",
            },
        },
    }


def attempt_rows() -> list[dict[str, Any]]:
    return [
        {
            "node_id": "us1",
            "dispatch": "workflow-run-158a",
            "attempt": 1,
            "form": "NODE",
            "verdict": "FAIL",
            "persona": "debugger",
            "model_alias": "claude-opus-5",
            "route": "gateway",
            "evidence_source": "verification-store",
            "started_at": "2026-09-09T09:00:00Z",
            "finished_at": "2026-09-09T09:20:00Z",
        },
        {
            "node_id": "us1",
            "dispatch": "workflow-run-158b",
            "attempt": 1,
            "form": "NODE",
            "verdict": "PASS",
            "persona": "debugger",
            "model_alias": "claude-opus-5",
            "route": "subscription",
            "evidence_source": "verification-store",
            "started_at": "2026-09-09T10:00:00Z",
            "finished_at": "2026-09-09T10:30:00Z",
        },
        {
            "node_id": "us2",
            "dispatch": "workflow-run-158c",
            "attempt": 1,
            "form": "NODE",
            "verdict": "PASS",
            "persona": "promotion-debugger",
            "model_alias": "claude-sonnet-5",
            "route": "gateway",
            "evidence_source": "verification-store",
            "started_at": "2026-09-09T11:00:00Z",
            "finished_at": "2026-09-09T11:10:00Z",
        },
        {
            "node_id": "us2",
            "dispatch": "<unknown>",
            "attempt": 2,
            "form": "NODE",
            "verdict": "FAIL",
            "persona": "<unknown>",
            "model_alias": "<unknown>",
            "route": "<unknown>",
            "evidence_source": "verification-store",
            "started_at": "2026-09-09T11:00:00Z",
            "finished_at": "2026-09-09T11:10:00Z",
        },
    ]


def unavailable_services() -> dict[str, Any]:
    return {
        "temporal": {"state": "unavailable", "reason": "socket unavailable"},
        "landing_head": {"state": "unavailable", "reason": "target repo unavailable"},
        "process": {"state": "unavailable", "reason": "not running"},
    }


def status_fixture_document() -> dict[str, Any]:
    return status_fixture()


def attempt_fixture_document() -> dict[str, Any]:
    return {"attempts": attempt_rows()}


def test_floor_status_renders_recorded_history_without_registry(
    fixture_dir: Path,
) -> None:
    """Fixture routing and dispatches survive, even with the registry moved."""
    renderer = load_skill_script("floor_render.py")
    rendered = renderer.render_floor(
        status=status_fixture_document(),
        attempts=attempt_fixture_document()["attempts"],
        services=unavailable_services(),
        registry={"debugger": "today-changed-model", "routes": {}},
    )

    assert "runner debugger" in rendered
    assert "model claude-opus-5" in rendered
    assert "route gateway" in rendered
    assert "route subscription" in rendered
    assert "runner promotion-debugger" in rendered
    assert "model claude-sonnet-5" in rendered
    assert "route subscription" in rendered
    assert "dispatch 1 of 2: workflow-run-158a" in rendered
    assert "dispatch 2 of 2: workflow-run-158b" in rendered
    assert "dispatch 1 of 2" in rendered
    assert "evidence verification-store" in rendered
    assert "today-changed-model" not in rendered


def test_floor_status_reports_unavailable_without_reading_live_services(
    fixture_dir: Path,
) -> None:
    """A recorded unavailable fact is rendered, never re-probed into a state."""
    renderer = load_skill_script("floor_render.py")
    mutations = DeniedMutations()
    rendered = renderer.render_floor(
        status=status_fixture_document(),
        attempts=attempt_fixture_document()["attempts"],
        services=unavailable_services(),
        registry={},
        mutations=mutations,
    )

    assert "unavailable: temporal socket unavailable" in rendered
    assert "unavailable: landing head target repo unavailable" in rendered
    assert "unavailable: process not running" in rendered
    assert mutations.calls == []


def test_status_only_skills_and_helpers_have_no_forbidden_commands() -> None:
    """A static sweep covers the instruction text and deterministic helpers."""
    checked = [
        FLOOR_SKILL / "SKILL.md",
        FLOOR_SKILL / "floor_render.py",
        ESCALATION_SKILL / "SKILL.md",
        ESCALATION_SKILL / "escalation_render.py",
    ]
    for path in checked:
        assert path.exists(), f"missing status-only surface: {path}"
        text = path.read_text(encoding="utf-8")
        assert not FORBIDDEN_ACTION_RE.search(text), (
            f"{path.name} names an action seam: "
            f"{FORBIDDEN_ACTION_RE.search(text).group(0)}"
        )
        if path.suffix == ".py":
            assert not FORBIDDEN_IMPORT_RE.search(text), (
                f"{path.name} reaches a network or process seam: "
                f"{FORBIDDEN_IMPORT_RE.search(text).group(0)}"
            )


def test_escalation_brief_uses_the_choices_actually_offered() -> None:
    """A recommendation can only name a button the escalation offered."""
    renderer = load_skill_script("escalation_render.py")
    rendered = renderer.render_brief(
        {
            "escalation_id": "esc158",
            "epic_id": "158-epic",
            "node_id": "us1",
            "question": "retry available?",
            "expires_at": "2026-09-09T18:00:00Z",
            "choices": ["RETRY", "KILL_EPIC"],
            "recovery_evidence": {
                "classification": "deterministic",
                "tested_sha": "60943a0",
                "branch_moved": False,
            },
        }
    )

    assert "observed" in rendered
    assert "proposed answer" in rendered
    assert "offered choices: RETRY, KILL_EPIC" in rendered
    assert "proposed answer: RETRY" in rendered
    assert "no answer was sent" in rendered


def test_escalation_brief_does_not_assume_a_fixed_button_set() -> None:
    """Missing retry is visible rather than silently added to the choice set."""
    renderer = load_skill_script("escalation_render.py")
    rendered = renderer.render_brief(
        {
            "escalation_id": "esc158",
            "epic_id": "158-epic",
            "node_id": "us1",
            "question": "ending only",
            "expires_at": "2026-09-09T18:00:00Z",
            "choices": ["PAUSE_EPIC", "KILL_EPIC"],
            "recovery_evidence": {
                "classification": "deterministic",
                "tested_sha": "60943a0",
                "branch_moved": False,
            },
        }
    )

    assert "offered choices: PAUSE_EPIC, KILL_EPIC" in rendered
    assert "proposed answer: PAUSE_EPIC" in rendered
    assert "RETRY" not in rendered
    assert "no answer was sent" in rendered


def test_escalation_brief_refuses_a_proposal_outside_the_offer() -> None:
    """An explicit proposal must join the offered set or the read refuses."""
    renderer = load_skill_script("escalation_render.py")
    with pytest.raises(ValueError, match="not offered"):
        renderer.render_brief(
            {
                "escalation_id": "esc158",
                "epic_id": "158-epic",
                "node_id": "us1",
                "question": "wrong offer",
                "expires_at": "2026-09-09T18:00:00Z",
                "choices": ["KILL_EPIC"],
                "proposed_choice": "RETRY",
                "recovery_evidence": {"classification": "deterministic"},
            }
        )


def test_read_only_helpers_run_against_denied_mutation_fakes() -> None:
    """The CLI-facing helpers accept the read fakes and never call actions."""
    floor = load_skill_script("floor_render.py")
    escalation = load_skill_script("escalation_render.py")
    mutations = DeniedMutations()

    floor_report = floor.render_floor(
        status={"epic_id": "158", "epic_state": "RUNNING", "execution_status": "RUNNING", "nodes": {}},
        attempts=[],
        services={"temporal": {"state": "unavailable", "reason": "none"}},
        registry={},
        mutations=mutations,
    )
    escalation_brief = escalation.render_brief(
        {
            "escalation_id": "esc",
            "epic_id": "158",
            "node_id": "us1",
            "question": "q",
            "expires_at": "soon",
            "choices": ["KILL_EPIC"],
            "recovery_evidence": {"classification": "unknown"},
        },
        mutations=mutations,
    )

    assert "no recorded dispatches" in floor_report
    assert "no recorded attempts" in floor_report
    assert "proposed answer: KILL_EPIC" in escalation_brief
    assert mutations.calls == []


def test_committed_fixture_transcript_shows_unavailable_and_no_actions() -> None:
    """The committed transcript is the executable fixtures' actual output."""
    renderer = load_skill_script("floor_render.py")
    escalation_renderer = load_skill_script("escalation_render.py")
    mutations = DeniedMutations()
    floor = renderer.render_floor(
        status=status_fixture_document(),
        attempts=attempt_fixture_document()["attempts"],
        services=unavailable_services(),
        registry={},
        mutations=mutations,
    )
    brief = escalation_renderer.render_brief(
        {
            "escalation_id": "esc158",
            "epic_id": "158-operator-skills-report-and-act-by-declared-intent",
            "node_id": "us1",
            "question": "retry available?",
            "expires_at": "2026-09-09T18:00:00Z",
            "choices": ["RETRY", "KILL_EPIC"],
            "recovery_evidence": {
                "classification": "deterministic",
                "tested_sha": "60943a0",
                "branch_moved": False,
            },
        },
        mutations=mutations,
    )

    transcript = (FLOOR_SKILL / "fixtures/transcript.txt").read_text(encoding="utf-8")
    assert "unavailable: temporal socket unavailable" in transcript
    assert "no action seam was called" in transcript
    assert mutations.calls == []
    assert floor in transcript
    assert brief in transcript


def test_helpers_execute_the_committed_fixtures() -> None:
    """The helper entrypoints render the committed fixture files unchanged."""
    floor_run = subprocess.run(
        [
            "python3",
            str(FLOOR_SKILL / "floor_render.py"),
            str(FLOOR_SKILL / "fixtures/status.json"),
            str(FLOOR_SKILL / "fixtures/attempts.json"),
            str(FLOOR_SKILL / "fixtures/services.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    escalation_run = subprocess.run(
        [
            "python3",
            str(ESCALATION_SKILL / "escalation_render.py"),
            str(ESCALATION_SKILL / "fixtures/escalation.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "runner debugger" in floor_run.stdout
    assert "unavailable: landing head target repo unavailable" in floor_run.stdout
    assert "proposed answer: RETRY" in escalation_run.stdout


def test_build_attempts_json_carries_recorded_builder_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The attempt JSON is the typed surface the floor helper consumes."""
    path = tmp_path / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(path))
    with closing(connect(path)) as store:
        upsert_result(
            store,
            make_result(
                persona="debugger",
                model_alias="claude-opus-5",
                route="gateway",
            ),
        )

    run = invoke("build", "attempts", EPIC, "--json")

    assert run.code == 0, run.stderr
    attempts = json.loads(run.stdout)["attempts"]
    assert attempts[0]["dispatch"] == make_result().dispatch
    assert attempts[0]["persona"] == "debugger"
    assert attempts[0]["model_alias"] == "claude-opus-5"
    assert attempts[0]["route"] == "gateway"
