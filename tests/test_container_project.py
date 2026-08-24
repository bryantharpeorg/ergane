"""104-US2: the generator that renders the engine container's compose project.

Every test here is a **seam capture** in the sense of the plan's trap 14: the
renderer is a pure function of project data, the registry is a fixture file, and
the confinement artifacts are read off the checkout.  No Docker daemon, no
container and no `apparmor_parser` is contacted, because none is needed — this
story renders text and nothing else.

The word *container* is overloaded three ways in this tree, so everything below
says **the engine container**: the Docker container `ergane install` brings up,
never bwrap's sandbox and never "a container of specs".
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import os
import tomllib
from pathlib import Path

import pytest
import yaml

from factory.cli.errors import OperatorError
from factory.config import is_example_alias, load_personas, resolve_default_registry_path
from factory.controlplane.config import ControlPlaneConfig
from factory.registry import load_registry, resolve_state_home
from factory.supervision import container_project as cp
from factory.supervision.units import GeneratedFile, supervision_home

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_REFERENCE = REPO_ROOT / "container" / "compose.reference.yaml"


# ---------------------------------------------------------------------------
# Fixtures: a confirmed config, a two-repo registry, and a relocated state home
# ---------------------------------------------------------------------------


def _config(address: str = "127.0.0.1:7233") -> ControlPlaneConfig:
    """A confirmed control-plane config, built the way the parser would leave it."""
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
        escalation=ControlPlaneConfig.Escalation(
            adapter="telegram",
            bot_token_env="TELEGRAM_BOT_TOKEN",
            chat_id_env="TELEGRAM_CHAT_ID",
        ),
    )


#: A persona registry with no `example/` alias in it — the operator's own file,
#: as distinct from the packaged example `resolve_default_registry_path` falls
#: back to (`factory/config.py:134`).
OPERATOR_PERSONAS = """\
opus-closer:
  agent: claude-code
  model: anthropic/claude-opus-4
  write_scope: worktree
  needs_worktree: true
  timeout: 3600
verifier:
  agent: none
  model: null
  write_scope: read
  needs_worktree: false
"""


@dataclasses.dataclass(frozen=True)
class _Host:
    """Where the fixture put this host's directories."""

    home: Path
    state_home: Path
    config_dir: Path
    config_path: Path
    personas_path: Path
    repos: tuple[Path, ...]
    registry_path: Path
    install_root: Path

    @property
    def state_root(self) -> Path:
        """The state *root*: `resolve_state_home()` returns its parent."""
        return self.state_home / "ergane"


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Host:
    """A relocated host: two registered repos, an operator config and registry.

    `ERGANE_STATE_HOME` is moved off `~` deliberately (trap 5): a generator that
    copied the reference file's `${HOME}/.local/state/ergane` literal instead of
    calling `resolve_state_home()` renders a project that is mounted at one path
    and resolves another.
    """
    home = tmp_path / "home"
    state_home = tmp_path / "relocated-state"
    config_dir = home / ".config" / "ergane"
    for directory in (home, state_home, config_dir):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.delenv("ERGANE_CONFIG_PATH", raising=False)
    monkeypatch.delenv("FACTORY_CONFIG_PATH", raising=False)
    monkeypatch.delenv("ERGANE_PERSONAS_PATH", raising=False)
    monkeypatch.delenv("FACTORY_PERSONAS_PATH", raising=False)

    config_path = config_dir / "config.toml"
    config_path.write_text("version = 1\n", encoding="utf-8")
    personas_path = config_dir / "personas.yaml"
    personas_path.write_text(OPERATOR_PERSONAS, encoding="utf-8")

    repos = tuple(tmp_path / "src" / name for name in ("alpha", "beta"))
    for repo in repos:
        repo.mkdir(parents=True)
        (repo / "factory.yaml").write_text("version: 1\n", encoding="utf-8")

    registry_path = state_home / "ergane" / "repos.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "repos": {
                    repo.name: {
                        "path": str(repo),
                        "manifest": str(repo / "factory.yaml"),
                    }
                    for repo in repos
                },
            }
        ),
        encoding="utf-8",
    )

    install_root = tmp_path / "checkout"
    install_root.mkdir()
    (install_root / "Dockerfile").write_text("FROM debian\n", encoding="utf-8")

    return _Host(
        home=home,
        state_home=state_home,
        config_dir=config_dir,
        config_path=config_path,
        personas_path=personas_path,
        repos=repos,
        registry_path=registry_path,
        install_root=install_root,
    )


