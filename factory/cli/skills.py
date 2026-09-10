"""Pure inventory and release validation helpers for canonical operator skills."""

from __future__ import annotations

import argparse
import importlib
import hashlib
import json
import os
import re
import shutil
import stat as stat_module
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


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

CANONICAL_DESTINATION = CANONICAL_SKILLS_ROOT.as_posix()
COMPATIBILITY_DESTINATION = COMPATIBILITY_SKILLS_ROOT.as_posix()
MANIFEST_REL = Path("ergane") / "skills" / "manifest.json"
MANIFEST_VERSION = 1
MANIFEST_NAME = MANIFEST_REL.name

SUPPORTED_CLIENTS: tuple[tuple[str, Path], ...] = (
    ("codex", CANONICAL_SKILLS_ROOT),
    ("claude", COMPATIBILITY_SKILLS_ROOT),
)
MIGRATION_RUNBOOK = "docs/codex-primary-operator-migration-runbook-2026-09-09.md"
SHARED_DISCOVERY_GATE = "shared-discovery gate"


class SkillPackagingError(Exception):
    """One or more named refusals from packaging validation."""


class ManifestError(SkillPackagingError):
    """A skill ownership manifest cannot be trusted."""


@dataclass(frozen=True)
class Collision:
    path: str
    state: str


@dataclass(frozen=True)
class InstallResult:
    """The known result of one explicit skill installation."""

    manifest_path: Path
    created: tuple[Path, ...]
    upgraded: tuple[Path, ...]
    current: tuple[Path, ...]
    collisions: tuple[Collision, ...]
    source_version: str | None
    package_version: str | None
    client_destinations: Mapping[str, Path]
    client_availability: Mapping[str, bool]

    def destination_for(self, client: str) -> Path:
        return self.client_destinations[client]

    def client_available(self, client: str) -> bool:
        return self.client_availability[client]

    @property
    def unavailable_clients(self) -> tuple[str, ...]:
        return tuple(
            client for client, available in self.client_availability.items() if not available
        )


@dataclass(frozen=True)
class SkillStatusEntry:
    """One filesystem comparison for a skill and supported client."""

    client: str
    skill: str
    state: str
    path: str
    package_version: str | None
    installed_version: str | None
    remedy: str


@dataclass(frozen=True)
class SkillsStatus:
    """The pure, read-only result of comparing packaged skills to destinations."""

    package_version: str | None
    manifest_status: str
    manifest_schema: int | None
    entries: tuple[SkillStatusEntry, ...]

    @property
    def rendered(self) -> str:
        return render_status(self)


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


def packaged_inventory() -> tuple[ResourceRecord, ...]:
    """Inventory the canonical payload carried by the installed package."""

    package_root = Path(importlib.import_module("factory").__file__).resolve().parent
    packaged_root = package_root / "skills"
    if all((packaged_root / skill).is_dir() for skill in DECLARED_SKILLS):
        records: list[ResourceRecord] = []
        _inventory_directory(packaged_root, packaged_root, records)
        return tuple(sorted(records, key=lambda record: record.path))

    canonical_root = package_root.parent / CANONICAL_SKILLS_ROOT
    if all((canonical_root / skill).is_dir() for skill in DECLARED_SKILLS):
        return source_inventory(package_root.parent)
    raise SkillPackagingError(
        f"CANONICAL-PACKAGE-MISSING: {packaged_root} and {canonical_root}"
    )


def _packaged_payload() -> tuple[tuple[ResourceRecord, ...], dict[str, bytes]]:
    records = packaged_inventory()
    package_root = Path(importlib.import_module("factory").__file__).resolve().parent
    packaged_root = package_root / "skills"
    source_root = package_root.parent / CANONICAL_SKILLS_ROOT
    canonical_root = packaged_root if packaged_root.is_dir() else source_root
    payload: dict[str, bytes] = {}
    for record in records:
        path = canonical_root / record.path
        payload[record.path] = path.read_bytes()
    return records, payload


