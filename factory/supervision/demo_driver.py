"""110-US1: the one-shot demo driver the engine container spawns on first boot.

The demo compose project (`container/compose.demo.yaml`) hands a stranger a
running factory and nothing to build. This module is what fills that gap: with
`ERGANE_DEMO=1` the container supervisor spawns it as a plain subprocess once
the worker and the bridge are up, and it prepares a throwaway project the
factory can be pointed at — control plane installed from the bundled answers, a
git repository with a manifest and one demonstration spec, a commit, and a
proof that the agent sandbox can actually start on this host.

Three properties are deliberate and each one has a scar behind it:

- **It is not a supervised child.** The supervisor treats any child dying
  unprompted as a fault and stops the container naming it
  (`container_supervisor.py:418-426`), so a one-shot in the supervised set would
  kill the stack at the moment of success. It is spawned beside that set and
  merely reaped.
- **It is a subprocess, never an in-process call.** It blocks on an install, on
  git, and (in US2) on a long watch loop; running that on the supervisor's event
  loop is the shape that starved a Temporal heartbeat for 5m12s on 2026-08-24.
- **Its command line carries no `python -`.** Same reason the supervisor's does
  not: a cleanup sweep once ran `pkill -f "python -"` and matched a factory
  process (`container_supervisor.py:8-12`).

First boot is bounded by two sentinels under `$ERGANE_STATE_HOME/demo/`, and
they carry two different promises. `prepared` is written only *after* the
sandbox probe succeeds, so a probe refusal leaves nothing behind and a stranger
who fixes their host and restarts gets the demo rather than a permanent sulk.
`dispatch-attempted` (US2) is written *before* the dispatch verb, so a crash
between spending the stranger's key and recording that fact cannot re-spend it.
Merging them would collapse "retryable host problem" into "money was spent".
"""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from factory.cli import init as init_module
from factory.cli.install import (
    _demo_anchor,
    _demo_manifest_text,
    _git_init,
    _run_cli,
)
from factory.controlplane.config import resolve_config_path
from factory.doctor.scaffold import scaffold_spec
from factory.registry import resolve_state_home
from factory.verify.toolchain import (
    GIT,
    NODE,
    UV,
    SystemTreeError,
    ToolchainError,
    resolve_toolchain,
    system_tree_argv,
)
from factory.workgraph.adapter import BWRAP_BACKEND_BINARY

#: The environment flag that opts a container into the demo (FR-001).
DEMO_ENV_VAR = "ERGANE_DEMO"

#: The bundled answers file, at the path the image copies the repository to.
DEFAULT_ANSWERS_PATH = Path("/opt/ergane/container/ergane-install-answer.demo.toml")

#: The throwaway repository's path, declared here because the compose file
#: declares it: `ergane_repo:/home/ergane/repo` (`compose.demo.yaml:89`). Read
#: from a constant rather than derived from `HOME`, so the path the volume is
#: mounted at and the path the driver writes to cannot drift apart.
DEFAULT_REPO_PATH = Path("/home/ergane/repo")

#: The demonstration spec, as `scaffold_spec` names it and `build status` will.
DEMO_SPEC_SLUG = "demo"
DEMO_SPEC_TITLE = "Demonstration"
DEMO_SPEC_DIRNAME = "001-demo"

#: The commit identity, explicit because the container user has none. Deriving
#: it from the environment is what makes the first commit fail with "Please tell
#: me who you are" on a host that never ran `git config --global`.
DEMO_GIT_NAME = "Ergane Demo"
DEMO_GIT_EMAIL = "demo@ergane.invalid"

#: Sentinel directory and the two sentinel names (FR-006).
DEMO_STATE_DIRNAME = "demo"
PREPARED_SENTINEL = "prepared"
DISPATCH_SENTINEL = "dispatch-attempted"

#: The one remedy line a sandbox refusal prints under the probe's own stderr.
#: Docker masks parts of `/proc`, and the kernel refuses a fresh procfs mount in
#: a user namespace unless the existing one is fully visible (bubblewrap#284),
#: which is exactly what the agent sandbox does on every dispatch.
SANDBOX_REMEDY = (
    "remedy: the agent sandbox needs an unmasked /proc. Run this project with "
    "`security_opt: [systempaths=unconfined]` on the engine service — it is "
    "already set in container/compose.demo.yaml — and make sure unprivileged "
    "user namespaces are enabled on the host "
    "(`sysctl kernel.unprivileged_userns_clone=1`)."
)

