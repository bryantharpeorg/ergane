"""US3 of epic 127: one verb assembles the causal chain behind a dead node.

`ergane build why <epic-id> [node-id]` joins the two sources an operator
otherwise walks by hand:

- the **verification store** (`node_history`), which holds the verdicts, the
  gate results and the judge's feedback, and outlives the workflow — the same
  source `attempts_command` reads, for the same reason its docstring gives;
- the **`epic_status` query**, which holds the ending — the terminal reason,
  the landing's queue outcomes and its rejection cause — and dies with the
  execution.

The transcript directory is *composed*, never opened: the walk is the work this
verb exists to remove (plan trap 11). The gate output is clipped through the
escalation pages' own clipper, promoted to a public name for exactly this
import (FR-009), because `GateResult.output_tail` is up to 32 KiB and the
story's whole diff budget is 64 KiB (plan trap 15).

US3 stops at the present execution: on `NOT_FOUND` it refuses in the shape
`_query_status` refuses in, and the two-way "aged out vs. no such epic"
discriminator is US5's, not this story's (plan trap 16).

The tests are written first and must fail against the unimplemented verb
(T018–T020).
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest
from temporalio.service import RPCError, RPCStatusCode

import factory.cli.nouns as nouns
from factory.cli.main import main as ergane_main
from factory.env import (
    ERGANE_ROOT_ENV,
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_ROOT_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
)
from factory.notify.messages import EVIDENCE_TAIL_LINES
from factory.verify.models import (
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeVerdict,
    OverallVerdict,
    VerificationForm,
    compose_result,
)
from factory.verify.store import connect, upsert_result

EPIC_ID = "127-a-killed-node-says-why-it-died"
NODE_ID = "us3"
DEAD_NODE = "us1"
PASSED_NODE = "us2"


# --- harness ------------------------------------------------------------------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def invoke(*argv: str) -> Run:
    """Drive the real CLI entry point, capturing what an operator would see."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = StringIO(), StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = ergane_main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


class _FakeWorkflowHandle:
    """A handle that answers `epic_status` from a fixed document.

    The same shape of fake `test_ergane_build_status_refusal.py` uses, because
    the verb dials the same query the status verb does.
    """

    def __init__(self, client: "_FakeWhyClient", workflow_id: str) -> None:
        self._client = client
        self.id = workflow_id
        self.queried: list[str] = []

    async def describe(self) -> Any:
        from types import SimpleNamespace

        if self.id not in self._client.workflows:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        return SimpleNamespace(
            id=self.id,
            status=SimpleNamespace(name="RUNNING"),
            raw_description=SimpleNamespace(pending_activities=[]),
        )

    async def query(self, name: str, *args: Any, **kwargs: Any) -> Any:
        self.queried.append(name)
        if self.id not in self._client.workflows:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        document = self._client.workflows[self.id]
        if isinstance(document, BaseException):
            raise document
        return document


class _FakeWhyClient:
    def __init__(self, *, workflows: dict[str, Any] | None = None) -> None:
        self.workflows = dict(workflows or {})

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> Any:
        return _FakeWorkflowHandle(self, workflow_id)


def patch_client(
    monkeypatch: pytest.MonkeyPatch, client: _FakeWhyClient
) -> _FakeWhyClient:
    """Patch the package-level seam `factory.cli.main`'s reload cannot lose."""

    async def _open_client() -> _FakeWhyClient:
        return client

    monkeypatch.setattr(nouns, "_open_client", _open_client)
    return client


