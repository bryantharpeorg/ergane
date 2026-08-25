"""104 US7: `ergane uninstall` unplugs the engine container, and nothing else.

**Every test here is a seam capture** (plan trap 14). No Docker daemon exists in
this environment and none is contacted: the `down` goes through
`TeardownRequest.run` — the seam `uninstall()` already had and teardown already
carries — and the step table itself is replaced wholesale where a `--check` needs
to prove it reached no acting half. Nothing below starts a container, and
`apparmor_parser` is never named.

Three things are easy to build vacuously here, so each is written with the thing
that proves it is not:

- **"removes what install generated — and nothing else"** is provenance by
  digest, not a filename allow-list (`container_manifest.py`'s whole reason to
  exist). So the removal tests put a file the operator wrote *inside the project
  directory* and read it back afterwards, rather than only asserting that the
  four generated names are gone.
- **Bring-down may not require what bring-up requires** (trap 13). The
  unreachable-daemon test injects a runner that *raises* `FileNotFoundError` —
  `docker` not on PATH, the realistic shape — and asserts teardown reported it
  and still removed the files the manifest records. A test that only asserted
  "no exception escaped" would pass on a step that gave up.
- **The FR-018 guard sees the project directory before any step acts.** Asserted
  by making that directory contain the install root and reading the refusal, not
  by inspecting `removal_targets` as an attribute: a target the guard is never
  handed is a target that does not bound anything.

Pasted evidence (constitution VIII / D-037) is in
`docs/104-us7-teardown-transcript.md`, which is a seam capture and says so.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Sequence

import pytest

from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.cli.uninstall import (
    CLEAR_STATE,
    STOP_AND_REMOVE_UNITS,
    STOP_ENGINE_CONTAINER,
)
from factory.supervision import container_manifest as cm
from factory.supervision import container_project as cp
from factory.supervision.units import CommandResult, InstallLayout

from tests.test_teardown_names_what_it_kept import (
    Seeded,
    _seed,
    block_of,
    kept_in,
    labelled,
    plan_of,
    removed_in,
)
from tests.test_teardown_owns_the_ordering import drive, plan_lines

#: What the operator wrote into the project directory themselves. Nothing
#: generated it, so nothing but `--purge` may remove it.
HAND_ADDED = "docker-compose.override.yaml"
HAND_ADDED_TEXT = "# my own override, please keep\nservices: {}\n"


def _project(layout: InstallLayout) -> cp.ContainerProject:
    """A minimal engine-container project rooted at this layout's project dir.

    Built here rather than through `resolve_project` because what US7 is about is
    the *manifest*: the renderer's own agreement with the reference compose is
    US2's story and is asserted there. The four names are the real ones.
    """
    directory = cp.project_dir(layout)
    return cp.ContainerProject(
        image="ergane-local:0.3.0",
        build=None,
        security_opt=("no-new-privileges:true",),
        user="1000:1000",
        roots=(directory,),
        mounts=(),
        repo_mounts=(),
        environment=("ERGANE_STATE_HOME",),
        env_assignments=(cp.EnvAssignment("TEMPORAL_ADDRESS", "127.0.0.1:7233"),),
        ports=("127.0.0.1:7233:7233",),
        directory=directory,
    )


def _install_project(layout: InstallLayout, *, hand_added: bool = False) -> Path:
    """Write the project the way `ergane install` does, through US3's writer."""
    directory = cm.write_project(_project(layout)).directory
    if hand_added:
        (directory / HAND_ADDED).write_text(HAND_ADDED_TEXT, encoding="utf-8")
    return directory


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Seeded:
    """083-US4's fully populated host, with an engine container project on it."""
    host = _seed(tmp_path, monkeypatch)
    _install_project(host.host.layout)
    return host


def project_of(seeded: Seeded) -> Path:
    return cp.project_dir(seeded.host.layout)


def down_calls(seeded: Seeded) -> list[tuple[str, ...]]:
    """Every `docker compose … down` the step issued, from the one event log."""
    return [
        tuple(event)
        for event in seeded.host.events
        if tuple(event)[:2] == ("docker", "compose") and "down" in tuple(event)
    ]


