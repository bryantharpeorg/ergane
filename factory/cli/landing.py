"""The operator's landing dials, declared once for every start verb (081-US1).

`LandingConfig` (`factory/mergequeue/models.py:379`) has said in its own
docstring since 003 that "defaults are code defaults the operator overrides per
epic; none of these is a constant buried in the workflow". Nothing overrode
them: `ergane build start` passed no landing config at all, and the two sites
that did pass one passed a bare `LandingConfig()`. So the defaults *were*
constants, and an operator who wanted an epic to stop calling a landing stalled
at two hours had no way to say so.

This module is the surface, and it lives here rather than inside a noun for the
reason `factory/cli/promotion.py` gives for the same shape: `ergane build start`
and `ergane roadmap start` must offer *one* set of flags with one spelling, one
refusal and one default. Two copies drift, and the drift is invisible until an
operator types a flag on the verb that was not updated.

Four things, and deliberately nothing else:

- `LANDING_DIAL_FLAGS` — the map from flag to `LandingConfig` field. One
  declaration, so "which dials exist" is answerable without reading a parser.
- `add_landing_dial_flags` — the declaration on one start verb's parser.
- `landing_config_from_args` — the assembler.
- `landing_overrides_from_args` — which dials the operator actually typed
  (081-US3). The assembler above deliberately loses that: a `LandingConfig` is
  five values with no memory of where each came from, and `poll_interval_s=60`
  is the same object whether the operator typed it or never mentioned it. This
  is the other half, kept beside the config rather than inside it, and it is
  what lets `ergane build status` tell "set to 60" from "defaulted to 60"
  (FR-009) instead of guessing by comparing against the defaults — a guess that
  is wrong in exactly the case the operator is checking.

**No default is written here.** The overrides are built from what the operator
actually typed and everything else is left to the dataclass, so there is no
second copy of `60` or `7200` in the CLI to drift from the model. An operator
who sets nothing gets today's epic exactly (FR-002), and that is true by
construction rather than by a matching pair of literals.

**Refusal happens at parse time** (FR-004). A negative interval or a zero poll
that reaches a workflow becomes a timer that never fires or an activity failure
hours in, with the attempt already spent; the same value refused by `argparse`
costs one line on stderr and nothing else. The shape is the one
`factory/cli/nouns/build.py`'s `_positive_int` already uses — an
`ArgumentTypeError` naming the flag and the value the operator typed.

`merge_method` is **enumerated here** rather than checked against the forge, and
that is a decision worth stating (plan trap 8). The forge cannot be asked which
methods a branch allows until there is a branch and a proposal on it, which is
hours after dispatch and exactly the "four hours later inside a workflow"
failure FR-004 exists to prevent. The three names are the merge methods a forge
offers at all; whether the *target branch* allows the one named remains the
operator's to get right, and `factory/mergequeue/github_forge.py:172` documents
that a queue-governed branch owns the method regardless. So this refuses
nonsense, not disagreement — which is the most a pre-dispatch check can honestly
do.
"""

from __future__ import annotations

import argparse
from typing import Any, Mapping

from factory.mergequeue.models import LandingConfig

#: Flag → the `LandingConfig` field it sets. The one place the mapping is
#: written; `tests/test_landing_dials_reach_the_epic.py` holds it to covering
#: every field the dataclass has, so a field added later without a flag behind
#: it fails rather than quietly becoming un-settable again (FR-001).
LANDING_DIAL_FLAGS: Mapping[str, str] = {
    "--merge-method": "merge_method",
    "--landing-poll-interval-s": "poll_interval_s",
    "--stall-after-s": "stall_after_s",
    "--max-recovery-cycles": "max_recovery_cycles",
    "--max-free-rebases": "max_free_rebases",
}

#: The merge methods a forge offers. Sorted so the refusal reads the same every
#: time.
MERGE_METHODS = ("merge", "rebase", "squash")


def _dial(flag: str, value: str, *, floor: int) -> int:
    """An `argparse` type: an integer at or above `floor`, or a usage error.

    The refusal names the dial and quotes the value back, because a message that
    says only "invalid value" sends the operator to re-read a help page it could
    have quoted; `argparse` prefixes it with `argument --stall-after-s:`, which
    is where the exact spelling to retype comes from. That split is
    `factory/cli/nouns/build.py`'s `_positive_int` convention, unchanged.

    `floor` differs by dial and the difference is meaningful: a poll interval of
    zero is a spin loop and a stall window of zero would call every landing
    stalled the instant it enqueued, so both are refused — while a *bound* of
    zero is a coherent thing to ask for ("do not recover at all", "never rebase
    for free"), and 069 already ships a test that turns `max_free_rebases` to 0
    on purpose.
    """
    complaint = f"{flag.lstrip('-')} must be an integer >= {floor}, got {value!r}"
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(complaint)
    if parsed < floor:
        raise argparse.ArgumentTypeError(complaint)
    return parsed


