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

"Diff" means worktree-vs-`base_ref` — the ref the node branched from (D-027,
amending R7's worktree-vs-HEAD). R7 assumed the commit happens at salvage, after
verification; 005's prompt hands the agent the inner ralph contract, which says
commit as you go, and an agent that committed everything read as "no work" under
HEAD — while committed *out-of-scope* changes escaped this check entirely.
Callers that have no base (R7's original shape) pass `base_ref=None` and get
HEAD, which is only correct when nothing commits mid-attempt. Untracked files
count — new files are the normal shape of agent output — and ignored files do
not, which is what keeps generated noise from manufacturing the diff FR-004
demands.

**Some diffs are present and still unjudgeable** (045 FR-001). Overnight
2026-08-14→15 two agents committed their own session homes — `.ergane/homes/`,
18 files, 2.0 MB — into their worktrees, and the eight judge scorings that
followed read archive noise instead of code, each one confidently describing
work as absent that the truncation had hidden. Those files were *tracked*, and
a tracked file is invisible to `.gitignore`: prospectively fixing the ignore
list could not close the class, because every node whose base predates the fix
still commits the junk. So the refusal is the factory's own, it runs before a
judge token is spent, and it names what to remove — two rules, because the
incident needed both. The target's ignore rules are evaluated with `--no-index`
so tracked status cannot hide a match, and the runtime roots are refused by
prefix, since no ignore rule of any kind mentioned `.ergane/` on the night.

Hygiene examines the paths that are *in* the diff, never the worktree at large.
Untracked ignored files have never manufactured a diff and must not start
manufacturing a failure either — an attempt that ran its gates would otherwise
be refused for the log the gates themselves wrote. And it is asked of
diff-scoped nodes only (045 FR-008): a read node's verdict never consulted git,
so git can have no opinion about it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from factory.config import WriteScope
from factory.env import ERGANE_ROOT_ENV, FACTORY_ROOT_ENV, resolve_env_path
from factory.verify.gates import scrubbed_env
from factory.verify.models import HygieneViolation, OutputCheck
from factory.workgraph.worktree import DEFAULT_RUNTIME_ROOT, LEGACY_FACTORY_ROOT

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
    violations: Sequence[HygieneViolation] = (),
) -> bool:
    """The whole anti-rubber-stamp rule, with no filesystem in the way.

    `write_scope` may arrive as a plain string — it crosses the activity boundary
    as JSON — and a value outside `WriteScope` is a wiring bug rather than a
    licence: it never passes. `artifacts_present` is None when the node declared
    no artifacts, which is a pass for a diff scope with a diff and a failure for
    a read scope, whose only possible proof was the artifact.

    `violations` is the hygiene half (045 FR-001) and applies to diff scopes
    alone: a diff that carries paths nobody can judge is not a diff, however
    much of it there is. It defaults to empty so the rule this function stated
    before 045 is the rule it still states for every caller that has nothing to
    add.
    """
    scope = _as_scope(write_scope)
    if scope in DIFF_SCOPES:
        return has_diff and not violations
    if scope in ARTIFACT_SCOPES:
        return artifacts_present is True
    return False


def check_output(
    worktree: Path | str,
    write_scope: WriteScope | str,
    expected_artifacts: list[str] | tuple[str, ...] | None = None,
    base_ref: str | None = None,
) -> OutputCheck:
    """Read the worktree and decide whether this node proved it did work.

    Both halves of the evidence are always gathered, whichever one decides: the
    diff is recorded for read nodes and the artifacts for write nodes, so a
    verdict someone disputes later can be re-read from the record rather than
    re-derived from a worktree that is long gone.

    For a diff scope there are now two ways to fail: no diff at all, and a diff
    carrying paths nobody can judge (045 FR-001). Both express themselves as
    `passed=False` on this one record, so `judge_required` and `compose_result`
    keep deciding the verdict exactly where they already did — the moment two
    places can decide a FAIL, the stored row and the retry prompt can disagree.

    Raises `WorktreeMissingError` when the worktree is absent, or when git cannot
    read it — the diff or the ignore rules — and the scope's verdict depends on
    git.
    """
    worktree = Path(worktree)
    artifacts = list(expected_artifacts or ())

    if not worktree.is_dir():
        raise WorktreeMissingError(f"node worktree does not exist: {worktree}")

    scope = _as_scope(write_scope)
    changed = _changed_paths(
        worktree, required=scope not in ARTIFACT_SCOPES, base_ref=base_ref
    )
    has_diff = bool(changed)
    # Diff scopes only (FR-008): a read node is judged on its artifact, may have
    # no repository at all, and asking git about its paths would break the
    # `needs_worktree: false` personas rather than protect anybody.
    violations = (
        hygiene_violations(worktree, changed) if scope in DIFF_SCOPES else []
    )
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
            write_scope,
            has_diff=has_diff,
            artifacts_present=artifacts_present,
            violations=violations,
        ),
        hygiene_violations=violations,
    )


