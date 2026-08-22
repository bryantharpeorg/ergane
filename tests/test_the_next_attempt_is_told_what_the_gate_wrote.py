"""The next attempt is told which gate wrote what (084 US2, FR-007/FR-008).

US1 gave a gate that dirties the node worktree a status of its own,
`DIRTIED_WORKTREE`, and the paths it wrote on `GateResult.worktree_writes`. A
status and a tuple in the evidence store are not a fix on their own: the two
places a human or an agent actually reads are the retry prompt and the
escalation message, and until this story neither said a word about either.

That failure shape is measured, not feared. `033-ergane-install/us2` failed four
times on 2026-08-15 reading "No failing gate output and no judge feedback were
recorded" (`factory/workgraph/prompt.py:770-774`) — a byte-identical mystery,
four attempts deep. A gate that dirties the worktree is the same shape one door
further along: the gate exited 0, so its output tail says the suite was green,
and the paths that caused the refusal live only on a field nobody rendered.

So these tests are about attribution and about invention, not about a sentence:

- **The paths rendered are this gate's, and this attempt's.** Two gates in one
  attempt, each writing different paths, must render their own beside their own
  name; two attempts carrying different writes must not bleed into each other.
  A renderer that emits one honest-looking sentence per dirtied gate passes
  "the prompt mentions worktree writes" completely and fails every assertion
  here.
- **Nothing is invented.** US2-S2's control is byte parity: an attempt whose
  gates all passed cleanly renders exactly the bytes it rendered before this
  story, asserted against `EVIDENCE_SECTION_GOLDEN` — the same golden
  `tests/test_prompt_output_check.py` pins, from the same corpus. A green
  gate's output is noise in a prompt whose job is to say what went wrong
  (`factory/workgraph/prompt.py:701-703`), and that stays true.
- **A gate that failed *and* wrote reports both.** `_to_result` keeps the
  command's verdict as the headline and still records the writes
  (084 FR-005), so a renderer that only looks at `DIRTIED_WORKTREE` drops the
  paths for exactly the gate whose next attempt needs them most.

The operator's half is `factory/notify/messages.py:_gate_line`, and it exists
for the reason `concurrent_gates` is rendered there: a marker that lives only in
the evidence store is one the operator never sees. It shares a 4096-byte
message with every other attempt's evidence, so it names a bounded number of
paths and counts the rest — the discipline `_tail` already follows.

## The merge-queue PR body, decided rather than discovered

`factory/mergequeue/messages.py:130-141` `_gate_status` is the third renderer of
a `GateResult` and it takes no marker in this story, deliberately.
`render_pr_body` is documented as "the PR body for a passing node"
(`factory/mergequeue/messages.py:66`) and `gates_passed`
(`factory/verify/models.py:501-515`) refuses any status that is not `PASS`, so a
`DIRTIED_WORKTREE` gate cannot reach a landed PR at all. A marker there would be
unreachable code pretending to be coverage; `test_a_dirtied_gate_never_reaches_
a_landed_pr_body` pins the reasoning instead of the branch, so if that premise
ever stops holding this suite says so rather than the PR body going quietly
silent.
"""

from __future__ import annotations

from dataclasses import replace

from factory.notify.messages import GATE_WRITES_NAMED, _gate_line, render_history
from factory.usage.models import Termination
from factory.verify.models import GateResult, GateStatus, gates_passed
from factory.workgraph.prompt import AttemptEvidence
from tests.test_prompt import (
    ATTEMPT_ONE_TAIL,
    build,
    make_gate,
    make_judge,
    make_result,
    prior_two_attempts,
)
from tests.test_prompt_output_check import (
    EVIDENCE_SECTION_GOLDEN,
    NOTHING_FAILED_LOUDLY,
    evidence_section,
)
from tests.test_notify import make_gate as make_notify_gate
from tests.test_notify import make_result as make_notify_result

# --- planted evidence ---------------------------------------------------------
#
# Every path below is distinctive on purpose. An assertion that a *planted* path
# reached the prompt cannot be satisfied by a renderer inventing a plausible one.

#: The field report's shape: a `compileall` gate writing bytecode into a repo
#: whose ignore rules never mentioned `__pycache__/`.
COMPILED_PATHS = (
    "factory/PLANTED-WRITE-01/__pycache__/models.cpython-313.pyc",
    "factory/PLANTED-WRITE-02/__pycache__/gates.cpython-313.pyc",
)

#: The severe shape: a gate rewriting a source file the agent had already
#: modified, which `git status --porcelain` reports byte-identically either way.
REWRITTEN_PATH = "factory/verify/PLANTED-REWRITE-03/formatted.py"

#: A second gate's writes in the same attempt, so misattribution is observable.
OTHER_GATE_PATH = "docs/PLANTED-OTHER-GATE-04/generated.md"

