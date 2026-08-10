"""Handlers for the `ergane spec` noun.

The command surface now lives in `factory.cli.spec`; this module keeps the
reusable render handler (`render_command`, `_render_roadmap`) and the offline
drift resolver that the new noun reuses unchanged.
"""


from __future__ import annotations

import argparse
import json
from dataclasses import asdict
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

    readiness = compute_readiness(
        roadmap,
        drifted_for=_cli_drift_resolver(args.specs_root),
    )
    if getattr(args, "as_json", False):
        print(json.dumps({"roadmap": asdict(roadmap), "readiness": asdict(readiness)}, indent=2))
    else:
        print(_render_roadmap(roadmap, readiness))
    return EXIT_OK


def _cli_drift_resolver(specs_root: str):
    """Offline drift check for the render command: no Temporal, no git shell.

    The render command must work on a laptop with no factory running (US1). It
    therefore cannot read the target repo's landing history. The CLI treats the
    author's corpus as authoritative for drift: a `state: landed` spec is marked
    `amended` only when the operator requests it. This default resolver reports
    no drift so the offline render remains deterministic and safe; an online
    render (the workflow's `roadmap_status` query) uses the real git-backed
    resolver.
    """

    def resolve(spec_dir: str) -> bool:
        return False

    return resolve


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
    # Rendered state may be the computed `amended` value, not only declared states.
    state_values = [by_dir[entry.spec_dir].rendered_state for entry in roadmap.entries]
    state_width = max((len(value) for value in state_values), default=0)

    lines: list[str] = []
    for entry in roadmap.entries:
        spec = by_dir[entry.spec_dir]
        base = (
            f"{entry.spec_dir.ljust(id_width)}  "
            f"{spec.rendered_state.ljust(state_width)}"
        )
        if spec.blockers:
            lines.append(f"{base}  blocked by: {', '.join(spec.blockers)}")
        else:
            lines.append(base)
    return "\n".join(lines)
