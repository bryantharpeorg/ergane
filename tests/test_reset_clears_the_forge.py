"""069-US3: `ergane build reset` clears the forge state that rejects a rebuild.

`reset` archived the *local* survivors of a terminated epic and stopped there.
The forge kept the rest: an open pull request for `factory/<epic>/<node>`, and
that branch still on the remote at the tip the dead attempt pushed. A rebuilt
node then branches from the base again, so its first push is not a descendant of
what the remote holds and git refuses it — non-fast-forward, in the middle of a
recovery, with the remedy (delete the branch by hand) written down nowhere.

Two claims are made here, and they need different kinds of test:

- **What reset does to a forge** is asserted against `FakeForge`'s repository
  model — the proposal is closed and carries a note, the head is gone and its tip
  survives under an archive name. Asserted as *state*, never as a call log, for
  the reason `tests/fake_forge.py` gives: a test that passes because a method was
  called would pass if the method did nothing.
- **That a rebuilt node can push** (US3-S3) is asserted against real git, with a
  real bare origin, because it is a claim about git's own non-fast-forward rule
  and no model can make that true or false. Its control — the same rebuild with
  the forge half skipped — is `test_a_rebuilt_node_is_rejected_...` directly
  below it, so a reset that quietly did nothing could not pass both.

Two more tests read the `gh` argv `GithubForge` actually issues (US3-S1's "the
forge calls made"), because the namespace guard is only worth what the commands
say: every ref addressed is under `factory/<epic>/<node>`, and no call passes
`--delete-branch`.

**On `--delete-branch` and FR-008.** `tests/test_mergequeue_sweep.py` forbids
that flag across the merge surface, and it stays forbidden: it rides along with a
merge or a close and would destroy a branch *the queue is still landing*. The
removal here is a different act on a different path — a terminated epic (reset
refuses while the workflow is RUNNING), addressed by ref, and only after the tip
is archived, on the explicit authority of FR-010. The guards below are the proof
that it stayed that narrow.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest
from temporalio.service import RPCError, RPCStatusCode

import factory.cli.nouns as nouns
from factory.cli.nouns import build as build_module
from factory.env import ERGANE_ROOT_ENV, FACTORY_ROOT_ENV
from factory.mergequeue.forge import Proposal
from factory.mergequeue.gh import GhClient
from factory.mergequeue.github_forge import GithubForge
from factory.mergequeue.reset import (
    ForgeReset,
    archive_prefix,
    reset_node_on_forge,
    reset_note,
)
from factory.workgraph.worktree import branch_name, ensure, push_branch, WorktreeError
from tests.fake_forge import FakeForge, RepositoryModel
from tests.target_repo import git, git_env

EPIC_ID = "069-reset-clears-the-forge"
NODE_ID = "us1"

#: A branch an operator opened by hand. Outside `factory/<epic>/<node>`, which is
#: the whole of what reset owns (US3-S4, trap 8).
OPERATOR_HEAD = "hotfix/an-operator-opened-this"

#: A tip shape that reads as a sha and is nothing else in this file.
NODE_TIP = "3f9a1c4e7b20d8659af4c1e0b7d3592a6c8e4f11"


# --- scaffolding ---------------------------------------------------------------


def _node_head(node_id: str = NODE_ID) -> str:
    return branch_name(EPIC_ID, node_id)


class _NotFoundClient:
    """Temporal, answering "no such workflow" — the state reset exists for."""

    def get_workflow_handle(self, workflow_id: str) -> Any:
        class Handle:
            async def describe(self) -> None:
                raise RPCError(
                    message=f"workflow {workflow_id} not found",
                    status=RPCStatusCode.NOT_FOUND,
                    raw_grpc_status=b"",
                )

        return Handle()


@pytest.fixture
def offline_temporal(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Temporal server: reset's guard read finds nothing and proceeds."""

    async def client() -> Any:
        return _NotFoundClient()

    monkeypatch.setattr(nouns, "_open_client", client)


