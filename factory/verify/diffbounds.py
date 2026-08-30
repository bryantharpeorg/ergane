"""How big a diff is, how much the judge may be shown, and how much is too much.

The last two are separate settings and used to be one (092 FR-001).
`judge.prepare_diff` abridges to the attention budget, and — since 045 FR-003 —
`diffcheck.check_output` refuses above the refusal threshold, so that an attempt
whose diff cannot carry its own evidence fails deterministically instead of
buying a verdict formed partly out of elisions. What the two must agree on is
not a number but a *measurement*: they weigh the same assembly, and the number
each weighs it against is now its own. They cannot both reach it
through `factory/verify/judge.py`: that module is the component's only LLM edge
and its only outbound HTTP call, and exactly one module in the component may
import it (FR-009, enforced on the import graph by
`tests/test_verification_sweep.py`). That fence is worth more than the
convenience of a shared constant, and it says something precise — *importing the
judge means you can spend money* — which a pure byte count has no business
weakening.

So the pure half lives here: both caps, the split of a unified diff into one
section per file, the measurement that turns "too big" into a refusal an
operator can act on, and — since 092 FR-007 — that same measurement stated as a
record of how much of the diff the judge was shown, so a PASS taken on an
abridgement is not read later as one taken on the whole thing. Nothing here talks to a model, reads a credential, or
knows what a verdict is. `judge.py` keeps the budgeting and the truncation that
spends the attention budget, unchanged; this module is what both readers of a
diff's size count with, so they cannot drift into two answers.

The measurement is deliberately not a call to `prepare_diff`. That function's
truncation is the defense in depth behind the new check and is left exactly as
it was; asking it to measure would make the floor depend on the thing it stands
in front of.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from factory.verify.models import DiffAbridgement, DiffFileSize, DiffSizeRefusal

#: Diff bytes the judge may be shown (R6). ~16k tokens: comfortable beside the
#: criteria and instructions in any cheap-tier model's context. Raised from
#: 60 KiB on 2026-08-17 at the operator's direction — the original value was
#: a comfort margin, not a measurement, and its first false positive was a
#: fully-green story refused four times at 61,725 bytes (035/us1). Still an
#: attention budget, not a context limit: raise it only deliberately.
DIFF_INPUT_LIMIT = 64 * 1024

#: Diff bytes above which a story is refused unjudged (092 FR-001) — the second
#: question the constant above was answering on its own, and the reason that
#: comment reads as an argument about a model: it is one, and it was never an
#: argument about this. What the judge may be shown is a property of the model.
#: What may be refused unbuilt is a property of the work and of the operator's
#: tolerance, and sharing one name meant tuning either silently moved the other
#: — measured as a story no attempt could pass at 74,465 bytes, four gates green
#: and the judge never reached.
#:
#: Defined *as* the attention budget rather than as a second `64 * 1024`, and
#: both halves of that matter. One definition of each value, so tuning the
#: threshold cannot be undone by a copy somewhere else (092 trap 2). And a
#: default equal to the budget rather than pinned to today's bytes, because a
#: threshold below the budget refuses every diff the judge would merely have
#: abridged — the defect under a new name — so this is the floor of the range a
#: manifest may declare, and it stays the floor if the budget ever moves. The
#: dial an operator turns is the manifest key, not this line.
DIFF_REFUSAL_THRESHOLD = DIFF_INPUT_LIMIT

#: How many of the diff's biggest files an oversize refusal names (045 FR-003).
#: Bounded because this list is quoted verbatim into the next attempt's prompt:
#: a committed session home is eighteen files, and naming every one of them
#: turns the actionable half of the feedback into a wall to read past. The
#: biggest few are what end the hunt.
OVERSIZE_FILES_NAMED = 5

_SECTION_SPLIT_RE = re.compile(r"(?m)^(?=diff --git )")
_FILE_HEADER_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)")


@dataclass(frozen=True)
class DiffSection:
    """One file's slice of a unified diff, with its own stat line."""

    path: str | None
    text: str
    added: int
    removed: int

    @property
    def size(self) -> int:
        return len(self.text.encode("utf-8"))


def split_sections(diff_text: str) -> tuple[str, list[DiffSection]]:
    """Split a unified diff into its leading text and one section per file."""
    preamble = ""
    sections: list[DiffSection] = []

    for chunk in _SECTION_SPLIT_RE.split(diff_text):
        if not chunk:
            continue
        header = _FILE_HEADER_RE.match(chunk)
        if header is None:
            # Only the leading chunk can lack a `diff --git` header; git emits
            # nothing there, but a caller may have prefixed a summary.
            preamble += chunk
            continue
        sections.append(DiffSection(header.group(1), chunk, *count_changes(chunk)))

    return preamble, sections


