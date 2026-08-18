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


# --- US3 T012–T015: worker revision skew is visible and survivable ---------------
# The read-path degraded in US1; this story makes the cause legible. A worker
# built from a different revision than the CLI's must say so. Matching revisions
# must say nothing. An absent revision must degrade to today's behaviour and be
# reported as unknown.


def _query_document(worker_revision: str | None) -> dict[str, Any]:
    """A minimal `epic_status` answer that records what the worker reported."""
    return {
        "epic_state": "RUNNING",
        "nodes": {
            "us3": {
                "state": "RUNNING",
                "attempt": 1,
                "branch": "factory/053-worker-skew/us3",
                "verified": False,
                "landing_state": None,
                "landing_history": [],
                "recovery_cycles": 0,
                "terminal_reason": None,
                "provenance": None,
            }
        },
        "worker_revision": worker_revision,
    }


CLI_REVISION = "b6233ee"
WORKER_REVISION_A = "e840123"
WORKER_REVISION_B = "7837b2e"


class _RevisionRecordingFakeWorkflowHandle(_FakeWorkflowHandle):
    """Records how many times the query answer was asked for, to prove once-ness."""

    def __init__(self, client: "_FakeTemporalClient", workflow_id: str) -> None:
        super().__init__(client, workflow_id)
        self.query_count = 0

    async def query(self, name: str, *args: Any, **kwargs: Any) -> Any:
        self.query_count += 1
        return await super().query(name, *args, **kwargs)


class _RevisionRecordingFakeClient(_FakeTemporalClient):
    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> _RevisionRecordingFakeWorkflowHandle:
        return _RevisionRecordingFakeWorkflowHandle(self, workflow_id)


@pytest.fixture
def fake_revision_client(monkeypatch: pytest.MonkeyPatch) -> Callable[..., _RevisionRecordingFakeClient]:
    def setup(**kwargs: Any) -> _RevisionRecordingFakeClient:
        client = _RevisionRecordingFakeClient(**kwargs)

        async def _open_client() -> _RevisionRecordingFakeClient:
            return client

        monkeypatch.setattr(nouns, "_open_client", _open_client)
        return client

    return setup


def _set_cli_revision(monkeypatch: pytest.MonkeyPatch, revision: str | None) -> None:
    """Patch the CLI's own revision lookup to a known value without touching disk.

    The noun module is reloaded by `ergane_main`, so the patch has to live on the
    package object that survives reloads rather than on the imported module.
    """
    monkeypatch.setattr(nouns, "_cli_revision_for_tests", lambda: revision)


def test_skew_is_visible_when_worker_revision_differs(
    fake_revision_client: Callable[..., _RevisionRecordingFakeClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T012 / US3-S1 / FR-009: differing revisions name both and say the worker is different."""
    _set_cli_revision(monkeypatch, CLI_REVISION)
    fake_revision_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(_query_document(worker_revision=WORKER_REVISION_A))
        }
    )

    result = _invoke("build", "status", EPIC_ID)

    assert result.code == 0, result.stderr
    assert CLI_REVISION in result.stderr
    assert WORKER_REVISION_A in result.stderr
    assert "worker is running different code" in result.stderr.lower()


def test_skew_is_visible_in_json_when_worker_revision_differs(
    fake_revision_client: Callable[..., _RevisionRecordingFakeClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T012 / US3-S1: the JSON view also carries the skew notice on the degraded path."""
    _set_cli_revision(monkeypatch, CLI_REVISION)
    fake_revision_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(_query_document(worker_revision=WORKER_REVISION_B))
        }
    )

    result = _invoke("build", "status", EPIC_ID, "--json")

    assert result.code == 0, result.stderr
    document = result.json
    assert document.get("worker_revision") == WORKER_REVISION_B
    notice = document.get("skew_notice")
    assert notice is not None
    assert CLI_REVISION in notice
    assert WORKER_REVISION_B in notice
    assert "worker is running different code" in notice.lower()


