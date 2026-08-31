"""The stored attempt says what the judge was shown, and what it contradicted.

116-US3. US1 put the factory's own gate measurements into the judge's prompt and
US2 stopped charging the node for a verdict that contradicts one of them. Both
changes are invisible from the outside: two rows written a fortnight apart, one
judged blind and one judged with the measurements in hand, read identically —
and a PASS composed over a judge that returned FAIL reads, on the row alone, as
a composer that ignored its judge.

So two facts go onto the record, and the second one onto the reading:

- **Whether the judge was shown the gate results** (FR-008). Carried from the
  assembled prompt onto the verdict, which is exactly the route
  `truncated_input` already takes — the prompt is the only thing that knows,
  and it knows at assembly time.
- **What the judge contradicted** (US2's `GateContradiction`), persisted rather
  than composed and dropped, and rendered by `ergane build attempts` so an
  operator sees it without opening `sqlite3` (US3-S3).

Plan trap 8 is the whole shape of the first one: *silence must be a statement*.
A row that carried the field only when the answer was yes would be, when the
answer was no, byte-identical to a row written before this spec existed — so the
field is written in both cases, `false` spelled out, and a test reads the stored
JSON rather than the decoded dataclass to prove it. The decoded value cannot
tell the two apart; only the text in the column can.

The one thing genuinely absent, and the only thing read as absent, is the
pre-116 row: no prompt assembled before US1 had a parameter to carry gate
results through, so `false` there is a fact about the code that wrote it rather
than a guess about the run.
"""

from __future__ import annotations

import io
import json
import sqlite3
import sys
from pathlib import Path
from typing import Iterator, NamedTuple, Sequence

import pytest

from factory.cli import main as main_module
from factory.env import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
)
from factory.verify.judge import build_prompt, run_judge
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    Requirement,
    RequirementKind,
    Scenario,
    VerificationForm,
    compose_result,
)
from factory.verify.store import connect, node_history, upsert_result

from tests.judge_proxy import JUDGE_MODEL_ALIAS, FakeJudgeProxy

EPIC_ID = "116-the-judge-scores-against-what-the-factory-measured"


# --- what the node was dispatched against ------------------------------------


FIRST = Scenario(
    scenario_id="US3-S1",
    steps=[
        "**Given** an attempt judged with gate results in the prompt",
        "**When** its row is written",
        "**Then** the row records that they were included",
    ],
    raw_text="US3-S1: **Then** the row records that they were included",
)

CRITERIA = CriteriaSet(
    feature=EPIC_ID,
    spec_ref="the-record-says-what-the-judge-was-shown/us3",
    requirements=[
        Requirement(
            key="US3",
            kind=RequirementKind.STORY,
            title="The record says what the judge was shown",
            priority="P2",
            body=(
                "As an operator, I can tell from the stored attempt whether the "
                "judge scored it with the gate results in hand."
            ),
            scenarios=[FIRST],
        )
    ],
    source_path=f"specs/{EPIC_ID}/spec.md",
    source_sha256="e3b0c442" + "0" * 56,
    snapshotted_at="2026-08-31T09:00:00Z",
)

DIFF = (
    "diff --git a/factory/verify/store.py b/factory/verify/store.py\n"
    "--- a/factory/verify/store.py\n"
    "+++ b/factory/verify/store.py\n"
    "@@ -540,0 +541,1 @@ _RESULT_COLUMNS = (\n"
    '+    "gate_contradictions",\n'
)


# --- what the factory measured ------------------------------------------------


def gate(name: str, status: GateStatus = GateStatus.PASS) -> GateResult:
    """One recorded gate. PASS by default, because that is the judged path."""
    return GateResult(
        name=name,
        command=f"uv run {name}",
        status=status,
        exit_code=0 if status is GateStatus.PASS else 1,
        duration_s=0.4,
        output_tail="12 passed in 0.14s" if status is GateStatus.PASS else "1 failed",
    )


GREEN = [gate("test")]

