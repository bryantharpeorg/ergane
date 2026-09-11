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

import contextlib
import dataclasses
import json
import stat
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from factory.cli.errors import OperatorError
from factory.supervision.container_project import (
    APPARMOR_ARTIFACT,
    COMPOSE_NAME,
    ContainerProject,
    ENV_NAME,
    project_dir,
    project_files,
    SERVICE_NAME,
    SECCOMP_ARTIFACT,
    _scalar,
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
    "RetargetReport",
    "InstalledProject",
    "KeptFile",
    "RemovalReport",
    "WriteReport",
    "installed_project",
    "installed_project_at",
    "retarget_project",
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


def installed_project_at(directory: Path) -> InstalledProject | None:
    """The same ownership query as `installed_project`, pinned to an
    explicit directory.

    The upgrade honours `ERGANE_COMPOSE_PROJECT`, which can move the project
    off the layout default; ownership must follow the project the command is
    actually driving, never the directory the layout happens to derive.
    """
    recorded = _read_manifest(directory)
    if not recorded:
        return None
    return InstalledProject(directory=directory, digests=dict(recorded))


@dataclasses.dataclass(frozen=True)
class RetargetReport:
    """What a retarget rewrote, and what already sat at the target."""

    directory: Path
    retargeted: tuple[str, ...]
    unchanged: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class _StagedFile:
    """One retargeted file waiting in its temporary sibling, carrying the
    previous bytes so a mid-sequence failure can put them back."""

    path: Path
    temp: Path
    previous: bytes


#: The files a retarget requires the manifest to claim — every file
#: `project_files` renders.  A project missing one is not one this engine
#: owns, and no `--force` reaches here (spec 174 FR-007).
_REQUIRED_ARTIFACTS = (COMPOSE_NAME, ENV_NAME, SECCOMP_ARTIFACT, APPARMOR_ARTIFACT)


def retarget_project(
    directory: Path,
    *,
    image: str,
    version: str,
) -> RetargetReport:
    """Retarget the owned image and version declarations of the generated
    project at `directory`, leaving every other byte exactly as it is.

    Every refusal happens before stop or write and names the affected path:
    an unreadable manifest, an artifact that is unclaimed, missing,
    unreadable or changed, and a shape with no owned declaration to retarget.
    There is no force parameter on purpose — `--force` reaches the
    in-flight-work refusal only, never ownership (spec 174 FR-007).

    Persistence is one transaction: the updated files and the manifest are
    staged as temporary siblings, the files are renamed in order, and the
    manifest is renamed last as the commit point.  A rename that fails
    mid-sequence is rolled back to the previous bytes, so the prior project
    stays usable and a later invocation never proceeds on a half-retargeted
    one (spec 174 FR-008).
    """
    manifest_path = directory / MANIFEST_NAME
    recorded = _read_manifest(directory)
    if not recorded:
        raise OperatorError(
            f"refusing to retarget the engine container project at {directory}: "
            f"{manifest_path} is not a readable ownership manifest, so no file "
            "in it is provably ergane's; reconcile it or remove the project by "
            "hand, or re-run `ergane install` to regenerate it"
        )
    for name in _REQUIRED_ARTIFACTS:
        path = directory / name
        if name not in recorded:
            raise OperatorError(
                f"refusing to retarget the engine container project: {path} "
                "was not written by ergane, so the upgrade will not retarget "
                "it; move it aside and re-run `ergane install` to regenerate it"
            )
        if not path.is_file():
            raise OperatorError(
                f"refusing to retarget the engine container project: {path} "
                "is recorded as generated but is missing; run `ergane install` "
                "to regenerate it, or `ergane uninstall` to retire the project"
            )
        try:
            current = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as failure:
            raise OperatorError(
                f"refusing to retarget the engine container project: {path} "
                f"cannot be read as text ({failure}), so its ownership cannot "
                "be proven; fix its permissions or encoding, or move it aside "
                "and re-run `ergane install`"
            ) from failure
        if recorded[name] != _digest(current):
            raise OperatorError(
                f"refusing to retarget the engine container project: {path} "
                "changed since ergane wrote it, so the upgrade will not "
                "retarget it; reconcile the change or move the file aside, "
                "then re-run — `--force` does not adopt operator edits"
            )

    compose_text = (directory / COMPOSE_NAME).read_text(encoding="utf-8")
    env_text = (directory / ENV_NAME).read_text(encoding="utf-8")
    new_compose = _retargeted_compose(
        compose_text, image=image, path=directory / COMPOSE_NAME
    )
    new_env = _retargeted_env(env_text, version=version, path=directory / ENV_NAME)

    updates: dict[str, str] = {}
    if new_compose != compose_text:
        updates[COMPOSE_NAME] = new_compose
    if new_env != env_text:
        updates[ENV_NAME] = new_env
    unchanged = tuple(sorted(name for name in _REQUIRED_ARTIFACTS if name not in updates))
    if not updates:
        return RetargetReport(directory=directory, retargeted=(), unchanged=unchanged)

    recorded = {
        **recorded,
        **{name: _digest(text) for name, text in updates.items()},
    }
    updates[MANIFEST_NAME] = json.dumps(
        {_MANIFEST_KEY: dict(recorded)}, indent=2, sort_keys=True
    )

    staged: list[_StagedFile] = []
    try:
        for name, text in updates.items():
            path = directory / name
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=f".{name}.",
                suffix=".retarget",
                delete=False,
            ) as temp:
                temp.write(text)
                temp_path = Path(temp.name)
            temp_path.chmod(stat.S_IMODE(path.stat().st_mode))
            staged.append(
                _StagedFile(path=path, temp=temp_path, previous=path.read_bytes())
            )
    except OSError as failure:
        for item in staged:
            with contextlib.suppress(OSError):
                item.temp.unlink(missing_ok=True)
        raise OperatorError(
            f"could not stage the retargeted engine container project at "
            f"{directory}: {failure}"
        ) from failure

    _commit_staged(staged)
    return RetargetReport(
        directory=directory,
        retargeted=tuple(sorted(name for name in updates if name != MANIFEST_NAME)),
        unchanged=unchanged,
    )