#: A second attempt's writes, so cross-attempt bleed is observable.
LATER_ATTEMPT_PATH = "tests/PLANTED-LATER-ATTEMPT-05/fixture.json"

COMPILEALL_COMMAND = "uv run python -m compileall factory"


def dirtied_gate(**overrides: object) -> GateResult:
    """A gate that exited 0 and changed the worktree — US1's demotion."""
    fields: dict[str, object] = {
        "name": "compile",
        "command": COMPILEALL_COMMAND,
        "status": GateStatus.DIRTIED_WORKTREE,
        "exit_code": 0,
        "output_tail": "Listing 'factory'...\n",
        "worktree_writes": COMPILED_PATHS,
    }
    fields.update(overrides)
    return make_gate(**fields)


def attempt(
    *gates: GateResult,
    number: int = 1,
    judge: object = None,
    termination: Termination = Termination.COMPLETED,
) -> AttemptEvidence:
    """One prior attempt whose verification produced `gates`."""
    return AttemptEvidence(
        termination=termination,
        result=make_result(number, list(gates), judge),  # type: ignore[arg-type]
    )


# --- US2-S1 / FR-007: the prompt names the gate, its command and its paths -----


def test_the_retry_prompt_names_the_gate_its_command_and_every_path_it_wrote() -> None:
    """US2-S1: quoted rather than described, or the next attempt guesses.

    The gate exited 0 and its tail says so, so nothing else in this block hints
    that anything went wrong. The name says which gate to fix, the command says
    what to fix about it, and the paths say what it did — all three, or the
    agent is reading a green log under a red verdict.
    """
    section = evidence_section(attempt(dirtied_gate()))

    assert "compile" in section
    assert COMPILEALL_COMMAND in section
    for path in COMPILED_PATHS:
        assert path in section, path

    # The status is the reason the gate is reachable here at all (trap 7): the
    # block `continue`s past every PASS gate, so a marker on a PASS row would be
    # invisible exactly when it matters.
    assert GateStatus.DIRTIED_WORKTREE.value in section

    # The sentence the four `033-ergane-install/us2` attempts were shown.
    assert NOTHING_FAILED_LOUDLY not in section


def test_the_paths_are_quoted_verbatim_not_summarised() -> None:
    """FR-007's "quoted rather than described".

    A count is a description; a path is an instruction. The paths render inside
    a fence, on their own lines, so the agent can read them the way it reads a
    gate tail — and so a renderer that says "2 paths were written" fails.
    """
    section = evidence_section(attempt(dirtied_gate()))

    for path in COMPILED_PATHS:
        assert f"\n{path}\n" in section, path

    # Inside a fence, not loose in a sentence: an odd number of fence markers
    # precede the path, so a fence is open where it renders.
    before = section[: section.index(COMPILED_PATHS[0])]
    assert before.count("```") % 2 == 1, before.count("```")


def test_each_gate_renders_its_own_writes_and_no_other_s() -> None:
    """Attribution: two dirtied gates in one attempt, each with its own paths.

    This is the property a hardcoded block cannot have. `worktree_writes` is
    attributed to a gate by the name it was declared under (084 FR-003) — the
    whole point of attributing it — and a renderer that pooled the attempt's
    writes into one list would send the next attempt to fix the wrong command.
    """
    section = evidence_section(
        attempt(
            dirtied_gate(),
            dirtied_gate(
                name="docs",
                command="uv run mkdocs build",
                worktree_writes=(OTHER_GATE_PATH,),
            ),
        )
    )

    compile_at = section.index(COMPILEALL_COMMAND)
    docs_at = section.index("uv run mkdocs build")
    assert compile_at < docs_at

    # Each gate's paths sit in its own half of the block, beside its own name.
    for path in COMPILED_PATHS:
        assert compile_at < section.index(path) < docs_at, path
    assert section.index(OTHER_GATE_PATH) > docs_at


def test_each_attempt_renders_its_own_writes_and_no_other_s() -> None:
    """Two prior attempts, two different writes — neither borrows the other's."""
    first = attempt(dirtied_gate(worktree_writes=(REWRITTEN_PATH,)), number=1)
    second = attempt(
        dirtied_gate(worktree_writes=(LATER_ATTEMPT_PATH,)),
        number=2,
        termination=Termination.TIMEOUT,
    )

    section = evidence_section(first, second)
    parts = section.split("### Attempt ")
    blocks = [f"### Attempt {part}" for part in parts[1:]]
    assert len(blocks) == 2, blocks

    assert REWRITTEN_PATH in blocks[0]
    assert LATER_ATTEMPT_PATH not in blocks[0]

    assert LATER_ATTEMPT_PATH in blocks[1]
    assert REWRITTEN_PATH not in blocks[1]


