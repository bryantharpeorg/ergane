"""US2: the one-time load procedure in docs matches the shipped profile.

spec US2-S4, FR-010, plan T7.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = REPO_ROOT / "container" / "ergane-bwrap.apparmor"
README_PATH = REPO_ROOT / "README.md"
ONRAMP_PATH = REPO_ROOT / "docs" / "onramp.html"


def _normalize_profile(text: str) -> str:
    """Strip AppArmor comment lines and leading/trailing blank lines."""
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        if stripped:
            lines.append(stripped.rstrip(",").rstrip(";"))
    return "\n".join(lines)


def _extract_html_procedure(html_text: str) -> str:
    """Pull the printf arguments from the onramp HTML code block."""
    # Find the pre block that contains the printf and apparmor_parser.
    match = re.search(
        r"printf '%s\\n'\s+(.*?)\|.*?apparmor_parser",
        html_text,
        re.DOTALL,
    )
    if not match:
        return ""
    args = match.group(1)
    # Each printf argument is a single-quoted string, possibly split across lines.
    # Remove escapes produced by HTML encoding.
    args = args.replace("\\n", "\n").replace("\\t", "\t")
    args = args.replace("&lt;", "<")
    args = args.replace("&gt;", ">")
    args = args.replace("\\'", "'")
    # Split by unescaped single quotes.
    pieces = re.findall(r"'((?:[^'\\]|\\.)*)'", args)
    # Collapse whitespace inside each piece.
    normalized = [" ".join(piece.split()) for piece in pieces]
    return "\n".join(line for line in normalized if line)


def _extract_readme_procedure(md_text: str) -> str:
    """Pull the printf arguments from the README fenced code block."""
    # Find a ```bash ... ``` block containing printf and apparmor_parser.
    match = re.search(
        r"```bash\s+(.*?)```",
        md_text,
        re.DOTALL,
    )
    if not match:
        return ""
    block = match.group(1)
    if "printf" not in block or "apparmor_parser" not in block:
        return ""
    args_match = re.search(
        r"printf '%s\\n'\s+(.*?)\|",
        block,
        re.DOTALL,
    )
    if not args_match:
        return ""
    args = args_match.group(1)
    args = args.replace("\\n", "\n").replace("\\t", "\t")
    pieces = re.findall(r"'((?:[^'\\]|\\.)*)'", args)
    normalized = [" ".join(piece.split()) for piece in pieces]
    return "\n".join(line for line in normalized if line)


def test_onramp_procedure_matches_shipped_profile() -> None:
    assert PROFILE_PATH.exists()
    profile_text = _normalize_profile(PROFILE_PATH.read_text())
    html_text = ONRAMP_PATH.read_text()
    procedure_text = _normalize_profile(_extract_html_procedure(html_text))
    assert procedure_text, "could not extract profile procedure from docs/onramp.html"
    assert procedure_text == profile_text, (
        "docs/onramp.html procedure does not match the shipped profile"
    )


def test_readme_procedure_matches_shipped_profile() -> None:
    assert PROFILE_PATH.exists()
    profile_text = _normalize_profile(PROFILE_PATH.read_text())
    md_text = README_PATH.read_text()
    procedure_text = _normalize_profile(_extract_readme_procedure(md_text))
    assert procedure_text, "could not extract profile procedure from README.md"
    assert procedure_text == profile_text, (
        "README.md procedure does not match the shipped profile"
    )
