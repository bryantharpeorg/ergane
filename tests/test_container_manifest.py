"""104-US3: the writer that remembers the engine container's project by digest.

Every test here is a **seam capture** (trap 14): a scratch directory stands in
for the supervision home (`ERGANE_STATE_HOME`, `XDG_CONFIG_HOME` and `HOME` are
pointed at `tmp_path`), the project is rendered from an injected
`ControlPlaneConfig` and a fixture `repos.json`, and the only side effects are
files under that directory. **No Docker daemon is contacted, no container
started and `apparmor_parser` never invoked** (trap 11) — this story writes,
remembers and removes files.

The rule under test is provenance by digest, not by filename: *a file the engine
did not write is never overwritten, and teardown removes only files whose
recorded digest still matches*. A filename allow-list would pass a sloppier
version of every test below, which is why each one edits content rather than
adding a name.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from factory.controlplane.config import ControlPlaneConfig
from factory.registry import load_registry
from factory.supervision import container_manifest as cm
from factory.supervision import container_project as cp
from factory.supervision.units import resolve_layout

#: An operator's own registry — no `example/` alias, unlike the packaged one.
OPERATOR_PERSONAS = """\
opus-closer:
  agent: claude-code
  model: anthropic/claude-opus-4
  write_scope: worktree
  needs_worktree: true
"""


def _config() -> ControlPlaneConfig:
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
            mode="external", address="127.0.0.1:7233", namespace="ergane"
        ),
        telemetry=ControlPlaneConfig.Telemetry(mode="none"),
        escalation=ControlPlaneConfig.Escalation(adapter="telegram"),
    )


@dataclasses.dataclass(frozen=True)
class _Host:
    """A relocated host: everything the writer touches is under `tmp_path`."""

    home: Path
    state_home: Path
    config_path: Path
    personas_path: Path
    registry_path: Path
    install_root: Path

    @property
    def layout(self):
        """The layout later stories hand `installed_project` and `remove_project`."""
        return resolve_layout(home=self.home)


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Host:
    home, state_home = tmp_path / "home", tmp_path / "relocated-state"
    config_dir = home / ".config" / "ergane"
    for directory in (home, state_home, config_dir):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    for name in (
        "FACTORY_STATE_HOME",
        "ERGANE_CONFIG_PATH",
        "FACTORY_CONFIG_PATH",
        "ERGANE_PERSONAS_PATH",
        "FACTORY_PERSONAS_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    config_path = config_dir / "config.toml"
    config_path.write_text("version = 1\n", encoding="utf-8")
    personas_path = config_dir / "personas.yaml"
    personas_path.write_text(OPERATOR_PERSONAS, encoding="utf-8")

    repo = tmp_path / "src" / "alpha"
    repo.mkdir(parents=True)
    registry_path = state_home / "ergane" / "repos.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({"version": 1, "repos": {"alpha": {"path": str(repo)}}}),
        encoding="utf-8",
    )

    install_root = tmp_path / "checkout"
    install_root.mkdir()
    (install_root / "Dockerfile").write_text("FROM debian\n", encoding="utf-8")

    return _Host(
        home=home,
        state_home=state_home,
        config_path=config_path,
        personas_path=personas_path,
        registry_path=registry_path,
        install_root=install_root,
    )


@pytest.fixture
def project(host: _Host) -> cp.ContainerProject:
    """The operational project this host would generate."""
    return cp.resolve_project(
        _config(),
        registry=load_registry(host.registry_path),
        config_path=host.config_path,
        personas_path=host.personas_path,
        home=host.home,
        install_root=host.install_root,
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest(project: cp.ContainerProject) -> Path:
    return project.directory / cm.MANIFEST_NAME


def _snapshot(directory: Path) -> dict[str, bytes]:
    """Every file in the directory, by name, as bytes — the byte-identity check."""
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def _rendered(project: cp.ContainerProject) -> dict[str, str]:
    return {f.name: f.text for f in cp.project_files(project)}


# --- T024 [US3-S1] Written, with a digest recorded for every file ---


def test_write_project_writes_every_rendered_file(
    project: cp.ContainerProject,
) -> None:
    """The project on disk is exactly what the renderer produced — all four
    files of R5, compose and `.env` beside the two confinement artifacts."""
    report = cm.write_project(project)

    rendered = _rendered(project)
    assert set(rendered) == {
        cp.COMPOSE_NAME,
        cp.ENV_NAME,
        cp.SECCOMP_ARTIFACT,
        cp.APPARMOR_ARTIFACT,
    }
    for name, text in rendered.items():
        assert (project.directory / name).read_text(encoding="utf-8") == text
    assert report.written == tuple(rendered)
    assert report.kept == ()
    assert report.directory == project.directory


def test_write_project_records_each_files_digest_in_the_manifest(
    project: cp.ContainerProject,
) -> None:
    """The manifest is the provenance record: name → digest of what was written,
    and nothing else, so the record cannot disagree with the bytes."""
    cm.write_project(project)

    document = json.loads(_manifest(project).read_text(encoding="utf-8"))
    assert document == {
        "files": {name: _digest(text) for name, text in _rendered(project).items()}
    }


def test_the_writer_writes_under_the_supervision_home_where_the_query_looks(
    host: _Host, project: cp.ContainerProject
) -> None:
    """R1: the generated project *is* the record that this host runs the
    container tier, so the writer and `installed_project` must agree on where it
    is without being told twice."""
    cm.write_project(project)

    assert project.directory == cp.project_dir(host.layout)
    assert project.directory.parent == cp.supervision_home()
    record = cm.installed_project(host.layout)
    assert record is not None
    assert record.directory == project.directory


def test_the_env_file_keeps_the_restrictive_mode_the_renderer_gave_it(
    project: cp.ContainerProject,
) -> None:
    """`GeneratedFile.mode` is honoured, not defaulted: no secret is written to
    `.env`, but a file by that name attracts them."""
    cm.write_project(project)

    assert (project.directory / cp.ENV_NAME).stat().st_mode & 0o777 == 0o600
    assert (project.directory / cp.COMPOSE_NAME).stat().st_mode & 0o777 == 0o644


def test_a_second_write_leaves_the_directory_and_manifest_byte_identical(
    project: cp.ContainerProject,
) -> None:
    """US3-S1's re-run is a no-op — proven on the bytes, manifest included, not
    on a report that claims it."""
    cm.write_project(project)
    before = _snapshot(project.directory)

    report = cm.write_project(project)

    assert _snapshot(project.directory) == before
    assert report.written == ()
    assert report.unchanged == tuple(_rendered(project))
    assert "already current" in report.render()


def test_a_second_write_rewrites_a_file_this_engine_wrote_and_something_truncated(
    project: cp.ContainerProject,
) -> None:
    """The no-op is not "never write again": a file whose recorded digest still
    matches is the engine's, and the engine restores it."""
    cm.write_project(project)
    compose = project.directory / cp.COMPOSE_NAME
    compose.unlink()

    report = cm.write_project(project)

    assert compose.read_text(encoding="utf-8") == _rendered(project)[cp.COMPOSE_NAME]
    assert report.written == (cp.COMPOSE_NAME,)


