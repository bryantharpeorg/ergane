"""110-US2: the demo dispatches, narrates, and halts (T009-T012).

Every test here drives the driver's dispatch and watch phases against a scripted
CLI seam: a callable that records the argv it is handed and plays back prepared
`build status` documents.  Nothing in this file starts a Temporal server, a
worker, a gateway or a dispatch, and nothing spends anything (plan T8).

Two things the seam does *not* fake, on purpose:

- the status documents are rendered by the CLI's own `render_status`, so the
  text this file asserts is passed through verbatim is the text `ergane build
  status` actually prints, halting-mode statement included;
- the halting statement is quoted here in full, and pinned to
  `factory/cli/nouns/build.py:_LANDING_NOT_ATTEMPTED`, so a driver that
  paraphrases it fails rather than passing on a substring.

## Evidence (T014)

The scripted narration of T010, as the driver printed it (states PENDING →
RUNNING → VERIFYING → PASSED, then the terminal render), captured from the test
run itself:

    ergane demo: dispatching: ergane build ship <repo>/specs/001-demo --target-repo <repo> --yes --halt-after-pass
    ship: compiled graph '001-demo' has 1 node(s)
    dispatch order: US1
    001-demo-US1
    ergane demo: US1  PENDING
    ergane demo: US1  PENDING -> RUNNING
    ergane demo: US1  RUNNING -> VERIFYING
    ergane demo: US1  VERIFYING -> PASSED
    epic 001-demo  COMPLETED  execution COMPLETED
    landing dials  unavailable

    landing not attempted: the epic was dispatched with --halt-after-pass; to land, start the epic without that flag and ensure the target repo has a forge configured
    US1  PASSED  attempt 1  factory/001-demo/US1

The last block is `render_status`'s own output, printed by the driver unchanged;
the blank line before the statement is the CLI's, not the driver's.

Full suite on this tree with this file ignored: 5006 passed, 57 skipped in 337.65s.
Full suite on this tree with this file:         5015 passed, 57 skipped in 338.41s.
The delta is this file's nine tests and nothing else.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from factory.cli.nouns.build import _LANDING_NOT_ATTEMPTED, render_status


#: The halting-mode statement, quoted rather than imported into the assertions.
#: A driver that rewords it fails; the equality below proves the quote is the
#: CLI's own words rather than this file's paraphrase of them.
HALT_STATEMENT = (
    "landing not attempted: the epic was dispatched with --halt-after-pass; "
    "to land, start the epic without that flag and ensure the target repo has "
    "a forge configured"
)


def test_the_quoted_halt_statement_is_the_cli_s_own_words() -> None:
    """The pin behind every verbatim assertion in this file."""
    assert HALT_STATEMENT == _LANDING_NOT_ATTEMPTED


# -----------------------------------------------------------------------------
# fixtures and helpers
# -----------------------------------------------------------------------------


@pytest.fixture
def driver_mod():
    """Import the demo driver; tests fail cleanly until the phase exists."""
    from factory.supervision import demo_driver

    return demo_driver


EPIC_ID = "001-demo"
NODE_ID = "US1"

#: What `build ship` prints on the happy path, trimmed to its shape.  The seam
#: hands this back as the verb's stdout so the driver's pass-through is visible.
SHIP_TRANSCRIPT = (
    f"ship: compiled graph '{EPIC_ID}' has 1 node(s)\n"
    f"dispatch order: {NODE_ID}\n"
    f"{EPIC_ID}-{NODE_ID}\n"
)


def status_document(
    state: str,
    *,
    epic_state: str = "RUNNING",
    halt_after_pass: bool = True,
    terminal_reason: str | None = None,
) -> dict[str, Any]:
    """One `build status --json` answer for the demo's single-node graph."""
    node: dict[str, Any] = {
        "state": state,
        "attempt": 1,
        "branch": f"factory/{EPIC_ID}/{NODE_ID}",
    }
    if terminal_reason is not None:
        node["terminal_reason"] = terminal_reason
    return {
        "epic_state": epic_state,
        "halt_after_pass": halt_after_pass,
        "execution_status": epic_state,
        "nodes": {NODE_ID: node},
    }


