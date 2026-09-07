"""127-US2 — the rendered reading, from a real killed node with a remote branch.

T017's evidence is generated here rather than pasted from a scratch clone,
because the same end-to-end shape is reachable in-process: a node that pushed
its branch to a real bare origin, ended by an operator's KILL, and left the
archive-and-clear activity with something to report. Both verbs render the
same `epic_status` answer in each run, side by side, so the evidence is the
run itself — the two node lines, byte-compared, are committed below as the
story's pasted output (constitution VIII, D-037).

Two runs, because the epic's two paths reach the terminal record differently
and the story's verification section asks for the second one by name:

- **A ladder kill** — the node exhausts its ladder, the operator presses KILL,
  and the archive tidies up. This is the row US1's truth table calls row three:
  a report with no cause, so the line carries the housekeeping token alone.
- **A push-refusal kill** — the landing's push is refused non-fast-forward, the
  operator presses KILL on the page, and the node ends with git's refusal on
  the record *and* the archive's report beside it. This is the exact sequence
  that cost four hours, and the row the token exists for: both tokens on one
  line, cause first.

`RealArchiveWorld` is US1's harness (`test_126_us2_kill_archives_remote.py`);
`RefusedPushWorld` is epic 100's (`test_100_push_reports_refusal.py`). The
refusal world is composed with the real archive activity here — the one place
the two harnesses were not already joined, and the join is what makes row one
of the truth table observable end to end.
"""

from __future__ import annotations

import json
from typing import Any

from temporalio import activity
from temporalio.converter import default as default_data_converter
from temporalio.testing import WorkflowEnvironment

from factory.activities.agent_activities import archive_and_clear_remote_branch
from factory.activities.merge_activities import (
    LANDING_REF_CONFLICT,
    OpenLandingPrInput,
)
from factory.cli.nouns.build import render_status
from factory.verify.models import EscalationChoice
from factory.workgraph.models import EpicState, NodeState
from factory.workgraph.worktree import WorktreeError, push_branch
from temporalio.exceptions import ApplicationError

from tests.test_100_push_reports_refusal import _rejection_line, flat
from tests.test_126_us2_kill_archives_remote import (
    EPIC as EPIC_126,
    NODE as NODE_126,
    RealArchiveWorld,
    Repo,
    graph as graph_126,
    repo as repo_fixture,  # noqa: F401  — pytest fixture, re-exported
)

repo = repo_fixture

from tests.test_epic_escalation_child import ladder_fails
from tests.test_interpreter import (
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    passing,
    run_epic,
    states,
)

# The helpers that read the wire and the line, from the module this story owns.
from tests.test_127_us2_both_surfaces_print_the_housekeeping import (
    as_json_document,
    node_line,
    status_verb_lines,
)


class RefusedPushRealArchiveWorld(RealArchiveWorld):
    """The refusal world of epic 100, composed with the real archive activity.

    `open_landing_pr` fails the way the real one does — `ApplicationError` over
    a `WorktreeError` a real git raised, chained with `from exc` so the cause
    walk `_failure_detail` performs is the real one — and
    `archive_and_clear_remote_branch` is the real activity against real git.
    The composition is the point: the push-refusal KILL reaches
    `_archive_and_clear_remote_branch` directly, never `_close_out` (127 plan
    trap 1), so the report and the cause meet on the same record only here.
    """

    def __init__(
        self, script: dict[str, list[Any]], *, error: WorktreeError, **kwargs: Any
    ) -> None:
        super().__init__(script, **kwargs)
        self.error = error
        self.open_attempts = 0

    def activities(self) -> list[Any]:
        world = self
        inherited = [
            fn
            for fn in super().activities()
            if _activity_name(fn) != "open_landing_pr"
        ]

        @activity.defn(name="open_landing_pr")
        async def open_landing_pr(request: OpenLandingPrInput) -> Any:
            world._log("open_landing_pr", request.node_id)
            world.landing_requests.append(request)
            world.open_attempts += 1
            raise ApplicationError(
                str(world.error), type=LANDING_REF_CONFLICT
            ) from world.error

        return inherited + [open_landing_pr]


def _activity_name(fn: Any) -> str:
    """The name Temporal registers a scripted activity under."""
    definition = getattr(fn, "__temporal_activity_definition", None)
    return getattr(definition, "name", "")


def _paste(*, title: str, pushed: str, node: Any, build: str, status: list[str]) -> None:
    """Print one run's evidence block, both verbs side by side."""
    print()
    print(f"=== T017 evidence: {title} ===")
    print(f"pushed tip: {pushed[:12]}")
    print(f"terminal_reason: {node.terminal_reason!r}")
    print(f"housekeeping_report: {node.housekeeping_report!r}")
    print("--- ergane build status ---")
    print(build)
    print("--- ergane status (node table) ---")
    print("\n".join(status))
    agreed = [l for l in status if l.startswith(NODE_126)] == [
        l for l in build.splitlines() if l.startswith(NODE_126)
    ]
    print(f"--- node lines byte-identical between the verbs: {agreed}")


