"""Stack pack data: resolution, detection, hygiene, and rendering.

A stack pack is a YAML data file declaring the marker files that identify a
repository's stack, the toolchain name, test/lint/type commands, the tool roster
those commands are allowed to run, a dependency policy, and a human-readable
label. Packs live as package data so an installed wheel carries them, and they
are resolved `importlib.resources`-first after the pattern in `factory.config`
(057 FR-010).

Two properties of this module are load-bearing and easy to erode:

*Nothing here knows a pack's name.* Adding a pack is adding a file (FR-010), and
that stops being true the moment a selector or a renderer says
`if pack.name == ...`. Everything a pack needs said about it is said by the pack:
which markers identify it, which tools it may run, whether it is the fallback
that answers when nothing matched. `tests/test_057_us2_stack_pack.py` asserts no
shipped pack's name appears as a literal in this file or in `factory.cli.init`.

*Ambiguity is a question, not a coin flip.* Two marker files in one repository is
a fact about the repository, not a tie to break. `detect_stack_packs` reports
"several matched" as its own outcome, distinct from "none matched", because the
two demand opposite treatment: none means write the fallback, several means ask.
Collapsing them into one `None` forces every caller to guess, and a guess here
is invisible — it writes a plausible stack layer into a repository whose agents
then obey it.
"""

from __future__ import annotations

import importlib.resources
import re
import shlex
from itertools import combinations
from pathlib import Path
from typing import Any, NamedTuple

import yaml

#: Basename of the directory inside the package that holds stack packs.
PACKS_DIRNAME = "stack_packs"
#: Suffix for pack data files.
PACK_SUFFIX = ".yaml"

#: A shell word, for the purpose of asking whether a command names a given tool.
#: Deliberately coarse: it exists so `npm` does not match inside `npmx`, and so
#: `uv run npm test` yields `npm` even though `npm` is not the executable.
_WORD = re.compile(r"[A-Za-z0-9_.+@/-]+")


class StackPack(NamedTuple):
    """One resolved stack pack, with its source path for reporting."""

    name: str
    label: str
    markers: tuple[str, ...]
    toolchain: str
    commands: dict[str, str]
    dependency_policy: str
    source: str
    #: Executables this pack's commands are allowed to run. The cross-pack
    #: hygiene check is built on these rather than on the command strings,
    #: because a roster can be compared between packs and prose cannot.
    tools: tuple[str, ...] = ()
    #: True for the pack that answers when no marker matched. Declared by the
    #: data so no code has to know which pack that is (constitution IX).
    fallback: bool = False
    #: One line saying why this layer is in the document at all (FR-016).
    rationale: str = ""
    #: What the user must complete themselves. The fallback pack names commands
    #: it cannot know (FR-009); a real pack normally names nothing here.
    completion: tuple[str, ...] = ()

    def render_layer(self) -> str:
        """Return the Markdown stack layer written into a seeded constitution.

        One renderer for every pack, including the fallback. The fallback used to
        be rendered by a separate hardcoded function reached through a
        compare-the-pack-name branch in the writer, which meant the fallback was
        code while every other pack was data — so the one pack most likely to
        need editing by a user was the one pack they could not edit.
        """
        lines: list[str] = [f"## Stack: {self.label}", ""]
        if self.rationale:
            lines.extend([f"**Why this is here:** {self.rationale}", ""])
        lines.extend([f"**Toolchain:** {self.toolchain}", ""])
        if self.commands:
            lines.append("**Commands:**")
            lines.extend(f"- `{name}`: `{command}`" for name, command in self.commands.items())
            lines.append("")
        if self.completion:
            lines.append("**Complete these yourself:**")
            lines.extend(f"- {item}" for item in self.completion)
            lines.append("")
        lines.append(f"**Dependency policy:** {self.dependency_policy}")
        return "\n".join(lines) + "\n"