def human_render(document: Mapping[str, Any]) -> str:
    """The render the CLI would print for that document, from the CLI's code."""
    return render_status(EPIC_ID, document, str(document["execution_status"]))


class ScriptedCli:
    """A stand-in for the captured CLI seam that plays a scripted sequence.

    `build status --json` walks the prepared documents, one per call, holding on
    the last one; `build status` renders whichever document was last served, the
    way the real CLI would answer a second query a moment later.  Any other verb
    is a test failure rather than a silent zero: US2's whole first scenario is
    that no validate/derive/start invocation exists in this phase.
    """

    def __init__(
        self,
        driver_mod,
        *,
        documents: Sequence[Mapping[str, Any]] = (),
        ship_status: int = 0,
        ship_stdout: str = SHIP_TRANSCRIPT,
        ship_stderr: str = "",
    ) -> None:
        self._driver_mod = driver_mod
        self._documents = list(documents)
        self._index = 0
        self._ship = driver_mod.CliRun(
            status=ship_status, stdout=ship_stdout, stderr=ship_stderr
        )
        self.calls: list[list[str]] = []

    @property
    def served(self) -> Mapping[str, Any]:
        return self._documents[min(self._index, len(self._documents)) - 1]

    def __call__(self, argv: Sequence[str]):
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == ["build", "ship"]:
            return self._ship
        if argv[:2] == ["build", "status"]:
            if "--json" in argv:
                document = self._documents[min(self._index, len(self._documents) - 1)]
                self._index = min(self._index + 1, len(self._documents))
                return self._driver_mod.CliRun(
                    status=0, stdout=json.dumps(document, indent=2), stderr=""
                )
            return self._driver_mod.CliRun(
                status=0, stdout=human_render(self.served) + "\n", stderr=""
            )
        raise AssertionError(f"the dispatch phase ran an unexpected verb: {argv}")


def dispatch(driver_mod, cli: ScriptedCli, tmp_path: Path) -> int:
    """Run the whole dispatch phase against the scripted seam, without sleeping."""
    return driver_mod.run_dispatch_phase(
        state_home=tmp_path / "state",
        repo_root=tmp_path / "repo",
        run_cli_captured=cli,
        sleep=lambda _seconds: None,
    )


def watch(driver_mod, cli: ScriptedCli) -> int:
    """Run the watch phase alone, so its output is the whole of the assertion."""
    return driver_mod.run_watch_phase(
        epic_id=EPIC_ID,
        run_cli_captured=cli,
        sleep=lambda _seconds: None,
    )


def transition(state: str, previous: str | None = None) -> str:
    """The narration line the driver prints when it first observes `state`."""
    body = state if previous is None else f"{previous} -> {state}"
    return f"ergane demo: {NODE_ID}  {body}"


# -----------------------------------------------------------------------------
# T009 [US2-S1, FR-007] one verb, and nothing that reimplements it
# -----------------------------------------------------------------------------


def test_the_dispatch_is_exactly_one_ship_verb_with_yes_and_halt(
    driver_mod, tmp_path: Path, capsys
) -> None:
    """`build ship <spec-dir> --target-repo <repo> --yes --halt-after-pass`.

    The spec directory is absolute because the driver's working directory is
    the supervisor's and is nobody's declaration (constitution IX); it still
    ends in `specs/001-demo`, which is what the scenario names.
    """
    cli = ScriptedCli(
        driver_mod,
        documents=[status_document("PASSED", epic_state="COMPLETED")],
    )

    status = dispatch(driver_mod, cli, tmp_path)
    capsys.readouterr()

    assert status == 0
    repo = tmp_path / "repo"
    ship_calls = [call for call in cli.calls if call[:2] == ["build", "ship"]]
    assert ship_calls == [
        [
            "build",
            "ship",
            str(repo / "specs" / EPIC_ID),
            "--target-repo",
            str(repo),
            "--yes",
            "--halt-after-pass",
        ]
    ], cli.calls
    assert ship_calls[0][2].endswith(f"specs/{EPIC_ID}")

    # No reimplemented chain: every other invocation is a status read.
    others = [call for call in cli.calls if call[:2] != ["build", "ship"]]
    assert all(call[:2] == ["build", "status"] for call in others), cli.calls
    for forbidden in (["spec", "validate"], ["spec", "derive"], ["build", "start"]):
        assert not any(call[:2] == forbidden for call in cli.calls), forbidden