PROVED_OUTPUT = OutputCheck(
    write_scope="worktree",
    has_diff=True,
    expected_artifacts=[],
    artifacts_present=None,
    passed=True,
)

#: The assertion the deadlock was built from, in the judge's own voice.
CONTRADICTION = "The test gate would fail, because the font file is not in the diff."


def response(*findings: tuple[str, bool, str], verdict_word: str = "pass") -> str:
    """The JSON a judge returns, scored per scenario."""
    return json.dumps(
        {
            "verdict": verdict_word,
            "scenarios": [
                {"scenario": name, "pass": passed, "reasoning": reasoning}
                for name, passed, reasoning in findings
            ],
            "feedback": "; ".join(reasoning for _, _, reasoning in findings),
        }
    )


AGREED = response(("US3-S1", True, "the row carries the field in both cases"))


async def judged(
    *, gate_results: Sequence[GateResult] | None, reply: str = AGREED
) -> JudgeVerdict:
    """One real `run_judge` call against the scripted proxy."""
    proxy = FakeJudgeProxy()
    proxy.reply(reply)
    return await run_judge(
        CRITERIA,
        DIFF,
        proxy_url=proxy.base_url,
        virtual_key=proxy.virtual_key,
        model_alias=JUDGE_MODEL_ALIAS,
        gate_results=None if gate_results is None else list(gate_results),
        transport=proxy.transport,
        retry_backoff_s=0.0,
    )


def composed(
    judge: JudgeVerdict | None,
    *,
    node_id: str = "us3",
    gate_results: Sequence[GateResult] = GREEN,
):
    """Compose one attempt's evidence, with everything but the judge held green."""
    return compose_result(
        epic_id=EPIC_ID,
        node_id=node_id,
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=list(gate_results),
        output_check=PROVED_OUTPUT,
        judge=judge,
        criteria_sha256=CRITERIA.source_sha256,
        spec_ref=CRITERIA.spec_ref,
        started_at="2026-08-31T09:00:00Z",
        finished_at="2026-08-31T09:04:00Z",
    )


@pytest.fixture
def store(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "verification.db")
    yield conn
    conn.close()


def stored_judge_json(conn: sqlite3.Connection, node_id: str) -> str:
    """The `judge_verdict` column as text — what `sqlite3` would print.

    Read raw rather than through `node_history`, because the claim under test is
    about what the column *says*: a decoded dataclass answers `False` whether the
    key was written or defaulted, and telling those apart is the whole of trap 8.
    """
    row = conn.execute(
        "SELECT judge_verdict FROM verification_results WHERE node_id = ?",
        (node_id,),
    ).fetchone()
    assert row is not None, f"no row was written for {node_id!r}"
    return row[0]


# --- T021 / US3-S1: judged with the gate results, and the row says so ---------


async def test_an_attempt_judged_with_gate_results_records_that_they_were_included() -> None:
    """US3-S1, FR-008. The fact travels the route `truncated_input` already takes.

    Measured through a real `run_judge` rather than by constructing a verdict:
    the question is whether the *assembler* tells the verdict what it put in the
    prompt, and a hand-built `JudgeVerdict` would answer a question nobody asked.
    The prompt is cross-examined in the same test, so a `gates_shown` that was
    set from the argument rather than from the assembled section — and would
    therefore keep claiming the section exists the day `_gate_blocks` stops
    emitting one — fails here.
    """
    scored = await judged(gate_results=GREEN)

    assert scored.gates_shown is True, (
        "the judge was shown the factory's measurements and the verdict does "
        "not record it, so the row cannot either"
    )
    prompt = build_prompt(CRITERIA, DIFF, gate_results=GREEN)
    assert prompt.gates_shown is True
    assert "test" in prompt.messages[1]["content"]


async def test_the_row_carries_what_the_judge_was_shown(
    store: sqlite3.Connection,
) -> None:
    """US3-S1. Through the store, because the row is what outlives the run."""
    upsert_result(store, composed(await judged(gate_results=GREEN)))

    (read_back,) = node_history(store, EPIC_ID, "us3")

    assert read_back.judge is not None
    assert read_back.judge.gates_shown is True
    assert '"gates_shown": true' in stored_judge_json(store, "us3")