async def _rendered(status: Any, epic_id: str) -> tuple[Any, str, list[str]]:
    """Both verbs' renderings of one answer, and the answer's own node."""
    document = as_json_document(status)
    build_status = render_status(epic_id, document, "COMPLETED")
    status_lines = status_verb_lines(document, "COMPLETED", epic_id=epic_id)
    return status.nodes[NODE_126], build_status, status_lines


# ============================================================================
# T017 — the pasted evidence: both verbs, one killed node, side by side
# ============================================================================


async def test_both_verbs_render_one_killed_node_with_a_report(
    env: WorkflowEnvironment, repo: Repo
) -> None:
    """A ladder kill: the report token alone, on both verbs' identical node line.

    The node pushed its branch, exhausted its ladder, and was killed; the real
    archive activity tidied up after it and reported. No cause exists — the
    KILL press is the ending the operator chose — so the line must carry the
    housekeeping token and no reason.
    """
    repo.dispatch("1")
    pushed = push_branch(repo.repo, EPIC_126, NODE_126, factory_root=repo.factory_root)
    assert repo.remote_tip() == pushed

    script = RealArchiveWorld(
        {NODE_126: ladder_fails()},
        client=env.client,
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(env, script, graph=graph_126(repo.repo))

    assert status.epic_state == EpicState.COMPLETED
    assert states(status)[NODE_126] == NodeState.KILLED

    node, build_status, status_lines = await _rendered(status, EPIC_126)
    line = node_line(build_status, NODE_126)

    # Report only: no cause may be invented for a kill the operator pressed.
    assert node.housekeeping_report is not None
    assert node.terminal_reason is None
    assert "  housekeeping: " in line
    assert "  reason: " not in line

    # The two verbs agree character for character on the node's line — the part
    # FR-006 scopes. (The dial blocks above the nodes legitimately differ:
    # `ergane status`'s EpicView carries only the nodes, so those degrade to
    # `unavailable` on that surface. That is pre-existing behaviour, not drift.)
    status_node_lines = [l for l in status_lines if l.startswith(NODE_126)]
    assert status_node_lines == [line], (
        f"the two verbs disagree about the node:\n"
        f"  build status: {line!r}\n"
        f"  ergane status: {status_node_lines!r}"
    )

    _paste(
        title="a ladder kill — the report token alone, both verbs agreeing",
        pushed=pushed,
        node=node,
        build=build_status,
        status=status_lines,
    )


async def test_both_verbs_render_one_push_refused_and_killed_node(
    env: WorkflowEnvironment, repo: Repo
) -> None:
    """The four-hour case: git's refusal as the cause, the archive beside it.

    The landing's push is refused non-fast-forward, the operator presses KILL,
    and the node ends with both facts on its record. Both tokens must appear —
    the cause under `reason:`, the report under `housekeeping:`, neither shown
    as the other — and both verbs must print the same line.
    """
    worktree = repo.dispatch("1")
    pushed = push_branch(repo.repo, EPIC_126, NODE_126, factory_root=repo.factory_root)
    assert repo.remote_tip() == pushed

    # The refusal epic 100's fixture builds: a real push, refused by a real
    # remote, rebuilt on a sibling commit so the two share no ancestry. Here the
    # rebuild happens in the same worktree `repo.dispatch` prepared, which is
    # the ancestry relationship that killed the node.
    from tests.test_100_push_reports_refusal import _rebuild_on_a_sibling_commit
    from tests.target_repo import git_env
    import subprocess

    _rebuild_on_a_sibling_commit(worktree)
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo.repo),
            "push",
            "--quiet",
            "origin",
            "factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2",
        ],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    assert completed.returncode != 0, "the fixture did not produce a refused push"
    from factory.workgraph.worktree import WorktreeError as _WE

    script = RefusedPushRealArchiveWorld(
        {NODE_126: [passing()]},
        client=env.client,
        error=_WE(_rejection_line(completed.stderr)),
        press=EscalationChoice.KILL.value,
    )
    rejection = _rejection_line(completed.stderr)

    status = await run_epic(env, script, graph=graph_126(repo.repo))

    assert states(status)[NODE_126] == NodeState.KILLED

    node, build_status, status_lines = await _rendered(status, EPIC_126)
    line = node_line(build_status, NODE_126)

    # Both facts are on the record, and neither is the other.
    assert node.terminal_reason is not None, (
        "the refusal never reached the record as the cause"
    )
    assert flat(rejection) in flat(node.terminal_reason)
    assert node.housekeeping_report is not None

    # Both facts are on the line, in order, under their own labels.
    assert "  reason: " in line
    assert "  housekeeping: " in line
    assert line.index("  reason: ") < line.index("  housekeeping: ")
    assert flat(rejection) in flat(line)

    # And the two verbs agree on that line byte for byte.
    status_node_lines = [l for l in status_lines if l.startswith(NODE_126)]
    assert status_node_lines == [line], (
        f"the two verbs disagree about the node:\n"
        f"  build status: {line!r}\n"
        f"  ergane status: {status_node_lines!r}"
    )

    _paste(
        title="a push-refusal kill — both tokens on one line, both verbs agreeing",
        pushed=pushed,
        node=node,
        build=build_status,
        status=status_lines,
    )


