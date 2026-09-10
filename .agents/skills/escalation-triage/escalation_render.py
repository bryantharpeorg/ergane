"""Prepare an escalation observation brief without answering the escalation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


UNKNOWN = "<unknown>"
UNAVAILABLE = "<unavailable>"


def _value(value: Any) -> str:
    if value is None or value == "":
        return UNKNOWN
    return str(value)


def _proposal(choices: Sequence[str], requested: Any) -> str:
    if not choices:
        return "choices unavailable"
    if requested is None:
        proposal = choices[0]
    elif requested not in choices:
        raise ValueError(f"proposed answer {requested!r} is not offered")
    else:
        proposal = requested
    return f"proposed answer: {proposal}"


def render_brief(
    escalation: Mapping[str, Any],
    *,
    mutations: Any | None = None,
) -> str:
    """Render the offered choices and one proposed, unanswered choice.

    ``mutations`` is a seam for denied-action tests; the renderer never calls
    it. The choice set is the one carried in the typed escalation record, not a
    fixed set of possible buttons.
    """
    del mutations
    choices = escalation.get("choices")
    if choices is None:
        choices: Sequence[str] = []
    else:
        choices = tuple(str(choice) for choice in choices)
    proposal = _proposal(choices, escalation.get("proposed_choice"))
    evidence = escalation.get("recovery_evidence", {})
    if not isinstance(evidence, Mapping):
        raise ValueError("recovery evidence must be a mapping")
    evidence_tokens = "  ".join(
        f"{key} {_value(value)}" for key, value in sorted(evidence.items())
    ) or "recovery evidence unavailable"
    choice_tokens = ", ".join(choices) if choices else "unavailable"

    return "\n".join(
        [
            f"observed: escalation {_value(escalation.get('escalation_id'))} "
            f"epic {_value(escalation.get('epic_id'))} node "
            f"{_value(escalation.get('node_id'))} expires "
            f"{_value(escalation.get('expires_at'))}",
            f"observed: {evidence_tokens}",
            f"offered choices: {choice_tokens}",
            proposal,
            "observation only: this is not an answer and no answer was sent",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="render an escalation brief")
    parser.add_argument("escalation", type=Path)
    args = parser.parse_args(argv)
    with args.escalation.open(encoding="utf-8") as source:
        document = json.load(source)
    print(render_brief(document))
    return 0


if __name__ == "__main__":
    sys.exit(main())
