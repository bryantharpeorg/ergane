"""068 US3: every `build` verb that acts on a started epic is keyed by its id.

`ergane build reset` was the one verb in the family that took a compiled
artifact path instead of an epic id (`factory/cli/nouns/build.py`, the `reset`
subparser).  That is the verb an operator reaches for at exactly the moment the
epic has gone wrong, so the inconsistency cost five interventions in the
reported session before the workaround was known.

Two things are pinned here, and they pull in opposite directions on purpose:

- `reset <epic-id>` must resolve `<specs_root>/<epic_id>/workgraph.json`
  **itself**, with no Temporal read that could supply it.  There is no such
  read available: `describe()` exposes memo and static details only — no input
  — `ergane build start` sets no memo, and `fetch_history()` is gone past
  retention, which is precisely the state `reset` exists for.  Every test below
  that touches Temporal does so through a client whose only method is
  `describe()` and whose every answer is `NOT_FOUND`, so a graph that arrived
  from the server could not have arrived at all.
- `reset <path/to/workgraph.json>` must keep working.  Six call sites in
  `tests/test_ergane_build.py` pass one, and an argument that used to work and
  now means something else is its own defect.  A path is never silently
  reinterpreted as an epic id: a mistyped path fails naming the path.

**Concurrency note (068 plan, trap 8a).** US2 and US3 both edit
`factory/cli/nouns/build.py` — US2 widens `_reset_epic`, US3 rewrites the
`reset` subparser and `reset_command` — and both declare `depends_on: []`, so
nothing in the graph orders them.  This story's answer to the fork the plan
left open: **dispatch this epic at `--max-concurrent-nodes 1`**, rather than
adding a `depends_on: [us2]` edge that would misstate the relationship.
`depends_on` models what a story needs to *exist*; US3 needs nothing from US2.
The contention is over one file, which is a scheduling fact, not a graph one,
and encoding it as an edge would leave a false dependency in the compiled
artifact for every future re-derivation of this spec.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest
from temporalio.service import RPCError, RPCStatusCode

import factory.cli.nouns as nouns
from factory.activities.agent_activities import ERGANE_ROOT_ENV, FACTORY_ROOT_ENV
from factory.cli.main import main as ergane_main
from factory.cli.nouns.build import ARTIFACT_NAME, add_parser, workflow_id
from factory.workgraph.worktree import branch_name, ensure
from tests.target_repo import git, git_env

EPIC_ID = "091-reset-is-keyed-by-the-epic-id"
NODE_IDS = ("us1", "us2")

#: A node of a *different* epic, prepared in the same factory root.  Reset must
#: not touch it: "resets the right nodes" is only an assertion if there is a
#: wrong node available to reach.
DECOY_EPIC_ID = "090-a-neighbouring-epic"
DECOY_NODE_ID = "us9"


# --- harness ------------------------------------------------------------------


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


class AbsentFromTemporal:
    """A client for which every workflow is gone, and history is unreachable.

    The fake exposes `describe()` and nothing else — no `fetch_history`, no
    `query` — so any implementation that tried to recover the graph from the
    server would raise `AttributeError` here rather than pass.  `describe()`
    itself answers `NOT_FOUND`, which is the state a terminated epic is in by
    the time anyone runs `reset`.
    """

    def __init__(self) -> None:
        self.dialled: list[str] = []

    def get_workflow_handle(self, wf_id: str) -> Any:
        self.dialled.append(wf_id)

        class Handle:
            async def describe(self) -> None:
                raise RPCError(
                    message=f"workflow {wf_id} not found",
                    status=RPCStatusCode.NOT_FOUND,
                    raw_grpc_status=b"",
                )

        return Handle()


def _patch_client(
    monkeypatch: pytest.MonkeyPatch, client: AbsentFromTemporal
) -> AbsentFromTemporal:
    async def factory() -> AbsentFromTemporal:
        return client

    monkeypatch.setattr(nouns, "_open_client", factory)
    return client


def _forbid_temporal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any Temporal connection at all is a failure for the refusal tests."""

    async def factory() -> Any:
        raise AssertionError("reset dialled Temporal before resolving the graph")

    monkeypatch.setattr(nouns, "_open_client", factory)


