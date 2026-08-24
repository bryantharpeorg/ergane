"""104-US1: the interview asks where the engine runs.

`ergane install` gains one question — where the **engine container** runs:
`container`, `systemd` (today's path) or `none` (configure only, today's exit).
This module is the whole of US1's evidence: the question is offered with the
container first when a Docker daemon answers, the container is refused by name
when no daemon does, and the two flag-driven paths (`--non-interactive`,
`--from-file`) are left exactly as they were.

**No test here contacts a Docker daemon** (plan trap 11). Every one drives the
capability predicate `factory.cli.install._docker_daemon_available` as a seam,
and the repo-wide autouse fixture `_docker_daemon_unavailable_in_tests`
(`tests/conftest.py`) pins it to "absent" for every other test in the suite, so
a developer who happens to have Docker running sees the same suite the gate
does.

Why the question is asked only when a daemon answers
----------------------------------------------------

The container backend is offered when it can actually run. On a host where no
daemon answers, install asks nothing new and behaves exactly as it does today —
which is what makes US1-S3's "their existing tests pass unmodified" true on
*every* host rather than only on hosts without Docker. An operator on such a
host who wants the container anyway says so with `--engine=container`, and gets
US1-S2's refusal naming the missing piece; the guard lives in `_interview_engine`
and is therefore the same guard whichever door the choice comes through.

The harness is 033's walkthrough harness, imported rather than rebuilt — a
second prompter convention one epic later is the drift the rename was spent
avoiding.
"""

from __future__ import annotations

import copy
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.install as install_module
from factory.cli.errors import EXIT_USER
from factory.cli.install import (
    BLANK_DOCUMENT,
    DEFAULT_ENGINE_BACKEND,
    ENGINE_BACKENDS,
    ENGINE_CONTAINER,
    ENGINE_NONE,
    ENGINE_SYSTEMD,
    _offered_engine_backend,
    _plan_file_answers,
)

#: The real predicate, bound before `tests/conftest.py`'s autouse fixture pins
#: the module attribute to "absent". The probe's own contract — bounded, and no
#: exception escapes it — is only assertable against the function itself.
_REAL_DAEMON_PROBE = install_module._docker_daemon_available

# The 033 walkthrough harness. Two of these are fixtures; importing them
# registers them in this module.
from tests.test_ergane_install_walkthrough import (  # noqa: F401
    GATEWAY_ANSWERS,
    Asked,
    Run,
    ScriptedPrompter,
    _answers,
    _invoke,
    config_path,
    walkthrough,
)

#: The prompt this story adds, in full. Asserting the whole string is the point:
#: US1-S1 is about what the operator is *offered*, not about a substring.
ENGINE_PROMPT = "engine backend (container|systemd|none)"


@pytest.fixture(autouse=True)
def _stub_persona_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """103's persona step is proven in its own file; these tests cover the rest.

    Driven for real it would reach the gateway named by the answers below, which
    is a closed loopback port on purpose.
    """
    monkeypatch.setattr(install_module, "_interview_personas", lambda _p, _d, _pp: None)


def _daemon(monkeypatch: pytest.MonkeyPatch, answers: bool) -> None:
    """Drive the one capability predicate the engine question consults."""
    monkeypatch.setattr(
        install_module, "_docker_daemon_available", lambda *_a, **_k: answers
    )


def _engine_questions(prompter: ScriptedPrompter) -> list[Asked]:
    return [asked for asked in prompter.asked if asked.prompt.startswith("engine backend")]


def _only_which(**paths: str | None) -> Callable[[str], str | None]:
    """A `shutil.which` that answers from a table and nothing else.

    Keeps the reason builder off the real PATH, so what the refusal says is a
    function of the stated host and not of the machine running pytest.
    """

    def which(name: str, *_args: Any, **_kwargs: Any) -> str | None:
        return paths.get(name.replace("-", "_"))

    return which


# ---------------------------------------------------------------------------
# T001 (US1-S1): the question, and the paths not chosen
# ---------------------------------------------------------------------------