# --- T022 / US3-S2, trap 8: absence is written down, not left silent ----------


async def test_an_attempt_judged_without_gate_results_records_their_absence() -> None:
    """US3-S2, plan trap 8. Silence is not a statement.

    The assertion is on the stored *text*, not on the decoded record. A field
    written only when the answer is yes decodes to `False` in both the "judged
    blind" case and the "written before this spec existed" case, and the reading
    that distinguishes them is the one an operator has: `sqlite3` on the column.
    """
    scored = await judged(gate_results=None)

    assert scored.gates_shown is False


async def test_the_absence_is_spelled_out_in_the_stored_row(
    store: sqlite3.Connection,
) -> None:
    """US3-S2, trap 8. The column says `false`; it does not say nothing."""
    upsert_result(store, composed(await judged(gate_results=None)))

    stored = stored_judge_json(store, "us3")

    assert "gates_shown" in stored, (
        "a row judged without the gate results omitted the field, which makes "
        "it indistinguishable from every row written before this spec"
    )
    assert '"gates_shown": false' in stored
    (read_back,) = node_history(store, EPIC_ID, "us3")
    assert read_back.judge is not None
    assert read_back.judge.gates_shown is False


def test_a_row_written_before_this_spec_still_reads_back(
    store: sqlite3.Connection,
) -> None:
    """FR-008 is additive. A stored verdict with no such key is not a crash.

    Every row in the live store was written by a codec that had no field to
    write, so the reader must accept its absence. It reads as `False` — which is
    a fact about the writer rather than a guess about the run, because no prompt
    assembled before US1 had a parameter to carry gate results through.
    """
    upsert_result(store, composed(_verdict()))
    legacy = json.loads(stored_judge_json(store, "us3"))
    legacy.pop("gates_shown", None)
    store.execute(
        "UPDATE verification_results SET judge_verdict = ? WHERE node_id = ?",
        (json.dumps(legacy), "us3"),
    )
    store.commit()

    (read_back,) = node_history(store, EPIC_ID, "us3")

    assert read_back.judge is not None
    assert read_back.judge.gates_shown is False


def _verdict(
    *findings: JudgeScenarioFinding,
    outcome: JudgeOutcome = JudgeOutcome.PASS,
    gates_shown: bool = True,
) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=outcome,
        findings=list(findings)
        or [JudgeScenarioFinding(scenario="US3-S1", passed=True, reasoning="ok")],
        feedback="",
        judge_attempt=1,
        truncated_input=False,
        model_alias=JUDGE_MODEL_ALIAS,
        gates_shown=gates_shown,
    )


# --- T024 / FR-008: both facts survive a store round trip ---------------------


def test_both_facts_survive_a_store_round_trip(store: sqlite3.Connection) -> None:
    """FR-008. A record that round-trips *almost* everything is the defect.

    The two facts this story adds travel on different carriers — one inside the
    judge verdict's JSON, one on the row itself — so a codec that learned about
    only one of them would still pass a test that checked only the other. Both
    are asserted against the same read, and the contradiction is compared field
    by field rather than by "there is one", because a codec that dropped
    `recorded_status` would satisfy a count.
    """
    contradicting = _verdict(
        JudgeScenarioFinding(scenario="US3-S1", passed=False, reasoning=CONTRADICTION),
        outcome=JudgeOutcome.FAIL,
    )
    result = composed(contradicting)
    assert result.gate_contradictions, "US2 composes the contradiction being stored"

    upsert_result(store, result)
    (read_back,) = node_history(store, EPIC_ID, "us3")

    assert read_back.judge is not None
    assert read_back.judge.gates_shown is True
    assert read_back.gate_contradictions == result.gate_contradictions
    recorded = read_back.gate_contradictions[0]
    assert recorded.gate == "test"
    assert recorded.scenario == "US3-S1"
    assert recorded.recorded_status is GateStatus.PASS
    assert "would fail" in recorded.claim


