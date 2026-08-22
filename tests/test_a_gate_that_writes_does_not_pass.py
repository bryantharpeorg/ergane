"""A gate may not change what it measures (084 US1).

The gates run in the node's worktree and the judge's patch is assembled from
that same worktree afterwards (`factory/workgraph/workflow.py:2298-2313`), so a
gate that writes into it has edited the evidence it was scored on. This module
holds the refusal to eight properties, and three of them are controls:

- **The measurement is content-based, not status-based.** A gate that rewrites a
  file the agent had already modified leaves `git status --porcelain` reporting
  a byte-identical line on either side of the write. The test captures both
  sides and asserts they are equal, so the paste is the evidence that porcelain
  could not have found this.
- **Ignored paths are not writes.** This repository's own gate is
  `uv run pytest -q`, which writes `__pycache__/` and `.pytest_cache/` — both
  ignored, neither reaching the judge (`factory/workgraph/worktree.py:1006`). A
  check that counted them would fail every gate run Ergane has ever made,
  starting with the one verifying this story, so the control writes exactly
  those two paths into a fixture repo that ignores them and asserts PASS. It is
  a **fixture** gate and deliberately not a nested `uv run pytest -q`: a full
  suite inside a gate run inside this node's own gate run is the recursion
  behind `hardening/orphaned-test-servers-exhaust-host-memory`.
- **The check is at the seam, not in an executor.** `_run_gate_list` and
  `_run_gate_list_from_config` are near-identical twins and which one a repo
  takes is decided by whether its worktree carries a candidate parser, so a
  check in one is bypassable through the other; likewise a check inside
  `SubprocessGateExecutor` is bypassable by `BwrapGateExecutor`. Both runners
  and three executors are asserted, the third being a stub that is neither
  shipped class. The stub is not a test-only shape: production already runs a
  fourth, `_HeartbeatingExecutor`
  (`factory/activities/verify_activities.py:230-258`), which wraps the resolved
  backend and is what `run_gates` actually receives (`:278-279`) — a check
  living inside either shipped executor would be bypassed by the wrapper
  production uses.

Failing closed is the other half. An unreadable snapshot must never read as a
clean worktree, and `run_gates` must still return a list rather than raise: the
module's promise is one result per declared gate, and an exception costs the
attempt its evidence (`factory/verify/gates.py:1094-1098`).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Mapping

import pytest

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    PARSE_CLI_OK,
    load_factory_config,
)
from factory.verify.gates import (
    BWRAP_BACKEND_BINARY,
    BwrapGateExecutor,
    CandidateOutcome,
    ExecutionOutcome,
    GateInvocation,
    SubprocessGateExecutor,
    _run_gate_list,
    _run_gate_list_from_config,
    run_gates,
)
from factory.verify.models import GateResult, GateStatus, gates_passed
from factory.verify.store import _gate_from_dict, _gate_to_dict

#: The two directories this repository's own gate leaves behind, named here
#: because the control is only a control if it writes what the real gate writes.
IGNORED_BY_THE_REAL_GATE = ("__pycache__/", ".pytest_cache/")


def _bwrap_available() -> bool:
    """Copied verbatim from `tests/test_us4_boundary.py:165`.

    The node agent that wrote this file is itself sandboxed and may have no
    nested bubblewrap, so the `BwrapGateExecutor` case is guarded the way every
    other bwrap test in this repository is guarded rather than left to fail on
    hosts that cannot run it.
    """
    return BWRAP_BACKEND_BINARY.is_file() and os.access(BWRAP_BACKEND_BINARY, os.X_OK)


# --- fixture target repos ----------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _node_worktree(tmp_path: Path, *, ignore: tuple[str, ...] = ()) -> Path:
    """A throwaway target repo with a node worktree attached, and the worktree.

    The topology the factory actually runs against: gates and diffs see a linked
    worktree whose `.git` is a file pointing back at the parent repo, never the
    repo's own checkout. It matters here beyond fidelity — `BwrapGateExecutor`
    binds the parent read-only and the worktree writable
    (`factory/verify/gates.py:628-642`), so a fixture that put `.git` *inside*
    the worktree would have the parent bind cover the leaf and every gate would
    fail on a read-only filesystem instead of writing anything.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "--quiet", "--initial-branch=main")
    _git(repo, "config", "user.email", "factory@example.invalid")
    _git(repo, "config", "user.name", "Ergane Tests")
    (repo / ".gitignore").write_text(
        "".join(f"{name}\n" for name in ignore), encoding="utf-8"
    )
    (repo / "src.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "base")

    worktree = tmp_path / "worktree"
    _git(repo, "worktree", "add", "--quiet", "-b", "node/work", str(worktree))
    return worktree


def _manifest(repo: Path, gates: Mapping[str, str]) -> Path:
    """Write a minimal v1 manifest declaring `gates`, in declaration order."""
    lines = ["version: 1", "runtime: bwrap", "gates:"]
    for name, command in gates.items():
        # Single-quoted YAML, so no gate command here may contain one: a
        # double-quoted scalar would eat the backslashes shell commands use.
        assert "'" not in command, command
        lines.append(f"  {name}: '{command}'")
    path = repo / MANIFEST_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class StubGateExecutor:
    """A `GateExecutor` that is neither shipped class (US1-S5).

    It runs no process at all: it performs the writes it was constructed with
    and reports the exit code it was told to. If the refusal survives this, the
    check cannot be living inside `SubprocessGateExecutor` or
    `BwrapGateExecutor` — it is at `backend.run(invocation)`, the one line both
    of them, and production's `_HeartbeatingExecutor`
    (`factory/activities/verify_activities.py:230-258`), pass through. It is
    also the only one of the three cases that runs on every host.
    """

    def __init__(self, writes: Mapping[str, str], *, exit_code: int = 0) -> None:
        self.writes = dict(writes)
        self.exit_code = exit_code
        self.invocations: list[GateInvocation] = []

    def run(self, invocation: GateInvocation) -> ExecutionOutcome:
        self.invocations.append(invocation)
        for relative, contents in self.writes.items():
            target = Path(invocation.cwd) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")
        return ExecutionOutcome(
            exit_code=self.exit_code,
            output=f"StubGateExecutor ran {invocation.name}",
            duration_s=0.01,
            timed_out=False,
        )


# --- T001 US1-S1: a gate that writes an unignored file is not PASS -----------


def test_a_gate_that_writes_an_unignored_file_is_not_reported_pass(
    tmp_path: Path,
) -> None:
    """US1-S1 / FR-001 / FR-004: exit 0 is not enough; the path is recorded."""
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    manifest = _manifest(worktree, {"test": "echo generated > generated.txt"})

    results = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )

    [result] = results
    assert result.name == "test"
    assert result.status is not GateStatus.PASS
    assert result.status is GateStatus.DIRTIED_WORKTREE
    # The command really did succeed; the refusal is about what it wrote.
    assert result.exit_code == 0
    assert result.worktree_writes == ("generated.txt",)
    # FR-004 reaches the decider that already owns the deterministic half, with
    # no edit to it: `gates_passed` refuses any status that is not PASS.
    assert not gates_passed(results)


