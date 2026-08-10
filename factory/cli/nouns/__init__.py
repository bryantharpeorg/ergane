"""The registry type shared by every noun module.

A noun is one module under `factory/cli/nouns/` that declares a module-level
`NOUN`. Discovery walks the package directory; there is no list elsewhere.

Shared seams that tests can patch without reloading individual noun modules
also live here, because this package `__init__.py` is not exec'd by discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from factory.usage.litellm_client import LiteLLMClient


@dataclass(frozen=True)
class Noun:
    name: str
    summary: str
    order: int
    add_parser: Callable[[Any], None]


def _open_preflight_client() -> LiteLLMClient:
    """Default preflight client factory; tests patch this seam."""
    return LiteLLMClient.from_env()
