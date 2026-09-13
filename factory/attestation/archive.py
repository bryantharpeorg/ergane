"""Deterministic, bounded, offline story-packet archives."""

from __future__ import annotations

import dataclasses
import hashlib
import html
import io
import json
import math
import os
import re
import sqlite3
import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Sequence

from factory.attestation.journal import (
    read_attempt_evidence,
    read_launches,
    read_scoring_evaluations,
)
from factory.attestation.usage import read_usage_evidence
from factory.verify.models import ArtifactType, GateArtifact, VerificationResult
from factory.verify.store import connect_readonly, node_history

FORMAT = "ergane-attestation-story"
GENERATOR_VERSION = "1.0.0"
MANIFEST_NAME = "manifest.json"
DIGEST_NAME = "manifest.sha256"
REPORT_NAME = "report.md"
ATTACHMENT_PREFIX = "attachments/"


@dataclass(frozen=True)
class ArchiveLimits:
    max_artifact_bytes: int = 8 * 1024 * 1024
    max_total_bytes: int = 32 * 1024 * 1024
    max_archive_bytes: int = 32 * 1024 * 1024
    max_expanded_bytes: int = 64 * 1024 * 1024
    max_entries: int = 512

    def __post_init__(self) -> None:
        values = dataclasses.asdict(self)
        for name, value in values.items():
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive, finite, and numeric")


class Identity(NamedTuple):
    gate: str
    path: str
    dispatch: str
    capture_id: str

    def key(self) -> str:
        return "|".join(self)


class Item(NamedTuple):
    identity: Identity
    status: str
    reason: str
    sensitivity: str = "text"
    archive_name: str | None = None


class ExportResult(NamedTuple):
    archive: Path
    revision: str
    content_revision: str
    predecessor_revision: str | None
    complete: bool
    items: tuple[Item, ...]

    @property
    def predecessor(self) -> str | None:
        return self.predecessor_revision


class PacketError(Exception):
    """A bounded refusal; the packet is not published or accepted."""


@dataclass(frozen=True)
class Subject:
    target: str
    epic_id: str
    node_id: str

    @property
    def value(self) -> str:
        return f"{self.target}:{self.epic_id}/{self.node_id}"


def parse_subject(value: str) -> Subject:
    if not value or ":" not in value or "/" not in value.partition(":")[2]:
        raise PacketError("subject must be TARGET:EPIC/NODE")
    target, remainder = value.split(":", 1)
    epic, node = remainder.split("/", 1)
    if not target or not epic or not node:
        raise PacketError("subject must be TARGET:EPIC/NODE")
    _safe_component(target.replace("/", "-"), "target")
    _safe_component(epic, "epic")
    _safe_component(node, "node")
    return Subject(target, epic, node)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _safe_component(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) or value in {".", ".."}:
        raise PacketError(f"unsafe {label}")
    return value


def _packet_directory(root: Path, subject: Subject) -> Path:
    target = _safe_component(subject.target.replace("/", "-"), "target")
    path = root / "attestation" / "packets" / target / subject.epic_id / subject.node_id
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    for directory in (path, *path.parents[:4]):
        os.chmod(directory, 0o700)
    return path


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise PacketError(f"missing {label}: {path}")
    return path


