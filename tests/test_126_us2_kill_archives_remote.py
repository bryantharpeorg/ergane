"""126-US2: a killed node archives its remote branch, not the next dispatch.

The factory's kill path used to leave `factory/<epic>/<node>` on origin. The
next dispatch branched fresh from the landing head, so its first push was
refused non-fast-forward *after* the agent, gates and judge had all been paid.
US2 closes that loop by archiving the killed branch before clearing it.

These tests are written against the real workflow interpreter and real git.
They will fail until the implementation adds an activity to `_close_out` that
archives then clears the remote ref on terminal (non-None, non-parked) states.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities.agent_activities import archive_and_clear_remote_branch
from factory.verify.models import EscalationChoice
from factory.workgraph.models import EpicState, NodeState, WorkGraph
from factory.workgraph.workflow import EpicWorkflow
from factory.workgraph.worktree import (
    archive_branch_prefix,
    branch_name,
    ensure,
    push_branch,
)
from tests.target_repo import git, git_env
from tests.test_interpreter import (
    RESUME_SIGNAL,
    ScriptedWorld,
    env,
    make_graph,
    make_node,
    merged_snapshot,
    passing,
    run_epic,
    start_epic,
    states,
    wait_for_status,
)
from tests.test_epic_escalation_child import ladder_fails
from tests.test_pause_is_not_a_kill import PARKED

EPIC = "126-a-killed-node-leaves-no-ref-to-collide-with"
NODE = "us2"
BRANCH = branch_name(EPIC, NODE)


class Repo:
    """A target clone with a real bare `origin`, ready to dispatch a node into."""

    def __init__(self, repo: Path, origin: Path, factory_root: Path) -> None:
        self.repo = repo
        self.origin = origin
        self.factory_root = factory_root

    def dispatch(self, value: str = "1") -> Path:
        """Prepare the node's worktree and leave a commit on its branch."""
        prepared = ensure(self.repo, EPIC, NODE, factory_root=self.factory_root)
        worktree = Path(prepared.path)
        (worktree / f"added_by_{NODE}.py").write_text(f"VALUE = {value}\n", "utf-8")
        git(worktree, "add", "-A")
        git(worktree, "commit", "--quiet", "-m", f"work by {NODE} ({value})")
        return worktree

    def push(self) -> str:
        return push_branch(self.repo, EPIC, NODE, factory_root=self.factory_root)

    def remote_tip(self, branch: str | None = None) -> str:
        """What origin holds for `branch`, or "" when it holds nothing."""
        ref = f"refs/heads/{branch or BRANCH}"
        listing = git(self.origin, "for-each-ref", "--format=%(objectname)", ref)
        return listing.strip()

    def archive_refs(self) -> tuple[str, ...]:
        """Every archive ref this node has on origin, by full name."""
        namespace = f"refs/heads/{archive_branch_prefix(EPIC, NODE)}"
        listing = git(self.origin, "for-each-ref", "--format=%(refname)", namespace)
        return tuple(line for line in listing.splitlines() if line)


@pytest.fixture
def repo(tmp_path: Path, target_repo: Callable[..., Path], monkeypatch: Any) -> Repo:
    """A target clone with a real bare `origin`, ready for the kill path."""
    local = target_repo("passing", name="target")
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "clone", "--bare", "--quiet", str(local), str(origin)],
        check=True,
        capture_output=True,
        env=git_env(),
    )
    git(local, "remote", "add", "origin", str(origin))
    git(local, "fetch", "--quiet", "origin")
    factory_root = tmp_path / ".factory"
    monkeypatch.setenv("ERGANE_ROOT", str(factory_root))
    monkeypatch.setenv("FACTORY_ROOT", str(factory_root))
    return Repo(local, origin, factory_root)


def graph(target_repo: Path | str | None = None) -> WorkGraph:
    """The one-node graph US2 exercises: `us2` of epic 126."""
    kwargs: dict[str, Any] = {"epic_id": EPIC}
    if target_repo is not None:
        kwargs["target_repo"] = str(target_repo)
    return make_graph([make_node(NODE, "US2")], **kwargs)


class RealArchiveWorld(ScriptedWorld):
    """A scripted world that runs the real archive/clear activity.

    All other activities stay scripted; only `archive_and_clear_remote_branch`
    talks to real git, because US2 tests assert ref states on a real bare
    origin.
    """

    def activities(self) -> list[Any]:
        acts = super().activities()
        acts = [
            a
            for a in acts
            if getattr(a, "__name__", None) != "archive_and_clear_remote_branch"
        ]
        acts.append(archive_and_clear_remote_branch)
        return acts


def exhausted_kill(client: Any) -> RealArchiveWorld:
    """`us2` exhausts its ladder, then the operator presses KILL."""
    return RealArchiveWorld(
        {NODE: ladder_fails()},
        client=client,
        press=EscalationChoice.KILL.value,
    )


def exhausted_pause(client: Any) -> RealArchiveWorld:
    """`us2` exhausts its ladder, then the operator presses PAUSE_EPIC."""
    return RealArchiveWorld(
        {NODE: ladder_fails()},
        client=client,
        press=EscalationChoice.PAUSE_EPIC.value,
    )


# --- T011 / US2-S1 / FR-007: kill archives the live ref and clears it from origin


