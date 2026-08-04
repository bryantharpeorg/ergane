"""Proof that the node did something, before any other verdict is believed.

Gates answer "does the suite pass?" and the judge answers "does the work meet
the criteria?". Neither answers "is there any work?" — a suite passes just as
loudly over an untouched worktree, so an agent that burned its budget and
produced nothing would otherwise collect a PASS and unlock the downstream graph.
This module is the floor under both (FR-004), and the reason it is a separate
check rather than another gate is that no gate and no judge may rescue it.

The rule is persona-derived (`WriteScope`, component 1's registry) and the two
halves are asymmetric on purpose:

- **Write scopes (`worktree`, `docs`) are judged on their diff, and only on it.**
  A declared artifact does not substitute for a diff, and a missing one does not
  veto it. Whether the node produced *everything* it promised is a question for
  the scenarios and the judge; this check owns the floor, and widening it here
  would put a second, quieter verdict in front of them.
- **The read scope is judged on its declared artifact, and only on it.** A
  researcher's output is a report, not a diff, so the diff is recorded as
  evidence and ignored as a criterion. A read node that declared no artifact has
  nothing that could prove work, and so cannot pass — R7's "no diff and no
  artifact → FAIL" holds in that direction too.

Two properties are load-bearing:

**Nothing fails open.** A scope the registry never defined does not pass; an
empty file is not an artifact, a directory is not an artifact, and a path that
escapes the worktree is not this node's artifact. Every unknown answers "not
proved", because the only thing worse than a false FAIL here is the false PASS
this exists to prevent.

**"No diff" is a fact about the worktree, never a failure to look.** A vanished
directory and one git refuses to read both resemble a clean worktree exactly, and
reading git's exit 128 as "no changes" would be the pass-by-default this
component refuses everywhere else — pointed the other way, since for a
write-scoped node it fabricates a FAIL and charges an infrastructure failure to
the agent's attempt budget. Both raise `WorktreeMissingError`, which the activity
maps to `WORKTREE_MISSING` (contracts/activities.md). The read scope is the
exception: its personas may run with `needs_worktree: false`, and git's absence
cannot change a verdict that never consulted git.

"Diff" means worktree-vs-HEAD (R7), so an agent that *committed* inside its
worktree reads as clean. That is the contract's definition rather than an
oversight: in the node lifecycle the commit happens at salvage, after
verification. Untracked files count — new files are the normal shape of agent
output — and ignored files do not, which is what keeps the factory's own leavings
from manufacturing the diff FR-004 demands.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from factory.config import WriteScope
from factory.verify.gates import scrubbed_env
from factory.verify.models import OutputCheck

#: Scopes whose proof of work is the diff (FR-004).
DIFF_SCOPES: frozenset[WriteScope] = frozenset({WriteScope.WORKTREE, WriteScope.DOCS})

#: Scopes whose proof of work is a declared artifact instead (R7).
ARTIFACT_SCOPES: frozenset[WriteScope] = frozenset({WriteScope.READ})

#: Long enough for a cold index on a large repo, short enough that a wedged git
#: cannot hold the verification open; expiring reads as unreadable, not as clean.
GIT_TIMEOUT_S = 120


class WorktreeMissingError(RuntimeError):
    """The worktree could not be read — an infrastructure failure, not a verdict.

    Raised instead of returning the clean worktree an absent or unreadable
    directory superficially resembles. The message names the path, because by the
    time this surfaces as `WORKTREE_MISSING` the operator is looking at a node id
    and needs to know which directory went missing.
    """


def decide_passed(
    write_scope: WriteScope | str,
    *,
    has_diff: bool,
    artifacts_present: bool | None,
) -> bool:
    """The whole anti-rubber-stamp rule, with no filesystem in the way.

    `write_scope` may arrive as a plain string — it crosses the activity boundary
    as JSON — and a value outside `WriteScope` is a wiring bug rather than a
    licence: it never passes. `artifacts_present` is None when the node declared
    no artifacts, which is a pass for a diff scope with a diff and a failure for
    a read scope, whose only possible proof was the artifact.
    """
    scope = _as_scope(write_scope)
    if scope in DIFF_SCOPES:
        return has_diff
    if scope in ARTIFACT_SCOPES:
        return artifacts_present is True
    return False


def check_output(
    worktree: Path | str,
    write_scope: WriteScope | str,
    expected_artifacts: list[str] | tuple[str, ...] | None = None,
) -> OutputCheck:
    """Read the worktree and decide whether this node proved it did work.

    Both halves of the evidence are always gathered, whichever one decides: the
    diff is recorded for read nodes and the artifacts for write nodes, so a
    verdict someone disputes later can be re-read from the record rather than
    re-derived from a worktree that is long gone.

    Raises `WorktreeMissingError` when the worktree is absent, or when git cannot
    read it and the scope's verdict depends on git.
    """
    worktree = Path(worktree)
    artifacts = list(expected_artifacts or ())

    if not worktree.is_dir():
        raise WorktreeMissingError(f"node worktree does not exist: {worktree}")

    scope = _as_scope(write_scope)
    has_diff = _has_diff(worktree, required=scope not in ARTIFACT_SCOPES)
    artifacts_present = (
        all(_is_artifact(worktree, path) for path in artifacts) if artifacts else None
    )

    return OutputCheck(
        # The raw value, not the resolved member: an unrecognised scope is a bug
        # someone has to find, and the evidence should name what was passed.
        write_scope=scope.value if scope is not None else str(write_scope),
        has_diff=has_diff,
        expected_artifacts=artifacts,
        artifacts_present=artifacts_present,
        passed=decide_passed(
            write_scope, has_diff=has_diff, artifacts_present=artifacts_present
        ),
    )


def _as_scope(value: WriteScope | str) -> WriteScope | None:
    """The registry member `value` names, or None if the registry has no such scope."""
    try:
        return WriteScope(value)
    except ValueError:
        return None


def _has_diff(worktree: Path, *, required: bool) -> bool:
    """Whether the worktree differs from HEAD, untracked files included (R7).

    `required` says whether git is allowed to fail: for a scope the diff decides,
    an unreadable repository raises rather than reporting the clean worktree it
    looks like; for a read scope it is merely unrecorded, since a
    `needs_worktree: false` persona may have no repository at all.
    """
    status = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    if status is None:
        if required:
            raise WorktreeMissingError(
                f"git could not read the node worktree: {worktree}"
            )
        return False
    if status.strip():
        return True

    # R7 defines an empty diff as porcelain *and* `git diff HEAD` both empty, so
    # HEAD is consulted even though porcelain already covers everything it
    # reports. A failure here can only be an unborn branch — status just
    # succeeded, and it said nothing changed — so it is not fatal either way.
    committed = _git(worktree, "diff", "HEAD", "--name-only")
    return bool(committed and committed.strip())


def _git(worktree: Path, *args: str) -> str | None:
    """Run one read-only git command in `worktree`; None if git could not answer.

    The environment is the gate runner's allowlist (constitution V) — a
    subprocess the factory spawns gets no factory credentials, and dropping
    `GIT_DIR`/`GIT_WORK_TREE` along with them keeps the worker's own environment
    from redirecting the read. `GIT_OPTIONAL_LOCKS=0` stops a check that is only
    ever asking a question from taking the index lock to answer it.
    """
    env = scrubbed_env() | {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
    try:
        completed = subprocess.run(
            ["git", "-C", str(worktree), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _is_artifact(worktree: Path, declared: str) -> bool:
    """Whether one declared path is a real, non-empty file inside the worktree.

    Every way of not being one — absent, empty, a directory, a path that escapes
    the worktree, an unreadable one — is the same answer, because each of them
    means the same thing: nothing here proves the node did its work.
    """
    candidate = worktree / declared
    try:
        root = worktree.resolve()
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            return False
        return resolved.is_file() and resolved.stat().st_size > 0
    except OSError:
        return False