def _project(host: _Host, **overrides: object) -> cp.ContainerProject:
    """The operational project for the fixture host."""
    kwargs: dict[str, object] = {
        "registry": load_registry(host.registry_path),
        "config_path": host.config_path,
        "personas_path": host.personas_path,
        "home": host.home,
        "install_root": host.install_root,
    }
    kwargs.update(overrides)
    return cp.resolve_project(_config(), **kwargs)  # type: ignore[arg-type]


def _env_map(project: cp.ContainerProject) -> dict[str, str]:
    return {assignment.name: assignment.value for assignment in project.env_assignments}


def _comment_lines(text: str) -> tuple[str, ...]:
    """Every line whose first non-space character is `#`, stripped (R4)."""
    return tuple(
        line.strip() for line in text.splitlines() if line.strip().startswith("#")
    )


def _binds(compose: dict) -> list[str]:
    return [str(entry) for entry in compose["services"]["ergane"]["volumes"]]


# ---------------------------------------------------------------------------
# T009 [US2-S3] One fact, two files, one test — structurally, not byte-for-byte
# ---------------------------------------------------------------------------


def test_reference_render_parses_equal_to_the_committed_compose() -> None:
    """`yaml.safe_load` of the render equals `yaml.safe_load` of the reference.

    Deliberately not byte equality (R4): the committed file mixes flow and block
    style, quotes `user` but not `init`, and carries
    `${ERGANE_REPO_EXAMPLE:-/path/to/repo}` interpolation.  Pinning that makes
    the renderer a museum of one file's whitespace.
    """
    rendered = cp.render_compose(cp.reference_project())
    committed = COMPOSE_REFERENCE.read_text(encoding="utf-8")
    assert yaml.safe_load(rendered) == yaml.safe_load(committed)


def test_reference_render_carries_the_same_comment_lines_in_order() -> None:
    """Comments are data (R4), so they are the second half of the agreement."""
    rendered = cp.render_compose(cp.reference_project())
    committed = COMPOSE_REFERENCE.read_text(encoding="utf-8")
    assert _comment_lines(rendered) == _comment_lines(committed)


# ---------------------------------------------------------------------------
# T010 [US2-S3] The comment model: header and annotations are project data
# ---------------------------------------------------------------------------


def test_container_project_is_frozen_and_carries_the_comment_fields() -> None:
    assert cp.ContainerProject.__dataclass_params__.frozen is True
    names = {field.name for field in dataclasses.fields(cp.ContainerProject)}
    assert {"header", "annotations"} <= names, (
        f"ContainerProject must carry the R4 comment fields, has {sorted(names)}"
    )


def test_reference_header_is_the_committed_files_own_header() -> None:
    """The header above `services:` in the committed file, carried as data."""
    committed = COMPOSE_REFERENCE.read_text(encoding="utf-8").splitlines()
    committed_header = tuple(line.strip() for line in committed[: committed.index("")])

    rendered = cp.render_compose(cp.reference_project()).splitlines()
    rendered_header = tuple(line.strip() for line in rendered[: rendered.index("")])

    assert rendered_header == committed_header
    assert len(committed_header) == 6, "the committed header is six comment lines"


def test_reference_annotations_key_the_elements_they_precede() -> None:
    project = cp.reference_project()
    assert cp.REPO_MOUNT_KEY in project.annotations
    for mount in project.mounts:
        assert project.annotations.get(mount.source), (
            f"every reference mount carries its committed comment; {mount.source} does not"
        )