def test_ship_argv_is_assembled_from_the_repo_it_is_given(driver_mod) -> None:
    """The argv is a pure function of the repository root — no ambient cwd."""
    argv = driver_mod.ship_argv(Path("/home/ergane/repo"))

    assert argv == [
        "build",
        "ship",
        f"/home/ergane/repo/specs/{EPIC_ID}",
        "--target-repo",
        "/home/ergane/repo",
        "--yes",
        "--halt-after-pass",
    ]


# -----------------------------------------------------------------------------
# T010 [US2-S2, FR-008] the narration, and the statement it closes on
# -----------------------------------------------------------------------------


def test_each_transition_is_printed_once_and_the_halt_statement_reaches_the_stream(
    driver_mod, tmp_path: Path, capsys
) -> None:
    """PENDING → RUNNING → VERIFYING → PASSED, then the render, verbatim.

    Each state is observed twice by the poll loop (the sequence repeats one
    document before advancing), so a driver that printed what it read rather
    than what changed would print eight transition lines instead of four.
    """
    sequence = ["PENDING", "PENDING", "RUNNING", "RUNNING", "VERIFYING", "VERIFYING"]
    documents = [status_document(state) for state in sequence]
    documents.append(status_document("PASSED", epic_state="COMPLETED"))
    cli = ScriptedCli(driver_mod, documents=documents)

    status = dispatch(driver_mod, cli, tmp_path)
    printed = capsys.readouterr().out
    lines = printed.splitlines()

    assert status == 0, printed

    expected = [
        transition("PENDING"),
        transition("RUNNING", "PENDING"),
        transition("VERIFYING", "RUNNING"),
        transition("PASSED", "VERIFYING"),
    ]
    for line in expected:
        assert lines.count(line) == 1, f"{line!r} appeared {lines.count(line)}x\n{printed}"

    # In the order they happened, and nothing else narrated between them.
    assert [line for line in lines if line.startswith(f"ergane demo: {NODE_ID}")] == expected

    # The terminal render, whole, and the statement inside it word for word.
    terminal = human_render(status_document("PASSED", epic_state="COMPLETED"))
    assert terminal in printed, printed
    assert HALT_STATEMENT in printed, printed
    assert HALT_STATEMENT in lines, "the statement was reflowed rather than passed through"


def test_a_passed_node_is_terminal_only_because_the_epic_is_halting(
    driver_mod, capsys
) -> None:
    """Without halting mode a PASSED node still owes a landing, so watching goes on.

    The same document with `halt_after_pass` false is not terminal: PASSED is
    made terminal by the dispatch, not by the state's name
    (`factory/workgraph/workflow.py:284-294`).
    """
    landing = status_document("PASSED", halt_after_pass=False)
    merged = status_document("MERGED", epic_state="COMPLETED", halt_after_pass=False)
    cli = ScriptedCli(driver_mod, documents=[landing, landing, merged])

    status = watch(driver_mod, cli)
    lines = capsys.readouterr().out.splitlines()

    assert status == 0
    assert [line for line in lines if line.startswith(f"ergane demo: {NODE_ID}")] == [
        transition("PASSED"),
        transition("MERGED", "PASSED"),
    ]


# -----------------------------------------------------------------------------
# T011 [US2-S3, FR-009] a refusal is the last word, and it is not retried
# -----------------------------------------------------------------------------


REFUSAL_STDOUT = (
    "preflight: alias: persona 'implementer' names model 'demo/implementer', "
    "which the proxy does not serve\n"
)
REFUSAL_STDERR = "ergane: preflight found 1 problem; nothing was dispatched\n"