def test_the_engine_question_offers_the_container_first_and_leaves_today_alone(
    monkeypatch: pytest.MonkeyPatch,
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
) -> None:
    """US1-S1: container first, `systemd` and `none` present, config unchanged.

    Three runs of the same interview against the same scratch config: one on a
    host with no daemon (today's install, asked nothing new), then `systemd` and
    `none` on a host where one answers. The bytes on disk have to be identical
    across all three — that is the whole of "the paths I do not choose are left
    exactly as they are today", and it is asserted on the file rather than on
    the absence of a code path.
    """
    # 1. Today: no daemon, no engine question at all.
    _daemon(monkeypatch, False)
    today, today_prompter = walkthrough(_answers())
    assert today.code == EXIT_USER  # verify fails against four closed ports
    assert _engine_questions(today_prompter) == []
    today_config = config_path.read_bytes()
    assert b"engine" not in today_config

    # 2. A daemon answers: the question is asked, and `container` is first.
    _daemon(monkeypatch, True)
    chose_systemd, systemd_prompter = walkthrough(_answers() + [ENGINE_SYSTEMD])
    asked = _engine_questions(systemd_prompter)
    assert len(asked) == 1
    assert asked[0].prompt == ENGINE_PROMPT
    assert asked[0].default == ENGINE_CONTAINER

    offered = asked[0].prompt[asked[0].prompt.index("(") + 1 : -1].split("|")
    assert offered[0] == ENGINE_CONTAINER
    assert set(offered) == {ENGINE_CONTAINER, ENGINE_SYSTEMD, ENGINE_NONE}

    assert chose_systemd.code == EXIT_USER
    assert config_path.read_bytes() == today_config

    # 3. And `none`, the other path this story must not disturb.
    chose_none, none_prompter = walkthrough(_answers() + [ENGINE_NONE])
    assert len(_engine_questions(none_prompter)) == 1
    assert chose_none.code == EXIT_USER
    assert config_path.read_bytes() == today_config

    # Neither answer printed a backend line: only `container` announces itself,
    # and that print is what US5 replaces with the bring-up.
    assert "engine backend:" not in chose_systemd.stdout
    assert "engine backend:" not in chose_none.stdout


def test_choosing_the_container_where_a_daemon_answers_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
) -> None:
    """US1-S1: the offered answer is a real answer, and it reaches the operator.

    US1 asks and holds the choice as a value (plan R2); the printed line is the
    seam US5 replaces with generation, consent and bring-up. Nothing about the
    container is written to `config.toml` — the carrier is the generated project
    on disk (plan R1), so a config that mentioned the engine would be the defect.
    """
    _daemon(monkeypatch, True)
    run, prompter = walkthrough(_answers() + [ENGINE_CONTAINER])

    assert len(_engine_questions(prompter)) == 1
    assert f"engine backend: {ENGINE_CONTAINER}" in run.stdout
    assert "engine" not in config_path.read_text(encoding="utf-8")


def test_an_unrecognised_backend_is_re_asked_rather_than_accepted(
    monkeypatch: pytest.MonkeyPatch,
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
) -> None:
    """A typo may not fall through as "not container" and silently configure only.

    The engine answer never reaches the config parser (plan R1), so `_ask`'s own
    refuse-and-re-ask loop cannot judge it; this is the check that stands in for
    the parser on this one question.
    """
    _daemon(monkeypatch, True)
    run, prompter = walkthrough(_answers() + ["contianer", ENGINE_CONTAINER])

    assert len(_engine_questions(prompter)) == 2
    assert "contianer" in run.stdout
    assert f"engine backend: {ENGINE_CONTAINER}" in run.stdout


# ---------------------------------------------------------------------------
# T002 (US1-S2): no daemon, and the container chosen anyway
# ---------------------------------------------------------------------------


def test_the_container_without_a_daemon_is_refused_naming_the_daemon(
    monkeypatch: pytest.MonkeyPatch,
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
) -> None:
    """US1-S2: refused, naming the daemon as missing and how to get it.

    Refused *before* the write, the way `_ask_temporal` refuses managed mode:
    an install that cannot do what was asked leaves no half-configured host
    behind, so the absence of the config file is part of the assertion.
    """
    _daemon(monkeypatch, False)
    monkeypatch.setattr(shutil, "which", _only_which())

    run, prompter = walkthrough(_answers(), "--engine", ENGINE_CONTAINER)

    assert run.code == EXIT_USER
    assert _engine_questions(prompter) == []  # the flag answered the question
    message = run.stderr
    assert '"container"' in message
    assert "Docker daemon" in message
    assert "`docker` is not on PATH" in message
    assert "https://docs.docker.com/engine/install/" in message
    # …and what to do instead, so the refusal is not a dead end.
    assert "`systemd`" in message and "`none`" in message
    assert not config_path.exists()