def test_operational_header_names_itself_generated_and_never_a_reference(
    host: _Host,
) -> None:
    """The operational project may not claim to be the reference artifact.

    A renderer that hard-coded the reference's header would emit "this is a
    reference artifact" into a file `ergane install` regenerates on every run —
    a generated file lying about itself.
    """
    reference_text = cp.render_compose(cp.reference_project())
    operational_text = cp.render_compose(_project(host))

    assert "reference artifact" in reference_text
    assert "reference artifact" not in operational_text
    assert "do not hand-edit" in operational_text.lower()
    assert "ergane install" in operational_text
    assert cp._engine_image_version() in operational_text


# ---------------------------------------------------------------------------
# T011 [US2-S1] Same-path mounts, bare passthrough names, resolved values in .env
# ---------------------------------------------------------------------------


def test_operational_project_mounts_every_root_same_path(host: _Host) -> None:
    project = _project(host)
    compose = yaml.safe_load(cp.render_compose(project))
    binds = _binds(compose)

    expected = [
        resolve_state_home() / "ergane",
        supervision_home(),
        host.config_dir,
        *host.repos,
    ]
    for path in expected:
        assert f"{path}:{path}" in binds, f"expected a same-path bind for {path}"

    # The resolvers were called, not the reference file's literals copied.
    assert resolve_state_home() == host.state_home
    assert str(host.state_root) in "\n".join(binds)

    repo_mounts = compose[cp.REPO_MOUNT_KEY]
    assert [entry["source"] for entry in repo_mounts] == [str(r) for r in host.repos]
    assert all(entry["source"] == entry["target"] for entry in repo_mounts)


def test_operational_environment_keeps_the_bare_passthrough_names(host: _Host) -> None:
    """R5: `environment:` carries names; values live in `.env`.

    The committed drift derivation (now this module's
    `derived_environment_names`) requires bare names like `ERGANE_STATE_HOME`;
    an `ERGANE_STATE_HOME=/home/...` entry would not match it.
    """
    compose = yaml.safe_load(cp.render_compose(_project(host)))
    names = compose["services"]["ergane"]["environment"]

    assert all("=" not in name for name in names), (
        f"environment entries must be bare names, got {names}"
    )
    missing = cp.derived_environment_names() - set(names)
    assert not missing, f"environment missing passthrough for: {sorted(missing)}"


def test_resolved_values_land_in_the_generated_env_file(host: _Host) -> None:
    project = _project(host)
    env_text = cp.render_env(project)
    env = _env_map(project)

    assert env["ERGANE_STATE_HOME"] == str(host.state_home)
    assert env["HOME"] == str(host.home)
    for name, value in env.items():
        assert f"{name}={value}" in env_text

    files = {generated.name: generated for generated in cp.project_files(project)}
    assert set(files) == {
        "compose.yaml",
        ".env",
        cp.SECCOMP_ARTIFACT,
        cp.APPARMOR_ARTIFACT,
    }
    assert all(isinstance(f, GeneratedFile) for f in files.values())
    assert files[".env"].text == env_text
    assert files["compose.yaml"].directory == cp.project_dir()


# ---------------------------------------------------------------------------
# T012 [US2-S1] Trap 3: the engine is handed its config and registry by path
# ---------------------------------------------------------------------------


def test_env_pins_config_personas_and_home_to_absolute_host_paths(
    host: _Host,
) -> None:
    project = _project(host)
    env = _env_map(project)

    for name, expected in (
        ("ERGANE_CONFIG_PATH", host.config_path),
        ("ERGANE_PERSONAS_PATH", host.personas_path),
        ("HOME", host.home),
    ):
        assert env[name] == str(expected)
        assert Path(env[name]).is_absolute(), f"{name} must be an absolute host path"

    compose = yaml.safe_load(cp.render_compose(project))
    assert f"{host.config_dir}:{host.config_dir}" in _binds(compose), (
        "the config directory must be mounted same-path, or `~/.config` does not "
        "exist inside the engine (the image pins HOME=/home/ergane)"
    )