# --- the wire and line helpers live in the module this story owns -------------

# ============================================================================
# Pasted evidence (constitution VIII, D-037) — the run above, output as printed.
# Generated by `uv run pytest tests/test_127_us2_evidence.py -q -s`; the lines
# below are that run's stdout, trimmed of nothing.
# ============================================================================
#
# === T017 evidence: a ladder kill — the report token alone, both verbs agreeing ===
# pushed tip: 362fbf6e8cb2
# terminal_reason: None
# housekeeping_report: 'archived branch; deleted origin branch factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 at 362fbf6e8cb2 (kept as refs/heads/archive/factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2/362fbf6e8cb2, here and on origin)'
# --- ergane build status ---
# epic 126-a-killed-node-leaves-no-ref-to-collide-with  COMPLETED  execution COMPLETED
# ladder dials
#   max_attempts       3
#   max_judge_retries  2
#   debugger_cycles    1
# landing dials
#   --merge-method             squash  default
#   --landing-poll-interval-s      60  default
#   --stall-after-s              7200  default
#   --max-recovery-cycles           1  default
#   --max-free-rebases              3  default
# us2  KILLED  attempt 4  factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2  persona debugger  model ollama-cloud/glm-5.3  base 999999999999  landing head unavailable  housekeeping: archived branch; deleted origin branch factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 at 362fbf6e8cb2 (kept as refs/heads/archive/factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2/362fbf6e8cb2, here and on origin)
# --- ergane status (node table) ---
# epic 126-a-killed-node-leaves-no-ref-to-collide-with  COMPLETED  execution COMPLETED
# ladder dials  unavailable
# landing dials  unavailable
# us2  KILLED  attempt 4  factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2  persona debugger  model ollama-cloud/glm-5.3  base 999999999999  landing head unavailable  housekeeping: archived branch; deleted origin branch factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 at 362fbf6e8cb2 (kept as refs/heads/archive/factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2/362fbf6e8cb2, here and on origin)
# --- node lines byte-identical between the verbs: True
#
# === T017 evidence: a push-refusal kill — both tokens on one line, both verbs agreeing ===
# pushed tip: 362fbf6e8cb2
# terminal_reason: 'WorktreeError: ! [rejected]        factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 -> factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 (non-fast-forward)'
# housekeeping_report: 'archived branch; kept origin branch factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 at 362fbf6e8cb2: no archive ref of this node holds that commit, so nothing else carries its content (FR-002)'
# --- ergane build status ---
# epic 126-a-killed-node-leaves-no-ref-to-collide-with  COMPLETED  execution COMPLETED
# ladder dials
#   max_attempts       3
#   max_judge_retries  2
#   debugger_cycles    1
# landing dials
#   --merge-method             squash  default
#   --landing-poll-interval-s      60  default
#   --stall-after-s              7200  default
#   --max-recovery-cycles           1  default
#   --max-free-rebases              3  default
# us2  KILLED  attempt 1  factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2  persona implementer  model implementer-alias  base 999999999999  landing head unavailable  reason: WorktreeError: ! [rejected] factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 -> factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 (non-fast-forward)  housekeeping: archived branch; kept origin branch factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 at 362fbf6e8cb2: no archive ref of this node holds that commit, so nothing else carries its content (FR-002)
# --- ergane status (node table) ---
# epic 126-a-killed-node-leaves-no-ref-to-collide-with  COMPLETED  execution COMPLETED
# ladder dials  unavailable
# landing dials  unavailable
# us2  KILLED  attempt 1  factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2  persona implementer  model implementer-alias  base 999999999999  landing head unavailable  reason: WorktreeError: ! [rejected] factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 -> factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 (non-fast-forward)  housekeeping: archived branch; kept origin branch factory/126-a-killed-node-leaves-no-ref-to-collide-with/us2 at 362fbf6e8cb2: no archive ref of this node holds that commit, so nothing else carries its content (FR-002)
# --- node lines byte-identical between the verbs: True
