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
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest
import yaml

import factory.supervision.container_manifest as manifest_module
import factory.supervision.engine_upgrade as upgrade_module
from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.controlplane.config import ControlPlaneConfig
from factory.controlplane.verify import render_findings
from factory.mergequeue.models import Finding
from factory.supervision.engine_upgrade import COMPOSE_NAME
from factory.supervision.engine_identity import (
    EngineIdentity,
    IMAGE_REPOSITORY,
    cli_version,
    identity_path,
    image_reference,
    read_identity,
    write_identity,
)
from factory.registry import Registry, RegistryEntry
from factory.supervision.units import (
    MANIFEST_NAME,
    CommandResult,
    _digest,
    supervision_home,
)
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
        verify_result: tuple[list[Finding], int] = (
            [Finding(check="engine", passed=True, detail="engine verified")],
            EXIT_OK,
        ),
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
        if not self.stop_ok:
            raise OperatorError("stop failed")

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
    """A minimal generated project, with the ownership manifest the writer
    keeps — enough for every upgrade flow to run against real files."""
    return _make_owned_project(_project_dir(state_home))


def _make_owned_project(directory: Path, *, version: str = "0.3.0") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        "compose.yaml": (
            "services:\n"
            "  ergane:\n"
            f"    image: {image_reference(version)}\n"
            "    init: true\n"
        ),
        ".env": f"ERGANE_VERSION={version}\n",
        "seccomp-ergane.json": "{}\n",
        "ergane-engine.profile": "profile\n",
    }
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
    manifest_module._write_manifest(
        directory, {name: _digest(text) for name, text in files.items()}
    )
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