def test_the_pins_are_what_stops_the_packaged_example_registry(
    host: _Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trap 3, asserted with the detector the tree already ships.

    Without the pin, `resolve_default_registry_path` falls through to its
    `factory/config.py:134` branch and hands the engine the packaged example —
    whose aliases `is_example_alias` recognises.  The engine then looks healthy
    and fails at the first dispatch, hours later.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(host.home / "unconfigured"))
    fallback = load_personas(resolve_default_registry_path())
    assert any(
        is_example_alias(persona.model) for persona in fallback.values() if persona.model
    ), "the packaged example registry is expected to carry example/ aliases"

    for assignment in _project(host).env_assignments:
        monkeypatch.setenv(assignment.name, assignment.value)
    pinned = load_personas(resolve_default_registry_path())
    assert pinned, "the pinned registry must resolve the operator's own personas"
    assert not any(
        is_example_alias(persona.model) for persona in pinned.values() if persona.model
    )


# ---------------------------------------------------------------------------
# T013 [US2-S1] R6: the engine's own Temporal database, under the state root
# ---------------------------------------------------------------------------


def test_env_pins_the_engines_own_temporal_database(host: _Host) -> None:
    from factory.supervision.container_supervisor import DEFAULT_DB_FILENAME
    from factory.supervision.units import resolve_layout

    project = _project(host)
    pinned = _env_map(project)["ERGANE_TEMPORAL_DB_FILENAME"]
    expected = resolve_state_home() / "ergane" / "temporal" / "engine.db"
    assert pinned == str(expected)

    # Not the supervisor's landed default: nothing mounts /var/lib/ergane and the
    # Dockerfile never creates it (findings failure mode 5).
    assert pinned != DEFAULT_DB_FILENAME
    # Not the native managed unit's file either (`units.py:500`): two Temporal
    # servers on one SQLite file is the corruption hazard findings §3 prevents.
    assert pinned != str(resolve_layout().temporal_db_path)
    assert Path(pinned).name != "dev.db"


def test_the_temporal_database_is_covered_by_the_state_root_mount(host: _Host) -> None:
    """The covering mount is the state root; the supervision home is a sibling."""
    project = _project(host)
    pinned = Path(_env_map(project)["ERGANE_TEMPORAL_DB_FILENAME"])

    assert pinned.is_relative_to(host.state_root)
    assert not pinned.is_relative_to(supervision_home())
    assert any(Path(mount.source) == host.state_root for mount in project.mounts)


# ---------------------------------------------------------------------------
# T014 [US2-S1] Trap 4: refuse at generation time what no mount covers
# ---------------------------------------------------------------------------


def test_a_mount_outside_every_declared_root_is_refused_naming_the_path(
    host: _Host,
) -> None:
    project = _project(host)
    stray = Path("/var/lib/ergane")
    with pytest.raises(OperatorError) as error:
        dataclasses.replace(
            project, mounts=project.mounts + (cp.Mount(str(stray), str(stray)),)
        )
    assert str(stray) in str(error.value)


def test_a_non_same_path_bind_is_refused_naming_the_path(host: _Host) -> None:
    project = _project(host)
    source = host.repos[0]
    with pytest.raises(OperatorError) as error:
        dataclasses.replace(
            project, mounts=project.mounts + (cp.Mount(str(source), "/mnt/repo"),)
        )
    message = str(error.value)
    assert str(source) in message and "same-path" in message


def test_an_env_path_outside_every_declared_root_is_refused(host: _Host) -> None:
    """The guard is what would have caught R6's `/var/lib/ergane` before it shipped."""
    project = _project(host)
    with pytest.raises(OperatorError) as error:
        dataclasses.replace(
            project,
            env_assignments=project.env_assignments
            + (
                cp.EnvAssignment(
                    "ERGANE_TEMPORAL_DB_FILENAME",
                    "/var/lib/ergane/temporal.sqlite",
                    cp.ENV_PATH,
                ),
            ),
        )
    assert "/var/lib/ergane/temporal.sqlite" in str(error.value)


