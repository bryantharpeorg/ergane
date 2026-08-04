"""Materialise `tests/fixtures/target_repo/` as a real git repository.

The gate runner and the diff check both read a *node worktree*: a directory with
a committed `factory.yaml`, tracked files to modify, and a `HEAD` to diff against.
None of that can be committed into this repository as-is — a nested `.git` is not
a thing git stores — so the fixture ships as plain files and this module builds
the repo from them under `tmp_path`, one fresh repo per test.

Two things this does that a bare `git init` would not, both of them about tests
that pass on the author's laptop and fail on someone else's:

- **The operator's git configuration is not consulted.** `GIT_CONFIG_GLOBAL` and
  `GIT_CONFIG_SYSTEM` point at `/dev/null`, and identity, branch name and commit
  dates are supplied explicitly. A machine with `commit.gpgsign = true`, a
  `core.hooksPath`, or `init.defaultBranch = trunk` builds byte-identical repos.
- **Variants differ by exactly one file.** Every variant is the same skeleton with
  a different manifest — or, for `missing-manifest`, with none. A fixture where
  the failing case also had different sources would leave "which difference
  mattered?" to the reader.

`manifests/` is fixture bookkeeping rather than repo content, so it is left out of
the built repo; everything else in the fixture directory is copied and committed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "target_repo"

#: Directory of variant manifests — bookkeeping, never copied into a built repo.
MANIFEST_DIR = FIXTURE_ROOT / "manifests"

#: The committed manifest's filename at the repo root (contracts/factory-yaml.md).
MANIFEST_NAME = "factory.yaml"

#: Gate scripts append their name here; gitignored, so running gates leaves the
#: worktree clean and gate evidence never masquerades as agent work.
GATE_ORDER_LOG = ".factory-gate-order.log"

#: Variant → the manifest the built repo ends up with. `MANIFEST_NAME` means the
#: fixture's own committed `factory.yaml` (so the fixture directory reads as the
#: target repo it stands in for); `None` means no manifest at all, which is the
#: missing-manifest CONFIG_ERROR case; anything else names a file in `manifests/`.
VARIANTS: dict[str, str | None] = {
    "passing": MANIFEST_NAME,
    "missing-manifest": None,
    "failing-gate": "failing-gate.yaml",
    "hanging-gate": "hanging-gate.yaml",
    "sigterm-defying-gate": "sigterm-defying-gate.yaml",
    "noisy-gate": "noisy-gate.yaml",
    "env-probe": "env-probe.yaml",
    "malformed-manifest": "malformed.yaml",
    "unknown-gate": "unknown-gate.yaml",
}

DEFAULT_BRANCH = "main"

#: Fixed so commit hashes are reproducible across machines and runs.
_FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"
_FIXTURE_IDENTITY = ("Ergane Fixture", "fixture@ergane.invalid")


def git_env() -> dict[str, str]:
    """A git environment that ignores whatever the host operator has configured."""
    name, email = _FIXTURE_IDENTITY
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        # HOME still matters to git even with the config files silenced; point it
        # somewhere harmless rather than at the operator's home directory.
        "HOME": os.devnull,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_AUTHOR_DATE": _FIXTURE_TIMESTAMP,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_COMMITTER_DATE": _FIXTURE_TIMESTAMP,
        "GIT_TERMINAL_PROMPT": "0",
    }


def git(repo: Path, *args: str) -> str:
    """Run one git command in `repo`, returning stdout; raises on failure."""
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=git_env(),
        check=True,
    )
    return completed.stdout


def build_target_repo(dest: Path, variant: str = "passing") -> Path:
    """Copy the fixture skeleton to `dest` and commit it as a git repo.

    Returns `dest`, which is a repository with one commit on `main` containing
    every fixture file plus the variant's manifest.
    """
    if variant not in VARIANTS:
        known = ", ".join(sorted(VARIANTS))
        raise KeyError(f"unknown target-repo variant {variant!r}; known: {known}")

    shutil.copytree(
        FIXTURE_ROOT,
        dest,
        ignore=shutil.ignore_patterns(MANIFEST_DIR.name, "__pycache__"),
    )

    manifest = dest / MANIFEST_NAME
    source = VARIANTS[variant]
    if source is None:
        manifest.unlink()
    elif source != MANIFEST_NAME:
        shutil.copyfile(MANIFEST_DIR / source, manifest)

    git(dest, "init", "-b", DEFAULT_BRANCH, "--quiet")
    git(dest, "add", "-A")
    git(dest, "commit", "--quiet", "-m", f"Fixture target repo ({variant})")
    return dest


def add_worktree(repo: Path, path: Path, branch: str = "node/work") -> Path:
    """Attach a node worktree on a new branch — the shape a node actually gets.

    Gates run and diffs are read in a worktree, not in the repo's own checkout, so
    tests that skip this step would be testing a topology the factory never uses.
    """
    git(repo, "worktree", "add", "--quiet", "-b", branch, str(path))
    return path


def gate_order(worktree: Path) -> list[str]:
    """Gate names in the order their scripts actually ran (see gates/README.md)."""
    log = worktree / GATE_ORDER_LOG
    if not log.exists():
        return []
    return log.read_text(encoding="utf-8").split()