# --- T002 US1-S2: the control ------------------------------------------------


def test_a_gate_that_writes_only_ignored_paths_still_passes(tmp_path: Path) -> None:
    """US1-S2 / FR-002: `__pycache__/` and `.pytest_cache/` are not writes.

    The control, and not a formality. These are the two directories
    `uv run pytest -q` leaves in every Ergane worktree, so a check that counted
    ignored paths would turn this repository's own gate red — including the run
    that verifies this story.
    """
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    manifest = _manifest(
        worktree,
        {
            "test": (
                "mkdir -p __pycache__ .pytest_cache "
                "&& echo compiled > __pycache__/src.cpython-312.pyc "
                "&& echo cache > .pytest_cache/CACHEDIR.TAG"
            )
        },
    )

    results = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )

    [result] = results
    assert result.status is GateStatus.PASS
    assert result.worktree_writes == ()
    assert gates_passed(results)
    # The paths were written. They are simply not counted, because a
    # `.gitignore`d path never reaches the judge's patch either.
    assert (worktree / "__pycache__" / "src.cpython-312.pyc").exists()
    assert (worktree / ".pytest_cache" / "CACHEDIR.TAG").exists()


# --- T003 US1-S3: the tracked rewrite porcelain cannot see -------------------


def test_a_gate_that_rewrites_a_modified_tracked_file_is_refused(
    tmp_path: Path,
) -> None:
    """US1-S3 / FR-002: content, not `git status --porcelain`.

    The agent modifies `src.py`; the gate then rewrites it. Porcelain reports
    ` M src.py` before the gate and ` M src.py` after it — the same bytes — so
    the equality asserted here is the proof that a status-based check would
    have called this clean.
    """
    worktree = _node_worktree(tmp_path)
    (worktree / "src.py").write_text("value = 2  # the agent's edit\n", encoding="utf-8")
    manifest = _manifest(worktree, {"test": "echo value = 3 > src.py"})

    porcelain_before = _git(worktree, "status", "--porcelain")
    results = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )
    porcelain_after = _git(worktree, "status", "--porcelain")

    assert " M src.py" in porcelain_before
    assert porcelain_before == porcelain_after
    # ...and the file really was rewritten between those two identical reads.
    assert (worktree / "src.py").read_text(encoding="utf-8") == "value = 3\n"

    [result] = results
    assert result.status is GateStatus.DIRTIED_WORKTREE
    assert result.worktree_writes == ("src.py",)


