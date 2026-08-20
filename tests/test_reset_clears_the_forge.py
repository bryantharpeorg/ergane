"""069-US3: `ergane build reset` clears the forge state that rejects its rebuild.

`reset` archived the node's *local* survivors and stopped there. Everything the
node had put on the forge — the open pull request, and the
`factory/<epic>/<node>` branch on `origin` — survived the reset, and the next
build of the same epic met them: the rebuilt node branch starts at the target's
current head and therefore does not descend from what `origin` still holds, so
the landing push is refused as a non-fast-forward. The remedy was known and
manual, which made it silent until a push failed.

Three things these tests hold the fix to, and the second and third are the ones
worth failing over:

- **It clears both halves.** The proposal is closed with a note naming the reset
  (S1), and the remote branch is archive-renamed out of the node namespace (S2),
  so a rebuilt node's push is an ordinary create (S3). S3 is written as a *paired
  control*: the same repository, the same rebuilt commit, pushed once after the
  pre-069 local-only reset and once after this verb. The first push must be
  refused and the second must succeed, because a test that only asserts the
  second would pass against a remote that never held the branch at all.

- **It reaches nowhere else (trap 8).** A pull request an operator opened by
  hand, and a branch outside `factory/<epic>/<node>`, are not the factory's to
  close or move. A cleanup verb that reached them would be a far worse defect
  than the one being fixed, so the forge here holds one of each and the negative
  is asserted against what became of them.

- **It degrades rather than fails (trap 9).** An unreachable forge leaves the
  local reset complete and the undone forge work reported. The verb exists to
  get an operator out of a broken state; aborting halfway through on a network
  error strands them in it.

No test here reaches a network. The forge half runs against `FakeForge` — a
model of a repository, so every assertion below is about the state the proposals
were left in rather than about which calls were made; the git half runs against
a bare repository under `tmp_path`, which is what lets the S3 control push for
real and be refused for real.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest
from temporalio.service import RPCError, RPCStatusCode

import factory.cli.nouns as nouns
from factory.activities.agent_activities import ERGANE_ROOT_ENV, FACTORY_ROOT_ENV
from factory.cli.main import main as ergane_main
from factory.mergequeue.forge import ForgeError, Proposal
from factory.workgraph.worktree import (
    WorktreeError,
    branch_name,
    ensure,
    push_branch,
    reset as reset_worktree,
)
from tests.fake_forge import FakeForge, ProposalState, RepositoryModel
from tests.target_repo import DEFAULT_BRANCH, git

EPIC_ID = "069-reset-clears-the-forge"
NODES = ("us1", "us2")

#: A branch, and the head of a proposal, that the factory does not own.
#: Deliberately unlike a node branch in every part: not under `factory/`, not
#: naming the epic, not naming a node — so "the verb left it alone" is a real
#: assertion rather than a coincidence of prefixes.
FOREIGN_BRANCH = "hand/typed-hotfix"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        try:
            code = ergane_main(list(argv))
        except SystemExit as exit_request:
            code = exit_request.code
        captured = capsys.readouterr()
        return Run(0 if code is None else int(code), captured.out, captured.err)

    return invoke


@dataclass(frozen=True)
class Scene:
    """A target clone with a bare `origin`, one worktree per node, all pushed."""

    repo: Path
    origin: Path
    factory_root: Path
    graph_path: Path
    tips: dict[str, str]


def build_scene(
    target_repo: Callable[..., Path],
    tmp_path: Path,
    *,
    name: str = "reset",
    nodes: tuple[str, ...] = NODES,
) -> Scene:
    """A dispatched-and-terminated epic: node branches on the clone and on origin."""
    repo = target_repo("passing", name=name)
    origin = tmp_path / f"{name}-origin.git"
    git(repo, "init", "--bare", str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "--quiet", "-u", "origin", DEFAULT_BRANCH)

    factory_root = tmp_path / f"{name}-factory"
    tips: dict[str, str] = {}
    for node_id in nodes:
        prepared = ensure(repo, EPIC_ID, node_id, factory_root=factory_root)
        (Path(prepared.path) / f"{node_id}_work.py").write_text(
            f"VALUE_{node_id} = 1\n", encoding="utf-8"
        )
        git(prepared.path, "add", "-A")
        git(prepared.path, "commit", "--quiet", "-m", f"{node_id} work")
        tips[node_id] = push_branch(
            repo, EPIC_ID, node_id, factory_root=factory_root
        )

    graph_path = tmp_path / f"{name}-workgraph.json"
    graph_path.write_text(
        json.dumps(
            {
                "epic_id": EPIC_ID,
                "feature": EPIC_ID,
                "specs_root": str((tmp_path / "specs").resolve()),
                "target_repo": str(repo),
                "nodes": [
                    {
                        "id": node_id,
                        "story_key": node_id.upper(),
                        "persona": "implementer",
                        "spec_ref": f"{EPIC_ID}:{node_id.upper()}",
                        "requirement_keys": ["FR-010"],
                        "depends_on": [],
                        "depends_on_merged": [],
                        "timeout_override_s": None,
                    }
                    for node_id in nodes
                ],
            }
        ),
        encoding="utf-8",
    )
    return Scene(repo, origin, factory_root, graph_path, tips)


def offline(monkeypatch: pytest.MonkeyPatch, factory_root: Path) -> None:
    """Point the CLI at this scene's factory root and at no Temporal server.

    The reset's own guard reads the workflow before it changes anything; a
    terminated epic that has aged out of Temporal answers NOT_FOUND, which is the
    state an operator resets in. Stubbing it here is what keeps these tests off
    the network without weakening the guard, which `tests/test_ergane_build.py`
    already covers.
    """

    class NotFoundClient:
        def get_workflow_handle(self, workflow_id: str) -> Any:
            class Handle:
                async def describe(self) -> None:
                    raise RPCError(
                        message=f"workflow {workflow_id} not found",
                        status=RPCStatusCode.NOT_FOUND,
                        raw_grpc_status=b"",
                    )

            return Handle()

    async def open_client() -> Any:
        return NotFoundClient()

    monkeypatch.setenv(ERGANE_ROOT_ENV, str(factory_root))
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)
    monkeypatch.setattr(nouns, "_open_client", open_client)


def use_forge(monkeypatch: pytest.MonkeyPatch, forge: Any) -> None:
    """Give the reset `forge` instead of the one the repository would resolve.

    Patched on the *package*, not on `factory.cli.nouns.build`: `factory.cli.main`
    discovers nouns by `exec_module`-ing each file into a fresh module object, so
    a patch on the build module a test imported is not on the module the parser
    dispatches into. That mistake does not fail loudly — the verb reaches the
    real forge, against whatever repository the operator running the suite is
    logged into, and reads as a forge that refused.
    """
    monkeypatch.setattr(nouns, "_open_forge", lambda repo_path: forge)


def forge_holding(*heads: str) -> tuple[FakeForge, RepositoryModel]:
    """A forge holding one open proposal per head, in the order given.

    A model rather than a script (`tests/fake_forge.py`'s own rule): what the
    reset did is asserted against the state of the proposals afterwards, so a
    verb that called `close_proposal` and changed nothing would still fail.
    """
    model = RepositoryModel()
    for head in heads:
        model.landings.open(head)
    return FakeForge(model), model


def proposal_for(model: RepositoryModel, head: str) -> ProposalState:
    """The one proposal offered for `head`, open or closed."""
    found = [p for p in model.landings.proposals.values() if p.head == head]
    assert len(found) == 1, f"{head}: expected one proposal, found {found}"
    return found[0]


def ref_exists(repo: Path, ref: str) -> bool:
    try:
        git(repo, "rev-parse", "--verify", "--quiet", ref)
    except subprocess.CalledProcessError:
        return False
    return True


def sha_of(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", ref).strip()


def archive_ref(node_id: str, tip: str) -> str:
    """Where the node branch is archive-renamed to, local side and remote alike."""
    return f"refs/heads/archive/factory/{EPIC_ID}/{node_id}/{tip[:12]}"


# --- T021 / US3-S1: the pull request is closed, and says why --------------------


def test_reset_closes_the_node_pull_request_with_a_comment_naming_the_reset(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S1, FR-010: every node's open proposal is closed, with a note.

    The note is the part that matters to whoever finds the closed pull request
    later: a pull request that simply went away looks like somebody clicked, and
    an operator debugging a rebuild would have no way to tell the reset did it.
    So it names the verb, the epic and the node.

    Asserted against the proposals' state, not against which calls were made — a
    reset that called `close_proposal` and changed nothing would pass a call-log
    assertion.
    """
    scene = build_scene(target_repo, tmp_path)
    offline(monkeypatch, scene.factory_root)
    forge, model = forge_holding(*(branch_name(EPIC_ID, n) for n in NODES))
    use_forge(monkeypatch, forge)

    result = run("build", "reset", str(scene.graph_path))

    assert result.code == 0, result.stderr
    for node_id in NODES:
        proposal = proposal_for(model, branch_name(EPIC_ID, node_id))
        assert proposal.state == "CLOSED"
        assert proposal.merged_at is None
        assert "ergane build reset" in proposal.closing_note
        assert EPIC_ID in proposal.closing_note
        assert node_id in proposal.closing_note
        assert f"closed pull request #{proposal.number}" in result.stdout


# --- T022 / US3-S2: the remote node branch leaves the namespace ----------------


def test_reset_archive_renames_the_remote_node_branch(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S2, FR-010: `factory/<epic>/<node>` is gone from origin, not lost.

    Archive-renamed rather than deleted, and to the same name the local archive
    uses, because constitution VI is unconditional: the clone that runs the reset
    is not the only place that branch is read from, and a delete would leave the
    remote copy nowhere. Every commit that was on the remote node branch is still
    reachable from the remote archive ref.
    """
    scene = build_scene(target_repo, tmp_path)
    offline(monkeypatch, scene.factory_root)
    forge, _ = forge_holding(*(branch_name(EPIC_ID, n) for n in NODES))
    use_forge(monkeypatch, forge)

    for node_id in NODES:
        assert ref_exists(scene.origin, f"refs/heads/{branch_name(EPIC_ID, node_id)}")

    result = run("build", "reset", str(scene.graph_path))

    assert result.code == 0, result.stderr
    for node_id in NODES:
        branch = branch_name(EPIC_ID, node_id)
        archive = archive_ref(node_id, scene.tips[node_id])
        assert not ref_exists(scene.origin, f"refs/heads/{branch}")
        assert ref_exists(scene.origin, archive)
        assert sha_of(scene.origin, archive) == scene.tips[node_id]
        assert archive.removeprefix("refs/heads/") in result.stdout


# --- T023 / US3-S3: the rebuilt node pushes, and would not have before ---------


def test_a_rebuilt_node_pushes_only_after_the_forge_side_of_the_reset(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S3, FR-010: the reported failure, reproduced and then survived.

    The control is the whole test. A local-only reset — exactly what this verb
    did before this story — leaves `origin` holding the old node tip, so the
    rebuilt branch, which starts at the target's head and never saw that tip, is
    refused as a non-fast-forward. Then the verb runs, and the *same* rebuild
    pushes. Without the first half, the second would pass against a remote that
    had never held the branch at all.
    """
    scene = build_scene(target_repo, tmp_path, name="rebuild", nodes=("us1",))
    offline(monkeypatch, scene.factory_root)

    # The pre-069 reset: local survivors archived, forge untouched.
    reset_worktree(scene.repo, EPIC_ID, "us1", factory_root=scene.factory_root)
    rebuilt = ensure(scene.repo, EPIC_ID, "us1", factory_root=scene.factory_root)
    (Path(rebuilt.path) / "rebuilt.py").write_text("VALUE = 2\n", encoding="utf-8")
    git(rebuilt.path, "add", "-A")
    git(rebuilt.path, "commit", "--quiet", "-m", "rebuilt us1 work")

    with pytest.raises(WorktreeError) as refused:
        push_branch(scene.repo, EPIC_ID, "us1", factory_root=scene.factory_root)

    rejection = str(refused.value)
    assert "rejected" in rejection
    assert "non-fast-forward" in rejection or "fetch first" in rejection

    forge, _ = forge_holding(branch_name(EPIC_ID, "us1"))
    use_forge(monkeypatch, forge)

    result = run("build", "reset", str(scene.graph_path))
    assert result.code == 0, result.stderr

    # Rebuild once more — the reset archived the branch the failed push was on —
    # and push. No rejection: the namespace on origin is clear.
    again = ensure(scene.repo, EPIC_ID, "us1", factory_root=scene.factory_root)
    (Path(again.path) / "rebuilt.py").write_text("VALUE = 3\n", encoding="utf-8")
    git(again.path, "add", "-A")
    git(again.path, "commit", "--quiet", "-m", "rebuilt us1 work, second time")

    pushed = push_branch(scene.repo, EPIC_ID, "us1", factory_root=scene.factory_root)

    branch = branch_name(EPIC_ID, "us1")
    assert sha_of(scene.origin, f"refs/heads/{branch}") == pushed


# --- T024 / US3-S4: the negative. Nothing outside the namespace is touched -----


def test_reset_leaves_a_pull_request_outside_the_node_namespace_alone(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S4, FR-010, trap 8: the factory owns `factory/<epic>/<node>` and nothing else.

    The forge here would close the foreign proposal as readily as the node ones —
    it is the same fake, holding the same kind of object — so what this asserts is
    that the verb left it alone, not that something refused on its behalf. Same
    for the branch: a branch outside the namespace is still on origin, at the same
    commit, afterwards.
    """
    scene = build_scene(target_repo, tmp_path)
    git(scene.repo, "push", "--quiet", "origin", f"{DEFAULT_BRANCH}:refs/heads/{FOREIGN_BRANCH}")
    foreign_tip = sha_of(scene.origin, f"refs/heads/{FOREIGN_BRANCH}")
    offline(monkeypatch, scene.factory_root)

    # The forge holds the two node proposals *and* one an operator opened by hand.
    forge, model = forge_holding(
        branch_name(EPIC_ID, NODES[0]), FOREIGN_BRANCH, branch_name(EPIC_ID, NODES[1])
    )
    use_forge(monkeypatch, forge)

    result = run("build", "reset", str(scene.graph_path))

    assert result.code == 0, result.stderr
    # The node proposals closed; the hand-opened one is exactly as it was.
    closed = {p.head for p in model.landings.proposals.values() if p.state == "CLOSED"}
    assert closed == {branch_name(EPIC_ID, node_id) for node_id in NODES}
    foreign = proposal_for(model, FOREIGN_BRANCH)
    assert foreign.state == "OPEN"
    assert foreign.closing_note == ""
    # And the branch outside the namespace is untouched on the remote.
    assert sha_of(scene.origin, f"refs/heads/{FOREIGN_BRANCH}") == foreign_tip
    assert FOREIGN_BRANCH not in result.stdout


# --- T025 / US3-S5: an unreachable forge does not strand the operator ----------


def test_an_unreachable_forge_still_leaves_the_local_reset_complete(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S5, FR-011, trap 9: local reset completes; the undone forge work is said.

    Both halves are unreachable — the forge answers nothing and `origin` is not
    there — so this is the whole forge side failing, not the convenient half. The
    verb still exits 0 with the worktree removed, the branch archived and the
    sidecar gone, and names each thing it could not do. Exiting non-zero here
    would be the inversion: the operator resets *because* something is broken, and
    a verb that refuses to finish leaves them worse off than before.
    """
    scene = build_scene(target_repo, tmp_path, name="unreachable")
    vanished = tmp_path / "vanished-origin.git"
    git(scene.repo, "remote", "set-url", "origin", str(vanished))
    offline(monkeypatch, scene.factory_root)

    class UnreachableForge:
        """A forge that cannot be read at all — the shape `ForgeError` is for."""

        def find_proposal(self, head: str) -> Proposal | None:
            raise ForgeError(
                "FORGE_UNAVAILABLE", "could not reach the forge: no route to host"
            )

        def close_proposal(self, proposal: int, *, note: str) -> None:
            raise ForgeError(
                "FORGE_UNAVAILABLE", "could not reach the forge: no route to host"
            )

    use_forge(monkeypatch, UnreachableForge())

    result = run("build", "reset", str(scene.graph_path))

    assert result.code == 0, result.stderr
    for node_id in NODES:
        branch = branch_name(EPIC_ID, node_id)
        worktree = scene.factory_root / "worktrees" / EPIC_ID / node_id
        assert not worktree.exists()
        assert not (
            scene.factory_root / "worktrees" / EPIC_ID / f"{node_id}.json"
        ).exists()
        assert not ref_exists(scene.repo, f"refs/heads/{branch}")
        assert ref_exists(scene.repo, archive_ref(node_id, scene.tips[node_id]))
        # Both halves of the undone forge work are named, per node.
        undone = [
            line
            for line in result.stdout.splitlines()
            if line.startswith(f"{node_id}: forge not cleared:")
        ]
        assert len(undone) == 2, result.stdout
        assert any(branch in line and "origin" in line for line in undone)
        assert any("pull request" in line for line in undone)


# --- T026 / Edge case: a reset run twice ---------------------------------------


def test_a_second_reset_succeeds_with_the_pull_request_and_branch_already_gone(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec edge case: the second reset finds nothing left and is still a success.

    Idempotence is what makes this verb safe to reach for while recovering: an
    operator who is not sure whether the first reset finished has to be able to
    run it again. The second run must close nothing, refuse nothing, and report
    no undone forge work — the state it finds is the state it wanted.

    One forge across both runs, carrying what the first one did into the second.
    Two fakes would let the second run pass against a repository that was never
    reset, which is the case this is not about.
    """
    scene = build_scene(target_repo, tmp_path, name="twice", nodes=("us1",))
    offline(monkeypatch, scene.factory_root)
    branch = branch_name(EPIC_ID, "us1")
    forge, model = forge_holding(branch)
    use_forge(monkeypatch, forge)

    assert run("build", "reset", str(scene.graph_path)).code == 0
    closed_note = proposal_for(model, branch).closing_note
    assert closed_note

    again = run("build", "reset", str(scene.graph_path))

    assert again.code == 0, again.stderr
    assert "forge not cleared" not in again.stdout
    assert f"no open pull request for {branch}" in again.stdout
    assert f"{branch} is not on origin" in again.stdout
    # Nothing was closed a second time, and nothing was re-opened.
    assert proposal_for(model, branch).state == "CLOSED"
    assert proposal_for(model, branch).closing_note == closed_note
