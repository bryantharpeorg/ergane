"""Drive one real node branch through the merge queue (US1, spec § US1 IT).

`test_merge_activities.py` proves the four landing activities against a
`FakeGh` and a scratch repo — that the right `gh` commands run, in the right
order, from the right directory. It proves nothing at all about whether GitHub
will accept them: the queue has to be enabled, the branch pushable, the PR
creatable and auto-mergeable, and the sample repo's own required checks must
pass against the rebased tree. An operator would discover a broken assumption
at first landing, at 3am.

This file closes that gap once, behind the `live_merge` marker. It clones
`FACTORY_SAMPLE_REPO` (the D-010 sample repo), prepares one node branch in a
real worktree, renders a real PR body, and drives the *real* merge activities
against the real `gh` binary — push → open → enqueue → poll — until the queue
merges it. It asserts the two things US1 exists to prove: the factory observed
`MERGED`, and the PR body carried the spec reference.

Three deliberate choices:

- **The real `GhClient` subprocess runner; no fake is patched in.** The seam
  (`_client_factory`) is left untouched, so the activities construct the exact
  client production does and the real `gh` talks to the real queue. The runner
  seam is exercised, not replaced.
- **One branch, one landing.** The fixture is module-scoped: each test reads a
  different facet of a single merge, because several landings would be several
  merges into the shared sample repo to learn one fact.
- **It skips, it does not fail, without the env.** No `FACTORY_SAMPLE_REPO`
  (or an unauthenticated `gh`) means nobody asked for a live run; `uv run
  pytest -q` stays a pure-unit suite and `-m live_merge` selects this.

**The manual half (spec § Assumptions).** The sample repo must have merge
queue enabled on its default branch, a required check that passes on the node
branch's rebased tree, and a `factory.yaml` the branch does not break. This
test does not set that up — T001 (operator) did.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities.merge_activities import (
    EnqueueLandingInput,
    OpenLandingPrInput,
    PollLandingInput,
    PrepareLandingPrInput,
    enqueue_landing,
    open_landing_pr,
    poll_landing,
    prepare_landing_pr,
)
from factory.mergequeue import classify
from factory.mergequeue.models import Landing, LandingConfig, QueueOutcome
from factory.workgraph import worktree as worktrees

#: Selected with `-m live_merge`, deselected with `-m "not live_merge"`; skipped
#: outright without the sample repo (see `live_config`).
pytestmark = pytest.mark.live_merge

#: The D-010 sample repo's clone path (plan.md § US1, spec § Assumptions). Set by
#: the operator; unset means the live run was not asked for.
SAMPLE_REPO_ENV = "FACTORY_SAMPLE_REPO"

EPIC = "live-merge-us1"
NODE = "us1"
STORY_KEY = "US1"
FEATURE = "003-merge-queue"
REQUIREMENT_KEYS = ("US1", "FR-001", "FR-002")
BRANCH = f"factory/{EPIC}/{NODE}"
ATTEMPT = 1
MERGE_METHOD = "squash"

#: The landing's poll cadence. Real seconds, so the poll loop does not hammer the
#: API; the sample queue's checks run in well under this.
POLL_INTERVAL_S = 15

#: How long a landing may wait before we call the queue stuck. Bounded so a
#: queue that silently refuses the enqueue fails the smoke on its own rather
#: than hanging the suite.
STALL_AFTER_S = 300

#: The branch the PR is based on — the sample repo's default branch. Read live
#: at prepare time so a renamed trunk is never pushed over (FR-001's guard).
DEFAULT_BRANCH = "main"


@dataclass(frozen=True)
class LiveMergeConfig:
    """The sample repo, or a skip naming what is missing."""

    repo: Path


@pytest.fixture(scope="module")
def live_config() -> LiveMergeConfig:
    """`FACTORY_SAMPLE_REPO`, or a skip naming what is missing."""
    raw = os.environ.get(SAMPLE_REPO_ENV)
    if not raw:
        pytest.skip(
            f"live-merge smoke needs {SAMPLE_REPO_ENV} in the environment — a "
            "clone of the D-010 sample repo with merge queue enabled (spec § "
            "Assumptions)"
        )
    repo = Path(raw)
    if not repo.is_dir():
        pytest.skip(
            f"live-merge smoke: {SAMPLE_REPO_ENV}={repo} is not a directory"
        )
    if not _gh_authenticated(repo):
        pytest.skip(
            f"live-merge smoke needs `gh` authenticated for {SAMPLE_REPO_ENV} "
            "(spec § Assumptions)"
        )
    return LiveMergeConfig(repo=repo)


def _gh_authenticated(repo: Path) -> bool:
    """Whether `gh` can reach the remote the clone points at (auth, not queue)."""
    try:
        completed = subprocess.run(
            ["gh", "auth", "status", "--hostname", "github.com"],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )
    except OSError:
        return False
    return completed.returncode == 0


@dataclass(frozen=True)
class LiveMerge:
    """One real landing: its config and the recorded outcome."""

    config: LiveMergeConfig
    branch: str
    pr_number: int | None
    outcome: QueueOutcome
    body: str


#: git identity for the fixture's own worktree commit. Copy of the module's
#: salvage identity — the factory's automated commits are attributable to the
#: machine, never to the host's configured user (worktree.py's own rule).
_FACTORY_IDENTITY = {
    "GIT_AUTHOR_NAME": "Ergane Factory",
    "GIT_AUTHOR_EMAIL": "factory@ergane.invalid",
    "GIT_COMMITTER_NAME": "Ergane Factory",
    "GIT_COMMITTER_EMAIL": "factory@ergane.invalid",
}


@pytest.fixture(scope="module")
def live_merge(
    live_config: LiveMergeConfig,
    tmp_path_factory: pytest.TempPathFactory,
) -> LiveMerge:
    """Land one node branch through the sample repo's real queue, once."""
    root = tmp_path_factory.mktemp("live-merge")
    factory_root = root / ".factory"

    # The landing surface resolves `FACTORY_ROOT` from the environment (the same
    # resolver `agent_activities.factory_root()` and `_landing_body_dir()` use), so
    # it must agree with the root `ensure` prepares the worktree under, or the push
    # would look in a different directory than the worktree lives in.
    previous_root = os.environ.get("FACTORY_ROOT")
    os.environ["FACTORY_ROOT"] = str(factory_root)

    try:
        worktree = worktrees.ensure(
            live_config.repo, EPIC, NODE, factory_root=factory_root
        )
        worktree_path = Path(worktree.path)
        (worktree_path / "live-merge.txt").write_text(
            "live-merge smoke\n", encoding="utf-8"
        )
        worktrees._git(worktree_path, "add", "-A")
        worktrees._git(
            worktree_path,
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "live-merge node work",
            env_extra=_FACTORY_IDENTITY,
        )

        # The landing's base: the repo's current default branch (read live).
        base = worktree.default_branch or DEFAULT_BRANCH

        result = asyncio.run(_land_one(live_config, worktree_path, base))
    finally:
        if previous_root is None:
            os.environ.pop("FACTORY_ROOT", None)
        else:
            os.environ["FACTORY_ROOT"] = previous_root

    return LiveMerge(
        config=live_config,
        branch=BRANCH,
        pr_number=result["pr_number"],
        outcome=result["outcome"],
        body=result["body"],
    )


