"""US2: the bwrap path-pin comments are corrected, not removed.

spec US2-S2, US2-S3, FR-008, FR-009, plan T3.
"""

from __future__ import annotations

from pathlib import Path

from factory.controlplane.verify import _BWRAP_PINNED_PATH
from factory.workgraph.adapter import BWRAP_BACKEND_BINARY

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / "factory" / "workgraph" / "adapter.py"
VERIFY_PATH = REPO_ROOT / "factory" / "controlplane" / "verify.py"
PROFILE_PATH = REPO_ROOT / "container" / "ergane-bwrap.apparmor"

_DIST_ATTRIBUTION_PHRASES = (
    "Ubuntu",
    "Ubuntu 24.04",
    "distribution",
    "ships the profile",
    "stock profile",
)


def _comment_block(path: Path) -> str:
    text = path.read_text()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "bwrap" in line.lower() and "pinned" in line.lower():
            block = [line]
            for j in range(i + 1, min(i + 5, len(lines))):
                if lines[j].strip().startswith("#") or lines[j].strip().startswith("#:"):
                    block.append(lines[j])
                else:
                    break
            return "\n".join(block)
    return ""


def _adapter_comment() -> str:
    return _comment_block(ADAPTER_PATH)


def _verify_comment() -> str:
    return _comment_block(VERIFY_PATH)


def test_adapter_comment_does_not_attribute_grant_to_distribution() -> None:
    comment = _adapter_comment()
    assert comment, "adapter bwrap pin comment must exist"
    for phrase in _DIST_ATTRIBUTION_PHRASES:
        assert phrase.lower() not in comment.lower(), (
            f"adapter comment must not attribute the grant to a distribution: {phrase!r}"
        )


def test_adapter_comment_points_at_shipped_profile() -> None:
    comment = _adapter_comment()
    assert str(PROFILE_PATH.relative_to(REPO_ROOT)) in comment, (
        "adapter comment must name the committed profile's path"
    )


def test_verify_comment_does_not_attribute_grant_to_distribution() -> None:
    comment = _verify_comment()
    assert comment, "verify bwrap pin comment must exist"
    for phrase in _DIST_ATTRIBUTION_PHRASES:
        assert phrase.lower() not in comment.lower(), (
            f"verify comment must not attribute the grant to a distribution: {phrase!r}"
        )


def test_verify_comment_points_at_shipped_profile() -> None:
    comment = _verify_comment()
    assert str(PROFILE_PATH.relative_to(REPO_ROOT)) in comment, (
        "verify comment must name the committed profile's path"
    )


def test_pins_remain_at_system_bwrap() -> None:
    assert str(BWRAP_BACKEND_BINARY) == "/usr/bin/bwrap"
    assert str(_BWRAP_PINNED_PATH) == "/usr/bin/bwrap"
