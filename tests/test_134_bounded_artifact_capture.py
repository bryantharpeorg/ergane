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