class ResetTarget(NamedTuple):
    repo: Path
    factory_root: Path
    specs_root: Path
    graph_path: Path
    worktrees: dict[str, Path]
    decoy_worktree: Path


def _plant(
    target_repo: Callable[..., Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ResetTarget:
    """A target repo with survivors, plus the epic's compiled graph on disk.

    The graph is written where `reset <epic-id>` must find it —
    `<specs_root>/<epic_id>/workgraph.json` — and nowhere else, so a test that
    passes has resolved it from the epic id rather than from a path it was
    handed.
    """
    factory_root = tmp_path / ".factory"
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(factory_root))
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)

    repo = target_repo("passing", name="reset-by-id-repo")
    worktrees: dict[str, Path] = {}
    for node_id in NODE_IDS:
        prepared = ensure(repo, EPIC_ID, node_id, factory_root=factory_root)
        worktree = Path(prepared.path)
        worktrees[node_id] = worktree
        (worktree / f"added_by_{node_id}.py").write_text(
            f"VALUE_{node_id} = 1\n", encoding="utf-8"
        )

    decoy = Path(
        ensure(repo, DECOY_EPIC_ID, DECOY_NODE_ID, factory_root=factory_root).path
    )
    (decoy / "added_by_the_neighbour.py").write_text("VALUE = 1\n", encoding="utf-8")

    specs_root = (tmp_path / "specs").resolve()
    spec_dir = specs_root / EPIC_ID
    spec_dir.mkdir(parents=True, exist_ok=True)
    graph_path = spec_dir / ARTIFACT_NAME
    graph_path.write_text(
        json.dumps(
            {
                "epic_id": EPIC_ID,
                "feature": EPIC_ID,
                "specs_root": str(specs_root),
                "target_repo": str(repo),
                "nodes": [
                    {
                        "id": node_id,
                        "story_key": node_id.upper(),
                        "persona": "implementer",
                        "spec_ref": f"{EPIC_ID}:{node_id.upper()}",
                        "requirement_keys": [f"FR-00{index + 1}"],
                        "depends_on": [],
                        "depends_on_merged": [],
                        "timeout_override_s": None,
                    }
                    for index, node_id in enumerate(NODE_IDS)
                ],
            }
        ),
        encoding="utf-8",
    )
    return ResetTarget(
        repo=repo,
        factory_root=factory_root,
        specs_root=specs_root,
        graph_path=graph_path,
        worktrees=worktrees,
        decoy_worktree=decoy,
    )


