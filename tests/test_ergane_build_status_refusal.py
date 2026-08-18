"""053 US1: a refused `epic_status` query degrades `ergane build status` instead of killing it."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.client import WorkflowQueryFailedError
from temporalio.service import RPCError, RPCStatusCode

import factory.cli.nouns as nouns
import factory.cli.nouns.build as build_module
from factory.cli.main import main as ergane_main

EPIC_ID = "valid_epic"
WORKFLOW_ID = f"epic-{EPIC_ID}"


class _Run:
    def __init__(self, code: int, stdout: str, stderr: str) -> None:
        self.code = code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(*argv: str) -> _Run:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = StringIO(), StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = ergane_main(list(argv))
        except SystemExit as exit_request:
            code = exit_request.code
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return _Run(0 if code is None else int(code), buf_out.getvalue(), buf_err.getvalue())


class _FakeWorkflow:
    def __init__(self, document: Any, status_name: str = "RUNNING") -> None:
        self.document = document
        self.status_name = status_name


class _FakeWorkflowHandle:
    def __init__(self, client: "_FakeTemporalClient", workflow_id: str) -> None:
        self._client = client
        self.id = workflow_id

    async def describe(self) -> Any:
        from types import SimpleNamespace

        if self.id not in self._client.workflows:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        return SimpleNamespace(
            id=self.id,
            status=SimpleNamespace(name=self._client.workflows[self.id].status_name),
            raw_description=SimpleNamespace(
                pending_activities=[],
            ),
        )

    async def query(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if self.id not in self._client.workflows:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        document = self._client.workflows[self.id].document
        if isinstance(document, BaseException):
            raise document
        return document

    async def signal(self, name: str, *args: Any, **kwargs: Any) -> None:
        if self.id not in self._client.workflows:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        document = self._client.workflows[self.id].document
        if isinstance(document, BaseException):
            raise document


class _FakeTemporalClient:
    def __init__(self, *, workflows: dict[str, _FakeWorkflow] | None = None) -> None:
        self.workflows = dict(workflows or {})

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> _FakeWorkflowHandle:
        return _FakeWorkflowHandle(self, workflow_id)


@pytest.fixture
def fake_status_client(monkeypatch: pytest.MonkeyPatch) -> Callable[..., _FakeTemporalClient]:
    def setup(**kwargs: Any) -> _FakeTemporalClient:
        client = _FakeTemporalClient(**kwargs)

        async def _open_client() -> _FakeTemporalClient:
            return client

        monkeypatch.setattr(nouns, "_open_client", _open_client)
        return client

    return setup


REFUSAL_MESSAGE = "provenance field is not present on this history"


def test_status_degrades_when_epic_status_query_is_refused(
    fake_status_client: Callable[..., _FakeTemporalClient],
) -> None:
    """US1-S1 / FR-001 / FR-002: WorkflowQueryFailedError becomes exit 0 with the refusal named."""
    fake_status_client(
        workflows={WORKFLOW_ID: _FakeWorkflow(WorkflowQueryFailedError(REFUSAL_MESSAGE))}
    )

    result = _invoke("build", "status", EPIC_ID)

    assert result.code == 0, result.stderr
    assert "unavailable" in result.stdout.lower()
    assert REFUSAL_MESSAGE in result.stdout


def test_status_json_degrades_when_query_is_refused(
    fake_status_client: Callable[..., _FakeTemporalClient],
) -> None:
    """US1-S1 / FR-002: JSON still reports the refusal in place."""
    fake_status_client(
        workflows={WORKFLOW_ID: _FakeWorkflow(WorkflowQueryFailedError(REFUSAL_MESSAGE))}
    )

    result = _invoke("build", "status", EPIC_ID, "--json")

    assert result.code == 0, result.stderr
    document = result.json
    assert document.get("epic_state") is None or document.get("epic_state") == ""
    assert "refusal" in document
    assert REFUSAL_MESSAGE in document["refusal"]


def test_status_rpcerror_not_found_path_is_unchanged(
    fake_status_client: Callable[..., _FakeTemporalClient],
) -> None:
    """US1-S2 / FR-006: RPCError with NOT_FOUND reports 'no epic is running here'."""
    fake_status_client(workflows={})

    result = _invoke("build", "status", EPIC_ID)

    assert result.code == 1
    assert "no epic 'valid_epic' is running here" in result.stderr
    assert "looked for workflow id epic-valid_epic" in result.stderr


def test_status_rpcerror_other_status_is_exit_3(
    fake_status_client: Callable[..., _FakeTemporalClient],
) -> None:
    """US1-S2 / FR-006: non-NOT_FOUND RPCError stays a transport failure."""
    fake_status_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(
                RPCError("some upstream failure", RPCStatusCode.UNAVAILABLE, b""),
                status_name="RUNNING",
            )
        }
    )

    result = _invoke("build", "status", EPIC_ID)

    assert result.code == 3, result.stderr
    assert "cannot read epic 'valid_epic'" in result.stderr
    assert "some upstream failure" in result.stderr


def test_kill_still_exits_non_zero_when_signal_call_fails(
    fake_status_client: Callable[..., _FakeTemporalClient],
) -> None:
    """US1-S3 / FR-004: a signal verb that fails does not learn to shrug."""
    fake_status_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(
                RPCError("service unavailable", RPCStatusCode.UNAVAILABLE, b""),
                status_name="RUNNING",
            )
        }
    )

    result = _invoke("build", "kill", EPIC_ID, "--yes")

    assert result.code != 0, result.stdout
    assert "cannot signal" in result.stderr.lower()


def test_answer_still_exits_non_zero_when_signal_call_fails(
    fake_status_client: Callable[..., _FakeTemporalClient],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-S3 / FR-004: answer's signal path still exits non-zero on failure."""
    from factory.verify.models import QuestionRecord
    from factory.verify.store import connect as verify_connect, insert_question

    db_path = tmp_path / "verify.db"
    monkeypatch.setenv("ERGANE_VERIFICATION_DB_PATH", str(db_path))
    monkeypatch.delenv("FACTORY_VERIFICATION_DB_PATH", raising=False)
    conn = verify_connect(db_path)
    try:
        insert_question(
            conn,
            QuestionRecord(
                question_id="q053",
                workflow_id=WORKFLOW_ID,
                epic_id=EPIC_ID,
                node_id="us2",
                attempt=1,
                question_text="Which id form?",
                sent_at="2026-08-05T09:30:00Z",
                expires_at="2026-08-05T17:30:00Z",
                resolution=None,
                answer_text=None,
                resolved_at=None,
            ),
        )
    finally:
        conn.close()

    fake_status_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(
                RPCError("service unavailable", RPCStatusCode.UNAVAILABLE, b""),
                status_name="RUNNING",
            )
        }
    )

    result = _invoke("build", "answer", EPIC_ID, "q053", "text")

    assert result.code != 0, result.stdout
    assert "cannot signal" in result.stderr.lower()


