"""119-US2: what a unit passes after the wrapper's three positionals reaches it.

The wrapper ends in `exec "${3:-<interpreter>}" -m "$1"`, so everything after
the third argument is discarded (spec N6b). Worker and bridge pass a module name
and nothing else, which is why nobody noticed; the Temporal unit passes
`--db-filename`, `--namespace` and `--log-level`, and all three vanish.

Nothing here asserts *about* the generated text. The wrapper is shell defaulting
under `set -eu` — the kind of thing that reads correctly and behaves otherwise —
so every test below writes the generated script to `tmp_path` and runs it with
`/bin/sh`, against stub interpreters that report which one of them ran, where it
started, what it received, and whether the operator's environment command was
evaluated first. `check=True` on every run: the wrong fix for this defect turns
an override into a working directory that does not exist, and a wrapper that
dies must fail a test rather than be read as passing nothing on.

The three tests are US2's three scenarios:

- S1 the Temporal unit's own argument list, which is the case that is broken.
- S2 the control — a module name alone, the path worker and bridge take.
- S3 the wrong-fix catcher. Replacing `-m "$1"` with `-m "$@"` is the obvious
  patch and it is wrong: `$2` and `$3` are the working directory and the
  interpreter, so the module would be handed both as flags (plan trap 1). The
  three positionals keep their meaning; only what follows them changes.

Written before T012, run against the wrapper as it stands. The two arguments
tests fail and the three controls pass, which is the shape this story wants:
what is broken is broken, and what must not change is already right.

    $ PYTHONDONTWRITEBYTECODE=1 uv run pytest -q \
    >     tests/test_119_wrapper_forwards_args.py --no-header --tb=line
    F...F                                                                  [100%]
    =================================== FAILURES ===================================
    E   AssertionError: assert ('-m', 'facto...poral_server') == ('-m', 'facto...'ergane', ...)

          Right contains 6 more items, first extra item: '--db-filename'
    .../tests/test_119_wrapper_forwards_args.py:163: AssertionError
    E   AssertionError: assert ('-m', 'factory.worker') == ('-m', 'facto...d', 'c0ffee1')

          Right contains 2 more items, first extra item: '--build-id'
    .../tests/test_119_wrapper_forwards_args.py:272: AssertionError
    2 failed, 3 passed in 0.21s

After T012, the same command: `..... [100%]`, 5 passed. And the wrong fix —
`-m "$@"` in place of the captured-and-consumed positionals — applied to
`factory/supervision/units.py` and reverted, with every `__pycache__` purged
first so no mutant runs the previous bytecode:

    F..FF                                                                  [100%]
    E   AssertionError: assert ('-m', 'facto.../dev.db', ...) == ('-m', 'facto...'ergane', ...)
          At index 2 diff: '/tmp/.../erg' != '--db-filename'
    E   AssertionError: assert ('-m', 'facto.../bin/python3') == ('-m', 'factory.worker')
          Left contains 2 more items, first extra item: '/tmp/.../deployments/c0ffee1/tree'

Three killed it, and the second failure is trap 1 exactly: the deployment root
arriving as the module's first flag, with the interpreter behind it.
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import pytest

from factory.supervision.units import (
    BRIDGE_UNIT,
    WORKER_TEMPLATE_UNIT,
    WRAPPER_NAME,
    InstallLayout,
    generated_files,
)

#: The operator's environment command, and the variable it exports. The wrapper
#: exists so this runs from a script rather than being resolved into
#: `Environment=` lines the journal echoes back, so every run below checks it
#: still happened — a fix to argument passing that stopped evaluating it would
#: have moved the credential path.
ENV_COMMAND = "echo export SOPS_PROBE=from-the-env-command"


@dataclasses.dataclass(frozen=True)
class Spoken:
    """What the stub that got exec'd reported about its own invocation."""

    who: str
    cwd: str
    secret: str
    arguments: tuple[str, ...]


