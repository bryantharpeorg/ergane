"""`FakeGh`: a strict record/replay runner for the `gh` CLI (plan.md § Testing).

`GhClient` is the one place this component spawns `gh`, and it takes an
injectable runner so tests can script what `gh` would print without a real
network or a real repository. This is the same discipline as `FakeLiteLLM` in
`conftest.py`, applied to a subprocess runner rather than an HTTP transport:

- **Every invocation is scripted up front.** A test declares the argv it expects
  and the `(stdout, stderr, exit)` it should yield; running the runner is then a
  replay that either matches a scripted expectation or raises immediately. An
  unexpected command is a test failure, not a silent pass — the whole point is
  that the client only issues the commands the plan's table lists.
- **Every invocation is recorded in order, with its `cwd`.** Tests assert *what*
  was issued, in *which order*, from *which directory* — the `cwd` = target
  clone invariant is checked here because it is structural (FR-001: `gh` must
  run against the clone, never against a worktree).
- **Helpers script the canned `gh pr view --json` states.** The classifier's
  table turns on `state`/`mergedAt`/`closedAt`/`autoMergeRequest`/
  `mergeStateStatus`/`statusCheckRollup`, so this file ships builders for the
  payloads a poll test needs: merged, closed-unmerged, checks-failed, dirty,
  dequeued-clean, pending, stalled.

The runner's signature is `async (argv: list[str], cwd: str) -> Completed` where
`Completed` carries `stdout`, `stderr`, and `returncode` — the minimal shape the
client reads. A `FakeGhResult` with a non-zero `returncode` stands in for the
real `gh` refusing, which is how the failure-taxonomy tests (T007) get their
`GH_AUTH`/`GH_NOT_FOUND`/`GH_REFUSED`/`GH_UNAVAILABLE` without a real network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


@dataclass(frozen=True)
class FakeGhResult:
    """What a scripted `gh` invocation returns — stdout, stderr, exit code."""

    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


@dataclass(frozen=True)
class ScriptedCall:
    """One expected invocation: the argv prefix that must match, and its result."""

    args: tuple[str, ...]
    result: FakeGhResult


@dataclass
class RecordedInvocation:
    """One invocation the fake actually saw, in order, with its working directory."""

    args: tuple[str, ...]
    cwd: str


@dataclass
class FakeGh:
    """A strict scripted `gh`, recording every call the client makes.

    Expectations are matched as an argv *prefix* against the scripted `args`, so
    a test can pin the command's head (`gh pr merge 42 --auto --squash`) without
    re-encoding flag order. Unscripted calls raise immediately — the client only
    ever issues what the test planned for.
    """

    _expectations: list[ScriptedCall] = field(default_factory=list)
    calls: list[RecordedInvocation] = field(default_factory=list)

    #: A callable invoked for each new expectation index, if set — tests use it
    #: to replay a sequence of poll payloads.
    _on_match: Callable[[int], None] | None = None

    def __call__(self, argv: Sequence[str], cwd: str) -> FakeGhResult:
        """The runner entrypoint the client is handed.

        Matches against the next unconsumed expectation whose `args` is a prefix
        of `argv`; records the invocation (argv and cwd) regardless. Raises when
        no expectation matches — an unplanned command is a failed test.
        """
        args = tuple(argv)
        self.calls.append(RecordedInvocation(args=args, cwd=cwd))

        for index, expectation in enumerate(self._expectations):
            if args[: len(expectation.args)] == expectation.args:
                if self._on_match is not None:
                    self._on_match(index)
                return expectation.result

        raise AssertionError(
            f"unexpected gh invocation: {args} (cwd={cwd})\n"
            f"scripted expectations: {[e.args for e in self._expectations]}"
        )

    # --- scripting ----------------------------------------------------------

    def expect(
        self,
        *args: str,
        result: FakeGhResult | None = None,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ) -> None:
        """Script one invocation whose argv begins with `args`."""
        if result is None:
            result = FakeGhResult(stdout=stdout, stderr=stderr, returncode=returncode)
        self._expectations.append(ScriptedCall(args=args, result=result))

    def expect_json(self, *args: str, payload: Any) -> None:
        """Script an invocation that prints `payload` as JSON on stdout."""
        self.expect(*args, stdout=__import__("json").dumps(payload))

    def expect_error(self, *args: str, returncode: int = 1, stderr: str = "gh: refused") -> None:
        """Script an invocation that fails — the refusal path (T007)."""
        self.expect(*args, stderr=stderr, returncode=returncode)

    # --- helpers: canned `gh pr view --json` states -------------------------

    @staticmethod
    def pr_view_payload(
        *,
        state: str = "OPEN",
        is_draft: bool = False,
        merged_at: str | None = None,
        closed_at: str | None = None,
        merge_state_status: str = "CLEAN",
        auto_merge: bool = True,
        checks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """A `gh pr view <n> --json …` payload, shaped for `PrSnapshot.from_gh_json`.

        `checks` mirrors the `statusCheckRollup` entries: each is a `CheckRun`
        dict (`__typename`, `name`, `conclusion`) or a legacy `StatusCheckRollup`
        dict (`__typename`, `context`, `state`). `auto_merge` controls whether the
        `autoMergeRequest` object is present (a PR nobody enqueued has `null`).
        """
        rollup = checks if checks is not None else []
        return {
            "state": state,
            "isDraft": is_draft,
            "mergedAt": merged_at,
            "closedAt": closed_at,
            "mergeStateStatus": merge_state_status,
            "autoMergeRequest": {"enabledAt": "2026-08-06T10:00:00Z"} if auto_merge else None,
            "statusCheckRollup": rollup,
        }

    @classmethod
    def view_merged(cls, observed_at: str = "2026-08-06T10:10:00Z") -> dict[str, Any]:
        return cls.pr_view_payload(state="MERGED", merged_at="2026-08-06T10:09:00Z")

    @classmethod
    def view_closed_unmerged(cls, observed_at: str = "2026-08-06T10:10:00Z") -> dict[str, Any]:
        return cls.pr_view_payload(
            state="CLOSED", closed_at="2026-08-06T10:08:00Z", auto_merge=False
        )

    @classmethod
    def view_checks_failed(cls, observed_at: str = "2026-08-06T10:10:00Z") -> dict[str, Any]:
        return cls.pr_view_payload(
            state="OPEN",
            merge_state_status="CLEAN",
            auto_merge=False,
            checks=[
                {"__typename": "CheckRun", "name": "lint", "conclusion": "FAILURE"},
            ],
        )

    @classmethod
    def view_dirty(cls, observed_at: str = "2026-08-06T10:10:00Z") -> dict[str, Any]:
        return cls.pr_view_payload(
            state="OPEN", merge_state_status="DIRTY", auto_merge=False
        )

    @classmethod
    def view_dequeued_clean(cls, observed_at: str = "2026-08-06T10:10:00Z") -> dict[str, Any]:
        return cls.pr_view_payload(
            state="OPEN", merge_state_status="CLEAN", auto_merge=False, checks=[]
        )

    @classmethod
    def view_pending(cls, observed_at: str = "2026-08-06T10:10:00Z") -> dict[str, Any]:
        return cls.pr_view_payload(
            state="OPEN", merge_state_status="CLEAN", auto_merge=True, checks=[]
        )
