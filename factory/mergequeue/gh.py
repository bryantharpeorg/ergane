"""`GhClient`: the one place this component spawns `gh` (plan.md § US1).

The merge-queue component talks to GitHub through this client and only through
it. `gh` runs against the target clone — `cwd` is the clone, never a worktree
(FR-001) — with the same scrubbed environment the worktree operations use, so
no factory credential reaches the subprocess (constitution V).

The command surface is exactly the plan's table:

| operation | command |
|---|---|
| find existing PR | `gh pr list --head <branch> --state open --json number,url` |
| open PR | `gh pr create --base <default> --head <branch> --title <t> --body-file <f>` |
| enqueue | `gh pr merge <n> --auto --<merge_method>` |
| poll | `gh pr view <n> --json state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup` |
| kill cleanup | `gh pr merge <n> --disable-auto` |

Two structural guards hold here, and the tests assert them against the module
source so a future edit cannot silently widen the surface:

- **The only merge invocation is the queue's** (FR-002). `enqueue_pr` issues
  `gh pr merge --auto --<method>`; `disable_auto_merge` issues `--disable-auto`.
  There is no direct-merge form anywhere in this module.
- **No path ever requests branch deletion** (FR-008). The branch is the queue's
  to land; the node's cleanup never deletes it — the string the structural
  guard greps for must never appear in the commands this module builds.

Failures are classified into a small taxonomy rather than raised as generic
crashes, so an activity can catch them and return the refusal as data — an
enqueue rejected because the queue was disabled mid-flight is a queue rejection
routed to escalation (spec edge case), not a workflow failure.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

from factory.mergequeue.models import PrSnapshot
from factory.verify.gates import scrubbed_env

#: Failure taxonomy (plan.md § US1). A `GhError` carries one of these as `kind`.
GH_AUTH = "GH_AUTH"
GH_NOT_FOUND = "GH_NOT_FOUND"
GH_REFUSED = "GH_REFUSED"
GH_UNAVAILABLE = "GH_UNAVAILABLE"

#: The `gh pr view` field set that `poll_landing` needs — exactly the classifier's
#: inputs, nothing wider.
_VIEW_FIELDS = "state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup"

#: How much of a refused command's stderr is kept for the escalation to quote.
_STDERR_TAIL_LIMIT = 2048


class GhError(RuntimeError):
    """A classified `gh` failure — data an activity can return, not a crash.

    `kind` is one of the taxonomy constants; `stderr_tail` is the last of what
    `gh` printed, so `GH_REFUSED` is actionable without re-running the command.
    """

    def __init__(self, kind: str, message: str, stderr_tail: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.stderr_tail = stderr_tail


@dataclass(frozen=True)
class PrRef:
    """A PR's identity as `gh pr list --json` reports it."""

    number: int
    url: str


@dataclass(frozen=True)
class CreatedPr:
    """A PR's identity as `gh pr create --json` reports it."""

    number: int
    url: str


#: The runner seam: a callable `(argv: list[str], cwd: str) -> GhRunResult`.
#: The real `GhClient` uses `GhRunner` (subprocess); tests inject `FakeGh`.
class GhRunner(Protocol):
    def __call__(self, argv: Sequence[str], cwd: str) -> "GhRunResult": ...


@dataclass(frozen=True)
class GhRunResult:
    """What one `gh` invocation returned: stdout, stderr, and the exit code."""

    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class _Completed:
    """The minimal subprocess-completion shape the taxonomy reads."""

    stdout: str
    stderr: str
    returncode: int


