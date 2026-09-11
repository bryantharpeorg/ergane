"""US6: one bounded, safe source-reading boundary for artifact capture."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import pytest

from factory.verify.artifact_capture import (
    CaptureProvenance,
    SourceStatus,
    capture_source,
    observe_source,
)


def _regular_file(root: Path, relative_path: str = "report.txt") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"stable bytes\n")
    return path


def _escaping_symlink(root: Path, outside: Path) -> str:
    outside.write_bytes(b"UNRELATED OUTSIDE BYTES\n")
    (root / "escaped").symlink_to(outside, target_is_directory=False)
    return "escaped"


def _substituted_symlink(root: Path) -> str:
    (root / "substituted").symlink_to(
        root / "ordinary.txt",
        target_is_directory=False,
    )
    (root / "ordinary.txt").write_bytes(b"UNRELATED WORKTREE BYTES\n")
    return "substituted"


def _hardlink_alias(root: Path) -> str:
    original = root / "alias-original"
    alias = root / "alias"
    original.write_bytes(b"alias bytes\n")
    os.link(original, alias)
    return "alias"


def _fifo(root: Path) -> str:
    os.mkfifo(root / "pipe")
    return "pipe"


def _socket(root: Path) -> str:
    import socket

    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(root / "socket"))
    listener.close()
    return "socket"


@pytest.mark.parametrize(
    ("make_source", "expected_status", "payload_marker"),
    [
        (_regular_file, SourceStatus.PERMITTED, None),
        (
            _escaping_symlink,
            SourceStatus.UNSAFE,
            b"UNRELATED OUTSIDE BYTES",
        ),
        (
            _substituted_symlink,
            SourceStatus.UNSAFE,
            b"UNRELATED WORKTREE BYTES",
        ),
        (_hardlink_alias, SourceStatus.UNSAFE, None),
        (_fifo, SourceStatus.UNSAFE, None),
        (_socket, SourceStatus.UNSAFE, None),
    ],
)
def test_regular_files_are_read_and_unsafe_sources_are_refused(
    tmp_path: Path,
    make_source: object,
    expected_status: SourceStatus,
    payload_marker: bytes | None,
) -> None:
    """US6-S1: lexical containment is checked again on the real file."""
    if make_source is _escaping_symlink:
        outside_root = tmp_path / "outside-root"
        outside_root.mkdir()
        relative_path = _escaping_symlink(tmp_path, outside_root / "outside")
    elif callable(make_source):
        made_path_or_name = make_source(tmp_path)
        relative_path = (
            made_path_or_name.relative_to(tmp_path).as_posix()
            if isinstance(made_path_or_name, Path)
            else made_path_or_name
        )
    else:
        pytest.fail("bad parametrization")

    observation = observe_source(tmp_path, relative_path, byte_limit=16)

    assert observation.status is expected_status
    assert observation.reason is not None or expected_status is SourceStatus.PERMITTED
    if payload_marker is not None:
        assert observation.bytes is None or payload_marker not in observation.bytes
    else:
        if expected_status is SourceStatus.PERMITTED:
            assert observation.bytes == b"stable bytes\n"
        else:
            assert observation.bytes is None


def test_the_regular_control_reads_the_exact_bounded_bytes(tmp_path: Path) -> None:
    """US6-S1/S3: only the named file is opened, and no bound is invented."""
    with pytest.MonkeyPatch.context() as patch:
        reads: list[bytes] = []
        real_read = os.read

        def counted_read(fd: int, amount: int) -> bytes:
            chunk = real_read(fd, amount)
            reads.append(chunk)
            return chunk

        patch.setattr(os, "read", counted_read)
        root = tmp_path
        path = root / "ergane-us6-regular-control"
        path.write_bytes(b"0123456789abcdef")

        observation = observe_source(root, path.name, byte_limit=16)

        assert observation.status is SourceStatus.PERMITTED
        assert observation.bytes == b"0123456789abcdef"
        assert observation.size == 16
        assert observation.digest == hashlib.sha256(b"0123456789abcdef").hexdigest()
        assert b"".join(reads) == b"0123456789abcdef"
        path.unlink(missing_ok=True)


def test_absence_and_the_stored_byte_limit_are_explicit(tmp_path: Path) -> None:
    """US6-S3: absent and exactly-bound files are distinct outcomes."""
    root = tmp_path
    absent_path = root / "ergane-us6-absent-control"
    bound_path = root / "ergane-us6-bound-control"
    absent_path.unlink(missing_ok=True)
    bound_path.write_bytes(b"x" * 16)

    absent = observe_source(root, absent_path.name, byte_limit=16)
    bounded = observe_source(root, bound_path.name, byte_limit=16)

    assert absent.status is SourceStatus.ABSENT
    assert absent.bytes is None and absent.reason == "path does not name a file"
    assert bounded.status is SourceStatus.PERMITTED
    assert bounded.bytes == b"x" * 16
    assert bounded.size == 16


def test_an_oversized_file_stops_reading_and_publishes_no_bytes(tmp_path: Path) -> None:
    """US6-S3: a stable oversized source is present, oversized and unpublished."""
    with pytest.MonkeyPatch.context() as patch:
        reads: list[bytes] = []
        real_read = os.read

        def counted_read(fd: int, amount: int) -> bytes:
            chunk = real_read(fd, amount)
            reads.append(chunk)
            return chunk

        patch.setattr(os, "read", counted_read)
        path = tmp_path / "ergane-us6-oversize-control"
        path.write_bytes(b"y" * 17)

        observation = observe_source(path.parent, path.name, byte_limit=16)

        assert observation.status is SourceStatus.OVERSIZED
        assert observation.bytes is None
        assert observation.size == 17
        assert sum(len(chunk) for chunk in reads) <= 17
        path.unlink()


def test_unchanged_and_new_files_have_honest_provenance(tmp_path: Path) -> None:
    """US6-S2: pre-gate absence or identity is carried, not inferred from presence."""
    existing = _regular_file(tmp_path, "unchanged.txt")
    relative_path = existing.relative_to(tmp_path).as_posix()
    before_existing = observe_source(tmp_path, relative_path, byte_limit=16)
    capture_existing = capture_source(
        tmp_path,
        relative_path,
        byte_limit=16,
        baseline=before_existing,
    )

    new = tmp_path / "new.txt"
    new.unlink(missing_ok=True)
    before_new = observe_source(tmp_path, "new.txt", byte_limit=16)
    new.write_bytes(b"fresh report\n")
    capture_new = capture_source(tmp_path, "new.txt", byte_limit=16, baseline=before_new)

    assert before_existing.status is SourceStatus.PERMITTED
    assert capture_existing.status is SourceStatus.PERMITTED
    assert capture_existing.provenance is CaptureProvenance.UNCHANGED
    assert capture_existing.bytes == existing.read_bytes()
    assert before_new.status is SourceStatus.ABSENT
    assert capture_new.status is SourceStatus.PERMITTED
    assert capture_new.provenance is CaptureProvenance.NEW
    assert capture_new.bytes == new.read_bytes()


def test_an_unavailable_baseline_does_not_certify_newness(tmp_path: Path) -> None:
    """US6-S2: an unsafe pre-gate source cannot be upgraded to fresh."""
    outside_root = tmp_path / "outside-root"
    outside_root.mkdir()
    outside = outside_root / "us6-unavailable-outside"
    relative_path = _escaping_symlink(tmp_path, outside)
    before = observe_source(tmp_path, relative_path, byte_limit=16)

    os.unlink(tmp_path / relative_path)
    (tmp_path / relative_path).write_bytes(b"new report\n")
    capture = capture_source(tmp_path, relative_path, byte_limit=16, baseline=before)

    assert before.status is SourceStatus.UNSAFE
    assert capture.status is SourceStatus.PERMITTED
    assert capture.provenance is CaptureProvenance.UNKNOWN
    assert capture.bytes == b"new report\n"


def test_capture_bounds_actual_reads_in_both_observation_phases(
    tmp_path: Path,
) -> None:
    """US6-S3: pre-gate and post-gate reads obey the caller's limit."""
    path = tmp_path / "twice-read.txt"
    path.write_bytes(b"0123456789abcdefg")

    with pytest.MonkeyPatch.context() as patch:
        real_read = os.read
        pre_reads: list[bytes] = []
        post_reads: list[bytes] = []

        def pre_read(fd: int, amount: int) -> bytes:
            chunk = real_read(fd, amount)
            pre_reads.append(chunk)
            return chunk

        def post_read(fd: int, amount: int) -> bytes:
            chunk = real_read(fd, amount)
            post_reads.append(chunk)
            return chunk

        patch.setattr(os, "read", pre_read)
        before = observe_source(tmp_path, "twice-read.txt", byte_limit=16)
        patch.setattr(os, "read", post_read)
        capture = capture_source(
            tmp_path,
            "twice-read.txt",
            byte_limit=16,
            baseline=before,
        )

    assert b"".join(pre_reads) == b"0123456789abcdefg"
    assert b"".join(post_reads) == b"0123456789abcdefg"
    assert before.status is SourceStatus.OVERSIZED
    assert capture.status is SourceStatus.OVERSIZED
    assert capture.provenance is CaptureProvenance.UNCHANGED
    assert capture.bytes is None


