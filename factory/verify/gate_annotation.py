"""What the factory adds to a gate failure that echoes install-a-toolchain advice.

`HOME` inside the gate boundary is a fresh tmpfs (`gates.py`, the mount set that
gives a gate a reproducible environment), so a toolchain the attempt installed
under `HOME` is not there when the gate runs — only the worktree crosses. The
tool that then fails says the one thing guaranteed to spend the next attempt:
*just run the install*. Recorded verbatim, that advice reaches the retry prompt
looking like the tool's considered opinion about what to do next, and the agent
does the only thing the evidence supports — installs it again, harder. Three of
four gates green and a smoke gate failing on `npx playwright install` is the
measured instance, with the browser physically present in the worktree the whole
time.

So this module is one pure function: given a gate's failure detail, return it
with the boundary's `HOME` fact appended when the detail carries a signature of
that failure, and return the detail itself otherwise. `_to_result` applies it at
the single point where every executor's outcome becomes a `GateResult`.

Four decisions, each of which the obvious alternative gets wrong.

**Appended, never substituted.** The tool's output is the evidence; deleting the
advice would also delete the thing the next attempt recognises the failure by.
The note goes after it, bracketed and self-identifying, which is the convention
`_to_result` already uses for `[worktree snapshot failed: …]` and the answer to
`tail_output`'s objection that a marker "would put the factory's own voice inside
what is supposed to be the tool's output". The voice is there; it is labelled.

**A signature, not a guess** (101 trap 7). Three named tools and the exact phrase
each of them prints. The temptation is a pattern over "install" or "not found",
and it is the wrong trade in a direction this epic has already measured: a loose
match annotates every failing gate with a `HOME` lecture, and a retry prompt full
of confident irrelevant advice is the failure US1 exists to avoid, arriving
through a second door.

**Anchored on phrases, not on line starts.** The tempting `^\\s*npx playwright
install` matches nothing, because Playwright frames its advice in box-drawing
characters and the line begins with `║`. Word-boundary multi-word phrases are
what make the match explicit here; `tests/test_101_toolchain_failure_is_annotated
.py` pins that premise against the framing the tool really emits.

**The fact carries a remedy.** This is trap 1 reaching US3. An agent given no
guidance solved this in three attempts; an agent given the mechanism stated
correctly but incompletely put the variable where the text said, stopped
searching, and failed 3/3. An annotation that says "your `HOME` is a tmpfs" and
stops is not a smaller version of the fix — it is that failure with a shorter
word count. So the note leaves the reader holding an action, and points at the
prompt section that carries the worked two-command form rather than restating it
at length inside a gate tail.

The section is named by a literal here rather than imported from
`factory.workgraph.prompt`: verification does not depend on prompt assembly, and
inverting that for a heading string would be a worse trade than pinning the two
spellings together in a test, which is what
`test_the_section_the_annotation_points_at_is_really_in_the_prompt` does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The prompt section that carries the worked remedy (101 US1). Named in the
#: annotation so an agent reading a gate tail knows where the two-command form
#: is, without this module having to be a second copy of it.
GATE_BOUNDARY_SECTION = "What does not survive to gate time"


@dataclass(frozen=True)
class InstallSignature:
    """One tool's install-a-toolchain advice, and the phrase that identifies it.

    `tool` exists so the set reads as a roster rather than as a regex soup: a
    reviewer asking "which tools does the factory recognise?" gets an answer,
    and a test can require that every declared signature is exercised by output
    the tool it names really prints.
    """

    tool: str
    pattern: re.Pattern[str]


#: The whole set (FR-009, trap 7). Small, explicit, and each entry the imperative
#: the tool prints — not a symptom, and not a keyword. Growing it is cheap and
#: should stay deliberate: every addition widens the set of gate failures that
#: get a paragraph of factory prose stapled to them.
INSTALL_SIGNATURES: tuple[InstallSignature, ...] = (
    # "Looks like Playwright Test or Playwright was just installed or updated.
    #  Please run the following command to download new browsers:
    #      npx playwright install"
    InstallSignature("playwright", re.compile(r"\bplaywright install\b")),
    # "Run `npx puppeteer browsers install chrome` to download it."
    InstallSignature("puppeteer", re.compile(r"\bpuppeteer browsers install\b")),
    # "Please reinstall Cypress by running: cypress install"
    InstallSignature("cypress", re.compile(r"\bcypress install\b")),
)


#: The fact the agent cannot see, and what to do about it. Kept to one paragraph
#: on purpose: it is joined to a gate tail whose 32 KiB budget belongs to the
#: gate's own output, and it is read on the way past.
TMPFS_HOME_ANNOTATION = (
    "[ergane: the install advice above cannot work here. This gate ran inside "
    "the verification boundary, whose `HOME` is a fresh tmpfs — not the `HOME` "
    "the attempt installed into, and empty. Only the worktree crosses that "
    "boundary, so running that install again will not change this gate. Install "
    "under the worktree instead, git-ignored, and name that path in front of "
    "the gate command too, because the tool re-reads the variable on every "
    f'invocation — the prompt\'s "{GATE_BOUNDARY_SECTION}" section has the '
    "worked form.]"
)


def matched_install_signature(detail: str) -> InstallSignature | None:
    """The first signature `detail` carries, or `None` when it carries none.

    First rather than all: the annotation is the same whichever tool asked, and
    a repository with two browser drivers should still get one note.
    """
    for signature in INSTALL_SIGNATURES:
        if signature.pattern.search(detail):
            return signature
    return None


def annotate_install_advice(detail: str) -> str:
    """`detail` with the boundary's `HOME` fact appended, or `detail` itself.

    The unmatched path returns the argument object, not a copy of it: every gate
    this factory has ever run takes that path, and identity is what makes "a
    failure matching no signature is recorded unchanged" (US3-S2) a property of
    the code rather than a coincidence about today's whitespace.
    """
    if matched_install_signature(detail) is None:
        return detail
    if not detail:
        return TMPFS_HOME_ANNOTATION
    return f"{detail}\n{TMPFS_HOME_ANNOTATION}"
