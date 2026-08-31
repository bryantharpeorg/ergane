"""US3 of 101: a toolchain failure is annotated rather than echoed.

`HOME` inside the gate boundary is a fresh tmpfs, so a toolchain the attempt
installed under `HOME` is gone by gate time and only the worktree crosses. When
that happens the tool says the one thing guaranteed to waste the next attempt:
*just run the install*. The factory recorded that advice verbatim and passed it
into the retry prompt, where it reads as the tool's considered opinion about
what to do next. It is not: the install already ran, in a `HOME` that no longer
exists, and running it again lands it in the same place.

The measurement behind US1 says what this story may and may not add. An agent
given no guidance at all found the complete fix in three attempts; an agent
given the mechanism stated correctly but incompletely put the variable where the
text said, stopped searching, and failed 3/3 with the browser physically present
in its worktree. So an annotation that says "your `HOME` is a tmpfs" and stops
is not a smaller version of the fix — it is the failure mode, arriving through a
second door. The annotation carries the fact *and* the remedy, or it is not
worth its bytes.

What these tests defend:

- **The annotation is appended, never substituted.** The tool's own output is
  the evidence; the factory's sentence is a note beside it, bracketed so a
  reader can tell which voice is which — the convention `_to_result` already
  uses for `[worktree snapshot failed: …]`.
- **The match is a signature, not a guess** (trap 7). Three named tools, three
  exact phrases each of those tools prints. A loose match would annotate every
  failing gate with a `HOME` lecture, and noise in a retry prompt is precisely
  what the 3/3 measurement is about.
- **The control is byte identity.** A failure matching no signature is recorded
  as the same object it was recorded as before this story — asserted with `is`,
  not with `==`, because a rebuild that happens to produce equal bytes today is
  one refactor away from producing different ones.
- **It reaches the retry.** An annotation the next attempt never sees is a
  comment (trap 6), so US3-S3 runs the real recording path into the real prompt
  assembler and asserts the text arrives, rather than asserting that a field was
  set.

The gate results here come out of `run_gates` over a real (empty) git worktree
with the executor seam supplying the output, so the assertions are about what the
runner records rather than about what a hand-built `GateResult` was given.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.usage.models import Termination
from factory.verify.factory_yaml import MANIFEST_NAME
from factory.verify.gate_annotation import (
    GATE_BOUNDARY_SECTION,
    INSTALL_SIGNATURES,
    TMPFS_HOME_ANNOTATION,
    annotate_install_advice,
    matched_install_signature,
)
from factory.verify.gates import (
    OUTPUT_TAIL_LIMIT,
    ExecutionOutcome,
    run_gates,
    tail_output,
)
from factory.verify.models import GateResult, GateStatus
from factory.workgraph.prompt import AttemptEvidence
from tests.test_gates import RecordingExecutor, make_git_worktree
from tests.test_prompt import build, make_result

# --- the output the tools actually print --------------------------------------
#
# Reproduced with their own framing, because the framing is the reason the match
# is not line-anchored: Playwright prints its advice inside a box, so the line
# carrying `npx playwright install` starts with `║`, not with whitespace.

PLAYWRIGHT_TAIL = """\
    Error: browserType.launch: Executable doesn't exist at \
/home/node/.cache/ms-playwright/chromium-1091/chrome-linux/chrome
    ╔═════════════════════════════════════════════════════════════════════════╗
    ║ Looks like Playwright Test or Playwright was just installed or updated. ║
    ║ Please run the following command to download new browsers:              ║
    ║                                                                         ║
    ║     npx playwright install                                              ║
    ║                                                                         ║
    ║ <3 Playwright Team                                                      ║
    ╚═════════════════════════════════════════════════════════════════════════╝
"""

PUPPETEER_TAIL = """\
Error: Could not find Chrome (ver. 121.0.6167.85). This can occur if either
 1. you did not perform an installation before running the script
 2. your cache path is incorrectly configured