def _scratch_epic(
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str = "target",
    with_origin: bool = False,
) -> tuple[Path, Path, Any]:
    """A target clone with one dispatched node, and the graph reset acts on.

    Returns `(repo, factory_root, graph)`. The node's worktree exists, is dirty,
    and its branch carries a commit — the survivors reset is given.
    """
    repo = target_repo("passing", name=name)
    factory_root = tmp_path / f".factory-{name}"
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(factory_root))
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)

    if with_origin:
        origin = tmp_path / f"{name}-origin.git"
        subprocess.run(
            ["git", "clone", "--bare", "--quiet", str(repo), str(origin)],
            check=True,
            capture_output=True,
            env=git_env(),
        )
        git(repo, "remote", "add", "origin", str(origin))
        git(repo, "fetch", "--quiet", "origin")

    prepared = ensure(repo, EPIC_ID, NODE_ID, factory_root=factory_root)
    worktree = Path(prepared.path)
    (worktree / f"added_by_{NODE_ID}.py").write_text("VALUE = 1\n", encoding="utf-8")

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
                        "id": NODE_ID,
                        "story_key": "US1",
                        "persona": "implementer",
                        "spec_ref": f"{EPIC_ID}:US1",
                        "requirement_keys": ["FR-010"],
                        "depends_on": [],
                        "depends_on_merged": [],
                        "timeout_override_s": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return repo, factory_root, build_module.load_workgraph(graph_path)


def _model_with_a_dispatched_node(
    *, tip: str = NODE_TIP, node_id: str = NODE_ID
) -> tuple[RepositoryModel, Proposal]:
    """A forge holding exactly what a dead node leaves: a proposal and a head."""
    model = RepositoryModel()
    head = _node_head(node_id)
    state = model.landings.open(head, model.address)
    model.push_head(head, tip)
    return model, Proposal(state.number, state.url)


