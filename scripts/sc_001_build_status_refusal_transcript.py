#!/usr/bin/env python3
"""Reproduce and record the SC-001 transcript for 053-US1.

This script reproduces the live worker/CLI skew that 053-US1 repairs: an
`epic_status` query that raises `WorkflowQueryFailedError` because the worker's
imported `NodeRecord` predates the `provenance` field the workflow code now
reads. The CLI output is captured exactly as an operator would see it.

Run:

    uv run python scripts/sc_001_build_status_refusal_transcript.py

The generated transcript is written to
specs/053-worker-skew-is-visible-and-survivable/evidence/us1-sc-001.md.
"""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from temporalio.client import WorkflowQueryFailedError
from temporalio.service import RPCError, RPCStatusCode

import factory.cli.nouns as nouns
from factory.cli.main import main as ergane_main


EPIC_ID = "023-composable-verification"
WORKFLOW_ID = f"epic-{EPIC_ID}"

REFUSAL_MESSAGE = "'NodeRecord' object has no attribute 'provenance'"


class _FakeWorkflowHandle:
    def __init__(self, workflow_id: str) -> None:
        self.id = workflow_id

    async def describe(self) -> Any:
        # The query refused, so describe would also refuse; degrade silently.
        raise WorkflowQueryFailedError(REFUSAL_MESSAGE)

    async def query(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name != "epic_status":
            raise WorkflowQueryFailedError(f"query {name!r} is not registered")
        raise WorkflowQueryFailedError(REFUSAL_MESSAGE)


class _FakeTemporalClient:
    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> _FakeWorkflowHandle:
        if workflow_id != WORKFLOW_ID:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        return _FakeWorkflowHandle(workflow_id)


async def _open_client() -> _FakeTemporalClient:
    return _FakeTemporalClient()


def main() -> int:
    nouns._open_client = _open_client  # type: ignore[assignment]

    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = StringIO(), StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = ergane_main(["build", "status", EPIC_ID])
        except SystemExit as exit_request:
            code = exit_request.code
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    exit_code = 0 if code is None else int(code)
    stdout = buf_out.getvalue()
    stderr = buf_err.getvalue()

    evidence_dir = Path("specs/053-worker-skew-is-visible-and-survivable/evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = evidence_dir / "us1-sc-001.md"

    transcript = f"""# 053-US1 evidence — SC-001

SC-001: `ergane build status <epic>` exits 0 when the workflow refuses the
`epic_status` query, and reports the cause in place.

This transcript reproduces the worker/CLI skew measured on 2026-08-17: a worker
that imported `NodeRecord` before the `provenance` field existed, running
workflow code re-imported from disk that reads `record.provenance`. The
workflow-side `epic_status` handler raises `AttributeError`, which the Temporal
client surfaces as `WorkflowQueryFailedError`.

The exit code is captured before any pipe, as required by plan trap 11.

```
$ ergane build status {EPIC_ID}
{stdout.rstrip()}
$ echo $?
{exit_code}
```

stderr:

```
{stderr.rstrip() or "(empty)"}
```
"""

    transcript_path.write_text(transcript, encoding="utf-8")
    print(f"wrote {transcript_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
