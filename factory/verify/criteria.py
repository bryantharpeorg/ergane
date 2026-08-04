"""The mechanical reader of Spec Kit feature specs — no LLM, ever (D-023).

Everything downstream is built on what this module returns: a node is dispatched
against requirement keys it produces, the judge scores a diff against exactly the
scenarios it captured (FR-003), and drift detection compares the hash it took.
That is the whole reason parsing is a pure function over markdown rather than a
model call — a parser that hallucinated one acceptance criterion would move the
goalposts under a node without leaving a trace, and no amount of judging
downstream would catch it (constitution IV).

The grammar is the Spec Kit feature-spec template, four productions wide
(architecture §2): `### User Story <n> - <title> (Priority: P<m>)`,
`**Acceptance Scenarios**:` introducing a numbered list, the bold
**Given**/**When**/**Then**/**And** steps inside each item, and
`- **FR-###**: <body>` bullets. Nothing else in the template is criteria: the
prioritisation note, the human's independent-test recipe, Key Entities and
Success Criteria bullets are all read past.

Four rules do most of the work here:

- **Fences are masked before anything else is scanned.** Real specs quote the
  template — this repo's own do — so a `### User Story 8` or a `- **FR-900**:`
  inside a fenced block is text about requirements, not a requirement. Leaking
  one would fabricate criteria the node was never dispatched against, which is
  the same failure as hallucinating one.
- **Identity is declared, not positional.** `US<n>` comes from the number the
  header states, so deleting the first story does not silently renumber the
  second and re-point every verdict already stored against it. Scenario ids are
  the exception and say so: `US<n>-S<k>` uses the item's position in its list,
  because the enumerator in the markdown is what humans mistype.
- **Unverifiable input is refused, naming the offender.** A story with no
  scenarios, an FR with no MUST/SHALL, an item with no keyword steps, a
  duplicated key: each raises `CriteriaParseError` carrying the one requirement
  at fault. The audience is an operator who has to go edit one line of one spec,
  so the message says which line — and mentions no sibling requirement, so the
  name in the error is unambiguous.
- **A spec is valid as a whole or not at all.** `load_criteria` validates the
  entire file before filtering to the requested keys. The alternative — validate
  lazily, only what was asked for — would let two nodes disagree about whether
  the same system-of-record file is usable.

Two representations of every scenario travel onward on purpose. `raw_text` is
the source item byte-for-byte, enumerator and line breaks included, for the
prompt to quote; `steps` unwraps those line breaks and splits on the four
keywords, for anything that needs to read the criterion. Splitting on the
keywords specifically — not on "a bold run" — is what keeps a phrase like
**no spend cap** inside its **Then** instead of becoming a step of its own.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from factory.verify.models import CriteriaSet, Requirement, RequirementKind, Scenario

# Grammar (architecture §2) ---------------------------------------------------

#: Any ATX header, at any level; the level decides where a story section ends.
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

#: A story header's text, e.g. `User Story 2 - Return a book (Priority: P2)`.
#: The dash is spelled three ways because specs are written by hand.
_STORY_RE = re.compile(
    r"^User Story\s+(\d+)\s*[-–—]\s*(.+?)\s*\(Priority:\s*(P\d+)\)$"
)

#: A functional-requirement bullet. `SC-###` and `- **Loan**:` shapes miss it by
#: design — only `FR-###` bullets declare requirements.
_FR_RE = re.compile(r"^-\s+\*\*(FR-\d+)\*\*:\s*(.*)$")

#: The label introducing a story's numbered scenario list.
_SCENARIOS_MARKER_RE = re.compile(r"^\*\*Acceptance Scenarios\*\*:?\s*$")

#: A numbered list item at the left margin; continuations are indented under it.
_ITEM_RE = re.compile(r"^(\d+)\.\s+(.*)$")

#: The four keywords that begin a step. Bold that is not one of them is emphasis.
_STEP_RE = re.compile(r"\*\*(?:Given|When|Then|And)\*\*")

#: A template label line (`**Why this priority**:`) — where a narrative stops.
_LABEL_RE = re.compile(r"^\*\*[^*]+\*\*:")

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")

#: An FR body without one of these states no obligation, so nothing can be
#: scored against it.
_OBLIGATION_KEYWORDS = ("MUST", "SHALL")


class CriteriaParseError(ValueError):
    """A spec that cannot be dispatched against, and which requirement is why.

    `offender` is the requirement key (`US2`, `FR-002`) or scenario id
    (`US1-S2`) at fault — the store and the `CRITERIA_PARSE_FAILED` activity
    error carry it, and tests assert on it rather than on prose. The rendered
    message names that one requirement and no other: an error that listed its
    well-formed siblings would send the operator to the wrong line.
    """

    def __init__(self, offender: str, problem: str, line: int | None = None) -> None:
        where = f" (line {line})" if line is not None else ""
        super().__init__(f"{offender}{where}: {problem}")
        self.offender = offender
        self.problem = problem
        self.line = line


# Parsing ---------------------------------------------------------------------


def parse_spec(text: str) -> list[Requirement]:
    """Extract every requirement a Spec Kit feature spec declares, in file order.

    Raises `CriteriaParseError` on the first violation found; the file is either
    wholly usable or not usable at all.
    """
    lines = text.splitlines()
    in_code = _mask_fences(lines)

    requirements: list[Requirement] = []
    declared_at: dict[str, int] = {}
    index = 0
    while index < len(lines):
        if in_code[index]:
            index += 1
            continue

        header = _HEADER_RE.match(lines[index])
        if header:
            story = _STORY_RE.match(header.group(2))
            if story:
                end = _section_end(lines, in_code, index, level=len(header.group(1)))
                requirement = _parse_story(lines, in_code, index, end, story)
                _declare(requirements, declared_at, requirement, index + 1)
                # A story owns its whole section: requirement bullets quoted
                # inside one are that story's prose, not declarations.
                index = end
                continue
            index += 1
            continue

        bullet = _FR_RE.match(lines[index])
        if bullet:
            end = _bullet_end(lines, in_code, index)
            requirement = _parse_functional(lines, index, end, bullet)
            _declare(requirements, declared_at, requirement, index + 1)
            index = end
            continue

        index += 1

    return requirements


def _declare(
    requirements: list[Requirement],
    declared_at: dict[str, int],
    requirement: Requirement,
    line: int,
) -> None:
    """Append a requirement, refusing a key the spec already declared.

    Last-write-wins would hand two nodes different criteria for the same key;
    first-wins would hide the second author's requirement entirely.
    """
    if requirement.key in declared_at:
        raise CriteriaParseError(
            requirement.key,
            "requirement key is declared twice "
            f"(first at line {declared_at[requirement.key]}); "
            "a key must identify exactly one requirement",
            line,
        )
    declared_at[requirement.key] = line
    requirements.append(requirement)


def _mask_fences(lines: Sequence[str]) -> list[bool]:
    """Flag every line inside (or delimiting) a fenced code block.

    A fence closes only on the same character at least as long as the one that
    opened it, so a ```` ``` ```` quoted inside a ```` ```` ```` block stays
    inert. An unclosed fence masks to end of file — the conservative direction:
    a spec whose fences do not balance yields fewer requirements, never invented
    ones.
    """
    masked: list[bool] = []
    fence_char = ""
    fence_width = 0
    for line in lines:
        match = _FENCE_RE.match(line)
        if not fence_char:
            if match:
                fence_char = match.group(1)[0]
                fence_width = len(match.group(1))
            masked.append(bool(match))
            continue
        masked.append(True)
        closes = (
            match is not None
            and match.group(1)[0] == fence_char
            and len(match.group(1)) >= fence_width
            and not match.group(2).strip()
        )
        if closes:
            fence_char = ""
            fence_width = 0
    return masked


def _section_end(
    lines: Sequence[str], in_code: Sequence[bool], start: int, level: int
) -> int:
    """The line index where the section opened at `start` stops.

    A header at the same level or shallower ends it — which is what keeps
    `### Edge Cases` and `### Functional Requirements` out of the last story.
    """
    for index in range(start + 1, len(lines)):
        if in_code[index]:
            continue
        header = _HEADER_RE.match(lines[index])
        if header and len(header.group(1)) <= level:
            return index
    return len(lines)


def _parse_story(
    lines: Sequence[str],
    in_code: Sequence[bool],
    start: int,
    end: int,
    header: re.Match[str],
) -> Requirement:
    number, title, priority = header.group(1), header.group(2), header.group(3)
    key = f"US{number}"

    marker = _find_scenarios_marker(lines, in_code, start, end)
    if marker is None:
        raise CriteriaParseError(
            key,
            "user story declares no acceptance scenarios; a story with nothing "
            "to accept cannot gate a node",
            start + 1,
        )

    items = _collect_items(lines, in_code, marker + 1, end)
    if not items:
        raise CriteriaParseError(
            key,
            "user story lists no acceptance scenarios under its "
            "**Acceptance Scenarios** heading",
            marker + 1,
        )

    scenarios = [
        _parse_scenario(key, position, item_start, lines[item_start:item_end])
        for position, (item_start, item_end) in enumerate(items, start=1)
    ]
    return Requirement(
        key=key,
        kind=RequirementKind.STORY,
        title=title,
        priority=priority,
        body=_narrative(lines, in_code, start + 1, end),
        scenarios=scenarios,
    )


def _find_scenarios_marker(
    lines: Sequence[str], in_code: Sequence[bool], start: int, end: int
) -> int | None:
    for index in range(start + 1, end):
        if not in_code[index] and _SCENARIOS_MARKER_RE.match(lines[index]):
            return index
    return None


def _narrative(
    lines: Sequence[str], in_code: Sequence[bool], start: int, end: int
) -> str:
    """The story's own words: everything before the first template label.

    `**Why this priority**` and `**Independent Test**` are notes to the humans
    triaging the spec, not acceptance criteria, and the judge prompt carries
    this body verbatim.
    """
    collected: list[str] = []
    for index in range(start, end):
        if in_code[index]:
            break
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            # A blank line is not the end: a narrative may run to several
            # paragraphs, and they all stop where a single one would.
            continue
        if (
            _LABEL_RE.match(line)
            or _HEADER_RE.match(line)
            or _ITEM_RE.match(line)
            or stripped.startswith(("-", "*", "---"))
        ):
            break
        collected.append(stripped)
    return " ".join(collected)


def _collect_items(
    lines: Sequence[str], in_code: Sequence[bool], start: int, end: int
) -> list[tuple[int, int]]:
    """Half-open spans of the numbered items in one scenario list.

    The list ends at the first non-blank line that is neither an item nor a
    continuation of one — a `---`, the next label, a fence. Blank lines between
    items do not end it, because specs are written both ways.
    """
    items: list[tuple[int, int]] = []
    index = start
    while index < end:
        if in_code[index]:
            break
        if not lines[index].strip():
            index += 1
            continue
        if not _ITEM_RE.match(lines[index]):
            break
        item_end = index + 1
        while (
            item_end < end
            and not in_code[item_end]
            and lines[item_end].strip()
            and lines[item_end][:1].isspace()
        ):
            item_end += 1
        items.append((index, item_end))
        index = item_end
    return items


def _parse_scenario(
    story_key: str, position: int, start: int, item_lines: Sequence[str]
) -> Scenario:
    scenario_id = f"{story_key}-S{position}"
    raw_text = "\n".join(item_lines)

    head = _ITEM_RE.match(item_lines[0])
    assert head is not None  # _collect_items only yields matching lines
    unwrapped = " ".join(
        part
        for part in [head.group(2).strip(), *(line.strip() for line in item_lines[1:])]
        if part
    )

    boundaries = [match.start() for match in _STEP_RE.finditer(unwrapped)]
    if not boundaries:
        raise CriteriaParseError(
            scenario_id,
            "acceptance scenario states no **Given**/**When**/**Then** steps, so "
            "there is nothing for the judge to score",
            start + 1,
        )

    edges = [*boundaries, len(unwrapped)]
    steps = [
        unwrapped[edges[i] : edges[i + 1]].strip() for i in range(len(boundaries))
    ]
    return Scenario(scenario_id=scenario_id, steps=steps, raw_text=raw_text)


def _bullet_end(lines: Sequence[str], in_code: Sequence[bool], start: int) -> int:
    end = start + 1
    while (
        end < len(lines)
        and not in_code[end]
        and lines[end].strip()
        and lines[end][:1].isspace()
    ):
        end += 1
    return end


def _parse_functional(
    lines: Sequence[str], start: int, end: int, bullet: re.Match[str]
) -> Requirement:
    key = bullet.group(1)
    continuations = (line.strip() for line in lines[start + 1 : end])
    body = " ".join(
        part for part in [bullet.group(2).strip(), *continuations] if part
    )
    if not any(keyword in body for keyword in _OBLIGATION_KEYWORDS):
        raise CriteriaParseError(
            key,
            "functional requirement states no obligation (MUST or SHALL), so it "
            "cannot be passed or failed",
            start + 1,
        )
    return Requirement(
        key=key,
        kind=RequirementKind.FUNCTIONAL,
        title=None,
        priority=None,
        body=body,
        scenarios=[],
    )


# Selection -------------------------------------------------------------------


def select_requirements(
    requirements: Sequence[Requirement], keys: Sequence[str]
) -> list[Requirement]:
    """Narrow a parsed spec to the keys a node was dispatched against.

    No keys means the whole spec, in document order. A requested key the spec
    does not declare is an error rather than an empty result: a node verified
    against nothing would pass on an empty diff, which is precisely the failure
    FR-004 exists to prevent.
    """
    if not keys:
        return list(requirements)

    by_key = {requirement.key: requirement for requirement in requirements}
    selected: list[Requirement] = []
    for key in keys:
        requirement = by_key.get(key)
        if requirement is None:
            raise CriteriaParseError(
                key, "requested requirement key is not declared in this spec"
            )
        selected.append(requirement)
    return selected


# Snapshotting ----------------------------------------------------------------


def load_criteria(
    source: str | Path,
    *,
    feature: str,
    spec_ref: str,
    requirement_keys: Sequence[str] | None = None,
    snapshotted_at: str | None = None,
) -> CriteriaSet:
    """Read, validate and snapshot a feature spec for one node's dispatch.

    The hash covers the file's raw bytes, not the parsed requirements: drift
    detection (R8) asks "did the system of record change under this node?", and
    a whitespace edit that changes no criterion still means the operator has been
    editing the spec mid-flight. Flagging that is cheap; missing a real change
    because it happened to parse the same is not.

    A missing file raises `FileNotFoundError` rather than `CriteriaParseError` —
    the activity maps the two to different errors (`CRITERIA_FILE_MISSING` vs
    `CRITERIA_PARSE_FAILED`) because one is a wiring mistake and the other is a
    spec to go fix.
    """
    path = Path(source)
    raw = path.read_bytes()
    requirements = select_requirements(
        parse_spec(raw.decode("utf-8")), requirement_keys or []
    )
    return CriteriaSet(
        feature=feature,
        spec_ref=spec_ref,
        requirements=requirements,
        source_path=str(source),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        snapshotted_at=snapshotted_at or _utc_now(),
    )


def _utc_now() -> str:
    stamped = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return stamped.replace("+00:00", "Z")
