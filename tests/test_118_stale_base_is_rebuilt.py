"""A worktree too far behind is rebuilt at dispatch (118 US1).

The defect this file exists for was measured, not hypothesised: a story passed
four gates, the judge and 7/7 scenarios, and failed immediately when pushed to a
PR against the real landing branch. Its merge-base was three landings stale and
had never seen a test file a sibling story introduced. Both halves of the loop
scored it correct, because both read the worktree and the worktree was
internally consistent — neither has any notion of how old the base is.

The guard that should have caught it exists and checks the wrong property:
`if _is_ancestor(repo, recorded.base_ref)`. A base three landings behind the
landing branch **is** an ancestor of it — that is precisely what "behind"
means. The validity test answers "is this pin still real?"; the question that
decides a landing is "is this pin still current?". So the currency test this
spec adds sits beside the validity test at exactly the place the module already
rebuilds — dispatch — and measures *distance*, not membership (plan trap 1).

Four properties these tests defend:

- **Behind past the tolerance → rebuilt, archived (US1-S1, FR-001).** The old
  branch is never deleted; the rebuild goes through the one `_archive_node`
  path the divergence arm already uses (T008).
- **At or within the tolerance → untouched (US1-S2, FR-002).** Reuse is the
  rule and this story *narrows* it. This is the control the whole file leans
  on: an implementation that rebuilt on any commit behind — the boolean trap
  (plan trap 2) — dies right here.
- **Not an ancestor at all → rebuilt exactly as today (US1-S3, FR-003).** The
  validity check keeps its behaviour; the currency test does not replace it.
  The fixture here diverges origin rather than advancing it, so the rebuild
  fires through the *old* arm at a distance no larger than the tolerance — the
  two checks have to stay independent, and this is the shape that proves it.
- **Between attempts → never rechecked (US1-S4, FR-004, plan trap 3).** A
  retry of a prepared node opens the same tree whatever the landing branch has
  done, because rebuilding between attempts would move the goalposts mid-node
  — the failure R5 and 002's criteria snapshot exist to prevent. The workflow
  executes `prepare_worktree` once per node, before its attempt loop; the
  interpreter test asserts that count is one even across a retry, with the
  landing branch moved far outside the tolerance in between — plus the
  dispatch-time control that a fresh preparation against that same
  post-epic state *does* rebuild, so the exemption is structural and not a
  vacuous "nothing was far enough behind".

Two arms are deliberately left alone, and each has a control:

- **The explicit-pin arm (US1-S5, FR-005).** An explicit caller instruction
  remains the caller's authority (spec Edge Cases); a caller asking for a
  behind-by-many base gets exactly that base.
- **The adopt arm (plan trap 4).** A worktree whose record was swept is
  adopted pinning to where it stands. Judging it against a pin nobody
  recorded is how in-progress work gets discarded, which is the failure that
  arm exists to avoid.

Real git throughout, against the `tests/fixtures/target_repo/` skeleton — the
subject is what git says about ancestry and distance, and a fake would only
prove the fake agrees with itself.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.activities.agent_activities import PrepareWorktreeInput
from factory.workgraph.worktree import (
    STALE_BASE_TOLERANCE_COMMITS,
    PreparedWorktree,
    WorktreeError,
    _read_record,
    ensure,
)
from factory.workgraph.workflow import EpicInput, EpicWorkflow
from tests.target_repo import build_target_repo, git, git_env

EPIC = "118-a-verified-tree-is-the-tree-that-will-merge"
NODE = "us1"

#: Branch and worktree naming — machine-attributable from the ref alone.
BRANCH = f"factory/{EPIC}/{NODE}"

#: A tracked file in the fixture repo, for "the agent left work here".
TRACKED_FILE = "src/calc.py"

#: An untracked one — the normal shape of in-progress work a rebuild must not
#: lose, which is why `_archive_node` commits a dirty tree before renaming.
NEW_FILE = "src/node_work.py"


# --- setup -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_operator_git_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every identity git could fall back on (see test_worktree.py)."""
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_NAME", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """The worker host's state directory — outside every target clone."""
    return tmp_path / ".ergane"


