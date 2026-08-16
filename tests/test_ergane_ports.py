"""US4 port tests: `ergane doctor`, `usage`, and `repo onboard`.

These tests mirror the assertions of the legacy doctor, usage and repo-onboard
suites, but drive them through the unified `ergane`
dispatcher. Two cases the old suites could not have are included:

- a probe that raises a non-service exception is reported as one line naming
  `--debug` rather than as a traceback;
- a missing ledger exits 3 under the unified exit-code contract.

Written before `factory/cli/{doctor,usage,repo}.py` exist (T023 precedes T027):
until they land, every path here fails at `ergane: unknown noun` or import.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterator, NamedTuple

import pytest

from factory.cli import main as main_module


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> Run:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


@pytest.fixture
def invoke(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    def _caller(*argv: str, env: dict[str, str] | None = None) -> Run:
        saved: dict[str, str | None] = {}
        if env:
            saved = {k: os.environ.get(k) for k in env}
            for k, v in env.items():
                monkeypatch.setenv(k, v)
        try:
            return _invoke(list(argv), monkeypatch)
        finally:
            for k, v in saved.items():
                if v is None:
                    monkeypatch.delenv(k, raising=False)
                else:
                    monkeypatch.setenv(k, v)

    return _caller


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "doctor.db"


# --- doctor -------------------------------------------------------------------


def _patch_probe(
    monkeypatch: pytest.MonkeyPatch,
    exc: Exception | None = None,
) -> None:
    """Replace the global probe registry with a single synthetic probe."""
    from factory.doctor.probes import Probe

    class FakeProbe(Probe):
        name = "fake"

        def gather(self) -> str:
            if exc is not None:
                raise exc
            return "ok"

        def evaluate(self, snapshot: str) -> list[Any]:
            return []

    monkeypatch.setattr("factory.doctor.probes.REGISTRY", [FakeProbe()])


def test_doctor_non_service_probe_exception_is_one_line_naming_debug(
    invoke: Callable[..., Run],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe bug is reported as one line naming --debug, never a traceback."""
    _patch_probe(monkeypatch, RuntimeError("probe blew up"))

    result = invoke("doctor")

    assert result.code == 1
    assert result.stdout == ""
    lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(lines) == 1
    assert "--debug" in result.stderr
    assert "Traceback" not in result.stderr


