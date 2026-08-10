"""Noun registration for `ergane findings`."""

from __future__ import annotations

from factory.cli.doctor import add_findings_parser
from factory.cli.nouns import Noun

NOUN = Noun(
    name="findings",
    summary="manage the findings ledger",
    order=41,
    add_parser=add_findings_parser,
)