def test_an_attempt_that_contradicted_nothing_round_trips_as_empty(
    store: sqlite3.Connection,
) -> None:
    """The control. Empty is the ordinary case and must not become a false one."""
    upsert_result(store, composed(_verdict(), node_id="us1"))

    (read_back,) = node_history(store, EPIC_ID, "us1")

    assert read_back.gate_contradictions == ()


def test_a_row_written_before_the_column_existed_reads_as_no_contradictions(
    store: sqlite3.Connection,
) -> None:
    """Additive, and NULL is what a pre-116 row carries in the new column."""
    upsert_result(store, composed(_verdict(), node_id="us1"))
    store.execute(
        "UPDATE verification_results SET gate_contradictions = NULL WHERE node_id = ?",
        ("us1",),
    )
    store.commit()

    (read_back,) = node_history(store, EPIC_ID, "us1")

    assert read_back.gate_contradictions == ()


# --- T023 / US3-S3: the contradiction is visible through the CLI --------------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def invoke(*argv: str) -> Run:
    """Drive the real CLI entry point, capturing what an operator would see."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


@pytest.fixture
def seeded_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One epic, two PASSes: one composed over a contradiction, one not.

    The clean PASS is the control. A reading that printed the contradiction and
    nothing else would look right on one row and tell an operator nothing,
    because the question they arrive with is which of two green rows to trust.
    """
    path = tmp_path / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(path))

    conn = connect(path)
    contradicting = _verdict(
        JudgeScenarioFinding(scenario="US3-S1", passed=False, reasoning=CONTRADICTION),
        outcome=JudgeOutcome.FAIL,
    )
    upsert_result(conn, composed(contradicting, node_id="us2"))
    upsert_result(conn, composed(_verdict(), node_id="us1"))
    conn.close()
    return path


def node_lines(stdout: str, node_id: str) -> str:
    """The printed line for a node and everything indented under it."""
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(f"{node_id} "):
            continue
        block = [line]
        for following in lines[index + 1 :]:
            if not following.startswith(" "):
                break
            block.append(following)
        return "\n".join(block)
    raise AssertionError(f"no line for {node_id!r} in:\n{stdout}")


def test_the_cli_shows_a_recorded_contradiction(seeded_store: Path) -> None:
    """US3-S3. Visible without reading the store, which is the whole ask.

    A PASS composed over a judge that returned FAIL is the shape that needs
    explaining, and the row is the only place the explanation lives. The reading
    names the gate, the scenario the finding was neutralised on, and the status
    that was measured — the three things an operator deciding whether the judge
    persona needs re-routing has to have.
    """
    run = invoke("build", "attempts", EPIC_ID)

    assert run.code == 0, run.stderr
    shown = node_lines(run.stdout, "us2")
    assert "contradict" in shown.lower(), (
        "a PASS composed over a FAIL verdict reads, without this, as a composer "
        "that ignored its judge"
    )
    assert "US3-S1" in shown
    assert "test" in shown
    assert GateStatus.PASS.value in shown
    assert OverallVerdict.PASS.value in shown


def test_an_attempt_that_contradicted_nothing_says_nothing(
    seeded_store: Path,
) -> None:
    """The control: the ordinary row is unchanged, and stays one line."""
    run = invoke("build", "attempts", EPIC_ID)

    assert run.code == 0, run.stderr
    assert "contradict" not in node_lines(run.stdout, "us1").lower()


def test_the_claim_is_quoted_rather_than_summarised(seeded_store: Path) -> None:
    """The judge's own words, because a disagreement nobody can read is a rumour.

    `GateContradiction.claim` exists so the record does not send its reader back
    to the reasoning to find out what was disagreed with; a reading that dropped
    it would put them right back there.
    """
    run = invoke("build", "attempts", EPIC_ID)

    assert "would fail" in node_lines(run.stdout, "us2")