def test_the_refusal_names_the_legacy_compose_binary_when_that_is_what_is_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec Assumptions: name the missing piece when only the legacy binary exists.

    `docker-compose` (v1, hyphenated) and `docker compose` (v2, a subcommand of
    the daemon's own CLI) are different programs, and only the second can bring
    the engine container up. An operator who has the first and is told "Docker is
    not installed" will reasonably believe the installer is wrong.
    """
    monkeypatch.setattr(
        shutil, "which", _only_which(docker_compose="/usr/local/bin/docker-compose")
    )

    offered = _offered_engine_backend(False)

    assert offered.backend == ENGINE_NONE
    assert offered.unavailable_reason is not None
    reason = offered.unavailable_reason
    assert "/usr/local/bin/docker-compose" in reason  # the binary that is there
    assert "docker-compose" in reason  # named as the legacy one
    assert "docker compose" in reason  # and distinguished from v2
    assert "docker-compose-plugin" in reason  # how to get it


def test_the_refusal_names_a_silent_daemon_when_docker_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installed but not answering is a different fix from not installed."""
    monkeypatch.setattr(shutil, "which", _only_which(docker="/usr/bin/docker"))

    reason = _offered_engine_backend(False).unavailable_reason

    assert reason is not None
    assert "/usr/bin/docker" in reason
    assert "docker info" in reason
    assert "systemctl start docker" in reason
    assert "usermod -aG docker" in reason


def test_a_daemon_that_answers_offers_the_container_with_no_reason_to_give(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _daemon(monkeypatch, True)
    offered = _offered_engine_backend(True)

    assert offered.backend == ENGINE_CONTAINER
    assert offered.choices == "|".join(ENGINE_BACKENDS)
    assert offered.unavailable_reason is None


def test_the_daemon_probe_is_bounded_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T005: one bounded, `check=False` subprocess, and no exception escapes.

    A probe that hangs is worse than a probe that says no: the operator is at a
    prompt waiting for a question that never arrives. `docker info` against a
    wedged socket is exactly that shape, which is why the timeout is asserted
    here rather than assumed.
    """
    monkeypatch.setattr(shutil, "which", _only_which(docker="/usr/bin/docker"))
    calls: list[dict[str, Any]] = []

    def _raise(exc: BaseException) -> Callable[..., Any]:
        def run(command: Any, **kwargs: Any) -> Any:
            calls.append({"command": tuple(command), **kwargs})
            raise exc

        return run

    for failure in (
        subprocess.TimeoutExpired(cmd="docker info", timeout=1.0),
        OSError("socket vanished"),
    ):
        monkeypatch.setattr(subprocess, "run", _raise(failure))
        assert _REAL_DAEMON_PROBE() is False

    assert len(calls) == 2
    for call in calls:
        assert call["command"][0] == "docker"
        assert call["check"] is False
        assert isinstance(call["timeout"], float) and call["timeout"] > 0

    # And an absent binary is answered without spawning anything at all.
    calls.clear()
    monkeypatch.setattr(shutil, "which", _only_which())
    assert _REAL_DAEMON_PROBE() is False
    assert calls == []


# ---------------------------------------------------------------------------
# T003 (US1-S3): the two flag-driven paths, and the answer list they consume
# ---------------------------------------------------------------------------


def test_the_flag_driven_paths_ask_nothing_new_and_default_to_none(
    monkeypatch: pytest.MonkeyPatch,
    config_path: Path,
) -> None:
    """US1-S3: `--non-interactive` and `--from-file` configure only.

    Each path is run twice from the same blank host — once on a host with no
    Docker daemon (today), once on a host where one answers — and the two
    question lists must be *the same list*: same length, same order, same
    prompts. That is the property plan trap 1 exists to protect, and comparing
    the runs asserts it directly rather than re-deriving the planner's
    arithmetic here.
    """
    #: An answer file with one declared field; every other answer is a
    #: documented default, exactly as `--from-file` is meant to be used.
    answer_text = '[escalation]\nadapter = "none"\n'

    asked: list[str] = []
    real_prompter = install_module._FilePrompter

    class _Recording(real_prompter):  # type: ignore[valid-type,misc]
        def ask(self, prompt: str, *, default: Any = None, error: Any = None) -> str:
            asked.append(prompt)
            return super().ask(prompt, default=default, error=error)

    monkeypatch.setattr(install_module, "_FilePrompter", _Recording)

    answer_file = config_path.parent / "answers.toml"
    answer_file.parent.mkdir(parents=True, exist_ok=True)
    answer_file.write_text(answer_text, encoding="utf-8")

    def _questions(argv: list[str], daemon_answers: bool) -> list[str]:
        config_path.unlink(missing_ok=True)  # each run starts from a blank host
        _daemon(monkeypatch, daemon_answers)
        asked.clear()
        run = _invoke(argv)
        assert run.code == EXIT_USER  # verify against the default closed ports
        assert config_path.exists()
        return list(asked)

    for argv in (
        ["install", "--non-interactive"],
        ["install", "--from-file", str(answer_file)],
    ):
        today = _questions(argv, False)
        with_docker = _questions(argv, True)

        assert today, argv  # the interview really ran through the seam
        assert with_docker == today, argv
        assert not any("engine" in prompt for prompt in today), argv

    # Both paths plan their answers from the same document `_plan_file_answers`
    # builds, and this story added nothing to it.
    planned, _reports, missing, _completed = _plan_file_answers(
        copy.deepcopy(BLANK_DOCUMENT)
    )
    assert missing == []
    assert not any("engine" in report for report in _reports)

    # The declared default for both paths, which US5 reads and never asks about.
    assert DEFAULT_ENGINE_BACKEND == ENGINE_NONE


def test_the_answer_list_the_five_modules_share_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-S3: the five modules that reach `GATEWAY_ANSWERS` keep their ordinals.

    Plan trap 1: the definer indexes that list by literal position, three modules
    import the very same object, and a fifth duplicates it wholesale. A question
    added inside `_interview` would shift every ordinal after it and be seen here
    first — as a positional anchor landing on the wrong subsystem — rather than in
    a suite failure that names the last prompt instead of the new one.
    """
    import tests.test_controlplane_direct_mode as controlplane_direct_mode
    import tests.test_direct_mode_refused as direct_mode_refused
    import tests.test_ergane_install_walkthrough as definer
    import tests.test_install_mode_routing as mode_routing
    import tests.test_us2_shipped_registry as duplicator

    #: Length, and the ordinal each subsystem's *mode* answer sits at. The two
    #: lists differ — the duplicate declares `memory.backend = "none"` and skips
    #: that block's two follow-ups — so each is pinned against its own shape.
    shapes = {
        "tests/test_ergane_install_walkthrough.py": (
            definer.GATEWAY_ANSWERS,
            15,
            {0: "gateway", 3: "hindsight", 6: "external", 12: "telegram"},
        ),
        "tests/test_us2_shipped_registry.py": (
            duplicator.GATEWAY_ANSWERS,
            11,
            {0: "gateway", 3: "none", 4: "external", 10: "none"},
        ),
    }
    for name, (answers, length, anchors) in shapes.items():
        assert len(answers) == length, name
        for index, expected in anchors.items():
            assert answers[index] == expected, (name, index)

    # The three importers share the definer's object rather than a copy of it,
    # so there is exactly one list to keep honest.
    for importer in (mode_routing, direct_mode_refused, controlplane_direct_mode):
        assert importer.GATEWAY_ANSWERS is definer.GATEWAY_ANSWERS


# ---------------------------------------------------------------------------
# T004 (US1-S1, US1-S3): the `--engine` flag
# ---------------------------------------------------------------------------


def test_the_engine_flag_skips_the_question_and_its_absence_still_asks(
    monkeypatch: pytest.MonkeyPatch,
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
) -> None:
    """T004: declared once on the command line, or asked once in the interview."""
    _daemon(monkeypatch, True)

    declared, declared_prompter = walkthrough(_answers(), "--engine", ENGINE_SYSTEMD)
    assert declared.code == EXIT_USER
    assert _engine_questions(declared_prompter) == []

    asked, asked_prompter = walkthrough(_answers() + [ENGINE_SYSTEMD])
    assert asked.code == EXIT_USER
    assert len(_engine_questions(asked_prompter)) == 1


def test_the_engine_flag_takes_the_same_refusal_path_as_the_question(
    monkeypatch: pytest.MonkeyPatch,
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
) -> None:
    """T004: one guard, whichever door the choice came through.

    `--engine=container` is not a way around the capability check; it is a way
    to reach it without being asked.
    """
    _daemon(monkeypatch, False)
    monkeypatch.setattr(shutil, "which", _only_which())

    run, _prompter = walkthrough(_answers(), "--engine", ENGINE_CONTAINER)
    flagged = run.stderr

    _daemon(monkeypatch, False)
    reason = _offered_engine_backend(False).unavailable_reason
    assert reason is not None
    assert reason in flagged


@pytest.mark.parametrize(
    "argv, colliding",
    [
        (["install", "--engine", "container", "--non-interactive"], "--non-interactive"),
        (["install", "--engine", "container", "--from-file", "/nonexistent/answers.toml"], "--from-file"),
    ],
)
def test_the_engine_flag_beside_a_flag_driven_path_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
    config_path: Path,
    argv: list[str],
    colliding: str,
) -> None:
    """US1-S3: refused by name, never silently ignored.

    Both paths return before any engine step could run, so honouring the flag is
    impossible; discarding an explicit operator instruction without saying so is
    the failure this refusal exists to prevent. The refusal fires *first* — the
    `--from-file` case names a path that does not exist, so an install that got
    as far as reading the answer file would say so instead.
    """
    _daemon(monkeypatch, True)

    run = _invoke(argv)

    assert run.code == EXIT_USER
    assert "--engine" in run.stderr
    assert colliding in run.stderr
    assert "answer file not found" not in run.stderr
    assert not config_path.exists()


def test_the_engine_flag_admits_only_the_three_backends() -> None:
    """An unknown backend is refused by argparse, naming what is accepted."""
    run = _invoke(["install", "--engine", "podman"])

    assert run.code != 0
    assert "podman" in run.stderr
    for backend in ENGINE_BACKENDS:
        assert backend in run.stderr