def _merge_method(value: str) -> str:
    """An `argparse` type: one of the forge's merge methods, or a usage error."""
    if value not in MERGE_METHODS:
        raise argparse.ArgumentTypeError(
            f"merge-method must be one of {', '.join(MERGE_METHODS)}, "
            f"got {value!r}"
        )
    return value


def add_landing_dial_flags(parser: argparse.ArgumentParser) -> None:
    """Declare every landing dial on one start verb's parser (FR-001).

    Each defaults to `None`, never to the model's value: `None` is how
    `landing_config_from_args` tells "the operator did not say" from "the
    operator asked for today's number", and only the first of those may be
    changed by a future default.

    The poll flag is `--landing-poll-interval-s` rather than
    `--poll-interval-s` on purpose. `EpicInput` already carries a
    `poll_interval_s` — the usage-poll beat (`factory/workgraph/workflow.py:481`)
    — and `ergane roadmap start` already spells *its* scan beat
    `--poll-interval-s`. Three different beats with one name is a flag an
    operator sets on the wrong thing.
    """
    parser.add_argument(
        "--merge-method",
        type=_merge_method,
        default=None,
        metavar="METHOD",
        help=(
            f"how a passing node's pull request lands "
            f"({', '.join(MERGE_METHODS)}; default: "
            f"{LandingConfig.merge_method})"
        ),
    )
    parser.add_argument(
        "--landing-poll-interval-s",
        type=lambda value: _dial("--landing-poll-interval-s", value, floor=1),
        default=None,
        metavar="SECONDS",
        help=(
            "how often a landing in the queue is polled "
            f"(default: {LandingConfig.poll_interval_s})"
        ),
    )
    parser.add_argument(
        "--stall-after-s",
        type=lambda value: _dial("--stall-after-s", value, floor=1),
        default=None,
        metavar="SECONDS",
        help=(
            "how long a landing may sit queued and unanswered before it "
            f"classifies as stalled (default: {LandingConfig.stall_after_s})"
        ),
    )
    parser.add_argument(
        "--max-recovery-cycles",
        type=lambda value: _dial("--max-recovery-cycles", value, floor=0),
        default=None,
        metavar="N",
        help=(
            "how many times a rejected landing may be recovered before the "
            f"node escalates (default: {LandingConfig.max_recovery_cycles})"
        ),
    )
    parser.add_argument(
        "--max-free-rebases",
        type=lambda value: _dial("--max-free-rebases", value, floor=0),
        default=None,
        metavar="N",
        help=(
            "how many times a landing rejected for a moved base may be rebased "
            f"and requeued for free (default: {LandingConfig.max_free_rebases})"
        ),
    )


def _typed_dials(args: Any) -> dict[str, Any]:
    """Every dial the operator actually typed, by `LandingConfig` field name.

    Read with `getattr(..., None)` rather than by attribute, and that is load
    bearing rather than defensive: `start_command` is called with hand-built
    namespaces by several tests and by neighbouring code, and a namespace that
    predates these flags means "the operator said nothing" — the same answer as
    a flag left off the command line — not an `AttributeError` at dispatch.
    """
    typed = {
        field: getattr(args, flag.lstrip("-").replace("-", "_"), None)
        for flag, field in LANDING_DIAL_FLAGS.items()
    }
    return {field: value for field, value in typed.items() if value is not None}


def landing_config_from_args(args: Any) -> LandingConfig:
    """The dials the operator typed, over today's values for the ones they did not."""
    return LandingConfig(**_typed_dials(args))


def landing_overrides_from_args(args: Any) -> tuple[str, ...]:
    """The `LandingConfig` fields the operator set, in declaration order (081-US3).

    Names, not values: the values are already in the config beside this, and a
    second copy of them would be a second thing to keep in step. What travels
    with the dispatch is only the fact that the operator named each of these,
    which is the fact a status reading cannot reconstruct from the config alone.

    A dial set to the number that is already its default is in here, and that is
    the whole point (FR-009): the operator's question is "did my flag reach the
    epic", not "is this value unusual".
    """
    return tuple(_typed_dials(args))
