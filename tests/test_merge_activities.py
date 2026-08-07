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


# --- sync_landing_branch (US2 recovery, plan.md § US2) ------------------------


def _advance_and_push(repo: Path) -> str:
    """Land a commit on the target clone's `main` and push it to origin."""
    (repo / "README.md").write_text("moved on\n", encoding="utf-8")
    git(repo, "commit", "--quiet", "-a", "-m", "someone else landed work")
    git(repo, "push", "--quiet", "origin", "main")
    return git(repo, "rev-parse", "HEAD").strip()


def _node_worktree_with_work(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A prepared node worktree with a commit on the branch, pushed to origin."""
    root = tmp_path
    monkeypatch.setenv("FACTORY_ROOT", str(root))
    prepared = worktrees.ensure(repo, EPIC, NODE, factory_root=root)
    worktree = Path(prepared.path)
    (worktree / "landed.txt").write_text("work\n", encoding="utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "node work")
    worktrees.push_branch(repo, EPIC, NODE, factory_root=root)
    return worktree


def _node_worktree_editing_calc(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A node worktree whose work edits `src/calc.py` — the target will too.

    A conflict needs both sides to touch the same tracked file; this is the shape
    that produces one.
    """
    root = tmp_path
    monkeypatch.setenv("FACTORY_ROOT", str(root))
    prepared = worktrees.ensure(repo, EPIC, NODE, factory_root=root)
    worktree = Path(prepared.path)
    (worktree / "src/calc.py").write_text(
        "def add(left, right):\n    return left + right + 1\n", encoding="utf-8"
    )
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "node edits calc")
    worktrees.push_branch(repo, EPIC, NODE, factory_root=root)
    return worktree


