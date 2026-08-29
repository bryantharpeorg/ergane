"""US1-S1/S2 — the addressee grammar, over both surfaces the 008 channel has.

017-US1. The 008 question grammar has two surfaces — the final-message marker
and the in-flight ferry file — and 008 pinned exactly one addressee into both:
the operator. This story adds the address. An optional first line names who the
question is for, and everything after it is the body; absence of that line is
the common case and the compatibility contract, because a message with no
addressee must behave byte-identically to 008's operator question on every path
(FR-001, acceptance scenario 4).

The grammar is one function, not two. The marker body and the ferry body are
the same shape — free text the agent wrote — so a question addressed in a
final message and one addressed mid-flight parse by the same rule, and the two
surfaces cannot drift into two grammars the way two parsers always do. What
differs is where the text came from; nothing about the parse is allowed to.

What these tests pin down:

- **The addressee is an optional first line, and absence is the default.**
  `To: <name>` on the first line of a body addresses the message; a body that
  starts any other way has no addressee and routes to the operator exactly as
  008 did. The addressee-less text is returned unchanged, byte for byte, so
  the 008 fixtures' meaning is preserved without editing them (FR-001).
- **The addressee is peeled off the body, not swallowed by it.** The body a
  peer receives is the text under the address line — what the asker meant the
  peer to read — while the addressee itself is routing data, not content.
- **A self-address is refused at routing, not by the grammar.** The grammar
  parses `To: us1` the same as any other name; the refusal is a routing
  decision the workflow owns, tested where routing is tested. What the grammar
  owns is only the shape: a line that is not `To:`-spelled is body, never a
  misread address.
- **An empty body under an address line is still malformed.** 008's rule that a
  question with no content parks nothing is unchanged by the arrival of the
  address: there is nothing to route, so there is no message.

Written before the grammar exists (T003 precedes T007): until it lands, every
test here fails at import.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.verify.question import (
    QUESTION_HEADING,
    TranscriptReadError,
    detect_operator_question,
)

#: The fixed heading the agent writes, unchanged from 008 — the addressee is a
#: line inside the body, so the marker itself is exactly what it was (FR-001).
MARKER = "## OPERATOR QUESTION"

#: The line that names a recipient. One spelling, one place — the first line of
#: the body — because "optional" has to mean "there is exactly one way to do
#: it", or two spellings drift and an agent that used the wrong one silently
#: paged the operator about a question meant for a peer.
ADDRESSEE_LINE = "To: us2"

#: What a peer-question body looks like under the address line.
PEER_BODY = (
    "You wrote the plan this story implements. Does the interface in\n"
    "`factory/escalation/question.py` match what the plan's reuse inventory\n"
    "meant, or was the anchor moved after you wrote it?\n"
)

#: What an operator-question body looks like — no address line, 008's shape
#: exactly. Byte-identical to the fixture `tests/test_operator_question.py`
#: uses for its genuine-marker case, so the two suites read the same text.
OPERATOR_BODY = (
    "I hit a fork on how the questions table should key its rows.\n\n"
    "Option A: a 12-hex id like escalations. Option B: the (epic, node, "
    "attempt) tuple. I lean A for reply-routing parity.\n\n"
    "Which?"
)


def _archive(tmp_path: Path, *, stdout: str, name: str = "attempt-1") -> Path:
    """Build a transcript archive holding ``stdout`` and return its directory.

    The same helper shape `tests/test_operator_question.py` uses: the detector
    reads ``stdout.log`` from the archive directory, so each case is a real
    directory with a real file — the shape the adapter leaves on disk.
    """
    transcript = tmp_path / "transcripts" / "epic-017" / "us1" / name
    transcript.mkdir(parents=True)
    (transcript / "stdout.log").write_text(stdout, encoding="utf-8")
    return transcript


# --- the addressee line is parsed off both surfaces ---------------------------


def test_a_marker_body_with_an_addressee_line_names_the_addressee(
    tmp_path: Path,
) -> None:
    """US1-S1: `To: <peer>` on the marker body's first line addresses the peer.

    The detector finds the same marker it always did; what changed is that the
    body's first line is routing data rather than question text. The addressee
    is what routing keys on and the body is what the peer reads — both travel
    out of the marker, neither is invented.
    """
    stdout = f"{MARKER}\n{ADDRESSEE_LINE}\n{PEER_BODY}"
    marker = detect_operator_question(_archive(tmp_path, stdout=stdout))

    assert marker is not None
    assert marker.is_question is True
    assert marker.addressee == "us2"
    assert marker.text == PEER_BODY.strip()


def test_a_ferry_body_with_an_addressee_line_parses_the_same_way(
    tmp_path: Path,
) -> None:
    """US1-S1: the ferry body and the marker body are one grammar.

    The in-flight ferry writes its question to a file rather than a final
    message, but the body it holds is the same free text the marker holds, so
    the same parse applies. Two surfaces, one grammar — a question addressed
    mid-flight routes to the same peer the same way.
    """
    from factory.workgraph.peers import parse_addressee

    parsed = parse_addressee(f"{ADDRESSEE_LINE}\n{PEER_BODY}")

    assert parsed.addressee == "us2"
    assert parsed.body == PEER_BODY.strip()


def test_a_body_with_no_addressee_line_has_no_addressee(tmp_path: Path) -> None:
    """FR-001: absence is the common case, and it means the operator.

    A body that starts any other way carries no address: the addressee is None
    and the text is the whole body, unchanged — the shape 008 shipped, byte for
    byte, so the operator path never learns the grammar exists.
    """
    from factory.workgraph.peers import parse_addressee

    parsed = parse_addressee(OPERATOR_BODY)

    assert parsed.addressee is None
    assert parsed.body == OPERATOR_BODY.strip()


def test_a_marker_with_no_addressee_keeps_the_008_shape_byte_for_byte(
    tmp_path: Path,
) -> None:
    """FR-001 / acceptance scenario 4: an addressee-less marker is 008's.

    The 008 fixture body, unedited, produces exactly the marker the 008 suite
    asserts: no addressee, and the body verbatim. This is the compatibility
    contract — every existing 008 test keeps its meaning because the
    addressee-less path returns the same text it always did.
    """
    stdout = f"{MARKER}\n{OPERATOR_BODY}"
    marker = detect_operator_question(_archive(tmp_path, stdout=stdout))

    assert marker is not None
    assert marker.is_question is True
    assert marker.addressee is None
    assert marker.text == OPERATOR_BODY.strip()
    # Byte for byte: the 008 assertion, on the 008 text, still holds.
    assert marker.text == (
        "I hit a fork on how the questions table should key its rows.\n\n"
        "Option A: a 12-hex id like escalations. Option B: the (epic, node, "
        "attempt) tuple. I lean A for reply-routing parity.\n\n"
        "Which?"
    )


def test_the_008_marker_fixtures_still_mean_what_they_meant(
    tmp_path: Path,
) -> None:
    """FR-001: the 008 detection tests' meaning, asserted on their own text.

    The compatibility contract is not an assertion about this feature's code
    alone — it is the claim that the 008 suite needs no edit. Re-created here
    from `tests/test_operator_question.py`'s own bodies: the genuine marker
    case, the multi-marker case, the fenced-block case, and the prose case all
    produce exactly the answers they produced before the grammar existed.
    """
    # The genuine-marker case: body extracted verbatim, no addressee.
    stdout = f"Here is the work so far.\n\nI wrote the detection module.\n\n{MARKER}\n{OPERATOR_BODY}\n"
    marker = detect_operator_question(_archive(tmp_path, stdout=stdout, name="a1"))
    assert marker is not None
    assert marker.text == OPERATOR_BODY.strip()
    assert marker.addressee is None

    # Only the final marker counts.
    twice = (
        f"{MARKER}\nFirst question, withdrawn.\n\n"
        "I kept working and resolved that.\n\n"
        f"{MARKER}\nSecond question, the real fork.\n"
    )
    marker = detect_operator_question(_archive(tmp_path, stdout=twice, name="a2"))
    assert marker is not None
    assert marker.text == "Second question, the real fork."
    assert marker.addressee is None

    # A marker discussed in prose is not a question.
    prose = (
        "I considered using the heading `## OPERATOR QUESTION` to flag a fork, "
        "but decided against it.\n"
    )
    assert detect_operator_question(_archive(tmp_path, stdout=prose, name="a3")) is None

    # A marker inside a fence is not a question.
    fenced = (
        "The contract says:\n\n```\n## OPERATOR QUESTION\n<the fork>\n```\n\n"
        "I followed it where I could.\n"
    )
    assert detect_operator_question(_archive(tmp_path, stdout=fenced, name="a4")) is None


def test_the_marker_heading_is_unchanged_by_the_grammar() -> None:
    """FR-001: the heading the prompt teaches and the detector matches is 008's.

    The addressee is a line inside the body, so the heading contract — level
    two, exactly spelled — is what it was. An agent taught by an 008 prompt is
    recognised, addressee or no.
    """
    assert QUESTION_HEADING == "## OPERATOR QUESTION"


# --- the address line's shape ------------------------------------------------


def test_an_address_line_written_inline_is_body_not_an_addressee() -> None:
    """The line must start the body: `To:` mid-text is prose, not an address.

    A question that mentions an addressee in its middle is asking the operator
    about a peer, not asking the peer — and a parser that read any `To:` line
    would route operator questions to nodes that were never addressed.
    """
    from factory.workgraph.peers import parse_addressee

    body = f"Should I ask {ADDRESSEE_LINE} about this, or is it yours?\n\nWhich?"
    parsed = parse_addressee(body)

    assert parsed.addressee is None
    assert parsed.body == body.strip()


def test_an_address_line_in_a_fenced_block_is_body_not_an_addressee() -> None:
    """A `To:` line inside a fence is quoted grammar, the way a quoted marker is.

    The 008 rule R9 generalises: a heading quoted in a code block is
    documentation of the marker, not a marker, and an address line quoted the
    same way is documentation of the grammar, not an address.
    """
    from factory.workgraph.peers import parse_addressee

    body = (
        "The plan's example says:\n\n"
        "```\n"
        "To: us2\n"
        "<the question>\n"
        "```\n\n"
        "Does the implementation match that example?"
    )
    parsed = parse_addressee(body)

    assert parsed.addressee is None
    assert "To: us2" in parsed.body


def test_a_case_variant_of_the_address_line_still_addresses() -> None:
    """`to:` and `TO:` address the same as `To:` — one grammar, not three.

    The address line is a wire shape the prompt teaches, and the detector
    matches. Case is not part of what the prompt can reliably teach, so the
    parse accepts it — the same way the criteria parser accepts the template's
    key words in either case — rather than silently paging the operator about
    a question the agent spelled `TO:` and meant for a peer.
    """
    from factory.workgraph.peers import parse_addressee

    parsed = parse_addressee(f"to: us2\n{PEER_BODY}")
    assert parsed.addressee == "us2"

    parsed = parse_addressee(f"TO: us2\n{PEER_BODY}")
    assert parsed.addressee == "us2"


def test_an_address_line_surrounded_by_spaces_still_addresses() -> None:
    """A leading blank line above the address does not orphan the address.

    Agents wrap headings in blank lines; a parse that demanded the address at
    line zero would miss every question an agent formatted the way this
    factory's own prose formats headings. Whitespace before the line and
    around the name is not content.
    """
    from factory.workgraph.peers import parse_addressee

    parsed = parse_addressee(f"\n  To:  us2  \n{PEER_BODY}")

    assert parsed.addressee == "us2"
    assert parsed.body == PEER_BODY.strip()


def test_an_empty_addressee_name_is_no_addressee() -> None:
    """`To:` with nothing after it is not an address to a name that does not
    exist — routing would refuse it, so the grammar must not produce it.

    The one shape the grammar owns outright: an address line that names nobody
    is body text, the same way an empty body under a marker is no question.
    """
    from factory.workgraph.peers import parse_addressee

    parsed = parse_addressee(f"To:\n{PEER_BODY}")

    assert parsed.addressee is None
    assert parsed.body == f"To:\n{PEER_BODY}".strip()


def test_an_addressee_name_may_carry_a_hyphen_or_digit() -> None:
    """Node ids, story keys and persona names are the legal names — the grammar
    must accept every shape the registry and the graph spell.

    `us1`, `us2`, `architect`, `017-peer-channel` — the namespace is the
    routing table's, and the grammar must not silently reject a name the table
    accepts.
    """
    from factory.workgraph.peers import parse_addressee

    for name in ("us2", "architect", "us10", "017-peer-channel"):
        parsed = parse_addressee(f"To: {name}\n{PEER_BODY}")
        assert parsed.addressee == name, name


def test_an_addressee_name_may_not_carry_a_space() -> None:
    """One address, one name: a second word is body, not a list of recipients.

    A `To:` line naming two nodes would need a semantics this story does not
    have, and guessing one silently — first wins, say — routes a question to
    one peer while the asker believes it reached both. The line is body when
    it is not exactly one name.
    """
    from factory.workgraph.peers import parse_addressee

    parsed = parse_addressee(f"To: us2 and us3\n{PEER_BODY}")

    assert parsed.addressee is None
    assert parsed.body.startswith("To: us2 and us3")


# --- the malformed and infrastructure cases 008 owns, unchanged -------------


def test_a_marker_with_an_addressee_but_no_body_is_malformed(tmp_path: Path) -> None:
    """008's rule, unchanged by the address: a question with no content parks
    nothing, and an address line alone is not content.

    There is nothing to route, so there is no message — the detector returns
    None and the attempt falls through to today's grading, exactly as it did
    before the grammar existed.
    """
    stdout = f"{MARKER}\n{ADDRESSEE_LINE}\n"
    assert detect_operator_question(_archive(tmp_path, stdout=stdout)) is None

    stdout = f"{MARKER}\n{ADDRESSEE_LINE}\n   \n  \n"
    assert detect_operator_question(_archive(tmp_path, stdout=stdout)) is None


def test_a_missing_transcript_is_still_an_infrastructure_failure(tmp_path: Path) -> None:
    """The detector's read half is untouched by the grammar: a vanished archive
    raises rather than reading as a clean attempt that asked nothing."""
    with pytest.raises(TranscriptReadError):
        detect_operator_question(tmp_path / "no" / "such" / "dir")