def status_document(
    *,
    terminal_reason: str | None,
    landing_history: tuple[dict[str, Any], ...] = (),
    rejection_cause: str | None = None,
    nodes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A minimal `epic_status` answer, in the query's own shape.

    Same keys the real query's `NodeStatus` serialises; only the ones this
    verb reads are carried meaningfully.
    """
    if nodes is None:
        nodes = {
            NODE_ID: {
                "state": "KILLED",
                "attempt": 3,
                "branch": f"factory/{EPIC_ID}/{NODE_ID}",
                "verified": False,
                "landing_state": None,
                "landing_history": list(landing_history),
                "recovery_cycles": 0,
                "terminal_reason": terminal_reason,
                "rejection_cause": rejection_cause,
                "housekeeping_report": None,
            }
        }
    return {"epic_state": "RUNNING", "nodes": nodes}


def store_result(
    *,
    node_id: str = NODE_ID,
    attempt: int = 1,
    verdict: OverallVerdict = OverallVerdict.FAIL,
    gates: list[GateResult] | None = None,
    judge: JudgeVerdict | None = None,
    dispatch: str = "run-abc",
) -> Any:
    """The smallest complete evidence bundle the verb is meant to read."""
    if gates is None:
        gates = [
            GateResult(
                name="test",
                command="uv run pytest -q",
                status=GateStatus.FAIL,
                exit_code=1,
                duration_s=2.0,
                output_tail="E   assert 1 == 2\n1 failed in 0.01s\n",
            )
        ]
    return compose_result(
        epic_id=EPIC_ID,
        node_id=node_id,
        attempt=attempt,
        form=VerificationForm.PHASE,
        gate_results=gates,
        output_check=replace(_passing_check(), passed=True),
        judge=judge,
        criteria_sha256="a" * 64,
        spec_ref=f"specs/{EPIC_ID}/spec.md",
        started_at="2026-09-06T10:00:00Z",
        finished_at="2026-09-06T10:03:00Z",
        dispatch=dispatch,
    )


def _passing_check() -> Any:
    from factory.verify.models import OutputCheck
    from factory.config import WriteScope

    return OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )


@pytest.fixture
def seeded_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A store with one failing attempt and one passing one, in the env.

    Both env names are set, the way every reader of this store does it, so the
    verb resolves the same path the test seeded.
    """
    path = tmp_path / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(path))

    conn = connect(path)
    upsert_result(conn, store_result(node_id=DEAD_NODE, attempt=1))
    upsert_result(
        conn,
        store_result(
            node_id=PASSED_NODE,
            attempt=1,
            verdict=OverallVerdict.PASS,
            gates=[
                GateResult(
                    name="test",
                    command="uv run pytest -q",
                    status=GateStatus.PASS,
                    exit_code=0,
                    duration_s=1.0,
                    output_tail="3 passed in 0.01s\n",
                )
            ],
        ),
    )
    conn.close()
    return path


@pytest.fixture
def factory_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The factory root the transcript path must resolve against (trap 11)."""
    root = tmp_path / ".factory"
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(root))
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)
    return root


def why_document(**kwargs: Any) -> dict[str, Any]:
    """The query document the failing-node scenario dials against."""
    return status_document(
        terminal_reason=kwargs.get(
            "terminal_reason",
            "push to origin/factory/127-a-killed-node-says-why-it-died/us1 refused: "
            "non-fast-forward",
        ),
        landing_history=kwargs.get(
            "landing_history",
            (
                {"at": "2026-09-06T10:05:00Z", "outcome": "CHECKS_FAILED"},
                {"at": "2026-09-06T10:40:00Z", "outcome": "CONFLICT"},
            ),
        ),
        rejection_cause=kwargs.get("rejection_cause", "NODE_CODE"),
        nodes=kwargs.get(
            "nodes",
            {
                DEAD_NODE: {
                    "state": "KILLED",
                    "attempt": 1,
                    "branch": f"factory/{EPIC_ID}/{DEAD_NODE}",
                    "verified": False,
                    "landing_state": None,
                    "landing_history": [
                        {"at": "2026-09-06T10:05:00Z", "outcome": "CHECKS_FAILED"},
                        {"at": "2026-09-06T10:40:00Z", "outcome": "CONFLICT"},
                    ],
                    "recovery_cycles": 0,
                    "terminal_reason": (
                        "push to origin/factory/127-a-killed-node-says-why-it-died/us1 "
                        "refused: non-fast-forward"
                    ),
                    "rejection_cause": "NODE_CODE",
                    "housekeeping_report": None,
                }
            },
        ),
    )


# --- T018 / US3-S1: the chain of a failed node --------------------------------


def test_a_failed_node_gets_its_whole_chain(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S1 / FR-009. One command names the verdict, the gate, the judge, the
    queue, the transcripts and the ending."""
    client = patch_client(
        monkeypatch, _FakeWhyClient(workflows={f"epic-{EPIC_ID}": why_document()})
    )

    run = invoke("build", "why", EPIC_ID, DEAD_NODE)

    assert run.code == 0, run.stderr
    out = run.stdout

    # The last verdict, from the store.
    assert OverallVerdict.FAIL.value in out
    # The failing gate, by name.
    assert "test" in out
    # Its output tail, from the store.
    assert "E   assert 1 == 2" in out
    # The judge feedback where one exists — a gate-failed attempt has none, so
    # the judge half is exercised on its own in the next test.
    # The queue outcomes the landing recorded, from the query.
    assert "CHECKS_FAILED" in out
    assert "CONFLICT" in out
    # The rejection cause.
    assert "NODE_CODE" in out
    # The terminal reason, from the query.
    assert "non-fast-forward" in out
    # The transcript directory of the latest attempt, composed with the
    # declared factory root (trap 11) — and never opened.
    assert "attempt-1" in out
    assert str(factory_root / "transcripts" / EPIC_ID / DEAD_NODE) in out


