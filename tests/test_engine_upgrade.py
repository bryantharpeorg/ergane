"""105-US4: `ergane engine upgrade` refuses in-flight work, drains, verifies
through the new engine, and reaps older images while keeping the current and
previous versions.

Every test here is a **seam capture**: the open-epic read, the project directory,
and every docker interaction are injected. No test starts a container, contacts a
daemon, or shells out to docker (trap 21).
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest

import factory.supervision.engine_upgrade as upgrade_module
from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.controlplane.verify import render_findings
from factory.mergequeue.models import Finding
from factory.supervision.engine_identity import (
    EngineIdentity,
    IMAGE_REPOSITORY,
    cli_version,
    identity_path,
    image_reference,
)
from factory.supervision.units import CommandResult, supervision_home
from factory.versioning import OpenEpic


# ---------------------------------------------------------------------------
# Helpers and fakes
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    return state


class _FakeDockerSeam:
    """Records every call made through the docker seam in order."""

    def __init__(
        self,
        *,
        stop_ok: bool = True,
        start_ok: bool = True,
        verify_result: tuple[list[Finding], int] = ([], EXIT_OK),
        images: list[str] | None = None,
        remove_ok: bool = True,
    ) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.stop_ok = stop_ok
        self.start_ok = start_ok
        self.verify_result = verify_result
        self.images = images or []
        self.remove_ok = remove_ok
        self.removed: list[str] = []
        self.started_image: str | None = None
        self.started_env: dict[str, str] | None = None

    def stop(self) -> None:
        self.calls.append(("stop", ()))

    def start(self, image_reference: str, *, env: dict[str, str] | None = None) -> None:
        self.calls.append(("start", (image_reference,)))
        self.started_image = image_reference
        self.started_env = env
        if not self.start_ok:
            raise OperatorError("start failed")

    def verify(self) -> tuple[list[Finding], int]:
        self.calls.append(("verify", ()))
        return self.verify_result

    def list_images(self) -> list[str]:
        self.calls.append(("list_images", ()))
        return self.images

    def remove_image(self, ref: str) -> None:
        self.calls.append(("remove_image", (ref,)))
        self.removed.append(ref)
        if not self.remove_ok:
            raise OperatorError("remove failed")


def _project_dir(state_home: Path) -> Path:
    return state_home / "ergane" / "supervision" / "container"


def _make_project(state_home: Path) -> Path:
    directory = _project_dir(state_home)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    return directory


def _write_identity(state_home: Path, version: str, *, image_reference_value: str | None = None) -> Path:
    from factory.supervision.engine_identity import EngineIdentity, write_identity

    image = image_reference_value if image_reference_value is not None else image_reference(version)
    return write_identity(
        state_home,
        EngineIdentity(
            version=version,
            started_at="2026-08-25T12:00:00+00:00",
            image_reference=image,
            image_digest=None,
        ),
    )


def test_retention_removes_only_exact_repository_older_releases() -> None:
    """T001 / US1-S1 / FR-001: exact repository equality bounds cleanup."""
    target = image_reference("0.4.0")
    previous = image_reference("0.3.0")
    older = [image_reference("0.1.0"), image_reference("0.2.0")]
    unrelated = "example.com/operator/another-service:0.1.0"
    prefix_lookalike = f"{IMAGE_REPOSITORY}-operator/another-service:0.1.0"

    decision = upgrade_module._retention_decision(
        [target, previous, *older, unrelated, prefix_lookalike],
        target_image=target,
        previous_image=previous,
    )

    assert decision.remove == tuple(older)
    assert decision.keep == (target, previous, unrelated, prefix_lookalike)


# ---------------------------------------------------------------------------
# T033: refuse while work is in flight
# ---------------------------------------------------------------------------


def test_upgrade_refuses_while_epics_in_flight(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T033 / US4-S1 / FR-018: in-flight epics named, no docker calls, nonzero."""
    open_epic = OpenEpic(epic_id="105-test/us1", behavior=0, build_id=None)

    def _open_epics() -> tuple[OpenEpic, ...]:
        return (open_epic,)

    seam = _FakeDockerSeam()

    with pytest.raises(OperatorError) as raised:
        upgrade_module.upgrade(
            open_epics=_open_epics,
            docker=seam,
        )

    message = str(raised.value)
    assert "105-test/us1" in message
    assert "in flight" in message or "flight" in message
    assert "strands" in message or "stop" in message
    assert "--force" in message
    assert seam.calls == []


# ---------------------------------------------------------------------------
# T034: --force proceeds and records it
# ---------------------------------------------------------------------------


def test_upgrade_force_proceeds_past_open_epics(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T034 / US4-S1 / FR-018: `--force` continues and reports that it was forced."""
    _make_project(isolated_state_home)
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")

    open_epic = OpenEpic(epic_id="105-test/us1", behavior=0, build_id=None)

    def _open_epics() -> tuple[OpenEpic, ...]:
        return (open_epic,)

    seam = _FakeDockerSeam()
    report = upgrade_module.upgrade(
        open_epics=_open_epics,
        docker=seam,
        force=True,
    )

    assert report.forced is True
    assert any("105-test/us1" in note for note in report.notes)
    assert ("stop", ()) in seam.calls


# ---------------------------------------------------------------------------
# T035: drained path seam order
# ---------------------------------------------------------------------------


def test_upgrade_drained_path_calls_stop_start_verify_retention_in_order(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T035 / US4-S2 / FR-019 / FR-020: ordered stop, start, verify, retention."""
    _make_project(isolated_state_home)
    _write_identity(isolated_state_home, "0.3.0")
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")

    seam = _FakeDockerSeam(images=[
        f"{image_reference('0.4.0')}",
        f"{image_reference('0.3.0')}",
        f"{image_reference('0.2.0')}",
        f"{image_reference('0.1.0')}",
    ])

    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=seam,
    )

    assert report.degraded is False
    call_names = [name for name, _args in seam.calls]
    assert call_names == ["stop", "start", "verify", "list_images", "remove_image", "remove_image"]
    assert seam.started_image == image_reference("0.4.0")
    assert seam.started_env == {"ERGANE_VERSION": "0.4.0"}