def count_changes(text: str) -> tuple[int, int]:
    """`(added, removed)` content lines, ignoring the `---`/`+++` file headers."""
    added = removed = 0
    for line in text.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def file_listing(sections: Sequence[DiffSection]) -> str:
    """The always-complete file list and stat summary that heads the diff."""
    named = [section for section in sections if section.path]
    if not named:
        return ""
    lines = [f"Changed files ({len(named)}):"]
    lines += [
        f"  {section.path} | +{section.added} -{section.removed}" for section in named
    ]
    return "\n".join(lines) + "\n\n"


def assembled(diff_text: str) -> tuple[int, list[DiffSection]]:
    """What this diff would cost the judge's prompt, and what spent it.

    The one measurement both limits are compared against, and the reason it is
    a function rather than a line inside each of them: the refusal, the
    abridgement record and `prepare_diff` all weigh the *assembly* — the
    always-complete file listing, plus the preamble, plus every file's section —
    and two of them weighing something else would disagree exactly at the margin
    where one elides and the other calls the diff whole (092 trap 3).

    A diff with no `diff --git` header at all is one unnamed section, which is
    the reading `prepare_diff` gives it too, so the caps apply to it either way.
    """
    preamble, sections = split_sections(diff_text)
    if not sections:
        sections = [DiffSection(None, preamble, *count_changes(preamble))]
        preamble = ""

    whole = file_listing(sections) + preamble + "".join(s.text for s in sections)
    return len(whole.encode("utf-8")), sections


def abridgement(diff_text: str, *, limit: int = DIFF_INPUT_LIMIT) -> DiffAbridgement:
    """How much of `diff_text` the judge may be shown, recorded either way.

    A record and never `None`, because both outcomes are claims worth making:
    over the budget the judge rules on an abridgement and a PASS has to say so
    (092 FR-007), and under it the row states that the judge read the diff
    whole rather than leaving a reader to infer it from a missing field.
    Whether the abridger will actually cut anything is `total > budget`, the
    same comparison `prepare_diff` makes on the same bytes; nothing here calls
    it, because a measurement taken by running the thing being measured would
    make this record depend on the mechanism it describes.

    `limit` is the judge's attention budget and defaults to `DIFF_INPUT_LIMIT` —
    a property of the model, separate since 092 FR-001 from the refusal
    threshold `size_refusal` compares against. Spelled `limit` rather than
    `budget` for the reason `tests/test_final_sweep.py` enforces: this component
    may not speak enforcement vocabulary in code, because a module that can
    spell a cap is one line from sending one (D-021).
    """
    total, _sections = assembled(diff_text)
    return DiffAbridgement(total_bytes=total, limit_bytes=limit)


def size_refusal(
    diff_text: str, *, limit: int = DIFF_REFUSAL_THRESHOLD
) -> DiffSizeRefusal | None:
    """What `diff_text` would cost the judge, iff that is more than may be spent.

    `None` means this diff is small enough to be judged, which is the case the
    output check must leave untouched — an answer, not an omission. It does not
    mean the judge will see all of it: between the attention budget and this
    threshold the diff is abridged and the verdict says so, which is the outcome
    092 exists to make reachable. Anything else is the refusal `check_output`
    records instead of buying a completion it would then have to distrust
    (045 FR-003).

    `limit` is the *refusal threshold* and defaults to it; `prepare_diff` reads
    the attention budget. Two limits, one measurement: the bytes the judge's
    prompt actually carries — the always-complete file listing, plus the
    preamble, plus every file's section. That assembly is what `prepare_diff`
    compares against its own cap, so measuring the raw patch here would
    disagree with it at the margin — the one place a disagreement would matter,
    because it is where one of the two would elide and the other would call the
    diff whole.

    The per-file sizes come out of the same sections, which is what lets the
    refusal name what spent the budget rather than only the total: "your diff is
    2.1 MB" starts a hunt that "`.ergane/homes/chat.json` is 1.4 MB" ends.
    """
    total, sections = assembled(diff_text)
    if total <= limit:
        return None

    named = sorted(
        (section for section in sections if section.path),
        key=lambda section: section.size,
        reverse=True,
    )
    return DiffSizeRefusal(
        total_bytes=total,
        limit_bytes=limit,
        largest_files=[
            DiffFileSize(path=section.path or "", size_bytes=section.size)
            for section in named[:OVERSIZE_FILES_NAMED]
        ],
    )