def test_no_temporal_call_site_in_build_py_uses_a_blanket_except() -> None:
    """US1-S4 / FR-005: no `except Exception` guards a Temporal call in build.py.

    Derived from the source so the next Temporal call added to the module cannot
    be guarded wrongly in silence. A site that awaits something (and therefore
    can see a Temporal failure) must not catch `Exception`, `BaseException`, or
    a bare `except`.
    """
    import ast

    source = Path(build_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    def awaits_or_async_iterates(node: ast.AST) -> bool:
        return any(
            isinstance(sub, (ast.Await, ast.AsyncFor)) for sub in ast.walk(node)
        )

    def caught_names(handler: ast.ExceptHandler) -> tuple[str, ...]:
        if handler.type is None:
            return ("<bare except>",)
        caught = (
            handler.type.elts
            if isinstance(handler.type, ast.Tuple)
            else [handler.type]
        )
        return tuple(ast.unparse(c) for c in caught)

    offenders: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not awaits_or_async_iterates(node):
            continue
        for try_node in ast.walk(node):
            if not isinstance(try_node, ast.Try):
                continue
            for handler in try_node.handlers:
                names = caught_names(handler)
                if any(
                    name in ("Exception", "BaseException", "<bare except>")
                    for name in names
                ):
                    offenders.append((node.name, names))

    # `_live_spend` has two `except Exception` clauses, but neither guards a
    # Temporal call: one catches `client.data_converter` (a local attribute
    # access), the other catches `converter.decode` of a heartbeat payload.
    # They are allowed because they do not swallow Temporal failures.
    temporal_offenders = [
        (name, names)
        for name, names in offenders
        if name != "_live_spend"
    ]
    assert temporal_offenders == []
