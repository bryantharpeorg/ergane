"""Noun registration for `ergane repo`."""

from __future__ import annotations

from factory.cli.nouns import Noun
from factory.cli.repo import add_repo_parser

NOUN = Noun(
    name="repo",
    summary="manage target repositories",
    order=43,
    add_parser=add_repo_parser,
)
