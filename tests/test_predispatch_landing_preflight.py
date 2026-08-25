"""The epic refuses at dispatch, before it spends (107 US4).

Two facts decide whether a verified story can land, both knowable offline, and
until this story neither was asked before an agent was paid: which repository
owns each node's worktree, and whether the landing branch is declared or merely
inferred from whatever branch the target clone is sitting on.

US1 landed the ownership predicate and made `ensure()` refuse on it. That is the
enforcement and it is per node, at the worker, at the last free moment. This is
the *report*: epic-wide, offline, before the first key is issued, naming every
offending node in one pass rather than the first one — an operator fixing one
refusal per dispatch is the failure mode the collected-findings discipline in
this module already exists to avoid.

Three things these tests pin that a cheaper version would not:

- **The factory root is part of the answer, never an assumption** (plan R5). The
  CLI resolves the operator host's root and the worker resolves its own; on a
  split host the CLI arm reads a directory tree that is not the one the epic will
  build in, so a finding that did not name the root it read would leave "checked
  and clean" indistinguishable from "checked the wrong disk".
- **Silence costs one git call per *existing* directory.** A graph of sixteen
  nodes on a host that has never built it must not shell out sixteen times, and
  the assertion is on the call count, not on the wall clock.
- **One implementation, two surfaces** (FR-011). The parity test drives the
  roadmap's pre-dispatch activity and `ergane build start`'s preflight over one
  fixture and asserts the finding lists are *equal*, so a second copy of either
  check cannot be added without a red test.

Real git and real repositories throughout (plan trap 15): the subject is what
git says about a directory and what a committed manifest declares, and a fake
would only prove the fake agrees with itself.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from factory.workgraph import preflight as preflight_module
from factory.workgraph.models import WorkGraph, WorkNode
from factory.workgraph.preflight import (
    LANDING_BRANCH_CHECK,
    WORKTREE_OWNERSHIP_CHECK,
    landing_branch_findings,
    landing_readiness_preflight,
    worktree_ownership_findings,
)
from factory.workgraph.worktree import ensure, worktree_path
from tests.conftest import FAKE_MASTER_KEY, FakeLiteLLM
from tests.target_repo import git

EPIC = "107-a-landing-refuses"
NODES = ("us1", "us2")


# --- setup -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_operator_git_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every identity git could fall back on (tests/test_worktree.py)."""
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """One worker-host state directory, shared by both clones — the whole point.

    `worktree_path` takes no repository, so two dispatchers of one epic id on one
    host resolve the same node directory. The preflight reads this root and says
    so in every finding.
    """
    return tmp_path / ".ergane"


@pytest.fixture
def repo_a(target_repo: Callable[..., Path]) -> Path:
    """The clone that gets there first, and ends up owning the directories."""
    return target_repo("landing-branch", name="clone-a")


@pytest.fixture
def repo_b(target_repo: Callable[..., Path]) -> Path:
    """A second clone of the same repository, and the one the epic dispatches."""
    return target_repo("landing-branch", name="clone-b")


def graph_for(repo: Path, *, node_ids: tuple[str, ...] = NODES) -> WorkGraph:
    """A graph of `node_ids` dispatched against `repo` — the check's whole input."""
    return WorkGraph(
        epic_id=EPIC,
        feature="107-a-landing-refuses",
        specs_root="/srv/factory/specs",
        target_repo=str(repo),
        nodes=[
            WorkNode(
                id=node_id,
                story_key=f"US{index}",
                persona="implementer",
                spec_ref=f"specs/107/spec.md#US{index}",
                requirement_keys=[f"US{index}"],
                depends_on=[],
            )
            for index, node_id in enumerate(node_ids, start=1)
        ],
    )


def register_nodes(repo: Path, factory_root: Path) -> list[Path]:
    """Create a worktree for every node of the graph, registered to `repo`."""
    return [
        Path(ensure(repo, EPIC, node_id, factory_root=factory_root).path).resolve()
        for node_id in NODES
    ]