For (2), check out our guide on configuring puppeteer at https://pptr.dev.
Run `npx puppeteer browsers install chrome` to download it.
"""

CYPRESS_TAIL = """\
The cypress npm package is installed, but the Cypress binary is missing.
We expected the binary to be installed here: /root/.cache/Cypress/13.6.0/Cypress
Please reinstall Cypress by running: cypress install
"""

SIGNED_TAILS = {
    "playwright": PLAYWRIGHT_TAIL,
    "puppeteer": PUPPETEER_TAIL,
    "cypress": CYPRESS_TAIL,
}

#: An ordinary failing suite: the control's input, and the shape of nearly every
#: gate failure this factory records.
ORDINARY_TAIL = """\
FAILED tests/test_loans.py::test_a_second_loan_is_refused - AssertionError
E       assert loans == 1
E        +  where loans = 2
1 failed, 41 passed in 3.12s
"""


# --- harness ------------------------------------------------------------------


def run_one_gate(
    worktree: Path,
    output: str,
    *,
    exit_code: int | None = 1,
    timed_out: bool = False,
) -> GateResult:
    """Record one gate whose executor produced `output`, through `run_gates`.

    The whole recording path — the executor seam, the worktree watch,
    `_to_result` — so an annotation applied anywhere else than where the detail
    is actually built would not satisfy these assertions.
    """
    make_git_worktree(worktree)
    (worktree / MANIFEST_NAME).write_text(
        "version: 1\nruntime: bwrap\ngates:\n  test: uv run pytest -q\n",
        encoding="utf-8",
    )
    executor = RecordingExecutor(
        {
            "test": ExecutionOutcome(
                exit_code=exit_code,
                output=output,
                duration_s=1.5,
                timed_out=timed_out,
            )
        }
    )
    results = run_gates(worktree, executor=executor)
    assert len(results) == 1, results
    return results[0]


def home_fact_present(text: str) -> bool:
    """The boundary's `HOME` fact, spelled out rather than named by a constant.

    A test that asserted `TMPFS_HOME_ANNOTATION in text` and nothing else would
    pass for an annotation that said "the boundary is different" — the exact
    shape of guidance the 3/3 measurement condemns. These are the three claims
    that make the fact a fact.
    """
    lowered = text.lower()
    return "home" in lowered and "tmpfs" in lowered and "worktree" in lowered


# --- T016 / US3-S1: a known signature carries the boundary's HOME fact ---------


def test_a_playwright_install_failure_carries_the_boundary_home_fact(
    tmp_path: Path,
) -> None:
    """US3-S1, on the failure that was actually measured.

    Three of four gates green, the smoke gate failing with Playwright's own
    "just installed… npx playwright install" — with the browser present in the
    agent's worktree the whole time. This is that gate, recorded.
    """
    result = run_one_gate(tmp_path / "playwright", PLAYWRIGHT_TAIL)

    assert result.status is GateStatus.FAIL
    assert TMPFS_HOME_ANNOTATION in result.output_tail
    assert home_fact_present(result.output_tail)


@pytest.mark.parametrize("tool", sorted(SIGNED_TAILS))
def test_every_declared_signature_is_matched_by_its_own_tool_s_output(
    tmp_path: Path, tool: str
) -> None:
    """Each signature is matched by the text the tool it names really prints.

    A signature nothing produces is not a small set kept honest, it is dead
    code that reads as coverage. Parametrised over the declared set so adding a
    signature without a fixture that exercises it fails here.
    """
    matched = matched_install_signature(SIGNED_TAILS[tool])
    assert matched is not None and matched.tool == tool

    result = run_one_gate(tmp_path / tool, SIGNED_TAILS[tool])
    assert TMPFS_HOME_ANNOTATION in result.output_tail


def test_the_declared_set_and_the_fixtures_are_the_same_set() -> None:
    """Neither side grows silently past the other (trap 7's "small and explicit")."""
    assert {signature.tool for signature in INSTALL_SIGNATURES} == set(SIGNED_TAILS)


def test_the_match_is_not_line_anchored_because_the_advice_arrives_in_a_box() -> None:
    """Why the patterns anchor on words rather than on `^`.

    Playwright frames its advice in box-drawing characters, so the line carrying
    the command begins with `║` and a `^\\s*npx` pattern matches nothing at all.
    The premise is pinned here rather than left in a comment: if the fixture ever
    stops being box-framed, this test says so instead of the anchoring choice
    quietly becoming arbitrary.
    """
    advice_line = next(
        line for line in PLAYWRIGHT_TAIL.splitlines() if "playwright install" in line
    )
    assert advice_line.lstrip().startswith("║")
    assert matched_install_signature(PLAYWRIGHT_TAIL) is not None


def test_the_tool_s_own_output_is_kept_verbatim_beside_the_annotation(
    tmp_path: Path,
) -> None:
    """Appended, never substituted: the tool's output is the evidence.

    The factory's note is an addition to the detail, so the recorded tail still
    opens with exactly what the gate emitted. A rewrite that replaced the advice
    with the correction would destroy the one thing the next attempt needs to
    recognise the failure by.
    """
    result = run_one_gate(tmp_path / "verbatim", PLAYWRIGHT_TAIL)

    assert result.output_tail.startswith(PLAYWRIGHT_TAIL)
    assert result.output_tail.index(PLAYWRIGHT_TAIL) < result.output_tail.index(
        TMPFS_HOME_ANNOTATION
    )


def test_the_annotation_is_legible_as_the_factory_s_voice(tmp_path: Path) -> None:
    """Bracketed, the way `[worktree snapshot failed: …]` already is.

    `tail_output`'s docstring refuses to insert a truncation marker because it
    "would put the factory's own voice inside what is supposed to be the tool's
    output". That objection is answered by making the voice visible rather than
    by staying silent, and the convention for that in this module already
    exists.
    """
    result = run_one_gate(tmp_path / "voice", PLAYWRIGHT_TAIL)

    assert TMPFS_HOME_ANNOTATION.startswith("[")
    assert TMPFS_HOME_ANNOTATION.rstrip().endswith("]")
    assert "ergane" in result.output_tail


def test_the_annotation_names_the_remedy_and_not_only_the_mechanism() -> None:
    """Trap 1, applied to US3: a mechanism without a recipe is worse than silence.

    The measured failure is an agent that was told the mechanism, believed it,
    and stopped searching. So the annotation has to leave the agent holding an
    action: put the toolchain under the worktree, and name that path in front of
    the gate command — and it points at the prompt section that carries the
    worked form rather than restating it at length here.
    """
    assert "worktree" in TMPFS_HOME_ANNOTATION
    assert "gate command" in TMPFS_HOME_ANNOTATION
    assert GATE_BOUNDARY_SECTION in TMPFS_HOME_ANNOTATION

    # Short enough to read on the way past; the tail it joins has a 32 KiB
    # budget that belongs to the gate's own output.
    assert len(TMPFS_HOME_ANNOTATION) < 700


def test_the_section_the_annotation_points_at_is_really_in_the_prompt() -> None:
    """A pointer to a heading that does not exist is worse than no pointer.

    The heading is spelled in `gate_annotation` rather than imported from
    `factory.workgraph.prompt` — verification does not depend on prompt
    assembly, and this story is not the place to invert that — so the two
    spellings are pinned together here instead.
    """
    assert GATE_BOUNDARY_SECTION in build()


def test_a_timed_out_gate_carrying_the_signature_is_annotated_too(
    tmp_path: Path,
) -> None:
    """A gate that hung mid-download is the same failure, one symptom along.

    The tool printed the advice and then the deadline arrived; there is no exit
    code to read, and the next attempt is owed the same correction.
    """
    result = run_one_gate(
        tmp_path / "timeout", PLAYWRIGHT_TAIL, exit_code=None, timed_out=True
    )

    assert result.status is GateStatus.TIMEOUT
    assert TMPFS_HOME_ANNOTATION in result.output_tail


def test_the_annotation_survives_a_gate_that_overflowed_the_tail(
    tmp_path: Path,
) -> None:
    """The cap is honoured and the annotation is what is kept.

    `output_tail` is the last ≤32 KiB, and a gate that printed a megabyte before
    failing is exactly the gate whose next attempt most needs the correction.
    Appending before re-tailing is what keeps it: the note is at the end, so the
    cut lands on the noise ahead of it.
    """
    noisy = ("x" * 79 + "\n") * 500 + PLAYWRIGHT_TAIL
    assert len(noisy.encode("utf-8")) > OUTPUT_TAIL_LIMIT

    result = run_one_gate(tmp_path / "noisy", noisy)

    assert TMPFS_HOME_ANNOTATION in result.output_tail
    assert len(result.output_tail.encode("utf-8")) <= OUTPUT_TAIL_LIMIT


# --- T017 / US3-S2: the control ------------------------------------------------


def test_a_failure_matching_no_signature_is_recorded_unchanged(
    tmp_path: Path,
) -> None:
    """US3-S2: an ordinary failing suite is recorded as it was before this story.

    Byte identity against `tail_output` of the raw output — the whole of what
    `_to_result` used to do — so an annotation emitted unconditionally, a
    trailing newline, or a blank line moves this assertion.
    """
    result = run_one_gate(tmp_path / "ordinary", ORDINARY_TAIL)

    assert result.status is GateStatus.FAIL
    assert result.output_tail == tail_output(ORDINARY_TAIL)
    assert "tmpfs" not in result.output_tail
    assert "ergane" not in result.output_tail.lower()


def test_the_unmatched_detail_is_returned_as_the_same_object() -> None:
    """Identity, not equality: nothing is rebuilt on the path that adds nothing.

    Asserted with `is` because equal bytes today are one refactor away from a
    reconstructed string that normalises a newline, and every gate this factory
    has ever run took this path.
    """
    assert annotate_install_advice(ORDINARY_TAIL) is ORDINARY_TAIL
    assert annotate_install_advice("") is ""
    assert matched_install_signature(ORDINARY_TAIL) is None


def test_a_passing_gate_whose_output_mentions_the_advice_is_not_annotated(
    tmp_path: Path,
) -> None:
    """The trigger is a failure, not a string.

    A green suite whose own output quotes the advice — a test asserting on this
    very fixture, for one — is not a toolchain failure, and a `HOME` lecture on
    a PASS row is noise nobody asked for.
    """
    result = run_one_gate(tmp_path / "passing", PLAYWRIGHT_TAIL, exit_code=0)

    assert result.status is GateStatus.PASS
    assert result.output_tail == tail_output(PLAYWRIGHT_TAIL)


def test_a_near_miss_is_not_a_signature() -> None:
    """The set is explicit: adjacent phrases from the same tools do not match.

    `npm install`, `pip install` and Playwright's own system-dependency helper
    are all things a failing gate says while having nothing to do with a
    toolchain that did not cross the boundary.
    """
    for near_miss in (
        "npm ERR! run `npm install` to fix 3 vulnerabilities\n",
        "ERROR: pip install --upgrade pip is available\n",
        "install the missing package and try again\n",
        "Chrome could not be found; check your PATH.\n",
    ):
        assert matched_install_signature(near_miss) is None, near_miss


# --- T018 / US3-S3: the annotation reaches the next attempt --------------------


def test_the_annotation_reaches_the_next_attempt_s_prompt(tmp_path: Path) -> None:
    """US3-S3 end to end: recorded gate -> attempt evidence -> assembled prompt.

    The `GateResult` here is the one `run_gates` produced two functions up, not
    a hand-built stand-in carrying the annotation because the test put it there.
    That is the whole point of trap 6: an annotation added to a record the retry
    prompt does not read is a comment, and only running both halves can tell the
    difference.
    """
    result = run_one_gate(tmp_path / "e2e", PLAYWRIGHT_TAIL)
    evidence = AttemptEvidence(
        termination=Termination.COMPLETED,
        result=make_result(attempt=1, gates=[result], judge=None),
    )

    prompt = build(prior_attempts=[evidence])

    assert TMPFS_HOME_ANNOTATION in prompt
    assert home_fact_present(prompt[prompt.index(TMPFS_HOME_ANNOTATION) :])

    # Beside the tool's own advice, in the same block, so the correction is read
    # against the thing it corrects rather than as a free-floating warning.
    assert "npx playwright install" in prompt
    assert prompt.index("npx playwright install") < prompt.index(
        TMPFS_HOME_ANNOTATION
    )


def test_an_unannotated_failure_reaches_the_prompt_with_nothing_added(
    tmp_path: Path,
) -> None:
    """The control, end to end: the retry for an ordinary failure is untouched.

    US3-S2 asserts the record; this asserts the thing an agent is actually
    handed, because the record and the prompt are two places an annotation
    could leak into and only one of them costs an attempt.
    """
    result = run_one_gate(tmp_path / "e2e-control", ORDINARY_TAIL)
    evidence = AttemptEvidence(
        termination=Termination.COMPLETED,
        result=make_result(attempt=1, gates=[result], judge=None),
    )

    prompt = build(prior_attempts=[evidence])

    assert ORDINARY_TAIL in prompt
    assert TMPFS_HOME_ANNOTATION not in prompt
