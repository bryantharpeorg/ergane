"""Stack pack data: resolution, detection, and rendering.

A stack pack is a YAML data file declaring the marker files that identify a
repository's stack, the toolchain name, test/lint/type commands, dependency
policy, and a human-readable label. Packs live as package data so an installed
wheel carries them, and they are resolved `importlib.resources`-first after the
pattern in `factory.config` (057 FR-010).
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any, NamedTuple

import yaml

#: Basename of the directory inside the package that holds stack packs.
PACKS_DIRNAME = "stack_packs"
#: Suffix for pack data files.
PACK_SUFFIX = ".yaml"


class StackPack(NamedTuple):
    """One resolved stack pack, with its source path for reporting."""

    name: str
    label: str
    markers: tuple[str, ...]
    toolchain: str
    commands: dict[str, str]
    dependency_policy: str
    source: str

    def render_layer(self) -> str:
        """Return the Markdown stack layer written into a seeded constitution."""
        lines: list[str] = [
            f"## Stack: {self.label}",
            "",
            f"**Toolchain:** {self.toolchain}",
            "",
            "**Commands:**",
        ]
        for name, command in self.commands.items():
            lines.append(f"- `{name}`: `{command}`")
        lines.extend(["", f"**Dependency policy:** {self.dependency_policy}"])
        return "\n".join(lines) + "\n"


def _pack_from_data(source: str, data: dict[str, Any]) -> StackPack:
    """Validate and construct a `StackPack` from parsed YAML data."""
    name = data.get("name")
    label = data.get("label", name)
    markers = data.get("markers", [])
    toolchain = data.get("toolchain", "")
    commands = data.get("commands", {})
    dependency_policy = data.get("dependency_policy", "")
    if not isinstance(name, str) or not name:
        raise ValueError(f"stack pack {source!r} missing required field 'name'")
    if not isinstance(markers, list) or not all(isinstance(m, str) for m in markers):
        raise ValueError(f"stack pack {source!r} 'markers' must be a list of strings")
    if not isinstance(commands, dict) or not all(isinstance(v, str) for v in commands.values()):
        raise ValueError(f"stack pack {source!r} 'commands' must be a mapping of strings")
    return StackPack(
        name=name,
        label=str(label),
        markers=tuple(markers),
        toolchain=str(toolchain),
        commands={str(k): str(v) for k, v in commands.items()},
        dependency_policy=str(dependency_policy),
        source=source,
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

    Package data is resolved `importlib.resources`-first. In a development
    checkout the source directory lives beside the module at the repo root.
    Extra directories allow tests to inject synthetic packs without editing code.
    """
    packs: list[StackPack] = []

    # Shipped packs from package data / checkout.
    packaged = importlib.resources.files("factory") / PACKS_DIRNAME
    if packaged.is_dir():
        for entry in sorted(packaged.iterdir()):
            if entry.name.endswith(PACK_SUFFIX):
                text = entry.read_text(encoding="utf-8")
                data = yaml.safe_load(text) or {}
                packs.append(_pack_from_data(str(entry), data))
    else:
        # Development checkout fallback: source tree at repo root.
        checkout_dir = Path(__file__).resolve().parents[1] / PACKS_DIRNAME
        if checkout_dir.is_dir():
            for path in sorted(checkout_dir.glob(f"*{PACK_SUFFIX}")):
                packs.append(_load_pack(path))

    # Extra directories override by name and extend the list by data alone.
    seen = {p.name for p in packs}
    for directory in (extra_directories or []):
        for path in sorted(directory.glob(f"*{PACK_SUFFIX}")):
            pack = _load_pack(path)
            if pack.name in seen:
                # Replace the shipped pack of the same name; this is the data path.
                packs = [p if p.name != pack.name else pack for p in packs]
            else:
                packs.append(pack)
                seen.add(pack.name)

    return packs


def detect_stack(
    repo_root: Path,
    *,
    extra_directories: list[Path] | None = None,
) -> StackPack | None:
    """Detect the stack for a repository from its marker files.

    Returns the matching pack when exactly one matches, or `None` when no pack
    matches (the caller falls back to the language-agnostic layer) or when more
    than one pack matches (ambiguous markers produce a question, not a coin flip).
    """
    repo_files = {p.name for p in repo_root.iterdir() if p.is_file()}
    matching: list[StackPack] = []
    for pack in resolve_stack_packs(extra_directories=extra_directories):
        if any(marker in repo_files for marker in pack.markers):
            matching.append(pack)
    if len(matching) == 1:
        return matching[0]
    if len(matching) > 1:
        return None
    return None


def detect_stack_or_ask(
    repo_root: Path,
    prompter: Any,
    *,
    extra_directories: list[Path] | None = None,
) -> StackPack:
    """Detect a stack, state it, and let the operator override.

    If detection is unambiguous, the detected stack is stated and the operator
    may confirm or override. If no pack matches, the language-agnostic fallback
    is offered. If multiple packs match, the operator is asked to choose among
    them. Returns the selected pack.
    """
    packs = resolve_stack_packs(extra_directories=extra_directories)
    repo_files = {p.name for p in repo_root.iterdir() if p.is_file()}
    matching = [p for p in packs if any(m in repo_files for m in p.markers)]

    if len(matching) == 1:
        detected = matching[0]
        print(f"detected stack: {detected.label} ({detected.name})")
        answer = prompter.ask(
            "detected stack",
            default=f"{detected.name}",
        )
        if answer.strip() and answer.strip() != detected.name:
            chosen = next((p for p in packs if p.name == answer.strip()), None)
            if chosen is None:
                raise ValueError(f"unknown stack: {answer.strip()}")
            print(f"using operator-chosen stack: {chosen.label} ({chosen.name})")
            return chosen
        return detected

    if len(matching) > 1:
        names = ", ".join(p.name for p in matching)
        print(f"ambiguous markers; detected stacks: {names}")
        answer = prompter.ask(
            "choose stack",
            default="",
        )
        if not answer.strip():
            raise ValueError("ambiguous markers require a stack choice")
        chosen = next((p for p in packs if p.name == answer.strip()), None)
        if chosen is None:
            raise ValueError(f"unknown stack: {answer.strip()}")
        print(f"using operator-chosen stack: {chosen.label} ({chosen.name})")
        return chosen

    # No match: return the language-agnostic fallback pack.
    fallback = next((p for p in packs if p.name == "agnostic"), None)
    if fallback is None:
        raise ValueError("no language-agnostic fallback pack shipped")
    print("detected no shipped stack; using language-agnostic fallback")
    return fallback


def agnostic_layer() -> str:
    """Return the Markdown for the language-agnostic fallback stack layer."""
    return """\
## Stack layer

**Why this is here:** every repository needs a concrete command an agent can run.
When no shipped stack matched the marker files, this layer names what the user
must complete so the document is useful rather than empty.

**Toolchain:** language-agnostic

No shipped stack matched this repository's marker files. Complete the sections
below with the commands an agent can run in this repository:

- `test`: the command that runs the test suite
- `lint`: the command that checks style
- `type`: the command that performs type checking
- `build`: the command that produces a release artifact

**Dependency policy:** state the rule for adding dependencies and the approval
this repository requires before a new dependency is introduced.
"""