def _source_version() -> str | None:
    from factory.supervision.engine_identity import cli_version

    version = cli_version()
    return None if version == "unknown" else version


def _skill_digest(records: Sequence[ResourceRecord], skill: str) -> str:
    selected = sorted(
        (record for record in records if record.path.split("/", 1)[0] == skill),
        key=lambda record: record.path,
    )
    payload = "\0".join(f"{record.path}:{record.digest}" for record in selected)
    return _digest(payload.encode("utf-8"))


def _current_skill_digest(root: Path, records: Sequence[ResourceRecord], skill: str) -> str | None:
    lines: list[str] = []
    for record in sorted(
        (item for item in records if item.path.split("/", 1)[0] == skill),
        key=lambda item: item.path,
    ):
        path = root / record.path
        try:
            content = path.read_bytes()
        except OSError:
            return None
        lines.append(f"{record.path}:{_digest(content)}")
    return _digest("\0".join(lines).encode("utf-8"))


def manifest_path() -> Path:
    """Return the declared operator-state ownership manifest path."""

    from factory.registry import resolve_state_home

    return resolve_state_home() / MANIFEST_REL


def _manifest_path_for_state(state_home: Path) -> Path:
    return Path(state_home) / MANIFEST_REL


def _safe_relative(value: object) -> PurePosixPath | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        return None
    return relative


def _manifest_path_error(raw_path: object, relative: PurePosixPath | None) -> str:
    if relative is None:
        if isinstance(raw_path, str) and ".." in raw_path.split("/"):
            return f"MANIFEST-PATH-OUT-OF-ROOT: {raw_path}"
        return f"MANIFEST-PATH-INVALID: {raw_path!r}"
    path = relative.as_posix()
    if path.startswith(f"{CANONICAL_DESTINATION}/") or path.startswith(
        f"{COMPATIBILITY_DESTINATION}/"
    ):
        return f"MANIFEST-PATH-INVALID: {path}"
    return f"MANIFEST-PATH-OUT-OF-ROOT: {path}"


def _validate_manifest(document: object) -> dict[str, dict[str, Any]]:
    if not isinstance(document, dict):
        raise ManifestError("MANIFEST-MALFORMED: document is not an object")
    if document.get("schema") != MANIFEST_VERSION:
        raise ManifestError(
            f"MANIFEST-SCHEMA-UNSUPPORTED: {document.get('schema')!r}; wanted {MANIFEST_VERSION}"
        )
    if document.get("canonical_destination") != CANONICAL_DESTINATION:
        raise ManifestError(
            f"MANIFEST-DESTINATION-INVALID: canonical {document.get('canonical_destination')!r}"
        )
    if document.get("compatibility_destination") != COMPATIBILITY_DESTINATION:
        raise ManifestError(
            f"MANIFEST-DESTINATION-INVALID: compatibility {document.get('compatibility_destination')!r}"
        )
    for field in ("source_version", "package_version"):
        value = document.get(field)
        if value is not None and not isinstance(value, str):
            raise ManifestError(f"MANIFEST-MALFORMED: {field}")

    raw_entries = document.get("entries")
    if not isinstance(raw_entries, dict):
        raise ManifestError("MANIFEST-MALFORMED: entries")
    entries: dict[str, dict[str, Any]] = {}
    for raw_path, raw_entry in raw_entries.items():
        relative = _safe_relative(raw_path)
        if relative is None:
            raise ManifestError(_manifest_path_error(raw_path, relative))
        path = relative.as_posix()
        in_canonical = path.startswith(f"{CANONICAL_DESTINATION}/")
        in_compatibility = path.startswith(f"{COMPATIBILITY_DESTINATION}/")
        if not in_canonical and not in_compatibility:
            raise ManifestError(_manifest_path_error(raw_path, relative))
        if not isinstance(raw_entry, dict):
            raise ManifestError(f"MANIFEST-ENTRY-MALFORMED: {path}")
        digest = raw_entry.get("digest")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ManifestError(f"MANIFEST-DIGEST-INVALID: {path}")
        kind = raw_entry.get("kind")
        if in_canonical:
            if kind != "file" or len(relative.parts) < 4:
                raise ManifestError(f"MANIFEST-ENTRY-INVALID: {path}")
            entries[path] = {"kind": "file", "digest": digest}
            continue
        if len(relative.parts) != 3 or kind != "alias":
            raise ManifestError(f"MANIFEST-ENTRY-INVALID: {path}")
        target = raw_entry.get("target")
        expected_target = f"../../{CANONICAL_DESTINATION}/{relative.name}"
        if target != expected_target:
            raise ManifestError(f"MANIFEST-ALIAS-INVALID: {path}")
        entries[path] = {"kind": "alias", "digest": digest, "target": target}
    return entries


