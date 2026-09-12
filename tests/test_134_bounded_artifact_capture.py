"""US6: one bounded, safe source-reading boundary for artifact capture."""

from __future__ import annotations

import hashlib
import os
import socket
from pathlib import Path

import pytest

from factory.verify.artifact_capture import observe_source


def _regular_file(root: Path, relative_path: str = "report.txt") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"stable bytes\n")
    return path


def _escaping_symlink(root: Path, outside: Path) -> str:
    outside.write_bytes(b"UNRELATED OUTSIDE BYTES\n")
    (root / "escaped").symlink_to(outside)
    return "escaped"


def _substituted_symlink(root: Path) -> str:
    (root / "ordinary.txt").write_bytes(b"UNRELATED WORKTREE BYTES\n")
    (root / "substituted").symlink_to(root / "ordinary.txt")
    return "substituted"


def _hardlink_alias(root: Path) -> str:
    original = root / "alias-original"
    original.write_bytes(b"alias bytes\n")
    os.link(original, root / "alias")
    return "alias"


def _fifo(root: Path) -> str:
    os.mkfifo(root / "pipe")
    return "pipe"


def _socket(root: Path) -> str:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(str(root / "socket"))
    finally:
        listener.close()
    return "socket"


@pytest.mark.parametrize(
    ("make_source", "expected_status", "payload_marker"),
    [
        (_regular_file, "permitted", None),
        (_escaping_symlink, "unsafe", b"UNRELATED OUTSIDE BYTES"),
        (_substituted_symlink, "unsafe", b"UNRELATED WORKTREE BYTES"),
        (_hardlink_alias, "unsafe", None),
        (_fifo, "unsafe", None),
        (_socket, "unsafe", None),
    ],
)
def test_regular_files_are_read_and_unsafe_sources_are_refused(
    tmp_path: Path,
    make_source,
    expected_status: str,
    payload_marker: bytes | None,
) -> None:
    """US6-S1: lexical containment is checked again on the real descriptor."""
    outside_marker = b"UNRELATED OUTSIDE BYTES"
    if make_source is _escaping_symlink:
        outside_root = tmp_path / "outside-root"
        outside_root.mkdir()
        outside = outside_root / "outside"
        outside.write_bytes(outside_marker)
        relative_path = _escaping_symlink(tmp_path, outside)
    else:
        result = make_source(tmp_path)
        relative_path = (
            result.relative_to(tmp_path).as_posix()
            if isinstance(result, Path)
            else result
        )

    observation = observe_source(tmp_path, relative_path, byte_limit=16)

    assert observation.status.value == expected_status
    if expected_status == "permitted":
        assert observation.bytes == b"stable bytes\n"
        assert observation.reason is None
    else:
        assert observation.bytes is None
        assert observation.reason is not None
        if payload_marker is not None:
            assert payload_marker not in (observation.bytes or b"")


def test_the_regular_control_reads_the_exact_bounded_bytes(tmp_path: Path) -> None:
    """US6-S1/S3: the named regular file is read to the exact caller bound."""
    with pytest.MonkeyPatch.context() as patch:
        reads: list[bytes] = []
        real_read = os.read

        def counted_read(fd: int, amount: int) -> bytes:
            chunk = real_read(fd, amount)
            reads.append(chunk)
            return chunk

        patch.setattr(os, "read", counted_read)
        path = tmp_path / "ergane-us6-regular-control"
        path.write_bytes(b"0123456789abcdef")

        observation = observe_source(tmp_path, path.name, byte_limit=16)

    assert observation.status.value == "permitted"
    assert observation.bytes == b"0123456789abcdef"
    assert observation.size == 16
    assert observation.digest == hashlib.sha256(b"0123456789abcdef").hexdigest()
    assert b"".join(reads) == b"0123456789abcdef"


def test_unchanged_and_new_files_have_honest_provenance(tmp_path: Path) -> None:
    """US6-S2: identity comes from the baseline, never from presence alone."""
    from factory.verify.artifact_capture import CaptureProvenance, capture_source

    existing = _regular_file(tmp_path, "unchanged.txt")
    relative_path = existing.relative_to(tmp_path).as_posix()
    before_existing = observe_source(tmp_path, relative_path, byte_limit=16)
    capture_existing = capture_source(
        tmp_path,
        relative_path,
        byte_limit=16,
        baseline=before_existing,
    )

    before_new = observe_source(tmp_path, "new.txt", byte_limit=16)
    new = tmp_path / "new.txt"
    new.write_bytes(b"fresh report\n")
    capture_new = capture_source(
        tmp_path,
        "new.txt",
        byte_limit=16,
        baseline=before_new,
    )

    assert before_existing.status.value == "permitted"
    assert capture_existing.status.value == "permitted"
    assert capture_existing.provenance is CaptureProvenance.UNCHANGED
    assert capture_existing.bytes == existing.read_bytes()
    assert before_new.status.value == "absent"
    assert capture_new.status.value == "permitted"
    assert capture_new.provenance is CaptureProvenance.NEW
    assert capture_new.bytes == b"fresh report\n"


