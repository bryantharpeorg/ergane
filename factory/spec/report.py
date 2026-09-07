"""The finding type and the typed report, modelled on what the verb prints today.

The finding is a frozen dataclass with `_ValidateFinding`'s attribute names and
constructor shape — positional layer and message, keyword-only `severity`
defaulting to `"refusal"` — so no relocated checker needs a signature edit
(plan trap 7). The report carries all four channels as separate members
(FR-002); the skipped channel with its reason strings is load-bearing (plan
trap 10), and neither information notes nor skipped layers may affect the
verdict (FR-002, US1-S3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The severity a finding carries when its constructor is given none. Refusal is
#: the default today and stays the default here: a checker that means to advise
#: says so at the call, as `slice_contention` and `_check_scenario_coverage` do.
REFUSAL = "refusal"
ADVISORY = "advisory"


@dataclass(frozen=True)
class SpecFinding:
    """One finding: a layer name, a severity and a message.

    The shape every layer body constructs — the same three attributes and the
    same keyword-only severity default the CLI module's private
    `_ValidateFinding` has today — frozen because a finding is a fact about a
    run, not a cell another layer edits.
    """

    layer: str
    message: str
    severity: str = REFUSAL


@dataclass(frozen=True)
class SpecValidation:
    """The typed validation report: all four channels, and a verdict.

    The four members are the four rows of the channel table in 133's spec.md:
    `refusals` and `advisories` are the findings the CLI splits on severity,
    `information` is the separate stated-not-counted list, and `skipped` holds
    the layers that did not run, each with its reason string. The verdict reads
    the refusal channel alone — the deliberate non-effect of the other three on
    the exit code is preserved by construction (US1-S3).
    """

    refusals: list[SpecFinding] = field(default_factory=list)
    advisories: list[SpecFinding] = field(default_factory=list)
    information: list[SpecFinding] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """`"pass"` unless a refusal is present, whatever else the run carries.

        Information notes and skipped layers ride their own channels and never
        move this: a sentinel is stated, a skipped layer was not checked, and
        neither is a verdict.
        """
        return "fail" if self.refusals else "pass"