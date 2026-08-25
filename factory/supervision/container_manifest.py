"""What the engine container's project is on disk, and how it is remembered
(104-US3).

*The engine container* is the Docker container `ergane install` brings up —
never bwrap's sandbox, never "a container of specs".

Rendering and persisting are two jobs with two failure modes (R11), so this
module is the second one: it takes the tuple of `GeneratedFile`s
`container_project.py` renders and writes it under the supervision home, keeping
a digest manifest beside it. It imports `project_files` and edits that module not
at all.

One rule runs through all three entry points, and it is provenance by **digest**,
never by filename:

* `write_project` — writes what the render produced, records each file's digest,
  and refuses to overwrite a file whose digest it does not recognise. A file the
  operator has edited has become theirs, and the edit was probably a response to
  something.
* `remove_project` — removes only files whose recorded digest still matches, from
  the manifest alone. Bring-down may not require what bring-up requires (trap
  13): nothing here re-renders, so teardown works on a host whose config, registry
  or Docker daemon has since gone away.
* `installed_project` — the query R1 makes the installation's record. This
  directory and its manifest *are* the fact that the host runs the container
  tier; US5, US6 and US7 ask here, never `config.toml`.

A filename allow-list would be a strictly weaker version of the same code: it
cannot tell the file it wrote from the file an operator replaced, so it either
clobbers hand edits on write or deletes them at teardown. That is the whole
reason the manifest exists.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path

from factory.supervision.container_project import (
    COMPOSE_NAME,
    ContainerProject,
    project_dir,
    project_files,
)
from factory.supervision.units import (
    MANIFEST_NAME,
    GeneratedFile,
    InstallLayout,
    _digest,
    _is_someone_elses,
)

#: `MANIFEST_NAME`, `_digest` and `_is_someone_elses` are imported rather than
#: copied. Provenance by digest is one rule, and two implementations of it are
#: two implementations that can drift apart — the same argument `units.py` makes
#: for keeping capability probes in one place. Neither helper knows anything
#: about systemd or an `InstallLayout`; they are private by convention only.
__all__ = [
    "KEPT_CHANGED",
    "KEPT_UNCLAIMED",
    "MANIFEST_NAME",
    "InstalledProject",
    "KeptFile",
    "RemovalReport",
    "WriteReport",
    "installed_project",
    "remove_project",
    "write_project",
]

#: The manifest's one key. `units.py` calls its map `units` because they are
#: units; these are files, and the noun is the only difference.
_MANIFEST_KEY = "files"

#: Why a file was left alone, in the operator's words rather than a status code.
KEPT_CHANGED = "changed since ergane wrote it"
KEPT_UNCLAIMED = "not written by ergane"


@dataclasses.dataclass(frozen=True)
class KeptFile:
    """One file that was left exactly as it was, and why.

    The reason is carried rather than derived at print time because write and
    removal keep files for the same two reasons and an operator acts on the
    reason: a changed file is theirs to reconcile, an unclaimed one is theirs to
    remove.
    """

    name: str
    reason: str


@dataclasses.dataclass(frozen=True)
class InstalledProject:
    """The record that this host runs the engine container (R1).

    Carries what the manifest recorded, not what the renderer would produce now:
    a later story asking "is there a project here" must be answerable on a host
    whose config has moved on, and comparing the two is a different question.
    """

    directory: Path
    digests: Mapping[str, str]

    @property
    def files(self) -> tuple[str, ...]:
        """Every file name the manifest claims, sorted — the order a report reads
        in and the order two runs agree on."""
        return tuple(sorted(self.digests))

    @property
    def compose_path(self) -> Path:
        """What `docker compose -f` is handed. Named here so no caller spells the
        join itself and gets it right in five places and wrong in the sixth."""
        return self.directory / COMPOSE_NAME

    def claims(self, name: str) -> bool:
        """Whether this engine wrote the file called `name`."""
        return name in self.digests


@dataclasses.dataclass(frozen=True)
class WriteReport:
    """What the writer wrote, left alone, and no longer generates."""

    directory: Path
    written: tuple[str, ...]
    unchanged: tuple[str, ...]
    kept: tuple[KeptFile, ...]
    #: Files an earlier project wrote that this render no longer produces, still
    #: on disk and still ours.
    retired: tuple[str, ...] = ()

    def render(self) -> str:
        # Three headlines rather than two: a run that wrote nothing *because it
        # refused something* is not a converged install, and one line saying
        # "already current" above a refusal is how an operator reads past it.
        if self.written:
            headline = f"wrote {len(self.written)} file(s) to {self.directory}"
        elif self.kept:
            headline = (
                f"engine container project at {self.directory}: wrote nothing, "
                f"{len(self.kept)} file(s) left as the operator left them"
            )
        else:
            headline = (
                f"engine container project at {self.directory} is already current"
            )
        lines = [headline]
        lines += [f"  wrote: {name}" for name in self.written]
        lines += [f"  unchanged: {name}" for name in self.unchanged]
        # Named by path, not by count: the operator has to open this file.
        lines += [
            f"  refused to overwrite ({kept.reason}): {self.directory / kept.name}"
            for kept in self.kept
        ]
        if self.kept:
            lines.append(
                "  the engine will run what is on disk; move the file aside to have "
                "`ergane install` generate it again"
            )
        lines += [
            f"  no longer generated, still installed: {self.directory / name}"
            for name in self.retired
        ]
        return "\n".join(lines)


@dataclasses.dataclass(frozen=True)
class RemovalReport:
    """What teardown removed, what it kept and why, and what was already gone."""

    directory: Path
    removed: tuple[str, ...]
    kept: tuple[KeptFile, ...]
    #: Recorded, but not on disk when removal ran — a half-removed project is a
    #: state teardown meets, not one it refuses.
    missing: tuple[str, ...] = ()
    directory_removed: bool = False

    def render(self) -> str:
        if not self.removed and not self.kept and not self.missing:
            return f"no engine container project at {self.directory}"
        lines = [f"engine container project at {self.directory}:"]
        lines += [f"  removed: {name}" for name in self.removed]
        lines += [f"  already gone: {name}" for name in self.missing]
        lines += [
            f"  kept ({kept.reason}): {self.directory / kept.name}"
            for kept in self.kept
        ]
        lines.append(
            "  removed the project directory"
            if self.directory_removed
            else "  left the project directory: it still holds files ergane "
            "did not write"
        )
        return "\n".join(lines)


def write_project(project: ContainerProject) -> WriteReport:
    """Write the rendered project under the supervision home, remembering it.

    Idempotent by construction: the text is a function of the project data, so a
    second run finds every digest matching and writes nothing. A file whose digest
    is not the one recorded is never touched — that is the half of a collision
    that cannot be undone.
    """
    directory = project.directory
    directory.mkdir(parents=True, exist_ok=True)

    recorded = _read_manifest(directory)
    rendered = project_files(project)
    written: list[str] = []
    unchanged: list[str] = []
    kept: list[KeptFile] = []
    fresh: dict[str, str] = {}
    for generated in rendered:
        if _not_provably_ours(generated, recorded):
            # It exists and it is not what we recorded, so it is either an
            # operator's edit or a file that was here before this engine was.
            kept.append(
                KeptFile(
                    generated.name,
                    KEPT_CHANGED if generated.name in recorded else KEPT_UNCLAIMED,
                )
            )
            continue
        fresh[generated.name] = _digest(generated.text)
        if _matches(generated, fresh[generated.name]):
            # Byte-identical already. Skipping the write is what makes a re-run a
            # no-op on the *bytes* — an operator watching mtimes should see a
            # converged install stop touching the directory.
            unchanged.append(generated.name)
            continue
        generated.path.write_text(generated.text, encoding="utf-8")
        generated.path.chmod(generated.mode)
        written.append(generated.name)

    carried = _carried_provenance(directory, recorded, rendered)
    _write_manifest(directory, {**carried, **fresh})

    return WriteReport(
        directory=directory,
        written=tuple(written),
        unchanged=tuple(unchanged),
        kept=tuple(kept),
        retired=tuple(sorted(carried)),
    )


def _not_provably_ours(generated: GeneratedFile, recorded: Mapping[str, str]) -> bool:
    """`_is_someone_elses`, plus the file that cannot be read at all.

    That rule reads the file to digest it, so an unreadable one raises out of the
    middle of an install or a teardown — and the two ways a file in this
    directory becomes unreadable are both real: a previous `sudo ergane install`
    leaving a root-owned file behind, and bytes that are not UTF-8. Unreadable is
    *unproven*, and the safe reading of unproven is the same one the digest rule
    already makes: leave it alone and name it.
    """
    try:
        return _is_someone_elses(generated, recorded)
    except (OSError, ValueError):
        return True


def _matches(generated: GeneratedFile, digest: str) -> bool:
    """Whether the file on disk is already exactly this text."""
    try:
        return _digest(generated.path.read_text(encoding="utf-8")) == digest
    except (OSError, ValueError):
        return False


def _carried_provenance(
    directory: Path,
    recorded: Mapping[str, str],
    rendered: tuple[GeneratedFile, ...],
) -> dict[str, str]:
    """The provenance of what this engine wrote once and writes no longer.

    082-US4's trap, in this directory: the manifest is rebuilt from what was just
    written, so a name that falls out of the render falls out of the record too —
    and the file is left on the host with nothing to prove it is the engine's,
    which teardown must then keep forever. Carried, and named in the report,
    rather than deleted: removing a file the operator did not ask about is a
    surprise, and `ergane uninstall` is the verb that removes things.
    """
    still_rendered = {generated.name for generated in rendered}
    return {
        name: digest
        for name, digest in recorded.items()
        if name not in still_rendered
        and _matches(GeneratedFile(name, "", directory), digest)
    }


def installed_project(layout: InstallLayout | None = None) -> InstalledProject | None:
    """The engine container project this host has, or `None` if it has none.

    The record R1 puts on disk instead of in `config.toml`: a host that generated
    a project runs the container tier, and one that did not, does not. Answers
    `None` rather than raising for an unreadable manifest — every caller is a
    branch in an install, an init or a teardown, and a traceback out of the
    question "is there a project here" helps none of them.
    """
    directory = project_dir(layout)
    recorded = _read_manifest(directory)
    if not recorded:
        return None
    return InstalledProject(directory=directory, digests=dict(recorded))


def remove_project(layout: InstallLayout | None = None) -> RemovalReport:
    """Remove exactly the files the writer wrote, and report the rest.

    Reads the manifest and nothing else: no render, no config, no daemon (trap
    13). A file whose recorded digest no longer matches was changed after this
    engine wrote it, and a file the manifest never claimed was never ours —
    both stay, both are named with the reason.
    """
    directory = project_dir(layout)
    recorded = _read_manifest(directory)
    if not recorded:
        return RemovalReport(directory=directory, removed=(), kept=())

    removed: list[str] = []
    missing: list[str] = []
    kept: list[KeptFile] = []
    for name in sorted(recorded):
        generated = GeneratedFile(name, "", directory)
        if not generated.path.exists():
            missing.append(name)
            continue
        if _not_provably_ours(generated, recorded):
            kept.append(KeptFile(name, KEPT_CHANGED))
            continue
        generated.path.unlink()
        removed.append(name)

    (directory / MANIFEST_NAME).unlink(missing_ok=True)
    kept += [
        KeptFile(path.name, KEPT_UNCLAIMED)
        for path in sorted(directory.iterdir())
        if path.name not in recorded
    ]

    directory_removed = False
    if not any(directory.iterdir()):
        # Nothing of anyone else's is left, so the empty shell of a tier this
        # host no longer runs goes too.
        directory.rmdir()
        directory_removed = True

    return RemovalReport(
        directory=directory,
        removed=tuple(removed),
        kept=tuple(kept),
        missing=tuple(missing),
        directory_removed=directory_removed,
    )


def _read_manifest(directory: Path) -> dict[str, str]:
    """What the manifest in `directory` records, or nothing it can be sure of.

    The same tolerance `units.py:980` has, for the same reason: a truncated or
    hand-mangled manifest means no file in the directory can be proven ours, and
    the safe reading of "unproven" is to touch nothing.
    """
    try:
        document = json.loads(
            (directory / MANIFEST_NAME).read_text(encoding="utf-8")
        )
        return {str(k): str(v) for k, v in document[_MANIFEST_KEY].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def _write_manifest(directory: Path, files: Mapping[str, str]) -> None:
    """Sorted and indented, so two runs of the same project write the same bytes
    — US3-S1's byte-identical re-run is decided here as much as in the renderer."""
    manifest = directory / MANIFEST_NAME
    manifest.write_text(
        json.dumps({_MANIFEST_KEY: dict(files)}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    # Explicit rather than left to the process umask, like every other file
    # here: the generated project should not read differently on two hosts.
    # (Compressing that phrase into one hyphenated word trips
    # `test_final_sweep.py`'s credential sweep, which reads its tail as a key.)
    manifest.chmod(0o644)