def counted_ownership(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record every directory the check asks git about, and answer for real.

    One `_worktree_ownership` call is exactly one `git rev-parse` (US1's helper
    asks both of its questions in a single invocation), so this list *is* the git
    call count — and it still returns git's real answer, because a fake here
    would prove nothing about a real worktree.
    """
    asked: list[Path] = []
    real = preflight_module._worktree_ownership

    def spy(repo: Path, path: Path) -> Any:
        asked.append(path)
        return real(repo, path)

    monkeypatch.setattr(preflight_module, "_worktree_ownership", spy)
    return asked


# --- T029 / US4-S1, FR-009: every offending node, in one pass -----------------


def test_every_cross_registered_node_is_reported_with_its_owning_clone(
    repo_a: Path, repo_b: Path, factory_root: Path
) -> None:
    """US4-S1: two nodes, both foreign, both named — not the first of them.

    Clone A registered both node directories; the epic is dispatched against
    clone B. Before this story nothing asked, and each node discovered it
    separately, hours apart, after its agent had been paid for.
    """
    paths = register_nodes(repo_a, factory_root)

    findings = worktree_ownership_findings(graph_for(repo_b), factory_root)

    assert [finding.check for finding in findings] == [WORKTREE_OWNERSHIP_CHECK] * 2
    assert all(finding.passed is False for finding in findings)
    # Not a transport finding: nothing was dialled, so nothing could be down.
    assert all(finding.transport is False for finding in findings)

    for node_id, path, finding in zip(NODES, paths, findings):
        assert f"node {node_id}" in finding.detail
        assert str(path) in finding.detail
        # The clone that owns the registration, and the one the epic named.
        assert str(repo_a.resolve()) in finding.detail
        assert str(repo_b.resolve()) in finding.detail
        # The root this check read (plan R5): the CLI's and the worker's can
        # differ, so "checked and clean" must be distinguishable from "checked
        # the wrong disk".
        assert str(factory_root.resolve()) in finding.detail
        # The remedy is issued against the owning clone, because `git worktree
        # remove` run in the dispatched repo answers `fatal: not a working tree`.
        assert (
            f"git -C {repo_a.resolve()} worktree remove --force {path}"
            in finding.detail
        )


def test_the_remedy_block_clears_the_refusal_it_names(
    repo_a: Path, repo_b: Path, factory_root: Path
) -> None:
    """US4-S1: the printed command is run, and the next check is silent.

    Trap 6: nothing in the tree sweeps these directories, so the remedy is the
    operator's whole next move and an untested one is a guess. Run exactly what
    the finding printed, against the clone it named.
    """
    register_nodes(repo_a, factory_root)
    graph = graph_for(repo_b)

    for finding in worktree_ownership_findings(graph, factory_root):
        remedy = finding.detail.split("git -C ", 1)[1]
        repo, _, worktree = remedy.partition(" worktree remove --force ")
        git(Path(repo), "worktree", "remove", "--force", worktree.strip())

    assert worktree_ownership_findings(graph, factory_root) == []


# --- T030 / US4-S2, FR-009: silence, and what it costs ------------------------


def test_a_graph_with_no_worktrees_yet_is_silent_and_asks_git_nothing(
    repo_b: Path, factory_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US4-S2: nothing on disk is nothing to report, and nothing to shell out for.

    Every epic's first dispatch is this case. A check that paid a subprocess per
    node to learn that a directory does not exist would be a tax on the common
    path for a fact `Path.is_dir()` already answers.
    """
    asked = counted_ownership(monkeypatch)

    assert worktree_ownership_findings(graph_for(repo_b), factory_root) == []
    assert asked == []


def test_correctly_owned_worktrees_are_silent_at_one_git_call_each(
    repo_a: Path, factory_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US4-S2: the same clone that registered them dispatches, and nothing is said.

    The relaunch case — an epic reset and started again against its own clone —
    must stay silent, or the check would refuse every second dispatch of every
    epic. One git call per existing directory, and not one more.
    """
    paths = register_nodes(repo_a, factory_root)
    asked = counted_ownership(monkeypatch)

    assert worktree_ownership_findings(graph_for(repo_a), factory_root) == []
    assert asked == paths


# --- T031 / US4-S3, FR-010: declared, or inferred and said so -----------------


def test_a_declared_landing_branch_reports_nothing(repo_a: Path) -> None:
    """US4-S3: the manifest answers, so the landing has a declaration to obey.

    The `landing-branch` fixture declares `landing_branch: ergane-buildout` while
    its checkout sits on `main` — the disagreement that made this spec — so a
    check that read HEAD and called it declared would pass this test for the
    wrong reason. It does not: the branch reported by the resolver is the
    declared one.
    """
    assert git(repo_a, "symbolic-ref", "--short", "HEAD").strip() == "main"

    assert landing_branch_findings(graph_for(repo_a)) == []


@pytest.mark.parametrize("variant", ["missing-manifest", "malformed-manifest"])
def test_a_landing_branch_that_resolves_by_fallback_is_reported(
    variant: str, target_repo: Callable[..., Path]
) -> None:
    """US4-S3: no readable manifest, so the branch is a guess — and it says so.

    `landing_branch()` fails open by design (plan trap 5): a target clone with a
    missing or typo'd manifest silently reinstates the defect this spec exists to
    remove, reading the branch off whatever HEAD the clone is sitting on. The
    finding names the repository, the branch that *would* be used, and the fact
    that HEAD rather than a declaration produced it.
    """
    repo = target_repo(variant, name=f"clone-{variant}")

    findings = landing_branch_findings(graph_for(repo))

    assert [finding.check for finding in findings] == [LANDING_BRANCH_CHECK]
    finding = findings[0]
    assert finding.passed is False
    assert finding.transport is False
    assert str(repo.resolve()) in finding.detail
    # The branch that would be used, read the way the landing reads it.
    assert git(repo, "symbolic-ref", "--short", "HEAD").strip() == "main"
    assert "main" in finding.detail
    assert "inferred" in finding.detail
    assert "landing_branch" in finding.detail


def test_a_target_repo_this_host_cannot_read_is_not_a_fallback_finding(
    tmp_path: Path,
) -> None:
    """A repository the check cannot reach at all has no branch to report.

    The CLI arm runs on the operator's host and the roadmap's on the worker's
    (plan R5), so a target clone that is simply not on this disk is an unchecked
    fact, not a resolved-by-fallback one: there is no branch that "would be
    used", and inventing a finding here would make a check that cannot see the
    repository indistinguishable from one that read a broken manifest.
    """
    assert landing_branch_findings(graph_for(tmp_path / "no-such-clone")) == []


# --- T032 / US4-S4, FR-011: one implementation, two surfaces ------------------


WELL_FORMED = (
    Path(__file__).resolve().parent / "fixtures" / "prompt_assembly" / "903-well-formed"
)


def plant_ready(destination: Path) -> Path:
    """Copy the well-formed fixture trio into a corpus and mark it `ready`.

    Borrowed from `tests/test_roadmap_prompt_assembly.py`: this suite needs the
    assembly half of both preflights to be *silent*, so the only findings either
    surface returns are the two this story adds.
    """
    shutil.copytree(WELL_FORMED, destination)
    spec_path = destination / "spec.md"
    text = spec_path.read_text(encoding="utf-8")
    assert "state: draft" in text, "903-well-formed is no longer authored draft"
    spec_path.write_text(
        text.replace("state: draft", "state: ready", 1), encoding="utf-8"
    )
    return destination


async def test_both_dispatch_surfaces_return_the_same_findings(
    tmp_path: Path,
    target_repo: Callable[..., Path],
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US4-S4: the roadmap's activity and `ergane build start` answer alike.

    Asserted rather than assumed (FR-011). The two surfaces build their own
    client and their own registry and resolve their own factory root — that split
    is deliberate — but the checks and their wording come from this one module,
    and equality of the two lists is what makes a second implementation
    impossible to add quietly.

    The fixture is deliberately doubly broken: two node worktrees registered to
    another clone *and* a dispatched clone with no readable manifest, so both new
    checks speak on both surfaces in one pass.
    """
    from factory.activities import roadmap_activities
    from factory.cli.nouns import build as build_noun
    from factory.usage.litellm_client import LiteLLMClient
    from temporalio.testing import ActivityEnvironment

    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    plant_ready(specs_root / "001-short-links")

    owner = target_repo("landing-branch", name="clone-a")
    dispatched = target_repo("missing-manifest", name="clone-b")
    register_nodes(owner, factory_root)

    from factory.workgraph.derive import derive_workgraph

    graph = derive_workgraph(
        (specs_root / "001-short-links" / "spec.md").read_text(encoding="utf-8"),
        epic_id=EPIC,
        feature="001-short-links",
        specs_root=str(specs_root),
        target_repo=str(dispatched),
    )
    assert [node.id for node in graph.nodes] == list(NODES)

    # Both surfaces resolve the runtime root from the host they run on; point
    # both at the fixture root so the comparison is of the checks, not the hosts.
    monkeypatch.setenv("ERGANE_ROOT", str(factory_root))

    fake = FakeLiteLLM()

    def client(*_args: Any, **_kwargs: Any) -> LiteLLMClient:
        return LiteLLMClient(
            base_url=fake.base_url,
            master_key=FAKE_MASTER_KEY,
            transport=fake.transport,
        )

    monkeypatch.setattr(build_noun, "_preflight_registry", dict)
    monkeypatch.setattr(build_noun, "_open_preflight_client", client)
    monkeypatch.setattr(roadmap_activities, "_preflight_registry", dict)
    monkeypatch.setattr(roadmap_activities, "_preflight_client", client)

    from_cli = await build_noun._run_preflight(graph)
    from_roadmap = await ActivityEnvironment().run(
        roadmap_activities.preflight_spec,
        roadmap_activities.PreflightInput(
            graph=graph,
            proxy_url=fake.base_url,
            spec_dir="001-short-links",
            specs_root=str(specs_root),
        ),
    )

    assert from_cli == from_roadmap
    assert [finding.check for finding in from_cli] == [
        WORKTREE_OWNERSHIP_CHECK,
        WORKTREE_OWNERSHIP_CHECK,
        LANDING_BRANCH_CHECK,
    ]
    assert str(owner.resolve()) in from_cli[0].detail
    assert str(factory_root.resolve()) in from_cli[1].detail
    assert str(dispatched.resolve()) in from_cli[2].detail

    # Both surfaces refuse: a finding is a refusal here, and `ergane build start`
    # maps it to a user error (exit 1) rather than a service failure (exit 3).
    assert await build_noun._preflight_exit_code(from_cli) == 1


def test_the_shared_entry_point_collects_both_checks_in_order(
    repo_a: Path, factory_root: Path, target_repo: Callable[..., Path]
) -> None:
    """Both checks run and both are collected; neither short-circuits the other.

    An operator fixing one refusal per dispatch, with the second revealed only
    after the first is cleared, is the failure mode this module's collected
    findings already exist to avoid — and it is the more expensive mistake here,
    because each round trip is a dispatch the operator has to start again.
    """
    dispatched = target_repo("missing-manifest", name="clone-b")
    register_nodes(repo_a, factory_root)
    graph = graph_for(dispatched)

    findings = landing_readiness_preflight(graph, factory_root)

    assert findings == (
        worktree_ownership_findings(graph, factory_root)
        + landing_branch_findings(graph)
    )
    assert [finding.check for finding in findings] == [
        WORKTREE_OWNERSHIP_CHECK,
        WORKTREE_OWNERSHIP_CHECK,
        LANDING_BRANCH_CHECK,
    ]


def test_the_check_reads_no_environment_of_its_own(
    repo_a: Path, repo_b: Path, factory_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The root is the caller's to supply, never the module's to find (plan R5).

    `ergane build start` runs in the operator's shell and the roadmap activity on
    the worker, and on a split host those two roots differ. A module that read
    `ERGANE_ROOT` itself would answer for whichever process imported it, and the
    finding's named root would be a fiction.
    """
    register_nodes(repo_a, factory_root)
    monkeypatch.setenv("ERGANE_ROOT", str(factory_root / "somewhere-else"))
    monkeypatch.setenv("FACTORY_ROOT", str(factory_root / "somewhere-else"))

    findings = worktree_ownership_findings(graph_for(repo_b), factory_root)

    assert [str(factory_root.resolve()) in f.detail for f in findings] == [True] * 2
    assert worktree_path(factory_root, EPIC, NODES[0]).is_dir()


def test_a_target_repo_this_host_cannot_read_reports_no_ownership_finding(
    repo_a: Path, factory_root: Path, tmp_path: Path
) -> None:
    """An unreachable dispatched clone leaves the comparison unmade, not crashed.

    The same split-host reasoning as the landing-branch arm: `ergane build start`
    may be run where the target clone is not, and there is no identity to compare
    a directory against. It is an unchecked fact — `ensure()` on the worker is
    the enforcement (plan R5) — and never a traceback out of a preflight that
    every other check would still have had something to say in.
    """
    register_nodes(repo_a, factory_root)

    assert worktree_ownership_findings(graph_for(tmp_path / "gone"), factory_root) == []
