"""Noun registration for `ergane doctor`."""

from __future__ import annotations

from factory.cli.doctor import add_doctor_parser
from factory.cli.nouns import Noun

NOUN = Noun(
    name="doctor",
    summary="run all registered probes",
    order=40,
    add_parser=add_doctor_parser,
)
