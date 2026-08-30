"""The record says what the verdict was measured against (118 US2).

US1 stops the next stale-base PASS. This story makes every PASS — past and
future — auditable, because until now a verdict recorded *that* a node passed
and never *what it passed against*. `PreparedWorktree` has always known its
`base_ref`; the verification row did not carry it, so the case US1 exists to
prevent was invisible in the record even after the fact.

Three properties, one per acceptance scenario:

- **The row carries the pin (US2-S1, FR-006, plan trap 5).** And it carries the
  pin *the attempt actually ran against*, taken from the prepared worktree
  rather than re-derived at record-writing time. The e2e test below arranges
  for all three candidate answers to differ — the pin, the worktree's HEAD
  after the node committed, and the landing branch's head after siblings landed
  — so an implementation that re-asks git dies on the assertion rather than
  passing by coincidence. Re-deriving is the same class of defect as the one
  this whole spec is about: an answer that can differ from the one the verdict
  was measured on.
- **The status line shows the base beside the landing head (US2-S2, FR-007).**
  One line, so the stale-base diagnosis is a reading rather than an
  investigation. The landing head is read live, at status time, because a head
  captured at preparation is precisely the number that cannot show staleness.
- **Old rows read as unknown (US2-S3, FR-006).** Every `verification.db` in the
  world predates this column. A row that answers with a plausible-looking sha
  it never measured is worse than one that says it does not know, so the
  migration adds a NULL column and the read maps NULL to one named sentinel.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.activities.agent_activities import PrepareWorktreeInput
from factory.cli.nouns.build import _landing_head, render_status
from factory.verify import store
from factory.verify.models import UNKNOWN_BASE_REF, VerificationResult
from factory.workgraph.models import NodeState
from factory.workgraph.workflow import EpicInput, EpicWorkflow
from factory.workgraph.worktree import PreparedWorktree, ensure
from tests.target_repo import build_target_repo, git

NODE = "us1"


def head(repo: Path, ref: str = "HEAD") -> str:
    return git(repo, "rev-parse", ref).strip()


def commit(repo: Path, name: str, text: str) -> str:
    """One commit in `repo`, returning the new head."""
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", f"add {name}")
    return head(repo)


# --- T011 [US2] (spec US2-S1, trap 5) ----------------------------------------


async def test_a_verified_attempts_row_carries_the_base_it_was_pinned_to(
    tmp_path: Path,
) -> None:
    """FR-006: the row's base is the prepared worktree's pin, not a re-reading.

    The world is arranged so that the three answers an implementation could
    give are three different shas: the pin `ensure` recorded, the worktree's
    HEAD once the node has committed its work, and the landing branch's head
    once a sibling has landed. Only one of them is what the verdict was
    measured against, and it is the one `PreparedWorktree` already carries.
    """
    from tests.test_interpreter import (
        EPIC_ID,
        PROXY_URL,
        WORKFLOW_ID,
        ScriptedWorld,
        make_graph,
        make_node,
        passing,
    )

    env = await WorkflowEnvironment.start_time_skipping()
    try:
        repo = build_target_repo(tmp_path / "target")
        factory_root = tmp_path / ".ergane"

        script = ScriptedWorld({NODE: [passing()]}, client=env.client)
        prepared: list[PreparedWorktree] = []

        @activity.defn(name="prepare_worktree")
        async def real_prepare_worktree(
            request: PrepareWorktreeInput,
        ) -> PreparedWorktree:
            script._log("prepare_worktree", request.node_id)
            script.prepare_requests.append(request)
            result = ensure(
                request.target_repo,
                request.epic_id,
                request.node_id,
                factory_root=factory_root,
            )
            prepared.append(result)
            # The node's own work, committed the way an agent commits as it
            # goes: the worktree's HEAD is now a different sha from the pin.
            commit(Path(result.path), "node_work.py", "the node's own work\n")
            # And a sibling lands while this node runs: the landing branch's
            # head is a third sha, different from both.
            commit(repo, "sibling.py", "landed while the node ran\n")
            return result

        activities = [
            candidate
            for candidate in script.activities()
            if activity._Definition.must_from_callable(candidate).name
            != "prepare_worktree"
        ] + [real_prepare_worktree]

        graph = make_graph([make_node(NODE, "US1")], target_repo=str(repo))

        async with Worker(
            env.client,
            task_queue="workgraph",
            workflows=[EpicWorkflow],
            activities=activities,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                EpicWorkflow.run,
                EpicInput(graph=graph, proxy_url=PROXY_URL),
                id=WORKFLOW_ID,
                task_queue="workgraph",
            )
            status = await handle.result()

        assert status.nodes[NODE].state == NodeState.MERGED
        assert len(prepared) == 1
        pin = prepared[0].base_ref

        # The premise: three distinct answers were available.
        worktree_head = head(Path(prepared[0].path))
        landing_head = head(repo)
        assert len({pin, worktree_head, landing_head}) == 3

        (row,) = script.records
        assert row.base_ref == pin
        assert row.base_ref != worktree_head
        assert row.base_ref != landing_head

        # And the same pin reaches the operator's status document, from the
        # same prepared worktree rather than from a second reading.
        assert status.nodes[NODE].base_ref == pin
    finally:
        await env.shutdown()


def test_the_recorded_base_survives_the_evidence_store(tmp_path: Path) -> None:
    """FR-006: the base is a stored column, not a value that lives in memory.

    A verdict is audited after the fact or not at all, so the pin has to be on
    the row an operator reads back — the same trip `node_history` makes for the
    retry prompt and the escalation summary.
    """
    from tests.test_verify_store import make_result

    pinned = "b" * 40
    with closing(store.connect(tmp_path / "verification.db")) as conn:
        store.upsert_result(conn, make_result(base_ref=pinned))
        (restored,) = store.node_history(conn, "epic-7", "node-3")

    assert restored.base_ref == pinned


# --- T012 [US2] (spec US2-S2) ------------------------------------------------


def _document(base_ref: str = "a" * 40) -> dict[str, Any]:
    """A status document with one dispatched node, as the CLI decodes one."""
    return {
        "epic_state": "RUNNING",
        "nodes": {
            NODE: {
                "state": NodeState.VERIFYING,
                "attempt": 1,
                "branch": f"factory/118/{NODE}",
                "base_ref": base_ref,
                "history": [],
            }
        },
    }


def node_line(rendered: str) -> str:
    lines = [line for line in rendered.splitlines() if line.startswith(NODE)]
    assert len(lines) == 1, f"expected one '{NODE}' line in:\n{rendered}"
    return lines[0]


def test_the_status_line_shows_the_base_beside_the_landing_head() -> None:
    """FR-007: one line, both shas — the stale-base case in seconds.

    The two numbers have to sit on the same line for the same node, because the
    question an operator is asking is a comparison. A base in one block and a
    landing head in another is the investigation this story exists to end.
    """
    base = "a" * 40
    landing = "c" * 40

    line = node_line(
        render_status(
            "118-epic",
            _document(base),
            "RUNNING",
            landing_head=("ergane-buildout", landing),
        )
    )

    assert base[:12] in line
    assert landing[:12] in line
    assert "ergane-buildout" in line


def test_a_landing_head_that_cannot_be_read_costs_only_its_own_token() -> None:
    """FR-007, degraded: a reading that failed says so and prints no number.

    `ergane build status` degrades rather than breaks (052), and the one thing
    it may never do here is invent the comparison — a landing head guessed from
    the base would read as "current" for every node in the epic.
    """
    base = "a" * 40

    line = node_line(render_status("118-epic", _document(base), "RUNNING"))

    assert base[:12] in line
    assert "landing head unavailable" in line


def test_the_landing_head_is_read_live_from_the_declared_target_repo(
    tmp_path: Path,
) -> None:
    """FR-007: *current* head, resolved against the repo the epic declares.

    Two halves, and the story needs both. Live, because a head captured when
    the worktree was pinned is the base — reading it at dispatch would print
    the same number twice and show nothing. Declared, because a status read
    against whatever clone the operator's shell happens to sit in would answer
    with a head that governs nothing (constitution IX).
    """
    repo = build_target_repo(tmp_path / "target")
    document = {"nodes": {}, "target_repo": str(repo)}

    reading = _landing_head(document)
    assert reading is not None
    branch, head_now = reading
    assert branch == "main"
    assert head_now == head(repo)

    # It moves when the landing branch moves.
    moved = commit(repo, "sibling.py", "a sibling landed\n")
    assert _landing_head(document) == (branch, moved)
    assert moved != head_now

    # An answer naming no repository gets no reading — never one taken against
    # the reader's own directory.
    assert _landing_head({"nodes": {}}) is None


def test_a_node_that_never_dispatched_reports_no_base() -> None:
    """The control: no pin, no reading. A node that has prepared nothing has no
    base, and printing the sentinel beside a landing head would invite exactly
    the comparison there is nothing to compare."""
    document = _document()
    document["nodes"][NODE]["base_ref"] = UNKNOWN_BASE_REF
    document["nodes"][NODE]["state"] = NodeState.PENDING

    line = node_line(
        render_status(
            "118-epic", document, "RUNNING", landing_head=("ergane-buildout", "c" * 40)
        )
    )

    assert "base" not in line
    assert UNKNOWN_BASE_REF not in line


# --- T013 [US2] (spec US2-S3) ------------------------------------------------


#: `verification_results` exactly as every store written before this story has
#: it: no `base_ref` column. Written out here rather than read from git, so the
#: migration is tested against a shape rather than against whatever the DDL
#: file says today.
_PRE_118_RESULTS_DDL = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version (version) VALUES (7);

CREATE TABLE verification_results (
    id                INTEGER PRIMARY KEY,
    epic_id           TEXT    NOT NULL CHECK (epic_id <> ''),
    node_id           TEXT    NOT NULL CHECK (node_id <> ''),
    attempt           INTEGER NOT NULL CHECK (attempt >= 1),
    form              TEXT    NOT NULL CHECK (form IN ('PHASE', 'NODE')),
    verdict           TEXT    NOT NULL CHECK (verdict IN ('PASS', 'FAIL')),
    gate_results      TEXT    NOT NULL,
    output_check      TEXT    NOT NULL,
    judge_verdict     TEXT,
    judge_unavailable INTEGER NOT NULL DEFAULT 0 CHECK (judge_unavailable IN (0, 1)),
    criteria_drift    INTEGER NOT NULL DEFAULT 0 CHECK (criteria_drift IN (0, 1)),
    criteria_sha256   TEXT    NOT NULL,
    spec_ref          TEXT    NOT NULL CHECK (spec_ref <> ''),
    started_at        TEXT    NOT NULL,
    finished_at       TEXT    NOT NULL,
    provenance        TEXT,
    loop_digest       TEXT,
    loop_summary      TEXT,
    UNIQUE (epic_id, node_id, attempt, form)
);

INSERT INTO verification_results (
    epic_id, node_id, attempt, form, verdict, gate_results, output_check,
    criteria_sha256, spec_ref, started_at, finished_at
) VALUES (
    'pre-118', 'us1', 1, 'PHASE', 'PASS', '[]',
    '{"write_scope":"worktree","has_diff":true,"expected_artifacts":[],"artifacts_present":null,"passed":true}',
    'aaaa', 'pre-118/US1', '2026-08-01T10:00:00Z', '2026-08-01T10:03:00Z'
);
"""


