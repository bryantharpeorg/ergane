"""The activity surface of verification.

`factory/verify/` is a library of pure functions and one-purpose runners; this
module is where they become things the orchestrator can call, which means it
owns exactly two concerns the library deliberately does not: reading the world
at a known moment, and turning a library exception into an error a workflow can
branch on without reading prose.

`snapshot_criteria` is the first of those calls and the only one that runs
*before* an agent does any work. What it returns is the node's goalposts for the
rest of its life (FR-010) — every later attempt is judged against this value,
not against whatever the spec file says by then — so it stamps the moment it
read and hashes the bytes it read, and the difference between that hash and a
later one is the whole of drift detection (R8).

Its two failure modes are why the parser raises two different exception classes.
A spec the grammar refuses and a spec file that is not there both mean "this
node cannot be verified", but they send an operator to different places: one
goes and edits a requirement, the other fixes a wrong `specs_root` or a
misspelled feature. They come back as `CRITERIA_PARSE_FAILED` and
`CRITERIA_FILE_MISSING` so the workflow can tell them apart. Both are
non-retryable — neither a malformed spec nor an absent file becomes well-formed
by being read again a second later, and the ladder's retry budget exists for
proxies and worktrees, not for typos.

The parse error carries the parser's message verbatim. That message names the
one offending requirement and no sibling, and it is the operator's entire
diagnosis; an error that only said "spec did not parse" would make this activity
strictly less useful than the library call it wraps.

T021 extends this module with `run_gates`, `check_output`, `run_judge` and
`record_verification`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from temporalio import activity
from temporalio.exceptions import ApplicationError

from factory.verify.criteria import CriteriaParseError, load_criteria
from factory.verify.models import CriteriaSet

#: The activity error type for a spec the grammar refuses (spec US1). The
#: message is the parser's, naming the one requirement at fault.
CRITERIA_PARSE_FAILED = "CRITERIA_PARSE_FAILED"

#: The activity error type for a spec file that is not where the dispatch said
#: it would be — a wiring mistake, not a spec to go fix.
CRITERIA_FILE_MISSING = "CRITERIA_FILE_MISSING"

#: The system of record's filename under `<specs_root>/<feature>/` (D-023).
SPEC_FILENAME = "spec.md"


@dataclass(frozen=True)
class SnapshotCriteriaInput:
    """A node's dispatch, in the terms the criteria parser needs.

    `requirement_keys` is what this node owes — empty means the whole feature,
    which is a legitimate dispatch and must not quietly become "no criteria"
    (a node verified against nothing passes on an empty diff, the very failure
    FR-004 exists to prevent). `spec_ref` is component 1's work-attribution key
    and is carried through untouched: the activity has no business inventing one.
    """

    specs_root: str
    feature: str
    spec_ref: str
    requirement_keys: list[str] = field(default_factory=list)


@activity.defn
async def snapshot_criteria(request: SnapshotCriteriaInput) -> CriteriaSet:
    """Take the node's acceptance criteria from the spec, once (FR-010).

    A pure read and parse, safe for Temporal to retry: two runs against
    unchanged bytes agree on everything but the timestamp.

    Raises `CRITERIA_FILE_MISSING` when there is no `spec.md` at the dispatched
    path, `CRITERIA_PARSE_FAILED` when there is one and the grammar refuses it.
    Both are non-retryable.
    """
    path = spec_path(request.specs_root, request.feature)
    try:
        return load_criteria(
            path,
            feature=request.feature,
            spec_ref=request.spec_ref,
            requirement_keys=request.requirement_keys,
        )
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError) as exc:
        # Every one of these means the same thing to the operator: nothing
        # readable at that path. The path is in the message because the root,
        # the feature name and the filename are all suspects.
        raise ApplicationError(
            f"no feature spec at {path}",
            type=CRITERIA_FILE_MISSING,
            non_retryable=True,
        ) from exc
    except CriteriaParseError as exc:
        # Verbatim: the parser already named the offending requirement and said
        # what is wrong with it, and that is the whole diagnosis.
        raise ApplicationError(
            str(exc),
            type=CRITERIA_PARSE_FAILED,
            non_retryable=True,
        ) from exc


def spec_path(specs_root: str, feature: str) -> Path:
    """The file D-023 designates as the system of record for one feature."""
    return Path(specs_root) / feature / SPEC_FILENAME