def runtime_root_prefixes() -> tuple[str, ...]:
    """Worktree-relative directory names that are the factory's, never a node's.

    Both names, always (FR-007). `.ergane/` is current and `.factory/` is
    legacy, and the population this check exists for is precisely the nodes
    whose base predates the rename: they cannot have the new name, and they
    cannot have the `.gitignore` that was fixed alongside it either. The names
    come from `factory.workgraph.worktree`'s own constants rather than from
    literals here, because 043/US2 exists because one module hardcoded a single
    root and the rename left it behind.

    An operator override is honoured too, but only when it names a
    repo-relative directory: an absolute runtime root lives outside every
    worktree and so can never appear in a node's diff.
    """
    names = {DEFAULT_RUNTIME_ROOT.name, LEGACY_FACTORY_ROOT.name}

    override = resolve_env_path(ERGANE_ROOT_ENV, FACTORY_ROOT_ENV, default="")
    if override != Path("") and not override.is_absolute() and override.parts:
        names.add(override.parts[0])

    return tuple(sorted(names))


def hygiene_violations(
    worktree: Path | str, paths: Sequence[str]
) -> list[HygieneViolation]:
    """Which of `paths` the diff may not carry, and the rule that refused each.

    `paths` is the diff's own path list, so nothing on disk is discovered here:
    build noise the agent never staged is not the agent's work in either
    direction (trap 2). Order follows `paths`, and the ignore rule is preferred
    over the runtime-root prefix when both match, because "your repository
    already ignores this" is the more actionable of the two answers.

    Raises `WorktreeMissingError` when git cannot answer the ignore question —
    an unreadable exclude file is an infrastructure failure, and returning an
    empty list would be the pass-by-default this component refuses everywhere
    else (FR-006).
    """
    ordered = list(dict.fromkeys(paths))
    if not ordered:
        return []

    matched = _ignore_matches(Path(worktree), ordered)
    prefixes = runtime_root_prefixes()

    violations = []
    for path in ordered:
        rule = matched.get(path) or _runtime_root_rule(path, prefixes)
        if rule is not None:
            violations.append(HygieneViolation(path=path, rule=rule))
    return violations


def _as_scope(value: WriteScope | str) -> WriteScope | None:
    """The registry member `value` names, or None if the registry has no such scope."""
    try:
        return WriteScope(value)
    except ValueError:
        return None


def _changed_paths(
    worktree: Path, *, required: bool, base_ref: str | None = None
) -> list[str]:
    """Every path this attempt changed — uncommitted and committed, in that order.

    An empty list is the clean worktree, which is what `has_diff` reads off this;
    the paths themselves are what hygiene is asked about (FR-001), and that is
    why both halves are collected rather than short-circuited the moment one of
    them is non-empty — the 2026-08-14 homes were committed, so a check that
    stopped at a dirty `status` would never have seen them. Both reads are `-z`,
    so a path with a space or a quote in it arrives intact rather than as git's
    quoted rendering of itself.

    `required` says whether git is allowed to fail: for a scope the diff decides,
    an unreadable repository raises rather than reporting the clean worktree it
    looks like; for a read scope it is merely unrecorded, since a
    `needs_worktree: false` persona may have no repository at all.
    """
    status = _git(worktree, "status", "--porcelain", "-z", "--untracked-files=all")
    if status is None:
        if required:
            raise WorktreeMissingError(
                f"git could not read the node worktree: {worktree}"
            )
        return []

    paths = _status_paths(status)

    # Porcelain covers the uncommitted half; the committed half is everything
    # the attempt landed on the node branch since its base (D-027) — with no
    # base to compare against, HEAD, which R7's original semantics called an
    # empty diff. A failure here can only be an unborn branch or a base that has
    # gone missing — status just succeeded — so it is not fatal either way.
    committed = _git(worktree, "diff", base_ref or "HEAD", "--name-only", "-z")
    if committed:
        paths.extend(path for path in committed.split("\0") if path)

    return list(dict.fromkeys(paths))