# -----------------------------------------------------------------------------
# T053 / US7-S1 — the engine goes down, the project goes, the rest stays
# -----------------------------------------------------------------------------


def test_the_step_takes_the_engine_down_and_removes_what_install_generated(
    seeded: Seeded,
) -> None:
    """US7-S1: down through the injected runner, then the four generated files.

    The state root and the config are read back afterwards rather than merely
    absent from the removal lines: "and nothing else" is a claim about files
    this step did not open, and only a read can make it.
    """
    directory = project_of(seeded)
    compose = directory / cp.COMPOSE_NAME
    assert compose.is_file(), "the fixture wrote no project"

    result = drive(seeded.host.request())

    assert result.code == EXIT_OK, result.stderr
    assert down_calls(seeded) == [
        ("docker", "compose", "-f", str(compose), "down")
    ], seeded.host.events

    # The generated project is gone, directory and all: nothing else was in it.
    assert not directory.exists()

    # …while the state root and the config are exactly as they were.
    assert (seeded.state_home / "doctor.db").read_text(encoding="utf-8") == "seeded\n"
    assert seeded.config.is_file()
    assert seeded.secret.is_file()

    block = block_of(result, STOP_ENGINE_CONTAINER)
    for name in (cp.COMPOSE_NAME, cp.ENV_NAME, cp.SECCOMP_ARTIFACT, cp.APPARMOR_ARTIFACT):
        assert removed_in(block, directory / name), f"{name} is on no removed line of {block}"
    # FR-013's symmetry: the step says what it did *not* touch, in the same block
    # and with the same width of claim as what it did.
    assert kept_in(block, seeded.state_home)
    assert kept_in(block, seeded.config)


def test_a_file_the_operator_wrote_into_the_project_directory_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US7-S1, the control: provenance is a digest, not a filename allow-list.

    A file the manifest never claimed is the operator's, and the directory that
    still holds it is not teardown's to remove either. Its bytes are read back,
    because "survives" is a claim about content and not about a directory entry.
    """
    seeded = _seed(tmp_path, monkeypatch)
    directory = _install_project(seeded.host.layout, hand_added=True)

    result = drive(seeded.host.request())

    assert result.code == EXIT_OK, result.stderr
    assert (directory / HAND_ADDED).read_text(encoding="utf-8") == HAND_ADDED_TEXT
    assert directory.is_dir(), "the directory holding it was removed anyway"
    assert not (directory / cp.COMPOSE_NAME).exists()

    block = block_of(result, STOP_ENGINE_CONTAINER)
    assert kept_in(block, directory / HAND_ADDED)
    assert removed_in(block, directory / cp.COMPOSE_NAME)
    # The directory wears a label too: a project directory that survives is a
    # fact about the host, and silence is how 083's field report went wrong.
    assert kept_in(block, directory)


def test_a_host_with_no_engine_container_project_says_so_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-011 for the new step: the systemd-only host is the common one.

    Nothing to do, said by name — and no `docker` command issued, which is the
    half that matters: a teardown that shells out to a daemon that is not there
    on every host is a regression for every operator who never chose the
    container tier.
    """
    seeded = _seed(tmp_path, monkeypatch)

    result = drive(seeded.host.request())

    assert result.code == EXIT_OK, result.stderr
    assert "nothing to do:" in plan_of(result, STOP_ENGINE_CONTAINER)
    assert down_calls(seeded) == [], seeded.host.events


# -----------------------------------------------------------------------------
# T054 / US7-S1, FR-010 — `--check` performs none of it
# -----------------------------------------------------------------------------


