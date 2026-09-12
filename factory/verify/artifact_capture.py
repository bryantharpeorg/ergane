"""The bounded source-reading boundary used by artifact collection.

This module is deliberately a source boundary and nothing else.  It never
resolves the factory's operational root, writes durable evidence, runs a gate,
or changes a gate verdict.  Its results are internal capture records: bytes may
cross an in-process boundary, but they must never be copied onto a Temporal
activity result model.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath


_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_READ_CHUNK_BYTES = 64 * 1024


class SourceStatus(StrEnum):
    """What one bounded observation of a declared relative path observed."""

    PERMITTED = "permitted"
    ABSENT = "absent"
    OVERSIZED = "oversized"
    UNSAFE = "unsafe"
    UNSTABLE = "unstable"
    UNAVAILABLE = "unavailable"


class CaptureProvenance(StrEnum):
    """Freshness observed by comparing pre-gate and captured source bytes.

    `NEW` is relative to the supplied baseline only.  It never means that a
    gate produced the bytes: an absent or unusable baseline leaves `UNKNOWN`.
    """

    NEW = "new"
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SourceObservation:
    """A bounded source outcome, safe to return inside a process only."""

    status: SourceStatus
    bytes: bytes | None = None
    size: int | None = None
    digest: str | None = None
    metadata_digest: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SourceCapture:
    """A post-gate capture compared against the supplied pre-gate baseline."""

    status: SourceStatus
    provenance: CaptureProvenance
    bytes: bytes | None
    size: int | None
    digest: str | None
    metadata_digest: str | None
    reason: str | None
    pre_status: SourceStatus
    post_status: SourceStatus


def _relative_segments(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("relative path must be a non-empty string")
    candidate = PurePosixPath(relative_path)
    if candidate.is_absolute():
        raise ValueError("relative path must not be absolute")
    segments = candidate.parts
    if not segments or any(
        segment in {"", ".", "..", "/"} for segment in segments
    ):
        raise ValueError(
            "relative path must be normalized and contain no '.' or '..' segment"
        )
    return segments


def _metadata_digest(value: os.stat_result) -> str:
    metadata = (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
    digest = hashlib.sha256()
    for item in metadata:
        digest.update(f"{item}\0".encode("ascii"))
    return digest.hexdigest()


def _refusal(reason: str, *, absent: bool = False) -> SourceObservation:
    if absent:
        return SourceObservation(
            status=SourceStatus.ABSENT,
            reason="path does not name a file",
        )
    return SourceObservation(status=SourceStatus.UNSAFE, reason=reason)


def _open_bounded_root(root: os.PathLike[str] | str) -> int:
    if not os.path.isabs(os.fspath(root)):
        raise ValueError("worktree root must be absolute")
    flags = os.O_RDONLY | os.O_DIRECTORY | _CLOEXEC | _NOFOLLOW
    return os.open(root, flags)


def _observation_error(error: OSError) -> SourceObservation:
    if error.errno == errno.ENOENT:
        return _refusal("path does not name a file", absent=True)
    if error.errno == errno.ELOOP:
        return _refusal("path component is a symlink")
    return _refusal("source path could not be opened safely")


def _read_bounded_regular_file(
    descriptor: int,
    before: os.stat_result,
    byte_limit: int,
) -> SourceObservation:
    if not stat.S_ISREG(before.st_mode):
        return _refusal("source is not an ordinary regular file")
    if before.st_nlink != 1:
        return _refusal("source is a hardlink alias")

    payload = bytearray()
    remaining = byte_limit + 1
    while remaining:
        chunk = os.read(descriptor, min(remaining, _READ_CHUNK_BYTES))
        if not chunk:
            break
        payload.extend(chunk)
        remaining -= len(chunk)
        if len(payload) > byte_limit:
            break

    after = os.fstat(descriptor)
    metadata_digest = _metadata_digest(after)
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
    ):
        return SourceObservation(
            status=SourceStatus.UNSTABLE,
            size=after.st_size,
            metadata_digest=metadata_digest,
            reason="source changed during reading",
        )
    if len(payload) > byte_limit:
        return SourceObservation(
            status=SourceStatus.OVERSIZED,
            size=after.st_size,
            metadata_digest=metadata_digest,
            reason="source is larger than the supplied byte limit",
        )

    bounded_bytes = bytes(payload)
    return SourceObservation(
        status=SourceStatus.PERMITTED,
        bytes=bounded_bytes,
        size=after.st_size,
        digest=hashlib.sha256(bounded_bytes).hexdigest(),
        metadata_digest=metadata_digest,
    )


def _observe_relative_path(
    root: os.PathLike[str] | str,
    relative_path: str,
    byte_limit: int,
) -> SourceObservation:
    if byte_limit < 0:
        raise ValueError("byte limit must not be negative")
    segments = _relative_segments(relative_path)

    root_descriptor = -1
    parent_descriptor = -1
    source_descriptor = -1
    try:
        root_descriptor = _open_bounded_root(root)
        parent_descriptor = root_descriptor
        for segment in segments[:-1]:
            directory = os.open(
                segment,
                os.O_RDONLY | os.O_DIRECTORY | _CLOEXEC | _NOFOLLOW | _NONBLOCK,
                dir_fd=parent_descriptor,
            )
            if parent_descriptor != root_descriptor:
                os.close(parent_descriptor)
            parent_descriptor = directory

        source_descriptor = os.open(
            segments[-1],
            os.O_RDONLY | _CLOEXEC | _NOFOLLOW | _NONBLOCK,
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        return _observation_error(error)
    finally:
        if parent_descriptor >= 0 and parent_descriptor != root_descriptor:
            os.close(parent_descriptor)
        if root_descriptor >= 0:
            os.close(root_descriptor)

    try:
        source_stat = os.fstat(source_descriptor)
        return _read_bounded_regular_file(source_descriptor, source_stat, byte_limit)
    finally:
        os.close(source_descriptor)


def observe_source(
    worktree_root: os.PathLike[str] | str,
    relative_path: str,
    *,
    byte_limit: int,
) -> SourceObservation:
    """Observe one bounded, contained, ordinary regular file.

    The worktree root must already be explicit and absolute.  Directory and
    file components are opened with `O_NOFOLLOW`, the final file with
    `O_NONBLOCK`, and the file type and link count are checked by descriptor
    rather than by its lexical manifest spelling.
    """
    try:
        return _observe_relative_path(worktree_root, relative_path, byte_limit)
    except OSError as error:
        return _observation_error(error)


def _compare_provenance(
    before: SourceObservation | None,
    after: SourceObservation,
) -> CaptureProvenance:
    if before is None:
        return CaptureProvenance.UNKNOWN
    if before.status is SourceStatus.ABSENT:
        if after.status in {SourceStatus.PERMITTED, SourceStatus.OVERSIZED}:
            return CaptureProvenance.NEW
        if after.status is SourceStatus.ABSENT:
            return CaptureProvenance.UNCHANGED
        return CaptureProvenance.UNKNOWN
    if before.status is SourceStatus.OVERSIZED:
        if after.status is SourceStatus.OVERSIZED:
            if before.metadata_digest == after.metadata_digest:
                return CaptureProvenance.UNCHANGED
            return CaptureProvenance.CHANGED
        if after.status is SourceStatus.PERMITTED:
            return CaptureProvenance.CHANGED
        return CaptureProvenance.UNKNOWN
    if before.status is SourceStatus.PERMITTED:
        if (
            after.status is SourceStatus.PERMITTED
            and before.digest == after.digest
            and before.metadata_digest == after.metadata_digest
        ):
            return CaptureProvenance.UNCHANGED
        return CaptureProvenance.CHANGED
    return CaptureProvenance.UNKNOWN


def capture_source(
    worktree_root: os.PathLike[str] | str,
    relative_path: str,
    *,
    byte_limit: int,
    baseline: SourceObservation | None = None,
) -> SourceCapture:
    """Capture a bounded source and compare it with its pre-gate observation.

    `baseline=None` is an explicitly unavailable observation and produces
    `UNKNOWN`, never a claim that presence means the gate just produced the
    file.  Any observable rewrite between observations is refused as unstable,
    including an oversized baseline that later becomes within-bound.
    """
    after = observe_source(worktree_root, relative_path, byte_limit=byte_limit)
    provenance = _compare_provenance(baseline, after)
    if provenance is CaptureProvenance.CHANGED:
        status = SourceStatus.UNSTABLE
        bounded_bytes = None
        size = after.size
        digest = None
        reason = "source changed between observations"
    elif baseline is not None and baseline.status is SourceStatus.UNSTABLE:
        status = SourceStatus.UNSTABLE
        bounded_bytes = None
        size = after.size
        digest = None
        reason = "baseline changed during its observation"
    else:
        status = after.status
        bounded_bytes = after.bytes
        size = after.size
        digest = after.digest
        reason = after.reason

    return SourceCapture(
        status=status,
        provenance=provenance,
        bytes=bounded_bytes,
        size=size,
        digest=digest,
        metadata_digest=after.metadata_digest,
        reason=reason,
        pre_status=(
            baseline.status if baseline is not None else SourceStatus.UNAVAILABLE
        ),
        post_status=after.status,
    )