#: Prefix on every line the driver prints, so its narration is legible in the
#: interleaved `docker compose up` stream.
_PREFIX = "ergane demo:"


def _emit(line: str) -> None:
    """Print one narration line, flushed: the container log is a pipe."""
    print(f"{_PREFIX} {line}", flush=True)


@dataclass(frozen=True)
class ProbeOutcome:
    """What the sandbox probe found: whether it started, and what it said."""

    ok: bool
    stderr: str


def demo_state_dir(state_home: Path | str) -> Path:
    """The directory both sentinels live in."""
    return Path(state_home) / DEMO_STATE_DIRNAME


def sentinel_path(state_home: Path | str, name: str) -> Path:
    """The path of one named sentinel under the state home."""
    return demo_state_dir(state_home) / name


def write_sentinel(state_home: Path | str, name: str) -> Path:
    """Write one sentinel, creating the demo state directory if it is absent."""
    path = sentinel_path(state_home, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def sandbox_probe_argv(
    *,
    system_root: Path | str = Path("/"),
    binary: Path | str = BWRAP_BACKEND_BINARY,
) -> list[str]:
    """Assemble an adapter-shaped `bwrap` invocation that runs `true` and exits.

    The shape mirrors `factory/workgraph/adapter.py:427-580`: the environment is
    built rather than inherited, the system tree is read off this host, `/proc`
    and `/dev` are mounted fresh, the toolchain is bound read-only, and the
    process gets its own PID namespace and dies with its parent.

    `--proc` is the load-bearing token. The measured failure on 2026-08-26 —
    `bwrap: Can't mount proc on /newroot/proc` — fires at the fresh procfs mount
    and *nowhere earlier*, so a probe of `bwrap true` without `--unshare-pid
    --proc` passes cheerfully on a host where no agent can start.

    The toolchain is resolved as optional here, unlike in the adapter, because
    this probe answers one question — can bwrap build a namespace on this host —
    and a missing `node` is a different refusal that the adapter already makes
    by name at dispatch. Binding what is present keeps the mount set honest
    without inventing a second toolchain gate.
    """
    tools = resolve_toolchain(
        (UV, NODE, GIT),
        purpose="the demo sandbox probe",
        optional=(UV, NODE, GIT),
    )

    argv: list[str] = [str(binary), "--clearenv"]
    argv.extend(system_tree_argv(system_root))
    argv.extend(["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"])
    for tool in tools:
        source, dest = tool.bind
        argv.extend(["--ro-bind", source, dest])
    argv.extend(["--unshare-pid", "--die-with-parent"])
    argv.extend(["--", "/usr/bin/true"])
    return argv


def run_sandbox_probe(argv: Sequence[str]) -> ProbeOutcome:
    """Run the assembled probe, returning its verdict and its own stderr."""
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except OSError as error:
        return ProbeOutcome(ok=False, stderr=f"{argv[0]}: {error}")
    except subprocess.TimeoutExpired:
        return ProbeOutcome(
            ok=False, stderr=f"{argv[0]}: probe did not finish within 60s"
        )
    return ProbeOutcome(ok=completed.returncode == 0, stderr=completed.stderr.strip())


def _commit_demo_project(repo_root: Path) -> str:
    """Stage everything and commit it under the repo's own declared identity.

    The identity is written into the repository's config and used from there:
    the container user has no global one, and every later git operation on this
    repository — the worktrees a dispatch creates, the salvage commit a
    terminated node makes — needs one too.
    """
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.name", DEMO_GIT_NAME],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.email", DEMO_GIT_EMAIL],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True)

    staged = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--cached", "--quiet"],
    )
    if staged.returncode == 0:
        return "nothing to commit; the demonstration project is already committed"

    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "commit",
            "--quiet",
            "-m",
            "The demonstration project, prepared on first boot",
        ],
        check=True,
    )
    return f"committed the demonstration project as {DEMO_GIT_NAME} <{DEMO_GIT_EMAIL}>"


def _write_demo_spec(repo_root: Path) -> Path:
    """Write the demonstration spec trio under `specs/001-demo/`."""
    spec_text, plan_text, tasks_text = scaffold_spec(
        slug=DEMO_SPEC_SLUG,
        title=DEMO_SPEC_TITLE,
        anchor=_demo_anchor(repo_root),
        demonstration=True,
    )
    spec_dir = repo_root / "specs" / DEMO_SPEC_DIRNAME
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (spec_dir / "plan.md").write_text(plan_text, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks_text, encoding="utf-8")
    return spec_dir


