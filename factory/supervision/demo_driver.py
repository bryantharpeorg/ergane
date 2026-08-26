"""US1/US2: one-shot demo driver spawned by the container supervisor.

The driver is **not** a supervised child.  It runs as a plain subprocess,
reaped by a task whose failure is logged and never fatal, because it blocks
on installs, git, and a long watch loop and must not run on the supervisor's
event loop.

Command lines assembled here intentionally avoid `python -`: a 2026-08-12
cleanup sweep ran `pkill -f "python -"` and matched the worker's own command
line (`factory/supervision/temporal_server.py:9-12`).  Using `python3 -m`
keeps the visible argv free of that substring.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

from factory.cli.install import _demo_manifest_text, _run_cli
from factory.doctor.scaffold import scaffold_spec

#: The two named factory seams the prepare phase reaches past `ergane` verbs for.
from factory.cli import init as init_module

#: Default paths inside the demo container.  The demo compose file mounts the
#: repo at this path and copies the answer file into the image at this path.
DEFAULT_DEMO_REPO_ROOT = Path("/home/ergane/repo")
DEFAULT_DEMO_ANSWERS = Path("/opt/ergane/container/ergane-install-answer.demo.toml")

#: Explicit git identity for the throwaway demo repository.  The container user
#: has no global git identity, and `build ship` creates worktrees from `main`,
#: so the demo repo needs at least one commit authored locally.
DEMO_AUTHOR_NAME = "Ergane Demo"
DEMO_AUTHOR_EMAIL = "demo@ergane.invalid"

#: Directory under the state home that holds the two first-boot sentinels.
DEMO_SENTINEL_DIR = Path("demo")

#: Sentinel written only after the sandbox probe succeeds.  A probe refusal
#: leaves this absent so a restart retries the probe.
PREPARED_SENTINEL = "prepared"

#: Sentinel written immediately before `build ship` so a crash window does not
#: re-spend the operator's key on restart.
DISPATCH_ATTEMPTED_SENTINEL = "dispatch-attempted"

#: bwrap binary path.  The container profile permits unprivileged user
#: namespaces only for the system binary at this path.
BWRAP_BINARY = Path("/usr/bin/bwrap")

#: Remedy line printed after a probe refusal, naming the mechanism so a stranger
#: who fixes their host by adding `systempaths=unconfined` recognises the fix.
SANDBOX_PROBE_REMEDY = (
    "remedy: the engine container needs systempaths=unconfined (bubblewrap#284); "
    "Docker's masked /proc paths trip the kernel's fully-visible-proc refusal "
    "when bwrap mounts a fresh procfs in its user namespace."
)


CliRunner = Callable[[list[str]], int]
ProbeRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _state_home() -> Path:
    """Resolve the engine state home, refusing to fall back to ambient defaults."""
    raw = os.environ.get("ERGANE_STATE_HOME") or os.environ.get("FACTORY_STATE_HOME")
    if raw:
        return Path(raw)
    raise RuntimeError(
        "ERGANE_STATE_HOME or FACTORY_STATE_HOME must be set in the container"
    )


def _sentinel_path(state_home: str | Path, name: str) -> Path:
    return Path(state_home) / DEMO_SENTINEL_DIR / name


def _prepared(state_home: str | Path) -> bool:
    return _sentinel_path(state_home, PREPARED_SENTINEL).is_file()


def _write_prepared(state_home: str | Path) -> None:
    sentinel = _sentinel_path(state_home, PREPARED_SENTINEL)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("first-boot prepare phase completed\n", encoding="utf-8")


def _dispatch_attempted(state_home: str | Path) -> bool:
    return _sentinel_path(state_home, DISPATCH_ATTEMPTED_SENTINEL).is_file()


def _write_dispatch_attempted(state_home: str | Path) -> None:
    sentinel = _sentinel_path(state_home, DISPATCH_ATTEMPTED_SENTINEL)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("build ship was attempted\n", encoding="utf-8")


def _git_checked(repo_root: Path, *args: str, env: dict[str, str] | None = None) -> None:
    """Run a git command and raise if it fails."""
    cmd = ["git", "-C", str(repo_root), *args]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {repo_root}: {completed.stderr.strip()}"
        )


def _git_config_env() -> dict[str, str]:
    """Return an environment that suppresses any inherited git identity."""
    base = dict(os.environ)
    base["GIT_CONFIG_GLOBAL"] = os.devnull
    base["GIT_CONFIG_SYSTEM"] = os.devnull
    return base


def _init_demo_repo(repo_root: Path) -> None:
    """Run git init on the persistent demo repo."""
    repo_root.mkdir(parents=True, exist_ok=True)
    env = _git_config_env()
    _git_checked(repo_root, "init", "-b", "main", "--quiet", env=env)


def _write_demo_manifest(repo_root: Path) -> None:
    """Write the same manifest text the interactive demonstration uses."""
    init_module._write_scaffold(repo_root, _demo_manifest_text())


def _write_demo_spec(repo_root: Path) -> None:
    """Write the demonstration spec trio under specs/001-demo/."""
    manifest_name = init_module.MANIFEST_NAME
    anchor = f"{manifest_name}:1"
    spec_text, plan_text, tasks_text = scaffold_spec(
        slug="demo",
        title="Demonstration",
        anchor=anchor,
        demonstration=True,
    )
    spec_dir = repo_root / "specs" / "001-demo"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (spec_dir / "plan.md").write_text(plan_text, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks_text, encoding="utf-8")


def _commit_demo_repo(repo_root: Path) -> None:
    """Commit the scaffolded demo repository under the explicit demo identity.

    Idempotent: if a commit already exists and the working tree is clean, this
    is a no-op.  A probe refusal leaves no sentinel, so a restart may reach here
    again; repeating the commit must not fail for lack of changes.
    """
    env = _git_config_env()
    # Set the identity for this repository only; no global identity is assumed.
    _git_checked(repo_root, "config", "user.name", DEMO_AUTHOR_NAME, env=env)
    _git_checked(repo_root, "config", "user.email", DEMO_AUTHOR_EMAIL, env=env)
    _git_checked(repo_root, "add", ".", env=env)

    # Skip the commit when there is nothing to commit, but still succeed when
    # this is the first commit.
    has_commits = (
        subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--quiet", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        ).returncode
        == 0
    )
    if has_commits:
        clean = (
            subprocess.run(
                ["git", "-C", str(repo_root), "diff-index", "--quiet", "HEAD", "--"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            ).returncode
            == 0
        )
        if clean:
            return

    _git_checked(
        repo_root,
        "commit",
        "--quiet",
        "-m",
        "demo: throwaway demonstration repository",
        env=env,
    )


def _build_sandbox_probe_argv() -> list[str]:
    """Assemble an adapter-shaped bwrap probe that mounts a fresh /proc.

    The probe must include `--proc`: the measured failure
    (`bwrap: Can't mount proc`) fires there and nowhere earlier.  The shape
    mirrors the agent boundary in `factory/workgraph/adapter.py:427-580`: a
    read-only system tree, `--proc /proc`, `--dev /dev`, `--unshare-pid`,
    `--die-with-parent`, and read-only toolchain-root binds.
    """
    argv: list[str] = [str(BWRAP_BINARY)]

    # Minimal read-only system tree.  We do not import the full toolchain
    # discovery here because the probe only needs to exercise /proc mounting;
    # the read-only `/usr` bind is enough to mirror the adapter's system-tree
    # shape while keeping the driver free of factory internals beyond the two
    # named seams for the prepare phase itself.
    argv.extend(["--ro-bind", "/usr", "/usr"])
    for mirrored in ("/bin", "/lib", "/lib64", "/sbin"):
        target = Path(mirrored)
        if target.is_symlink():
            argv.extend(["--symlink", os.readlink(target), mirrored])
        elif (Path("/usr") / mirrored.lstrip("/")).is_dir():
            argv.extend(["--symlink", "/usr" + mirrored, mirrored])

    # Runtime pseudo-filesystems: the probe must try to mount proc.
    argv.extend(["--proc", "/proc", "--dev", "/dev"])

    # Read-only binds of the toolchain roots the adapter would bind.  We bind
    # the common directories rather than resolving per-host paths, because the
    # point is to exercise the namespace/proc mount, not to run the agent.
    for bind in ("/opt/ergane", "/home"):
        if Path(bind).is_dir():
            argv.extend(["--ro-bind", bind, bind])

    # Process/signal boundary.
    argv.extend(["--unshare-pid", "--die-with-parent"])

    # The probe payload: a no-op that exits successfully if the namespace works.
    argv.extend(["--", "/bin/true"])
    return argv


def _default_probe_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=argv,
            returncode=1,
            stdout="",
            stderr=f"{argv[0]}: not found on this host",
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=argv,
            returncode=1,
            stdout=exc.stdout or "",
            stderr="sandbox probe timed out",
        )


def prepare_phase(
    state_home: str | Path,
    repo_root: str | Path,
    answers_path: str | Path,
    *,
    run_cli: CliRunner,
    run_probe: ProbeRunner | None = None,
) -> int:
    """Run the first-boot prepare phase and prove the sandbox can start.

    Order (FR-002):
      1. `ergane install --from-file <answers>`
      2. `git init -b main` of the demo repository
      3. manifest via `_demo_manifest_text` / `init_module._write_scaffold`
      4. spec trio via `scaffold_spec(..., demonstration=True)` under `specs/001-demo/`
      5. one git commit under the explicit demo identity
      6. sandbox probe; on refusal print stderr + remedy and return nonzero
      7. write the `prepared` sentinel

    The `prepared` sentinel is written only after the probe succeeds (FR-006),
    so a probe refusal leaves no sentinel and a restart retries.
    """
    if _prepared(state_home):
        print("first boot already happened; the demo project is prepared")
        return 0

    run_probe = run_probe or _default_probe_runner
    repo = Path(repo_root)

    # 1. Install the control plane from the bundled answers.
    code = run_cli(["install", "--from-file", str(answers_path)])
    if code != 0:
        print(f"demo driver: ergane install exited {code}; stopping", file=sys.stderr)
        return code

    # 2. Initialize the persistent demo repository.
    _init_demo_repo(repo)

    # 3. Write the manifest.
    _write_demo_manifest(repo)

    # 4. Write the demonstration spec trio.
    _write_demo_spec(repo)

    # 5. Commit everything under the explicit demo identity.
    _commit_demo_repo(repo)

    # 6. Prove the sandbox can start before any dispatch.
    probe_argv = _build_sandbox_probe_argv()
    probe = run_probe(probe_argv)
    if probe.returncode != 0:
        print(probe.stderr)
        print(SANDBOX_PROBE_REMEDY)
        return probe.returncode if probe.returncode != 0 else 1

    # 7. Record that prepare completed successfully.
    _write_prepared(state_home)
    print("demo: prepared repository and sandbox probe succeeded")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    state_home: str | Path | None = None,
    repo_root: str | Path | None = None,
    answers_path: str | Path | None = None,
    run_cli: CliRunner | None = None,
    run_probe: ProbeRunner | None = None,
) -> int:
    """Container entry point for the one-shot demo driver."""
    if state_home is None:
        state_home = _state_home()
    if repo_root is None:
        repo_root = DEFAULT_DEMO_REPO_ROOT
    if answers_path is None:
        answers_path = DEFAULT_DEMO_ANSWERS
    if run_cli is None:
        run_cli = _run_cli
    if run_probe is None:
        run_probe = _default_probe_runner

    # A restart after successful prepare is a one-line no-op.
    if _prepared(state_home):
        print("first boot already happened; the demo project is prepared")
        return 0

    return prepare_phase(
        state_home,
        repo_root,
        answers_path,
        run_cli=run_cli,
        run_probe=run_probe,
    )
