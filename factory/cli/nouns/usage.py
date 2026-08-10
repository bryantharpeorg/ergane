"""Noun registration for `ergane usage`."""

from __future__ import annotations

from factory.cli.nouns import Noun
from factory.cli.usage import add_usage_parser

NOUN = Noun(
    name="usage",
    summary="read-only usage rollups over the ledger",
    order=42,
    add_parser=add_usage_parser,
)