def run_prepare_phase(
    *,
    state_home: Path | str,
    repo_root: Path | str,
    answers_path: Path | str = DEFAULT_ANSWERS_PATH,
    run_cli: Callable[[Sequence[str]], int] = _run_cli,
    probe: Callable[[Sequence[str]], ProbeOutcome] = run_sandbox_probe,
    emit: Callable[[str], None] = _emit,
) -> int:
    """Install, scaffold, commit, and prove the sandbox — once (FR-002…FR-006).

    Returns 0 when the demonstration project is dispatchable and the sandbox
    started, and nonzero on a refusal. Nothing here dispatches: a nonzero return
    means the caller must stop *before* any spend, which is why the probe runs
    at the end of this phase rather than at the start of the next one.
    """
    state_home = Path(state_home)
    repo_root = Path(repo_root)
    answers_path = Path(answers_path)

    prepared = sentinel_path(state_home, PREPARED_SENTINEL)
    if prepared.is_file():
        emit(f"first boot already happened ({prepared}); nothing to prepare")
        return 0

    emit("first boot preparing the demonstration project")

    # 1. The control plane, from the bundled answers, through the CLI verb.
    config_path = resolve_config_path()
    emit(f"step 1/5 ergane install --from-file {answers_path}")
    install_status = run_cli(["install", "--from-file", str(answers_path)])
    if not config_path.is_file():
        emit(
            f"refusing: `ergane install` wrote no configuration at {config_path} "
            f"(exit {install_status}); the transcript above says why"
        )
        return 1
    if install_status != 0:
        # Install's exit code is control-plane *verification*, not whether the
        # config was written: an unauthenticated `gh` is a FAIL and is also the
        # normal state of a demo container. The configuration is what the rest
        # of this phase needs, and it exists.
        emit(
            f"control-plane verification reported findings (exit {install_status}); "
            f"the configuration was written, so preparation continues"
        )

    # 2. The throwaway repository.
    repo_root.mkdir(parents=True, exist_ok=True)
    _git_init(repo_root)
    emit(f"step 2/5 git init -b main {repo_root}")

    # 3. The manifest, from the same text the install demonstration writes.
    init_module._write_scaffold(repo_root, _demo_manifest_text())
    emit(f"step 3/5 wrote {repo_root / init_module.MANIFEST_NAME}")

    # 4. The demonstration spec trio.
    spec_dir = _write_demo_spec(repo_root)
    emit(f"step 4/5 wrote {spec_dir}")

    # 5. The commit, under an identity this container declares for itself.
    emit(f"step 5/5 {_commit_demo_project(repo_root)}")

    # The sandbox, before anything can be dispatched into it.
    try:
        argv = sandbox_probe_argv()
    except (ToolchainError, SystemTreeError) as refusal:
        emit(f"refusing: the agent sandbox cannot be assembled on this host\n{refusal}")
        emit(SANDBOX_REMEDY)
        return 1

    outcome = probe(argv)
    if not outcome.ok:
        emit("refusing: the agent sandbox could not start on this host")
        if outcome.stderr:
            print(outcome.stderr, flush=True)
        emit(SANDBOX_REMEDY)
        return 1
    emit("agent sandbox probe succeeded")

    sentinel = write_sentinel(state_home, PREPARED_SENTINEL)
    emit(f"first boot complete; {sentinel}")
    return 0


def _default_state_home() -> Path:
    """The state home this container declares, or the resolver's default."""
    declared = os.environ.get("ERGANE_STATE_HOME")
    return Path(declared) if declared else Path(resolve_state_home())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and drive the Ergane demonstration project."
    )
    parser.add_argument(
        "--state-home",
        default=None,
        help="Where the first-boot sentinels live; defaults to ERGANE_STATE_HOME",
    )
    parser.add_argument(
        "--repo",
        default=str(DEFAULT_REPO_PATH),
        help=f"The demonstration repository (default: {DEFAULT_REPO_PATH})",
    )
    parser.add_argument(
        "--answers-file",
        default=str(DEFAULT_ANSWERS_PATH),
        help=f"Install answer file (default: {DEFAULT_ANSWERS_PATH})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python3 -m factory.supervision.demo_driver`."""
    args = _build_parser().parse_args(argv)
    state_home = Path(args.state_home) if args.state_home else _default_state_home()
    return run_prepare_phase(
        state_home=state_home,
        repo_root=Path(args.repo),
        answers_path=Path(args.answers_file),
    )


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
