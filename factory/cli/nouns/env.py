"""Noun registration for `ergane env`."""

from __future__ import annotations

from factory.cli.env import add_env_parser
from factory.cli.nouns import Noun

NOUN = Noun(
    name="env",
    summary="show environment variables the CLI reads",
    order=60,
    add_parser=add_env_parser,
)