def show_subject(root: Path, subject: str, revision: str | None = None) -> dict[str, object]:
    parsed = parse_subject(subject)
    if not root.is_dir():
        raise PacketError(f"missing evidence root: {root}")
    journal = _require_file(root / "attestation.db", "attestation journal")
    connection = sqlite3.connect(f"file:{journal}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        launches = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM launches WHERE target = ? AND epic_id = ? AND node_id = ?"
                " ORDER BY launch_ordinal",
                (parsed.target, parsed.epic_id, parsed.node_id),
            )
        ]
        alias_prefix = f"{parsed.epic_id}:{parsed.node_id}:"
        evaluations = [
            dict(row)
            for row in connection.execute(
                "SELECT payload FROM evidence_records ORDER BY evidence_id"
            )
        ]
        evaluations = [
            row
            for row in evaluations
            if str(json.loads(row["payload"]).get("key_alias", "")).startswith(alias_prefix)
        ]
    finally:
        connection.close()
    if not launches:
        raise PacketError(f"no subject {subject}")
    if revision is None and len(launches) > 1:
        raise PacketError("ambiguous subject; pass an explicit revision")
    if revision is not None:
        selected = []
        invocation_ids = {launch["invocation_id"] for launch in launches}
        payloads = [json.loads(item["payload"]) for item in evaluations]
        for launch in launches:
            if launch["outcome"] == revision or (
                launch["invocation_id"] in invocation_ids
                and any(payload.get("tested_revision") == revision for payload in payloads)
            ):
                selected.append(launch)
        if not selected:
            raise PacketError(f"revision {revision} not found")
    return {"subject": subject, "launches": launches, "latest_launch": launches[-1], "revision": revision}


def _find_artifacts(results: Sequence[VerificationResult], identity: Identity) -> tuple[GateArtifact, ...]:
    found = [
        artifact
        for result in results
        for gate in result.gate_results
        for artifact in gate.artifacts
        if Identity(artifact.gate, artifact.path, artifact.dispatch, artifact.capture_id) == identity
    ]
    unique = {repr(dataclasses.asdict(item)) for item in found}
    if len(unique) > 1:
        raise PacketError(f"ambiguous artifact selection: {identity.key()}")
    return tuple(found)


def _artifact_root(root: Path) -> Path:
    path = root / "artifacts"
    if not path.is_dir():
        raise PacketError(f"missing artifact store: {path}")
    return path


