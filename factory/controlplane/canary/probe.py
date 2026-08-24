"""Judge canary probe.

Asks a single alias "can this model judge?" by sending it a toy diff, acceptance
criteria and a required JSON verdict schema.  A model that returns prose, a
schema-violating object, or the wrong verdict on a known-bad diff fails the
canary with a distinct reason.

The canary runs under the same minted-key discipline as the existing alias
probes (`factory/controlplane/verify.py:420-460`).  It is deliberately not wired
into `LLMProbe.gather`; the install interview calls it for the operator's
chosen judge alias and reuses `LLMProbe`'s client seam.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from factory.controlplane.canary.diff import (
    CANARY_CRITERIA,
    KNOWN_BAD_DIFF,
    VERDICT_SCHEMA,
    VERDICT_SCHEMA_TEXT,
)
from factory.usage.litellm_client import LiteLLMClient


@dataclass(frozen=True)
class CanaryResult:
    """Outcome of one judge-canary probe."""

    alias: str
    passed: bool
    detail: str
    request: dict[str, Any] | None = None


class CanaryFailure(Exception):
    """The canary found this alias unfit to judge."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


#: Reasoning models need real output to parse.  Empty content under a tight cap
#: looks like a broken gateway (operator memory, kimi incident).
CANARY_MAX_TOKENS = 512


def _build_canary_request(alias: str) -> dict[str, Any]:
    """Build the chat-completion request the canary sends."""
    criteria_lines = "\n".join(f"- {c}" for c in CANARY_CRITERIA)
    content = (
        "You are judging whether a code change satisfies acceptance criteria.\n\n"
        "Review the diff below and respond with ONLY a JSON object matching this "
        f"schema: {VERDICT_SCHEMA_TEXT}\n\n"
        f"{criteria_lines}\n\n"
        "```diff\n"
        f"{KNOWN_BAD_DIFF}"
        "```\n"
    )
    return {
        "model": alias,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": CANARY_MAX_TOKENS,
    }


def _parse_verdict(raw_content: str | None) -> dict[str, Any]:
    """Parse the model's content as JSON and validate against the schema.

    Returns the parsed object on success.  Raises `CanaryFailure` with a reason
    naming the broken check on schema violation or prose.
    """
    if raw_content is None or not raw_content.strip():
        raise CanaryFailure("canary response was empty")

    content = raw_content.strip()

    # Common wrapper around JSON: markdown fenced code block.
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise CanaryFailure(f"canary response was not valid JSON: {type(exc).__name__}") from exc

    if not isinstance(parsed, dict):
        raise CanaryFailure(f"canary response JSON was {type(parsed).__name__}, expected object")

    required = set(VERDICT_SCHEMA.get("required", []))
    missing = required - set(parsed)
    if missing:
        raise CanaryFailure(
            f"canary response JSON missing required field(s): {', '.join(sorted(missing))}"
        )

    extra = set(parsed) - set(VERDICT_SCHEMA.get("properties", {}))
    if extra and VERDICT_SCHEMA.get("additionalProperties") is False:
        raise CanaryFailure(
            f"canary response JSON has disallowed extra field(s): {', '.join(sorted(extra))}"
        )

    verdict = parsed.get("verdict")
    allowed = VERDICT_SCHEMA.get("properties", {}).get("verdict", {}).get("enum")
    if allowed and verdict not in allowed:
        raise CanaryFailure(
            f"canary response JSON verdict was {verdict!r}, expected one of {allowed}"
        )

    return parsed


def _check_verdict(parsed: dict[str, Any]) -> None:
    """Confirm the parsed verdict FAILs the known-bad diff."""
    verdict = parsed.get("verdict")
    if verdict != "FAIL":
        raise CanaryFailure(
            f"canary verdict on the known-bad diff was {verdict!r}, expected 'FAIL'"
        )


async def judge_canary(
    alias: str,
    client: LiteLLMClient,
) -> CanaryResult:
    """Run the judge canary against ``alias`` using ``client``.

    ``client`` is typically a `LiteLLMClient` minted with a short-TTL
    model-constrained key by the caller.  The canary makes one chat completion,
    demands a JSON verdict matching `VERDICT_SCHEMA`, and checks the verdict on
    the known-bad diff is ``FAIL``.
    """
    request = _build_canary_request(alias)
    response_data = await client.chat_completion(request)

    content = None
    choices = response_data.get("choices") if isinstance(response_data, dict) else None
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")

    try:
        parsed = _parse_verdict(content)
        _check_verdict(parsed)
    except CanaryFailure as exc:
        return CanaryResult(
            alias=alias,
            passed=False,
            detail=str(exc),
            request=request,
        )

    return CanaryResult(
        alias=alias,
        passed=True,
        detail="judge canary passed: returned schema-valid FAIL verdict on the known-bad diff",
        request=request,
    )