def _ref_exists(repo: Path, ref: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return completed.returncode == 0


def _archive_refs(repo: Path, epic_id: str) -> set[str]:
    refs = git(
        repo, "for-each-ref", "--format=%(refname)", "refs/heads"
    ).splitlines()
    return {ref for ref in refs if ref.startswith(f"refs/heads/archive/factory/{epic_id}/")}


def _assert_reset(target: ResetTarget, result: Run) -> None:
    """The survivors are archived, the sidecars are gone, the neighbour is not."""
    assert result.code == 0, result.stderr
    for node_id in NODE_IDS:
        assert f"{node_id}:" in result.stdout
        assert not target.worktrees[node_id].exists()
        sidecar = target.factory_root / "worktrees" / EPIC_ID / f"{node_id}.json"
        assert not sidecar.exists()
        assert not _ref_exists(target.repo, f"refs/heads/{branch_name(EPIC_ID, node_id)}")
    assert _archive_refs(target.repo, EPIC_ID)

    # The right nodes, and only those: the neighbouring epic's node is intact
    # and was never reported on.
    assert target.decoy_worktree.exists()
    assert f"{DECOY_NODE_ID}:" not in result.stdout
    assert _ref_exists(
        target.repo, f"refs/heads/{branch_name(DECOY_EPIC_ID, DECOY_NODE_ID)}"
    )
    assert (
        target.factory_root / "worktrees" / DECOY_EPIC_ID / f"{DECOY_NODE_ID}.json"
    ).exists()


# --- T019 (US3-S1) -------------------------------------------------------------


def test_reset_resolves_the_graph_from_the_epic_id_without_temporal_history(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009: an epic id in, the compiled graph resolved off disk, nodes reset."""
    target = _plant(target_repo, tmp_path, monkeypatch)
    client = _patch_client(monkeypatch, AbsentFromTemporal())

    result = run(
        "build", "reset", EPIC_ID, "--specs-root", str(target.specs_root)
    )

    _assert_reset(target, result)
    # The one Temporal read reset makes is the safety check, and it answered
    # NOT_FOUND.  The graph therefore came from
    # <specs_root>/<epic_id>/workgraph.json and could have come from nowhere else.
    assert client.dialled == [workflow_id(EPIC_ID)]


# --- T020 (US3-S2) -------------------------------------------------------------


def test_unknown_epic_id_is_refused_naming_the_id_and_where_it_looked(
    run: Callable[..., Run],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S2: the refusal names the epic id and the path it resolved."""
    _forbid_temporal(monkeypatch)
    specs_root = tmp_path / "specs"
    specs_root.mkdir()

    result = run(
        "build", "reset", "999-no-such-epic", "--specs-root", str(specs_root)
    )

    assert result.code != 0
    assert "999-no-such-epic" in result.stderr
    expected = specs_root.resolve() / "999-no-such-epic" / ARTIFACT_NAME
    assert str(expected) in result.stderr


# --- T021 (US3-S3) -------------------------------------------------------------


def _build_subcommands() -> dict[str, argparse.ArgumentParser]:
    """Every `ergane build` subcommand, read off the real parser."""
    parser = argparse.ArgumentParser(prog="ergane")
    nouns_group = parser.add_subparsers(dest="noun", required=True)
    add_parser(nouns_group)
    build_parser = nouns_group.choices["build"]
    action = next(
        candidate
        for candidate in build_parser._actions
        if isinstance(candidate, argparse._SubParsersAction)
    )
    return dict(action.choices)


def _first_positional(parser: argparse.ArgumentParser) -> str | None:
    for action in parser._actions:
        if action.option_strings:
            continue
        return action.dest
    return None


#: The verbs that act on an epic that has already been started.  Every one of
#: them is something an operator does *to a running or finished epic*, and the
#: only handle they have on it is the id Temporal's own output prints.
LIVE_EPIC_VERBS = (
    "status",
    # 092-US3: reads the epic's verification rows rather than the workflow, so
    # it still answers once the execution has aged out — but the handle an
    # operator holds is the same epic id, which is what this family is about.
    "attempts",
    # 127-US3: joins the same verification rows with the live `epic_status`
    # query to explain a node's death. The epic id is the handle the operator
    # arrives holding, which is what this family is about.
    "why",
    "pause",
    "resume",
    "kill",
    "answer",
    "resolve",
    "reset",
    "complete-node-externally",
)

#: The declared exclusions, each with the reason it is one.  A subcommand that
#: is in neither list fails the test below; a new verb must be classified on
#: purpose, which is what keeps the family in line after this story lands.
DECLARED_EXCLUSIONS = {
    "start": (
        "start creates the epic. There is no epic id to key it by until it has "
        "run, and the compiled artifact is the thing that declares what to "
        "start — the id is derived from it, not the other way round (FR-010)."
    ),
    "salvage": (
        "salvage keeps its graph path deliberately "
        "(factory/cli/nouns/build.py, salvage_command's docstring): it needs no "
        "Temporal at all, because the moment it is most needed is the moment a "
        "terminated epic's workflow has already aged out. Keying it by epic id "
        "would not change that, and the graph is the only artifact that survives."
    ),
    "external-completion-count": (
        "external-completion-count takes no positional at all. It reports a "
        "store-wide count across every spec, so there is no single epic to name."
    ),
    "ship": (
        "ship creates the epic from a spec directory. The epic id does not exist "
        "until after validate, derive and confirmation; the spec directory is the "
        "only handle the operator has (106-US4)."
    ),
    "credential-status": (
        "credential-status reports a worker-host fact (the subscription credential "
        "runway). It is not keyed by an epic because it answers before any epic "
        "starts; it needs no Temporal read."
    ),
}


def test_every_live_epic_verb_takes_epic_id_as_its_first_positional() -> None:
    """FR-010: one argument convention across the family, and it stays that way."""
    subcommands = _build_subcommands()

    unclassified = set(subcommands) - set(LIVE_EPIC_VERBS) - set(DECLARED_EXCLUSIONS)
    assert not unclassified, (
        f"new `build` subcommand(s) {sorted(unclassified)} are in neither the "
        "live-epic family nor the declared exclusions. Add each to "
        "LIVE_EPIC_VERBS (and give it an `epic_id` first positional) or to "
        "DECLARED_EXCLUSIONS with the reason it is one."
    )
    missing = (set(LIVE_EPIC_VERBS) | set(DECLARED_EXCLUSIONS)) - set(subcommands)
    assert not missing, f"these subcommands no longer exist: {sorted(missing)}"

    for verb in LIVE_EPIC_VERBS:
        assert _first_positional(subcommands[verb]) == "epic_id", (
            f"`ergane build {verb}` must take the epic id as its first "
            f"positional; it takes {_first_positional(subcommands[verb])!r}"
        )

    # The exclusions are excluded for a stated reason, not by omission.
    for verb, reason in DECLARED_EXCLUSIONS.items():
        assert reason.strip(), f"{verb} is excluded without a reason"
    assert _first_positional(subcommands["start"]) == "graph"
    assert _first_positional(subcommands["salvage"]) == "graph"
    assert _first_positional(subcommands["external-completion-count"]) is None


# --- T022 (US3-S4) -------------------------------------------------------------


def test_a_supplied_graph_path_is_still_accepted(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S4: the old argument form keeps working, unchanged in meaning."""
    target = _plant(target_repo, tmp_path, monkeypatch)
    client = _patch_client(monkeypatch, AbsentFromTemporal())

    result = run("build", "reset", str(target.graph_path))

    _assert_reset(target, result)
    assert client.dialled == [workflow_id(EPIC_ID)]


def test_a_missing_graph_path_is_never_reinterpreted_as_an_epic_id(
    run: Callable[..., Run],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trap 8: a path that does not exist fails as a path, naming the path.

    The one unacceptable outcome for this argument change is a mistyped graph
    path being read as an epic id and refused against a specs root the operator
    never mentioned. The refusal must name what was actually typed.
    """
    _forbid_temporal(monkeypatch)
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    missing = tmp_path / "nowhere" / ARTIFACT_NAME

    result = run(
        "build", "reset", str(missing), "--specs-root", str(specs_root)
    )

    assert result.code != 0
    assert str(missing) in result.stderr
    assert str(specs_root) not in result.stderr


# --- T022b (US3-S5) ------------------------------------------------------------


@pytest.mark.parametrize("form", ["epic-id", "graph-path"])
def test_reset_archives_survivors_when_the_workflow_is_gone_from_temporal(
    form: str,
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S5: NOT_FOUND proceeds, in both argument forms.

    `_reset_epic` treats an absent workflow as normal rather than as an error,
    and `tests/test_ergane_build.py` has pinned that since 047. The argument
    change must not disturb it, so the guarantee is re-asserted here through
    the new form as well as the old one.
    """
    target = _plant(target_repo, tmp_path, monkeypatch)
    _patch_client(monkeypatch, AbsentFromTemporal())
    argv = (
        (EPIC_ID, "--specs-root", str(target.specs_root))
        if form == "epic-id"
        else (str(target.graph_path),)
    )

    result = run("build", "reset", *argv)

    assert result.code == 0, result.stderr
    assert _archive_refs(target.repo, EPIC_ID)
    for node_id in NODE_IDS:
        assert not target.worktrees[node_id].exists()

    # Idempotent, as before: a second run finds nothing to do and still exits 0.
    again = run("build", "reset", *argv)
    assert again.code == 0, again.stderr
    for node_id in NODE_IDS:
        assert f"{node_id}: nothing to do" in again.stdout
