"""What a judge's feedback may say to the next attempt, and what it may only say
to the operator (102 US3, FR-009/FR-010).

The judge is the only thing standing between a node and its own acceptance
criteria, so the one remedy it must never offer is "change the criterion". The
measured case: a criterion was unsatisfiable as drafted, the judge refused the
attempt — correctly — and its feedback offered two remediation paths, the second
being "reconcile the scenario text with…". `criteria_drift` did not fire, because
nothing had drifted; the judge had merely proposed that it should. The verdict was
right, which is exactly why the mechanism is worth fencing: carried verbatim into
the next attempt's prompt, that sentence is an instruction from the one authority
the agent may not argue with, telling it to move its own bar.

`judge.SYSTEM_PROMPT` forbids the proposal, and an instruction is a reduction in
how often this fires rather than a guarantee that it never does (plan trap 6).
This module is the enforceable half — and it is deliberately three separable
facts, not one:

- **Carried.** What the next attempt is shown. Byte-for-byte identical to the
  feedback whenever nothing was withheld, because a retry handed a reflowed
  verdict has been handed a summary of its failure rather than the failure
  (002 FR-006). Only a line that actually carried a proposal is rebuilt.
- **Proposals.** Withheld from the prompt, kept here verbatim, and surfaced on
  the operator's side (`notify.messages`) — withheld is not discarded (trap 8).
  An operator asking why an epic struggled has to be able to see that the judge
  wanted the bar moved. `JudgeVerdict.feedback` itself is never rewritten, so the
  evidence store keeps the judge's words whole.
- **Unsatisfiability reports.** Preserved *and* carried. "This criterion cannot
  be met" and "change this criterion" are one sentence apart in English (trap 7),
  and a filter that ate both would silence the report this spec exists to surface
  earlier — an unsatisfiable criterion is an operator defect, and the operator is
  the only one who can fix it.

The rule is deliberately narrow, because the asymmetry runs the other way from
`spec validate`'s: a false positive here deletes a failing attempt's only
guidance. A sentence is withheld only when an editing verb takes the bar itself
as its object — `reword the acceptance criterion`, `the scenario text should be
relaxed` — which is why `update the test to cover the criterion` survives: the
verb's object is the test. A sentence that both reports unsatisfiability and
proposes the edit is withheld from the agent and recorded under *both* headings,
so the operator loses nothing the judge said.

Pure and stdlib-only, because both callers are pure: the judge's prompt assembly
and the attempt prompt assembler, which is imported by workflow code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: What replaces a withheld proposal in the prompt. It is not silence: an agent
#: reading feedback with a hole in it invents the missing half, and the rule is
#: worth stating anyway — it is the same rule the judge is held to, said to the
#: side that would have to act on it.
WITHHELD_NOTICE = (
    "[A remediation proposing a change to the acceptance criteria was withheld "
    "from this prompt. The criteria are fixed for this node: satisfy them as "
    "written, or say why they cannot be satisfied — never edit them. The full "
    "text of what was withheld is recorded for the operator.]"
)

#: The bar itself, as a judge names it — including by scenario id, which is how
#: the shortest proposals are phrased ("reword US1-S2"). Narrow on purpose:
#: `requirement` and a bare `spec` are left out because a remediation
#: legitimately talks about the requirements file and the spec directory, and a
#: false positive costs a retry its guidance.
_TARGETS = (
    r"(?:acceptance[\s-]+)?criteri(?:on|a)"
    r"|acceptance[\s-]+scenarios?"
    r"|scenarios?[\s-]+(?:text|wording|statement|steps?)"
    r"|then[\s-]+clauses?"
    r"|the\s+bar"
    r"|spec(?:ification)?[\s-]+(?:text|wording)"
    r"|[A-Z][A-Z0-9]{0,5}-S\d+"
)

#: What disqualifies a target: the next word makes it a *thing named after* the
#: criteria rather than the criteria. This factory builds itself, so its judge
#: writes sentences like "change the criteria parser" and "the diff does not
#: update the criteria snapshot" — remediations about code, and exactly the
#: guidance a retry cannot afford to lose. Words that sharpen the bar rather
#: than rename it (`text`, `wording`) are deliberately absent.
_NOT_THE_BAR = (
    r"parser|snapshot|file|module|package|set|hash|digest|store|table|column"
    r"|field|section|block|helper|fixture|suite|tests?|code|path|layer|check"
    r"|list|dict|object|class|function|method|docstring|json|payload|record"
    r"|row|report|argument|parameter|flag|branch|repo(?:sitory)?"
)

#: Editing verbs, e-dropped so one suffix group covers the inflections
#: (`chang` + `e|es|ed|ing`). `fix` and `correct` are absent: applied to a
#: scenario they usually mean "make the code satisfy it", which is the remedy the
#: judge is supposed to offer.
_VERBS = (
    r"(?:chang|reword|rephras|rewrit|revis|restat|redefin|relax|loosen|weaken"
    r"|soften|amend|edit|updat|adjust|reconcil|align|narrow|broaden|lower|mov"
    r"|drop|remov|delet|replac|tweak|retitl|rescop)e?(?:s|d|es|ed|ing)?"
    r"|modif(?:y|ies|ied|ying)"
    r"|clarif(?:y|ies|ied|ying)"
)

_DETERMINERS = r"(?:the|this|that|these|those|its|your|our|their|a|an|any|one)"

_MODALS = r"(?:should|shall|must|could|can|may|might|ought\s+to|has\s+to|have\s+to|will)"

#: Active voice: the verb, then at most two words, then the bar. The filler can
#: never cross a sentence boundary — `\w+\s+` cannot consume `criterion.` — so
#: "Update the loan module. The criterion requires a refusal path" is not a
#: match, and neither is "update the test to assert the criterion", where the
#: verb's object is the test.
_PROPOSAL_ACTIVE = re.compile(
    rf"\b(?:{_VERBS})\b\s+(?:{_DETERMINERS}\s+)?(?:\w+\s+){{0,2}}?"
    rf"(?:{_TARGETS})\b(?!'?s?\s+(?:{_NOT_THE_BAR})\b)",
    re.IGNORECASE,
)

#: Passive voice: the bar, then a modal, then the verb close behind it. The verb
#: has to follow the modal almost immediately, or "the criterion must be
#: satisfied by changing borrow()" would read as a proposal to edit the criterion.
_PROPOSAL_PASSIVE = re.compile(
    rf"\b(?:{_TARGETS})\b(?!'?s?\s+(?:{_NOT_THE_BAR})\b)(?:\s+\w+){{0,3}}?\s+{_MODALS}\s+"
    rf"(?:probably\s+|perhaps\s+|instead\s+)?(?:needs?\s+to\s+|need\s+to\s+)?"
    rf"(?:be\s+|been\s+)?(?:{_VERBS})\b",
    re.IGNORECASE,
)

#: The report the judge *should* make. Recognised in the spellings a judge
#: actually reaches for, and kept independent of the proposal patterns: a
#: sentence can match both, and when it does the operator is told both.
_UNSATISFIABLE = re.compile(
    r"\bunsatisfiable\b|\bunprovable\b|\bnot\s+(?:provable|satisfiable)\b"
    r"|\b(?:cannot|can\s+not|can't|could\s+not|couldn't|can\s+never|impossible\s+to)"
    r"(?:\s+\w+){0,4}?\s*\b"
    r"(?:satisf\w*|met|meet|proven|proved|prove|demonstrat\w*|eviden\w*|shown|show)\b",
    re.IGNORECASE,
)

#: Sentence boundaries, and lines. Lines first, so a bulleted remediation list
#: keeps its bullets and an untouched line is emitted with its bytes intact.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

#: Collapses the gap a dropped line leaves behind. Nothing else about the
#: carried text's whitespace is touched.
_BLANK_RUN = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class ScreenedFeedback:
    """One verdict's feedback, split into who may read which sentence.

    `carried` is what the next attempt's prompt may quote — the feedback itself
    when nothing was withheld, and otherwise the surviving sentences followed by
    `WITHHELD_NOTICE`. `proposals` and `unsatisfiable_reports` are verbatim
    sentences, for the operator's surfaces; a sentence can appear in both.
    """

    carried: str
    proposals: tuple[str, ...]
    unsatisfiable_reports: tuple[str, ...]

    @property
    def withheld(self) -> bool:
        """Whether anything was kept out of `carried`."""
        return bool(self.proposals)


def proposes_criteria_change(text: str) -> bool:
    """Whether `text` proposes editing the acceptance criteria themselves."""
    return bool(_PROPOSAL_ACTIVE.search(text) or _PROPOSAL_PASSIVE.search(text))


def reports_unsatisfiable(text: str) -> bool:
    """Whether `text` reports that a criterion cannot be satisfied or proven."""
    return bool(_UNSATISFIABLE.search(text))


def screen_feedback(feedback: str) -> ScreenedFeedback:
    """Split judge feedback into what the agent may read and what only the
    operator may (FR-009, FR-010).

    Sentence-granular inside a line, line-granular outside one: a line no
    sentence of which proposes an edit is emitted byte-for-byte, and only a line
    that carried one is rebuilt from its surviving sentences. A line left empty
    by the removal is dropped rather than left as a dangling bullet.
    """
    if not feedback.strip():
        return ScreenedFeedback(feedback, (), ())

    proposals: list[str] = []
    reports: list[str] = []
    kept_lines: list[str] = []

    for line in feedback.splitlines():
        sentences = _SENTENCE_SPLIT.split(line)
        offending = [
            sentence for sentence in sentences if proposes_criteria_change(sentence)
        ]
        reports += [
            sentence for sentence in sentences if reports_unsatisfiable(sentence)
        ]

        if not offending:
            kept_lines.append(line)
            continue

        proposals += offending
        survivors = [
            sentence
            for sentence in sentences
            if sentence.strip() and sentence not in offending
        ]
        if survivors:
            kept_lines.append(" ".join(survivors))

    if not proposals:
        return ScreenedFeedback(feedback, (), tuple(reports))

    body = _BLANK_RUN.sub("\n\n", "\n".join(kept_lines)).strip()
    carried = f"{body}\n\n{WITHHELD_NOTICE}" if body else WITHHELD_NOTICE
    return ScreenedFeedback(carried, tuple(proposals), tuple(reports))
