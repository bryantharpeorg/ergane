"""Noun registration for `ergane completion`."""

from __future__ import annotations

from factory.cli.completion import add_completion_parser
from factory.cli.nouns import Noun

NOUN = Noun(
    name="completion",
    summary="emit a shell completion script",
    order=70,
    add_parser=add_completion_parser,
)