@pytest.fixture
def origin_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A target repo with a bare `origin` the landing branch can move on.

    The currency test answers against the *remote* landing-branch head — the
    same read `capture_base_ref` makes — so the fixture pushes every landing to
    `origin` and tests read the bare repo. "What the branch has done since" is
    then a fact about the remote the factory reads, not the clone's working
    state.
    """
    repo = build_target_repo(tmp_path / "target")
    bare = tmp_path / "origin.git"
    git(repo, "init", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "--quiet", "-u", "origin", "main")
    return repo, bare


# --- helpers -----------------------------------------------------------------


def head(path: Path, ref: str = "HEAD") -> str:
    return git(path, "rev-parse", ref).strip()


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    """`merge-base --is-ancestor` — exit 1 is an answer, not a failure."""
    completed = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return completed.returncode == 0


def ref_exists(repo: Path, ref: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return completed.returncode == 0


def land(repo: Path, note: str) -> str:
    """Land one squash-shaped commit on the landing branch, on origin too.

    The merge queue's landing is one commit per story PR, so a sibling landing
    moves the branch by exactly one — the unit the tolerance is expressed in.
    The push happens only when the repo has an origin (the workflow-level test
    runs against a bare clone with none); the returned head is read back from
    the *remote* when one exists, because the currency test reads origin — if
    the clone and origin ever disagreed here the test would be measuring the
    fetch, not the currency decision.
    """
    (repo / "README.md").write_text(note, encoding="utf-8")
    git(repo, "commit", "--quiet", "-a", "-m", note)
    if git(repo, "remote").strip():
        git(repo, "push", "--quiet", "origin", "main")
        return head(repo, "refs/remotes/origin/main")
    return head(repo, "refs/heads/main")


def dirty(worktree: Path) -> None:
    """Leave the shape of an agent's work: one edit, one new file."""
    (worktree / TRACKED_FILE).write_text("# edited by the agent\n", encoding="utf-8")
    (worktree / NEW_FILE).write_text("VALUE = 1\n", encoding="utf-8")


def status(worktree: Path) -> str:
    return git(worktree, "status", "--porcelain", "--untracked-files=all")


def registered_worktrees(repo: Path) -> list[str]:
    lines = git(repo, "worktree", "list", "--porcelain").splitlines()
    paths = [
        Path(line.split(" ", 1)[1]) for line in lines if line.startswith("worktree ")
    ]
    return [str(path.resolve()) for path in paths if path.resolve() != repo.resolve()]


def archive_refs(repo: Path, epic_id: str = EPIC, node_id: str = NODE) -> list[str]:
    """Every archive ref this node ever produced, fully qualified."""
    prefix = f"refs/heads/archive/factory/{epic_id}/{node_id}/"
    out = git(repo, "for-each-ref", f"{prefix}*", "--format=%(refname)")
    return [line.strip() for line in out.splitlines() if line.strip()]


def all_local_refs(repo: Path) -> set[str]:
    out = git(repo, "for-each-ref", "--format=%(refname)")
    return {line.strip() for line in out.splitlines() if line.strip()}


def commits_behind(repo: Path, ancestor: str, descendant: str) -> int:
    """The distance the currency test measures, read the way git reads it."""
    return int(git(repo, "rev-list", "--count", f"{ancestor}..{descendant}").strip())


def sidecar(factory_root: Path, epic_id: str = EPIC, node_id: str = NODE) -> Path:
    return factory_root / "worktrees" / epic_id / f"{node_id}.json"


def reset_origin_to_orphan(repo: Path, bare: Path, tmp_path: Path) -> str:
    """Force origin/main to an orphan root that does not descend from the pin.

    A fast-forward advance would keep the pin an ancestor, so a test that
    needs a *diverged* origin needs this: `merge-base --is-ancestor` then
    answers 1, whatever the distance happens to be.
    """
    scratch = tmp_path / "scratch-orphan"
    git(repo, "worktree", "add", "--quiet", "--detach", str(scratch))
    git(scratch, "checkout", "--quiet", "--orphan", "scratch-reset")
    (scratch / "README.md").write_text("fresh start\n", encoding="utf-8")
    git(scratch, "add", "README.md")
    git(scratch, "commit", "--quiet", "-m", "origin reset to orphan")
    git(repo, "push", "--quiet", "--force", "origin", "scratch-reset:main")
    git(repo, "worktree", "remove", "--force", str(scratch))
    return head(bare, "refs/heads/main")