def test_the_judge_feedback_prints_where_one_exists(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009: a verdict with a judge behind it names what the judge said."""
    patch_client(
        monkeypatch, _FakeWhyClient(workflows={f"epic-{EPIC_ID}": why_document()})
    )
    conn = sqlite3.connect(seeded_store)
    # Overwrite the dead node's row with one carrying a judge verdict: the
    # upsert key is (epic, node, attempt, form), so this replaces attempt 1.
    upsert_result(
        conn,
        store_result(
            node_id=DEAD_NODE,
            attempt=1,
            judge=JudgeVerdict(
                outcome=JudgeOutcome.RETRY,
                findings=[],
                feedback="US3-S1 scenario 2: the scenario was never exercised; "
                "the diff deletes the check.",
                judge_attempt=1,
                truncated_input=False,
                model_alias="judge-alias",
            ),
        ),
    )
    conn.close()

    run = invoke("build", "why", EPIC_ID, DEAD_NODE)

    assert run.code == 0, run.stderr
    assert "the diff deletes the check" in run.stdout
    assert JudgeOutcome.RETRY.value in run.stdout


def test_the_gate_output_is_clipped_not_printed_whole(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009 / trap 15: a long `output_tail` prints as a bounded tail.

    `GateResult.output_tail` is up to 32 KiB; the verb keeps the last
    `EVIDENCE_TAIL_LINES` lines and names what it dropped, the way the
    escalation pages already clip. Printing the field whole would make one
    noisy gate unreadable and spend half this story's diff bound in one print.
    """
    patch_client(
        monkeypatch, _FakeWhyClient(workflows={f"epic-{EPIC_ID}": why_document()})
    )
    noise_lines = 200
    noisy = (
        "\n".join(f"noise line {n}" for n in range(noise_lines)) + "\nTHE ANSWER LINE\n"
    )
    conn = sqlite3.connect(seeded_store)
    upsert_result(
        conn,
        store_result(
            node_id=DEAD_NODE,
            attempt=1,
            gates=[
                GateResult(
                    name="test",
                    command="uv run pytest -q",
                    status=GateStatus.FAIL,
                    exit_code=1,
                    duration_s=2.0,
                    output_tail=noisy,
                )
            ],
        ),
    )
    conn.close()

    run = invoke("build", "why", EPIC_ID, DEAD_NODE)

    assert run.code == 0, run.stderr
    out = run.stdout
    # The tail is kept.
    assert "THE ANSWER LINE" in out
    # The head was dropped, and the drop is named with its count.
    assert "noise line 0" not in out
    dropped = noise_lines + 1 - EVIDENCE_TAIL_LINES
    assert str(dropped) in out
    assert "truncated" in out
    # Kept lines are the LAST ones, not the first.
    assert f"noise line {noise_lines - 1}" in out


def test_the_transcript_directory_is_composed_and_never_opened(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009 / trap 11: print the path, do not walk it.

    The verb's whole point is to end the filesystem walk, so it must not
    perform one. The transcript directory of the latest attempt is composed
    from the declared factory root and printed — nothing under it is read.
    """
    patch_client(
        monkeypatch, _FakeWhyClient(workflows={f"epic-{EPIC_ID}": why_document()})
    )
    # A second attempt in the store: the transcript printed is the LATEST's.
    conn = sqlite3.connect(seeded_store)
    upsert_result(conn, store_result(node_id=DEAD_NODE, attempt=2))
    conn.close()

    # No transcript directory exists at all — the verb must still answer.
    run = invoke("build", "why", EPIC_ID, DEAD_NODE)

    assert run.code == 0, run.stderr
    expected = factory_root / "transcripts" / EPIC_ID / DEAD_NODE / "attempt-2"
    assert str(expected) in run.stdout
    # The latest attempt's transcript is the one printed — attempt-1 is not.
    assert "attempt-1" not in run.stdout


def test_the_transcript_path_resolves_the_declared_root_not_the_cwd(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Trap 11: the path is composed from `resolve_env_path`, never the cwd.

    A bare relative default prints a path that is right only from the worker's
    cwd; the operator will `cd` to it. The declared root wins.
    """
    monkeypatch.chdir(tmp_path)
    patch_client(
        monkeypatch, _FakeWhyClient(workflows={f"epic-{EPIC_ID}": why_document()})
    )

    run = invoke("build", "why", EPIC_ID, DEAD_NODE)

    assert run.code == 0, run.stderr
    assert str(factory_root / "transcripts" / EPIC_ID / DEAD_NODE / "attempt-1") in (
        run.stdout
    )
    # And the cwd-relative spelling is not what got printed.
    assert f"./transcripts/{EPIC_ID}" not in run.stdout


# --- T019 / US3-S2: every terminal node when no node is named -----------------


def test_without_a_node_argument_every_terminal_node_is_reported(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S2. Same shape, one report per terminal node."""
    patch_client(
        monkeypatch,
        _FakeWhyClient(
            workflows={
                f"epic-{EPIC_ID}": status_document(
                    terminal_reason="push refused: non-fast-forward",
                    nodes={
                        DEAD_NODE: {
                            "state": "KILLED",
                            "attempt": 1,
                            "branch": f"factory/{EPIC_ID}/{DEAD_NODE}",
                            "verified": False,
                            "landing_state": None,
                            "landing_history": [],
                            "recovery_cycles": 0,
                            "terminal_reason": "push refused: non-fast-forward",
                            "rejection_cause": None,
                        },
                        PASSED_NODE: {
                            "state": "MERGED",
                            "attempt": 1,
                            "branch": f"factory/{EPIC_ID}/{PASSED_NODE}",
                            "verified": True,
                            "landing_state": "MERGED",
                            "landing_history": [
                                {"at": "2026-09-06T11:00:00Z", "outcome": "MERGED"}
                            ],
                            "recovery_cycles": 0,
                            "terminal_reason": None,
                            "rejection_cause": None,
                        },
                    }
                )
            }
        ),
    )

    run = invoke("build", "why", EPIC_ID)

    assert run.code == 0, run.stderr
    out = run.stdout
    # The dead node's chain is there.
    assert "non-fast-forward" in out
    assert "E   assert 1 == 2" in out
    # And so is the passed node's own account (US3-S3's answer, in place).
    assert PASSED_NODE in out
    assert DEAD_NODE in out


# --- T020 / US3-S3: a passed node has nothing to explain ----------------------


def test_a_passed_node_says_it_has_no_failure_to_explain(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S3, the control. No empty chain, no implied failure."""
    patch_client(
        monkeypatch,
        _FakeWhyClient(
            workflows={
                f"epic-{EPIC_ID}": status_document(
                    terminal_reason=None,
                    nodes={
                        PASSED_NODE: {
                            "state": "MERGED",
                            "attempt": 1,
                            "branch": f"factory/{EPIC_ID}/{PASSED_NODE}",
                            "verified": True,
                            "landing_state": "MERGED",
                            "landing_history": [
                                {"at": "2026-09-06T11:00:00Z", "outcome": "MERGED"}
                            ],
                            "recovery_cycles": 0,
                            "terminal_reason": None,
                            "rejection_cause": None,
                        }
                    },
                )
            }
        ),
    )

    run = invoke("build", "why", EPIC_ID, PASSED_NODE)

    assert run.code == 0, run.stderr
    out = run.stdout
    assert "no failure" in out
    # No chain is printed for it: no gate tail, no queue outcomes.
    assert "3 passed in 0.01s" not in out
    assert "CHECKS_FAILED" not in out
    assert "CONFLICT" not in out


# --- the seam the verb dials, and what it refuses -----------------------------


def test_a_node_missing_from_the_query_document_is_reported(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A node id the epic does not hold is an operator-fixable argument error."""
    patch_client(
        monkeypatch, _FakeWhyClient(workflows={f"epic-{EPIC_ID}": why_document()})
    )

    run = invoke("build", "why", EPIC_ID, "us-nine")

    assert run.code != 0
    assert "us-nine" in run.stderr


def test_not_found_refuses_in_the_status_verb_shape(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3 stops at the present execution (trap 16): `NOT_FOUND` refuses,
    in the shape `_query_status` refuses in — one line, no traceback."""
    patch_client(monkeypatch, _FakeWhyClient(workflows={}))

    run = invoke("build", "why", EPIC_ID, DEAD_NODE)

    assert run.code != 0
    assert "no epic" in run.stderr
    assert f"epic-{EPIC_ID}" in run.stderr
    assert "Traceback" not in run.stderr


def test_a_refused_query_degrades_to_the_store_half(
    seeded_store: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A query the workflow will not answer is a degraded reading, not a
    failed command: the store half of the chain is still real, and the ending
    is said to be unavailable rather than silently missing."""
    from temporalio.client import WorkflowQueryFailedError

    patch_client(
        monkeypatch,
        _FakeWhyClient(
            workflows={f"epic-{EPIC_ID}": WorkflowQueryFailedError("refused")}
        ),
    )

    run = invoke("build", "why", EPIC_ID, DEAD_NODE)

    assert run.code == 0, run.stderr
    out = run.stdout
    assert "E   assert 1 == 2" in out, "the store half survives the refusal"
    assert "ending: unavailable" in out
    assert "epic_status" in out