def test_skew_is_silent_when_revisions_match(
    fake_revision_client: Callable[..., _RevisionRecordingFakeClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T013 / US3-S2 / FR-009: matching revisions produce no skew notice anywhere."""
    _set_cli_revision(monkeypatch, CLI_REVISION)
    fake_revision_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(_query_document(worker_revision=CLI_REVISION))
        }
    )

    result = _invoke("build", "status", EPIC_ID)

    assert result.code == 0, result.stderr
    assert "worker is running different code" not in result.stderr.lower()
    assert "skew" not in result.stderr.lower()
    # The revision identifiers themselves must not appear in the human output either.
    assert CLI_REVISION not in result.stderr


def test_skew_is_silent_in_json_when_revisions_match(
    fake_revision_client: Callable[..., _RevisionRecordingFakeClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T013 / US3-S2: the JSON answer has no skew key when revisions match."""
    _set_cli_revision(monkeypatch, CLI_REVISION)
    fake_revision_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(_query_document(worker_revision=CLI_REVISION))
        }
    )

    result = _invoke("build", "status", EPIC_ID, "--json")

    assert result.code == 0, result.stderr
    assert "skew_notice" not in result.json
    assert result.json.get("worker_revision") == CLI_REVISION


def test_skew_degrades_when_worker_revision_is_unknown(
    fake_revision_client: Callable[..., _RevisionRecordingFakeClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T014 / US3-S3 / FR-010: an absent worker revision reports unknown and does not raise."""
    _set_cli_revision(monkeypatch, CLI_REVISION)
    fake_revision_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(_query_document(worker_revision=None))
        }
    )

    result = _invoke("build", "status", EPIC_ID)

    assert result.code == 0, result.stderr
    assert "worker revision is unknown" in result.stderr.lower()
    assert CLI_REVISION in result.stderr


def test_skew_degrades_in_json_when_worker_revision_is_unknown(
    fake_revision_client: Callable[..., _RevisionRecordingFakeClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T014 / US3-S3: the JSON answer reports unknown, not guessed."""
    _set_cli_revision(monkeypatch, CLI_REVISION)
    fake_revision_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(_query_document(worker_revision=None))
        }
    )

    result = _invoke("build", "status", EPIC_ID, "--json")

    assert result.code == 0, result.stderr
    document = result.json
    assert document.get("worker_revision") is None
    notice = document.get("skew_notice")
    assert notice is not None
    assert "unknown" in notice.lower()
    assert CLI_REVISION in notice


def test_worker_revision_is_recorded_once_and_carried_not_recomputed(
    fake_revision_client: Callable[..., _RevisionRecordingFakeClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T015 / US3-S4 / FR-008: the revision is captured at worker start and carried.

    A per-call `git rev-parse` would report the tree's current revision, which is
    the CLI's; the worker's own revision can only differ if it is snapshotted at
    boot and carried. We prove the snapshot path by making the query answer carry
    a worker_revision that does not match the CLI's: if the code recomputed from
    the tree, it would see the CLI's revision and the skew notice above could
    never be tested.
    """
    _set_cli_revision(monkeypatch, CLI_REVISION)
    client = fake_revision_client(
        workflows={
            WORKFLOW_ID: _FakeWorkflow(_query_document(worker_revision=WORKER_REVISION_A))
        }
    )

    # Capture the actual handle returned to _query_status so we count the same
    # object the CLI used, not a freshly-created twin.
    used_handles: list[_RevisionRecordingFakeWorkflowHandle] = []
    original_get_handle = client.get_workflow_handle

    def recording_get_handle(workflow_id: str, **kwargs: Any) -> _RevisionRecordingFakeWorkflowHandle:
        handle = original_get_handle(workflow_id, **kwargs)
        used_handles.append(handle)
        return handle

    monkeypatch.setattr(
        client, "get_workflow_handle", recording_get_handle
    )

    result = _invoke("build", "status", EPIC_ID)
    assert result.code == 0, result.stderr

    assert used_handles, "status did not request a workflow handle"
    assert used_handles[0].query_count >= 1
    assert WORKER_REVISION_A in result.stderr