class StackDetection(NamedTuple):
    """What the marker files said, with "several" kept apart from "none".

    `pack` is the single match and is `None` unless exactly one pack matched, so
    a caller that only wants the easy case can read it and ignore the rest. A
    caller that must not guess reads `ambiguous` and `candidates`.
    """

    candidates: tuple[StackPack, ...]
    #: Every pack available at detection time, so a caller resolving an
    #: override or a fallback does not have to resolve them a second time.
    available: tuple[StackPack, ...]

    @property
    def pack(self) -> StackPack | None:
        """The detected pack, or `None` when there was not exactly one."""
        return self.candidates[0] if len(self.candidates) == 1 else None

    @property
    def ambiguous(self) -> bool:
        """More than one pack's markers are present: a question, not a pick."""
        return len(self.candidates) > 1

    @property
    def unmatched(self) -> bool:
        """No pack's markers are present: the fallback answers."""
        return not self.candidates

    def fallback(self) -> StackPack:
        """The pack that declared itself the fallback."""
        for pack in self.available:
            if pack.fallback:
                return pack
        raise ValueError(
            "no stack pack declares itself the fallback (`fallback: true`); a "
            "repository matching no shipped stack has nothing to be given"
        )

    def by_name(self, name: str) -> StackPack | None:
        """Look up an available pack by the name an operator typed."""
        return next((p for p in self.available if p.name == name), None)


def _pack_from_data(source: str, data: dict[str, Any]) -> StackPack:
    """Validate and construct a `StackPack` from parsed YAML data."""
    name = data.get("name")
    label = data.get("label", name)
    markers = data.get("markers") or []
    toolchain = data.get("toolchain", "")
    commands = data.get("commands") or {}
    tools = data.get("tools") or []
    completion = data.get("completion") or []
    dependency_policy = data.get("dependency_policy", "")
    if not isinstance(name, str) or not name:
        raise ValueError(f"stack pack {source!r} missing required field 'name'")
    if not isinstance(markers, list) or not all(isinstance(m, str) for m in markers):
        raise ValueError(f"stack pack {source!r} 'markers' must be a list of strings")
    if not isinstance(commands, dict) or not all(isinstance(v, str) for v in commands.values()):
        raise ValueError(f"stack pack {source!r} 'commands' must be a mapping of strings")
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        raise ValueError(f"stack pack {source!r} 'tools' must be a list of strings")
    if not isinstance(completion, list) or not all(isinstance(c, str) for c in completion):
        raise ValueError(f"stack pack {source!r} 'completion' must be a list of strings")
    return StackPack(
        name=name,
        label=str(label),
        markers=tuple(markers),
        toolchain=str(toolchain),
        commands={str(k): str(v) for k, v in commands.items()},
        dependency_policy=str(dependency_policy),
        source=source,
        tools=tuple(tools),
        fallback=bool(data.get("fallback", False)),
        rationale=str(data.get("rationale", "")),
        completion=tuple(completion),
    )


def _load_pack(path: Path) -> StackPack:
    """Load a single pack file from disk."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _pack_from_data(str(path), data)


def resolve_stack_packs(
    *,
    extra_directories: list[Path] | None = None,
) -> list[StackPack]:
    """Return all available stack packs, shipped first, then extras.

    Package data is resolved `importlib.resources`-first, which in a development
    checkout resolves to the same `factory/stack_packs/` directory the wheel
    ships — the packs live inside the package, unlike `default_floor.md`, which
    is force-included from the repo root. Extra directories let a supplied
    template (US4) and the suite add packs without editing code.
    """
    packs: list[StackPack] = []

    packaged = importlib.resources.files("factory") / PACKS_DIRNAME
    if packaged.is_dir():
        for entry in sorted(packaged.iterdir(), key=lambda e: e.name):
            if entry.name.endswith(PACK_SUFFIX):
                data = yaml.safe_load(entry.read_text(encoding="utf-8")) or {}
                packs.append(_pack_from_data(str(entry), data))

    # Extra directories override by name and extend the list by data alone.
    seen = {p.name for p in packs}
    for directory in extra_directories or []:
        for path in sorted(directory.glob(f"*{PACK_SUFFIX}")):
            pack = _load_pack(path)
            if pack.name in seen:
                packs = [p if p.name != pack.name else pack for p in packs]
            else:
                packs.append(pack)
                seen.add(pack.name)

    return packs


def detect_stack_packs(
    repo_root: Path,
    *,
    extra_directories: list[Path] | None = None,
) -> StackDetection:
    """Match a repository's files against every pack's declared markers.

    Reports what it found without deciding what to do about it: exactly one
    match, several (a question), or none (the fallback). The fallback pack
    declares no markers, so it never appears among the candidates.
    """
    packs = resolve_stack_packs(extra_directories=extra_directories)
    repo_files = {p.name for p in repo_root.iterdir() if p.is_file()}
    candidates = tuple(p for p in packs if any(m in repo_files for m in p.markers))
    return StackDetection(candidates=candidates, available=tuple(packs))


def detect_stack(
    repo_root: Path,
    *,
    extra_directories: list[Path] | None = None,
) -> StackPack | None:
    """The detected pack when exactly one matched, else `None`.

    Kept for callers that only care about the unambiguous case. A caller that
    must distinguish "none matched" from "several matched" — and anything that
    writes a stack layer must — uses `detect_stack_packs` instead.
    """
    return detect_stack_packs(repo_root, extra_directories=extra_directories).pack


def _command_words(command: str) -> set[str]:
    """Every bare word in a command, flags excluded."""
    return {word for word in _WORD.findall(command) if not word.startswith("-")}


def _leading_executable(command: str) -> str | None:
    """The executable a command runs, or `None` if it cannot be parsed."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    return parts[0] if parts else None


