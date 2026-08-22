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
- **No path ever asks a landing command to take the branch with it** (FR-008).
  The branch is the queue's to land; the node's cleanup never deletes it. `gh`'s
  delete-branch flag is what would, so that flag must never appear in the
  commands this module builds — the structural guard greps for the literal, and
  this file may not spell it even in prose.

  069-US3 added the one act that removes a ref, and it is deliberately none of
  the above: `remove_ref` addresses `refs/heads/factory/<epic>/<node>` by name,
  on the reset path, after the epic is terminated (`ergane build reset` refuses
  while the workflow is running) and after `create_ref` has put the tip beyond
  reach of loss. It is not a flag riding along with a landing, which is the
  thing the guard exists to keep out.

Failures are classified into a small taxonomy rather than raised as generic
crashes, so an activity can catch them and return the refusal as data — an
enqueue rejected because the queue was disabled mid-flight is a queue rejection
routed to escalation (spec edge case), not a workflow failure.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

from factory.mergequeue.models import CheckFailure, PrSnapshot
from factory.verify.gates import scrubbed_env

#: Failure taxonomy (plan.md § US1). A `GhError` carries one of these as `kind`.
GH_AUTH = "GH_AUTH"
GH_NOT_FOUND = "GH_NOT_FOUND"
GH_REFUSED = "GH_REFUSED"
GH_UNAVAILABLE = "GH_UNAVAILABLE"

#: The `gh pr view` field set that `poll_landing` needs — exactly the classifier's
#: inputs, nothing wider. `baseRefOid` is 069-US1's: the head this PR is offered
#: against right now, which is what says whether a sibling landed under a tree
#: the queue was already testing. Without it every rejection reads as the node's
#: own fault and the free rebase never fires in production, however green the
#: suite is.
_VIEW_FIELDS = (
    "state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,"
    "statusCheckRollup,baseRefOid"
)

#: The `_VIEW_FIELDS` entries this factory knowingly sends ahead of the oldest
#: `gh` still in the wild — the ones a sufficiently old binary will not declare.
#: `baseRefOid` reached `gh pr view` well after the rest of the set, so a host
#: whose `gh` predates it is behind this tree rather than in conflict with it.
#:
#: This is deliberately **not** a second copy of the field set (078 trap 5) and
#: deliberately **not** a `gh` version number. It is the strictly smaller set of
#: fields whose absence from a host's `gh` is a fact about that host, and
#: `tests/test_gh_argv_contract.py` both holds it to being a subset of
#: `_VIEW_FIELDS` and refuses to excuse anything outside it: a field named here
#: degrades explicitly when the local `gh` lacks it, and a field *not* named
#: here — a typo, a rename, an invention — fails the suite on every host. Adding
#: a name here is therefore a claim that the field is real and merely new, and
#: it is the only way to make the check tolerate its absence.
_VERSION_SENSITIVE_VIEW_FIELDS = frozenset({"baseRefOid"})

#: How much of a refused command's stderr is kept for the escalation to quote.
_STDERR_TAIL_LIMIT = 2048

#: US2: how much of one failing check's log tail is quoted in the recovery prompt.
#: pytest and most CI tools print the failure summary last, so the tail is the
#: useful part; this bound keeps one oversized check from blowing the context.
_FAILED_LOG_PER_CHECK_LIMIT = 4096

#: US2: how much log tail is quoted across all failing checks combined.
_FAILED_LOG_TOTAL_LIMIT = 8192


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