# --- T025 [US3-S2] A hand edit is never clobbered ---


def test_the_writer_refuses_to_overwrite_a_file_it_did_not_write(
    project: cp.ContainerProject,
) -> None:
    """`_is_someone_elses` (`units.py:962`) applied to the project directory: the
    operator's bytes survive, and the refusal names the path rather than the
    count."""
    cm.write_project(project)
    compose = project.directory / cp.COMPOSE_NAME
    compose.write_text("# hand-tuned by the operator\nservices: {}\n", encoding="utf-8")

    report = cm.write_project(project)

    assert compose.read_text(encoding="utf-8") == (
        "# hand-tuned by the operator\nservices: {}\n"
    )
    assert [kept.name for kept in report.kept] == [cp.COMPOSE_NAME]
    assert cp.COMPOSE_NAME not in report.written
    rendered = report.render()
    assert str(compose) in rendered
    assert "refus" in rendered


def test_a_run_that_refused_a_file_does_not_report_itself_as_current(
    project: cp.ContainerProject,
) -> None:
    """A write that wrote nothing *because it refused something* has not
    converged, and a headline saying otherwise is how an operator reads past the
    refusal underneath it."""
    cm.write_project(project)
    (project.directory / cp.COMPOSE_NAME).write_text("services: {}\n", encoding="utf-8")

    headline = cm.write_project(project).render().splitlines()[0]

    assert "already current" not in headline
    assert "left as the operator left them" in headline


def test_the_manifest_mode_is_pinned_rather_than_left_to_the_umask(
    project: cp.ContainerProject,
) -> None:
    """The generated project should not read differently on two hosts."""
    cm.write_project(project)

    assert _manifest(project).stat().st_mode & 0o777 == 0o644


def test_a_refused_file_is_no_longer_claimed_by_the_manifest(
    project: cp.ContainerProject,
) -> None:
    """The manifest records what this engine wrote, so a file it declined to
    write drops out of it — which is what makes teardown leave the edit alone."""
    cm.write_project(project)
    (project.directory / cp.COMPOSE_NAME).write_text("services: {}\n", encoding="utf-8")

    cm.write_project(project)

    claimed = json.loads(_manifest(project).read_text(encoding="utf-8"))["files"]
    assert cp.COMPOSE_NAME not in claimed
    assert cp.ENV_NAME in claimed