def _commit_staged(staged: Sequence[_StagedFile]) -> None:
    """Rename every staged retarget into place, manifest last.

    The manifest is the commit point: it is renamed after the files, so a
    crash can only leave a project the manifest still fully owns.  A rename
    that fails mid-sequence is rolled back to the previous bytes rather than
    left half-applied (spec 174 FR-008).
    """
    renamed: list[tuple[Path, bytes]] = []
    try:
        for item in staged:
            item.temp.replace(item.path)
            renamed.append((item.path, item.previous))
    except OSError as failure:
        failed = item.path
        for path, previous in renamed:
            with contextlib.suppress(OSError):
                path.write_bytes(previous)
        for item in staged:
            with contextlib.suppress(OSError):
                item.temp.unlink(missing_ok=True)
        raise OperatorError(
            f"could not commit the retargeted engine container project: "
            f"{failed} could not be replaced ({failure}); the previous "
            "project bytes were restored"
        ) from failure


def _retargeted_compose(text: str, *, image: str, path: Path) -> str:
    """`text` with the ergane service's owned image line swapped for `image`.

    The digest check has just proven the bytes are the generator's render, so
    the declaration is the first `image:` line inside the service block, and
    every other byte is carried through untouched.
    """
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.rstrip("\n") != f"  {SERVICE_NAME}:":
            continue
        for offset in range(index + 1, len(lines)):
            following = lines[offset]
            if not following.startswith("    "):
                break
            if following.startswith("    image:"):
                lines[offset] = f"    image: {_scalar(image)}\n"
                return "".join(lines)
        break
    raise OperatorError(
        f"refusing to retarget the engine container project: {path} has no "
        f"image declaration under the {SERVICE_NAME} service, so this "
        "project's shape is unsupported for retargeting; regenerate it with "
        "`ergane install`"
    )


def _retargeted_env(text: str, *, version: str, path: Path) -> str:
    """`text` with the owned ERGANE_VERSION assignment swapped for `version`."""
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("ERGANE_VERSION="):
            lines[index] = f"ERGANE_VERSION={version}\n"
            return "".join(lines)
    raise OperatorError(
        f"refusing to retarget the engine container project: {path} declares "
        "no ERGANE_VERSION, so this project's shape is unsupported for "
        "retargeting; regenerate it with `ergane install`"
    )


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