def test_a_refused_dispatch_is_the_drivers_last_words_and_is_not_retried(
    driver_mod, tmp_path: Path, capsys
) -> None:
    """The refusal prints as given, the sentinel is down, the exit is nonzero.

    The sentinel is written *before* `build ship` runs (plan T4), which is why a
    refusal leaves it behind: a driver that wrote it after a success would
    re-spend the stranger's key on the next boot of a container that crashed
    between the dispatch and the record of it.
    """
    cli = ScriptedCli(
        driver_mod,
        ship_status=1,
        ship_stdout=REFUSAL_STDOUT,
        ship_stderr=REFUSAL_STDERR,
        documents=[status_document("PENDING")],
    )

    status = dispatch(driver_mod, cli, tmp_path)
    printed = capsys.readouterr().out

    assert status != 0
    assert REFUSAL_STDOUT.strip() in printed
    assert printed.strip().splitlines()[-1] == REFUSAL_STDERR.strip()

    # Nothing was watched: the phase stopped at the refusal.
    assert [call[:2] for call in cli.calls] == [["build", "ship"]], cli.calls

    sentinel = tmp_path / "state" / "demo" / driver_mod.DISPATCH_SENTINEL
    assert sentinel.is_file()

    # A second run spends nothing and says so in one line.
    second = ScriptedCli(driver_mod, documents=[status_document("PENDING")])
    again = dispatch(driver_mod, second, tmp_path)
    repeated = capsys.readouterr().out.strip()

    assert again == 0
    assert second.calls == []
    assert len(repeated.splitlines()) == 1, repeated
    assert "already" in repeated


def test_the_dispatch_phase_touches_no_supervisor(driver_mod) -> None:
    """FR-009's "without stopping the services": there is nothing to stop with.

    The driver holds no reference to the supervisor module, so a refusal cannot
    reach the supervised children even by accident — it is a subprocess that
    exits, and the supervisor only reaps it (110-US1, FR-001).
    """
    imported = [
        getattr(value, "__name__", "")
        for value in vars(driver_mod).values()
        if getattr(value, "__name__", "").startswith("factory.")
    ]
    assert not any(name.endswith("container_supervisor") for name in imported), imported


# -----------------------------------------------------------------------------
# T012 [US2-S4, FR-010] a failure is reported as the CLI states it
# -----------------------------------------------------------------------------


def test_a_failing_epic_is_reported_with_the_cli_s_own_render_and_nothing_added(
    driver_mod, capsys
) -> None:
    """The watch phase's whole output is the transitions plus the render.

    Asserted as an equality over every line printed, so a driver that offers a
    consolation, a diagnosis or a summary of the failure fails this test.  The
    mode changes where success stops, never what failure means (109 US3-S4).
    """
    failed = status_document(
        "FAILED",
        epic_state="COMPLETED",
        terminal_reason="gate test failed: exit 1",
    )
    documents = [
        status_document("PENDING"),
        status_document("RUNNING"),
        status_document("VERIFYING"),
        failed,
    ]
    cli = ScriptedCli(driver_mod, documents=documents)

    status = watch(driver_mod, cli)
    printed = capsys.readouterr().out

    assert status != 0, "a failed epic reported a successful watch"

    render = human_render(failed)
    assert render in printed, printed
    assert printed.splitlines() == [
        transition("PENDING"),
        transition("RUNNING", "PENDING"),
        transition("VERIFYING", "RUNNING"),
        transition("FAILED", "VERIFYING"),
        *render.splitlines(),
    ], printed


def test_an_unreadable_status_is_retried_and_then_refused(
    driver_mod, capsys
) -> None:
    """A `build status` that will not answer bounds the loop instead of hanging.

    The demo runs unattended in a stranger's terminal: a poll loop with no floor
    under it is a container that looks busy forever.
    """

    class MuteCli:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def __call__(self, argv: Sequence[str]):
            self.calls.append(list(argv))
            return driver_mod.CliRun(
                status=3,
                stdout="",
                stderr=f"ergane: cannot read epic '{EPIC_ID}': connection refused\n",
            )

    cli = MuteCli()
    status = driver_mod.run_watch_phase(
        epic_id=EPIC_ID, run_cli_captured=cli, sleep=lambda _seconds: None
    )
    printed = capsys.readouterr().out

    assert status != 0
    assert len(cli.calls) == driver_mod.MAX_CONSECUTIVE_POLL_FAILURES
    assert "connection refused" in printed