def test_a_gate_that_failed_and_also_wrote_reports_both() -> None:
    """FR-005's composition, rendered: the verdict *and* the writes.

    `_to_result` keeps the command's own verdict as the headline — a FAIL is
    the more actionable one — and still records what the gate wrote
    (`factory/verify/gates.py:1426-1431`). A renderer keyed on
    `DIRTIED_WORKTREE` alone would drop the paths for the gate whose next
    attempt is most likely to trip over them again.
    """
    section = evidence_section(
        attempt(
            make_gate(
                name="test",
                status=GateStatus.FAIL,
                exit_code=1,
                output_tail=ATTEMPT_ONE_TAIL,
                worktree_writes=(REWRITTEN_PATH,),
            )
        )
    )

    assert ATTEMPT_ONE_TAIL in section
    assert "exit 1" in section
    assert REWRITTEN_PATH in section


def test_the_writes_sit_with_their_gate_and_before_the_judge() -> None:
    """Verification order, rendered in verification order.

    The gate's own tail, then what that gate wrote, then the judge — so a block
    appended after everything cannot drift from the order the evidence was
    produced in, and the paths stay adjacent to the command that wrote them.
    """
    section = evidence_section(
        attempt(
            dirtied_gate(output_tail=ATTEMPT_ONE_TAIL),
            judge=make_judge("PLANTED-JUDGE-FEEDBACK-06"),
        )
    )

    assert (
        section.index(ATTEMPT_ONE_TAIL)
        < section.index(COMPILED_PATHS[0])
        < section.index("PLANTED-JUDGE-FEEDBACK-06")
    )


def test_the_prompt_does_not_send_the_next_attempt_at_the_manifest() -> None:
    """The advice stays inside what US2 can promise.

    A `writes:` declaration is US3's key and US3 has not necessarily landed when
    this prompt renders. The config gate parses a node's manifest with the
    *worker's installed* parser rather than the worktree's, so a prompt telling
    an agent to declare a key its worker does not know would turn a dirtied gate
    into a `CONFIG_ERROR` in 0.0s before any gate command ran — the failure
    `factory.yaml:38-42` records 020/US1 dying four times to prove.
    """
    section = evidence_section(attempt(dirtied_gate()))

    assert "factory.yaml" not in section
    assert "writes:" not in section


# --- US2-S2 / FR-007: the control -------------------------------------------


def test_a_clean_attempt_renders_byte_identically_to_before_this_story() -> None:
    """US2-S2: nothing about worktree writes appears when nothing was written.

    `EVIDENCE_SECTION_GOLDEN` is the corpus's evidence section captured before
    `_attempt_block` was ever touched. Prompt stability is what makes an
    untouched graph assemble identical prompts, so this is equality rather than
    a spot check: a writes block emitted unconditionally, an extra blank line,
    a changed heading — each moves these bytes.
    """
    section = evidence_section(*prior_two_attempts())

    assert section == EVIDENCE_SECTION_GOLDEN
    assert "wrote" not in section.lower()
    assert "worktree" not in section.lower()


def test_a_passing_gate_that_somehow_carried_writes_is_still_not_quoted() -> None:
    """The gate filter is untouched: a PASS row stays out, writes or not.

    `_to_result` cannot produce this — a gate with writes is demoted, which is
    the whole design (trap 7) — so this pins the filter rather than a reachable
    state: the block's rule is "failing gates only", and this story did not buy
    an exception to it.
    """
    section = evidence_section(
        attempt(
            make_gate(
                name="lint",
                status=GateStatus.PASS,
                exit_code=0,
                output_tail="PASSING-TAIL-MUST-NOT-APPEAR-07",
                worktree_writes=("PLANTED-PASS-WRITE-08.txt",),
            ),
            make_gate(output_tail=ATTEMPT_ONE_TAIL),
        )
    )

    assert "PASSING-TAIL-MUST-NOT-APPEAR-07" not in section
    assert "PLANTED-PASS-WRITE-08.txt" not in section


def test_a_failing_gate_that_wrote_nothing_gains_no_empty_block() -> None:
    """No writes, no block — an empty fence is noise with a heading on it."""
    section = evidence_section(attempt(make_gate(output_tail=ATTEMPT_ONE_TAIL)))

    assert ATTEMPT_ONE_TAIL in section
    assert "wrote" not in section.lower()


# --- US2-S3 / FR-008: the operator's gate line -------------------------------