def test_the_refusal_is_by_digest_and_not_by_filename(
    project: cp.ContainerProject,
) -> None:
    """A file at a name the writer *would* write, present before any manifest
    exists: an allow-list keyed on names overwrites it, and the digest rule does
    not. This is the difference the story is about."""
    project.directory.mkdir(parents=True, exist_ok=True)
    stranger = project.directory / cp.COMPOSE_NAME
    stranger.write_text("# not ours, and never was\n", encoding="utf-8")

    report = cm.write_project(project)

    assert stranger.read_text(encoding="utf-8") == "# not ours, and never was\n"
    assert [kept.name for kept in report.kept] == [cp.COMPOSE_NAME]
    assert set(report.written) == {
        cp.ENV_NAME,
        cp.SECCOMP_ARTIFACT,
        cp.APPARMOR_ARTIFACT,
    }


def test_a_file_that_cannot_be_read_is_kept_rather_than_raised_over(
    host: _Host, project: cp.ContainerProject
) -> None:
    """The digest rule reads a file to compare it, so an unreadable one raises
    out of the middle of an install — and both ways a file here becomes
    unreadable are real: bytes that are not UTF-8, and a root-owned file left by
    a previous `sudo ergane install`. Unreadable is unproven, and unproven is
    left alone on both paths."""
    cm.write_project(project)
    compose = project.directory / cp.COMPOSE_NAME
    compose.write_bytes(b"services: \xff\xfe not utf-8\n")

    write = cm.write_project(project)

    assert [kept.name for kept in write.kept] == [cp.COMPOSE_NAME]
    assert compose.read_bytes() == b"services: \xff\xfe not utf-8\n"


def test_removal_keeps_a_recorded_file_it_cannot_read(
    host: _Host, project: cp.ContainerProject
) -> None:
    """The same tolerance on the teardown path, where the manifest still claims
    the file — so the branch is the recorded one, not the leftovers sweep."""
    cm.write_project(project)
    compose = project.directory / cp.COMPOSE_NAME
    compose.write_bytes(b"services: \xff\xfe not utf-8\n")

    report = cm.remove_project(host.layout)

    assert compose.read_bytes() == b"services: \xff\xfe not utf-8\n"
    assert cp.COMPOSE_NAME not in report.removed
    assert {kept.name: kept.reason for kept in report.kept}[cp.COMPOSE_NAME] == (
        cm.KEPT_CHANGED
    )