def test_oversized_rewrites_are_changed_and_refuse_bytes(tmp_path: Path) -> None:
    """US6-S2: observable rewrites cannot become publishable snapshots.

    PR #528 returned the smaller rewrite as permitted.  The 17-to-8-byte case
    at a 16-byte limit is the regression control for that transition.
    """
    from factory.verify.artifact_capture import CaptureProvenance, capture_source

    cases = [(b"y" * 17, b"small"), (b"y" * 17, b"z" * 19)]
    for index, (before_bytes, after_bytes) in enumerate(cases):
        path = tmp_path / f"rewrite-{index}.txt"
        path.write_bytes(before_bytes)
        relative_path = path.relative_to(tmp_path).as_posix()
        before = observe_source(tmp_path, relative_path, byte_limit=16)
        assert before.status.value == "oversized"
        path.write_bytes(after_bytes)

        capture = capture_source(
            tmp_path,
            relative_path,
            byte_limit=16,
            baseline=before,
        )

        assert capture.status.value == "unstable"
        assert capture.provenance is CaptureProvenance.CHANGED
        assert capture.bytes is None
        assert capture.size == len(after_bytes)
        assert capture.digest is None


def test_a_baseline_unavailable_during_capture_does_not_certify_newness(
    tmp_path: Path,
) -> None:
    """US6-S2: an unusable baseline cannot upgrade unsafe freshness to new."""
    from factory.verify.artifact_capture import CaptureProvenance, capture_source

    outside_root = tmp_path / "outside-root"
    outside_root.mkdir()
    outside = outside_root / "unavailable"
    outside.write_bytes(b"UNRELATED OUTSIDE BYTES\n")
    relative_path = _escaping_symlink(tmp_path, outside)
    before = observe_source(tmp_path, relative_path, byte_limit=16)
    os.unlink(tmp_path / relative_path)
    path = tmp_path / relative_path
    path.write_bytes(b"new report\n")

    capture = capture_source(
        tmp_path,
        relative_path,
        byte_limit=16,
        baseline=before,
    )

    assert before.status.value == "unsafe"
    assert capture.status.value == "permitted"
    assert capture.provenance is CaptureProvenance.UNKNOWN
    assert capture.bytes == b"new report\n"


def test_mutation_during_capture_is_refused_without_partial_bytes(
    tmp_path: Path,
) -> None:
    """US6-S2: an unstable comparison is not published as a snapshot."""
    from factory.verify.artifact_capture import CaptureProvenance, capture_source

    path = _regular_file(tmp_path, "changing.txt")
    relative_path = path.relative_to(tmp_path).as_posix()
    before = observe_source(tmp_path, relative_path, byte_limit=16)
    path.write_bytes(b"COMPLETELY DIFFERENT")

    capture = capture_source(
        tmp_path,
        relative_path,
        byte_limit=16,
        baseline=before,
    )

    assert before.status.value == "permitted"
    assert capture.status.value == "unstable"
    assert capture.provenance is CaptureProvenance.CHANGED
    assert capture.bytes is None
    assert capture.digest is None
    assert "changed between observations" in (capture.reason or "")


def test_absence_and_the_stored_byte_limit_are_explicit(tmp_path: Path) -> None:
    """US6-S3: absence, an exact fit and oversize are distinct outcomes."""
    absent_path = tmp_path / "ergane-us6-absent-control"
    bounded_path = tmp_path / "ergane-us6-bound-control"
    bounded_path.write_bytes(b"x" * 16)

    absent = observe_source(tmp_path, absent_path.name, byte_limit=16)
    bounded = observe_source(tmp_path, bounded_path.name, byte_limit=16)

    assert absent.status.value == "absent"
    assert absent.bytes is None
    assert absent.reason == "path does not name a file"
    assert bounded.status.value == "permitted"
    assert bounded.bytes == b"x" * 16
    assert bounded.size == 16


def test_an_oversized_file_stops_reading_and_publishes_no_bytes(
    tmp_path: Path,
) -> None:
    """US6-S3: an oversized source is observed, not truncated."""
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

        observation = observe_source(tmp_path, path.name, byte_limit=16)

    assert observation.status.value == "oversized"
    assert observation.bytes is None
    assert observation.size == 17
    assert sum(len(chunk) for chunk in reads) <= 17


def test_capture_bounds_actual_reads_in_both_observation_phases(
    tmp_path: Path,
) -> None:
    """US6-S3: pre-gate and post-gate reads both obey the caller's limit."""
    from factory.verify.artifact_capture import CaptureProvenance, capture_source

    path = tmp_path / "twice-read.txt"
    path.write_bytes(b"0123456789abcdefg")
    relative_path = path.relative_to(tmp_path).as_posix()

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
        before = observe_source(tmp_path, relative_path, byte_limit=16)
        patch.setattr(os, "read", post_read)
        capture = capture_source(
            tmp_path,
            relative_path,
            byte_limit=16,
            baseline=before,
        )

    assert b"".join(pre_reads) == b"0123456789abcdefg"
    assert b"".join(post_reads) == b"0123456789abcdefg"
    assert before.status.value == "oversized"
    assert capture.status.value == "oversized"
    assert capture.provenance is CaptureProvenance.UNCHANGED
    assert capture.bytes is None


def test_growth_during_reading_is_refused_without_partial_bytes(
    tmp_path: Path,
) -> None:
    """US6-S3: growth during the bounded read is unstable, never partial."""
    from factory.verify.artifact_capture import CaptureProvenance, capture_source

    path = tmp_path / "growing.txt"
    path.write_bytes(b"stable bytes\n")
    relative_path = path.relative_to(tmp_path).as_posix()
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
        capture = capture_source(tmp_path, relative_path, byte_limit=16)

    assert capture.status.value == "unstable"
    assert capture.provenance is CaptureProvenance.UNKNOWN
    assert capture.bytes is None
    assert "changed during reading" in (capture.reason or "")