def test_the_operator_gate_line_carries_the_writes_marker() -> None:
    """US2-S3: the marker on the line an operator actually reads.

    `concurrent_gates` is rendered here for exactly this reason
    (`factory/notify/messages.py:501-505`): a marker that lives only in the
    evidence store is one the operator never sees. The operator deciding
    RETRY/KILL on a `DIRTIED_WORKTREE` verdict is asking "what did it write" —
    and the gate's quoted output tail cannot answer, because the gate exited 0.
    """
    line = _gate_line(dirtied_gate())

    assert "compile" in line
    assert GateStatus.DIRTIED_WORKTREE.value in line
    for path in COMPILED_PATHS:
        assert path in line, path
    assert str(len(COMPILED_PATHS)) in line

    # One line, so it stays a line in a message read on a phone.
    assert "\n" not in line


def test_the_marker_reaches_the_escalation_message_not_only_the_helper() -> None:
    """The line is rendered through the history the escalation body is built
    from, so the assertion is about what the operator is paged with rather than
    about a private helper nobody's message passes through."""
    summary = render_history(
        [make_notify_result(gate_results=[make_notify_gate(**_notify_dirtied())])]
    )

    assert COMPILED_PATHS[0] in summary
    assert GateStatus.DIRTIED_WORKTREE.value in summary


def test_a_clean_gate_line_carries_no_marker() -> None:
    """The control: a gate that wrote nothing renders exactly as it did.

    Byte equality against the pre-story spelling, because every PASS gate of
    every attempt renders through this function and the escalation message has
    a 4096-byte budget to spend on evidence rather than on empty brackets.
    """
    assert _gate_line(make_notify_gate()) == "  gate test: PASS (exit 0, 12.5s)"
    assert _gate_line(make_notify_gate(concurrent_gates=2)) == (
        "  gate test: PASS (exit 0, 12.5s) [contended: 2 peer(s)]"
    )


def test_both_markers_render_together_when_both_were_recorded() -> None:
    """Neither marker shadows the other: a gate can be contended and dirty."""
    line = _gate_line(dirtied_gate(concurrent_gates=1))

    assert "contended: 1 peer(s)" in line
    assert COMPILED_PATHS[0] in line


def test_a_gate_that_wrote_many_paths_names_some_and_counts_the_rest() -> None:
    """The message budget, honoured out loud.

    A `compileall` gate over this repository writes hundreds of paths. Spilling
    all of them would push the attempt history — the thing the decision turns
    on — out of a 4096-byte message, so the line names a bounded number and
    says how many it did not, the way `_tail` names what it dropped. Silent
    truncation would read as "that is all of them".
    """
    paths = tuple(f"factory/PLANTED-MANY-09/module_{index}.pyc" for index in range(9))
    line = _gate_line(dirtied_gate(worktree_writes=paths))

    for path in paths[:GATE_WRITES_NAMED]:
        assert path in line, path
    for path in paths[GATE_WRITES_NAMED:]:
        assert path not in line, path

    # The total is on the line whatever was clipped, and so is the remainder.
    assert str(len(paths)) in line
    assert f"+{len(paths) - GATE_WRITES_NAMED} more" in line


# --- the third renderer, decided rather than discovered ----------------------


def test_a_dirtied_gate_never_reaches_a_landed_pr_body() -> None:
    """Why `factory/mergequeue/messages.py:_gate_status` takes no marker.

    `render_pr_body` is "the PR body for a passing node" and `gates_passed`
    refuses anything that is not `PASS`, so a `DIRTIED_WORKTREE` gate cannot be
    in a landed PR's gate list. The premise is pinned here rather than the
    branch, so a future change that lands a non-PASS gate fails this test
    instead of leaving the PR body quietly silent about it.
    """
    assert not gates_passed([dirtied_gate()])
    assert not gates_passed([make_gate(status=GateStatus.PASS, exit_code=0), dirtied_gate()])
    assert gates_passed([make_gate(status=GateStatus.PASS, exit_code=0)])


def _notify_dirtied() -> dict[str, object]:
    """`dirtied_gate`'s fields, for `tests.test_notify`'s builder."""
    return {
        "name": "compile",
        "command": COMPILEALL_COMMAND,
        "status": GateStatus.DIRTIED_WORKTREE,
        "exit_code": 0,
        "output_tail": "Listing 'factory'...\n",
        "worktree_writes": COMPILED_PATHS,
    }


def test_the_planted_gate_is_the_one_us1_would_actually_produce() -> None:
    """The fixture is not wishful: `_to_result` demotes exactly this shape.

    Every assertion above is built on `dirtied_gate()`, so if that shape is not
    one US1's runner produces, this whole module tests a fiction. The demotion
    rule is exit 0 plus writes, and `replace` here is the same dataclass US1
    populates.
    """
    gate = dirtied_gate()

    assert gate.exit_code == 0
    assert gate.status is GateStatus.DIRTIED_WORKTREE
    assert gate.worktree_writes == COMPILED_PATHS
    assert replace(gate, worktree_writes=()).worktree_writes == ()