def test_check_names_the_engine_and_the_files_and_performs_nothing(
    seeded: Seeded,
) -> None:
    """US7-S1: the survey/perform split at `factory/cli/uninstall.py:130` and
    `:158` already makes this conclusive — the acting half is unreachable on the
    `--check` path — so what is asserted here is the *other* obligation: that
    the read-only half named the engine and every file it would remove.
    """
    directory = project_of(seeded)
    before = sorted(path.name for path in directory.iterdir())

    result = drive(seeded.host.request(check=True))

    assert result.code == EXIT_OK, result.stderr

    plan = plan_of(result, STOP_ENGINE_CONTAINER)
    assert "engine container" in plan
    assert str(directory) in plan
    for name in (cp.COMPOSE_NAME, cp.ENV_NAME, cp.SECCOMP_ARTIFACT, cp.APPARMOR_ARTIFACT):
        assert name in plan, plan

    # Nothing ran and nothing moved.
    assert seeded.host.events == [], seeded.host.events
    assert sorted(path.name for path in directory.iterdir()) == before
    assert json.loads((directory / cm.MANIFEST_NAME).read_text(encoding="utf-8"))["files"]
    assert "nothing was written, removed, stopped or signalled" in result.stdout


# -----------------------------------------------------------------------------
# T055 / US7-S2, FR-013 — purge extends to the generated artifacts
# -----------------------------------------------------------------------------


def test_purge_extends_to_the_generated_artifacts_and_names_every_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US7-S2: what the digest rule kept on a bare run, `--purge` takes and names.

    The bare run above left the operator's file and the directory holding it.
    `--purge` is the operator saying they want the host emptied — and the step
    that follows would take the whole supervision home regardless, as one
    `shutil.rmtree` naming nothing. So the extension is not "delete more" so much
    as *name* it, one line per path, in 083's own grammar.
    """
    seeded = _seed(tmp_path, monkeypatch)
    directory = _install_project(seeded.host.layout, hand_added=True)

    result = drive(seeded.host.request(purge=True))

    assert result.code == EXIT_OK, result.stderr
    assert not directory.exists()

    block = block_of(result, STOP_ENGINE_CONTAINER)
    for name in (
        cp.COMPOSE_NAME,
        cp.ENV_NAME,
        cp.SECCOMP_ARTIFACT,
        cp.APPARMOR_ARTIFACT,
        HAND_ADDED,
    ):
        assert removed_in(block, directory / name), f"{name} is on no removed line of {block}"
    assert removed_in(block, directory), "the directory itself was removed but not named"

    # …and the same block still says what purge did *not* reach: the config is
    # kept on every path there is, purge included (083 US4's judgement, unchanged).
    assert kept_in(block, seeded.config)
    assert seeded.config.is_file()
    assert seeded.secret.is_file()

    removed = labelled(block, "removed")
    kept = labelled(block, "kept")
    assert removed and kept, block
    assert not {line.split()[1] for line in removed} & {line.split()[1] for line in kept}

    # The purge run and the bare run agree about the config: the step after this
    # one still keeps it, and this one did not quietly take it first.
    assert kept_in(block_of(result, CLEAR_STATE), seeded.config)


def test_the_fr018_guard_sees_the_project_directory_before_any_step_acts(
    seeded: Seeded,
) -> None:
    """T055's second half: `removal_targets` is wired, proven by the refusal.

    The guard runs over every step's `removal_targets` *before* the loop starts
    (`factory/cli/uninstall.py:725`), so a project directory containing the
    installation this process runs from must stop the verb with nothing done —
    not at step three, and not after dispatch has already been paused.
    """
    directory = project_of(seeded)
    request = seeded.host.request(
        layout=replace(seeded.host.layout, install_root=directory / "us7")
    )

    result = drive(request)

    assert result.code == EXIT_USER
    assert f"step {STOP_ENGINE_CONTAINER!r} would remove {directory}" in result.stderr
    assert "the installation this process is running from" in result.stderr

    # Refused before anything acted: nothing paused, nothing forgotten, nothing
    # removed — and the engine was never asked to come down.
    assert seeded.host.events == []
    assert (directory / cp.COMPOSE_NAME).is_file()
    assert seeded.host.schedules.schedules != {}


# -----------------------------------------------------------------------------
# T056 / US7-S1 — trap 13: bring-down may not require what bring-up requires
# -----------------------------------------------------------------------------


def _refusing_runner(seeded: Seeded, failure: Exception):
    """A runner that answers systemd and raises for `docker` — the real asymmetry.

    `uninstall()`'s own systemd commands go through the same seam, so a runner
    that raised at everything would prove nothing about the engine step.
    """
    record = seeded.host.runner()

    def run(argv: Sequence[str]) -> CommandResult:
        if tuple(argv)[:1] == ("docker",):
            record(argv)
            raise failure
        return record(argv)

    return run


def test_an_unreachable_daemon_is_reported_and_the_files_still_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US7-S1 / trap 13: `docker` is not on PATH, and teardown finishes anyway.

    `factory/cli/nouns/worker.py:30` refuses three verbs without a systemd user
    session and `_uninstall` (`:49`) deliberately does not call it — removal must
    work everywhere. The same asymmetry: the recorded manifest still says what to
    remove, so a host whose daemon has gone away is *reported on*, not refused.
    """
    seeded = _seed(tmp_path, monkeypatch)
    directory = _install_project(seeded.host.layout)

    result = drive(
        seeded.host.request(
            run=_refusing_runner(seeded, FileNotFoundError(2, "No such file", "docker"))
        )
    )

    assert result.code == EXIT_OK, result.stderr
    assert down_calls(seeded) != [], "the step never tried"

    block = block_of(result, STOP_ENGINE_CONTAINER)
    reported = [line for line in block if "could not" in line]
    assert reported, block
    assert "docker" in " ".join(reported)

    # It removed what it could: the manifest is the record, and it did not need
    # the daemon to read it.
    assert not directory.exists()
    assert removed_in(block, directory / cp.COMPOSE_NAME)


