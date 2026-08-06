"""A scripted stand-in for the proxy's `/chat/completions` endpoint.

The judge is one bounded chat completion (R4), so the only thing a fake has to
be good at is *replying whatever the test wants* and *remembering exactly what
it was asked*. Both halves are load-bearing:

- The reply is scripted, never inferred. A fake that derived a sensible verdict
  from the prompt would agree with the parser about what a verdict looks like,
  and the malformed-response rules (R5) are precisely where that agreement must
  not be assumed. An unscripted call is a 500 saying so, rather than a helpful
  default that would let a test pass without meaning to.
- Every request is recorded whole — headers included, as one flat string — so a
  test can assert that the master key is nowhere in it. Component 1's fake
  proves the admin client never leaks the master key; this one has to prove the
  judge never *acquires* it, because the judge authenticates with a per-attempt
  virtual key and the master key is merely sitting in the same worker
  environment (contracts/activities.md, FR-009).

The blanket 401 on a wrong `Authorization` header means every passing test here
also asserts the Bearer credential, and the 404 on any other path means a
runner that posted somewhere else fails loudly instead of silently succeeding.

Lives outside `test_judge.py` because `test_verify_activities.py` (T021) needs
the same fake for `run_judge`'s activity wrapper — the same reason
`tests/target_repo.py` sits next to it rather than inside `test_gates.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

#: The fake's base URL; `run_judge` appends `/chat/completions` to it.
JUDGE_PROXY_URL = "http://litellm.test"

#: The per-attempt virtual key component 1 mints for the judge persona. Its
#: value is a reminder, not a secret: it must not show up in an error either.
JUDGE_VIRTUAL_KEY = "sk-judge-attempt-do-not-log"

#: The LiteLLM alias a `personas.yaml` judge entry would resolve to. A stand-in
#: for a real alias — code never names a model (constitution VII).
JUDGE_MODEL_ALIAS = "fake-provider/judge-tier"


@dataclass(frozen=True)
class RecordedCompletion:
    """One request the fake received, in arrival order."""

    method: str
    url: str
    path: str
    headers: dict[str, str]
    body: dict[str, Any] | None
    raw: str

    @property
    def messages(self) -> list[dict[str, str]]:
        return list((self.body or {}).get("messages") or [])

    @property
    def system_message(self) -> str:
        return self._content("system")

    @property
    def user_message(self) -> str:
        return self._content("user")

    def _content(self, role: str) -> str:
        for message in self.messages:
            if message.get("role") == role:
                return message.get("content", "")
        return ""


class FakeJudgeProxy:
    """In-memory `/chat/completions` whose every reply the test writes."""

    def __init__(
        self,
        *,
        base_url: str = JUDGE_PROXY_URL,
        virtual_key: str = JUDGE_VIRTUAL_KEY,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.virtual_key = virtual_key

        self.calls: list[RecordedCompletion] = []

        self._script: list[dict[str, Any]] = []
        self._sticky: dict[str, Any] | None = None

        self.transport = httpx.MockTransport(self._handle)

    # --- scripting ----------------------------------------------------------

    def reply(self, content: str, *, times: int = 1) -> None:
        """Queue `times` completions carrying `content` as the assistant text."""
        self._script.extend([{"status": 200, "json": completion(content)}] * times)

    def reply_payload(self, payload: dict[str, Any], *, status: int = 200) -> None:
        """Queue an arbitrary response body — for shapes a real API never sends."""
        self._script.append({"status": status, "json": payload})

    def fail_next(self, status: int = 503, *, times: int = 1) -> None:
        self._script.extend(
            [{"status": status, "json": _error_body(status)}] * times
        )

    def fail_always(self, status: int = 503) -> None:
        self._sticky = {"status": status, "json": _error_body(status)}

    # --- inspection ---------------------------------------------------------

    @property
    def last(self) -> RecordedCompletion:
        return self.calls[-1]

    def transcript(self) -> str:
        """Every recorded request, flattened — for credential-leak assertions."""
        return "\n".join(call.raw for call in self.calls)

    # --- request handling ---------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        content = request.content.decode("utf-8", "replace")
        try:
            body = json.loads(content) if content else None
        except json.JSONDecodeError:
            body = None

        headers = dict(request.headers)
        self.calls.append(
            RecordedCompletion(
                method=request.method,
                url=str(request.url),
                path=request.url.path,
                headers=headers,
                body=body if isinstance(body, dict) else None,
                raw="\n".join(
                    [
                        f"{request.method} {request.url}",
                        *(f"{name}: {value}" for name, value in headers.items()),
                        content,
                    ]
                ),
            )
        )

        if not request.url.path.endswith("/chat/completions"):
            return _error(404, f"unknown route {request.method} {request.url.path}")
        if request.headers.get("Authorization") != f"Bearer {self.virtual_key}":
            # Never echo the offered credential (FR-009).
            return _error(401, "Authentication Error: invalid virtual key")

        if self._script:
            queued = self._script.pop(0)
        elif self._sticky is not None:
            queued = self._sticky
        else:
            return _error(500, "no scripted reply: the test must script one")

        return httpx.Response(queued["status"], json=queued["json"])


# --- payload builders --------------------------------------------------------


def completion(content: str) -> dict[str, Any]:
    """An OpenAI-shaped chat completion carrying `content`."""
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "model": JUDGE_MODEL_ALIAS,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 180},
    }


def truncated(content: str = "", *, reasoning: str = "Let me score each ") -> dict[str, Any]:
    """A completion the backend cut off at `max_tokens` (`finish_reason` "length").

    Shaped on what a reasoning model really returns through LiteLLM: the thinking
    lands in `reasoning_content`, spends the same output budget the verdict needs,
    and `content` is whatever was left — routinely nothing at all. Observed live
    2026-08-06 on `ollama-cloud/glm-5.2`, four attempts in a row.
    """
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "model": JUDGE_MODEL_ALIAS,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": reasoning,
                },
                "finish_reason": "length",
            }
        ],
        "usage": {"prompt_tokens": 17061, "completion_tokens": 2000},
    }


def verdict_json(
    *,
    verdict: str = "pass",
    scenarios: Mapping[str, bool] | Sequence[tuple[str, bool]],
    feedback: str = "nothing to report",
) -> str:
    """The judge's response object, serialized exactly as a model would send it."""
    items = scenarios.items() if isinstance(scenarios, Mapping) else scenarios
    return json.dumps(
        {
            "verdict": verdict,
            "scenarios": [
                {
                    "scenario": scenario,
                    "pass": passed,
                    "reasoning": f"{scenario}: the diff {'does' if passed else 'does not'} satisfy every step",
                }
                for scenario, passed in items
            ],
            "feedback": feedback,
        },
        indent=2,
    )


def fence(body: str, *, language: str = "json") -> str:
    return f"```{language}\n{body}\n```"


def _error_body(status: int) -> dict[str, Any]:
    return {"error": {"message": f"injected {status}", "code": str(status)}}


def _error(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": message, "code": str(status)}})