def test_doctor_unreachable_service_exits_three(
    invoke: Callable[..., Run],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe whose service does not answer exits 3 and names the address."""
    from factory.doctor.probes import ServiceNotAnswering

    _patch_probe(monkeypatch, ServiceNotAnswering("temporal", reason="127.0.0.1:1"))

    result = invoke("doctor")

    assert result.code == 3
    assert result.stdout == ""
    assert "127.0.0.1:1" in result.stderr
    assert "Traceback" not in result.stderr


# --- usage --------------------------------------------------------------------


@pytest.fixture
def ledger_path(tmp_path: Path) -> Iterator[Path]:
    """A minimal seeded ledger, closed before the CLI opens it read-only."""
    from factory.usage.ledger import connect, upsert_record
    from factory.usage.models import Termination, UsageRecord

    path = tmp_path / "ledger.db"
    conn = connect(path)
    try:
        upsert_record(
            conn,
            UsageRecord(
                epic_id="epic-a",
                node_id="node-plan",
                attempt=1,
                persona="architect",
                spec_ref="epic-a:US1",
                key_alias="epic-a:node-plan:1:architect",
                prompt_tokens=1000,
                completion_tokens=100,
                cache_read_tokens=None,
                cache_write_tokens=None,
                request_count=4,
                spend_usd=0.10,
                final_usage_confirmed=True,
                termination=Termination.COMPLETED,
                issued_at="2026-08-10T09:00:00Z",
                torn_down_at="2026-08-10T10:00:00Z",
            ),
        )
    finally:
        conn.close()
    yield path


def test_usage_reads_a_ledger_through_ergane(
    invoke: Callable[..., Run], ledger_path: Path
) -> None:
    result = invoke("usage", "--db", str(ledger_path), "--by", "epic", "--json")

    assert result.code == 0
    assert result.json["by"] == "epic"
    assert result.json["totals"]["rows"] == 1


def test_usage_missing_ledger_is_exit_three(
    invoke: Callable[..., Run], tmp_path: Path
) -> None:
    missing = tmp_path / "nowhere" / "ledger.db"

    result = invoke(
        "usage", "--db", str(missing), "--by", "persona", "--json"
    )

    assert result.code == 3
    assert result.stdout == ""
    assert result.stderr != ""
    assert not missing.exists()
    assert not missing.parent.exists()


# --- repo onboard -------------------------------------------------------------


@pytest.fixture
def onboard_gh(monkeypatch: pytest.MonkeyPatch) -> "Any":
    """Inject a FakeGh into the onboard client factory, as the epic suite does."""
    from tests.fake_gh import FakeGh

    fake = FakeGh()

    def factory(*, repo_path: str):
        from factory.mergequeue.gh import GhClient
        from factory.mergequeue.github_forge import GithubForge

        return GithubForge(GhClient(repo=repo_path, runner=fake))

    monkeypatch.setattr("factory.workgraph.cli._onboard_forge_factory", factory)
    return fake


def _script_conforming_gh(fake: "Any", owner_repo: str = "OWNER/REPO") -> None:
    fake.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={
            "nameWithOwner": owner_repo,
            "visibility": "PUBLIC",
            "defaultBranchRef": "main",
        },
    )
    fake.expect_json(
        "api", f"repos/{owner_repo}",
        payload={"squash_merge_commit_title": "PR_TITLE"},
    )
    fake.expect_json(
        "api", f"repos/{owner_repo}/rules/branches/main",
        payload=[{
            "type": "merge_queue",
            "parameters": {
                "required_status_checks": [
                    {"context": "lint"},
                    {"context": "test"},
                    {"context": "typecheck"},
                ],
            },
        }],
    )


def _script_queue_less_gh(fake: "Any", owner_repo: str = "OWNER/REPO") -> None:
    fake.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={
            "nameWithOwner": owner_repo,
            "visibility": "PUBLIC",
            "defaultBranchRef": "main",
        },
    )
    fake.expect_json(
        "api", f"repos/{owner_repo}",
        payload={"squash_merge_commit_title": "PR_TITLE"},
    )
    fake.expect_json(
        "api", f"repos/{owner_repo}/rules/branches/main",
        payload=[],
    )


def test_repo_onboard_passes_a_conforming_repo(
    invoke: Callable[..., Run],
    tmp_path: Path,
    onboard_gh: "Any",
) -> None:
    from tests.target_repo import build_target_repo

    repo = build_target_repo(tmp_path / "target")
    _script_conforming_gh(onboard_gh)

    result = invoke("repo", "onboard", str(repo))

    assert result.code == 0
    assert "visibility" in result.stdout
    assert "merge_queue" in result.stdout
    assert "factory_yaml" in result.stdout


def test_repo_onboard_json_is_a_parseable_profile(
    invoke: Callable[..., Run],
    tmp_path: Path,
    onboard_gh: "Any",
) -> None:
    from tests.target_repo import build_target_repo

    repo = build_target_repo(tmp_path / "target")
    _script_conforming_gh(onboard_gh)

    result = invoke("repo", "onboard", "--json", str(repo))

    assert result.code == 0
    document = result.json
    assert document["passed"] is True
    assert "findings" in document


def test_repo_onboard_queue_less_repo_is_exit_one(
    invoke: Callable[..., Run],
    tmp_path: Path,
    onboard_gh: "Any",
) -> None:
    from tests.target_repo import build_target_repo

    repo = build_target_repo(tmp_path / "target")
    _script_queue_less_gh(onboard_gh)

    result = invoke("repo", "onboard", str(repo))

    assert result.code == 1
    assert "merge_queue" in result.stdout


# Import at module bottom to avoid circular imports with fixtures.
import os  # noqa: E402