def test_a_daemon_that_answers_nonzero_is_reported_the_same_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of trap 13: the daemon is there and says no.

    A stopped daemon raises; a daemon that refuses the project exits non-zero,
    and teardown may not read one as fatal and the other as fine.
    """
    seeded = _seed(tmp_path, monkeypatch)
    directory = _install_project(seeded.host.layout)
    events = seeded.host.events

    def run(argv: Sequence[str]) -> CommandResult:
        events.append(tuple(argv))
        if tuple(argv)[:1] == ("docker",):
            return CommandResult(1, "Cannot connect to the Docker daemon\n")
        return CommandResult(0, "")

    result = drive(seeded.host.request(run=run))

    assert result.code == EXIT_OK, result.stderr
    block = block_of(result, STOP_ENGINE_CONTAINER)
    assert [line for line in block if "Cannot connect to the Docker daemon" in line], block
    assert not directory.exists()


# -----------------------------------------------------------------------------
# R9 — where the step sits, and why
# -----------------------------------------------------------------------------


def test_the_engine_comes_down_before_the_units_and_before_the_state_goes(
    seeded: Seeded,
) -> None:
    """R9: dispatch is paused first, repositories forgotten second, and the engine
    is down before `clear state` could remove anything it is writing.

    Asserted on the acts in the one shared event log, not on the printed order:
    the sentences are what the table says, and the log is what happened.
    """
    result = drive(seeded.host.request(purge=True))

    assert result.code == EXIT_OK, result.stderr
    verbs = [tuple(event) for event in seeded.host.events]
    downed = next(i for i, event in enumerate(verbs) if event[:2] == ("docker", "compose"))
    stopped = next(
        i for i, event in enumerate(verbs) if event[:3] == ("systemctl", "--user", "disable")
    )
    paused = next(i for i, event in enumerate(verbs) if event[:1] == ("pause",))
    forgotten = next(i for i, event in enumerate(verbs) if event[:1] == ("delete",))
    assert paused < forgotten < downed < stopped

    assert f"3/6 {STOP_ENGINE_CONTAINER}" in result.stdout
    assert f"4/6 {STOP_AND_REMOVE_UNITS}" in result.stdout


def test_the_check_plan_and_the_performed_plan_still_come_from_one_table(
    seeded: Seeded,
) -> None:
    """FR-009 with six steps: `--check` cannot describe a sequence teardown does
    not perform, because both read `STEPS` — the property the insert must not
    break, asserted on a host that actually has an engine container to describe.
    """
    checked = drive(seeded.host.request(check=True))
    performed = drive(seeded.host.request())

    assert plan_lines(checked.stdout) == plan_lines(performed.stdout)