def test_every_bind_is_same_path_and_no_named_volume_is_declared(host: _Host) -> None:
    compose = yaml.safe_load(cp.render_compose(_project(host)))
    for entry in _binds(compose):
        source, _, target = entry.partition(":")
        assert source == target, f"bind must be same-path, got {entry!r}"
        assert source.startswith("/"), f"bind source must be an absolute path: {entry!r}"
    assert "volumes" not in compose, "no top-level named volumes (trap 4)"


def test_the_database_path_passes_the_guard_through_the_state_root_mount(
    host: _Host,
) -> None:
    """The declared roots are the project's own mount set, so R6's path is legal."""
    project = _project(host)
    assert host.state_root in project.roots
    assert supervision_home() in project.roots
    assert host.config_dir in project.roots
    for repo in host.repos:
        assert repo in project.roots


# ---------------------------------------------------------------------------
# T015 [US2-S1] R7/R10: the image reference is derived, never guessed
# ---------------------------------------------------------------------------


def test_the_image_version_is_derived_through_module_private_helpers() -> None:
    """Spec 105 claims the public vocabulary; 104 keeps its derivation private."""
    import importlib.metadata

    assert cp._engine_image_version() == importlib.metadata.version("ergane-cli")
    public = {name for name in vars(cp) if not name.startswith("_")}
    assert not {"cli_version", "IMAGE_REPOSITORY", "image_reference"} & public, (
        "spec 105 owns that vocabulary; 104 must not create a second public "
        f"version module (found {sorted(public)})"
    )


def test_registry_source_emits_an_image_only_and_local_source_adds_a_build(
    host: _Host,
) -> None:
    registry_project = _project(host, image_source=cp.IMAGE_SOURCE_REGISTRY)
    service = yaml.safe_load(cp.render_compose(registry_project))["services"]["ergane"]
    assert "build" not in service
    assert service["image"].startswith(cp._IMAGE_REPOSITORY + ":")

    local_project = _project(host, image_source=cp.IMAGE_SOURCE_LOCAL)
    service = yaml.safe_load(cp.render_compose(local_project))["services"]["ergane"]
    assert service["build"] == {
        "context": str(host.install_root),
        "dockerfile": "Dockerfile",
    }
    assert service["image"] == f"{cp._LOCAL_IMAGE_REPOSITORY}:{cp._engine_image_version()}"


def test_local_source_is_the_default_until_105_lands(host: _Host) -> None:
    signature = inspect.signature(cp.resolve_project)
    assert signature.parameters["image_source"].default == cp.IMAGE_SOURCE_LOCAL