async def _land_one(
    config: LiveMergeConfig, worktree: Path, base: str
) -> dict[str, Any]:
    """The real landing: prepare → push/open → enqueue → poll → classify."""
    env = ActivityEnvironment()

    prepared = await env.run(
        prepare_landing_pr,
        PrepareLandingPrInput(
            epic_id=EPIC,
            node_id=NODE,
            branch=BRANCH,
            attempt=ATTEMPT,
            feature=FEATURE,
            requirement_keys=REQUIREMENT_KEYS,
            result=_passing_result(),
            story_title=STORY_KEY,
        ),
    )

    opened = await env.run(
        open_landing_pr,
        OpenLandingPrInput(
            epic_id=EPIC,
            node_id=NODE,
            target_repo=str(config.repo),
            base=base,
            branch=BRANCH,
            title=f"{EPIC}/{NODE}: {STORY_KEY}",
            body_file=prepared.body_file,
        ),
    )

    enqueued = await env.run(
        enqueue_landing,
        EnqueueLandingInput(
            pr_number=opened.number,
            merge_method=MERGE_METHOD,
            target_repo=str(config.repo),
        ),
    )
    assert not enqueued.rejected, f"queue refused the enqueue: {enqueued.reason}"

    # Poll on the landing's own beat until a terminal outcome or the stall bound.
    landing = Landing(node_id=NODE, branch=BRANCH, pr_number=opened.number)
    config_lc = LandingConfig(
        merge_method=MERGE_METHOD,
        poll_interval_s=POLL_INTERVAL_S,
        stall_after_s=STALL_AFTER_S,
    )
    deadline = time.time() + STALL_AFTER_S
    outcome: QueueOutcome | None = None
    snapshot = None
    while time.time() < deadline:
        snapshot = await env.run(
            poll_landing,
            PollLandingInput(pr_number=opened.number, target_repo=str(config.repo)),
        )
        outcome = classify.classify(snapshot, landing, config_lc, now=snapshot.observed_at)
        if outcome is not None:
            break
        await asyncio.sleep(POLL_INTERVAL_S)

    assert outcome is not None, (
        f"landing neither merged nor rejected within {STALL_AFTER_S}s; last poll: "
        f"state={snapshot.state if snapshot else None}"
    )

    body = Path(prepared.body_file).read_text(encoding="utf-8")
    return {"pr_number": opened.number, "outcome": outcome, "body": body}


