"""Marker detection: when an agent's final message carries the OPERATOR QUESTION
heading, verification classifies the attempt QUESTION rather than FAIL (FR-001).

The detector is a read-only scan over the archived ``stdout.log`` the adapter
already streams on every termination path (plan § US1): no new artifact, no
worktree pollution. Its input is the attempt's transcript directory — the same
``AdapterResult.transcript_path`` the adapter points at the archive — and its
output is the question text the bridge ships, or nothing.

Four cases are the whole contract, and each is a test:

- **A genuine marker classifies QUESTION with the body extracted.** The heading
  ``## OPERATOR QUESTION`` is line-anchored (exactly two hashes, a heading not a
  mention), sits in the agent's final message, and is followed by a non-empty
  body naming the fork. The detector returns the body verbatim.
- **A discussion of the marker does not classify.** The heading quoted mid-text
  (inside prose, inside a fenced block, or at the wrong level) is *about* the
  marker, not *a* marker. None of those produce a QUESTION, because none is a
  line-anchored heading outside a fence in the final message.
- **An empty body under the marker is malformed.** A question with no content is
  not a question — the detector returns ``None`` so the attempt falls through to
  today's FAIL, the same as a message with no marker at all. (FR-010's guard: the
  marker can park a node, but a marker with no body parks nothing — there is
  nothing to page the operator with.)
- **A missing or unreadable transcript is an infrastructure failure.** Detection
  raises rather than returning ``None``: ``None`` means "no question, grade as
  today", and a vanished archive must never be read as a clean attempt that
  happened to ask nothing (the same line ``check_output`` draws for a vanished
  worktree). It is never a QUESTION and never a silent FAIL — the activity that
  calls the detector surfaces it as a non-QUESTION error the ladder can spend a
  retry on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.verify.question import (
    QUESTION_HEADING,
    QuestionMarker,
    TranscriptReadError,
    detect_operator_question,
)

#: The fixed heading the agent writes in its final message (spec § US1). Exactly
#: two hashes — a level-2 heading, not a mention, not a level-3 subsection.
MARKER = "## OPERATOR QUESTION"


def _archive(tmp_path: Path, *, stdout: str, name: str = "attempt-1") -> Path:
    """Build a transcript archive holding ``stdout`` and return its directory.

    The detector reads ``stdout.log`` from the archive directory the adapter
    streams into (``AdapterResult.transcript_path``), so each case is a real
    directory with a real file — the same shape the adapter leaves on disk.
    """
    transcript = tmp_path / "transcripts" / "epic-008" / "us1" / name
    transcript.mkdir(parents=True)
    (transcript / "stdout.log").write_text(stdout, encoding="utf-8")
    return transcript


# --- the genuine marker ------------------------------------------------------


def test_a_final_message_with_the_marker_classifies_question_with_the_body(
    tmp_path: Path,
) -> None:
    body = (
        "I hit a fork on how the questions table should key its rows.\n\n"
        "Option A: a 12-hex id like escalations. Option B: the (epic, node, "
        "attempt) tuple. I lean A for reply-routing parity.\n\n"
        "Which?"
    )
    stdout = (
        "Here is the work so far.\n\n"
        "I wrote the detection module and its tests.\n\n"
        f"{MARKER}\n{body}\n"
    )
    marker = detect_operator_question(_archive(tmp_path, stdout=stdout))

    assert marker is not None
    assert marker.is_question is True
    # The body is extracted verbatim — the bridge ships what the agent wrote,
    # not a paraphrase of it (FR-002).
    assert marker.text == body.strip()


def test_the_marker_body_is_extracted_only_to_the_next_heading(tmp_path: Path) -> None:
    # A later level-2 heading ends the question body; a deeper one does not.
    stdout = (
        f"{MARKER}\n"
        "The fork: store answers in the questions table or a sibling.\n\n"
        "### Why it matters\n"
        "Routing depends on it.\n\n"
        "## Summary\n"
        "Done.\n"
    )
    marker = detect_operator_question(_archive(tmp_path, stdout=stdout))

    assert marker is not None
    assert "The fork" in marker.text
    assert "Why it matters" in marker.text  # the deeper heading is inside the body
    assert "Summary" not in marker.text  # the same-level heading ends it
    assert "Done" not in marker.text


def test_only_the_final_marker_counts_when_several_appear(tmp_path: Path) -> None:
    # An agent that asked, kept going, and asked again: the last marker is the
    # one in the final message, and its body is what ships.
    stdout = (
        f"{MARKER}\nFirst question, withdrawn.\n\n"
        "I kept working and resolved that.\n\n"
        f"{MARKER}\nSecond question, the real fork.\n"
    )
    marker = detect_operator_question(_archive(tmp_path, stdout=stdout))

    assert marker is not None
    assert marker.text == "Second question, the real fork."


# --- the false positives the trap exists for --------------------------------


def test_a_marker_discussed_in_prose_is_not_a_question(tmp_path: Path) -> None:
    # The heading spelled out in a sentence is text about a heading, not a
    # heading: it does not start at column 0 and it is not a level-2 header.
    stdout = (
        "I considered using the heading `## OPERATOR QUESTION` to flag a fork, "
        "but decided against it.\n"
    )
    assert detect_operator_question(_archive(tmp_path, stdout=stdout)) is None


def test_a_marker_inside_a_fenced_block_is_not_a_question(tmp_path: Path) -> None:
    # A heading quoted in a code block is documentation of the marker, not a
    # marker: the fence masks it, the same way the criteria parser masks a
    # quoted `### User Story` (plan § US1 "the trap").
    stdout = (
        "The contract says:\n\n"
        "```\n"
        f"{MARKER}\n"
        "<the fork, the options, the lean>\n"
        "```\n\n"
        "I followed it where I could.\n"
    )
    assert detect_operator_question(_archive(tmp_path, stdout=stdout)) is None


def test_a_marker_at_the_wrong_heading_level_is_not_a_question(tmp_path: Path) -> None:
    # A level-3 subsection is not the level-2 heading the contract names; an
    # agent that uses it as a sub-point is not raising a question.
    stdout = (
        "## Work done\n"
        "I refactored the detector.\n\n"
        "### OPERATOR QUESTION\n"
        "Just thinking out loud about naming.\n"
    )
    assert detect_operator_question(_archive(tmp_path, stdout=stdout)) is None


def test_a_message_with_no_marker_is_no_question(tmp_path: Path) -> None:
    # The common case: nothing changes from today (acceptance scenario 3).
    stdout = "All tasks done. Tests green.\n"
    assert detect_operator_question(_archive(tmp_path, stdout=stdout)) is None


def test_an_empty_body_under_the_marker_is_malformed_not_a_question(
    tmp_path: Path,
) -> None:
    # A question with no content is not a question (T003): the marker with an
    # empty body returns None, so the attempt falls through to today's FAIL
    # rather than parking the node on nothing.
    stdout = f"{MARKER}\n\n## Summary\nDone.\n"
    assert detect_operator_question(_archive(tmp_path, stdout=stdout)) is None


def test_a_marker_whose_body_is_only_whitespace_is_malformed(tmp_path: Path) -> None:
    stdout = f"{MARKER}\n   \n  \n"
    assert detect_operator_question(_archive(tmp_path, stdout=stdout)) is None


# --- the infrastructure failure that must never be silent --------------------


def test_a_missing_transcript_directory_is_an_infrastructure_failure(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "transcripts" / "epic-008" / "us1" / "attempt-1"
    with pytest.raises(TranscriptReadError):
        detect_operator_question(missing)


def test_a_missing_stdout_log_is_an_infrastructure_failure(tmp_path: Path) -> None:
    transcript = tmp_path / "transcripts" / "epic-008" / "us1" / "attempt-1"
    transcript.mkdir(parents=True)
    with pytest.raises(TranscriptReadError):
        detect_operator_question(transcript)


def test_an_unreadable_transcript_is_an_infrastructure_failure(tmp_path: Path) -> None:
    transcript = _archive(tmp_path, stdout="## OPERATOR QUESTION\nreal fork\n")
    # Strip read permission — the detector must not read silence as "no question".
    (transcript / "stdout.log").chmod(0o000)
    try:
        with pytest.raises(TranscriptReadError):
            detect_operator_question(transcript)
    finally:
        (transcript / "stdout.log").chmod(0o644)


# --- the heading constant is the contract the prompt teaches ----------------


def test_the_heading_constant_is_exactly_the_level_two_marker() -> None:
    # The prompt contract names this heading; the detector matches it. The two
    # must agree, or an agent that follows the prompt is not recognised.
    assert QUESTION_HEADING == "## OPERATOR QUESTION"