async def test_killed_node_clears_remote_ref_and_keeps_archive(
    env: WorkflowEnvironment, repo: Repo
) -> None:
    """The branch on origin is renamed to archive/<...> and the live name freed."""
    repo.dispatch("1")
    pushed = repo.push()
    assert repo.remote_tip() == pushed

    script = exhausted_kill(env.client)

    status = await run_epic(env, script, graph=graph(repo.repo))

    # The operator press ended the node, not the epic: a one-node graph that
    # kills its only node still reports EpicState.COMPLETED, with the node KILLED.
    assert status.epic_state == EpicState.COMPLETED
    assert states(status)[NODE] == NodeState.KILLED

    # The live ref is gone from origin and the archive ref carries the same tip.
    assert repo.remote_tip() == ""
    archives = repo.archive_refs()
    assert len(archives) == 1
    archive = archives[0]
    assert archive.endswith(f"/{pushed[:12]}")
    assert repo.remote_tip(archive[len("refs/heads/"):]) == pushed


# --- T012 / trap 1: a PAUSE_EPIC park leaves the remote ref untouched


async def test_pause_epic_park_leaves_remote_ref_untouched(
    env: WorkflowEnvironment, repo: Repo
) -> None:
    """`_close_out` is called with `Termination.KILLED, state=_PARKED`, but the
    branch must survive because the node is parked, not killed."""
    repo.dispatch("1")
    pushed = repo.push()
    assert repo.remote_tip() == pushed

    script = exhausted_pause(env.client)

    async with start_epic(env, script, graph=graph(repo.repo)) as handle:
        parked = await wait_for_status(
            handle,
            lambda status: status.epic_state == EpicState.PAUSED
            and states(status).get(NODE) == PARKED,
            what=f"{NODE} to park and the epic to pause",
        )
        assert states(parked)[NODE] == PARKED

        await handle.signal(RESUME_SIGNAL)
        status = await handle.result()

    assert status.epic_state == EpicState.COMPLETED
    # The remote branch was never touched: the pause path must not archive/clear.
    assert repo.remote_tip() == pushed
    assert repo.archive_refs() == ()


# --- T013 / trap 2: the PASS path leaves the remote ref untouched


async def test_passed_node_leaves_remote_ref_for_landing(
    env: WorkflowEnvironment, repo: Repo
) -> None:
    """A passing node keeps its live branch so the landing PR can open from it."""
    repo.dispatch("1")
    pushed = repo.push()
    assert repo.remote_tip() == pushed

    script = ScriptedWorld({NODE: [passing()]}, client=env.client)
    script.script_landing(NODE, merged_snapshot())

    status = await run_epic(env, script, graph=graph(repo.repo))

    assert status.epic_state == EpicState.COMPLETED
    assert states(status)[NODE] == NodeState.MERGED
    # The live branch was preserved through landing.
    assert repo.remote_tip() == pushed
    assert repo.archive_refs() == ()


# --- T014 / US2-S2 / FR-008: an unarchived remote tip is kept and reported


async def test_unarchived_remote_tip_is_kept_and_reported(
    env: WorkflowEnvironment, repo: Repo
) -> None:
    """Reachability decides deletion. A tip no archive holds survives the kill."""
    worktree = repo.dispatch("1")
    first = repo.push()
    (worktree / "second.py").write_text("VALUE = 2\n", "utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "a second commit, pushed then rewound")
    pushed = repo.push()
    git(worktree, "reset", "--quiet", "--hard", first)
    assert pushed != first
    assert repo.remote_tip() == pushed

    script = exhausted_kill(env.client)

    status = await run_epic(env, script, graph=graph(repo.repo))

    assert states(status)[NODE] == NodeState.KILLED
    # The remote tip is still there because no archive ref holds it.
    assert repo.remote_tip() == pushed
    # And the terminal record reports the kept ref.
    assert status.nodes[NODE].terminal_reason is not None
    assert BRANCH in status.nodes[NODE].terminal_reason
    assert pushed[:12] in status.nodes[NODE].terminal_reason


# --- T015 / US2-S3 / FR-009: an unreachable remote completes and reports


async def test_unreachable_remote_completes_kill_and_reports_surviving_ref(
    env: WorkflowEnvironment, repo: Repo
) -> None:
    """The kill must reach terminal state even when origin cannot be reached."""
    repo.dispatch("1")
    pushed = repo.push()
    assert repo.remote_tip() == pushed

    # Point origin at a path with no repository.
    git(repo.repo, "remote", "set-url", "origin", str(repo.repo.parent / "gone.git"))

    script = exhausted_kill(env.client)

    status = await run_epic(env, script, graph=graph(repo.repo))

    assert states(status)[NODE] == NodeState.KILLED
    # Local archive happened; remote could not be cleared.
    assert status.nodes[NODE].terminal_reason is not None
    assert "origin" in status.nodes[NODE].terminal_reason


# --- T016 / US2-S4 / FR-010: a second kill is idempotent and never overwrites


async def test_second_kill_is_idempotent_and_preserves_archive(
    env: WorkflowEnvironment, repo: Repo
) -> None:
    """Retry of the terminal activity finds nothing to do and leaves archives intact."""
    repo.dispatch("1")
    pushed = repo.push()

    script = exhausted_kill(env.client)

    status = await run_epic(env, script, graph=graph(repo.repo))
    assert states(status)[NODE] == NodeState.KILLED
    assert repo.remote_tip() == ""
    archive = repo.archive_refs()
    assert len(archive) == 1

    # A second epic killing the same node would find the live ref gone and the
    # archive already present. Simulate by re-running the archive/clear helper.
    # (This is exercised through the activity in integration; here we assert
    # the helper itself is idempotent.)
    from factory.workgraph.worktree import archive_and_clear_remote_branch

    report = archive_and_clear_remote_branch(
        repo.repo, EPIC, NODE, factory_root=repo.factory_root
    )
    assert repo.remote_tip() == ""
    assert repo.archive_refs() == archive
    # A true no-op second run returns an empty report; the workflow records
    # that as no terminal_reason, which is the right shape for idempotency.
    assert report == []