def test_a_failed_version_derivation_refuses_rather_than_guessing_a_tag(
    host: _Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.metadata

    def _absent(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(cp, "_distribution_version", _absent)
    with pytest.raises(OperatorError) as error:
        _project(host)
    assert "ergane-cli" in str(error.value)


def test_local_source_refuses_by_name_when_there_is_no_build_context(
    host: _Host, tmp_path: Path
) -> None:
    """R10: a wheel install has no repository, so `COPY . /opt/ergane` has nothing."""
    wheel_root = tmp_path / "site-packages"
    wheel_root.mkdir()
    with pytest.raises(OperatorError) as error:
        _project(host, install_root=wheel_root, image_source=cp.IMAGE_SOURCE_LOCAL)
    message = str(error.value)
    assert "Dockerfile" in message
    assert "wheel" in message
    assert "105" in message

    # The registry source needs no build context and is unaffected.
    _project(host, install_root=wheel_root, image_source=cp.IMAGE_SOURCE_REGISTRY)


# ---------------------------------------------------------------------------
# T016 [US2-S1] R10 packaging: the confinement artifacts ship in the wheel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("artifact", ["seccomp-ergane.json", "ergane-engine.profile"])
def test_confinement_artifact_text_equals_the_committed_file(artifact: str) -> None:
    assert cp.confinement_artifact_text(artifact) == confinement_committed(artifact)


def test_package_data_is_consulted_before_the_checkout_walk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordering `factory/config.py:98-101` exists to fix: a wheel has no repo
    above it, so `importlib.resources` must win."""

    class _Packaged:
        def is_file(self) -> bool:
            return True

        def read_text(self, encoding: str = "utf-8") -> str:
            return "PACKAGED"

    monkeypatch.setattr(cp, "_packaged_artifact", lambda name: _Packaged())
    assert cp.confinement_artifact_text(cp.SECCOMP_ARTIFACT) == "PACKAGED"


def test_the_wheel_mapping_exists_in_pyproject() -> None:
    """A dropped force-include fails here, not at an operator's first install."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    table = data["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    for artifact in (cp.SECCOMP_ARTIFACT, cp.APPARMOR_ARTIFACT):
        assert table[f"container/{artifact}"] == f"factory/container/{artifact}"


def test_the_artifacts_are_copied_beside_the_generated_compose(host: _Host) -> None:
    """`security_opt`'s relative `./seccomp-ergane.json` resolves beside compose.yaml."""
    project = _project(host)
    files = {generated.name: generated for generated in cp.project_files(project)}
    for artifact in (cp.SECCOMP_ARTIFACT, cp.APPARMOR_ARTIFACT):
        assert files[artifact].text == confinement_committed(artifact)
        assert files[artifact].directory == files["compose.yaml"].directory
    service = yaml.safe_load(cp.render_compose(project))["services"]["ergane"]
    assert f"seccomp:./{cp.SECCOMP_ARTIFACT}" in service["security_opt"]


def confinement_committed(artifact: str) -> str:
    return (REPO_ROOT / "container" / artifact).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# T017 [US2-S3] Trap 9: config F is unreachable from the reference render
# ---------------------------------------------------------------------------


def test_the_reference_render_carries_no_unconfined_token() -> None:
    """`tests/test_088_us3_container_drift.py:380` bans the token in the committed
    file; the render that claims to agree with it must be held to the same bar."""
    assert "unconfined" not in cp.render_compose(cp.reference_project()).lower()


def test_reference_project_takes_no_parameters_so_no_variant_reaches_it() -> None:
    """Structurally unreachable, not merely untaken.

    A parameter that merely *defaults* to the shipped confinement leaves a
    committed test one wrong default away from red on a file nobody edited.
    """
    assert inspect.signature(cp.reference_project).parameters == {}
    project = cp.reference_project()
    assert project.security_opt == cp.CONFINED_SECURITY_OPT
    assert f"apparmor={cp.APPARMOR_PROFILE_NAME}" in project.security_opt


# ---------------------------------------------------------------------------
# T018 [US2-S2] Determinism: the render is a function of the project data alone
# ---------------------------------------------------------------------------


def test_rendering_the_same_project_twice_is_identical(host: _Host) -> None:
    project = _project(host)
    assert cp.render_compose(project) == cp.render_compose(project)
    assert cp.render_env(project) == cp.render_env(project)
    assert cp.render_compose(cp.reference_project()) == cp.render_compose(
        cp.reference_project()
    )


def test_the_render_reads_neither_the_clock_nor_the_environment(
    host: _Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolution happens once, in `resolve_project`; the renderer is pure.

    Moving the whole environment out from under a project that has already been
    resolved may not change one byte of its render.
    """
    project = _project(host)
    before = cp.render_compose(project), cp.render_env(project)

    monkeypatch.setenv("ERGANE_STATE_HOME", "/somewhere/else")
    monkeypatch.setenv("HOME", "/nobody")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/nobody/.config")
    monkeypatch.setattr(os, "getuid", lambda: 4242)

    assert (cp.render_compose(project), cp.render_env(project)) == before


def test_two_resolutions_of_one_host_render_identically(host: _Host) -> None:
    """US2-S2 stated end to end: same inputs twice, same text."""
    assert cp.render_compose(_project(host)) == cp.render_compose(_project(host))
    assert cp.render_env(_project(host)) == cp.render_env(_project(host))
