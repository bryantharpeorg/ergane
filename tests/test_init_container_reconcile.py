"""104-US6: `ergane init .` regenerates the mount list and reconciles the engine.

*The engine container* is the Docker container `ergane install` brings up —
never bwrap's sandbox, never "a container of specs".

A repo joined after the engine came up is registered and not mounted, and the
supervisor's same-path check (088 FR-009) refuses on exactly that state. US6's
claim is that the operator never has to know: `ergane init .` stays one command,
and the engine picks the repo up.

**Seam capture** (traps 11 and 14): the project writer (`_project_writer`) and
the compose runner (`_compose_runner`) are injected, so no Docker daemon is
contacted and no container is started. `bind_offline_seams` closes the forge,
the control plane and the schedule server for the same reason. The generated
compose these tests read back is written to `tmp_path` by the real renderer.

The host is relocated off `~` deliberately (trap 5): config and personas share
one `~/.config/ergane` because the project mounts the config *directory*, and a
state home copied from the reference rather than resolved could not pass the
mount guard here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

import pytest
import yaml

import factory.cli.init as init_module
from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.config import shipped_registry_text
from factory.controlplane.config import load_controlplane_config
from factory.supervision.container_manifest import (
    InstalledProject,
    installed_project,
    write_project,
)
from factory.supervision.container_project import (
    COMPOSE_NAME,
    CONFINEMENT_UNCONFINED,
    REPO_MOUNT_KEY,
    SERVICE_NAME,
    resolve_project,
)
from factory.supervision.units import CommandResult

from tests.test_ergane_init import ScriptedPrompter, _git, _invoke
from tests.test_ergane_init_check import bind_offline_seams

SLUG = "widgets"


# --- The host -----------------------------------------------------------------


@pytest.fixture
def engine_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch host shaped like one that ran `ergane install --engine=container`.

    Every path the generated project names has to be covered by one of the
    project's own mounts (trap 4), which is why HOME, the config directory, the
    persona registry and the state home are relocated together rather than
    piecemeal: `~/.config/ergane` under HOME, and the personas file inside it.
    """
    home = tmp_path / "home"
    config_dir = home / ".config" / "ergane"
    state_home = tmp_path / "state"
    for directory in (config_dir, state_home / "ergane"):
        directory.mkdir(parents=True, exist_ok=True)
    # A real persona registry beside the config, as `ergane install` leaves one.
    # Without it `resolve_default_registry_path` reaches the *packaged example*
    # (trap 3) — which lives outside every mount, so the project would refuse to
    # resolve and every test here would fail for a reason that is not its claim.
    (config_dir / "personas.yaml").write_text(shipped_registry_text(), encoding="utf-8")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state_home))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    for name in ("ERGANE_CONFIG_PATH", "FACTORY_CONFIG_PATH"):
        monkeypatch.setenv(name, str(config_dir / "config.toml"))
    for name in ("ERGANE_PERSONAS_PATH", "FACTORY_PERSONAS_PATH"):
        monkeypatch.setenv(name, str(config_dir / "personas.yaml"))
    return state_home


