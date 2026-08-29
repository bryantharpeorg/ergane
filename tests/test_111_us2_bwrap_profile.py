"""US2: the shipped bwrap AppArmor profile grants the right directives.

spec US2-S1, FR-006, FR-007.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = REPO_ROOT / "container" / "ergane-bwrap.apparmor"

_PROFILE_ATTACHMENT_RE = re.compile(
    r"profile\s+bwrap\s+/usr/bin/bwrap\s+flags=\(unconfined\)",
)


def _parse_grants(profile_text: str) -> list[str]:
    """Return the first-level capability/permission lines inside the profile block."""
    lines = profile_text.splitlines()
    in_block = False
    grants: list[str] = []
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("abi") or line.startswith("include"):
            continue
        if "{" in line:
            in_block = True
            continue
        if in_block and line == "}":
            break
        if in_block and line:
            grants.append(line.rstrip(",").rstrip(";"))
    return grants


def test_profile_exists_and_parses() -> None:
    assert PROFILE_PATH.exists(), f"profile not at {PROFILE_PATH}"
    text = PROFILE_PATH.read_text()
    assert _PROFILE_ATTACHMENT_RE.search(text), "profile must attach at /usr/bin/bwrap"
    grants = _parse_grants(text)
    assert "userns" in grants, "profile must grant userns"


def test_profile_without_userns_would_fail() -> None:
    """Companion negative case: losing the grant must break the check (plan T6)."""
    assert PROFILE_PATH.exists()
    text = PROFILE_PATH.read_text()
    grants = _parse_grants(text)
    assert "userns" in grants

    removed = text.replace("  userns,", "")
    removed_grants = _parse_grants(removed)
    assert "userns" not in removed_grants