def check_tool_hygiene(packs: list[StackPack]) -> list[str]:
    """Return every way these packs name a tool that is not theirs (SC-003).

    A pack that names another stack's tool is worse than a missing pack, because
    it looks authoritative: a repository is handed `npm test` under a heading
    that says Python and the agent that reads it has no way to know better. The
    check is mechanical rather than a reading of the pack files (plan trap 8),
    and it is built from four rules that close each other's gaps:

    1. No two packs claim the same tool, so a pack cannot legitimise a foreign
       tool by adding it to its own roster.
    2. Every command's executable is on its own pack's roster, so the roster
       covers what actually runs.
    3. No command names another pack's tool anywhere in it, not merely as the
       executable — `uv run npm test` runs `uv` and is still wrong.
    4. Every rostered tool is run by some command, so a roster cannot be padded
       to pre-claim tools a pack has no business with.

    Returns a list of human-readable violations; empty means clean.
    """
    violations: list[str] = []
    rosters = {pack.name: set(pack.tools) for pack in packs}

    for first, second in combinations(packs, 2):
        shared = rosters[first.name] & rosters[second.name]
        if shared:
            violations.append(
                f"packs {first.name!r} and {second.name!r} both claim "
                f"{sorted(shared)}; a tool belongs to one stack"
            )

    for pack in packs:
        own = rosters[pack.name]
        foreign = {t for name, roster in rosters.items() if name != pack.name for t in roster}
        foreign -= own

        if pack.commands and not own:
            violations.append(
                f"pack {pack.name!r} names commands but declares no tools, so "
                "nothing can be checked against another stack's roster"
            )

        invoked: set[str] = set()
        for gate, command in pack.commands.items():
            if not command.strip():
                violations.append(f"pack {pack.name!r} command {gate!r} is empty")
                continue
            words = _command_words(command)
            invoked |= words
            executable = _leading_executable(command)
            if executable is None:
                violations.append(
                    f"pack {pack.name!r} command {gate!r} ({command!r}) is not a "
                    "parseable command line"
                )
            elif executable not in own:
                violations.append(
                    f"pack {pack.name!r} command {gate!r} runs {executable!r}, "
                    f"which is not on its roster {sorted(own)}"
                )
            for tool in sorted(words & foreign):
                violations.append(
                    f"pack {pack.name!r} command {gate!r} ({command!r}) names "
                    f"{tool!r}, a tool of another stack"
                )

        for tool in sorted(own - invoked):
            violations.append(
                f"pack {pack.name!r} declares tool {tool!r} that none of its "
                "commands runs"
            )

    return violations


def fallback_pack(*, extra_directories: list[Path] | None = None) -> StackPack:
    """The pack that answers for a repository matching no shipped stack."""
    packs = resolve_stack_packs(extra_directories=extra_directories)
    for pack in packs:
        if pack.fallback:
            return pack
    raise ValueError(
        "no stack pack declares itself the fallback (`fallback: true`); a "
        "repository matching no shipped stack has nothing to be given"
    )


def agnostic_layer() -> str:
    """The Markdown for the language-agnostic fallback stack layer (FR-009)."""
    return fallback_pack().render_layer()
