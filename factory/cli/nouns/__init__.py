"""The registry type shared by every noun module.

A noun is one module under `factory/cli/nouns/` that declares a module-level
`NOUN`. Discovery walks the package directory; there is no list elsewhere."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Noun:
    name: str
    summary: str
    order: int
    add_parser: Callable[[Any], None]