def _status_paths(raw: str) -> list[str]:
    """The paths out of `git status --porcelain -z` output.

    Each record is `XY <path>` terminated by NUL; a rename or copy is followed by
    one more NUL-terminated field naming where the file came from, and both ends
    of it are changed paths. Without `-z` this would have to un-quote git's own
    escaping, which is the kind of parsing that works until a filename has a
    backslash in it.
    """
    fields = raw.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if len(record) <= 3:
            continue
        code, path = record[:2], record[3:]
        paths.append(path)
        if "R" in code or "C" in code:
            if index < len(fields) and fields[index]:
                paths.append(fields[index])
            index += 1
    return paths


def _ignore_matches(worktree: Path, paths: Sequence[str]) -> dict[str, str]:
    """Path → `<source>:<line>:<pattern>` for each path the ignore rules refuse.

    `--no-index` is the whole mechanism (trap 1): without it git consults the
    index first and reports a *tracked* file as unmatched, which is precisely the
    2026-08-14 case — the session homes were committed, so every one of them
    would have come back clean. `--stdin -z` keeps the query off the command line,
    where a large diff would eventually exceed the argument limit, and keeps
    awkward filenames intact in both directions.

    Exit 1 is git's answer for "none of these match" and is a real answer; every
    other failure is git declining to answer at all, and the caller turns that
    into `WorktreeMissingError` rather than into a pass.
    """
    payload = "".join(f"{path}\0" for path in paths)
    raw = _git(
        worktree,
        "check-ignore",
        "--verbose",
        "--no-index",
        "-z",
        "--stdin",
        stdin=payload,
        allowed_codes=(0, 1),
    )
    if raw is None:
        raise WorktreeMissingError(
            f"git could not read the ignore rules of the node worktree: {worktree}"
        )

    # `-v -z` emits one NUL-terminated quad per matching path: source, line
    # number, pattern, pathname. Non-matching paths emit nothing at all.
    fields = raw.split("\0")
    matches: dict[str, str] = {}
    for index in range(0, len(fields) - 3, 4):
        source, line, pattern, path = fields[index : index + 4]
        matches[path] = f"{source}:{line}:{pattern}"
    return matches


def _runtime_root_rule(path: str, prefixes: Sequence[str]) -> str | None:
    """The runtime root `path` sits under, if any — the rule gitignore never had.

    Matched on the leading path component so `.ergane/homes/…` is refused and
    `.ergane-detector/…` is not: a directory whose name merely starts with a
    root's name is a different directory.
    """
    head = path.split("/", 1)[0]
    return f"runtime root: {head}/" if head in prefixes else None


def _git(
    worktree: Path,
    *args: str,
    stdin: str | None = None,
    allowed_codes: tuple[int, ...] = (0,),
) -> str | None:
    """Run one read-only git command in `worktree`; None if git could not answer.

    The environment is the gate runner's allowlist (constitution V) — a
    subprocess the factory spawns gets no factory credentials, and dropping
    `GIT_DIR`/`GIT_WORK_TREE` along with them keeps the worker's own environment
    from redirecting the read. `GIT_OPTIONAL_LOCKS=0` stops a check that is only
    ever asking a question from taking the index lock to answer it.

    `allowed_codes` exists because one caller needs an exit code that is an
    answer rather than a failure: `check-ignore` reports "nothing matched" as
    exit 1, and collapsing that into None would make an unreadable exclude file
    indistinguishable from a clean diff.
    """
    env = scrubbed_env() | {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
    try:
        completed = subprocess.run(
            ["git", "-C", str(worktree), *args],
            capture_output=True,
            text=True,
            input=stdin,
            env=env,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode in allowed_codes else None


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
