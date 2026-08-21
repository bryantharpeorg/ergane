"""The operator's promotion-rung flag, declared once for both start verbs.

070/US5 built the ladder's third rung — a struggling node retried on a stronger
persona once its ordinary attempts are spent — and left it unreachable:
`VerificationConfig.promotion_persona` had no operator surface, so
`ladder._promotion_available` returned `False` on every floor. This module is
that surface, and it lives here rather than in either noun because
`ergane build start` and `ergane roadmap start` must offer *one* flag with one
spelling, one refusal and one default. Two copies would drift, and the drift
would be invisible until an operator typed the flag on the verb that had not
been updated.

Three things, and deliberately nothing else:

- `add_promotion_persona_flag` — the flag's single declaration.
- `checked_promotion_persona` — the pre-dispatch refusal (FR-009). A persona
  the registry does not name is refused *before* anything is started, because
  the alternative is an epic that runs its ordinary attempts, reaches the rung,
  and only then discovers it cannot resolve the persona it was told to promote
  to. That is a workflow's worth of spend to learn about a typo.
- `with_promotion_persona` — the overlay. An override, never a reset: an
  operator who omits the flag has said nothing about promotion, and saying
  nothing must not switch off a rung the target repo's manifest declared
  (`ladder.promotion_persona`, `factory/verify/factory_yaml.py`).

The flag names a *persona*, never a model (constitution VII). What that persona
runs is the registry's business, which is also why the check here is a
membership test against the registry rather than any judgement about which
personas are "stronger" — that judgement is the operator's, recorded in
`personas.yaml`.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

from factory.cli.errors import OperatorError
from factory.config import ConfigError, load_personas
from factory.verify.models import VerificationConfig

#: The one spelling. Named so a test can assert both verbs offer the same flag
#: rather than two that merely look alike.
PROMOTION_PERSONA_FLAG = "--promotion-persona"

_HELP = (
    "persona a node is promoted to once its ordinary attempts are spent "
    "(default: whatever the target repo's manifest declares, else no "
    "promotion rung)"
)


def add_promotion_persona_flag(parser: argparse.ArgumentParser) -> None:
    """Declare the flag on one start verb's parser."""
    parser.add_argument(
        PROMOTION_PERSONA_FLAG,
        default=None,
        metavar="PERSONA",
        help=_HELP,
    )


def checked_promotion_persona(name: str | None) -> str | None:
    """The declared persona, or a refusal naming it — before anything starts.

    `None` in, `None` out, without touching the registry: the default path must
    not fail on a floor whose `personas.yaml` is missing or broken, because an
    operator who did not ask for promotion has not asked for a registry read
    either (FR-010).

    The refusal lists the registry's own names. An operator who typed `cl0ser`
    needs to see both what they typed and what they could have typed; a bare
    "unknown persona" sends them to open a YAML file the message could have
    quoted. `ladder.PROMOTION_PERSONA` — the synthetic `__promotion__`
    placeholder — is refused here by construction rather than by a special
    case, because it is not a registry entry and never may be.
    """
    if name is None:
        return None

    try:
        registry = load_personas()
    except ConfigError as error:
        raise OperatorError(
            f"cannot check promotion persona '{name}': {error}"
        ) from error

    if name not in registry:
        known = ", ".join(sorted(registry))
        raise OperatorError(
            f"promotion persona '{name}' is not in the persona registry; "
            f"known personas: {known}"
        )
    return name


def with_promotion_persona(
    config: VerificationConfig, persona: str | None
) -> VerificationConfig:
    """`config` with the operator's rung on top, or `config` unchanged.

    One field moves. Every other ladder dial belongs to whoever set it — the
    manifest at dispatch, or the deployment default — and this flag has no
    standing over any of them.
    """
    if persona is None:
        return config
    return replace(config, promotion_persona=persona)