@pytest.fixture
def floor(engine_host: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every outward seam bound. Ordered after `engine_host` so the offline
    control-plane config it writes lands in *this* host's config directory —
    the one the project mounts."""
    bind_offline_seams(monkeypatch)


class Compose:
    """The compose runner seam, recording every argv it was handed."""

    def __init__(self, code: int = 0, out: str = "") -> None:
        self.argv: list[tuple[str, ...]] = []
        self.result = CommandResult(code, out)

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        self.argv.append(tuple(argv))
        return self.result

    @property
    def verbs(self) -> list[str]:
        return [argv[4] for argv in self.argv if len(argv) > 4]


@pytest.fixture
def compose(monkeypatch: pytest.MonkeyPatch) -> Compose:
    runner = Compose()
    monkeypatch.setattr(init_module, "_compose_runner", runner)
    return runner


@pytest.fixture
def writes(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The writer seam, recording the projects handed to it and still writing —
    a recorder rather than a no-op, because what the mount list *became* is the
    claim and a stubbed writer could not be asked."""
    seen: list[Any] = []

    def record(project: Any) -> Any:
        seen.append(project)
        return write_project(project)

    monkeypatch.setattr(init_module, "_project_writer", record)
    return seen


# --- Repos and the planted project --------------------------------------------


def make_repo(tmp_path: Path, name: str) -> Path:
    """A git repo with one commit and no Ergane presence at all."""
    repo = tmp_path / name
    (repo / "specs").mkdir(parents=True)
    _git(repo, "init", "-b", "main", "--quiet")
    (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")
    return repo


def plant_project(**kwargs: Any) -> InstalledProject:
    """Write the project this host would have had after `ergane install`.

    Resolved from the live registry, so planting *before* a repo is registered
    is what produces the state US6 is about: an engine that is up and does not
    mount the repo the operator is joining.
    """
    write_project(resolve_project(load_controlplane_config(), **kwargs))
    installed = installed_project()
    assert installed is not None
    return installed


def repo_mounts(compose_path: Path) -> list[tuple[str, str]]:
    """The `x-ergane-repos` list as the engine would read it back."""
    document = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    return [(m["source"], m["target"]) for m in document[REPO_MOUNT_KEY] or ()]


def run_init(
    monkeypatch: pytest.MonkeyPatch, repo: Path, *, slug: str = SLUG
) -> Any:
    """A full `ergane init <repo>`, scripting the interview in key order."""
    answers = [
        "1", "bwrap", 'test: "uv run pytest -q"', "", "", "main", "", "", "", "", "",
        slug,
    ]
    monkeypatch.setattr(
        init_module, "_prompter_factory", lambda: ScriptedPrompter(answers)
    )
    return _invoke(["init", str(repo)])


# --- T047 (US6-S1): the mount list is regenerated and the engine reconciled ----


def test_init_adds_the_new_repo_to_the_mount_list_and_reups_the_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: None,
    compose: Compose,
    writes: list[Any],
) -> None:
    """US6-S1: one command; the repo lands at its own path and the engine is up."""
    first = make_repo(tmp_path, "alpha")
    registry.register("alpha", first)
    installed = plant_project()
    assert repo_mounts(installed.compose_path) == [(str(first), str(first))]

    joining = make_repo(tmp_path, "widgets")
    run = run_init(monkeypatch, joining)

    assert run.code == EXIT_OK, run.stdout + run.stderr

    # Regenerated: both repos, each at its own path on both sides of the bind.
    assert repo_mounts(installed.compose_path) == [
        (str(first), str(first)),
        (str(joining), str(joining)),
    ]
    assert len(writes) == 1

    # Reconciled: `up -d` against the project just regenerated, and nothing else.
    assert compose.argv == [
        ("docker", "compose", "-f", str(installed.compose_path), "up", "-d")
    ]
    assert not [v for v in compose.verbs if v in ("down", "stop", "rm", "kill")]


def test_the_reconcile_is_reported_as_one_line_beside_the_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: None,
    compose: Compose,
    writes: list[Any],
) -> None:
    """US6-S1: it is reported where an operator already reads what init did.

    Beside the registry line rather than in a section of its own: the mount and
    the registry row are two halves of one fact — the engine knowing this repo
    exists — and an operator who reads one has read the other.
    """
    joining = make_repo(tmp_path, "widgets")
    plant_project()

    run = run_init(monkeypatch, joining)

    assert run.code == EXIT_OK, run.stdout + run.stderr
    lines = run.stdout.splitlines()
    registered = next(i for i, line in enumerate(lines) if line.startswith("registered:"))
    reconciled = lines[registered + 1]

    assert reconciled.startswith("engine container:")
    assert str(joining) in reconciled
    # One line, not a block: the next line is the step that follows registration.
    assert not lines[registered + 2].startswith("engine container")


def test_a_hand_edited_project_is_reported_rather_than_silently_not_regenerated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: None,
    compose: Compose,
    writes: list[Any],
) -> None:
    """The writer refuses to overwrite an operator's edit (US3), and a line
    claiming the repo was mounted would then be false — the engine would come up
    without it and fail at the first dispatch, hours later."""
    joining = make_repo(tmp_path, "widgets")
    installed = plant_project()
    installed.compose_path.write_text("# mine now\nservices: {}\n", encoding="utf-8")

    run = run_init(monkeypatch, joining)

    assert run.code == EXIT_OK, run.stdout + run.stderr
    assert installed.compose_path.read_text(encoding="utf-8") == "# mine now\nservices: {}\n"
    line = next(l for l in run.stdout.splitlines() if l.startswith("engine container:"))
    assert COMPOSE_NAME in line
    assert "ergane install" in line