class GhClient:
    """Runs `gh` against the target clone, parsing and classifying the results.

    `runner` is injectable so tests can script `gh` without a network; it
    defaults to a subprocess runner that spawns the real `gh` binary.
    """

    def __init__(
        self,
        *,
        repo: str,
        runner: Callable[..., Any] | None = None,
    ) -> None:
        self._repo = repo
        self._runner = runner if runner is not None else self._subprocess_runner

    # --- the command surface -------------------------------------------------

    def find_existing_pr(self, head: str) -> PrRef | None:
        """The open PR for `head`, if any — idempotency: reuse before create."""
        payload = self._run_json("pr", "list", "--head", head, "--state", "open",
                                 "--json", "number,url")
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            number = entry.get("number")
            url = entry.get("url")
            if number is None or url is None:
                continue
            return PrRef(number=int(number), url=str(url))
        return None

    def create_pr(
        self,
        *,
        base: str,
        head: str,
        title: str,
        body_file: str,
    ) -> CreatedPr:
        """Open a ready (never draft) PR; the body is passed via file (plan.md)."""
        payload = self._run_json(
            "pr", "create",
            "--base", base,
            "--head", head,
            "--title", title,
            "--body-file", body_file,
        )
        return CreatedPr(
            number=int(payload["number"]),
            url=str(payload["url"]),
        )

    def enqueue_pr(self, pr_number: int, *, merge_method: str) -> None:
        """Enqueue the PR through GitHub's merge queue (FR-002).

        This is the factory's *only* merge invocation — `--auto`, never a direct
        merge. No strategy flag rides along: a branch governed by a merge-queue
        ruleset owns its merge method (ours declares SQUASH), and gh refuses
        the flag outright — "The merge strategy for <branch> is set by the
        merge queue", proved live 2026-08-07 by the queue canary. The
        `merge_method` from `LandingConfig` stays as the operator's declared
        intent, which must match the queue's own configuration.
        """
        self._run("pr", "merge", str(pr_number), "--auto")

    def poll_pr(self, pr_number: int) -> PrSnapshot:
        """One `gh pr view` — the poll that becomes a classifier input."""
        payload = self._run_json("pr", "view", str(pr_number), "--json", _VIEW_FIELDS)
        return PrSnapshot.from_gh_json(payload, observed_at=_now_utc())

    def disable_auto_merge(self, pr_number: int) -> None:
        """Take the PR out of the queue — best-effort kill cleanup (FR-008)."""
        self._run("pr", "merge", str(pr_number), "--disable-auto")

    # --- US3 onboarding (FR-010) ---------------------------------------------

    def repo_view(self) -> dict[str, Any]:
        """The repo's identity and visibility, as `gh` resolves them from the clone.

        `gh repo view` resolves owner/repo from the clone's `origin` remote (the
        client runs with `cwd` = the clone), so the slug, visibility and default
        branch all come back in one call — the activity needs the slug to address
        the rules API, and the visibility/default-branch to judge the repo.
        """
        payload = self._run_json(
            "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef"
        )
        if not isinstance(payload, dict):
            raise GhError(
                GH_REFUSED, "gh repo view returned an unexpected JSON shape"
            )
        return payload

    def rules_for_branch(self, owner_repo: str, branch: str) -> list[dict[str, Any]]:
        """The branch rules list for `owner_repo`'s `branch` (the merge_queue rule).

        The `merge_queue` rule (when present) carries the required checks the
        queue will demand of a PR. `gh api` prints the endpoint's JSON verbatim,
        so a list is returned and the caller reads the merge-queue rule from it.
        """
        payload = self._run_json("api", f"repos/{owner_repo}/rules/branches/{branch}")
        if isinstance(payload, list):
            return [p for p in payload if isinstance(p, dict)]
        if isinstance(payload, dict):
            # Some endpoints nest under a key; tolerate it rather than guess.
            nested = payload.get("rules") or payload.get("branches")
            if isinstance(nested, list):
                return [p for p in nested if isinstance(p, dict)]
        raise GhError(
            GH_REFUSED, "gh api rules/branches returned an unexpected JSON shape"
        )

    def classic_branch_protection(self, owner_repo: str, branch: str) -> dict[str, Any]:
        """The classic branch-protection payload, when the rules list carries no checks.

        A repo that enables the queue but configures its required checks through
        the classic protection endpoint names none in the rules payload; this
        reads the `required_status_checks.contexts` fallback (plan.md § US3).
        """
        payload = self._run_json(
            "api", f"repos/{owner_repo}/branches/{branch}/protection"
        )
        if not isinstance(payload, dict):
            raise GhError(
                GH_REFUSED, "gh api branches/protection returned an unexpected JSON shape"
            )
        return payload

    # --- plumbing ------------------------------------------------------------

    def _run_json(self, *args: str) -> dict[str, Any] | list[Any]:
        result = self._run(*args)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GhError(
                GH_REFUSED,
                f"gh {' '.join(args)} returned non-JSON output",
                _tail(result.stderr),
            ) from exc
        if isinstance(payload, (dict, list)):
            return payload
        raise GhError(
            GH_REFUSED,
            f"gh {' '.join(args)} returned an unexpected JSON shape",
            _tail(result.stderr),
        )

    def _run(self, *args: str) -> GhRunResult:
        try:
            completed = self._runner(list(args), self._repo)
        except (OSError, subprocess.SubprocessError) as exc:
            raise GhError(
                GH_UNAVAILABLE,
                f"could not run gh {' '.join(args)} in {self._repo}: {exc}",
            ) from exc
        return self._classify(list(args), completed)

    @staticmethod
    def _classify(args: list[str], completed: Any) -> GhRunResult:
        """Turn a subprocess completion into a success or a classified `GhError`.

        `gh` exits non-zero for many reasons; only the ones an operator or the
        interpreter can act on are told apart. Everything else is `GH_REFUSED`
        carrying the stderr tail, because refusing is the one shape an activity
        can route to escalation as data.
        """
        result = GhRunResult(
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            returncode=int(completed.returncode),
        )
        if result.returncode == 0:
            return result

        stderr = result.stderr or result.stdout or ""
        tail = _tail(stderr)
        lower = stderr.lower()

        if "not authenticated" in lower or "auth" in lower and "401" in lower:
            raise GhError(GH_AUTH, f"gh {args}: not authenticated", tail)
        if "404" in lower or "not found" in lower:
            raise GhError(GH_NOT_FOUND, f"gh {args}: not found", tail)
        raise GhError(GH_REFUSED, f"gh {args} refused: {tail}", tail)

    def _subprocess_runner(self, argv: Sequence[str], cwd: str) -> _Completed:
        """The real runner: spawn `gh` in the target clone with a scrubbed env."""
        env = scrubbed_env() | {"GIT_TERMINAL_PROMPT": "0"}
        completed = subprocess.run(
            ["gh", *argv],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
        )
        return _Completed(
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )


def _tail(text: str, limit: int = _STDERR_TAIL_LIMIT) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    window = encoded[-limit:]
    return window.decode("utf-8", errors="ignore")


def _now_utc() -> str:
    """A UTC instant for `observed_at` — the subprocess has no clock worth trusting.

    Kept as the interpreter's own spelling (ISO 8601, `Z` suffix); the workflow
    stamps its own `observed_at` in production, this is only the fallback when
    the client is used directly.
    """
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
