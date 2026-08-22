"""Noun registration for `ergane uninstall`."""

from __future__ import annotations

from factory.cli.nouns import Noun
from factory.cli.uninstall import add_uninstall_parser

NOUN = Noun(
    name="uninstall",
    summary="take Ergane off this host, in the order that is safe",
    order=7,
    add_parser=add_uninstall_parser,
)
