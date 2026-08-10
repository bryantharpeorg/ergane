"""Implementation of `ergane completion`.

Emits a small static completion script for bash or zsh. The script is built
from the live parser tree, so it completes both top-level nouns and each
noun's verbs. Any other shell is rejected with exit code 2 and a message naming
the two supported shells.
"""

from __future__ import annotations

import argparse
import shlex

from factory.cli.errors import EXIT_USAGE, OperatorError


def add_completion_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "completion",
        help="emit a shell completion script",
        description="Print a completion script for bash or zsh.",
    )
    parser.add_argument(
        "shell",
        choices=["bash", "zsh"],
        help="target shell (bash or zsh)",
    )
    parser.set_defaults(run=completion_command)
    return parser


def _noun_and_verb_map() -> tuple[list[str], dict[str, list[str]]]:
    """Return (all noun names, noun -> sorted verb names) from the parser tree.

    Verbs come from a noun's own subparsers, or from positional arguments (not
    options) that declare a fixed set of choices. Nouns with neither still appear
    in the noun list, but produce no second-level completions.
    """
    from factory.cli import main as main_module

    root = main_module._build_parser()
    nouns: list[str] = []
    mapping: dict[str, list[str]] = {}
    for action in root._subparsers._group_actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for noun, noun_parser in action._name_parser_map.items():
            nouns.append(noun)
            verbs: set[str] = set()
            if noun_parser._subparsers is not None:
                for sub_action in noun_parser._subparsers._group_actions:
                    if isinstance(sub_action, argparse._SubParsersAction):
                        verbs.update(sub_action._name_parser_map.keys())
            for sub_action in noun_parser._actions:
                if (
                    isinstance(sub_action, argparse._StoreAction)
                    and not sub_action.option_strings
                    and sub_action.choices is not None
                ):
                    verbs.update(sub_action.choices)
            if verbs:
                mapping[noun] = sorted(verbs)
    nouns.sort()
    return nouns, mapping


def _bash_script(nouns: list[str], verbs: dict[str, list[str]]) -> str:
    noun_list = " ".join(shlex.quote(n) for n in nouns)
    case_branches = []
    for noun in nouns:
        noun_verbs = verbs.get(noun, [])
        case_branches.append(
            f"        {shlex.quote(noun)}) local verbs={shlex.quote(' '.join(noun_verbs))} ;;"
        )
    case_block = "\n".join(case_branches)
    return f"""_ergane_completion() {{
    local cur prev words cword
    _init_completion || return
    local nouns={noun_list}
    local noun="${{words[1]}}"
    local verbs=""
    case "$noun" in
{case_block}
    esac
    if [ "$cword" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$nouns" -- "$cur") )
    elif [ "$cword" -eq 2 ] && [ -n "$verbs" ]; then
        COMPREPLY=( $(compgen -W "$verbs" -- "$cur") )
    fi
}}
complete -F _ergane_completion ergane"""


def _zsh_script(nouns: list[str], verbs: dict[str, list[str]]) -> str:
    noun_array = " ".join(shlex.quote(n) for n in nouns)
    case_branches = []
    for noun in nouns:
        noun_verbs = verbs.get(noun, [])
        if noun_verbs:
            verb_array = " ".join(shlex.quote(v) for v in noun_verbs)
            case_branches.append(
                f"                {shlex.quote(noun)}) verbs=({verb_array}) ;;"
            )
        else:
            case_branches.append(
                f"                {shlex.quote(noun)}) verbs=() ;;"
            )
    case_block = "\n".join(case_branches)
    return f"""#compdef ergane
_ergane() {{
    local curcontext="$curcontext" state line
    typeset -A opt_args
    _arguments -C \\
        '1: :->noun' \\
        '2: :->verb' \\
        '*: :->args'
    case "$state" in
        noun)
            local -a nouns
            nouns=({noun_array})
            _describe -t nouns "ergane nouns" nouns
            ;;
        verb)
            local noun="$line[1]"
            local -a verbs
            case "$noun" in
{case_block}
            esac
            if [[ ${{#verbs}} -gt 0 ]]; then
                _describe -t verbs "ergane $noun verbs" verbs
            fi
            ;;
    esac
}}
compdef _ergane ergane"""


def completion_command(args: argparse.Namespace) -> int:
    shell = args.shell.lower()
    nouns, verbs = _noun_and_verb_map()
    if shell == "bash":
        print(_bash_script(nouns, verbs))
        return 0
    if shell == "zsh":
        print(_zsh_script(nouns, verbs))
        return 0
    raise OperatorError(
        f"unsupported shell {args.shell!r}; supported shells: bash, zsh",
        EXIT_USAGE,
    )