async def test_sync_landing_branch_reports_a_clean_base_ref(
    env: ActivityEnvironment, repo_with_origin: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean recovery sync returns the merged-in target head as the base_ref."""
    _node_worktree_with_work(repo_with_origin, tmp_path, monkeypatch)
    target_head = _advance_and_push(repo_with_origin)

    from factory.activities.merge_activities import (
        SyncLandingBranchInput,
        sync_landing_branch,
    )

    result = await env.run(sync_landing_branch, SyncLandingBranchInput(
        epic_id=EPIC, node_id=NODE, target_repo=str(repo_with_origin)
    ))

    assert result.clean is True
    assert result.base_ref == target_head
    assert result.conflicted_files == ()
    assert result.refused is False


async def test_sync_landing_branch_reports_a_conflict_as_data(
    env: ActivityEnvironment, repo_with_origin: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A conflicting sync surfaces clean=False with the conflicted file list."""
    _node_worktree_editing_calc(repo_with_origin, tmp_path, monkeypatch)
    (repo_with_origin / "src/calc.py").write_text(
        "def add(left, right):\n    return left + right + 2\n", encoding="utf-8"
    )
    git(repo_with_origin, "commit", "--quiet", "-a", "-m", "target edits calc")
    git(repo_with_origin, "push", "--quiet", "origin", "main")

    from factory.activities.merge_activities import (
        SyncLandingBranchInput,
        sync_landing_branch,
    )

    result = await env.run(sync_landing_branch, SyncLandingBranchInput(
        epic_id=EPIC, node_id=NODE, target_repo=str(repo_with_origin)
    ))

    assert result.clean is False
    assert "src/calc.py" in result.conflicted_files
    # A conflict is a reportable outcome, not a crash.
    assert result.refused is False


async def test_recovery_reenqueue_reuses_the_same_pr(
    env: ActivityEnvironment, repo_with_origin: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a recovery sync, re-opening lands on the same PR — never a duplicate.

    The queue holds one PR per head; a recovery that opened a second PR for the
    same branch would strand a live PR and split the queue's attention. The
    idempotent open reuses the existing PR, and the re-enqueue rides that number.
    """
    _node_worktree_with_work(repo_with_origin, tmp_path, monkeypatch)
    _advance_and_push(repo_with_origin)

    fake = FakeGh()
    # The reuse lookup finds the existing open PR — no `pr create` follows.
    fake.expect_json(
        "pr", "list", "--head", BRANCH, "--state", "open", "--json", "number,url",
        payload=[{"number": PR_NUMBER, "url": "https://x/pull/7"}],
    )
    fake.expect("pr", "merge", str(PR_NUMBER), "--auto", f"--{MERGE_METHOD}")
    monkeypatch.setattr(merge_activities, "_client_factory", _client_factory(fake, repo_with_origin))

    from factory.activities.merge_activities import (
        EnqueueLandingInput,
        OpenLandingPrInput,
        SyncLandingBranchInput,
        enqueue_landing,
        open_landing_pr,
        sync_landing_branch,
    )

    synced = await env.run(sync_landing_branch, SyncLandingBranchInput(
        epic_id=EPIC, node_id=NODE, target_repo=str(repo_with_origin)
    ))
    assert synced.clean is True

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
    assert all("create" not in a for a in [c.args for c in fake.calls])

    enqueued = await env.run(enqueue_landing, EnqueueLandingInput(
        pr_number=opened.number, merge_method=MERGE_METHOD, target_repo=str(repo_with_origin)
    ))
    assert enqueued.rejected is False


async def test_sync_landing_branch_surfaces_a_git_failure_as_data(
    env: ActivityEnvironment, repo_with_origin: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recovery sync that cannot run is a refusal, never a silent pass.

    A missing worktree (the node was never prepared) or a wedged git should
    surface with the reason, so the workflow can route to escalation rather than
    read a fake success. The reason carries the stderr tail from the underlying
    git failure.
    """
    # No worktree prepared: the sync must refuse with a reason, not crash.
    from factory.activities.merge_activities import (
        SyncLandingBranchInput,
        sync_landing_branch,
    )

    result = await env.run(sync_landing_branch, SyncLandingBranchInput(
        epic_id=EPIC, node_id=NODE, target_repo=str(repo_with_origin)
    ))

    assert result.refused is True
    assert result.reason != ""
    assert "worktree" in result.reason.lower()


# --- validate_target_repo (US3 onboarding, FR-010) ---------------------------


def _onboard_client_factory(fake: FakeGh, repo: Path):
    """A client factory wired to `fake` against `repo`, plus the gh surface scripted.

    `validate_target_repo` resolves the owner/repo slug from the clone's `origin`
    remote, reads repo facts with `gh repo view`, and reads the merge-queue rule
    (with a classic-protection fallback) from the rules API. This wires a fake so
    the activity constructs the exact `GhClient` it would in production.
    """

    def factory(*, repo_path: str):
        from factory.mergequeue.gh import GhClient

        return GhClient(repo=repo_path, runner=fake)

    return factory


def _fake_gh_conforming(fake: FakeGh, repo: Path, default_branch: str = "main") -> None:
    """Script `gh` for a fully conforming repo: public, queue enabled, checks match.

    The fixture repo declares gates `lint`, `test`, `typecheck`; the scripted
    queue requires checks of exactly those names. The rules payload carries a
    `merge_queue` rule with the required checks and no classic-protection
    fallback needed. The slug is read from the same `repo view` call (gh resolves
    the repo from the clone's cwd), so `owner/repo` for the rules API comes from
    `nameWithOwner`.
    """
    fake.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={
            "nameWithOwner": "OWNER/REPO",
            "visibility": "PUBLIC",
            # The real gh returns an object here, not a bare string — the
            # 2026-08-07 onboarding run against bryantharpeorg/ergane proved it,
            # after string-shaped fakes had hidden the parse bug.
            "defaultBranchRef": {"name": default_branch},
        },
    )
    fake.expect_json(
        "api", f"repos/OWNER/REPO/rules/branches/{default_branch}",
        payload=[
            {
                "type": "merge_queue",
                "parameters": {"required_status_checks": [
                    {"context": "lint"},
                    {"context": "test"},
                    {"context": "typecheck"},
                ]},
            }
        ],
    )


async def test_validate_target_repo_gathers_repo_facts_and_loads_the_manifest(
    env: ActivityEnvironment, repo_with_origin: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A conforming repo passes: repo facts + rules + the clone's factory.yaml.

    `validate_target_repo` reads the repo's committed `factory.yaml` (the
    fixture's declares `lint`/`test`/`typecheck`), gathers visibility and the
    queue rule from `gh`, and returns a profile whose checks all pass.
    """
    fake = FakeGh()
    _fake_gh_conforming(fake, repo_with_origin)
    monkeypatch.setattr(merge_activities, "_client_factory", _onboard_client_factory(fake, repo_with_origin))

    from factory.activities.merge_activities import (
        ValidateTargetRepoInput,
        validate_target_repo,
    )

    profile = await env.run(validate_target_repo, ValidateTargetRepoInput(
        target_repo=str(repo_with_origin)
    ))

    assert profile.passed is True
    assert profile.visibility == "PUBLIC"
    assert profile.default_branch == "main"
    assert profile.queue_enabled is True
    assert set(profile.declared_gates) == {"lint", "test", "typecheck"}
    assert set(profile.required_checks) == {"lint", "test", "typecheck"}
    checks = [f.check for f in profile.findings]
    assert "visibility" in checks
    assert "merge_queue" in checks
    assert "factory_yaml" in checks
    assert all(f.passed for f in profile.findings)


async def test_validate_target_repo_reports_a_queue_missing_repo_as_failing(
    env: ActivityEnvironment, repo_with_origin: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No merge_queue rule on the default branch is a failing finding, not a crash.

    The rules list is empty, so the queue is not enabled and the profile fails
    with a finding naming the branch.
    """
    fake = FakeGh()
    fake.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={"nameWithOwner": "OWNER/REPO", "visibility": "PUBLIC", "defaultBranchRef": {"name": "main"}},
    )
    fake.expect_json(
        "api", "repos/OWNER/REPO/rules/branches/main", payload=[]
    )
    monkeypatch.setattr(merge_activities, "_client_factory", _onboard_client_factory(fake, repo_with_origin))

    from factory.activities.merge_activities import (
        ValidateTargetRepoInput,
        validate_target_repo,
    )

    profile = await env.run(validate_target_repo, ValidateTargetRepoInput(
        target_repo=str(repo_with_origin)
    ))

    assert profile.passed is False
    queue_finding = next(f for f in profile.findings if f.check == "merge_queue")
    assert queue_finding.passed is False
    assert "main" in queue_finding.detail


async def test_validate_target_repo_falls_back_to_classic_protection_for_checks(
    env: ActivityEnvironment, repo_with_origin: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the rules list carries no required checks, the classic endpoint is asked.

    A repo that enables the queue but configures required checks via the classic
    branch-protection endpoint carries none in the rules payload; the activity
    must fall back to `repos/{owner}/{repo}/branches/{default}/protection` for the
    `required_status_checks.contexts`. The queue rule present but the checks
    absent means the activity reads them from the classic endpoint.
    """
    fake = FakeGh()
    fake.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={"nameWithOwner": "OWNER/REPO", "visibility": "PUBLIC", "defaultBranchRef": {"name": "main"}},
    )
    # Rules list has a merge_queue rule but no required checks within it.
    fake.expect_json(
        "api", "repos/OWNER/REPO/rules/branches/main",
        payload=[{"type": "merge_queue", "parameters": {"required_status_checks": []}}],
    )
    # Classic-protection fallback names the checks.
    fake.expect_json(
        "api", "repos/OWNER/REPO/branches/main/protection",
        payload={"required_status_checks": {"contexts": ["test"]}},
    )
    monkeypatch.setattr(merge_activities, "_client_factory", _onboard_client_factory(fake, repo_with_origin))

    from factory.activities.merge_activities import (
        ValidateTargetRepoInput,
        validate_target_repo,
    )

    profile = await env.run(validate_target_repo, ValidateTargetRepoInput(
        target_repo=str(repo_with_origin)
    ))

    # The fixture declares gates lint/test/typecheck; classic protection only
    # names `test`, so the declared-but-unchecked gates fail (deterministic-only
    # and every-gate-must-run).
    assert profile.passed is False
    assert profile.required_checks == ("test",)
    gate_finding = next(f for f in profile.findings if f.check == "gate_check:lint")
    assert gate_finding.passed is False
    assert "lint" in gate_finding.detail


async def test_validate_target_repo_a_gh_failure_is_a_failed_validation_not_a_pass(
    env: ActivityEnvironment, repo_with_origin: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any gh failure yields a failed validation with a finding — never a pass.

    A repo the factory cannot read is a repo the factory must not dispatch
    against. The activity reports the refusal as data with an actionable finding
    rather than raising, so the workflow can route it to the operator preflight.
    """
    fake = FakeGh()
    fake.expect_error(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        stderr="gh: not found", returncode=1,
    )
    monkeypatch.setattr(merge_activities, "_client_factory", _onboard_client_factory(fake, repo_with_origin))

    from factory.activities.merge_activities import (
        ValidateTargetRepoInput,
        validate_target_repo,
    )

    profile = await env.run(validate_target_repo, ValidateTargetRepoInput(
        target_repo=str(repo_with_origin)
    ))

    assert profile.passed is False
    assert any(not f.passed for f in profile.findings)
    assert any("gh" in f.detail.lower() or "read" in f.detail.lower() for f in profile.findings)


async def test_validate_target_repo_loads_the_clones_factory_yaml(
    env: ActivityEnvironment, repo_with_origin: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The manifest is read from the target clone itself, via the 002 loader."""
    fake = FakeGh()
    fake.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={"nameWithOwner": "OWNER/REPO", "visibility": "PUBLIC", "defaultBranchRef": {"name": "main"}},
    )
    # The fixture declares gates lint/test/typecheck; script the queue with a
    # matching rule so the only variable under test is the manifest load.
    fake.expect_json(
        "api", "repos/OWNER/REPO/rules/branches/main",
        payload=[{"type": "merge_queue", "parameters": {"required_status_checks": [
            {"context": "lint"}, {"context": "test"}, {"context": "typecheck"},
        ]}}],
    )
    monkeypatch.setattr(merge_activities, "_client_factory", _onboard_client_factory(fake, repo_with_origin))

    from factory.activities.merge_activities import (
        ValidateTargetRepoInput,
        validate_target_repo,
    )

    profile = await env.run(validate_target_repo, ValidateTargetRepoInput(
        target_repo=str(repo_with_origin)
    ))

    assert profile.passed is True
    assert set(profile.declared_gates) == {"lint", "test", "typecheck"}