class _IdentityLifecycleSeam(_FakeDockerSeam):
    """Moves the real identity file on the two disruptive lifecycle calls."""

    def __init__(
        self,
        state_home: Path,
        *,
        target_version: str,
        lifecycle_calls: list[tuple[str, tuple[Any, ...]]],
    ) -> None:
        super().__init__()
        self._state_home = state_home
        self._target_version = target_version
        self._lifecycle_calls = lifecycle_calls

    def stop(self) -> None:
        self._lifecycle_calls.append(("stop", ()))
        self.calls.append(("stop", ()))
        from factory.supervision.engine_identity import remove_identity

        remove_identity(self._state_home)

    def start(self, image_reference: str, *, env: dict[str, str] | None = None) -> None:
        self._lifecycle_calls.append(("start", (image_reference,)))
        super().start(image_reference, env=env)
        write_identity(
            self._state_home,
            EngineIdentity(
                version=self._target_version,
                started_at="2026-08-25T12:00:00+00:00",
                image_reference=image_reference,
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


def test_retention_unknown_previous_removes_nothing() -> None:
    """T002 / US1-S2 / FR-002: unknown rollback identity disables cleanup."""
    images = [
        image_reference("0.4.0"),
        image_reference("0.3.0"),
        image_reference("0.2.0"),
    ]

    decision = upgrade_module._retention_decision(
        images,
        target_image=image_reference("0.4.0"),
        previous_image=None,
    )

    assert decision.remove == ()
    assert decision.keep == tuple(images)
    assert any("keeping every local image" in note for note in decision.notes)


def test_retention_keeps_unrecognized_and_ambiguous_inventory() -> None:
    """T002 / US1-S2 / FR-002: only exact numeric release tags may be eligible."""
    target = image_reference("0.4.0")
    malformed_previous = f"{IMAGE_REPOSITORY}::malformed"
    inventory = [
        target,
        malformed_previous,
        f"{IMAGE_REPOSITORY}sha256:0123456789abcdef",
        "<dangling>:",
        f"{IMAGE_REPOSITORY}:latest",
        f"{IMAGE_REPOSITORY}:0.4.1-rc.1",
        f"{IMAGE_REPOSITORY}:0.5.0",
        f"{IMAGE_REPOSITORY}:0.10.0",
    ]

    decision = upgrade_module._retention_decision(
        inventory,
        target_image=target,
        previous_image=malformed_previous,
    )

    assert decision.remove == ()
    assert decision.keep == tuple(inventory)


def test_retention_orders_numeric_versions_not_tag_strings() -> None:
    """T002 / US1-S2 / FR-002: 0.10.0 is newer than 0.9.0 and stays eligible to keep."""
    target = image_reference("0.11.0")
    previous = image_reference("0.9.0")
    inventory = [
        target,
        previous,
        image_reference("0.8.0"),
        image_reference("0.10.0"),
    ]

    decision = upgrade_module._retention_decision(
        inventory,
        target_image=target,
        previous_image=previous,
    )

    assert decision.remove == (image_reference("0.8.0"),)
    assert decision.keep == (target, previous, image_reference("0.10.0"))


def test_upgrade_reads_old_identity_before_stop(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T001 / US1-S1 / FR-002: shutdown replaces the identity, not the rollback candidate."""
    state = isolated_state_home
    _make_project(state)
    old_version = "0.3.0"
    target_version = "0.4.0"
    _write_identity(state, old_version)
    lifecycle_calls: list[tuple[str, tuple[Any, ...]]] = []
    seam = _IdentityLifecycleSeam(
        state,
        target_version=target_version,
        lifecycle_calls=lifecycle_calls,
    )
    real_read_identity = upgrade_module.read_identity

    def read_pre_stop_identity(home: Path | str) -> EngineIdentity | None:
        lifecycle_calls.append(("read_identity", (str(identity_path(home)),)))
        return real_read_identity(home)

    monkeypatch.setattr(upgrade_module, "read_identity", read_pre_stop_identity)
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: target_version)
    older = image_reference("0.2.0")
    seam.images = [image_reference(target_version), image_reference(old_version), older]

    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=seam,
        _state_home=state,
    )

    assert [name for name, _arguments in lifecycle_calls] == ["read_identity", "stop", "start"]
    assert [name for name, _arguments in seam.calls] == [
        "stop",
        "start",
        "verify",
        "list_images",
        "remove_image",
    ]
    assert lifecycle_calls[0][1][0] == str(identity_path(state))
    assert seam.removed == [older]
    assert report.notes == (
        f"retargeted .env, compose.yaml to {image_reference(target_version)}",
        f"keeping target image {image_reference(target_version)}",
        f"keeping previous image {image_reference(old_version)}",
        f"removing 1 older image(s): {older}",
    )


@pytest.mark.parametrize(
    "initial_state",
    ["absent", "malformed", "image-less"],
)
def test_upgrade_unknown_pre_stop_identity_removes_nothing(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    initial_state: str,
) -> None:
    """T002 / US1-S2 / FR-003: uncertainty cannot be backfilled by the replacement."""
    state = isolated_state_home
    _make_project(state)
    target_version = "0.4.0"
    if initial_state == "malformed":
        identity_path(state).parent.mkdir(parents=True, exist_ok=True)
        identity_path(state).write_text("not-json", encoding="utf-8")
    elif initial_state == "image-less":
        write_identity(
            state,
            EngineIdentity(
                version="0.3.0",
                started_at="2026-08-25T12:00:00+00:00",
                image_reference=None,
                image_digest=None,
            ),
        )

    lifecycle_calls: list[tuple[str, tuple[Any, ...]]] = []
    seam = _IdentityLifecycleSeam(
        state,
        target_version=target_version,
        lifecycle_calls=lifecycle_calls,
    )
    real_read_identity = upgrade_module.read_identity

    def read_pre_stop_identity(home: Path | str) -> EngineIdentity | None:
        lifecycle_calls.append(("read_identity", (str(identity_path(home)),)))
        return real_read_identity(home)

    monkeypatch.setattr(upgrade_module, "read_identity", read_pre_stop_identity)
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: target_version)
    older = image_reference("0.2.0")
    seam.images = [image_reference(target_version), older]

    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=seam,
        _state_home=state,
    )

    assert [name for name, _arguments in lifecycle_calls] == ["read_identity", "stop", "start"]
    assert seam.removed == []
    assert any("keeping every local image" in note for note in report.notes)


@pytest.mark.parametrize("failure", ["stop", "start"])
def test_upgrade_lifecycle_failure_prevents_inventory_and_removal(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """T004 / US1-S3 / FR-004: lifecycle failure ends before image work."""
    _make_project(isolated_state_home)
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")
    seam = _FakeDockerSeam(
        stop_ok=failure != "stop",
        start_ok=failure != "start",
        images=[image_reference("0.2.0")],
    )

    with pytest.raises(OperatorError, match=f"{failure} failed"):
        upgrade_module.upgrade(
            open_epics=lambda: (),
            docker=seam,
        )

    assert [name for name, _args in seam.calls] == ["stop", "start"][: 1 if failure == "stop" else 2]
    assert ("list_images", ()) not in seam.calls
    assert seam.removed == []


def test_default_inventory_failure_prevents_image_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T004 / US1-S3 / FR-003: a failed inventory read disables all cleanup."""
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def run_subprocess(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(argv), kwargs))
        return subprocess.CompletedProcess(argv, 1, "", "connection refused")

    monkeypatch.setattr(upgrade_module.subprocess, "run", run_subprocess)
    seam = upgrade_module._ComposeDockerSeam(tmp_path / "engine-project")

    with pytest.raises(OperatorError, match=r"docker images.*\nconnection refused"):
        seam.list_images()

    assert [argv for argv, _kwargs in calls] == [(
        "docker", "images", "--format", "{{.Repository}}:{{.Tag}}",
    )]


def test_default_runner_routes_inventory_through_retention_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T004 / US1-S3 / FR-003: captured subprocess calls stay explicit and narrow."""
    project = _make_owned_project(tmp_path / "container")
    state = tmp_path / "state"
    _write_identity(state, "0.3.0")
    monkeypatch.setenv("ERGANE_COMPOSE_PROJECT", str(project))
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")

    target = image_reference("0.4.0")
    previous = image_reference("0.3.0")
    older = [image_reference("0.1.0"), image_reference("0.2.0")]
    unrelated = "example.com/operator/another-service:0.1.0"
    prefix_lookalike = f"{IMAGE_REPOSITORY}-operator/another-service:0.1.0"
    inventory = [target, previous, *older, unrelated, prefix_lookalike]
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    inventory_text = "\n".join(inventory)

    def run_subprocess(argv: list[str], **kwargs: Any) -> Any:
        calls.append((tuple(argv), kwargs))
        if argv[:2] == ["docker", "images"]:
            return subprocess.CompletedProcess(argv, 0, inventory_text, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def verify_engine() -> tuple[list[Finding], int]:
        finding = Finding(check="engine", passed=True, detail="0.4.0 matches")
        return ([finding], EXIT_OK)

    monkeypatch.setattr(upgrade_module.subprocess, "run", run_subprocess)
    monkeypatch.setattr(upgrade_module, "verify_controlplane", verify_engine)
    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=None,
        _state_home=state,
    )

    assert report.degraded is False
    assert [(name, args) for name, args in
            [(argv[1], argv[2:]) for argv, _kwargs in calls]] == [
        ("compose", ("-f", str(project / COMPOSE_NAME), "down")),
        ("compose", ("-f", str(project / COMPOSE_NAME), "up", "-d", "--no-build")),
        ("images", ("--format", "{{.Repository}}:{{.Tag}}")),
        ("rmi", (image_reference("0.1.0"),)),
        ("rmi", (image_reference("0.2.0"),)),
    ]
    assert all("--force" not in argv and "prune" not in argv for argv, _kwargs in calls)


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
    older = image_reference("0.2.0")
    seam = _FakeDockerSeam(
        verify_result=(findings, EXIT_USER),
        images=[image_reference("0.4.0"), older],
    )

    report = upgrade_module.upgrade(
        open_epics=lambda: (),
        docker=seam,
    )

    assert report.degraded is True
    assert any(f.check == "engine" and not f.passed for f in report.findings)
    assert ("list_images", ()) not in seam.calls
    assert seam.removed == []


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
    override = _make_owned_project(Path(isolated_state_home) / "override-project")
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


# ---------------------------------------------------------------------------
# US2: the owned project persists and launches the requested image
#
# The project under test is generated and persisted through the real
# `resolve_project`/`write_project` boundaries below temporary roots, and the
# upgrade runs through the real default runner with every docker child
# captured (FR-009).  No test contacts a daemon.
# ---------------------------------------------------------------------------


def _controlplane_config(address: str = "127.0.0.1:7233") -> ControlPlaneConfig:
    """A confirmed control-plane config, as the parser would leave it."""
    return ControlPlaneConfig(
        version=1,
        llm=ControlPlaneConfig.LLM(
            mode="gateway",
            gateway=ControlPlaneConfig.LLMGateway(
                base_url="http://127.0.0.1:4000",
                master_key_env="ERGANE_LLM_MASTER_KEY",
            ),
        ),
        memory=ControlPlaneConfig.Memory(backend="none"),
        temporal=ControlPlaneConfig.Temporal(
            mode="external", address=address, namespace="ergane"
        ),
        telemetry=ControlPlaneConfig.Telemetry(mode="none"),
        escalation=ControlPlaneConfig.Escalation(adapter="telegram"),
    )


def _generate_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str = "0.3.0",
    address: str = "127.0.0.1:7233",
    repos: tuple[Path, ...] = (),
    confinement: str = "profile",
    user: tuple[int, int] | None = None,
) -> Path:
    """Generate and persist a real owned project at `version` (US2-S1)."""
    import factory.supervision.container_project as project_module
    from factory.supervision.container_manifest import write_project

    monkeypatch.setattr(project_module, "_engine_image_version", lambda: version)
    if user is not None:
        monkeypatch.setattr(project_module.os, "getuid", lambda: user[0])
        monkeypatch.setattr(project_module.os, "getgid", lambda: user[1])
    monkeypatch.delenv("ERGANE_COMPOSE_PROJECT", raising=False)

    home = tmp_path / "home"
    config_dir = home / ".config" / "ergane"
    config_dir.mkdir(parents=True, exist_ok=True)
    for repo in repos:
        repo.mkdir(parents=True, exist_ok=True)
    registry = Registry(
        path=tmp_path / "repos.json",
        entries=tuple(
            RegistryEntry(slug=f"repo-{index}", path=path, manifest=path / "ergane.yaml")
            for index, path in enumerate(repos)
        ),
    )
    project = project_module.resolve_project(
        _controlplane_config(address),
        registry=registry,
        config_path=config_dir / "config.toml",
        personas_path=config_dir / "personas.yaml",
        home=home,
        install_root=tmp_path / "install",
        image_source=project_module.IMAGE_SOURCE_REGISTRY,
        confinement=confinement,
    )
    assert write_project(project).kept == ()
    return project.directory


def _capture_docker_children(
    monkeypatch: pytest.MonkeyPatch, *, inventory: list[str] | None = None
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    """Capture every docker child the default runner would spawn."""
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(argv), kwargs))
        if argv[:2] == ["docker", "images"]:
            return subprocess.CompletedProcess(
                argv, 0, "\n".join(inventory or []), ""
            )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(upgrade_module.subprocess, "run", run)
    return calls


def _green_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    finding = Finding(check="engine", passed=True, detail="engine verified")
    monkeypatch.setattr(
        upgrade_module, "verify_controlplane", lambda: ([finding], EXIT_OK)
    )


def _compose_child(
    calls: list[tuple[tuple[str, ...], dict[str, Any]]], verb: str
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """The one captured `docker compose … <verb>` child."""
    return next(
        (argv, kwargs)
        for argv, kwargs in calls
        if argv[1] == "compose" and verb in argv
    )


def test_upgrade_persists_cli_matched_image_and_version(
    isolated_state_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T006 / US2-S1 / FR-005: the persisted service image and version
    assignment match the CLI-matched published image request."""
    state = isolated_state_home
    directory = _generate_project(tmp_path, monkeypatch, version="0.3.0")
    _write_identity(state, "0.3.0")
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")
    _green_engine(monkeypatch)
    _capture_docker_children(monkeypatch)

    report = upgrade_module.upgrade(open_epics=lambda: (), _state_home=state)

    assert report.degraded is False
    assert any("retargeted" in note for note in report.notes)
    saved = yaml.safe_load(
        (directory / COMPOSE_NAME).read_text(encoding="utf-8")
    )
    assert saved["services"]["ergane"]["image"] == image_reference("0.4.0")
    env_text = (directory / ".env").read_text(encoding="utf-8")
    assert "ERGANE_VERSION=0.4.0" in env_text.splitlines()
    recorded = json.loads(
        (directory / MANIFEST_NAME).read_text(encoding="utf-8")
    )["files"]
    assert recorded[COMPOSE_NAME] == _digest(
        (directory / COMPOSE_NAME).read_text(encoding="utf-8")
    )
    assert recorded[".env"] == _digest(env_text)
    assert sorted(path.name for path in directory.iterdir()) == sorted(
        [COMPOSE_NAME, ".env", "seccomp-ergane.json", "ergane-engine.profile", MANIFEST_NAME]
    )


def test_compose_child_receives_requested_version_environment(
    isolated_state_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T006 / US2-S1 / FR-005: the real Compose child is started with the
    requested version in its actual subprocess environment."""
    state = isolated_state_home
    directory = _generate_project(tmp_path, monkeypatch, version="0.3.0")
    _write_identity(state, "0.3.0")
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")
    _green_engine(monkeypatch)
    calls = _capture_docker_children(
        monkeypatch,
        inventory=[
            image_reference("0.4.0"),
            image_reference("0.3.0"),
            image_reference("0.2.0"),
        ],
    )

    upgrade_module.upgrade(open_epics=lambda: (), _state_home=state)

    up_argv, up_kwargs = _compose_child(calls, "up")
    assert up_argv[:2] == ("docker", "compose")
    assert up_argv[up_argv.index("-f") + 1] == str(directory / COMPOSE_NAME)
    assert up_argv[-3:] == ("up", "-d", "--no-build")
    assert up_kwargs["cwd"] == str(directory)
    assert up_kwargs["env"]["ERGANE_VERSION"] == "0.4.0"


def test_upgrade_preserves_unrelated_fields_and_updates_ownership_digests(
    isolated_state_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T007 / US2-S2 / FR-006: retargeting rewrites only the owned image and
    version declarations; user, ports, mounts, confinement and unrelated
    environment survive byte-for-byte, and no secret is written."""
    repo = tmp_path / "repos" / "alpha"
    directory = _generate_project(
        tmp_path,
        monkeypatch,
        version="0.3.0",
        address="127.0.0.1:9055",
        repos=(repo,),
        confinement="unconfined",
        user=(1111, 2222),
    )
    compose_path = directory / COMPOSE_NAME
    env_path = directory / ".env"
    before_compose = compose_path.read_text(encoding="utf-8")
    before_env = env_path.read_text(encoding="utf-8")
    before_digests = dict(
        manifest_module.installed_project_at(directory).digests
    )
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")
    _green_engine(monkeypatch)
    _capture_docker_children(monkeypatch)

    upgrade_module.upgrade(open_epics=lambda: (), _state_home=isolated_state_home)

    after_compose = compose_path.read_text(encoding="utf-8")
    after_env = env_path.read_text(encoding="utf-8")
    _assert_only_line_changed(
        before_compose,
        after_compose,
        prefix="    image:",
        replacement=f"    image: {image_reference('0.4.0')}",
    )
    _assert_only_line_changed(
        before_env,
        after_env,
        prefix="ERGANE_VERSION=",
        replacement="ERGANE_VERSION=0.4.0",
    )
    # Operator-owned settings survive byte-for-byte.
    assert 'user: "1111:2222"' in after_compose
    assert '      - "127.0.0.1:9055:7233"' in after_compose
    assert "apparmor=unconfined" in after_compose
    assert f"      - {repo}:{repo}" in after_compose
    assert "TEMPORAL_NAMESPACE=ergane" in after_env
    # Retargeting writes no secret.
    assert not any(
        re.search(r"(KEY|TOKEN|SECRET|PASSWORD)=", line)
        for line in after_env.splitlines()
    )
    # Ownership digests: the retargeted files are re-recognized, the untouched
    # generated files are carried.
    installed = manifest_module.installed_project_at(directory)
    assert installed.claims(COMPOSE_NAME) and installed.claims(".env")
    assert installed.digests[COMPOSE_NAME] == _digest(after_compose)
    assert installed.digests[".env"] == _digest(after_env)
    assert (
        installed.digests["seccomp-ergane.json"]
        == before_digests["seccomp-ergane.json"]
    )
    assert (
        installed.digests["ergane-engine.profile"]
        == before_digests["ergane-engine.profile"]
    )


def _assert_only_line_changed(
    before: str, after: str, *, prefix: str, replacement: str
) -> None:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    assert len(before_lines) == len(after_lines)
    differing = [
        index
        for index, (one, other) in enumerate(zip(before_lines, after_lines))
        if one != other
    ]
    assert len(differing) == 1
    assert before_lines[differing[0]].startswith(prefix)
    assert after_lines[differing[0]] == replacement


_EXPECTED_OWNERSHIP_REFUSAL = {
    "changed": "changed since ergane wrote it",
    "unclaimed": "was not written by ergane",
    "missing": "is recorded as generated but is missing",
    "unsupported-compose": "unsupported",
    "unsupported-env": "unsupported",
    "manifest-absent": "not a readable ownership manifest",
}


def _mutate_project_artifact(directory: Path, mutation: str) -> Path:
    """Make one project artifact changed/unclaimed/missing/unsupported."""
    compose_path = directory / COMPOSE_NAME
    env_path = directory / ".env"
    manifest_path = directory / MANIFEST_NAME
    recorded = dict(
        manifest_module.installed_project_at(directory).digests
    )
    if mutation == "changed":
        compose_path.write_text(
            compose_path.read_text(encoding="utf-8") + "# operator edit\n",
            encoding="utf-8",
        )
        return compose_path
    if mutation == "unclaimed":
        del recorded[COMPOSE_NAME]
        manifest_module._write_manifest(directory, recorded)
        return compose_path
    if mutation == "missing":
        (directory / "seccomp-ergane.json").unlink()
        return directory / "seccomp-ergane.json"
    if mutation == "unsupported-compose":
        compose_path.write_text("services: {}\n", encoding="utf-8")
        recorded[COMPOSE_NAME] = _digest("services: {}\n")
        manifest_module._write_manifest(directory, recorded)
        return compose_path
    if mutation == "unsupported-env":
        text = "".join(
            line + "\n"
            for line in env_path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("ERGANE_VERSION=")
        )
        env_path.write_text(text, encoding="utf-8")
        recorded[".env"] = _digest(text)
        manifest_module._write_manifest(directory, recorded)
        return env_path
    if mutation == "manifest-absent":
        manifest_path.unlink()
        return manifest_path
    raise AssertionError(f"unknown mutation {mutation!r}")


@pytest.mark.parametrize(
    "mutation",
    [
        "changed",
        "unclaimed",
        "missing",
        "unsupported-compose",
        "unsupported-env",
        "manifest-absent",
    ],
)
def test_upgrade_refuses_artifact_problems_before_stop_or_write(
    isolated_state_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """T008 / US2-S3 / FR-007: changed, unclaimed, missing and unsupported
    artifacts refuse by path before stop or write, every byte is preserved,
    and `--force` does not adopt operator edits."""
    state = isolated_state_home
    directory = _generate_project(tmp_path, monkeypatch, version="0.3.0")
    affected = _mutate_project_artifact(directory, mutation)
    before = {path.name: path.read_bytes() for path in sorted(directory.iterdir())}
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")
    open_epic = OpenEpic(epic_id="174-test/us2", behavior=0, build_id=None)

    for forced, epics in ((False, ()), (True, (open_epic,))):
        seam = _FakeDockerSeam()
        with pytest.raises(OperatorError) as raised:
            upgrade_module.upgrade(
                open_epics=lambda: epics,
                docker=seam,
                force=forced,
                _state_home=state,
            )
        message = str(raised.value)
        assert str(affected) in message
        assert _EXPECTED_OWNERSHIP_REFUSAL[mutation] in message
        # Every byte preserved, and no lifecycle call authorized the stop.
        assert {
            path.name: path.read_bytes() for path in sorted(directory.iterdir())
        } == before
        assert seam.calls == []


def test_upgrade_persistence_failure_restores_previous_project(
    isolated_state_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T009 / US2-S4 / FR-008: a persistence failure after validation commits
    nothing, restores the prior bytes, and authorizes no lifecycle call; a
    later invocation proceeds on the restored prior project."""
    state = isolated_state_home
    directory = _generate_project(tmp_path, monkeypatch, version="0.3.0")
    before = {path.name: path.read_bytes() for path in sorted(directory.iterdir())}
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")

    real_replace = Path.replace
    renames = {"count": 0}

    def replace(self: Path, target: Path) -> Path:
        renames["count"] += 1
        if renames["count"] == 2:
            raise OSError("synthetic mid-transaction failure")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace)

    seam = _FakeDockerSeam()
    with pytest.raises(OperatorError) as raised:
        upgrade_module.upgrade(
            open_epics=lambda: (), docker=seam, _state_home=state
        )

    message = str(raised.value)
    assert "could not commit" in message
    assert str(directory / ".env") in message
    assert {path.name: path.read_bytes() for path in sorted(directory.iterdir())} == before
    assert seam.calls == []

    # No half-retargeted project is observable: the manifest still owns the
    # restored bytes exactly.
    installed = manifest_module.installed_project_at(directory)
    for name in (COMPOSE_NAME, ".env"):
        assert installed.digests[name] == _digest(
            (directory / name).read_text(encoding="utf-8")
        )

    # The restored prior project is usable: a subsequent invocation proceeds.
    monkeypatch.setattr(Path, "replace", real_replace)
    _green_engine(monkeypatch)
    _capture_docker_children(monkeypatch)
    report = upgrade_module.upgrade(open_epics=lambda: (), _state_home=state)

    assert report.degraded is False
    assert yaml.safe_load(
        (directory / COMPOSE_NAME).read_text(encoding="utf-8")
    )["services"]["ergane"]["image"] == image_reference("0.4.0")


def test_upgrade_rereads_saved_selection_on_next_invocation(
    isolated_state_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T011 / US2-S1 / FR-005 / FR-006: a later invocation selects the saved
    image and version, rewriting nothing, and re-proves both actual-boundary
    regressions."""
    state = isolated_state_home
    directory = _generate_project(tmp_path, monkeypatch, version="0.3.0")
    _write_identity(state, "0.3.0")
    monkeypatch.setattr(upgrade_module, "cli_version", lambda: "0.4.0")
    _green_engine(monkeypatch)
    _capture_docker_children(monkeypatch)

    upgrade_module.upgrade(open_epics=lambda: (), _state_home=state)

    saved_compose = (directory / COMPOSE_NAME).read_text(encoding="utf-8")
    saved_env = (directory / ".env").read_text(encoding="utf-8")
    saved_manifest = (directory / MANIFEST_NAME).read_bytes()

    calls = _capture_docker_children(
        monkeypatch,
        inventory=[image_reference("0.4.0"), image_reference("0.3.0")],
    )
    report = upgrade_module.upgrade(open_epics=lambda: (), _state_home=state)

    # The saved selection already matches the request: nothing is rewritten.
    assert (directory / COMPOSE_NAME).read_text(encoding="utf-8") == saved_compose
    assert (directory / ".env").read_text(encoding="utf-8") == saved_env
    assert (directory / MANIFEST_NAME).read_bytes() == saved_manifest
    assert yaml.safe_load(saved_compose)["services"]["ergane"][
        "image"
    ] == image_reference("0.4.0")
    assert any("already selects" in note for note in report.notes)

    # Both actual-boundary regressions re-run green.
    up_argv, up_kwargs = _compose_child(calls, "up")
    assert up_argv[up_argv.index("-f") + 1] == str(directory / COMPOSE_NAME)
    assert up_kwargs["env"]["ERGANE_VERSION"] == "0.4.0"