def _ref_exists(repo: Path, ref: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return completed.returncode == 0


# --- T021 / US3-S1: the open pull request is closed, and says why --------------


async def test_reset_closes_the_nodes_open_proposal_with_a_note_naming_the_reset(
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    offline_temporal: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """US3-S1 / FR-010. What edit would make this fail? Dropping the close call,
    or closing without saying what closed it — an operator who finds a PR shut
    with no comment cannot tell a reset from somebody's mistake."""
    _repo, _root, graph = _scratch_epic(tmp_path, target_repo, monkeypatch)
    model, proposal = _model_with_a_dispatched_node()

    code = await build_module._reset_epic(graph, forge=FakeForge(model))

    assert code == 0
    state = model.landings.proposals[proposal.number]
    assert state.state == "CLOSED"
    assert len(state.notes) == 1, state.notes
    note = state.notes[0]
    assert "reset" in note.lower()
    assert EPIC_ID in note and NODE_ID in note
    assert f"#{proposal.number}" in capsys.readouterr().out


# --- T022 / US3-S2: the remote node branch is archive-renamed -----------------


async def test_reset_retires_the_remote_node_branch_keeping_its_tip(
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    offline_temporal: None,
) -> None:
    """US3-S2 / FR-010. The head is gone — that is what unblocks the rebuild —
    and its tip is still reachable under the archive name, which is the same
    bargain the local half already strikes (`worktree.reset` renames, never
    deletes). Mutation: remove the archive write and the tip is unreachable."""
    _repo, _root, graph = _scratch_epic(tmp_path, target_repo, monkeypatch)
    model, _proposal = _model_with_a_dispatched_node()
    head = _node_head()

    await build_module._reset_epic(graph, forge=FakeForge(model))

    assert head not in model.heads
    assert model.heads == {f"{archive_prefix(head)}/{NODE_TIP[:12]}": NODE_TIP}


# --- T023 / US3-S3: a rebuilt node pushes, and would not have before ----------


@dataclass
class _OriginForge:
    """A forge whose head store is a real git repository — the clone's origin.

    `FakeForge` models a repository; this one *is* one, because US3-S3 is a claim
    about git's own non-fast-forward rule and a model can neither satisfy nor
    violate it. Only the three operations FR-010 authorises are implemented: a
    fourth call is a reset reaching further than the story allows and fails here
    with an attribute error rather than quietly working.
    """

    origin: Path

    def find_proposal(self, head: str) -> Proposal | None:
        return None

    def close_proposal(self, proposal: int, *, note: str) -> None:
        raise AssertionError("this origin holds no proposals")

    def retire_head(self, head: str, *, archive_prefix: str) -> str:
        tip = subprocess.run(
            ["git", "-C", str(self.origin), "rev-parse", "--verify", "--quiet",
             f"refs/heads/{head}"],
            capture_output=True, text=True, env=git_env(),
        )
        if tip.returncode != 0:
            return ""
        sha = tip.stdout.strip()
        archive = f"{archive_prefix}/{sha[:12]}"
        git(self.origin, "update-ref", f"refs/heads/{archive}", sha)
        git(self.origin, "update-ref", "-d", f"refs/heads/{head}")
        return f"{head} archived at {archive} and removed"


def _push_a_dead_attempt(repo: Path, factory_root: Path) -> None:
    """What the terminated node left on the remote: a branch, one commit ahead."""
    worktree = Path(
        ensure(repo, EPIC_ID, NODE_ID, factory_root=factory_root).path
    )
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "the attempt that was terminated")
    push_branch(repo, EPIC_ID, NODE_ID, factory_root=factory_root)


def _rebuild_and_push(repo: Path, factory_root: Path) -> None:
    """The rebuilt node's first push — the act US3-S3 is about."""
    worktree = Path(
        ensure(repo, EPIC_ID, NODE_ID, factory_root=factory_root).path
    )
    (worktree / "rebuilt.py").write_text("REBUILT = True\n", encoding="utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "the rebuilt node's work")
    push_branch(repo, EPIC_ID, NODE_ID, factory_root=factory_root)


async def test_a_rebuilt_node_is_rejected_when_the_forge_still_holds_the_head(
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    offline_temporal: None,
) -> None:
    """The control for US3-S3, and the reported failure itself: with the local
    half of reset done and the forge half skipped, the rebuilt node's push is
    refused. Without this test the one below could pass on a reset that cleared
    nothing, because a push to a remote that never held the branch also succeeds.
    """
    repo, factory_root, graph = _scratch_epic(
        tmp_path, target_repo, monkeypatch, name="control", with_origin=True
    )
    _push_a_dead_attempt(repo, factory_root)

    # The forge half skipped: exactly what reset did before this story.
    await build_module._reset_epic(graph, forge=_NoForge())

    with pytest.raises(WorktreeError) as refused:
        _rebuild_and_push(repo, factory_root)

    assert "rejected" in str(refused.value) or "fast-forward" in str(refused.value)


class _NoForge:
    """A forge that answers nothing and changes nothing — reset's old behaviour."""

    def find_proposal(self, head: str) -> Proposal | None:
        return None

    def close_proposal(self, proposal: int, *, note: str) -> None:
        raise AssertionError("nothing to close")

    def retire_head(self, head: str, *, archive_prefix: str) -> str:
        return ""


async def test_a_rebuilt_node_pushes_after_a_reset(
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    offline_temporal: None,
) -> None:
    """US3-S3 / FR-010: the same rebuild, after a reset that cleared the forge.
    The push is not asserted "not to be rejected" by reading a message — it is
    run, and a rejection raises."""
    repo, factory_root, graph = _scratch_epic(
        tmp_path, target_repo, monkeypatch, name="rebuilt", with_origin=True
    )
    origin = Path(git(repo, "remote", "get-url", "origin").strip())
    _push_a_dead_attempt(repo, factory_root)
    head = _node_head()
    assert _ref_exists(origin, f"refs/heads/{head}")
    dead_tip = git(origin, "rev-parse", f"refs/heads/{head}").strip()

    await build_module._reset_epic(graph, forge=_OriginForge(origin))

    assert not _ref_exists(origin, f"refs/heads/{head}")
    assert _ref_exists(origin, f"refs/heads/{archive_prefix(head)}/{dead_tip[:12]}")

    _rebuild_and_push(repo, factory_root)

    assert _ref_exists(origin, f"refs/heads/{head}")
    assert git(origin, "rev-parse", f"refs/heads/{head}").strip() != dead_tip


# --- T024 / US3-S4: the factory owns its namespace and nothing else -----------


async def test_a_proposal_outside_the_node_namespace_is_untouched(
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    offline_temporal: None,
) -> None:
    """US3-S4, trap 8. A cleanup verb that closes a pull request an operator
    opened by hand is a far worse defect than the one being fixed. Mutation:
    close every open proposal instead of the one for this head, and this fails
    on the operator's own."""
    _repo, _root, graph = _scratch_epic(tmp_path, target_repo, monkeypatch)
    model, node_proposal = _model_with_a_dispatched_node()
    operator = model.landings.open(OPERATOR_HEAD, model.address)
    model.push_head(OPERATOR_HEAD, "b" * 40)
    model.push_head("main", "c" * 40)
    # A *different* epic's node, which this reset also does not own.
    sibling = model.landings.open("factory/070-another-epic/us2", model.address)
    model.push_head("factory/070-another-epic/us2", "d" * 40)

    await build_module._reset_epic(graph, forge=FakeForge(model))

    assert model.landings.proposals[node_proposal.number].state == "CLOSED"
    for untouched in (operator.number, sibling.number):
        assert model.landings.proposals[untouched].state == "OPEN"
        assert model.landings.proposals[untouched].notes == []
    assert model.heads[OPERATOR_HEAD] == "b" * 40
    assert model.heads["main"] == "c" * 40
    assert model.heads["factory/070-another-epic/us2"] == "d" * 40


@pytest.mark.parametrize(
    "head",
    ["main", "hotfix/urgent", "factory/069-epic", "factory/069-epic/us1/extra", ""],
)
def test_the_forge_cleanup_refuses_a_head_outside_the_factory_namespace(
    head: str,
) -> None:
    """The guard itself, at the one place every forge call is addressed from.
    A node id that arrived carrying a slash would otherwise address a namespace
    the factory does not own, and every caller would inherit that reach."""
    model, _proposal = _model_with_a_dispatched_node()

    with pytest.raises(ValueError) as refused:
        reset_node_on_forge(FakeForge(model), head=head, note="never sent")

    assert "factory/" in str(refused.value)
    assert model.landings.proposals[1].state == "OPEN"
    assert model.heads == {_node_head(): NODE_TIP}


# --- T025 / US3-S5: an unreachable forge does not strand the operator ---------


async def test_an_unreachable_forge_leaves_the_local_reset_complete(
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    offline_temporal: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """US3-S5 / FR-011, trap 9. A cleanup verb that aborts on a network error
    strands the operator in the state it exists to clear. The local reset
    completes, the exit is success, and the work not done is named — with the
    head, so the remedy is doable by hand from what was printed."""
    repo, factory_root, graph = _scratch_epic(tmp_path, target_repo, monkeypatch)
    model, _proposal = _model_with_a_dispatched_node()
    model.unreachable = "the forge did not answer"
    worktree = factory_root / "worktrees" / EPIC_ID / NODE_ID

    code = await build_module._reset_epic(graph, forge=FakeForge(model))

    assert code == 0
    # The local half is complete: worktree gone, sidecar gone, branch archived.
    assert not worktree.exists()
    assert not (factory_root / "worktrees" / EPIC_ID / f"{NODE_ID}.json").exists()
    assert not _ref_exists(repo, f"refs/heads/{_node_head()}")
    assert git(repo, "for-each-ref", "--format=%(refname:short)",
               f"refs/heads/archive/factory/{EPIC_ID}/").strip()
    # The forge half is reported undone, in terms an operator can act on.
    out = capsys.readouterr().out
    assert "not done" in out.lower()
    assert _node_head() in out
    assert "the forge did not answer" in out
    # And nothing was half-done on the forge.
    assert model.landings.proposals[1].state == "OPEN"
    assert model.heads == {_node_head(): NODE_TIP}


def test_a_clone_with_no_origin_resolves_no_forge_and_says_so(
    tmp_path: Path,
    target_repo: Callable[..., Path],
) -> None:
    """FR-011's quieter half, and the distinction that keeps the report honest.
    A clone with no remote never pushed a node branch, so there is no forge state
    to clear and no forge to build — reset must not spawn one to find that out,
    which is also what keeps every other reset test in this repository offline.
    It is *nothing to do*, not *not done*: reporting it as undone work would send
    an operator hunting for a pull request nobody ever opened."""
    repo = target_repo("passing", name="no-origin")

    forge, absent = build_module._reset_forge(repo)

    assert forge is None
    assert "origin" in absent.reason
    assert absent.undone is False
    assert build_module._forge_reset_lines(forge, absent, EPIC_ID, NODE_ID) == [
        f"forge: nothing to do — {absent.reason}"
    ]


# --- T026 / spec Edge Cases: a reset run twice --------------------------------


async def test_a_second_reset_succeeds_with_the_proposal_closed_and_head_gone(
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    offline_temporal: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec Edge Cases: "A reset run twice. The second finds the pull request
    already closed and the branch already gone. It must succeed." Asserted as
    *the forge did not change again*, not as "the command exited 0" — a second
    close would leave a second note, and a second archive would leave a second
    ref."""
    _repo, _root, graph = _scratch_epic(tmp_path, target_repo, monkeypatch)
    model, proposal = _model_with_a_dispatched_node()
    forge = FakeForge(model)

    assert await build_module._reset_epic(graph, forge=forge) == 0
    after_first = (dict(model.heads), list(model.landings.proposals[proposal.number].notes))
    capsys.readouterr()

    assert await build_module._reset_epic(graph, forge=forge) == 0

    assert dict(model.heads) == after_first[0]
    assert list(model.landings.proposals[proposal.number].notes) == after_first[1]
    assert "nothing to do" in capsys.readouterr().out


# --- US3-S1/S2 at the wire: the `gh` calls the GitHub forge actually makes ----


@dataclass(frozen=True)
class _Completed:
    stdout: str
    stderr: str
    returncode: int


class _RecordingGh:
    """A `gh` runner that records argv and answers from a fixed payload table.

    Unlike `tests/fake_gh.py` this consumes nothing and claims nothing about
    idempotence: it exists so the *commands* can be asserted, which is the only
    place the namespace guard is visible from outside.
    """

    #: `gh repo view --json …`'s answer, the address every ref call is built on.
    REPO_VIEW = json.dumps(
        {
            "nameWithOwner": "acme/app",
            "visibility": "PUBLIC",
            "isInOrganization": True,
            "defaultBranchRef": {"name": "main"},
        }
    )

    def __init__(self, payloads: dict[tuple[str, ...], str], missing: Sequence[tuple[str, ...]] = ()) -> None:
        self.payloads = payloads
        self.missing = {tuple(m) for m in missing}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: Sequence[str], cwd: str) -> _Completed:
        key = tuple(argv)
        self.calls.append(key)
        if key in self.missing:
            return _Completed("", "gh: Not Found (HTTP 404)", 1)
        if key[:2] == ("repo", "view"):
            return _Completed(self.REPO_VIEW, "", 0)
        return _Completed(self.payloads.get(key, ""), "", 0)


def _github_forge(gh: _RecordingGh) -> GithubForge:
    return GithubForge(GhClient(repo="/srv/target", runner=gh))


def test_the_github_forge_closes_with_a_comment_and_never_deletes_the_branch() -> None:
    """US3-S1 at the wire. `gh pr close <n> --comment <note>` — and `-d` /
    `--delete-branch` never rides along, because that flag deletes the branch the
    queue may still be landing, which is what FR-008's guard is about. The
    removal this story does needs the tip archived first and is issued by ref."""
    gh = _RecordingGh({})

    _github_forge(gh).close_proposal(7, note="closed by reset")

    assert gh.calls == [("pr", "close", "7", "--comment", "closed by reset")]
    assert not any("--delete-branch" in arg or arg == "-d" for call in gh.calls for arg in call)


def test_the_github_forge_archives_the_tip_before_it_removes_the_head() -> None:
    """US3-S2 at the wire, and trap 8 made visible: every ref this issues is
    inside `factory/<epic>/<node>` or the archive name derived from it, the
    archive write precedes the removal, and no call reaches a wider path."""
    head = _node_head()
    archive = f"{archive_prefix(head)}/{NODE_TIP[:12]}"
    gh = _RecordingGh(
        {("api", f"repos/acme/app/git/ref/heads/{head}"):
            json.dumps({"object": {"sha": NODE_TIP}})},
        missing=[("api", f"repos/acme/app/git/ref/heads/{archive}")],
    )

    detail = _github_forge(gh).retire_head(head, archive_prefix=archive_prefix(head))

    api_calls = [call for call in gh.calls if call[0] == "api"]
    assert api_calls == [
        ("api", f"repos/acme/app/git/ref/heads/{head}"),
        ("api", f"repos/acme/app/git/ref/heads/{archive}"),
        ("api", "-X", "POST", "repos/acme/app/git/refs",
         "-f", f"ref=refs/heads/{archive}", "-f", f"sha={NODE_TIP}"),
        ("api", "-X", "DELETE", f"repos/acme/app/git/refs/heads/{head}"),
    ]
    assert archive in detail and head in detail

    # Trap 8 as a scan rather than as a reading of the list above: every ref any
    # argument names — endpoint path or `-f ref=` field — is this node's head or
    # its own archive. A widened call that still happened to match the list
    # cannot exist, and a vacuous scan fails on the emptiness assertion.
    named_refs = [
        arg
        for call in gh.calls
        for arg in call
        if "refs/heads/" in arg or "/git/ref/heads/" in arg
    ]
    assert len(named_refs) == 4, named_refs
    for arg in named_refs:
        assert f"heads/{head}" in arg or f"heads/{archive_prefix(head)}/" in arg


def test_a_head_the_forge_no_longer_holds_is_reported_as_nothing_to_do() -> None:
    """The second reset, at the wire: an absent head is an answer, not a failure,
    and nothing is written. Mutation: create the archive ref unconditionally and
    this fails on the extra call."""
    head = _node_head()
    gh = _RecordingGh({}, missing=[("api", f"repos/acme/app/git/ref/heads/{head}")])

    detail = _github_forge(gh).retire_head(head, archive_prefix=archive_prefix(head))

    assert detail == ""
    assert [call for call in gh.calls if "-X" in call] == []


def test_an_unreachable_forge_reports_both_halves_undone_and_raises_nothing() -> None:
    """FR-011 at the seam it is implemented on: `reset_node_on_forge` returns the
    undone work as data. A raise here would become an aborted reset."""
    model, _proposal = _model_with_a_dispatched_node()
    model.unreachable = "the forge did not answer"

    result = reset_node_on_forge(
        FakeForge(model), head=_node_head(), note=reset_note(EPIC_ID, NODE_ID)
    )

    assert isinstance(result, ForgeReset)
    assert result.done == ()
    assert len(result.not_done) == 2
    assert all("the forge did not answer" in line for line in result.not_done)
