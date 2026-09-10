"""Pure inventory and release validation helpers for canonical operator skills."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence


CANONICAL_SKILLS_ROOT = Path(".agents") / "skills"
COMPATIBILITY_SKILLS_ROOT = Path(".claude") / "skills"
PACKAGE_SKILLS_PREFIX = "factory/skills/"

DECLARED_SKILLS: tuple[str, ...] = (
    "floor-status",
    "escalation-triage",
    "findings-ingest",
    "away-mode",
    "build-metrics",
    "spec-html",
)


class SkillPackagingError(Exception):
    """One or more named refusals from packaging validation."""


@dataclass(frozen=True)
class ResourceRecord:
    path: str
    kind: str
    digest: str
    symlink_target: str | None = None


_CREDENTIAL_NAME_PATTERNS = (
    re.compile(r"(?:^|/)\.env(?:\..+)?$", re.IGNORECASE),
    re.compile(r"(?:^|/)id_(?:rsa|ed25519|ecdsa)(?:\..*)?$", re.IGNORECASE),
    re.compile(r"\.(?:pem|key|p12|pfx)$", re.IGNORECASE),
)
_CREDENTIAL_CONTENT_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        rb"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*[^\s]{8,}",
    ),
)


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _refuse(failures: Sequence[str]) -> None:
    if failures:
        raise SkillPackagingError("\n".join(failures))


def _validate_safe_file_symlink(path: Path, canonical_root: Path) -> Path:
    raw_target = os.readlink(path)
    if os.path.isabs(raw_target):
        raise SkillPackagingError(f"SYMLINK-ABSOLUTE: {path.relative_to(canonical_root)}")
    lexical_target = Path(os.path.normpath(os.path.join(path.parent, raw_target)))
    if not lexical_target.is_relative_to(canonical_root):
        raise SkillPackagingError(f"SYMLINK-ESCAPE: {path.relative_to(canonical_root)}")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as failure:
        raise SkillPackagingError(
            f"SYMLINK-DANGLING: {path.relative_to(canonical_root)}: {failure}"
        ) from failure
    except (OSError, RuntimeError) as failure:
        raise SkillPackagingError(
            f"SYMLINK-CYCLE: {path.relative_to(canonical_root)}: {failure}"
        ) from failure
    if resolved.is_dir():
        raise SkillPackagingError(f"SYMLINK-DIRECTORY: {path.relative_to(canonical_root)}")
    return resolved


def _credential_failure(path: Path, canonical_root: Path, content: bytes) -> str | None:
    name = path.name
    if any(pattern.search(name) for pattern in _CREDENTIAL_NAME_PATTERNS):
        return f"CREDENTIAL: {path.relative_to(canonical_root)}"
    if any(pattern.search(content) for pattern in _CREDENTIAL_CONTENT_PATTERNS):
        return f"CREDENTIAL: {path.relative_to(canonical_root)}"
    return None


def _validate_compatibility_aliases(repo_root: Path, failures: list[str]) -> None:
    compatibility_root = repo_root / COMPATIBILITY_SKILLS_ROOT
    canonical_root = repo_root / CANONICAL_SKILLS_ROOT
    if not compatibility_root.is_dir():
        failures.append(f"COMPAT-MISSING: {COMPATIBILITY_SKILLS_ROOT}")
        return
    present = {entry.name for entry in compatibility_root.iterdir()}
    for unexpected in sorted(present - set(DECLARED_SKILLS)):
        failures.append(f"COMPAT-UNDECLARED: {unexpected}")
    for skill in DECLARED_SKILLS:
        entry = compatibility_root / skill
        if not entry.is_symlink():
            failures.append(f"COMPAT-DIVERGENT: {skill}")
            continue
        try:
            resolved = entry.resolve(strict=True)
        except OSError as failure:
            failures.append(f"COMPAT-DIVERGENT: {skill}: {failure}")
            continue
        if resolved != canonical_root / skill:
            failures.append(f"COMPAT-DIVERGENT: {skill}")


def source_inventory(repo_root: Path) -> tuple[ResourceRecord, ...]:
    """Inventory the six declared canonical skills and their compatibility aliases."""
    canonical_root = repo_root / CANONICAL_SKILLS_ROOT
    failures: list[str] = []
    if canonical_root.is_symlink() or not canonical_root.is_dir():
        raise SkillPackagingError(f"CANONICAL-ROOT-MISSING: {CANONICAL_SKILLS_ROOT}")
    canonical_root = canonical_root.resolve(strict=True)

    present = {entry.name for entry in canonical_root.iterdir()}
    for skill in sorted(set(DECLARED_SKILLS) - present):
        failures.append(f"DECLARED-MISSING: {skill}")
    for unexpected in sorted(present - set(DECLARED_SKILLS)):
        failures.append(f"UNDECLARED-COLLECTION: {unexpected}")
    _refuse(failures)

    records: list[ResourceRecord] = []
    for skill in DECLARED_SKILLS:
        _inventory_directory(canonical_root / skill, canonical_root, records)

    compatibility_failures: list[str] = []
    _validate_compatibility_aliases(repo_root, compatibility_failures)
    _refuse(compatibility_failures)
    return tuple(sorted(records, key=lambda record: record.path))


def _inventory_directory(
    directory: Path, canonical_root: Path, records: list[ResourceRecord]
) -> None:
    for entry in sorted(directory.iterdir(), key=lambda path: path.name):
        relative = entry.relative_to(canonical_root).as_posix()
        if entry.is_symlink():
            _validate_safe_file_symlink(entry, canonical_root)
            target = entry.resolve(strict=True)
            records.append(
                ResourceRecord(
                    path=relative,
                    kind="symlink",
                    digest=_digest(target.read_bytes()),
                    symlink_target=os.readlink(entry),
                )
            )
        elif entry.is_dir():
            _inventory_directory(entry, canonical_root, records)
        elif entry.is_file():
            content = entry.read_bytes()
            if failure := _credential_failure(entry, canonical_root, content):
                raise SkillPackagingError(failure)
            records.append(ResourceRecord(relative, "file", _digest(content)))
        else:
            raise SkillPackagingError(f"UNSUPPORTED-KIND: {relative}")


def _wheel_resource_names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return [
            name
            for name in archive.namelist()
            if name.startswith(PACKAGE_SKILLS_PREFIX)
            and not name.endswith("/")
        ]


def wheel_inventory(
    wheel: Path, expected: Sequence[ResourceRecord] | None = None
) -> tuple[ResourceRecord, ...]:
    """Inventory packaged resources, comparing them when expected records are supplied."""
    records: list[ResourceRecord] = []
    with zipfile.ZipFile(wheel) as archive:
        packaged_names = set(_wheel_resource_names(wheel))
        for name in sorted(packaged_names):
            relative = PurePosixPath(name.removeprefix(PACKAGE_SKILLS_PREFIX)).as_posix()
            skill = relative.split("/", 1)[0]
            if skill not in DECLARED_SKILLS:
                raise SkillPackagingError(f"UNDECLARED-PACKAGE: {relative}")
            content = archive.read(name)
            if failure := _credential_failure(
                Path(PACKAGE_SKILLS_PREFIX.rstrip("/")) / relative,
                Path(PACKAGE_SKILLS_PREFIX.rstrip("/")),
                content,
            ):
                raise SkillPackagingError(failure)
            records.append(ResourceRecord(relative, "file", _digest(content)))

    if expected is None:
        return tuple(records)

    packaged = {record.path: record for record in records}
    wanted = {record.path: record for record in expected}
    failures = [f"MISSING: {path}" for path in sorted(set(wanted) - set(packaged))]
    failures.extend(f"EXTRA: {path}" for path in sorted(set(packaged) - set(wanted)))
    for path in sorted(set(packaged) & set(wanted)):
        if packaged[path].digest != wanted[path].digest:
            failures.append(f"CONTENT-DIVERGENT: {path}")
    _refuse(failures)
    return tuple(records)


def _single(noun: str, paths: list[Path]) -> Path:
    if len(paths) != 1:
        raise SkillPackagingError(f"{noun}: expected one, found {paths or 'none'}")
    return paths[0]


def validate_release(
    repo_root: Path, dist_dir: Path | None = None
) -> tuple[Path, Path]:
    """Validate the source, wheel, sdist and a wheel rebuilt from the unpacked sdist."""
    repo_root = repo_root.resolve()
    dist = repo_root / "dist" if dist_dir is None else dist_dir.resolve()
    source = source_inventory(repo_root)
    wheel = _single("WHEEL", sorted(dist.glob("*.whl")))
    sdist = _single("SDIST", sorted(dist.glob("*.tar.gz")))
    wheel_inventory(wheel, source)

    uv = shutil.which("uv")
    if uv is None:
        raise SkillPackagingError("BUILD-TOOL-MISSING: uv")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = ""
    environment.pop("VIRTUAL_ENV", None)
    with tempfile.TemporaryDirectory(prefix="ergane-skill-rebuild-") as temporary:
        temporary_root = Path(temporary)
        unpacked = temporary_root / "unpacked"
        with tarfile.open(sdist, "r:*") as archive:
            archive.extractall(unpacked, filter="data")
        extracted_root = next(unpacked.iterdir())
        subprocess.run(
            [uv, "build", "--wheel", "--out-dir", "dist"],
            cwd=extracted_root,
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        rebuilt = _single("REBUILT-WHEEL", sorted((extracted_root / "dist").glob("*.whl")))
        wheel_inventory(rebuilt, source)
    return wheel, sdist


def main(argv: Sequence[str] | None = None) -> int:
    """Run release validation from the release workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate-release",))
    parser.add_argument("--dist", default="dist", type=Path)
    arguments = parser.parse_args(argv)
    try:
        validate_release(Path.cwd(), arguments.dist)
    except (SkillPackagingError, subprocess.SubprocessError) as failure:
        print(f"VALIDATION-FAIL: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
