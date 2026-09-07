"""US5 of epic 127: the verb tells "no such epic" from "the execution aged out".

Both absences reach `build why` as `RPCStatusCode.NOT_FOUND` on the
`epic_status` query — the same error, collapsed into one refusal before this
story. The only fact that separates them is whether the verification store
holds rows for the epic, so the verb reads `epic_history` and branches on
rows-present, never on the status code (FR-010):

- **no rows** → refuse, naming the epic id, the workflow id it looked for and
  the store path it read, non-zero, no traceback (US5-S1, T028);
- **rows** → print the store half of the chain and report the ending as
  unavailable, rather than refusing the whole reading (US5-S2, T029).

`terminal_reason` is in no store — `grep -rn terminal_reason factory/verify/`
returns nothing — so the rows-present branch is the difference between a verb
that answers late and one that only answers early.

The tests are written first and must fail against the US3-shaped verb, which
refuses on `NOT_FOUND` regardless of rows (plan trap 10, trap 16).
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, NamedTuple

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
from factory.verify.models import (
    GateResult,
    GateStatus,
    OverallVerdict,
    VerificationForm,
    compose_result,
)
from factory.verify.store import connect, upsert_result

EPIC_ID = "127-a-killed-node-says-why-it-died"
DEAD_NODE = "us1"
OTHER_EPIC = "127-a-killed-node-says-why-it-died-sibling"


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
    """A handle whose `epic_status` query answers NOT_FOUND, always.

    The aged-out epic and the never-started one reach the verb identically —
    that identity is the story. The fake carries no workflows at all, so both
    scenarios below dial a workflow the server does not hold.
    """

    def __init__(self, client: "_FakeAbsentClient", workflow_id: str) -> None:
        self._client = client
        self.id = workflow_id

    async def query(self, name: str, *args: Any, **kwargs: Any) -> Any:
        raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")


class _FakeAbsentClient:
    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> Any:
        return _FakeWorkflowHandle(self, workflow_id)


def patch_client(
    monkeypatch: pytest.MonkeyPatch, client: _FakeAbsentClient
) -> _FakeAbsentClient:
    """Patch the package-level seam `factory.cli.main`'s reload cannot lose."""

    async def _open_client() -> _FakeAbsentClient:
        return client

    monkeypatch.setattr(nouns, "_open_client", _open_client)
    return client


def store_result(*, epic_id: str = EPIC_ID, node_id: str = DEAD_NODE) -> Any:
    """The smallest complete evidence bundle the verb is meant to read."""
    return compose_result(
        epic_id=epic_id,
        node_id=node_id,
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="uv run pytest -q",
                status=GateStatus.FAIL,
                exit_code=1,
                duration_s=2.0,
                output_tail="E   assert 1 == 2\n1 failed in 0.01s\n",
            )
        ],
        output_check=replace(_passing_check(), passed=True),
        judge=None,
        criteria_sha256="a" * 64,
        spec_ref=f"specs/{epic_id}/spec.md",
        started_at="2026-09-06T10:00:00Z",
        finished_at="2026-09-06T10:03:00Z",
        dispatch="run-abc",
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
def store_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A bootstrapped-but-unseeded store, resolved through the env names.

    Both env names are set, the way every reader of this store does it, so
    the verb resolves the same path the test seeded — and the refusal can be
    asserted to name exactly that path.
    """
    path = tmp_path / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(path))
    conn = connect(path)
    conn.close()
    return path


@pytest.fixture
def factory_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The factory root the transcript path must resolve against (trap 11)."""
    root = tmp_path / ".factory"
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(root))
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)
    return root


# --- T028 / US5-S1: NOT_FOUND with no rows refuses -----------------------------


def test_not_found_with_no_store_rows_refuses_naming_what_it_read(
    store_path: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US5-S1 / FR-010 / T028. The store, not the status code, is what tells
    this case from T029's: both are `NOT_FOUND`, so the verb reads
    `epic_history` and — finding no rows for *this* epic — refuses naming the
    epic id, the workflow id it looked for and the store path it read."""
    # Rows for a *different* epic prove the discriminator reads this epic's
    # rows, not the store's mere existence.
    conn = sqlite3.connect(store_path)
    upsert_result(conn, store_result(epic_id=OTHER_EPIC))
    conn.close()
    patch_client(monkeypatch, _FakeAbsentClient())

    run = invoke("build", "why", EPIC_ID)

    assert run.code != 0
    err = run.stderr
    # No traceback — the shape `_query_status` refuses in.
    assert "Traceback" not in err
    assert err.startswith("ergane: ")
    # The epic id, named.
    assert EPIC_ID in err
    # The workflow id it looked for.
    assert f"epic-{EPIC_ID}" in err
    # The store path it read.
    assert str(store_path) in err
    # And nothing of the other epic's chain leaks into the refusal.
    assert "E   assert 1 == 2" not in run.stdout


# --- T029 / US5-S2: NOT_FOUND with rows degrades, not refuses ------------------


def test_not_found_with_store_rows_prints_the_store_half(
    store_path: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US5-S2 / FR-010 / T029, the degradation control. The same `NOT_FOUND`
    as T028, but *with* rows: the verb prints the store half of the chain and
    says in place of the ending that the execution is gone, rather than
    refusing the whole reading."""
    conn = sqlite3.connect(store_path)
    upsert_result(conn, store_result())
    conn.close()
    patch_client(monkeypatch, _FakeAbsentClient())

    run = invoke("build", "why", EPIC_ID)

    assert run.code == 0, run.stderr
    out = run.stdout
    # The store half of the chain: the verdict and its failing gate's tail.
    assert OverallVerdict.FAIL.value in out
    assert "E   assert 1 == 2" in out
    # The transcript directory is composed from the declared root (trap 11),
    # part of the store half this branch keeps.
    assert (
        str(factory_root / "transcripts" / EPIC_ID / DEAD_NODE / "attempt-1") in out
    )
    # And the ending, in place of the terminal reason no store holds: named
    # as unavailable because the execution has aged out.
    assert "ending: unavailable" in out
    assert "aged out" in out
    # Not a refusal: the whole reading survived.
    assert "no epic" not in run.stderr
    assert "Traceback" not in run.stderr