def test_mutation_during_capture_is_refused_without_partial_bytes(
    tmp_path: Path,
) -> None:
    """US6-S2/S3: a changed source is never published as a consistent snapshot."""
    path = _regular_file(tmp_path, "changing.txt")
    relative_path = path.relative_to(tmp_path).as_posix()
    before = observe_source(tmp_path, relative_path, byte_limit=16)
    with path.open("rb+") as source:
        source.write(b"COMPLETELY DIFFERENT")
        source.flush()

    capture = capture_source(
        tmp_path,
        relative_path,
        byte_limit=16,
        baseline=before,
    )

    assert before.status is SourceStatus.PERMITTED
    assert capture.status is SourceStatus.UNSTABLE
    assert capture.provenance is CaptureProvenance.CHANGED
    assert capture.bytes is None
    assert "changed between observations" in (capture.reason or "")


def test_growth_during_reading_is_refused_without_partial_bytes(
    tmp_path: Path,
) -> None:
    """US6-S3: bounded actual reads also detect a file that grows while read."""
    path = _regular_file(tmp_path, "growing.txt")
    with pytest.MonkeyPatch.context() as patch:
        real_read = os.read
        appended = False

        def grow_after_first_read(fd: int, amount: int) -> bytes:
            nonlocal appended
            chunk = real_read(fd, amount)
            if not appended:
                with path.open("ab") as growing:
                    growing.write(b"-more-")
                appended = True
            return chunk

        patch.setattr(os, "read", grow_after_first_read)
        capture = capture_source(
            tmp_path,
            path.relative_to(tmp_path).as_posix(),
            byte_limit=16,
        )

    assert capture.status is SourceStatus.UNSTABLE
    assert capture.provenance is CaptureProvenance.UNKNOWN
    assert capture.bytes is None
    assert "changed during reading" in (capture.reason or "")
