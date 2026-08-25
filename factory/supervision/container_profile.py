"""The consent step that loads the engine container's AppArmor profile (104-US4).

*The engine container* is the Docker container `ergane install` brings up — never
bwrap's sandbox, never "a container of specs".

This is the only privileged act in spec 104, and it is one prompt: show the
profile text, ask, and — on consent — hand `sudo apparmor_parser -r <file>` to an
injected runner. What comes back is a `ProfileDecision`, which is data: it names
the confinement variant the generator must render, whether anything privileged
was attempted, the parser's own words when it refused, and the operator-facing
statement of what config F costs. The decision is made *before* anything is
written, so a refused load produces a whole F project rather than half a G one.

Three properties this module is built around:

- **The text shown is the text loaded.** The profile is read once through US2's
  package-data resolver and written to a scratch file for the parser, so consent
  is given to bytes that are then loaded, not to a display of a file that is read
  again later.
- **The prompt defaults to yes**, inverting this repository's only other consent
  grammar. The reasoning is in `_PROMPT`'s comment; read it before changing it.
- **Nothing here writes a project.** The consent step decides; US3's manifest
  writer writes. That is what makes "never a half-configured project" structural
  rather than a cleanup path.
"""

from __future__ import annotations

import dataclasses
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Sequence

from factory.supervision.container_project import (
    APPARMOR_ARTIFACT,
    APPARMOR_PROFILE_NAME,
    CONFINEMENT_PROFILE,
    CONFINEMENT_UNCONFINED,
    UNCONFINED_EXPLANATION,
    confinement_artifact_text,
)

#: The privileged argv, as the plan spells it: `apparmor_parser -r <file>` under
#: `sudo`. Named here so a caller — and a test — reads one definition.
PARSER_COMMAND: tuple[str, ...] = ("sudo", "apparmor_parser", "-r")


@dataclasses.dataclass(frozen=True)
class PrivilegedResult:
    """What the privileged load said.

    Not `units.CommandResult`: that one carries stdout only, and the text US4-S3
    must report verbatim is `apparmor_parser`'s *stderr* — a parser error goes
    nowhere else, so a result type that drops it makes the criterion unreachable.
    """

    code: int
    out: str = ""
    err: str = ""

    @property
    def text(self) -> str:
        """What the operator is shown, verbatim: stderr if there is any, because
        that is where this parser speaks, and stdout only as a fallback."""
        return self.err.strip() or self.out.strip()


@dataclasses.dataclass(frozen=True)
class ProfileDecision:
    """The consent step's answer, as data the generator can render from.

    `attempted` is asked by US4-S2's "no privileged command was attempted", and
    it is deliberately not derivable from `confinement`: a decline and a failed
    load both end at config F, and only this field distinguishes them.
    """

    #: `CONFINEMENT_PROFILE` (config G) or `CONFINEMENT_UNCONFINED` (config F) —
    #: passed straight to `resolve_project(confinement=...)`.
    confinement: str
    #: Whether anything ran under `sudo`.
    attempted: bool
    #: The parser's own words when it refused, verbatim and unreflowed; empty
    #: when nothing failed.
    failure: str = ""
    #: What the operator was told about the difference. Identical for the decline
    #: and the failure, because the resulting engine is identical.
    statement: tuple[str, ...] = ()


#: What counts as consent — and, unlike everywhere else in this tree, the empty
#: answer is one of them.
#:
#: `factory/cli/init.py:268` is the only other consent grammar here, and it reads
#: a blank answer as a decline on 060/FR-007's rule that an absent answer is not
#: an answer. **This prompt inverts that deliberately, with the operator's
#: explicit approval**, for a reason that does not apply there: declining does
#: not avoid the privileged act on a fresh host. Config F depends on a
#: `/etc/apparmor.d/bwrap` stub that is hand-installed and unowned by any package
#: (measured — findings section 8, item 3), so a default-no here hands the
#: operator an engine nobody chose, whose remaining prerequisite is also root.
#: The safe default and the shipped configuration are the same thing, which is
#: what makes default-yes the honest one.
#:
#: An implementer who greps this repository for a consent default will find
#: exactly one other answer, and it is the opposite one. That is expected. Do not
#: "fix" this back.
_CONSENT = ("y", "yes")
_DEFAULT_ANSWER = "y"