def test_the_writer_carries_provenance_for_a_file_it_no_longer_renders(
    project: cp.ContainerProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    """082-US4's lesson, in this directory: a name that falls out of the render
    also falls out of a manifest rebuilt from the render alone, and the file is
    then on the host with nothing left to prove it is the engine's. Teardown
    would keep it forever. The render is the seam here — `project_files` is
    rebound, so no Docker artifact changes shape to make the point."""
    cm.write_project(project)
    retired = project.directory / cp.SECCOMP_ARTIFACT

    full = cp.project_files(project)
    monkeypatch.setattr(
        cm,
        "project_files",
        lambda _project: tuple(f for f in full if f.name != cp.SECCOMP_ARTIFACT),
    )
    report = cm.write_project(project)

    assert retired.exists()
    assert report.retired == (cp.SECCOMP_ARTIFACT,)
    assert cp.SECCOMP_ARTIFACT in json.loads(
        _manifest(project).read_text(encoding="utf-8")
    )["files"]
    assert str(retired) in report.render()


# --- T026 [US3-S2] Removal takes ours and nothing else ---


def test_remove_project_removes_only_files_whose_digest_still_matches(
    host: _Host, project: cp.ContainerProject
) -> None:
    """Teardown's half of the same rule: the hand edit and the file the manifest
    never claimed both survive, and the report says which is which."""
    cm.write_project(project)
    edited = project.directory / cp.COMPOSE_NAME
    edited.write_text("# hand-tuned by the operator\n", encoding="utf-8")
    unclaimed = project.directory / "operator-notes.md"
    unclaimed.write_text("why we published a different port\n", encoding="utf-8")

    report = cm.remove_project(host.layout)

    assert not (project.directory / cp.ENV_NAME).exists()
    assert not (project.directory / cp.SECCOMP_ARTIFACT).exists()
    assert not (project.directory / cp.APPARMOR_ARTIFACT).exists()
    assert edited.read_text(encoding="utf-8") == "# hand-tuned by the operator\n"
    assert unclaimed.exists()
    assert set(report.removed) == {
        cp.ENV_NAME,
        cp.SECCOMP_ARTIFACT,
        cp.APPARMOR_ARTIFACT,
    }
    assert {kept.name: kept.reason for kept in report.kept} == {
        cp.COMPOSE_NAME: cm.KEPT_CHANGED,
        "operator-notes.md": cm.KEPT_UNCLAIMED,
    }


def test_removal_reports_what_it_kept_and_why(
    host: _Host, project: cp.ContainerProject
) -> None:
    """Reporting what it kept means by path and by reason: an operator reading
    `kept 2 file(s)` learns nothing they can act on."""
    cm.write_project(project)
    (project.directory / cp.COMPOSE_NAME).write_text("# mine now\n", encoding="utf-8")
    (project.directory / "operator-notes.md").write_text("mine too\n", encoding="utf-8")

    rendered = cm.remove_project(host.layout).render()

    assert str(project.directory / cp.COMPOSE_NAME) in rendered
    assert str(project.directory / "operator-notes.md") in rendered
    assert cm.KEPT_CHANGED in rendered
    assert cm.KEPT_UNCLAIMED in rendered
    assert project.directory.exists()


def test_removal_takes_the_project_directory_when_nothing_is_left(
    host: _Host, project: cp.ContainerProject
) -> None:
    """The supervision home keeps no empty shell of a tier the host no longer
    runs — but only when every last file in it was ours."""
    cm.write_project(project)

    report = cm.remove_project(host.layout)

    assert not project.directory.exists()
    assert report.directory_removed is True
    assert cm.installed_project(host.layout) is None


def test_removal_reads_the_manifest_alone_and_never_re_renders(
    host: _Host, project: cp.ContainerProject
) -> None:
    """Trap 13: bring-down may not require what bring-up requires. With the
    config and the registry gone — `resolve_project` could not run here — the
    recorded manifest still says what to remove."""
    cm.write_project(project)
    host.config_path.unlink()
    host.registry_path.unlink()

    report = cm.remove_project(host.layout)

    assert set(report.removed) == set(_rendered(project))
    assert not project.directory.exists()


def test_removal_on_a_host_with_no_project_removes_nothing_and_does_not_raise(
    host: _Host,
) -> None:
    """The systemd-tier host, and the second `ergane uninstall` in a row."""
    report = cm.remove_project(host.layout)

    assert report.removed == ()
    assert report.kept == ()
    assert report.directory_removed is False
    assert "no engine container project" in report.render()


def test_a_recorded_file_already_gone_is_reported_rather_than_raised(
    host: _Host, project: cp.ContainerProject
) -> None:
    """Half-removed is a state teardown meets, not one it refuses."""
    cm.write_project(project)
    (project.directory / cp.ENV_NAME).unlink()

    report = cm.remove_project(host.layout)

    assert cp.ENV_NAME not in report.removed
    assert report.missing == (cp.ENV_NAME,)


# --- T026 [US3-S2] The installation's record (R1) ---


def test_installed_project_is_none_on_a_host_that_has_no_project(
    host: _Host,
) -> None:
    """The query US5, US6 and US7 all ask instead of asking `config.toml` — R1
    puts the record on disk, so a systemd-tier host answers `None`."""
    assert cm.installed_project(host.layout) is None


def test_installed_project_returns_the_record_on_a_host_that_has_one(
    host: _Host, project: cp.ContainerProject
) -> None:
    cm.write_project(project)

    record = cm.installed_project(host.layout)

    assert record is not None
    assert record.directory == project.directory
    assert record.compose_path == project.directory / cp.COMPOSE_NAME
    assert record.files == tuple(sorted(_rendered(project)))
    assert record.digests == {
        name: _digest(text) for name, text in _rendered(project).items()
    }
    assert record.claims(cp.COMPOSE_NAME) is True
    assert record.claims("operator-notes.md") is False


def test_installed_project_defaults_to_the_supervision_home(
    project: cp.ContainerProject,
) -> None:
    """Called with no layout — the shape US5's bring-up uses — it looks where
    `project_dir()` puts the project."""
    cm.write_project(project)

    record = cm.installed_project()

    assert record is not None
    assert record.directory == cp.project_dir()


def test_an_unreadable_manifest_reads_as_no_project_rather_than_raising(
    host: _Host, project: cp.ContainerProject
) -> None:
    """Same tolerance `units.py:980` has: a truncated manifest is a host whose
    record is gone, and every later story would rather be told `None` than
    handed a traceback out of a teardown step."""
    cm.write_project(project)
    _manifest(project).write_text("{ truncated", encoding="utf-8")

    assert cm.installed_project(host.layout) is None