# --- US1-S1: behind past the tolerance → rebuilt, archived (T001) -------------


def test_a_pin_behind_by_more_than_the_tolerance_is_rebuilt_and_archived(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """US1-S1 / FR-001: staleness past the tolerance rebuilds at dispatch.

    The recorded pin stays an ancestor the whole time — the validity test
    passes it, which is exactly why it never caught the live defect: measured
    on the day, the failing merge-base was three landings behind, and this test
    lands that same distance. The currency test measures how far behind the
    pin sits instead, and its failure arm is `_archive_node`: rebuilt at the
    current landing head, old branch archived and never deleted, sidecar
    rewritten to the new pin.
    """
    repo, bare = origin_repo
    first = ensure(repo, EPIC, NODE, factory_root=factory_root)
    old_pin = first.base_ref
    old_refs = all_local_refs(repo)

    new_head = old_pin
    for i in range(STALE_BASE_TOLERANCE_COMMITS + 1):
        new_head = land(repo, f"landing {i}: a sibling story merged\n")
    assert commits_behind(repo, old_pin, new_head) > STALE_BASE_TOLERANCE_COMMITS

    second = ensure(repo, EPIC, NODE, factory_root=factory_root)

    # Rebuilt: same directory, same branch name, a pin at the landing head.
    assert isinstance(second, PreparedWorktree)
    assert Path(second.path) == Path(first.path)
    assert second.branch == first.branch
    assert second.base_ref == new_head
    assert second.base_ref != old_pin
    assert head(Path(second.path)) == new_head
    # The rebuild really moved the *content*: the tree holds what the landings
    # brought, which a reused tree would not.
    assert "a sibling story merged" in (Path(second.path) / "README.md").read_text(
        encoding="utf-8"
    )
    # The old branch is archived, never deleted, and nothing else was swept.
    archived = archive_refs(repo)
    assert len(archived) == 1
    assert is_ancestor(repo, old_pin, head(repo, archived[0]))
    assert all_local_refs(repo).issuperset(old_refs)
    # The sidecar no longer offers the stale pin to a later dispatch.
    record = _read_record(sidecar(factory_root))
    assert record is not None
    assert record.base_ref == new_head
    assert old_pin not in sidecar(factory_root).read_text(encoding="utf-8")
    # One worktree per node still: the rebuild took the old registration with it.
    assert registered_worktrees(repo) == [str(Path(second.path).resolve())]


# --- US1-S2: at or within the tolerance → untouched (T002) --------------------
#
# The reuse control. It passes today and must keep passing: an implementation
# that rebuilt on any commit behind (the boolean trap) dies right here.


def test_a_pin_within_the_tolerance_is_returned_untouched(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """US1-S2 / FR-002: reuse is the rule and this story narrows it."""
    repo, bare = origin_repo
    first = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(first.path)
    dirty(worktree)
    before_status = status(worktree)
    before_refs = all_local_refs(repo)
    before_record = _read_record(sidecar(factory_root))

    # Strictly within the tolerance: one landing fewer than the boundary.
    for i in range(STALE_BASE_TOLERANCE_COMMITS - 1):
        land(repo, f"landing {i}: within tolerance\n")

    second = ensure(repo, EPIC, NODE, factory_root=factory_root)

    # Returned untouched: the same answer with the same pin.
    assert second == first
    assert second.base_ref == first.base_ref
    assert head(worktree) == head(Path(first.path))
    assert status(worktree) == before_status
    assert (worktree / NEW_FILE).read_text(encoding="utf-8") == "VALUE = 1\n"
    assert _read_record(sidecar(factory_root)) == before_record
    # No rebuild, no rebase, no reset: no archive exists and no ref moved —
    # the tree is exactly the one the last attempt left.
    assert archive_refs(repo) == []
    assert all_local_refs(repo) == before_refs
    assert registered_worktrees(repo) == [str(worktree.resolve())]


def test_a_pin_behind_by_exactly_the_tolerance_is_returned_untouched(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """US1-S2's boundary: "more than the configured tolerance" excludes the edge.

    The requirement's word is "more than" — a pin behind by exactly the
    tolerance is *at* it, and FR-002 says at-or-within is reused.
    """
    repo, bare = origin_repo
    first = ensure(repo, EPIC, NODE, factory_root=factory_root)
    before_refs = all_local_refs(repo)

    for i in range(STALE_BASE_TOLERANCE_COMMITS):
        land(repo, f"landing {i}: exactly the tolerance\n")

    second = ensure(repo, EPIC, NODE, factory_root=factory_root)

    assert second == first
    assert second.base_ref == first.base_ref
    assert head(Path(second.path)) == head(Path(first.path))
    assert archive_refs(repo) == []
    assert all_local_refs(repo) == before_refs


# --- US1-S3: not an ancestor → rebuilt exactly as today (T003) ----------------


def test_a_pin_that_is_not_an_ancestor_is_rebuilt_as_today(
    origin_repo: tuple[Path, Path], factory_root: Path, tmp_path: Path
) -> None:
    """US1-S3 / FR-003: the validity check keeps its current behaviour.

    The origin is reset to an orphan root, so the recorded pin is *diverged*
    rather than merely behind — and the distance on that shape is one commit,
    well inside any sane tolerance. A currency test that had quietly replaced
    the validity test would reuse this worktree; the rebuild here is the old
    arm's, reached at a distance unable to explain it.
    """
    repo, bare = origin_repo
    first = ensure(repo, EPIC, NODE, factory_root=factory_root)
    old_pin = first.base_ref
    old_refs = all_local_refs(repo)

    new_head = reset_origin_to_orphan(repo, bare, tmp_path)
    assert not is_ancestor(repo, old_pin, new_head)
    # Distance small: only the validity test can be what fires the rebuild.
    assert commits_behind(repo, old_pin, new_head) <= STALE_BASE_TOLERANCE_COMMITS

    second = ensure(repo, EPIC, NODE, factory_root=factory_root)

    assert second.base_ref == new_head
    assert second.base_ref != old_pin
    assert head(Path(second.path)) == new_head
    assert (Path(second.path) / "README.md").read_text(
        encoding="utf-8"
    ) == "fresh start\n"
    archived = archive_refs(repo)
    assert len(archived) == 1
    assert all_local_refs(repo).issuperset(old_refs)


def test_an_unreachable_origin_still_raises_when_the_currency_test_reads_the_head(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """A failed fetch is infrastructure, never a quiet reuse (fail closed).

    The currency test reads the same landing-branch head `_remote_head` reads,
    so an unreachable origin must keep raising `WorktreeError`: a quiet stale
    pin is the defect, and an archive created on an answer nobody read would
    discard work over a network blip.
    """
    repo, bare = origin_repo
    ensure(repo, EPIC, NODE, factory_root=factory_root)
    git(repo, "remote", "set-url", "origin", str(bare.parent / "gone-really-gone.git"))

    with pytest.raises(WorktreeError) as raised:
        ensure(repo, EPIC, NODE, factory_root=factory_root)

    assert "git fetch" in str(raised.value)
    assert archive_refs(repo) == []


# --- US1-S4: never between attempts (T004, plan trap 3) -----------------------
#
# The R5 proof. The workflow's structure is what makes FR-004 true:
# `prepare_worktree` is executed once per node, before the attempt loop, and
# every attempt — the debugger's included — reuses `record.prepared`. A retry
# therefore cannot fire a currency test that lives in `ensure`, not because
# `ensure` counts anything, but because the caller that would run it between
# attempts is not called. This test drives the real workflow end to end with
# the real `ensure` wired in.


async def test_a_retry_of_a_prepared_node_opens_the_same_tree_untouched(
    tmp_path: Path,
) -> None:
    """US1-S4 / FR-004 / R5: the currency test runs at dispatch, never mid-node."""
    from factory.workgraph.models import NodeState
    from tests.test_interpreter import (
        EPIC_ID,
        PROXY_URL,
        WORKFLOW_ID,
        ScriptedWorld,
        failing,
        make_graph,
        make_node,
        passing,
    )

    env = await WorkflowEnvironment.start_time_skipping()
    try:
        repo = build_target_repo(tmp_path / "target")
        factory_root = tmp_path / ".ergane"
        branch = f"factory/{EPIC_ID}/us1"
        marker = "the first attempt left this in the tree\n"

        script = ScriptedWorld({"us1": [failing(1), passing()]}, client=env.client)

        prepared: list[PreparedWorktree] = []

        @activity.defn(name="prepare_worktree")
        async def real_prepare_worktree(
            request: PrepareWorktreeInput,
        ) -> PreparedWorktree:
            script._log("prepare_worktree", request.node_id)
            script.prepare_requests.append(request)
            result = ensure(
                request.target_repo,
                request.epic_id,
                request.node_id,
                factory_root=factory_root,
            )
            prepared.append(result)
            # Work the first attempt leaves behind; a rebuild between attempts
            # would archive-and-erase it.
            (Path(result.path) / "attempt_one_work.txt").write_text(marker)
            return result

        saved = script.activities()
        activities = [
            candidate
            for candidate in saved
            if activity._Definition.must_from_callable(candidate).name
            != "prepare_worktree"
        ] + [real_prepare_worktree]

        graph = make_graph([make_node("us1", "US1")], target_repo=str(repo))

        async with Worker(
            env.client,
            task_queue="workgraph",
            workflows=[EpicWorkflow],
            activities=activities,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                EpicWorkflow.run,
                EpicInput(graph=graph, proxy_url=PROXY_URL),
                id=WORKFLOW_ID,
                task_queue="workgraph",
            )
            status = await handle.result()

        assert status.nodes["us1"].state == NodeState.MERGED

        # The structural half: exactly one preparation for a node that ran two
        # attempts. A workflow that re-prepared between attempts re-ran the
        # currency test between attempts, and this line is where it dies.
        assert len(prepared) == 1

        first_pin = prepared[0].base_ref
        moved = first_pin
        for i in range(STALE_BASE_TOLERANCE_COMMITS + 1):
            moved = land(repo, f"landing {i}: moved while the node ran\n")
        # The landing branch really moved past the tolerance while the node was
        # mid-flight — the exemption is not riding on a quiet world.
        assert commits_behind(repo, first_pin, moved) > STALE_BASE_TOLERANCE_COMMITS

        # The between-attempts half: the tree attempt 2 opened is the one
        # attempt 1 left, marker and all. And no rebuild happened anywhere in
        # that life: the branch is still in place, no archive ref was created.
        worktree = Path(prepared[0].path)
        assert worktree.is_dir()
        assert (worktree / "attempt_one_work.txt").read_text() == marker
        assert ref_exists(repo, f"refs/heads/{branch}")
        assert archive_refs(repo, EPIC_ID, "us1") == []

        # The dispatch-time control: a *fresh* preparation against this same
        # state really does rebuild. The exemption above is not "nothing was
        # far enough behind" — it is that the currency test lives on the
        # preparation path and that path ran once.
        redispatched = ensure(repo, EPIC_ID, "us1", factory_root=factory_root)
        assert redispatched.base_ref == moved
        archived = archive_refs(repo, EPIC_ID, "us1")
        assert len(archived) == 1
    finally:
        await env.shutdown()


# --- US1-S5: explicit `base_ref` honoured without a currency test (T005) ------


def test_an_explicit_base_ref_is_honoured_without_a_currency_test(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """US1-S5 / FR-005: an explicit pin is the caller's authority.

    The caller's instruction is far behind the landing branch and still wins:
    the worktree is built exactly there, with no rebuild and no archive. FR-005
    keeps the documented authority statement true after the currency test
    exists, and this control dies the day a currency check reaches the
    explicit arm.
    """
    repo, bare = origin_repo
    explicit = head(repo)

    for i in range(STALE_BASE_TOLERANCE_COMMITS + 3):
        land(repo, f"landing {i}: the caller never asked about these\n")
    assert commits_behind(repo, explicit, head(repo, "refs/remotes/origin/main")) > (
        STALE_BASE_TOLERANCE_COMMITS
    )

    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root, base_ref=explicit)

    assert prepared.base_ref == explicit
    assert head(Path(prepared.path)) == explicit
    assert archive_refs(repo) == []
    assert registered_worktrees(repo) == [str(Path(prepared.path).resolve())]


# --- US1 FR-001: the adopt arm has no pin to judge (T006, plan trap 4) --------


def test_an_adopted_worktree_is_not_rebuilt_by_the_currency_test(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """US1 FR-001: a swept record is adopted pinning to where it stands.

    The sidecar is deleted — the shape of an older run's record being swept —
    and then the landing branch moves far past any tolerance. `ensure` finds a
    worktree and no pin, adopts the tree, and answers the worktree's own HEAD:
    there is nothing for the currency test to judge, and building the test on
    an invented pin is exactly how in-progress work gets discarded.
    """
    repo, bare = origin_repo
    first = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(first.path)
    (worktree / "in_progress.txt").write_text("half done\n")
    sidecar(factory_root).unlink()

    for i in range(STALE_BASE_TOLERANCE_COMMITS + 5):
        land(repo, f"landing {i}: the adopt arm does not care\n")

    second = ensure(repo, EPIC, NODE, factory_root=factory_root)

    assert isinstance(second, PreparedWorktree)
    assert Path(second.path) == worktree
    # Adopted: pinned to where it stands, in-progress work and all.
    assert second.base_ref == head(worktree)
    assert (worktree / "in_progress.txt").read_text() == "half done\n"
    assert archive_refs(repo) == []
    assert registered_worktrees(repo) == [str(worktree.resolve())]
    # The adopted pin is recorded, so the next dispatch has a real pin to
    # judge — the new one, which the currency test will read.
    record = _read_record(sidecar(factory_root))
    assert record is not None
    assert record.base_ref == head(worktree)


# --- T007: the tolerance is configuration, in commits behind ------------------


def test_the_tolerance_is_a_positive_commit_count_not_a_switch() -> None:
    """T007 / trap 2: a number with a unit, never a boolean or a clock.

    "Any commit behind" rebuilds almost every worktree on a live roadmap;
    wall-clock time ignores how fast a landing branch actually moves. The
    shipped default is a count of commits behind, positive, and named for its
    unit at every call site that overrides it.
    """
    assert type(STALE_BASE_TOLERANCE_COMMITS) is int
    assert STALE_BASE_TOLERANCE_COMMITS > 0


@pytest.mark.parametrize(
    ("tolerance", "expect_rebuild"),
    [
        (0, True),  # zero: one landing behind is already too far
        (STALE_BASE_TOLERANCE_COMMITS, False),  # shipped default: well within
    ],
)
def test_the_tolerance_knob_moves_the_boundary(
    tmp_path: Path, tolerance: int, expect_rebuild: bool
) -> None:
    """T007 / FR-001: the knob moves the boundary, in the unit it declares.

    Same world — one sibling landing — two callers. At tolerance zero the
    worktree is rebuilt and the old branch archived; at the shipped default
    the same world is inside the rule and the tree is reused untouched. The
    boundary belongs to the caller who sets the dial.
    """
    repo = build_target_repo(tmp_path / "target")
    root = tmp_path / ".ergane"

    first = ensure(repo, EPIC, NODE, factory_root=root)
    land(repo, "one sibling landing\n")

    second = ensure(
        repo,
        EPIC,
        NODE,
        factory_root=root,
        stale_base_tolerance_commits=tolerance,
    )

    if expect_rebuild:
        assert second.base_ref != first.base_ref
        assert archive_refs(repo)
        assert head(Path(second.path)) == head(repo, "refs/heads/main")
    else:
        assert second == first
        assert second.base_ref == first.base_ref
        assert archive_refs(repo) == []