# ---------------------------------------------------------------------------
# T036: retention keeps current + previous, removes older two, unknown-is-not-zero
# ---------------------------------------------------------------------------


def test_retention_keeps_current_and_previous_removes_older_two(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T036 / US4-S2 / FR-019: four versions; exactly the oldest two are removed."""
    _make_project(isolated_state_home)
    _write_identity(isolated_state_home, "0.3.0")
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")

    seam = _FakeDockerSeam(images=[
        image_reference("0.4.0"),  # current after start
        image_reference("0.3.0"),  # previous
        image_reference("0.2.0"),  # older -> remove
        image_reference("0.1.0"),   # older -> remove
    ])

    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=seam,
    )

    assert report.degraded is False
    assert seam.removed == [image_reference("0.2.0"), image_reference("0.1.0")]
    assert image_reference("0.4.0") not in seam.removed
    assert image_reference("0.3.0") not in seam.removed


def test_retention_unknown_running_version_removes_nothing(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T036 / US4-S2 / FR-019: when the running version is unreadable, nothing is removed."""
    _make_project(isolated_state_home)
    # No identity record, so current/previous cannot be determined.
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")

    seam = _FakeDockerSeam(images=[
        image_reference("0.4.0"),
        image_reference("0.3.0"),
        image_reference("0.2.0"),
    ])

    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=seam,
        _state_home=isolated_state_home,
    )

    assert seam.removed == []
    assert any("could not read" in note.lower() or "unknown" in note.lower() for note in report.notes)


# ---------------------------------------------------------------------------
# T037: degraded keyed on engine finding alone
# ---------------------------------------------------------------------------


def test_upgrade_degraded_when_engine_finding_mismatches(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T037 / US4-S2 / FR-019: a red engine finding makes the report degraded."""
    _make_project(isolated_state_home)
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")

    findings = [
        Finding(check="engine", passed=False, detail="engine mismatch"),
    ]
    seam = _FakeDockerSeam(verify_result=(findings, EXIT_USER))

    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=seam,
    )

    assert report.degraded is True
    assert any(f.check == "engine" and not f.passed for f in report.findings)


def test_upgrade_success_when_only_unrelated_probe_fails(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T037 / US4-S2 / FR-019: an unrelated red probe does not degrade the upgrade."""
    _make_project(isolated_state_home)
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")

    findings = [
        Finding(check="engine", passed=True, detail="engine version matches this CLI (0.4.0)"),
        Finding(check="llm", passed=False, detail="proxy refused"),
        Finding(check="forge", passed=False, detail="gh not capable"),
    ]
    seam = _FakeDockerSeam(verify_result=(findings, EXIT_USER), images=[image_reference("0.4.0")])

    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=seam,
    )

    assert report.degraded is False
    assert len(report.findings) == 3
    checks = {f.check: f.passed for f in report.findings}
    assert checks == {"engine": True, "llm": False, "forge": False}


# ---------------------------------------------------------------------------
# T038: project directory derived and checked
# ---------------------------------------------------------------------------


def test_upgrade_refuses_when_project_directory_missing(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T038 / US4-S3 / FR-023: missing directory names `ergane install`."""
    # Intentionally do not create the project directory.
    monkeypatch.delenv("ERGANE_COMPOSE_PROJECT", raising=False)

    seam = _FakeDockerSeam()

    with pytest.raises(OperatorError) as raised:
        upgrade_module.upgrade(
            open_epics=lambda: (),
            docker=seam,
        )

    message = str(raised.value)
    expected_dir = _project_dir(isolated_state_home)
    assert str(expected_dir) in message
    assert "ergane install" in message
    assert seam.calls == []


def test_upgrade_refuses_when_compose_yaml_missing(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T038 / US4-S3 / FR-023: directory exists without compose.yaml refuses the same way."""
    directory = _project_dir(isolated_state_home)
    directory.mkdir(parents=True, exist_ok=True)
    # No compose.yaml

    monkeypatch.delenv("ERGANE_COMPOSE_PROJECT", raising=False)

    seam = _FakeDockerSeam()

    with pytest.raises(OperatorError) as raised:
        upgrade_module.upgrade(
            open_epics=lambda: (),
            docker=seam,
        )

    message = str(raised.value)
    assert str(directory) in message
    assert "ergane install" in message
    assert seam.calls == []


def test_upgrade_compose_project_override_wins(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T038 / US4-S3 / FR-023: ERGANE_COMPOSE_PROJECT overrides the derived directory."""
    override = Path(isolated_state_home) / "override-project"
    override.mkdir(parents=True, exist_ok=True)
    (override / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setenv("ERGANE_COMPOSE_PROJECT", str(override))

    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")

    seam = _FakeDockerSeam(images=[image_reference("0.4.0")])
    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=seam,
    )

    assert report.degraded is False


def test_upgrade_refusal_does_not_tell_operator_to_set_variable(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T038 / US4-S3 / FR-023: the refusal never names ERGANE_COMPOSE_PROJECT."""
    monkeypatch.delenv("ERGANE_COMPOSE_PROJECT", raising=False)
    seam = _FakeDockerSeam()

    with pytest.raises(OperatorError) as raised:
        upgrade_module.upgrade(
            open_epics=lambda: (),
            docker=seam,
        )

    message = str(raised.value)
    assert "ERGANE_COMPOSE_PROJECT" not in message
