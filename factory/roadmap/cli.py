"""The roadmap's operator surface: one command renders the whole roadmap.

`factory-roadmap render` is US1's one command (acceptance scenario 5): it reads
a `specs/` corpus from disk and prints every spec with its state, naming each
blocked spec's unsatisfied dependencies — never a bare "blocked". The render
touches no service (US1's render needs no Temporal, no proxy), so it is the
offline verb `factory-epic derive` is, not the server verbs `start`/`status`
are: an operator can render the roadmap on a laptop with no factory anywhere
near it.

The CLI mirrors `factory-epic`'s parser shape and exit-code contract:

- `0` success — the corpus parsed and the render printed.
- `1` an operator-fixable grammar rejection — a spec the author has to edit.
  The offender and the file are named on stderr (FR-001), the same way
  `factory-epic derive` names every rejection.
- `2` a service that is not answering. The render never reaches `2` — it
  touches no service — but the number is reserved by the contract the rest of
  the factory's CLIs honour, and is stated here once.

The render is deterministic: specs appear in sorted order of their spec dir
(the order `read_roadmap` already returns), so two operators reading the same
corpus see the same lines.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from factory.roadmap.models import (
    SPEC_NAME,
    RoadmapError,
    compute_readiness,
    read_roadmap,
)

EXIT_OK = 0
EXIT_USER = 1
EXIT_TRANSPORT = 2

#: The directory the worker looks for feature specs unless told otherwise —
#: the same default as `factory.workgraph.cli.DEFAULT_SPECS_ROOT`.
DEFAULT_SPECS_ROOT = "specs"


class _OperatorError(Exception):
    """Something an operator can act on, and the status that says which kind.

    Carrying the exit code on the exception keeps every message in one printer:
    a transport failure and a broken spec take the same path out of a command
    and differ only in the number, so no command has to remember to print
    before it returns.
    """

    def __init__(self, message: str, code: int = EXIT_USER) -> None:
        super().__init__(message)
        self.code = code


def main(argv: Sequence[str] | None = None) -> int:
    """Run one invocation. Returns the process status; prints errors to stderr.

    Nothing but the rendered roadmap ever reaches stdout, so a caller that pipes
    the render into another command gets an empty string on failure rather than
    a sentence to parse around.
    """
    args = _parse_args(argv)
    try:
        return int(args.run(args))
    except _OperatorError as error:
        print(f"factory-roadmap: {error}", file=sys.stderr)
        return error.code


# --- render: the whole roadmap, every spec, every blocker named --------------


def render_command(args: argparse.Namespace) -> int:
    """Render every spec with its state and each blocked spec's blockers.

    Reads the corpus from disk (no service), computes readiness, and prints one
    line per spec in sorted order. A blocked spec names its unsatisfied
    dependencies on its line, so the operator's next move (unblock the edge or
    edit it) is on the line — never a bare "blocked".
    """
    try:
        roadmap = read_roadmap(args.specs_root)
    except RoadmapError as error:
        # The whole list, at the point the author can act on all of it at once,
        # and no partial render — a broken corpus prints nothing on stdout.
        raise _OperatorError(str(error)) from error
    except OSError as error:
        raise _OperatorError(f"cannot read specs root {args.specs_root}: {error}") from error

    readiness = compute_readiness(roadmap)
    print(_render_roadmap(roadmap, readiness))
    return EXIT_OK


def _render_roadmap(roadmap: object, readiness: object) -> str:
    """The human view: one line per spec, state and blockers named.

    `<spec-dir>  <state>  blocked by: <dep>, <dep>` — the blockers appear only
    when there are any, so a dispatchable or non-ready spec reads cleanly. The
    state is the declared intent; the blockers are the computed unsatisfied
    edges. Deterministic: `read_roadmap` already sorts by spec dir, and the
    render re-sorts nothing.
    """
    # Typed as `object` to keep this renderer decoupled from the model's exact
    # names at import time; the bodies are the real dataclasses by construction.
    from factory.roadmap.models import Roadmap, Readiness

    assert isinstance(roadmap, Roadmap)
    assert isinstance(readiness, Readiness)

    by_dir = {spec.spec_dir: spec for spec in readiness.specs}
    id_width = max((len(entry.spec_dir) for entry in roadmap.entries), default=0)
    state_width = max(
        (len(entry.state.value) for entry in roadmap.entries), default=0
    )

    lines: list[str] = []
    for entry in roadmap.entries:
        spec = by_dir[entry.spec_dir]
        base = (
            f"{entry.spec_dir.ljust(id_width)}  "
            f"{entry.state.value.ljust(state_width)}"
        )
        if spec.blockers:
            lines.append(f"{base}  blocked by: {', '.join(spec.blockers)}")
        else:
            lines.append(base)
    return "\n".join(lines)


# --- arguments ----------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    """An `ArgumentParser` that exits 1, because a bad invocation is a user error.

    argparse's own status for that is 2, which this CLI's contract reserves for
    a service that is not answering — the same distinction `factory-epic`'s
    parser makes, so a script does not lose it the moment someone mistypes a
    flag.
    """

    def error(self, message: str) -> object:  # pragma: no cover - argparse's path
        self.print_usage(sys.stderr)
        self.exit(EXIT_USER, f"{self.prog}: error: {message}\n")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(
        prog="factory-roadmap",
        description="Render the roadmap: every spec, its state, and its blockers (US1).",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser(
        "render",
        help=f"render every spec under <specs-root>/{SPEC_NAME} with state + blockers",
    )
    render.add_argument(
        "specs_root",
        nargs="?",
        default=DEFAULT_SPECS_ROOT,
        help=f"the specs root to scan (default: {DEFAULT_SPECS_ROOT})",
    )
    render.set_defaults(run=render_command)

    return parser.parse_args(argv)


if __name__ == "__main__":  # pragma: no cover - console script uses `main`
    sys.exit(main())