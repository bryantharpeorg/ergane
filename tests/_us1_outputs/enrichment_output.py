"""Generate the SC-001 enrichment output for the three source shapes.

This module is not a test.  It is a small script the committed evidence file
`enrichment_output.txt` was produced with, so a reviewer can reproduce the
pasted output.  Run it as:

    uv run python tests/_us1_outputs/enrichment_output.py

It drives the same `enrich_aliases` entry point the tests exercise, through
injected transports only — no real sockets.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from factory.discovery.llm_enrichment import enrich_aliases


class FixedLiteLLMTransport(httpx.AsyncBaseTransport):
    """Return the same responses for all three evidence scenarios."""

    def __init__(self, model_info: dict[str, Any], models: list[str]) -> None:
        self.model_info = model_info
        self.models = models

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        parsed = str(request.url).rsplit("/", 1)[1]
        if parsed == "model_info":
            return httpx.Response(200, json=self.model_info)
        if parsed == "models":
            return httpx.Response(
                200, json={"data": [{"id": a} for a in self.models]}
            )
        return httpx.Response(404, json={"error": "not found"})


class FixedOllamaTransport(httpx.AsyncBaseTransport):
    """Return /api/show responses for a fixed set of Ollama models."""

    def __init__(self, shows: dict[str, dict[str, Any]]) -> None:
        self.shows = shows

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = request.content and json.loads(request.content)
        name = body.get("name") if isinstance(body, dict) else None
        data = self.shows.get(name)
        if data is None:
            return httpx.Response(404, json={"error": "model not found"})
        return httpx.Response(200, json=data)


def main() -> None:
    out = []

    # Rich LiteLLM gateway
    rich_info = {
        "claude-sonnet-4": {
            "model_info": {
                "max_tokens": 200000,
                "input_cost_per_token": 3.0e-6,
                "output_cost_per_token": 1.5e-5,
                "supports_function_calling": True,
                "supports_response_schema": True,
                "supports_reasoning": False,
            }
        },
        "claude-opus-4": {
            "model_info": {
                "max_tokens": 200000,
                "input_cost_per_token": 1.5e-5,
                "output_cost_per_token": 7.5e-5,
                "supports_function_calling": True,
                "supports_response_schema": True,
                "supports_reasoning": True,
            }
        },
    }
    os.environ["FAKE_RICH_LITELLM_KEY"] = "sk-rich"
    rich = enrich_aliases(
        base_url="http://127.0.0.1:4000",
        aliases=("claude-sonnet-4", "claude-opus-4"),
        master_key_env="FAKE_RICH_LITELLM_KEY",
        transport=FixedLiteLLMTransport(rich_info, ["claude-sonnet-4", "claude-opus-4"]),
    )
    out.append("## Rich LiteLLM gateway")
    for r in rich:
        out.append(str(r))

    os.environ["FAKE_BARE_LITELLM_KEY"] = "sk-bare"
    # Bare gateway: /model/info 404, no /v1/models data for these aliases.
    bare = enrich_aliases(
        base_url="http://127.0.0.1:4000",
        aliases=("my-gpu-box", "my-gpu-box-large"),
        master_key_env="FAKE_BARE_LITELLM_KEY",
        transport=FixedLiteLLMTransport({}, []),
    )
    out.append("\n## Bare gateway")
    for r in bare:
        out.append(str(r))

    # Ollama endpoint
    ollama_shows = {
        "llama3.1": {
            "capabilities": {"tools": True, "structured_output": True},
            "details": {"context_length": 131072},
        },
        "qwq": {
            "capabilities": {"reasoning": True},
            "details": {"context_length": 32768},
        },
    }
    os.environ["FAKE_OLLAMA_KEY"] = "sk-ollama"
    ollama = enrich_aliases(
        base_url="http://127.0.0.1:11434",
        aliases=("llama3.1", "qwq"),
        master_key_env="FAKE_OLLAMA_KEY",
        transport=FixedOllamaTransport(ollama_shows),
    )
    out.append("\n## Ollama endpoint")
    for r in ollama:
        out.append(str(r))

    dest = Path(__file__).with_suffix(".txt")
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