def test_a_row_written_before_this_change_reads_as_unknown(tmp_path: Path) -> None:
    """US2-S3: the base of an unmeasured row is unknown, never a wrong value.

    The migration runs on the store that already exists — every one of them —
    and the column it adds is NULL for rows nobody measured a base for. The
    read maps that to one named sentinel, so a caller can never mistake it for
    a sha: angle brackets are not legal in a git ref.
    """
    db_path = tmp_path / "verification.db"
    with closing(sqlite3.connect(db_path)) as raw:
        raw.executescript(_PRE_118_RESULTS_DDL)
        raw.commit()

    with closing(store.connect(db_path)) as migrated:
        columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(verification_results)")
        }
        assert "base_ref" in columns

        (old,) = store.node_history(migrated, "pre-118", "us1")

    assert old.base_ref == UNKNOWN_BASE_REF
    # Nothing else was lost or invented on the way through.
    assert old.spec_ref == "pre-118/US1"
    assert old.loop_digest is None


def test_a_result_built_without_a_base_is_unknown_rather_than_empty() -> None:
    """The unknown reading is decided once, and the dataclass default is it.

    A caller that never supplied a base is in exactly the position a pre-118
    row is in: nothing measured one. An empty-string default would read as a
    value, and `None` would push the decision out to every renderer.
    """
    from tests.test_verify_store import make_result

    assert make_result().base_ref == UNKNOWN_BASE_REF
    assert VerificationResult.__dataclass_fields__["base_ref"].default == (
        UNKNOWN_BASE_REF
    )
