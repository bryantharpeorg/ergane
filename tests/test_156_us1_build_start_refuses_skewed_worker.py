"""156 US1: `ergane build start` refuses when the serving worker runs different code.

US1-S1/FR-001: a worker whose advertised revision differs from the CLI's tree
revision is refused before `start_workflow`, with both revisions and the restart
remedy in one line (US1-S5). US1-S3/FR-003: an advertisement of `None` — a
pre-053 or non-git worker — refuses with the "unknown" wording, the conservative
direction. US1-S4: a CLI that cannot resolve its own revision never refuses; its
own blindness must not lock the operator out. US1-S2/FR-006: the aligned case
behaves byte-identically to today — same output, same exit code, no skew text.

The worker's advertisement reaches the CLI through the seam 053 already built
(FR-002): `EpicStatus.worker_revision`, the same document `_query_status` reads.
`build start` reads it from an epic that is already open — the interceptor
re-stamps every activation, so any open epic's answer advertises the revision of
the worker serving it *now*, which is exactly the comparison the refusal needs.
When no advertisement can be read — no open epic, a listing the server will not
answer, a refused query — there is no skew to name and the dispatch proceeds:
the check activates only on evidence, like `engine_skew_findings` before it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, NamedTuple

import pytest
from temporalio.client import WorkflowQueryFailedError
from temporalio.service import RPCError, RPCStatusCode

import factory.cli.nouns as nouns_package
from factory.cli.main import main as ergane_main
from factory.cli.nouns import build as build_module
from tests.conftest import FAKE_MASTER_KEY, FakeLiteLLM
from tests.test_interpreter import (
    MODEL_ALIAS,
    PLAN_TEXT,
    PROXY_URL as TEST_PROXY_URL,
    TASKS_TEXT,
    TIMEOUT_S,
)
from factory.config import Persona, WriteScope
from factory.usage.litellm_client import PROXY_URL_ENV, LiteLLMClient
from factory.workgraph.derive import derive_workgraph
from factory.workgraph.workflow import JUDGE_PERSONA, EpicInput

EPIC_ID = "156-us1-demo"
WORKFLOW_ID = f"epic-{EPIC_ID}"
WORKER_REVISION_A = "b6233ee"
WORKER_REVISION_B = "c0ffee1"
CLI_REVISION = WORKER_REVISION_A
RESTART_REMEDY = "systemctl --user restart ergane-worker"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def _invoke(argv: tuple[str, ...]) -> int:
    try:
        code = ergane_main(list(argv))
    except SystemExit as exit_request:
        code = exit_request.code
    return 0 if code is None else int(code)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        code = _invoke(argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


@pytest.fixture
def run_async(
    capsys: pytest.CaptureFixture[str],
) -> Callable[..., Awaitable[Run]]:
    async def invoke(*argv: str) -> Run:
        code = await asyncio.to_thread(_invoke, argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


class RecordingClient:
    """Stands in for the Temporal client on the `build start` path.

    It answers the two reads the refusal makes — the open-epic listing and the
    `epic_status` query of the first open epic — and records every
    `start_workflow` call, so US1-S1's proof is an invocation count rather than
    an absence of output (constitution VIII: provable from what the command
    actually did). A client that lacks `list_workflows` exercises the read's
    degradation: it is never a refusal.
    """

    def __init__(
        self,
        *,
        open_epics: dict[str, dict[str, Any]] | None = None,
        list_error: Exception | None = None,
    ) -> None:
        self.open_epics = open_epics or {}
        self.list_error = list_error
        self.started: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> Any:
        return _RecordingHandle(self, workflow_id)

    def list_workflows(self, query: str) -> Any:
        if self.list_error is not None:
            error = self.list_error

            async def _broken() -> Any:
                raise error
                yield  # pragma: no cover - unreachable; makes this a generator

            return _broken()

        ids = list(self.open_epics)

        async def _open() -> Any:
            from types import SimpleNamespace

            for workflow_id in ids:
                yield SimpleNamespace(id=workflow_id)

        return _open()

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        self.started.append((args, kwargs))
        return object()

    async def close(self) -> None: ...


class _RecordingHandle:
    def __init__(self, client: RecordingClient, workflow_id: str) -> None:
        self._client = client
        self.id = workflow_id

    async def query(self, name: str, *args: Any, **kwargs: Any) -> Any:
        document = self._client.open_epics.get(self.id)
        if document is None:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        if isinstance(document, BaseException):
            raise document
        return document


def _query_document(worker_revision: str | None) -> dict[str, Any]:
    """A minimal `epic_status` answer — the same shape 053's tests query."""
    return {
        "epic_state": "RUNNING",
        "nodes": {
            "us1": {
                "state": "RUNNING",
                "attempt": 1,
                "branch": f"factory/156-skew/us1",
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


def _open_epics(worker_revision: str | None) -> dict[str, dict[str, Any]]:
    return {WORKFLOW_ID: _query_document(worker_revision)}


PERSONAS = {
    "implementer": Persona(
        name="implementer",
        agent="claude-code",
        model=MODEL_ALIAS,
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=TIMEOUT_S,
    ),
    JUDGE_PERSONA: Persona(
        name=JUDGE_PERSONA,
        agent="claude-code",
        model="judge-alias",
        fallback=None,
        skills=(),
        write_scope=WriteScope.READ,
        needs_worktree=False,
        timeout_s=3600,
    ),
}


def _write_graph(tmp_path: Path) -> Path:
    """Compile a one-node graph naming a scratch target repo (023's shape)."""
    target_repo = tmp_path / "target-repo"
    target_repo.mkdir(parents=True, exist_ok=True)
    (target_repo / "factory.yaml").write_text(
        "version: 1\nruntime: bwrap\ngates:\n  test: uv run pytest -q\n",
        encoding="utf-8",
    )
    spec_dir = tmp_path / EPIC_ID
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        f"""# Feature Specification: {EPIC_ID}

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build it (Priority: P1)

As the operator, I build the thing, so that it works.

**Acceptance Scenarios**:

1. **Given** a thing, **When** it is built, **Then** it works.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST build the thing.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
""",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text(PLAN_TEXT, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(TASKS_TEXT, encoding="utf-8")

    graph = derive_workgraph(
        (spec_dir / "spec.md").read_text(encoding="utf-8"),
        epic_id=EPIC_ID,
        feature=EPIC_ID,
        specs_root=str(tmp_path),
        target_repo=str(target_repo),
    )
    graph_path = tmp_path / "workgraph.json"
    graph_path.write_text(
        json.dumps(
            {
                "epic_id": graph.epic_id,
                "feature": graph.feature,
                "specs_root": graph.specs_root,
                "target_repo": graph.target_repo,
                "nodes": [
                    {
                        "id": node.id,
                        "story_key": node.story_key,
                        "persona": node.persona,
                        "spec_ref": node.spec_ref,
                        "requirement_keys": list(node.requirement_keys),
                        "depends_on": list(node.depends_on),
                        "depends_on_merged": list(node.depends_on_merged),
                        "timeout_override_s": node.timeout_override_s,
                    }
                    for node in graph.nodes
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return graph_path


@pytest.fixture
def fake_lite_llm_and_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeLiteLLM:
    """The preflight's alias probe answered by a fake proxy (023's fixture)."""
    fake = FakeLiteLLM(base_url=TEST_PROXY_URL, master_key=FAKE_MASTER_KEY)
    registry = build_module._preflight_registry()
    fake.served_models = {
        alias
        for name in ("implementer", JUDGE_PERSONA)
        for alias in (registry[name].model, registry[name].fallback)
        if alias
    }

    def preflight_client() -> LiteLLMClient:
        return LiteLLMClient(
            base_url=fake.base_url,
            master_key=fake.master_key,
            transport=fake.transport,
        )

    monkeypatch.setattr(nouns_package, "_open_preflight_client", preflight_client)
    return fake


@pytest.fixture
def start_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_lite_llm_and_preflight: FakeLiteLLM,
) -> Callable[..., RecordingClient]:
    """Point the CLI at the graph and the recording client; return the client.

    `worker_revision_seam` is the seam this story's comparison reads (FR-002):
    the revision an open epic's status answer advertises. Patching it here keeps
    every test's client construction in one place; each test states its own
    advertisement.
    """

    def setup(
        *,
        worker_revision_seam: str | None | Exception | object = WORKER_REVISION_A,
    ) -> RecordingClient:
        if worker_revision_seam is _UNPATCHED:
            client = RecordingClient()
        elif isinstance(worker_revision_seam, Exception):
            # The listing itself raises: a server that will not answer the
            # capacity-shaped read (the time-skipping server's own refusal).
            client = RecordingClient(list_error=worker_revision_seam)
        elif worker_revision_seam is None or isinstance(worker_revision_seam, str):
            client = RecordingClient(open_epics=_open_epics(worker_revision_seam))  # type: ignore[arg-type]
        else:
            client = RecordingClient()
        monkeypatch.setenv(PROXY_URL_ENV, TEST_PROXY_URL)

        async def _open_client() -> RecordingClient:
            return client

        monkeypatch.setattr(nouns_package, "_open_client", _open_client)
        monkeypatch.setattr(
            nouns_package, "_cli_revision_for_tests", lambda: CLI_REVISION
        )
        return client

    return setup


#: Sentinel: leave the CLI-revision seam at its default (unpatched) in tests
#: that patch the subprocess instead, or that need the real degradation.
_UNPATCHED = object()


# --- T001 (US1-S1, US1-S2, FR-001, FR-006) ------------------------------------


async def test_a_skewed_worker_is_refused_before_any_dispatch(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_env: Callable[..., RecordingClient],
) -> None:
    """US1-S1 / FR-001: skew refuses, names both facts plus the remedy, dispatches nothing.

    The proof is the recorded invocation count, not the shape of an error: the
    refusal must stand between preflight and `start_workflow` (constitution
    VIII), so the fake client records no call at all.
    """
    client = start_env(worker_revision_seam=WORKER_REVISION_B)  # differs from CLI's
    graph_path = _write_graph(tmp_path)

    result = await run_async("build", "start", str(graph_path))

    assert result.code != 0
    assert "worker revision" in result.stderr
    assert WORKER_REVISION_B in result.stderr
    assert CLI_REVISION in result.stderr
    assert RESTART_REMEDY in result.stderr
    assert client.started == [], (
        "the refusal must stand before `start_workflow`; the fake client "
        "recorded a dispatch it must never have made"
    )


async def test_an_aligned_worker_dispatches_with_no_skew_text_anywhere(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_env: Callable[..., RecordingClient],
) -> None:
    """US1-S2 / FR-006: the aligned case dispatches exactly as today, saying nothing.

    Both halves pinned: a dispatch is recorded, and no skew wording reaches
    either stream — the refusal adds no output to the case it does not fire on.
    """
    client = start_env(worker_revision_seam=WORKER_REVISION_A)  # equals the CLI's
    graph_path = _write_graph(tmp_path)

    result = await run_async("build", "start", str(graph_path))

    assert result.code == 0, result.stderr
    assert result.stdout.strip() == WORKFLOW_ID
    assert len(client.started) == 1
    assert isinstance(client.started[0][0][1], EpicInput)
    assert "different code" not in result.stdout
    assert "different code" not in result.stderr
    assert "unknown" not in result.stdout.lower()
    assert "restart" not in result.stdout.lower()


def test_an_aligned_refusal_message_is_never_composed(
    start_env: Callable[..., RecordingClient],
) -> None:
    """US1-S2, the seam itself: equality composes nothing, so nothing can leak.

    A message that today's aligned path could never print cannot be added to it
    by a caller reordering the arms — the pure function returns `None` on
    equality, which is the whole of the aligned case's silence.
    """
    start_env(worker_revision_seam=_UNPATCHED)
    assert build_module.skew_refusal(WORKER_REVISION_A, CLI_REVISION) is None
    assert build_module.skew_refusal(WORKER_REVISION_A, None) is None


# --- T002 (US1-S3, US1-S4, FR-003) ---------------------------------------------


async def test_a_worker_that_advertises_nothing_is_refused_as_unknown(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_env: Callable[..., RecordingClient],
) -> None:
    """US1-S3 / FR-003: a `None` advertisement refuses — the conservative direction.

    An unknown revision cannot be compared, so it earns the same refusal an
    unequal one does, with the wording 053's notice already uses.
    """
    client = start_env(worker_revision_seam=None)
    graph_path = _write_graph(tmp_path)

    result = await run_async("build", "start", str(graph_path))

    assert result.code != 0
    assert "worker revision is unknown" in result.stderr
    assert RESTART_REMEDY in result.stderr
    assert CLI_REVISION in result.stderr
    assert client.started == []


async def test_a_cli_that_cannot_resolve_its_own_revision_does_not_refuse(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_env: Callable[..., RecordingClient],
) -> None:
    """US1-S4: the CLI's own blindness must not lock the operator out.

    `_cli_revision` degrades to `None` off a git checkout; on that degenerate
    reading the refusal must not fire, even against a worker that advertises a
    revision — the comparison simply cannot be made.
    """
    client = start_env(worker_revision_seam=WORKER_REVISION_B)
    graph_path = _write_graph(tmp_path)
    # Genuine blindness, both halves: the test seam cleared to its no-override
    # answer (so `_cli_revision` falls through to the real read) and that read
    # made to fail the way it does off a git checkout.
    monkeypatch.setattr(nouns_package, "_cli_revision_for_tests", lambda: None)
    monkeypatch.setattr(
        build_module.subprocess,
        "check_output",
        lambda *a: (_ for _ in ()).throw(OSError("not a git repository")),
    )

    result = await run_async("build", "start", str(graph_path))

    assert result.code == 0, result.stderr
    assert len(client.started) == 1


def test_the_refusal_degrades_on_a_cli_revision_of_none_at_the_seam(
    start_env: Callable[..., RecordingClient],
) -> None:
    """FR-003 at the seam: CLI-`None` composes no refusal for either worker side."""
    start_env(worker_revision_seam=_UNPATCHED)
    assert build_module.skew_refusal(WORKER_REVISION_B, None) is None


# --- US1-S5 (T005) / FR-001: the one-line shape --------------------------------


async def test_the_refusal_names_all_three_facts_in_one_line(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_env: Callable[..., RecordingClient],
) -> None:
    """US1-S5 / FR-001: worker revision, tree revision, remedy — three facts, one line.

    No diagnosis step between the refusal and the remedy: the line the operator
    reads carries everything needed to act on it.
    """
    start_env(worker_revision_seam=WORKER_REVISION_B)
    graph_path = _write_graph(tmp_path)

    result = await run_async("build", "start", str(graph_path))

    lines = [line for line in result.stderr.splitlines() if "worker revision" in line]
    assert len(lines) == 1, f"expected exactly one refusal line, got {lines}"
    refusal = lines[0]
    assert WORKER_REVISION_B in refusal
    assert CLI_REVISION in refusal
    assert RESTART_REMEDY in refusal


def test_the_seam_refusal_is_one_line_for_every_case_it_refuses(
    start_env: Callable[..., RecordingClient],
) -> None:
    """US1-S5 at the seam: skew and unknown both render as exactly one line."""
    start_env(worker_revision_seam=_UNPATCHED)
    skew = build_module.skew_refusal(WORKER_REVISION_B, CLI_REVISION)
    assert skew is not None
    assert "\n" not in skew
    assert WORKER_REVISION_B in skew
    assert CLI_REVISION in skew
    assert RESTART_REMEDY in skew

    unknown = build_module.skew_refusal(None, CLI_REVISION)
    assert unknown is not None
    assert "\n" not in unknown
    assert "worker revision is unknown" in unknown
    assert RESTART_REMEDY in unknown


# --- the read degrades; the refusal must not fire on unreadable evidence -------


async def test_an_empty_floor_advertises_nothing_and_dispatch_proceeds(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_env: Callable[..., RecordingClient],
) -> None:
    """An empty floor is not skew: with no open epic to read, dispatch proceeds.

    `build start` reads the worker's advertisement from an epic that is already
    open (FR-002's source, read where an answer can exist). A fresh floor has
    none, and absence of evidence is not evidence of skew — the same direction
    US1-S4 gives the CLI's own blindness, and the only one that never locks an
    operator out of their factory. This is the first `build start` of every
    floor, so a refusal here would have refused the day before the first epic
    ever ran.
    """
    client = start_env(worker_revision_seam=_UNPATCHED)
    graph_path = _write_graph(tmp_path)

    result = await run_async("build", "start", str(graph_path))

    assert result.code == 0, result.stderr
    assert len(client.started) == 1


async def test_a_server_that_will_not_answer_the_listing_cannot_refuse(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_env: Callable[..., RecordingClient],
) -> None:
    """An unanswered read degrades to proceed: dispatch is never blocked by it.

    The listing is the production query shape exactly — and the time-skipping
    test server refuses it outright (`UNIMPLEMENTED`, probed 2026-09-07), so a
    read that hardened into a refusal would fail every test-server floor. The
    failure is a reading this command could not take, not a worker known to be
    skewed — the degradation `engine_skew_findings` already models, and the
    shape every Temporal read on this module carries (the guard sweep's own
    table).
    """
    client = start_env(worker_revision_seam=RPCError(
        "Worker Versioning not yet supported in test server", 12, b""
    ))
    graph_path = _write_graph(tmp_path)

    result = await run_async("build", "start", str(graph_path))

    assert result.code == 0, result.stderr
    assert len(client.started) == 1


async def test_a_refused_epic_status_query_cannot_refuse_the_start(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_env: Callable[..., RecordingClient],
) -> None:
    """An epic that will not answer degrades the reading, not the dispatch.

    The same posture `_query_status` takes (the 053 contract): a refused query
    is a degraded reading, never a failed command. An open epic whose history
    predates a field the answer now declares refuses exactly this way, and a
    previous *closed* run rejects a query with `WorkflowQueryRejectedError` —
    neither may become a refusal of a dispatch that has not happened.
    """
    client = start_env(worker_revision_seam=_UNPATCHED)
    # The first open epic refuses the query the way a pre-053 history does;
    # the listing itself answers, so the read reaches the query and degrades.
    client.open_epics = {
        WORKFLOW_ID: WorkflowQueryFailedError("provenance field is not present")
    }
    graph_path = _write_graph(tmp_path)

    result = await run_async("build", "start", str(graph_path))

    assert result.code == 0, result.stderr
    assert len(client.started) == 1