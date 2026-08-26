"""US1: first-boot driver for the Ergane demo.

This module runs once, the first time a demo container starts with
``ERGANE_DEMO=1``. It installs the control plane, scaffolds a throwaway
repository, commits the result, probes that the bubblewrap sandbox can actually
start, and records that first boot happened.

The module is runnable as ``python3 -m factory.supervision.demo_driver`` so the
supervisor can spawn it with the same argv convention the supervisor already
uses. As elsewhere in this tree, no assembled argv may contain the substring
``python -``, because a cleanup sweep ran ``pkill -f "python -"`` and matched
supervised children (container_supervisor.py:8-11).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from factory.cli import init as init_module
from factory.cli.install import (
    _demo_anchor,
    _demo_manifest_text,
    _run_cli,
    _spec_derive_argv,
    _spec_validate_argv,
)
from factory.doctor.scaffold import scaffold_spec
from factory.verify.toolchain import system_tree_argv

#: Where the state home sentinel lives.
DEMO_SENTINEL_REL = Path("demo") / "first-boot"

#: Where the dispatch sentinel lives (written before dispatch, FR-009).
DISPATCH_SENTINEL_REL = Path("demo") / "dispatched"

#: Demo git identity for the throwaway repository (FR-003).
DEMO_AUTHOR_NAME = "Ergane Demo"
DEMO_AUTHOR_EMAIL = "demo@ergane.invalid"

#: The bundled answer file path inside the container image.
DEFAULT_ANSWERS_FILE = Path("/opt/ergane/container/ergane-install-answer.demo.toml")

#: The demo repo path inside the container image.
DEFAULT_REPO_ROOT = Path("/home/ergane/repo")

#: Default sentinel line for an already-run driver.
ALREADY_BOOTED_LINE = "demo first boot already happened; doing nothing"

#: Remedy line printed when the sandbox probe refuses (FR-005).
PROBE_REFUSAL_REMEDY = (
    "remedy: add systempaths=unconfined to the engine service's security_opt; "
    "Docker's masked /proc paths refuse the fresh procfs mount the agent sandbox "
    "needs (bubblewrap#284)"
)


#: Type of an injected sandbox probe: argv in, (rc, stdout, stderr) out.
Probe = Callable[[list[str]], tuple[int, str, str]]


def _default_sandbox_probe(argv: list[str]) -> tuple[int, str, str]:
    """Run bwrap with the assembled argv and return outcome."""
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    return (completed.returncode, completed.stdout, completed.stderr)


def _sentinel_path(state_home: Path, rel: Path) -> Path:
    return state_home / rel


def _sentinel_exists(state_home: Path, rel: Path) -> bool:
    return _sentinel_path(state_home, rel).is_file()


def _write_sentinel(state_home: Path, rel: Path) -> None:
    path = _sentinel_path(state_home, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("done\n", encoding="utf-8")


def prepare_first_boot(
    state_home: Path,
    repo_root: Path,
    answers_file: Path,
    *,
    sandbox_probe: Probe | None = None,
) -> int:
    """Install, scaffold, commit, and probe. Returns 0 on success, nonzero on refusal.

    ``sandbox_probe`` is an injectable callable so tests can script refusal
    without running real bwrap.
    """
    if _sentinel_exists(state_home, DEMO_SENTINEL_REL):
        print(ALREADY_BOOTED_LINE)
        return 0

    # Step 1: install the control plane from the bundled answers.
    install_code = _install_runner(["install", "--from-file", str(answers_file)])
    if install_code != 0:
        print(f"demo driver: ergane install failed with status {install_code}", file=sys.stderr)
        return install_code

    # Step 2: initialise the demo repository.
    repo_root.mkdir(parents=True, exist_ok=True)
    _git_init(repo_root)

    # Step 3: write the manifest.
    manifest_text = _demo_manifest_text()
    init_module._write_scaffold(repo_root, manifest_text)

    # Step 4: write the spec trio under specs/001-demo/.
    anchor = _demo_anchor(repo_root)
    spec_text, plan_text, tasks_text = scaffold_spec(
        slug="demo",
        title="Demonstration",
        anchor=anchor,
        demonstration=True,
    )
    spec_dir = repo_root / "specs" / "001-demo"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (spec_dir / "plan.md").write_text(plan_text, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks_text, encoding="utf-8")

    # Step 5: git commit with an explicit demo identity (FR-003).
    _git_config_identity(repo_root)
    _git_commit(repo_root, "demo first boot")

    # Mark prepare complete before the expensive dispatch steps.
    _write_sentinel(state_home, DEMO_SENTINEL_REL)

    # Step 6: prove the sandbox can start before any dispatch (FR-005).
    probe = sandbox_probe or _default_sandbox_probe
    argv = _sandbox_probe_argv()
    rc, _stdout, stderr = probe(argv)
    if rc != 0:
        print(stderr, file=sys.stderr)
        print(PROBE_REFUSAL_REMEDY, file=sys.stderr)
        return 1

    return 0


def _git_init(repo_root: Path) -> None:
    """One git init for the throwaway demonstration repository."""
    subprocess.run(
        ["git", "-C", str(repo_root), "init", "-b", "main", "--quiet"],
        check=True,
    )


def _git_config_identity(repo_root: Path) -> None:
    """Set repo-local git identity so no global identity is needed."""
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.name", DEMO_AUTHOR_NAME],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.email", DEMO_AUTHOR_EMAIL],
        check=True,
    )


def _git_commit(repo_root: Path, message: str) -> None:
    """Stage and commit every file in the repository."""
    subprocess.run(
        ["git", "-C", str(repo_root), "add", "."],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "commit", "-m", message, "--quiet"],
        check=True,
    )


def _sandbox_probe_argv() -> list[str]:
    """Assemble an adapter-shaped bwrap probe.

    The probe mirrors the essential shape of the agent sandbox assembled at
    factory/workgraph/adapter.py:427-580: a fresh procfs mount inside a new user
    namespace. The measured failure on Docker's masked /proc is
    ``bwrap: Can't mount proc``; a probe without ``--proc`` would pass on a host
    where the real sandbox cannot start (plan T5).
    """
    argv: list[str] = ["bwrap"]
    argv.extend(system_tree_argv())
    argv.extend([
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--unshare-pid",
        "--die-with-parent",
        "--",
        "/usr/bin/true",
    ])
    return argv


def _state_home_from_env() -> Path:
    """Resolve the engine's state home from the environment or the usual default."""
    raw = os.environ.get("ERGANE_STATE_HOME") or os.environ.get("FACTORY_STATE_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".local" / "state" / "ergane"


#: Injectables for tests: module-level seams mirroring the CLI install path.
_install_runner: Callable[[list[str]], int] = _run_cli
_verify_runner: Callable[[list[str]], int] = _run_cli


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python3 -m factory.supervision.demo_driver``."""
    state_home = _state_home_from_env()
    repo_root = Path(os.environ.get("ERGANE_DEMO_REPO", str(DEFAULT_REPO_ROOT)))
    answers_file = Path(
        os.environ.get("ERGANE_DEMO_ANSWERS", str(DEFAULT_ANSWERS_FILE))
    )
    return prepare_first_boot(
        state_home=state_home,
        repo_root=repo_root,
        answers_file=answers_file,
    )


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