# --- T004 US1-S4: both gate-list runners -------------------------------------


@pytest.mark.parametrize("runner", ["_run_gate_list", "_run_gate_list_from_config"])
def test_both_gate_list_runners_refuse_a_gate_that_dirties(
    tmp_path: Path, runner: str
) -> None:
    """US1-S4 / FR-001: a check in one runner is bypassable through the other.

    Which one a repo takes is decided by whether its worktree carries a
    candidate parser (`factory/verify/gates.py:1135`): Ergane's own nodes take
    `_run_gate_list`, every other target repo takes
    `_run_gate_list_from_config`. The field report came from the second; this
    story's own verification runs on the first.
    """
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    manifest = _manifest(worktree, {"test": "echo generated > generated.txt"})
    executor = StubGateExecutor({"generated.txt": "generated\n"})

    if runner == "_run_gate_list":
        results = _run_gate_list(
            worktree,
            manifest,
            {"test": "echo generated > generated.txt"},
            {},
            executor=executor,
            timeout_overrides=None,
            concurrency_limiter=None,
        )
    else:
        results = _run_gate_list_from_config(
            worktree,
            load_factory_config(manifest),
            executor=executor,
            timeout_overrides=None,
            concurrency_limiter=None,
        )

    [result] = results
    assert result.status is GateStatus.DIRTIED_WORKTREE, runner
    assert result.worktree_writes == ("generated.txt",), runner


def test_run_gates_refuses_on_the_candidate_parser_path(tmp_path: Path) -> None:
    """US1-S4 / FR-001: the same refusal reached through `run_gates` itself.

    A worktree carrying `factory/verify/factory_yaml.py` is routed to
    `_run_gate_list` (`factory/verify/gates.py:1130-1146`) — the path Ergane's
    own nodes take, and the one the private-function test above cannot prove is
    wired up.
    """
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    candidate = worktree / "factory" / "verify" / "factory_yaml.py"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("# a worktree that carries its own parser\n", encoding="utf-8")
    command = "echo generated > generated.txt"
    manifest = _manifest(worktree, {"test": command})

    def accepting_candidate(worktree_path: Path, manifest_path: Path) -> CandidateOutcome:
        return CandidateOutcome(
            exit_code=PARSE_CLI_OK,
            stdout=json.dumps(
                {"kind": "accepted", "gates": {"test": command}, "timeouts": {}}
            ),
            stderr="",
        )

    results = run_gates(
        worktree,
        manifest_path=manifest,
        executor=SubprocessGateExecutor(),
        candidate_runner=accepting_candidate,
    )

    [result] = results
    assert result.status is GateStatus.DIRTIED_WORKTREE
    assert result.worktree_writes == ("generated.txt",)


# --- T005 US1-S5: every executor, including one that ships nowhere -----------


