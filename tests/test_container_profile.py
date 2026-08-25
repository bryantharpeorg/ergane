"""104-US4: the consent step that loads the engine container's AppArmor profile.

Every test here is a **seam capture** (trap 11/14). The seams closed are the
prompter, the printer and the privileged runner: **`apparmor_parser` is never
executed, no kernel policy is touched, no `sudo` is invoked and no Docker daemon
is contacted.** What is asserted is the order of the transcript, the argv the
privileged seam *recorded*, and the text of a rendered project — never a running
engine.
"""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path
from typing import Any

import pytest
import yaml

from factory.supervision import container_profile as cprof
from factory.supervision import container_project as cp

# The generator's own host fixture: a relocated `HOME`, `ERGANE_STATE_HOME` and
# `XDG_CONFIG_HOME` with two registered repos. US4 renders the same projects US2
# does, so it resolves them from the same host rather than a second copy of it.
from tests.test_container_project import (  # noqa: F401 - `host` is a fixture
    _Host,
    _project,
    host,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMITTED_PROFILE = REPO_ROOT / "container" / "ergane-engine.profile"


# --- The seams ---


@dataclasses.dataclass
class _Recorded:
    """One privileged call, and the text of the file it named — recorded while
    the call is in flight, because that is the only moment at which "the argv
    names the profile file" is a checkable claim rather than a path string."""

    argv: tuple[str, ...]
    file_text: str


class _Session:
    """Prompter, printer and privileged runner over **one** transcript.

    Sharing the list is the point: US4-S1 is an ordering claim ("the text was
    shown *before* the prompt"), and two separate capture mechanisms — capsys for
    output, a scripted prompter for answers — cannot decide an ordering between
    them. Here they interleave, so the order is read off the list.
    """

    def __init__(self, *answers: str, result: cprof.PrivilegedResult | None = None) -> None:
        self.transcript: list[tuple[str, ...]] = []
        self.answers = list(answers)
        self.calls: list[_Recorded] = []
        self.result = result or cprof.PrivilegedResult(0)

    # printer seam
    def emit(self, text: str = "") -> None:
        self.transcript.append(("out", text))

    # prompter seam — the shape `factory/cli/init.py:153` fixes
    def ask(self, prompt: str, *, default: str | None = None, error: str | None = None) -> str:
        self.transcript.append(("ask", prompt, default or ""))
        answer = self.answers.pop(0)
        self.transcript.append(("answer", answer))
        return answer

    # privileged runner seam — never a real `apparmor_parser` (trap 11)
    def run(self, argv: Any) -> cprof.PrivilegedResult:
        argv = tuple(str(part) for part in argv)
        self.calls.append(_Recorded(argv, Path(argv[-1]).read_text(encoding="utf-8")))
        return self.result

    # --- readers ---

    @property
    def printed(self) -> str:
        return "\n".join(entry[1] for entry in self.transcript if entry[0] == "out")

    def index_of_prompt(self) -> int:
        for index, entry in enumerate(self.transcript):
            if entry[0] == "ask":
                return index
        raise AssertionError("nothing was asked")

    def index_of_output(self, text: str) -> int:
        for index, entry in enumerate(self.transcript):
            if entry[0] == "out" and entry[1] == text:
                return index
        raise AssertionError(f"never printed: {text[:60]!r}")


def _load(session: _Session) -> cprof.ProfileDecision:
    return cprof.load_profile(session, run=session.run, emit=session.emit)


def _compose(project: cp.ContainerProject) -> dict:
    return yaml.safe_load(cp.render_compose(project))


def _compose_text(project: cp.ContainerProject) -> str:
    files = {f.name: f for f in cp.project_files(project)}
    return files[cp.COMPOSE_NAME].text


# --- T029 [US4-S1] Consent: the text is shown, then the prompt, then the load ---


def test_the_profile_text_is_read_through_the_package_data_resolver() -> None:
    """R10: the same reader US2 built, so the consent prompt works from a wheel
    where `container/` is not on disk at all."""
    assert cprof.confinement_artifact_text is cp.confinement_artifact_text
    assert cprof.profile_text() == COMMITTED_PROFILE.read_text(encoding="utf-8")


def test_the_profile_text_is_shown_verbatim_before_the_prompt() -> None:
    """US4-S1's ordering claim, decided off one interleaved transcript."""
    session = _Session("y")
    _load(session)

    shown = session.index_of_output(cprof.profile_text())
    assert shown < session.index_of_prompt()
    # Verbatim, not summarised: the operator consents to the text that is loaded.
    assert "profile ergane-engine flags=(attach_disconnected,mediate_deleted) {" in (
        session.printed
    )


def test_the_prompt_defaults_to_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trap 7: this inverts `factory/cli/init.py:268`'s only consent precedent,
    with the operator's explicit approval — declining does not avoid the
    privileged act on a fresh host, it only produces an engine nobody chose."""
    session = _Session("y")
    _load(session)

    (_, prompt, default) = session.transcript[session.index_of_prompt()]
    assert default == "y"
    assert "(Y/n)" in prompt

    # And a bare enter — the answer an operator gives by pressing a key — is
    # consent here, where every other prompt in this tree reads it as a decline.
    blank = _Session("")
    assert _load(blank).confinement == cp.CONFINEMENT_PROFILE
    assert len(blank.calls) == 1


def test_consent_runs_apparmor_parser_once_on_the_text_that_was_shown() -> None:
    """The recorded argv, not a spawned process: `apparmor_parser -r` edits
    kernel policy, so the seam is what the test may see (trap 11)."""
    session = _Session("y")
    decision = _load(session)

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call.argv[:3] == ("sudo", "apparmor_parser", "-r")
    assert len(call.argv) == 4
    # The argv names a file, and that file holds the profile that was displayed.
    assert call.file_text == cprof.profile_text()
    assert f"profile {cp.APPARMOR_PROFILE_NAME} " in call.file_text

    assert decision.confinement == cp.CONFINEMENT_PROFILE
    assert decision.attempted is True
    assert decision.failure == ""


@pytest.mark.parametrize("answer", ["y", "Y", "yes", "  YES  ", ""])
def test_every_spelling_of_consent_reaches_the_shipped_confinement(answer: str) -> None:
    session = _Session(answer)
    assert _load(session).confinement == cp.CONFINEMENT_PROFILE


def test_the_project_rendered_from_consent_names_the_profile(host: _Host) -> None:
    """The other half of US4-S1: the decision reaches the generated compose."""
    session = _Session("y")
    decision = _load(session)

    project = _project(host, confinement=decision.confinement)
    assert f"apparmor={cp.APPARMOR_PROFILE_NAME}" in _compose(project)["services"]["ergane"][
        "security_opt"
    ]
    assert "unconfined" not in _compose_text(project).lower()


# --- T030 [US4-S2] Decline: nothing privileged, and an honest F project ---


def test_declining_attempts_no_privileged_command() -> None:
    """Asserted on the seam's recorded calls, not on output: an installer that
    merely *says* nothing happened is what this criterion exists to rule out."""
    session = _Session("n")
    decision = _load(session)

    assert session.calls == []
    assert decision.attempted is False
    assert decision.confinement == cp.CONFINEMENT_UNCONFINED
    assert decision.failure == ""


@pytest.mark.parametrize("answer", ["n", "N", "no", "nope", "q", " no "])
def test_anything_that_is_not_consent_declines(answer: str) -> None:
    session = _Session(answer)
    assert _load(session).confinement == cp.CONFINEMENT_UNCONFINED
    assert session.calls == []


def test_the_declined_output_states_the_difference() -> None:
    printed = _Session("n")
    _load(printed)
    text = printed.printed

    assert "config F" in text
    assert "apparmor=unconfined" in text
    assert f"apparmor={cp.APPARMOR_PROFILE_NAME}" in text


def test_the_generated_f_project_annotates_the_difference_in_its_own_comments(
    host: _Host,
) -> None:
    """Comments are data (R4), so the honesty survives into the file rather than
    living only in a terminal the operator has since closed."""
    session = _Session("n")
    decision = _load(session)
    project = _project(host, confinement=decision.confinement)

    service = _compose(project)["services"]["ergane"]
    assert "apparmor=unconfined" in service["security_opt"]
    assert f"apparmor={cp.APPARMOR_PROFILE_NAME}" not in service["security_opt"]

    comments = [
        line.strip().lstrip("#").strip()
        for line in _compose_text(project).splitlines()
        if line.strip().startswith("#")
    ]
    annotated = "\n".join(comments)

    # The difference, and which one is shipped.
    assert "config F" in annotated
    assert "config G" in annotated
    assert "shipped" in annotated
    # Trap 8's measured facts, both of them.
    assert "/etc/apparmor.d/bwrap" in annotated
    assert "stock Ubuntu 24.04" in annotated
    assert "unprivileged_userns" in annotated
    # The story's own words: the prerequisites that remain are named.
    assert "honestly annotated" in annotated
    assert "remaining prerequisites" in annotated
    assert "apparmor_parser -r" in annotated


def test_the_printed_statement_and_the_file_annotation_are_one_fact(host: _Host) -> None:
    """One constant, two destinations: an output that reassures and a file that
    says something else is the failure this asserts against."""
    session = _Session("n")
    decision = _load(session)
    project = _project(host, confinement=decision.confinement)

    assert decision.statement == cp.UNCONFINED_EXPLANATION
    compose_text = _compose_text(project)
    for line in cp.UNCONFINED_EXPLANATION:
        if not line:
            continue
        assert line in session.printed
        assert line in compose_text


def test_the_declined_project_is_complete(host: _Host) -> None:
    """"A completely generated engine": all four files, seccomp and
    no-new-privileges untouched — F relaxes AppArmor and nothing else."""
    session = _Session("n")
    project = _project(host, confinement=_load(session).confinement)

    names = {f.name for f in cp.project_files(project)}
    assert names == {
        cp.COMPOSE_NAME,
        cp.ENV_NAME,
        cp.SECCOMP_ARTIFACT,
        cp.APPARMOR_ARTIFACT,
    }
    security_opt = _compose(project)["services"]["ergane"]["security_opt"]
    assert "no-new-privileges:true" in security_opt
    assert f"seccomp:./{cp.SECCOMP_ARTIFACT}" in security_opt
    # The profile is still shipped into the project: it is what the operator
    # loads to reach G later, and the annotation names that command.
    files = {f.name: f for f in cp.project_files(project)}
    assert files[cp.APPARMOR_ARTIFACT].text == COMMITTED_PROFILE.read_text(encoding="utf-8")


# --- T031 [US4-S3] A failing parser: verbatim, then the same fallback ---


_PARSER_STDERR = (
    "AppArmor parser error for /tmp/ergane-engine.profile in profile "
    "/tmp/ergane-engine.profile at line 8: Could not open 'abi/4.0'\n"
    "AppArmor parser error: syntax error, unexpected TOK_ID"
)


def _failing() -> _Session:
    return _Session("y", result=cprof.PrivilegedResult(1, "", _PARSER_STDERR))


def test_a_failing_parser_is_reported_verbatim() -> None:
    """Verbatim means the operator can paste it into a search box: not reflowed,
    not summarised, not prefixed line by line."""
    session = _failing()
    decision = _load(session)

    assert decision.failure == _PARSER_STDERR
    assert _PARSER_STDERR in session.printed
    assert "exited 1" in session.printed


def test_a_failing_parser_falls_back_to_f_with_the_same_statement() -> None:
    declined = _Session("n")
    declined_decision = _load(declined)
    failed_decision = _load(_failing())

    assert failed_decision.confinement == cp.CONFINEMENT_UNCONFINED
    assert failed_decision.statement == declined_decision.statement
    assert failed_decision.statement == cp.UNCONFINED_EXPLANATION
    # It differs from the decline in exactly one way: something was attempted.
    assert failed_decision.attempted is True


def test_a_failing_parser_still_yields_a_complete_f_project(host: _Host) -> None:
    """Never a half-configured project: the failure changes the confinement and
    nothing else, so what is generated is a whole project either way."""
    session = _failing()
    project = _project(host, confinement=_load(session).confinement)

    assert {f.name for f in cp.project_files(project)} == {
        cp.COMPOSE_NAME,
        cp.ENV_NAME,
        cp.SECCOMP_ARTIFACT,
        cp.APPARMOR_ARTIFACT,
    }
    compose = _compose(project)
    assert "apparmor=unconfined" in compose["services"]["ergane"]["security_opt"]
    assert compose["services"]["ergane"]["init"] is True
    assert compose["services"]["ergane"]["cap_drop"] == ["ALL"]
    assert "/etc/apparmor.d/bwrap" in _compose_text(project)


def test_the_failure_writes_no_project_directory(host: _Host) -> None:
    """The consent step decides; US3's writer writes. Nothing partial survives
    here because nothing is written here — asserted rather than assumed."""
    session = _failing()
    _load(session)

    assert not cp.project_dir().exists()
    assert not (host.state_home / "ergane" / "supervision").exists()


# --- The confinement variant is a parameter of the operational project only ---


def test_only_resolve_project_takes_the_variant() -> None:
    """T033/trap 9: `reference_project()` stays parameterless, so the committed
    reference cannot go red on a wrong default in a file nobody edited."""
    assert "confinement" in inspect.signature(cp.resolve_project).parameters
    assert inspect.signature(cp.reference_project).parameters == {}


def test_an_unknown_variant_is_refused_by_name(host: _Host) -> None:
    from factory.cli.errors import OperatorError

    with pytest.raises(OperatorError) as caught:
        _project(host, confinement="apparmor=off")
    assert "apparmor=off" in str(caught.value)


def test_the_shipped_variant_is_the_default(host: _Host) -> None:
    assert _project(host).security_opt == cp.CONFINED_SECURITY_OPT
    assert _project(host, confinement=cp.CONFINEMENT_PROFILE).security_opt == (
        cp.CONFINED_SECURITY_OPT
    )