def _stub(path: Path, who: str) -> Path:
    """An interpreter that answers instead of interpreting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'echo "who={who}"\n'
        'echo "cwd=$(pwd)"\n'
        'echo "secret=${SOPS_PROBE:-unset}"\n'
        'for argument in "$@"; do echo "arg=$argument"; done\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


@pytest.fixture
def installation(tmp_path: Path) -> Path:
    return tmp_path / "erg"


@pytest.fixture
def layout(installation: Path, tmp_path: Path) -> InstallLayout:
    """A managed installation: the mode whose unit passes arguments at all."""
    return InstallLayout(
        install_root=installation,
        interpreter=_stub(installation / ".venv/bin/python3", "installed"),
        unit_dir=tmp_path / "units",
        generated_dir=tmp_path / "state/ergane/supervision",
        env_command=ENV_COMMAND,
        temporal_mode="managed",
    )


@pytest.fixture
def wrapper(layout: InstallLayout, tmp_path: Path) -> Path:
    """The generated script itself, on disk and about to be run."""
    texts = {generated.name: generated.text for generated in generated_files(layout)}
    path = tmp_path / WRAPPER_NAME
    path.write_text(texts[WRAPPER_NAME], encoding="utf-8")
    return path


def run(wrapper: Path, *arguments: str) -> Spoken:
    """Run the wrapper as systemd would, and read back what the process got."""
    finished = subprocess.run(
        ["/bin/sh", str(wrapper), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )
    said = dict(
        line.split("=", 1)
        for line in finished.stdout.splitlines()
        if line.startswith(("who=", "cwd=", "secret="))
    )
    return Spoken(
        who=said["who"],
        cwd=said["cwd"],
        secret=said["secret"],
        arguments=tuple(
            line.removeprefix("arg=")
            for line in finished.stdout.splitlines()
            if line.startswith("arg=")
        ),
    )


# --- T009 [US2-S1 / FR-005] every argument after the positionals arrives ------


def test_a_unit_passing_flags_delivers_every_one_of_them(
    wrapper: Path, layout: InstallLayout, installation: Path
) -> None:
    """US2-S1: the Temporal unit's own three flags, all of them, in order.

    This is the defect in one assertion: today the module is exec'd as
    `-m "$1"` and these six words are dropped, so the managed server starts
    against a default database, a default namespace and a default log level —
    none of which is what the unit asked for.
    """
    spoken = run(
        wrapper,
        "factory.supervision.temporal_server",
        str(installation),
        str(layout.interpreter),
        "--db-filename",
        str(layout.temporal_db_path),
        "--namespace",
        "ergane",
        "--log-level",
        "warn",
    )

    assert spoken.arguments == (
        "-m",
        "factory.supervision.temporal_server",
        "--db-filename",
        str(layout.temporal_db_path),
        "--namespace",
        "ergane",
        "--log-level",
        "warn",
    )
    assert spoken.secret == "from-the-env-command"


# --- T010 [US2-S2 / FR-006] the control: a module name alone is untouched -----


def test_a_module_name_alone_behaves_exactly_as_today(
    wrapper: Path, installation: Path
) -> None:
    """US2-S2: the path worker and bridge take, unchanged in all four terms.

    The installed interpreter, the install root, the module and nothing else,
    and the environment command evaluated before any of it.
    """
    spoken = run(wrapper, "factory.notify.service")

    assert spoken.who == "installed"
    assert spoken.cwd == str(installation)
    assert spoken.arguments == ("-m", "factory.notify.service")
    assert spoken.secret == "from-the-env-command"


def test_no_generated_unit_passes_arguments_the_wrapper_did_not_take_before(
    layout: InstallLayout,
) -> None:
    """US2-S2: worker and bridge take the unchanged paths, and still do.

    The scenario's claim is about the units, not only about the script: the
    bridge passes a module name alone, and the worker template passes the three
    positionals 082-US2 gave it and stops there. Neither has a fourth argument,
    so neither can be moved by a change to what follows the third.
    """
    texts = {generated.name: generated.text for generated in generated_files(layout)}

    def exec_start(unit: str) -> list[str]:
        line = next(
            row for row in texts[unit].splitlines() if row.startswith("ExecStart=")
        )
        return line.removeprefix("ExecStart=").split()

    bridge = exec_start(BRIDGE_UNIT)
    assert bridge == [str(layout.wrapper), "factory.notify.service"]

    worker = exec_start(WORKER_TEMPLATE_UNIT)
    tree = layout.deployment_tree("%i")
    assert worker == [
        str(layout.wrapper),
        "factory.worker",
        str(tree),
        str(layout.deployment_interpreter("%i")),
    ]


# --- T011 [US2-S3 / FR-005, plan trap 1] the wrong-fix catcher ----------------


def test_the_overrides_apply_and_are_not_passed_on_to_the_module(
    wrapper: Path, tmp_path: Path
) -> None:
    """US2-S3: both overrides take effect, and neither reaches the module.

    A naive `-m "$@"` fails this twice over: the deployment root and the
    deployment's interpreter would arrive as the module's first two arguments.
    The positionals are consumed, not forwarded.
    """
    deployment = tmp_path / "state/ergane/supervision/deployments/c0ffee1/tree"
    interpreter = _stub(deployment / ".venv/bin/python3", "deployed")

    spoken = run(wrapper, "factory.worker", str(deployment), str(interpreter))

    assert spoken.who == "deployed"
    assert spoken.cwd == str(deployment)
    assert spoken.arguments == ("-m", "factory.worker")
    assert str(deployment) not in " ".join(spoken.arguments)


def test_the_overrides_are_consumed_even_when_arguments_follow_them(
    wrapper: Path, tmp_path: Path
) -> None:
    """US2-S3 and S1 together: overriding *and* passing flags, which is the
    shape a versioned unit that took an argument would have.

    The module receives what follows the third positional and only that, while
    the two overrides still decide where it runs and what runs it.
    """
    deployment = tmp_path / "state/ergane/supervision/deployments/c0ffee1/tree"
    interpreter = _stub(deployment / ".venv/bin/python3", "deployed")

    spoken = run(
        wrapper,
        "factory.worker",
        str(deployment),
        str(interpreter),
        "--build-id",
        "c0ffee1",
    )

    assert spoken.who == "deployed"
    assert spoken.cwd == str(deployment)
    assert spoken.arguments == ("-m", "factory.worker", "--build-id", "c0ffee1")