@pytest.mark.parametrize(
    "executor_name",
    ["SubprocessGateExecutor", "StubGateExecutor", "BwrapGateExecutor"],
)
def test_a_dirtying_gate_is_refused_under_every_executor(
    tmp_path: Path, executor_name: str
) -> None:
    """US1-S5 / FR-001: the check sits at `backend.run`, not inside a backend."""
    if executor_name == "BwrapGateExecutor" and not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")

    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    command = "echo generated > generated.txt"
    manifest = _manifest(worktree, {"test": command})
    executor = {
        "SubprocessGateExecutor": lambda: SubprocessGateExecutor(),
        "StubGateExecutor": lambda: StubGateExecutor({"generated.txt": "generated\n"}),
        "BwrapGateExecutor": lambda: BwrapGateExecutor(),
    }[executor_name]()

    results = run_gates(worktree, manifest_path=manifest, executor=executor)

    [result] = results
    assert result.status is GateStatus.DIRTIED_WORKTREE, (
        f"{executor_name}: {result.status} {result.output_tail}"
    )
    assert result.worktree_writes == ("generated.txt",), executor_name


# --- T006 US1-S6: failing and dirtying at once -------------------------------


def test_a_failing_gate_that_dirties_keeps_fail_and_does_not_stop_the_run(
    tmp_path: Path,
) -> None:
    """US1-S6 / FR-005: the exit code is the headline, the paths are the record.

    `test` is declared after `lint` and must still have run: the contract is one
    result per declared gate, and a failure never cancels the gates after it.
    `test`'s own record is empty because `lint`'s leavings were already there
    when `test` started — which is what attribution by gate means, and why N
    gates cost N+1 snapshots rather than 2N.
    """
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    manifest = _manifest(
        worktree,
        {"lint": "echo dirt > dirt.txt; exit 3", "test": "echo clean"},
    )

    results = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )

    assert [result.name for result in results] == ["lint", "test"]
    dirtying, following = results
    assert dirtying.status is GateStatus.FAIL
    assert dirtying.exit_code == 3
    assert dirtying.worktree_writes == ("dirt.txt",)
    assert following.status is GateStatus.PASS
    assert following.worktree_writes == ()


# --- T007 US1-S7: a snapshot git refuses -------------------------------------


def test_an_unreadable_snapshot_is_evidence_not_a_clean_worktree(
    tmp_path: Path,
) -> None:
    """US1-S7 / FR-006: fail closed, and still return a list.

    The worktree's `.git` is a gitfile pointing at a directory that does not
    exist, so every git invocation in it is refused. The result may not be PASS
    — an unreadable snapshot is not evidence of a clean tree — and `run_gates`
    may not raise, because an exception costs the attempt every gate's evidence.
    """
    worktree = tmp_path / "broken-repo"
    worktree.mkdir()
    (worktree / ".git").write_text(
        "gitdir: /nonexistent-ergane-084\n", encoding="utf-8"
    )
    manifest = _manifest(worktree, {"test": "echo hello"})

    results = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )

    assert isinstance(results, list)
    [result] = results
    assert result.status is not GateStatus.PASS
    assert not gates_passed(results)
    assert "fatal:" in result.output_tail
    assert "/nonexistent-ergane-084" in result.output_tail
    # The gate's own output survives beside git's complaint.
    assert "hello" in result.output_tail


# --- T008 US1-S8: the evidence codec -----------------------------------------


def test_worktree_writes_round_trips_through_the_evidence_store() -> None:
    """US1-S8 / FR-003: both codec halves, across a real JSON boundary."""
    gate = GateResult(
        name="test",
        command="uv run pytest -q",
        status=GateStatus.DIRTIED_WORKTREE,
        exit_code=0,
        duration_s=1.5,
        output_tail="",
        worktree_writes=("generated.txt", "pkg/module.py"),
    )

    stored = _gate_to_dict(gate)
    assert stored["worktree_writes"] == ["generated.txt", "pkg/module.py"]

    read_back = _gate_from_dict(json.loads(json.dumps(stored)))
    assert read_back.worktree_writes == ("generated.txt", "pkg/module.py")
    assert read_back == gate


def test_a_row_written_before_this_field_reads_back_as_nothing_recorded() -> None:
    """US1-S8 / FR-003: absence means "nothing recorded", never "unknown"."""
    legacy = {
        "name": "test",
        "command": "uv run pytest -q",
        "status": "PASS",
        "exit_code": 0,
        "duration_s": 1.5,
        "output_tail": "",
        "concurrent_gates": 0,
    }

    assert _gate_from_dict(legacy).worktree_writes == ()