def _open_bounded(source: Path, artifact_root: Path, limits: ArchiveLimits) -> bytes:
    try:
        relative = source.relative_to(artifact_root)
    except ValueError as error:
        raise PacketError("artifact path escapes artifact containment") from error
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise PacketError("artifact path escapes artifact containment")
    if any(part in {".codex", "sessions"} or "rollout" in part for part in relative.parts):
        raise PacketError("raw CLI transcripts are excluded")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory = os.open(artifact_root, directory_flags | no_follow)
    try:
        for part in relative.parts[:-1]:
            part_stat = os.lstat(part, dir_fd=directory)
            if stat.S_ISLNK(part_stat.st_mode):
                raise PacketError("artifact source path contains a symlink")
            if not stat.S_ISDIR(part_stat.st_mode):
                raise PacketError("artifact source path is not a directory")
            next_directory = os.open(part, directory_flags | no_follow, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        final_stat = os.lstat(relative.parts[-1], dir_fd=directory)
        if stat.S_ISLNK(final_stat.st_mode):
            raise PacketError("artifact source is a symlink")
        if stat.S_ISFIFO(final_stat.st_mode):
            raise PacketError("artifact source is a FIFO")
        if not stat.S_ISREG(final_stat.st_mode):
            raise PacketError("artifact source is not a regular file")
        if final_stat.st_nlink != 1:
            raise PacketError("artifact source is a hardlink alias")
        file_descriptor = os.open(relative.parts[-1], flags | no_follow, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(file_descriptor, "rb", closefd=True) as handle:
        file_stat = os.fstat(handle.fileno())
        if stat.S_ISLNK(file_stat.st_mode):
            raise PacketError("artifact source is a symlink")
        if not stat.S_ISREG(file_stat.st_mode):
            if stat.S_ISFIFO(file_stat.st_mode):
                raise PacketError("artifact source is a FIFO")
            raise PacketError("artifact source is not a regular file")
        if file_stat.st_nlink != 1:
            raise PacketError("artifact source is a hardlink alias")
        if file_stat.st_size > limits.max_artifact_bytes:
            raise PacketError("artifact is too large for max_artifact_bytes")
        data = handle.read(limits.max_artifact_bytes + 1)
    if len(data) > limits.max_artifact_bytes:
        raise PacketError("artifact is too large for max_artifact_bytes")
    return data


def _source_status(root: Path, artifact: GateArtifact, limits: ArchiveLimits) -> tuple[str, str, bytes | None]:
    if not artifact.present:
        return "missing", "artifact was not stored", None
    if artifact.status != "permitted":
        return artifact.status, artifact.reason or f"artifact status is {artifact.status}", None
    if not artifact.stored_path:
        return "missing", "artifact bytes were not retained", None
    if artifact.type == ArtifactType.OPAQUE and ("codex" in artifact.path or "session" in artifact.path or "rollout" in artifact.path):
        return "refused", "raw CLI transcripts are excluded", None
    source = Path(artifact.stored_path)
    try:
        data = _open_bounded(source, _artifact_root(root), limits)
    except PacketError as error:
        message = str(error)
        return ("oversized", message, None) if "too large for max_artifact_bytes" in message else ("refused", message, None)
    if artifact.digest and artifact.digest != hashlib.sha256(data).hexdigest():
        return "refused", "stored artifact digest does not match retained bytes", None
    return "included", "retained declared artifact", data


def _redact(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"/(?:home|Users|root)/[^ \t\r\n]+", "[PRIVATE_PATH]", text)
    text = re.sub(r"(?i)\b\w*(?:api[_-]?token|token|authorization)\b\s*[:=]\s*\S+", "[REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", text)
    return html.escape(text, quote=True)


def _usage_rows(root: Path, launches: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    ledger = root / "usage.db"
    if not ledger.is_file():
        return []
    aliases = {str(launch.get("key_alias")) for launch in launches if launch.get("key_alias")}
    return [
        {
            "key_alias": evidence.key_alias,
            "builder_or_judge": evidence.builder_or_judge,
            "usage_source": evidence.usage_source,
            "usage_status": evidence.usage_status,
            "cost_basis": evidence.cost_basis,
            "complete_total": evidence.complete_total,
        }
        for evidence in read_usage_evidence(ledger)
        if evidence.key_alias in aliases
    ]


def _report(root: Path, subject: Subject, results: Sequence[VerificationResult], launches: Sequence[dict[str, object]], evaluations: Sequence[dict[str, object]], completeness: Sequence[Item]) -> str:
    lines = [f"# Attestation: {html.escape(subject.value)}", ""]
    for launch in launches:
        lines.extend([
            f"- launch `{_redact(launch.get('invocation_id'))}`: outcome `{_redact(launch.get('outcome'))}`",
        ])
    lines.extend(["", "## Judge history", ""])
    for evaluation in evaluations:
        lines.append(f"- `{_redact(evaluation.get('evaluation_id'))}` status `{_redact(evaluation.get('status'))}`: {_redact(evaluation.get('feedback'))}")
        for scenario, passed, reasoning in evaluation.get("scenario_results", ()):
            lines.append(f"  - `{_redact(scenario)}`: `{'pass' if passed else 'fail'}` — {_redact(reasoning)}")
    lines.extend(["", "## Verification", ""])
    for result in results:
        lines.append(f"- attempt {result.attempt}: `{result.verdict.value}`")
    lines.extend(["", "## Completeness", ""])
    for item in completeness:
        lines.append(f"- `{item.identity.key()}`: `{item.status}` — {_redact(item.reason)}")
    lines.extend(["", "## Usage", ""])
    for row in _usage_rows(root, launches):
        lines.append(f"- {_redact(row)}")
    lines.extend(["", "Attachments are exact retained bytes. Opaque bytes are not redacted and may contain sensitive data."])
    return "\n".join(lines) + "\n"


def _read_existing_manifests(directory: Path) -> list[dict[str, object]]:
    manifests = []
    for path in sorted(directory.glob("*.zip")):
        try:
            with zipfile.ZipFile(path, "r") as archive:
                manifests.append(json.loads(archive.read(MANIFEST_NAME)))
        except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError):
            continue
    return manifests


def export_packet(
    root: Path,
    subject: str,
    *,
    output: Path | None = None,
    selectors: Sequence[Identity | tuple[str, str, str, str]] = (),
    limits: ArchiveLimits | None = None,
    strict: bool = False,
) -> ExportResult:
    parsed = parse_subject(subject)
    bounds = limits or ArchiveLimits()
    if not root.is_dir():
        raise PacketError(f"missing evidence root: {root}")
    journal = _require_file(root / "attestation.db", "attestation journal")
    verification_path = _require_file(root / "verification.db", "verification store")
    launches = [dataclasses.asdict(record) for record in read_launches(journal)]
    if not launches:
        raise PacketError(f"no subject {subject}")
    selected_launches = [
        launch for launch in launches
        if launch.get("target") == parsed.target and launch.get("epic_id") == parsed.epic_id and launch.get("node_id") == parsed.node_id
    ]
    if not selected_launches:
        raise PacketError(f"no subject {subject}")
    subject_launch = selected_launches[0]

    connection = connect_readonly(verification_path)
    connection.row_factory = None
    try:
        results = node_history(connection, parsed.epic_id, parsed.node_id)
    finally:
        connection.close()

    records = read_scoring_evaluations(journal)
    alias_prefix = f"{parsed.epic_id}:{parsed.node_id}:"
    evaluations = [
        dataclasses.asdict(record)
        for record in records
        if record.key_alias.startswith(alias_prefix)
    ]
    identities = tuple(Identity(*selector) for selector in selectors)
    if len(set(identities)) != len(identities):
        raise PacketError("duplicate artifact selection")
    items: list[Item] = []
    contents: dict[str, bytes] = {}
    total = 0
    used_names: set[str] = set()
    for identity in identities:
        found = _find_artifacts(results, identity)
        artifact = found[0] if found else None
        if artifact is None:
            item = Item(identity, "missing", "no matching captured artifact")
        else:
            status, reason, data = _source_status(root, artifact, bounds)
            sensitivity = "opaque" if artifact.type == ArtifactType.OPAQUE else "text"
            if data is None:
                item = Item(identity, status, reason, sensitivity)
            else:
                name = ATTACHMENT_PREFIX + _safe_component(Path(artifact.path).name, "artifact name")
                if name in used_names:
                    name = ATTACHMENT_PREFIX + f"{identity.capture_id}-{Path(artifact.path).name}"
                if name in used_names:
                    raise PacketError(f"duplicate archive name: {name}")
                total += len(data)
                if total > bounds.max_total_bytes:
                    item = Item(identity, "oversized", "selected artifacts are too large for max_total_bytes", sensitivity)
                else:
                    contents[name] = data
                    used_names.add(name)
                    item = Item(identity, "included", reason, sensitivity, name)
        items.append(item)

    incomplete = [item for item in items if item.status != "included"]
    if strict and incomplete:
        raise PacketError("packet is incomplete: " + "; ".join(f"{item.identity.key()}={item.status}" for item in incomplete))

    completeness = {
        item.identity.key(): {"status": item.status, "reason": item.reason}
        for item in items
    }
    report = _report(root, parsed, results, selected_launches, evaluations, items).encode("utf-8")
    contents[REPORT_NAME] = report
    entry_data = {
        name: {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "identity": next((item.identity._asdict() for item in items if item.archive_name == name), None),
            "sensitivity": next((item.sensitivity for item in items if item.archive_name == name), "text"),
        }
        for name, data in contents.items()
    }
    content_digest = hashlib.sha256(b"".join(contents[name] for name in sorted(contents))).hexdigest()
    directory = _packet_directory(root, parsed)
    existing = _read_existing_manifests(directory)
    matching = [manifest for manifest in existing if manifest.get("content_digest") == content_digest]
    if matching:
        revision = str(matching[0]["content_revision"])
        predecessor = matching[0].get("predecessor_revision")
    else:
        predecessor = max((str(item.get("content_revision")) for item in existing), default=None)
        revision = hashlib.sha256(
            f"{subject}\0{FORMAT}\0{subject_launch.get('spec_revision')}\0{subject_launch.get('spec_fingerprint')}\0{content_digest}\0{predecessor}".encode()
        ).hexdigest()
    manifest = {
        "schema_version": 1,
        "format": FORMAT,
        "generator_version": GENERATOR_VERSION,
        "subject": subject,
        "spec_revision": subject_launch.get("spec_revision"),
        "spec_fingerprint": subject_launch.get("spec_fingerprint"),
        "content_revision": revision,
        "content_digest": content_digest,
        "predecessor_revision": predecessor,
        "completeness": completeness,
        "entries": entry_data,
    }
    manifest_bytes = _canonical(manifest)
    archive_names = [MANIFEST_NAME, DIGEST_NAME, REPORT_NAME, *sorted(used_names)]
    if len(archive_names) > bounds.max_entries:
        raise PacketError("archive is too large for max_entries")
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in archive_names:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(
                info,
                manifest_bytes if name == MANIFEST_NAME
                else hashlib.sha256(manifest_bytes).hexdigest().encode() if name == DIGEST_NAME
                else contents[name],
            )
    archive_bytes = payload.getvalue()
    destination = output or directory / f"{revision}.zip"
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination.parent, 0o700)
    _atomic_archive_write(directory / f"{revision}.zip", archive_bytes)
    if destination.resolve() != (directory / f"{revision}.zip").resolve():
        _atomic_archive_write(destination, archive_bytes)
    return ExportResult(destination, revision, revision, predecessor, not incomplete, tuple(items))


def _atomic_archive_write(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() == data:
            return
        raise PacketError(f"refusing output collision: {path}")
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def read_manifest(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path, "r") as archive:
        return json.loads(archive.read(MANIFEST_NAME))


def verify_packet(path: Path, *, limits: ArchiveLimits | None = None) -> dict[str, object]:
    bounds = limits or ArchiveLimits()
    if not path.is_file():
        raise PacketError(f"missing archive: {path}")
    if path.stat().st_size > bounds.max_archive_bytes:
        raise PacketError("archive is too large for max_archive_bytes")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > bounds.max_entries:
                raise PacketError("archive is too large for max_entries")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise PacketError("duplicate archive entry")
            if any(info.is_dir() or info.filename.startswith("/") or ".." in Path(info.filename).parts for info in infos):
                raise PacketError("unsafe archive entry")
            if sum(info.compress_size for info in infos) > bounds.max_archive_bytes:
                raise PacketError("archive is too large for max_archive_bytes")
            if sum(info.file_size for info in infos) > bounds.max_expanded_bytes:
                raise PacketError("archive is too large for max_expanded_bytes")
            required = {MANIFEST_NAME, DIGEST_NAME, REPORT_NAME}
            if not required.issubset(names):
                raise PacketError("missing required archive entry")
            try:
                manifest_bytes = archive.read(MANIFEST_NAME)
                manifest = json.loads(manifest_bytes)
                manifest_digest = archive.read(DIGEST_NAME)
            except (KeyError, zipfile.BadZipFile, zlib.error, json.JSONDecodeError) as error:
                raise PacketError("unreadable manifest") from error
            try:
                digest = manifest_digest.decode("ascii", errors="strict")
            except UnicodeDecodeError as error:
                raise PacketError("manifest digest mismatch") from error
            if hashlib.sha256(manifest_bytes).hexdigest() != digest:
                raise PacketError("manifest digest mismatch")
            if manifest.get("schema_version") != 1 or manifest.get("format") != FORMAT:
                raise PacketError("unsupported packet format")
            entries = manifest.get("entries")
            if not isinstance(entries, dict):
                raise PacketError("invalid manifest entries")
            expected = required | set(entries)
            if set(names) != expected:
                raise PacketError("unlisted archive entry")
            expanded = 0
            for name, entry in entries.items():
                info = archive.getinfo(name)
                expanded += info.file_size
                if expanded > bounds.max_expanded_bytes:
                    raise PacketError("archive is too large for max_expanded_bytes")
                data = archive.read(name, pwd=None)
                if len(data) != entry.get("size") or hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                    raise PacketError(f"entry digest mismatch: {name}")
            return manifest
    except (zipfile.BadZipFile, zlib.error) as error:
        raise PacketError("corrupted archive") from error
