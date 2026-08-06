"""The merge activities: US1's landing surface (plan.md § US1, contracts/activities.md).

These four activities are what the workflow calls to land a PASS node through
GitHub's merge queue. They run in `ActivityEnvironment` against a real target
repo (with a bare origin) and a `FakeGh` for the `gh` boundary — the runner seam
is the same kind as `open_bot` and `judge_transport`: tests replace the client
factory so no real network opens, and the activity still constructs the exact
`GhClient` arguments it would in production.

The properties these tests defend:

- **`open_landing_pr` pushes first, then creates a ready PR** (FR-001). The push
  has to precede the create, and the PR is never `--draft` — a draft PR does not
  enter the queue. It is idempotent: an existing open PR for the branch is
  reused, not duplicated (the queue can hold only one PR per head).
- **`enqueue_landing` issues exactly `gh pr merge <n> --auto --<method>`** from
  `LandingConfig` (FR-002). A queue-disabled refusal is returned as rejection
  data, never raised — the spec edge case the workflow routes to escalation.
- **`poll_landing` returns a `PrSnapshot`** — the classifier's input.
- **`disable_auto_merge` is best-effort**: a failure is reported, not raised.
- **No activity deletes any branch** (FR-008): the branch is the queue's to land.

Written before `factory/activities/merge_activities.py` exists (T015 precedes
T016): until the module lands, every test here fails at import.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities import merge_activities
from factory.mergequeue.models import PrSnapshot
from factory.workgraph import worktree as worktrees
from tests.fake_gh import FakeGh
from tests.target_repo import build_target_repo, git, git_env

EPIC = "003-merge-queue"
NODE = "us1"
BRANCH = f"factory/{EPIC}/{NODE}"
TITLE = f"{EPIC}/{NODE}: Land verified work"
PR_NUMBER = 7
MERGE_METHOD = "squash"
BASE = "main"
TARGET = "/srv/target"


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
def repo_with_origin(tmp_path: Path) -> Path:
    """A target repo with a bare origin remote, and a pushed default branch."""
    repo = build_target_repo(tmp_path / "target")
    origin = tmp_path / "origin.git"
    git(repo, "init", "--bare", str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "--quiet", "-u", "origin", "main")
    return repo


def _client_factory(fake: FakeGh, repo: Path):
    """A client factory wired to `fake` against `repo` — the test seam."""

    def factory(*, repo_path: str):
        from factory.mergequeue.gh import GhClient

        return GhClient(repo=repo_path, runner=fake)

    return factory


def _branch_exists_on_origin(repo: Path, branch: str) -> bool:
    origin = Path(git(repo, "remote", "get-url", "origin").strip())
    completed = subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", "--verify", "--quiet",
         f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return completed.returncode == 0


# --- open_landing_pr ----------------------------------------------------------


def _prepare_node_worktree(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build the node worktree where `push_branch` expects it and point env there.

    `open_landing_pr` pushes via `push_branch` with `FACTORY_ROOT` from env (the
    same resolver `agent_activities.factory_root()` uses). git resolves a
    relative worktree path against the target clone, so the root must be
    *absolute* — the test sets it to a temp dir, reproduces the worker layout at
    `<tmp>/.factory/worktrees/<epic>/<node>`, and points `FACTORY_ROOT` at it.
    """
    root = tmp_path
    monkeypatch.setenv("FACTORY_ROOT", str(root))
    prepared = worktrees.ensure(repo, EPIC, NODE, factory_root=root)
    worktree = Path(prepared.path)
    (worktree / "landed.txt").write_text("work\n", encoding="utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "node work")
    return worktree


async def test_open_landing_pr_pushes_then_creates_a_ready_pr(
    env: ActivityEnvironment, repo_with_origin: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Push first, create second — a PR for a branch origin does not have is useless."""
    _prepare_node_worktree(repo_with_origin, tmp_path, monkeypatch)

    fake = FakeGh()
    # Reuse lookup finds nothing, so the create happens.
    fake.expect_json(
        "pr", "list", "--head", BRANCH, "--state", "open", "--json", "number,url",
        payload=[],
    )
    fake.expect_json(
        "pr", "create", "--base", BASE, "--head", BRANCH, "--title", TITLE,
        "--body-file", "/tmp/body.md", payload={"number": PR_NUMBER, "url": "https://x/pull/7"},
    )
    monkeypatch.setattr(merge_activities, "_client_factory", _client_factory(fake, repo_with_origin))

    from factory.activities.merge_activities import (
        OpenLandingPrInput,
        open_landing_pr,
    )

    opened = await env.run(open_landing_pr, OpenLandingPrInput(
        epic_id=EPIC,
        node_id=NODE,
        target_repo=str(repo_with_origin),
        base=BASE,
        branch=BRANCH,
        title=TITLE,
        body_file="/tmp/body.md",
    ))

    assert opened.number == PR_NUMBER
    assert opened.url == "https://x/pull/7"
    # The branch reached origin — the push happened before the create.
    assert _branch_exists_on_origin(repo_with_origin, BRANCH)
    # Never draft.
    assert "--draft" not in [a for c in fake.calls for a in c.args]


async def test_open_landing_pr_is_idempotent_reusing_an_existing_pr(
    env: ActivityEnvironment, repo_with_origin: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An existing open PR for the branch is reused, not duplicated."""
    _prepare_node_worktree(repo_with_origin, tmp_path, monkeypatch)

    fake = FakeGh()
    fake.expect_json(
        "pr", "list", "--head", BRANCH, "--state", "open", "--json", "number,url",
        payload=[{"number": PR_NUMBER, "url": "https://x/pull/7"}],
    )
    monkeypatch.setattr(merge_activities, "_client_factory", _client_factory(fake, repo_with_origin))

    from factory.activities.merge_activities import (
        OpenLandingPrInput,
        open_landing_pr,
    )

    opened = await env.run(open_landing_pr, OpenLandingPrInput(
        epic_id=EPIC,
        node_id=NODE,
        target_repo=str(repo_with_origin),
        base=BASE,
        branch=BRANCH,
        title=TITLE,
        body_file="/tmp/body.md",
    ))

    assert opened.number == PR_NUMBER
    # No `gh pr create` was issued — only the reuse lookup.
    assert all("create" not in a for a in [c.args for c in fake.calls])


# --- enqueue_landing ----------------------------------------------------------


async def test_enqueue_landing_issues_auto_merge_from_config(
    env: ActivityEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeGh()
    fake.expect("pr", "merge", str(PR_NUMBER), "--auto", f"--{MERGE_METHOD}")
    monkeypatch.setattr(merge_activities, "_client_factory", _client_factory(fake, Path(TARGET)))

    from factory.activities.merge_activities import (
        EnqueueLandingInput,
        enqueue_landing,
    )

    result = await env.run(enqueue_landing, EnqueueLandingInput(
        pr_number=PR_NUMBER, merge_method=MERGE_METHOD, target_repo=TARGET
    ))

    assert result.rejected is False
    assert [(c.args, c.cwd) for c in fake.calls] == [
        (("pr", "merge", "7", "--auto", "--squash"), TARGET)
    ]


async def test_enqueue_landing_returns_a_queue_disabled_refusal_as_data(
    env: ActivityEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A queue-disabled enqueue is rejection data, never a crash (spec edge case)."""
    fake = FakeGh()
    fake.expect(
        "pr", "merge", str(PR_NUMBER), "--auto", f"--{MERGE_METHOD}",
        stderr="gh: error: merge queue is disabled for this repository", returncode=1,
    )
    monkeypatch.setattr(merge_activities, "_client_factory", _client_factory(fake, Path(TARGET)))

    from factory.activities.merge_activities import (
        EnqueueLandingInput,
        enqueue_landing,
    )

    result = await env.run(enqueue_landing, EnqueueLandingInput(
        pr_number=PR_NUMBER, merge_method=MERGE_METHOD, target_repo=TARGET
    ))

    assert result.rejected is True
    assert "merge queue is disabled" in result.reason


# --- poll_landing -------------------------------------------------------------


async def test_poll_landing_returns_a_pr_snapshot(
    env: ActivityEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = FakeGh.pr_view_payload(auto_merge=True)
    fake = FakeGh()
    fake.expect_json(
        "pr", "view", str(PR_NUMBER), "--json",
        "state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup",
        payload=payload,
    )
    monkeypatch.setattr(merge_activities, "_client_factory", _client_factory(fake, Path(TARGET)))

    from factory.activities.merge_activities import PollLandingInput, poll_landing

    snapshot = await env.run(poll_landing, PollLandingInput(pr_number=PR_NUMBER, target_repo=TARGET))

    assert isinstance(snapshot, PrSnapshot)
    assert snapshot.state == "OPEN"
    assert snapshot.auto_merge_requested is True


# --- disable_auto_merge -------------------------------------------------------


async def test_disable_auto_merge_is_best_effort(
    env: ActivityEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure to disable auto-merge is reported, never raised (kill path)."""
    fake = FakeGh()
    fake.expect(
        "pr", "merge", str(PR_NUMBER), "--disable-auto",
        stderr="gh: not found", returncode=1,
    )
    monkeypatch.setattr(merge_activities, "_client_factory", _client_factory(fake, Path(TARGET)))

    from factory.activities.merge_activities import DisableAutoMergeInput, disable_auto_merge

    result = await env.run(disable_auto_merge, DisableAutoMergeInput(pr_number=PR_NUMBER, target_repo=TARGET))

    # Best-effort: the call returned normally, reporting what happened.
    assert result.failed is True
    assert result.reason != ""


# --- structural guard (FR-008) ------------------------------------------------


def test_no_merge_activity_deletes_a_branch() -> None:
    """No activity in the merge surface deletes a branch — the queue's to land."""
    import inspect

    source = inspect.getsource(merge_activities)
    assert "delete-branch" not in source.lower()