_PROMPT = (
    f"load the AppArmor profile `{APPARMOR_PROFILE_NAME}` into the kernel with "
    "sudo? (Y/n)"
)


def profile_text() -> str:
    """The profile to display and load, read through US2's package-data resolver
    (R10) so the consent step works from a wheel, where `container/` is not on
    disk at all."""
    return confinement_artifact_text(APPARMOR_ARTIFACT)


def _run_privileged(argv: Sequence[str]) -> PrivilegedResult:
    """Run the load. **The seam every test in this story closes** (trap 11):
    `apparmor_parser` edits kernel policy, and this host runs the factory.

    A missing `sudo` or `apparmor_parser` comes back as a failure with the OS's
    own text rather than an exception, because the fallback for "the load did not
    happen" is already written and is the same one.
    """
    try:
        finished = subprocess.run(  # noqa: S603 - fixed argv, no shell
            list(argv), capture_output=True, text=True, check=False
        )
    except OSError as error:
        return PrivilegedResult(127, "", str(error))
    return PrivilegedResult(finished.returncode, finished.stdout, finished.stderr)


def _emit_statement(emit: Callable[[str], None], lines: Sequence[str]) -> None:
    for line in lines:
        emit(f"  {line}" if line else "")


def load_profile(
    prompter: Any,
    *,
    run: Callable[[Sequence[str]], PrivilegedResult] | None = None,
    emit: Callable[[str], None] = print,
) -> ProfileDecision:
    """Show the profile, ask, and load it — returning what the generator renders.

    Every side effect is behind a seam: `prompter.ask` is the interview's own
    prompter, `run` is the privileged runner, `emit` is the printer. A test drives
    all three and no `apparmor_parser` is executed.

    The order is the story: the text is shown **before** the prompt, because a
    prompt that asks for consent to something the operator has not read is not
    asking for consent. It is shown verbatim, and the same string is what the
    parser is handed.
    """
    runner = _run_privileged if run is None else run
    text = profile_text()

    emit(
        f"the engine container runs under the AppArmor profile "
        f"`{APPARMOR_PROFILE_NAME}`, which must be loaded into the kernel once. "
        "This is the only privileged step of the install; the whole profile is "
        "below."
    )
    emit("")
    emit(text)

    answer = prompter.ask(_PROMPT, default=_DEFAULT_ANSWER)
    answer = (answer or "").strip().lower() or _DEFAULT_ANSWER

    if answer not in _CONSENT:
        emit("declined: nothing was run under sudo and no kernel policy was touched.")
        _emit_statement(emit, UNCONFINED_EXPLANATION)
        return ProfileDecision(
            confinement=CONFINEMENT_UNCONFINED,
            attempted=False,
            statement=UNCONFINED_EXPLANATION,
        )

    with tempfile.TemporaryDirectory(prefix="ergane-apparmor-") as scratch:
        # Written from the string that was just displayed, and handed to the
        # parser by path: `apparmor_parser` loads the profile *named in the
        # file* (`profile ergane-engine`), so the path is immaterial and the
        # bytes are everything. Reading the artifact a second time here would
        # make "the text shown is the text loaded" a hope rather than a fact.
        path = Path(scratch) / APPARMOR_ARTIFACT
        path.write_text(text, encoding="utf-8")
        argv = (*PARSER_COMMAND, str(path))
        result = runner(argv)

    if result.code == 0:
        emit(f"loaded AppArmor profile `{APPARMOR_PROFILE_NAME}`")
        return ProfileDecision(
            confinement=CONFINEMENT_PROFILE,
            attempted=True,
            statement=(f"confinement: config G, `apparmor={APPARMOR_PROFILE_NAME}`.",),
        )

    failure = result.text
    emit(f"`{' '.join(PARSER_COMMAND)} {path}` exited {result.code}; it said:")
    emit("")
    # Verbatim: not reflowed, not prefixed line by line, not summarised. The
    # operator has to be able to paste this into a search box.
    emit(failure)
    emit("")
    emit("falling back to the same configuration a decline produces:")
    _emit_statement(emit, UNCONFINED_EXPLANATION)
    return ProfileDecision(
        confinement=CONFINEMENT_UNCONFINED,
        attempted=True,
        failure=failure,
        statement=UNCONFINED_EXPLANATION,
    )
