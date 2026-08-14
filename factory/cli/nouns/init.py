"""Noun registration for `ergane init`."""

from __future__ import annotations

from factory.cli.init import add_init_parser
from factory.cli.nouns import Noun

NOUN = Noun(
    name="init",
    summary="join a git repository to Ergane",
    order=10,
    add_parser=add_init_parser,
)