def test_the_declined_confinement_survives_a_reconcile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: None,
    compose: Compose,
    writes: list[Any],
) -> None:
    """A config-F host stays config F.

    Regenerating as config G would ask Docker for an AppArmor profile this host
    never loaded, and the engine an `ergane init` was supposed to reconcile
    would refuse to start instead (trap 8: F is a real state, not a mistake to
    be corrected behind the operator's back).
    """
    joining = make_repo(tmp_path, "widgets")
    installed = plant_project(confinement=CONFINEMENT_UNCONFINED)

    run = run_init(monkeypatch, joining)

    assert run.code == EXIT_OK, run.stdout + run.stderr
    document = yaml.safe_load(installed.compose_path.read_text(encoding="utf-8"))
    assert "apparmor=unconfined" in document["services"][SERVICE_NAME]["security_opt"]
    # And it really was regenerated, F and all.
    assert repo_mounts(installed.compose_path) == [(str(joining), str(joining))]


# --- T047 (US6-S1): the systemd-tier host is untouched -------------------------


def test_a_host_with_no_project_regenerates_nothing_and_says_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: None,
    compose: Compose,
    writes: list[Any],
) -> None:
    """`installed_project()` is `None`, so the container tier is not this host's
    (R1) — and a tier an operator does not run is not one init reports on."""
    joining = make_repo(tmp_path, "widgets")
    assert installed_project() is None

    run = run_init(monkeypatch, joining)

    assert run.code == EXIT_OK, run.stdout + run.stderr
    assert writes == []
    assert compose.argv == []
    assert "engine container" not in run.stdout
    assert installed_project() is None


# --- T048 (US6-S1): the check reports it as a finding --------------------------


def findings(stdout: str, name: str) -> list[str]:
    return [line for line in stdout.splitlines() if f"] {name}:" in line]


def test_check_fails_when_the_engine_does_not_mount_this_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: None
) -> None:
    """US6-S1, through `--check`: a registered repo the engine cannot see is a
    finding on the surface an operator already scans, naming the verb that fixes
    it — not a new output surface, and not a discovery made at dispatch."""
    joining = make_repo(tmp_path, "widgets")
    plant_project()  # the engine came up before this repo joined...
    registry.register(SLUG, joining)  # ...and nothing has regenerated it since

    run = _invoke(["init", "--check", str(joining)])

    assert run.code == EXIT_USER
    line = findings(run.stdout, "engine_container")
    assert len(line) == 1
    assert line[0].startswith("  [FAIL]")
    assert f"`ergane init {joining.resolve()}`" in line[0]


def test_check_passes_once_init_has_reconciled_the_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: None,
    compose: Compose,
    writes: list[Any],
) -> None:
    """The same finding, after the same command — which is what makes it a
    remedy an operator can act on rather than a description of their host."""
    joining = make_repo(tmp_path, "widgets")
    plant_project()

    assert run_init(monkeypatch, joining).code == EXIT_OK

    run = _invoke(["init", "--check", str(joining)])
    line = findings(run.stdout, "engine_container")
    assert len(line) == 1
    assert line[0].startswith("  [PASS]")
    assert str(joining.resolve()) in line[0]


def test_check_on_a_host_with_no_project_renders_no_engine_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: None
) -> None:
    """Absent rather than passing: a host that does not run the container tier
    has not satisfied a container requirement, it has no container requirement —
    and a `[PASS] engine_container` line would teach it to expect one."""
    joining = make_repo(tmp_path, "widgets")
    registry.register(SLUG, joining)

    run = _invoke(["init", "--check", str(joining)])

    assert findings(run.stdout, "engine_container") == []


def test_check_reports_an_unreadable_project_rather_than_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: None
) -> None:
    """A gathering step that raises would abort the whole report — exactly the
    failure masking `--check` forbids. It is a failing finding instead."""
    joining = make_repo(tmp_path, "widgets")
    installed = plant_project()
    registry.register(SLUG, joining)
    installed.compose_path.write_text("services: [this is not a mapping\n", encoding="utf-8")

    run = _invoke(["init", "--check", str(joining)])

    line = findings(run.stdout, "engine_container")
    assert len(line) == 1
    assert line[0].startswith("  [FAIL]")
    # And every other finding still rendered.
    assert findings(run.stdout, "registry_entry")


# --- The seams are closed ------------------------------------------------------


def test_no_test_here_reaches_a_real_docker_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: None, writes: list[Any]
) -> None:
    """Trap 11, made structural: the default runner is what a real bring-up would
    spawn, so a path that stopped going through the seam is caught here rather
    than by a container appearing on the operator's host."""
    detonated: list[str] = []

    def detonate(argv: Sequence[str]) -> CommandResult:
        detonated.append(" ".join(argv))
        raise AssertionError(f"a test reached the real compose runner: {argv}")

    monkeypatch.setattr(init_module, "_compose_runner", detonate)
    joining = make_repo(tmp_path, "widgets")

    # No project on this host, so nothing may be run at all.
    assert run_init(monkeypatch, joining).code == EXIT_OK
    assert detonated == []
