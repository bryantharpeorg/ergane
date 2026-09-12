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
        (_regular_file, "PERMITTED", None),
        (_escaping_symlink, "UNSAFE", b"UNRELATED OUTSIDE BYTES"),
        (_substituted_symlink, "UNSAFE", b"UNRELATED WORKTREE BYTES"),
        (_hardlink_alias, "UNSAFE", None),
        (_fifo, "UNSAFE", None),
        (_socket, "UNSAFE", None),
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
    if expected_status == "PERMITTED":
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

    assert observation.status.value == "PERMITTED"
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

    assert before_existing.status.value == "PERMITTED"
    assert capture_existing.status.value == "PERMITTED"
    assert capture_existing.provenance is CaptureProvenance.UNCHANGED
    assert capture_existing.bytes == existing.read_bytes()
    assert before_new.status.value == "ABSENT"
    assert capture_new.status.value == "PERMITTED"
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
        assert before.status.value == "OVERSIZED"
        path.write_bytes(after_bytes)

        capture = capture_source(
            tmp_path,
            relative_path,
            byte_limit=16,
            baseline=before,
        )

        assert capture.status.value == "UNSTABLE"
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

    assert before.status.value == "UNSAFE"
    assert capture.status.value == "PERMITTED"
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

    assert before.status.value == "PERMITTED"
    assert capture.status.value == "UNSTABLE"
    assert capture.provenance is CaptureProvenance.CHANGED
    assert capture.bytes is None
    assert capture.digest is None
    assert "changed between observations" in (capture.reason or "")
