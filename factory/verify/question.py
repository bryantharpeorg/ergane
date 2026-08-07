"""Marker detection: when an agent's final message carries the OPERATOR QUESTION
heading, verification classifies the attempt QUESTION rather than FAIL (FR-001).

The detector is a read-only scan over the archived ``stdout.log`` the adapter
already streams on every termination path (plan § US1): no new artifact, no
worktree pollution. Its input is the attempt's transcript directory — the same
``AdapterResult.transcript_path`` the adapter points at the archive — and its
output is the question text the bridge ships, or nothing.

Four cases are the whole contract, and each is a test in
``tests/test_operator_question.py``:

- **A genuine marker classifies QUESTION with the body extracted.** The heading
  ``## OPERATOR QUESTION`` is line-anchored (exactly two hashes, a heading not a
  mention), sits in the agent's final message, and is followed by a non-empty
  body naming the fork. The detector returns the body verbatim.
- **A discussion of the marker does not classify.** The heading quoted mid-text
  (inside prose, inside a fenced block, or at the wrong level) is *about* the
  marker, not *a* marker. None of those produce a QUESTION.
- **An empty body under the marker is malformed.** A question with no content is
  not a question — the detector returns ``None`` so the attempt falls through to
  today's FAIL, the same as a message with no marker at all. (FR-010's guard: the
  marker can park a node, but a marker with no body parks nothing — there is
  nothing to page the operator with.)
- **A missing or unreadable transcript is an infrastructure failure.** Detection
  raises rather than returning ``None``: ``None`` means "no question, grade as
  today", and a vanished archive must never be read as a clean attempt that
  happened to ask nothing (the same line ``check_output`` draws for a vanished
  worktree). It is never a QUESTION and never a silent FAIL.

The detector reuses the criteria parser's fence-masking and heading grammar
(``HEADER_RE``, ``mask_fences``, ``section_end``) so "what is a heading, and what
is quoted text about one" is decided one way across the factory (R9): a marker
quoted inside a fenced code block is documentation of the marker, not a marker,
the same way a quoted ``### User Story`` is not a story declaration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from factory.verify.criteria import HEADER_RE, mask_fences, section_end

#: The fixed heading the agent writes in its final message (spec § US1). Exactly
#: two hashes — a level-2 heading, not a mention, not a level-3 subsection. The
#: prompt contract (T008) teaches this heading; the detector matches it. The two
#: must agree, or an agent that follows the prompt is not recognised.
QUESTION_HEADING = "## OPERATOR QUESTION"

#: The heading level the marker sits at: ``len("##")``. A level-3 subsection is
#: not the marker, and neither is a level-1 title.
_MARKER_LEVEL = 2


class TranscriptReadError(RuntimeError):
    """The archived transcript could not be read — an infrastructure failure.

    Raised rather than returning ``None``: ``None`` means "no question, grade as
    today", and a vanished or unreadable archive must never be read as a clean
    attempt that happened to ask nothing. The activity that calls the detector
    surfaces this as a non-QUESTION error the ladder can spend a retry on, the
    same way ``check_output`` raises ``WORKTREE_MISSING`` for a vanished worktree
    rather than returning an empty diff.
    """


@dataclass(frozen=True)
class QuestionMarker:
    """What the detection activity answers with.

    A read-only scan's whole output: whether the final message carried the
    marker, and the body verbatim. ``is_question=False`` is the common case (no
    marker — nothing changes from today, acceptance scenario 3); the workflow
    never consults gates or a judge for a question, and for ``False`` it carries
    on as today (FR-010).
    """

    is_question: bool
    text: str = ""


def detect_operator_question(transcript_path: Path) -> QuestionMarker | None:
    """Read the archived transcript and return the marker, or ``None``.

    ``None`` means the final message carried no marker *or* carried one with an
    empty body (malformed): in both cases the attempt falls through to today's
    grading, because there is nothing to park the node on. A marker with a real
    body returns ``QuestionMarker(is_question=True, text=body)``.

    A missing directory, a missing ``stdout.log``, or an unreadable file raises
    ``TranscriptReadError`` — the one outcome that is neither QUESTION nor the
    common case, because reading silence as "no question" would let a vanished
    archive look like a clean attempt that happened to ask nothing.
    """
    stdout = _read_stdout(transcript_path)
    lines = stdout.splitlines()
    in_code = mask_fences(lines)

    marker_index = _last_marker(lines, in_code)
    if marker_index is None:
        return None

    end = section_end(lines, in_code, marker_index, level=_MARKER_LEVEL)
    body = "\n".join(lines[marker_index + 1 : end]).strip()
    if not body:
        # A question with no content is not a question (FR-010): the marker with
        # an empty body parks nothing, so the attempt falls through to FAIL the
        # same as a message with no marker at all.
        return None
    return QuestionMarker(is_question=True, text=body)


# --- the read ----------------------------------------------------------------


def _read_stdout(transcript_path: Path) -> str:
    """Read the archived ``stdout.log``, or raise if it cannot be read.

    The directory and the file must both exist and be readable: a transcript the
    detector cannot open is an infrastructure failure (``TranscriptReadError``),
    never a silent ``None``.
    """
    if not transcript_path.is_dir():
        raise TranscriptReadError(
            f"transcript directory not found: {transcript_path}"
        )
    log = transcript_path / STDOUT_LOG_NAME
    if not log.is_file():
        raise TranscriptReadError(
            f"stdout.log not found in transcript: {log}"
        )
    try:
        return log.read_text(encoding="utf-8")
    except OSError as exc:
        raise TranscriptReadError(f"cannot read transcript {log}: {exc}") from exc


#: The archive file the adapter streams the agent's stdout into on every
#: termination path (``factory/workgraph/adapter.py``). Named here rather than
#: imported from the adapter so this module stays a leaf: the detector reads a
#: path the adapter points at, and coupling the two would make the read depend on
#: the writer's import graph.
STDOUT_LOG_NAME = "stdout.log"


# --- the scan ----------------------------------------------------------------


def _last_marker(lines: Sequence[str], in_code: Sequence[bool]) -> int | None:
    """The index of the final line-anchored ``## OPERATOR QUESTION`` heading.

    Only the *last* marker counts: an agent that asked, kept going, and asked
    again is raising the question in its final message, and that is the one the
    operator is paged with. A heading inside a fence is masked (``in_code``), a
    heading at the wrong level does not match ``QUESTION_HEADING`` exactly, and a
    mention spelled out in prose does not start at column 0.
    """
    found: int | None = None
    for index, line in enumerate(lines):
        if in_code[index]:
            continue
        if line == QUESTION_HEADING:
            found = index
    return found