# --- the assertions ---------------------------------------------------------


def test_the_queue_merged_the_node(live_merge: LiveMerge) -> None:
    """US1's core: verified work reached main, observed as MERGED (FR-004)."""
    assert live_merge.outcome == QueueOutcome.MERGED, (
        f"expected MERGED, got {live_merge.outcome} — the queue did not land "
        f"PR #{live_merge.pr_number}"
    )
    assert live_merge.pr_number is not None


def test_the_pr_body_carried_the_spec_reference(live_merge: LiveMerge) -> None:
    """The body an operator or future reader sees names the spec (US1-S1)."""
    body = live_merge.body
    assert FEATURE in body
    for key in REQUIREMENT_KEYS:
        assert key in body
    assert BRANCH in body
    assert "attempt 1" in body


def test_no_credential_escaped_into_the_public_pr_body(live_merge: LiveMerge) -> None:
    """The one body a repo may go public with leaks nothing (architecture §10)."""
    body = live_merge.body
    for secret in os.environ.get("LITELLM_MASTER_KEY", "").split():
        assert secret and secret not in body
    assert "/.factory/transcripts/" not in body


def test_a_conflicting_pair_is_classified_conflict_and_the_loser_survives(
    live_config: LiveMergeConfig,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """US2's IT: manufacture a conflicting pair, land the winner, the loser is CONFLICT.

    Two node branches edit the same file in different ways, so neither can rebase
    onto the other's merge. Both PRs are enqueued; the winner lands through the
    real queue. The loser — polled through the real `poll_landing`/`classify`
    path after the winner merges — is read as CONFLICT (the dirty merge state),
    and its branch is left untouched: the commit the queue is not deciding on
    stays reachable (FR-008). This proves *detection*; the full recovery drive
    stays in the time-skipping suite (plan.md § US2).
    """
    repo = live_config.repo
    root = tmp_path_factory.mktemp("live-conflict")
    factory_root = root / ".factory"
    os.environ["FACTORY_ROOT"] = str(factory_root)

    target_file = repo / "conflict-me.txt"
    winner = "factory/live-conflict/winner"
    loser = "factory/live-conflict/loser"
    env = ActivityEnvironment()

    winner_number: int | None = None
    loser_number: int | None = None
    try:
        _make_branch_editing(repo, winner, target_file, "winner's line\n")
        winner_number = asyncio.run(
            _open_pr(env, live_config, winner, "live-conflict winner")
        )
        _make_branch_editing(repo, loser, target_file, "loser's line\n")
        loser_number = asyncio.run(
            _open_pr(env, live_config, loser, "live-conflict loser")
        )

        # Land the winner; the loser's branch is now dirty against main.
        landing = Landing(node_id="winner", branch=winner, pr_number=winner_number)
        config_lc = LandingConfig(
            merge_method="squash",
            poll_interval_s=POLL_INTERVAL_S,
            stall_after_s=STALL_AFTER_S,
        )
        deadline = time.time() + STALL_AFTER_S
        winner_outcome: QueueOutcome | None = None
        while time.time() < deadline:
            snapshot = asyncio.run(
                env.run(
                    poll_landing,
                    PollLandingInput(pr_number=winner_number, target_repo=str(repo)),
                )
            )
            winner_outcome = classify.classify(
                snapshot, landing, config_lc, now=snapshot.observed_at
            )
            if winner_outcome is not None:
                break
            time.sleep(POLL_INTERVAL_S)
        assert winner_outcome == QueueOutcome.MERGED, (
            f"winner did not merge (got {winner_outcome}) — the sample repo's "
            "queue may not be enabled on its default branch"
        )

        # The loser is now unmergeable: its head and main disagree on the file.
        loser_landing = Landing(node_id="loser", branch=loser, pr_number=loser_number)
        loser_snapshot = asyncio.run(
            env.run(
                poll_landing,
                PollLandingInput(pr_number=loser_number, target_repo=str(repo)),
            )
        )
        loser_outcome = classify.classify(
            loser_snapshot, loser_landing, config_lc, now=loser_snapshot.observed_at
        )
        assert loser_outcome == QueueOutcome.CONFLICT, (
            f"expected the loser to be CONFLICT, got {loser_outcome}"
        )

        # The loser's branch survives untouched (FR-008): its tip commit is still
        # reachable by name.
        worktrees._git(repo, "log", "--oneline", "-1", loser)
    finally:
        if "FACTORY_ROOT" in os.environ:
            del os.environ["FACTORY_ROOT"]
        if winner_number is not None:
            _close_pr(repo, winner_number)
        if loser_number is not None:
            _close_pr(repo, loser_number)


def _make_branch_editing(repo: Path, branch: str, target_file: Path, content: str) -> None:
    """Create `branch` in the sample repo, editing `target_file` to `content`."""
    worktrees._git(repo, "checkout", "-b", branch)
    target_file.write_text(content, encoding="utf-8")
    worktrees._git(repo, "add", str(target_file))
    worktrees._git(
        repo,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        f"{branch} edits {target_file.name}",
        env_extra=_FACTORY_IDENTITY,
    )
    worktrees._git(repo, "push", "--quiet", "origin", branch)
    # Back onto the trunk so subsequent branch creations start from a clean HEAD.
    worktrees._git(repo, "checkout", worktrees._default_branch(repo))


def _open_pr(
    env: ActivityEnvironment, config: LiveMergeConfig, branch: str, title: str
) -> int:
    """Open + enqueue a PR for `branch`, returning its number."""
    body_file = Path(config.repo) / "pr-body.md"
    body_file.write_text("live-conflict smoke body\n", encoding="utf-8")
    opened = env.run_sync(
        open_landing_pr,
        OpenLandingPrInput(
            epic_id="live-conflict",
            node_id=branch.rsplit("/", 1)[-1],
            target_repo=str(config.repo),
            base=worktrees._default_branch(config.repo),
            branch=branch,
            title=title,
            body_file=str(body_file),
        ),
    )
    enqueued = env.run_sync(
        enqueue_landing,
        EnqueueLandingInput(
            pr_number=opened.number,
            merge_method="squash",
            target_repo=str(config.repo),
        ),
    )
    assert not enqueued.rejected, f"queue refused the enqueue: {enqueued.reason}"
    return opened.number


def _close_pr(repo: Path, pr_number: int) -> None:
    """Best-effort cleanup: close the PR without deleting its branch (FR-008)."""
    subprocess.run(
        ["gh", "pr", "close", str(pr_number), "--comment", "live-conflict smoke cleanup"],
        capture_output=True,
        text=True,
        cwd=str(repo),
    )


# --- the passing result ------------------------------------------------------


def _passing_result() -> Any:
    from factory.verify.models import (
        GateResult,
        GateStatus,
        JudgeOutcome,
        JudgeVerdict,
        OutputCheck,
        OverallVerdict,
        VerificationForm,
        VerificationResult,
    )

    return VerificationResult(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="pytest -q",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=1.25,
                output_tail="1 passed",
            ),
        ],
        output_check=OutputCheck(
            write_scope="target",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        judge=JudgeVerdict(
            outcome=JudgeOutcome.PASS,
            findings=[],
            feedback="Meets the scenarios.",
            judge_attempt=1,
            truncated_input=False,
            model_alias="implementer",
        ),
        verdict=OverallVerdict.PASS,
        judge_unavailable=False,
        criteria_drift=False,
        criteria_sha256="a" * 64,
        spec_ref=f"{FEATURE}:{STORY_KEY}",
        started_at="2026-08-06T09:00:00Z",
        finished_at="2026-08-06T09:05:00Z",
    )