def _read_manifest(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not path.exists():
        document: dict[str, Any] = {}
        return document, {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as failure:
        raise ManifestError(f"MANIFEST-UNREADABLE: {path}: {failure}") from failure
    return document, _validate_manifest(document)


def _status_manifest(path: Path) -> tuple[str, int | None, str | None]:
    if not path.exists():
        return "unavailable-version", None, None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "unsupported-manifest", None, None
    if not isinstance(document, dict):
        return "unsupported-manifest", None, None
    schema = document.get("schema")
    schema_value = schema if isinstance(schema, int) and not isinstance(schema, bool) else None
    installed = document.get("package_version")
    if installed is None:
        installed = document.get("source_version")
    if installed is not None and not isinstance(installed, str):
        installed = None
    try:
        _validate_manifest(document)
    except ManifestError:
        return "unsupported-manifest", schema_value, installed
    return "available", schema_value, installed


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.ergane-install-{os.getpid()}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_replace_symlink(path: Path, target: str) -> None:
    temporary = path.with_name(f".{path.name}.ergane-install-{os.getpid()}.tmp")
    os.symlink(target, temporary)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def _ensure_parents(path: Path) -> None:
    missing: list[Path] = []
    for parent in path.parents:
        if parent.exists():
            if parent.is_symlink() or not parent.is_dir():
                raise SkillPackagingError(f"DESTINATION-PARENT-SYMLINK: {parent}")
            continue
        missing.append(parent)
    for parent in reversed(missing):
        parent.mkdir()


def _lstat_kind(path: Path) -> tuple[str, int, str | None] | None:
    try:
        stat_result = path.lstat()
    except FileNotFoundError:
        return None
    if stat_module.S_ISLNK(stat_result.st_mode):
        return ("symlink", None, os.readlink(path))
    if stat_module.S_ISREG(stat_result.st_mode):
        try:
            return ("file", _digest(path.read_bytes()), None)
        except OSError:
            return ("file", None, None)
    if stat_module.S_ISDIR(stat_result.st_mode):
        return ("directory", _digest(path.name.encode("utf-8")), None)
    return ("other", _digest(str(stat_result.st_ino).encode("utf-8")), None)


def _parent_collision(home: Path, relative: PurePosixPath) -> Path | None:
    current = home
    for part in relative.parts[:-1]:
        current = current / part
        try:
            stat_result = current.lstat()
        except FileNotFoundError:
            return None

        if stat_module.S_ISLNK(stat_result.st_mode) or not stat_module.S_ISDIR(stat_result.st_mode):
            return current.relative_to(home)
    return None


def _classify_file(
    path: str,
    absolute: Path,
    digest: str,
    manifest_entries: Mapping[str, dict[str, Any]],
) -> str:
    current = _lstat_kind(absolute)
    if current is None:
        return "absent"
    kind, current_digest, _ = current
    owned = manifest_entries.get(path)
    if kind != "file":
        return "unowned-conflicting"
    if owned and owned.get("kind") == "file":
        if current_digest == digest:
            return "unchanged-owned"
        if current_digest == owned["digest"]:
            return "safely-upgradeable-owned"
        return "modified-owned"
    if current_digest == digest:
        return "identical-unowned"
    return "unowned-conflicting"


def _classify_alias(
    path: str,
    absolute: Path,
    target: str,
    digest: str,
    manifest_entries: Mapping[str, dict[str, Any]],
    records: Sequence[ResourceRecord],
    canonical_root: Path,
    canonical_safe_upgrade: bool,
) -> str:
    current = _lstat_kind(absolute)
    if current is None:
        return "absent"
    kind, current_digest, current_target = current
    if kind != "symlink" or current_target != target:
        return "broken-alias"
    current_digest = _current_skill_digest(canonical_root, records, Path(path).name)
    if current_digest is None:
        return "broken-alias"
    owned = manifest_entries.get(path)
    if owned and owned.get("kind") == "alias":
        if current_digest == digest:
            return "unchanged-owned"
        if canonical_safe_upgrade:
            return "safely-upgradeable-owned"
        return "modified-owned"
    if current_digest == digest:
        return "identical-unowned"
    return "unowned-conflicting"


def install() -> InstallResult:
    """Plan and atomically apply one explicit skill installation."""

    home_value = os.environ.get("HOME")
    if not home_value:
        raise SkillPackagingError("HOME-DECLARATION-MISSING: HOME")
    home = Path(home_value)
    path = manifest_path()
    prior_document, manifest_entries = _read_manifest(path)
    records, payload = _packaged_payload()
    source_version = _source_version()

    actions: list[dict[str, Any]] = []
    collision_states: dict[str, str] = {}
    created: list[Path] = []
    upgraded: list[Path] = []
    current: list[Path] = []

    canonical_absent = {skill for skill in DECLARED_SKILLS if not any(
        record.path.split("/", 1)[0] == skill for record in records
    )}

    for record in records:
        relative = PurePosixPath(CANONICAL_DESTINATION) / record.path
        absolute = home / relative
        parent = _parent_collision(home, relative)
        if parent is not None:
            collision_states[parent.as_posix()] = "parent-collision"
            actions.append({"path": relative, "absolute": absolute, "state": "parent-collision"})
            continue
        state = _classify_file(
            relative.as_posix(), absolute, record.digest, manifest_entries
        )
        action: dict[str, Any] = {
            "path": relative,
            "absolute": absolute,
            "state": state,
            "record": record,
            "content": payload[record.path],
        }
        actions.append(action)
        if state == "absent":
            action["apply"] = "write"
        elif state == "safely-upgradeable-owned":
            action["apply"] = "write"
        elif state == "unchanged-owned":
            action["apply"] = "none"
        else:
            action["apply"] = "none"

    for skill in DECLARED_SKILLS:
        canonical_skill = f"{CANONICAL_DESTINATION}/{skill}"
        canonical_ready = not any(
            action["path"].as_posix().startswith(f"{canonical_skill}/")
            and action["state"]
            not in {"absent", "unchanged-owned", "safely-upgradeable-owned"}
            for action in actions
        )
        relative = PurePosixPath(COMPATIBILITY_DESTINATION) / skill
        absolute = home / relative
        target = f"../../{CANONICAL_DESTINATION}/{skill}"
        if skill in canonical_absent:
            actions.append(
                {
                    "path": relative,
                    "absolute": absolute,
                    "state": "canonical-missing",
                }
            )
            continue
        if not canonical_ready:
            actions.append(
                {
                    "path": relative,
                    "absolute": absolute,
                    "state": "canonical-collision",
                }
            )
            continue
        parent = _parent_collision(home, relative)
        if parent is not None:
            collision_states[parent.as_posix()] = "parent-collision"
            actions.append({"path": relative, "absolute": absolute, "state": "parent-collision"})
            continue
        digest = _skill_digest(records, skill)
        canonical_safe_upgrade = any(
            action["path"].as_posix().startswith(f"{canonical_skill}/")
            and action["state"] == "safely-upgradeable-owned"
            for action in actions
        )
        state = _classify_alias(
            relative.as_posix(),
            absolute,
            target,
            digest,
            manifest_entries,
            records,
            home / CANONICAL_SKILLS_ROOT,
            canonical_safe_upgrade,
        )
        actions.append(
            {
                "path": relative,
                "absolute": absolute,
                "state": state,
                "kind": "alias",
                "target": target,
                "digest": digest,
            }
        )
        if state == "absent":
            actions[-1]["apply"] = "link"
        elif state == "safely-upgradeable-owned":
            actions[-1]["apply"] = "none"
        else:
            actions[-1]["apply"] = "none"

    for action in actions:
        state = action["state"]
        absolute: Path = action["absolute"]
        if state in {"unchanged-owned"}:
            current.append(absolute)
        elif state in {"unowned-conflicting", "identical-unowned", "modified-owned", "broken-alias", "parent-collision", "canonical-missing"}:
            collision_states[action["path"].as_posix()] = state
        elif state == "canonical-collision":
            collision_states[action["path"].as_posix()] = "canonical-collision"
        elif action.get("apply") == "write":
            try:
                _ensure_parents(absolute)
                _atomic_write_bytes(absolute, action["content"])
                if state == "safely-upgradeable-owned":
                    upgraded.append(absolute)
                    action["state"] = "upgraded"
                else:
                    created.append(absolute)
                    action["state"] = "created"
            except (OSError, SkillPackagingError) as failure:
                action["state"] = "write-failed"
                collision_states[action["path"].as_posix()] = "write-failed"
                action["failure"] = str(failure)
        elif action.get("apply") == "link":
            try:
                _ensure_parents(absolute)
                _atomic_replace_symlink(absolute, action["target"])
                created.append(absolute)
                action["state"] = "created"
            except (OSError, SkillPackagingError) as failure:
                action["state"] = "link-failed"
                collision_states[action["path"].as_posix()] = "link-failed"
                action["failure"] = str(failure)
        elif state == "safely-upgradeable-owned":
            upgraded.append(absolute)
            action["state"] = "upgraded"

    fresh_entries: dict[str, dict[str, Any]] = dict(manifest_entries)
    for action in actions:
        if action["state"] not in {"created", "unchanged-owned", "upgraded"}:
            continue
        if action["state"] == "upgraded" and action.get("kind") == "file" and action.get("apply") != "write":
            continue
        if "record" in action:
            fresh_entries[action["path"].as_posix()] = {
                "kind": "file",
                "digest": action["record"].digest,
            }
        elif action.get("kind") == "alias":
            fresh_entries[action["path"].as_posix()] = {
                "kind": "alias",
                "digest": action["digest"],
                "target": action["target"],
            }

    document = {
        "schema": MANIFEST_VERSION,
        "source_version": source_version,
        "package_version": source_version,
        "canonical_destination": CANONICAL_DESTINATION,
        "compatibility_destination": COMPATIBILITY_DESTINATION,
        "entries": fresh_entries,
    }
    collisions = tuple(
        Collision(path, state)
        for path, state in sorted(collision_states.items())
    )


    if (
        not created
        and not upgraded
        and fresh_entries == manifest_entries
        and prior_document.get("source_version") == source_version
        and prior_document.get("package_version") == source_version
        and path.exists()
    ):
        pass
    else:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            content = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
            temporary = path.with_name(f".{MANIFEST_NAME}.ergane-install-{os.getpid()}.tmp")
            try:
                temporary.write_bytes(content)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        except OSError as failure:
            collision_states[str(MANIFEST_REL)] = "manifest-replace-failed"
            collisions = tuple(
                Collision(path, state)
                for path, state in sorted(collision_states.items())
            )

    client_destinations: dict[str, Path] = {}
    client_availability: dict[str, bool] = {}
    for client, destination in SUPPORTED_CLIENTS:
        client_destinations[client] = home / destination
        client_availability[client] = shutil.which(client) is not None
    return InstallResult(
        manifest_path=path,
        created=tuple(created),
        upgraded=tuple(upgraded),
        current=tuple(current),
        collisions=collisions,
        source_version=source_version,
        package_version=source_version,
        client_destinations=client_destinations,
        client_availability=client_availability,
    )


def render_install(result: InstallResult) -> str:
    """Render one installation report without hiding partial failures."""

    lines = [f"skills install: {result.manifest_path}"]
    if result.created:
        lines.append("created:")
        lines.extend(f"  {path}" for path in result.created)
    if result.upgraded:
        lines.append("upgraded:")
        lines.extend(f"  {path}" for path in result.upgraded)
    if result.collisions:
        lines.append("preserved collisions:")
        lines.extend(
            f"  {collision.path} ({collision.state})" for collision in result.collisions
        )
    if result.unavailable_clients:
        lines.append("clients unavailable: " + ", ".join(result.unavailable_clients))
    return "\n".join(lines)


def _state_remedy(state: str) -> str:
    remedies = {
        "absent": "Run `ergane skills install`.",
        "current-filesystem": (
            "No repair needed; fresh client loading remains unqualified. "
            f"Authorize fresh evidence through the {MIGRATION_RUNBOOK} "
            f"{SHARED_DISCOVERY_GATE}."
        ),
        "stale": "Run `ergane skills install` after preserving desired local changes.",
        "modified": "Preserve the local bytes; run install for any unmodified paths.",
        "collided": "Preserve the conflicting path; resolve it deliberately before install.",
        "broken-alias": (
            "Run `ergane skills install` to replace the broken compatibility alias."
        ),
        "unavailable-version": "Install the packaged CLI to provide skill version metadata.",
        "unsupported-manifest": (
            "Back up and explicitly migrate or remove the unsupported manifest."
        ),
    }
    return remedies[state]


def _canonical_state(
    skill: str,
    records: Sequence[ResourceRecord],
    payload: Mapping[str, bytes],
    home: Path,
    manifest_entries: Mapping[str, dict[str, Any]],
) -> str:
    selected = [record for record in records if record.path.split("/", 1)[0] == skill]
    if not selected:
        return "absent"
    states: list[str] = []
    for record in selected:
        relative = PurePosixPath(CANONICAL_DESTINATION) / record.path
        absolute = home / relative
        current = _lstat_kind(absolute)
        if current is None:
            states.append("absent")
            continue
        kind, current_digest, _ = current
        if kind != "file" or current_digest is None:
            states.append("collided")
            continue
        owned = manifest_entries.get(relative.as_posix())
        if owned and owned.get("kind") == "file":
            if current_digest == record.digest:
                states.append("current")
            elif current_digest == owned.get("digest"):
                states.append("stale")
            else:
                states.append("modified")
        elif current_digest == record.digest:
            states.append("current")
        else:
            states.append("collided")
    if "modified" in states:
        return "modified"
    if "collided" in states:
        return "collided"
    if any(state in {"absent", "stale"} for state in states):
        return "stale" if "stale" in states else "absent"
    return "current-filesystem"


def _compatibility_state(
    skill: str,
    records: Sequence[ResourceRecord],
    home: Path,
    manifest_entries: Mapping[str, dict[str, Any]],
    expected_digest: str,
) -> str:
    relative = PurePosixPath(COMPATIBILITY_DESTINATION) / skill
    absolute = home / relative
    current = _lstat_kind(absolute)
    if current is None:
        return "absent"
    kind, _, current_target = current
    target = f"../../{CANONICAL_DESTINATION}/{skill}"
    if kind != "symlink" or current_target != target:
        return "broken-alias"
    current_digest = _current_skill_digest(
        home / CANONICAL_SKILLS_ROOT, records, skill
    )
    if current_digest is None:
        return "broken-alias"
    owned = manifest_entries.get(relative.as_posix())
    if owned and owned.get("kind") == "alias":
        if current_digest == expected_digest:
            return "current"
        return "modified"
    if current_digest == expected_digest:
        return "current"
    return "collided"


def skills_status() -> SkillsStatus:
    """Compare packaged skill resources to declared destinations without mutation."""

    home_value = os.environ.get("HOME")
    if not home_value:
        raise SkillPackagingError("HOME-DECLARATION-MISSING: HOME")
    home = Path(home_value)
    path = manifest_path()
    manifest_status, manifest_schema, installed_version = _status_manifest(path)
    manifest_entries: dict[str, dict[str, Any]] = {}
    if manifest_status == "available":
        _, manifest_entries = _read_manifest(path)
    records, payload = _packaged_payload()
    package_version = _source_version()
    if package_version is None:
        manifest_status = "unavailable-version"
        entries = tuple(
            SkillStatusEntry(
                client=client,
                skill=skill,
                state="unavailable-version",
                path=(home / destination / skill).relative_to(home).as_posix(),
                package_version=None,
                installed_version=installed_version,
                remedy=_state_remedy("unavailable-version"),
            )
            for skill in DECLARED_SKILLS
            for client, destination in SUPPORTED_CLIENTS
        )
        return SkillsStatus(None, manifest_status, manifest_schema, entries)
    if manifest_status == "unsupported-manifest":
        entries = tuple(
            SkillStatusEntry(
                client=client,
                skill=skill,
                state="unsupported-manifest",
                path=(home / destination / skill).relative_to(home).as_posix(),
                package_version=package_version,
                installed_version=installed_version,
                remedy=_state_remedy("unsupported-manifest"),
            )
            for skill in DECLARED_SKILLS
            for client, destination in SUPPORTED_CLIENTS
        )
        return SkillsStatus(package_version, manifest_status, manifest_schema, entries)

    stale_installed = (
        installed_version is not None
        and package_version is not None
        and installed_version != package_version
    )
    observed: list[SkillStatusEntry] = []
    for skill in DECLARED_SKILLS:
        for client, destination in SUPPORTED_CLIENTS:
            state = (
                _canonical_state(skill, records, payload, home, manifest_entries)
                if destination == CANONICAL_SKILLS_ROOT
                else _compatibility_state(
                    skill,
                    records,
                    home,
                    manifest_entries,
                    _skill_digest(records, skill),
                )
            )
            if state in {"current", "current-filesystem", "stale"} and stale_installed:
                state = "stale"
            elif state == "current":
                state = "current-filesystem"
            observed.append(
                SkillStatusEntry(
                    client=client,
                    skill=skill,
                    state=state,
                    path=(home / destination / skill).relative_to(home).as_posix(),
                    package_version=package_version,
                    installed_version=installed_version,
                    remedy=_state_remedy(state),
                )
            )
    return SkillsStatus(package_version, manifest_status, manifest_schema, tuple(observed))


def render_status(status: SkillsStatus) -> str:
    """Render filesystem status without claiming fresh client discovery."""

    package = status.package_version or "unavailable"
    installed = next(
        (entry.installed_version for entry in status.entries if entry.installed_version),
        "unavailable",
    )
    schema = "unavailable" if status.manifest_schema is None else str(status.manifest_schema)
    lines = [
        f"skills status: package={package} installed={installed} "
        f"manifest={status.manifest_status} schema={schema}",
        (
            "Filesystem status is not fresh client-loading evidence; client loading "
            "remains unqualified until separately authorized."
        ),
    ]
    lines.extend(
        f"{entry.client} {entry.skill} {entry.path}: {entry.state}"
        for entry in status.entries
    )
    lines.extend(f"remedy: {entry.remedy}" for entry in status.entries)
    return "\n".join(lines)


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
