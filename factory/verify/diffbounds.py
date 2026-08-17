"""How big a diff is, and how much of one the judge may be shown.

Two modules have to agree on that number. `judge.prepare_diff` abridges to it,
and — since 045 FR-003 — `diffcheck.check_output` refuses before it, so that an
attempt whose diff cannot be shown whole fails deterministically instead of
buying a verdict formed partly out of elisions. They cannot both reach it
through `factory/verify/judge.py`: that module is the component's only LLM edge
and its only outbound HTTP call, and exactly one module in the component may
import it (FR-009, enforced on the import graph by
`tests/test_verification_sweep.py`). That fence is worth more than the
convenience of a shared constant, and it says something precise — *importing the
judge means you can spend money* — which a pure byte count has no business
weakening.

So the pure half lives here: the cap, the split of a unified diff into one
section per file, and the measurement that turns "too big" into a refusal an
operator can act on. Nothing here talks to a model, reads a credential, or
knows what a verdict is. `judge.py` keeps the budgeting and the truncation that
spends this cap, unchanged; this module is what both readers of a diff's size
count with, so they cannot drift into two answers.

The measurement is deliberately not a call to `prepare_diff`. That function's
truncation is the defense in depth behind the new check and is left exactly as
it was; asking it to measure would make the floor depend on the thing it stands
in front of.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from factory.verify.models import DiffFileSize, DiffSizeRefusal

#: Diff bytes the judge may be shown (R6). ~16k tokens: comfortable beside the
#: criteria and instructions in any cheap-tier model's context. Raised from
#: 60 KiB on 2026-08-17 at the operator's direction — the original value was
#: a comfort margin, not a measurement, and its first false positive was a
#: fully-green story refused four times at 61,725 bytes (035/us1). Still an
#: attention budget, not a context limit: raise it only deliberately.
DIFF_INPUT_LIMIT = 64 * 1024

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


def size_refusal(
    diff_text: str, *, limit: int = DIFF_INPUT_LIMIT
) -> DiffSizeRefusal | None:
    """What `diff_text` would cost the judge, iff that is more than it may spend.

    `None` means the judge can be shown this diff whole, which is the case the
    output check must leave untouched — an answer, not an omission. Anything
    else is the refusal `check_output` records instead of buying a completion it
    would then have to distrust (045 FR-003).

    Measured on the bytes the judge's prompt actually carries: the
    always-complete file listing, plus the preamble, plus every file's section.
    That assembly is what `prepare_diff` compares against the cap, so measuring
    the raw patch alone would disagree with it at the margin — the one place a
    disagreement would matter, because it is where one of the two would elide
    and the other would call the diff whole.

    The per-file sizes come out of the same sections, which is what lets the
    refusal name what spent the budget rather than only the total: "your diff is
    2.1 MB" starts a hunt that "`.ergane/homes/chat.json` is 1.4 MB" ends.
    """
    preamble, sections = split_sections(diff_text)
    if not sections:
        # Not git's output (or one raw patch body): the whole thing is a single
        # unnamed section, the reading `prepare_diff` gives it too, so the cap
        # applies to it either way.
        sections = [DiffSection(None, preamble, *count_changes(preamble))]
        preamble = ""

    whole = file_listing(sections) + preamble + "".join(s.text for s in sections)
    total = len(whole.encode("utf-8"))
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
