"""The `skills` noun: the explicit operator install and observation front door."""

from __future__ import annotations

import argparse
from typing import Any

from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.cli.nouns import Noun
from factory.cli.skills import install, render_install, render_status, skills_status


def _install(_args: Any) -> int:
    result = install()
    print(render_install(result))
    return EXIT_USER if result.collisions else EXIT_OK


def _status(_args: Any) -> int:
    status = skills_status()
    print(render_status(status))
    return EXIT_OK


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "skills",
        help="install canonical operator skills and safe client entry points",
    description=(
        "Install the packaged canonical skill tree into the declared operator "
            "home and create compatibility aliases. Existing paths are preserved "
            "and reported; the explicit verb is the only mutation."
        ),
    )
    verbs = parser.add_subparsers(dest="verb", required=True)
    installer = verbs.add_parser(
        "install",
        help="plan, classify and safely install skills and compatibility aliases",
    )
    installer.set_defaults(run=_install)
    observer = verbs.add_parser(
        "status",
        help="report skill filesystem state without changing anything",
    )
    observer.set_defaults(run=_status)


NOUN = Noun(
    name="skills",
    summary="install collision-safe operator skills for supported clients",
    order=5,
    add_parser=add_parser,
)
