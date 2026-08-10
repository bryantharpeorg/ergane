"""Implementation of `ergane completion`.

Emits a small static completion script for bash or zsh. Any other shell is
rejected with exit code 2 and a message naming the two supported shells.
"""

from __future__ import annotations

import argparse

from factory.cli.errors import EXIT_USAGE, OperatorError

_BASH_SCRIPT = '''
_ergane_completion() {
    local cur prev words cword
    _init_completion || return
    local nouns="doctor findings usage repo roadmap env completion"
    if [ "$cword" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$nouns" -- "$cur") )
    fi
}
complete -F _ergane_completion ergane
'''

_ZSH_SCRIPT = '''
#compdef ergane
_ergane() {
    local -a nouns
    nouns=(doctor findings usage repo roadmap env completion)
    _describe -t nouns "ergane nouns" nouns
}
compdef _ergane ergane
'''


def add_completion_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "completion",
        help="emit a shell completion script",
        description="Print a completion script for bash or zsh.",
    )
    parser.add_argument("shell", help="target shell (bash or zsh)")
    parser.set_defaults(run=completion_command)
    return parser


def completion_command(args: argparse.Namespace) -> int:
    shell = args.shell.lower()
    if shell == "bash":
        print(_BASH_SCRIPT.strip())
        return 0
    if shell == "zsh":
        print(_ZSH_SCRIPT.strip())
        return 0
    raise OperatorError(
        f"unsupported shell {args.shell!r}; supported shells: bash, zsh",
        EXIT_USAGE,
    )