@dataclass(frozen=True)
class PrCheckEntry:
    """US1: one row from `gh pr view --json statusCheckRollup`."""

    name: str
    state: str
    link: str


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
        """Open a ready (never draft) PR; the body is passed via file (plan.md).

        `gh pr create` prints the created PR's URL on stdout, not JSON, so the
        number is derived from that URL. A follow-up `find_existing_pr(head)` is
        avoided here: it is a second network round-trip and a second chance to
        fail, and the URL `gh` prints is the authoritative answer (FR-008).
        """
        result = self._run(
            "pr", "create",
            "--base", base,
            "--head", head,
            "--title", title,
            "--body-file", body_file,
        )
        url = result.stdout.strip()
        number = _pr_number_from_url(url)
        if number is None:
            raise GhError(
                GH_REFUSED,
                f"gh pr create printed an unrecognised URL: {url!r}",
                _tail(result.stderr),
            )
        return CreatedPr(number=number, url=url)

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

    # --- US2 check-failure evidence (FR-005/006/007) -------------------------

    def pr_checks(self, pr_number: int) -> tuple[PrCheckEntry, ...]:
        """The checks table for a PR: name, state, and run link.

        `gh pr checks` has no `--json` flag, so this reads the same data from
        `gh pr view --json statusCheckRollup`. The rollup mixes CheckRun entries
        (`conclusion`, `detailsUrl`) with legacy StatusContext entries
        (`state`, `targetUrl`); an unrecognised entry is skipped so the rest of
        the batch still returns evidence (FR-005).
        """
        payload = self._run_json(
            "pr", "view", str(pr_number), "--json", "statusCheckRollup"
        )
        rollup = payload.get("statusCheckRollup") if isinstance(payload, dict) else None
        if not isinstance(rollup, list):
            return ()
        entries: list[PrCheckEntry] = []
        for entry in rollup:
            if not isinstance(entry, dict):
                continue
            typename = entry.get("__typename")
            if typename == "CheckRun":
                name = entry.get("name")
                state = entry.get("conclusion")
                link = entry.get("detailsUrl")
            elif typename in ("StatusCheckRollup", "StatusContext"):
                name = entry.get("context")
                state = entry.get("state")
                link = entry.get("targetUrl")
            else:
                continue
            if name is None or state is None or link is None:
                continue
            entries.append(
                PrCheckEntry(
                    name=str(name), state=str(state), link=str(link)
                )
            )
        return tuple(entries)

    def run_failed_log(self, run_id: str) -> str:
        """The failing-step log for one run, bounded to the per-check limit."""
        result = self._run("run", "view", str(run_id), "--log-failed")
        return _tail(result.stdout, _FAILED_LOG_PER_CHECK_LIMIT)

    # --- 069-US3 reset cleanup (FR-010) --------------------------------------

    def close_pr(self, pr_number: int, *, comment: str) -> None:
        """`gh pr close <n> --comment <text>` — end it, and say what ended it.

        The comment is a parameter rather than a default because the only caller
        is a reset, and an operator who finds a closed PR has to be able to read
        which one closed it. `gh`'s delete-branch flag is not passed and never
        may be (FR-008): the ref is removed by name below, after its tip is
        archived.
        """
        self._run("pr", "close", str(pr_number), "--comment", comment)

    def ref_sha(self, owner_repo: str, ref: str) -> str | None:
        """What `refs/<ref>` points at, or `None` when the repo has no such ref.

        `ref` is spelled the way the git-refs API wants it — `heads/<branch>` —
        so a branch name carrying slashes needs no escaping. A 404 is an answer
        here, not a failure: "the head is already gone" is the state a second
        reset finds.
        """
        try:
            payload = self._run_json("api", f"repos/{owner_repo}/git/ref/{ref}")
        except GhError as error:
            if error.kind == GH_NOT_FOUND:
                return None
            raise
        obj = payload.get("object") if isinstance(payload, dict) else None
        sha = obj.get("sha") if isinstance(obj, dict) else None
        return str(sha) if sha else None

    def create_ref(self, owner_repo: str, ref: str, sha: str) -> None:
        """Point `refs/<ref>` at `sha` for the first time — the archive write."""
        self._run(
            "api", "-X", "POST", f"repos/{owner_repo}/git/refs",
            "-f", f"ref=refs/{ref}", "-f", f"sha={sha}",
        )

    def remove_ref(self, owner_repo: str, ref: str) -> None:
        """Remove `refs/<ref>`. Issued only by reset, only for a node head, and
        only once that head's tip is reachable from an archive ref (FR-010)."""
        self._run("api", "-X", "DELETE", f"repos/{owner_repo}/git/refs/{ref}")

    # --- US3 onboarding (FR-010) ---------------------------------------------

    def repo_view(self) -> dict[str, Any]:
        """The repo's identity, visibility and ownership, as `gh` resolves them.

        `gh repo view` resolves owner/repo from the clone's `origin` remote (the
        client runs with `cwd` = the clone), so the slug, visibility and default
        branch all come back in one call — the activity needs the slug to address
        the rules API, and the visibility/default-branch to judge the repo.

        `isInOrganization` is added here (US2, FR-008) so the wiring precondition
        can decide merge-queue eligibility from owner type and visibility together
        without a second `gh` invocation.
        """
        payload = self._run_json(
            "repo", "view", "--json",
            "nameWithOwner,visibility,isInOrganization,defaultBranchRef"
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

    def merge_settings(self, owner_repo: str) -> dict[str, Any]:
        """The repo-level merge settings payload (`gh api repos/{owner_repo}`).

        `gh repo view --json` cannot express `squash_merge_commit_title` (its
        field set has `squashMergeAllowed` but no title source), so this reads the
        REST repo endpoint directly. The setting is repo-scoped, not branch-scoped.
        """
        payload = self._run_json("api", f"repos/{owner_repo}")
        if not isinstance(payload, dict):
            raise GhError(
                GH_REFUSED, "gh api repos returned an unexpected JSON shape"
            )
        return payload

    # --- 034/US3 wiring: the writes that make a repo dispatchable -------------

    def auth_status(self) -> str:
        """`gh auth status` — the prerequisite probe, and a read.

        Wiring calls this first so "gh is missing" and "gh is not logged in" are
        refusals, not a traceback halfway through a half-applied change. An
        absent binary surfaces as `GH_UNAVAILABLE` (the runner's `OSError`).
        """
        return self._run("auth", "status").stdout

    def set_squash_merge_commit_title(self, owner_repo: str, value: str) -> None:
        """Set the repo's squash-merge title source; repo-scoped, and read back
        through `merge_settings` — which is what `evaluate_repo` judges."""
        self._run(
            "api", "-X", "PATCH", f"repos/{owner_repo}",
            "-f", f"squash_merge_commit_title={value}",
        )

    def set_allow_auto_merge(self, owner_repo: str, value: bool) -> None:
        """Set the repo's `allow_auto_merge` flag — a precondition for the queue
        driver's only merge invocation, `gh pr merge --auto`.
        """
        self._run(
            "api", "-X", "PATCH", f"repos/{owner_repo}",
            "-f", f"allow_auto_merge={str(value).lower()}",
        )

    def list_rulesets(self, owner_repo: str) -> list[dict[str, Any]]:
        """The repo's branch rulesets, as summaries (`id`, `name`, `target`)."""
        payload = self._run_json("api", f"repos/{owner_repo}/rulesets")
        if isinstance(payload, list):
            return [p for p in payload if isinstance(p, dict)]
        raise GhError(GH_REFUSED, "gh api rulesets returned an unexpected JSON shape")

    def ruleset(self, owner_repo: str, ruleset_id: int) -> dict[str, Any]:
        """One ruleset in full — its conditions and its rules, which summaries omit."""
        payload = self._run_json("api", f"repos/{owner_repo}/rulesets/{ruleset_id}")
        if not isinstance(payload, dict):
            raise GhError(
                GH_REFUSED, "gh api rulesets/<id> returned an unexpected JSON shape"
            )
        return payload

    def create_ruleset(self, owner_repo: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a branch ruleset from `payload`, returning what GitHub stored."""
        with _json_body(payload) as body_file:
            created = self._run_json(
                "api", "-X", "POST", f"repos/{owner_repo}/rulesets",
                "--input", body_file,
            )
        return created if isinstance(created, dict) else {}

    def update_ruleset(
        self, owner_repo: str, ruleset_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Replace a branch ruleset's contents with `payload`."""
        with _json_body(payload) as body_file:
            updated = self._run_json(
                "api", "-X", "PUT", f"repos/{owner_repo}/rulesets/{ruleset_id}",
                "--input", body_file,
            )
        return updated if isinstance(updated, dict) else {}

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


@contextlib.contextmanager
def _json_body(payload: dict[str, Any]):
    """Write `payload` to a temp file and yield its absolute path, then remove it.

    `gh api --input <file>` is how the nested rulesets payload is sent: `-f`
    fields express only a flat mapping, and the runner seam is `(argv, cwd)` with
    no stdin. `create_pr` passes its body the same way (`--body-file`). The path
    is absolute because the client's `cwd` is the target clone.
    """
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False
    )
    try:
        json.dump(payload, handle)
        handle.close()
        yield handle.name
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


def _tail(text: str, limit: int = _STDERR_TAIL_LIMIT) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    window = encoded[-limit:]
    return window.decode("utf-8", errors="ignore")


_RUN_ID_RE = __import__("re").compile(r"/actions/runs/(\d+)")

#: US2: extract the PR number from the URL `gh pr create` prints on stdout.
_PR_NUMBER_RE = __import__("re").compile(r"/pull/(\d+)")


def _parse_run_id(link: str) -> str | None:
    """US2: extract the run id from a GitHub Actions run link, if present."""
    match = _RUN_ID_RE.search(link)
    if match is None:
        return None
    return match.group(1)


def _pr_number_from_url(url: str) -> int | None:
    """US2: extract the PR number from the URL `gh pr create` prints."""
    match = _PR_NUMBER_RE.search(url)
    if match is None:
        return None
    return int(match.group(1))


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
